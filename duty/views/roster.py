from datetime import date, timedelta
from urllib.parse import quote, urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .. import perms
from ..csv_io import split_names
from ..errors import DutyError
from ..models import Board, Department, Memo, RosterPref, User
from ..services import boards, changes, holidays, memos, prefs
from ..services.roster import find_day, member_schedule, published_days
from ..shifts import (
    DAY_LABELS, DEVELOPER, LUNCH, REASONS, SHIFT, SLOT, SLOT_GROUP, STAFF, by_key, cell_label, display_order, is_slot_cell,
    kind, lunch_defs, ordered, shift_defs, slot_defs,
)
from .common import date_param, int_param, safe_next


def _item(label: str, names: list[str], removed: bool = False, reasons: dict[str, str] | None = None) -> dict:
    """라벨(A, A>B>C, +B)을 이름 토큰으로 나눈다. 마지막 이름 앞은 취소선, hl은 검색어 번호(1..3).
    reason = 지금 배정된(마지막) 사람의 사유. 있으면 "이름(사유)" 전체를 긋고 옅은 회색(변경 내역을 끄면 _visible 이 숨긴다)."""
    parts = [p.strip().lstrip("+") for p in label.split(">")]
    tokens = [
        {"name": n, "struck": removed or k < len(parts) - 1, "hl": next((i for i, q in enumerate(names, 1) if q == n), 0)}
        for k, n in enumerate(parts)
    ]
    return {"tokens": tokens, "changed": len(parts) > 1 or label.startswith("+") or removed,
            "reason": "" if removed else (reasons or {}).get(parts[-1], "")}


def _items(labels: list[str], names: list[str], removed: bool = False, reasons: dict[str, str] | None = None) -> list[dict]:
    return [_item(lb, names, removed, reasons) for lb in labels]


def _why(day, cell: str) -> dict[str, str]:
    """그날 사유가 있는 사람들 {이름: 사유}. 사유는 그날 그 사람 전체라 당번 칸에도 붙는다."""
    return {n: day.reason(cell, n) for _, n in day.reasons} if day else {}


def _latest(labels: list[str]) -> list[str]:
    """변경 내역을 숨길 때: 'A>B>C'·'+C' → 'C'(지금 근무하는 사람만)."""
    return [lb.split(">")[-1].strip().lstrip("+") for lb in labels]


def _visible(labels: list[str], why: dict[str, str], history: bool) -> list[str]:
    """변경 내역 표시를 끄면 지금 사람만 남기고, 사유 있는 사람도 빠진 사람처럼 숨긴다."""
    return labels if history else [n for n in _latest(labels) if n not in why]


def _lines(labels: list[str], names: list[str], removed: bool = False, per_line: int = 3,
           reasons: dict[str, str] | None = None) -> list[list[dict]]:
    items = _items(labels, names, removed, reasons)
    return [items[i:i + per_line] for i in range(0, len(items), per_line)]


def _member(username: str | None) -> User | None:
    if not username:
        return None
    m = User.objects.filter(username=username).first()
    if m is None:
        raise DutyError("없는 멤버입니다.")  # 조작된 코드가 '삭제'로 해석되지 않게
    return m


def _selection(request, remember: bool = False) -> tuple[list[Board], Board | None]:
    """고른 근무표와 내 근무표(근무표 통합 설계 9.1). 순서 = 내 근무표 먼저, 나머지 id 순(boards.in_order).
    ?board=a&board=b(중복·빈 값은 버리고 없는 code 는 404) → (근무표 화면만) pick=1 이면 내 근무표만, 아니면 기억한 목록
    (없는 code 는 버림) → 내 근무표. remember=True(근무표 화면)는 고른 목록을 기억한다([내 근무표]면 비운다).
    /day/ 는 기억을 읽지 않는다: ?board= 없는 알림 링크는 늘 내 근무표다."""
    user, home = request.user, boards.home(request.user)
    codes = [c for c in dict.fromkeys(request.GET.getlist("board")) if c]
    if codes:
        chosen = list(Board.objects.filter(code__in=codes))
        if len(chosen) != len(codes):
            raise Http404
    elif remember and not request.GET.get("pick"):
        pref = RosterPref.objects.filter(user=user).first()
        chosen = list(Board.objects.filter(code__in=pref.boards)) if pref else []
    else:
        chosen = []
    chosen = boards.in_order(chosen or [home], home)
    if remember:
        prefs.remember_boards(user, chosen, home)  # DB 쓰기는 services(뷰는 읽기만)
    return chosen, home


def _page_next(request) -> str:
    """팝업이 돌아올 주소(설계 9.4): 지금 주소 그대로에서 pick 만 뺀다(돌아온 화면이 '방금 폼에서 골랐음'이 되지 않게).
    pick 이 없으면 get_full_path() 그대로라 근무표 하나인 화면의 링크는 글자 그대로다."""
    if "pick" not in request.GET:
        return request.get_full_path()
    q = request.GET.copy()
    del q["pick"]
    return request.path + ("?" + q.urlencode() if q else "")


def _to_mine(chosen, home, view_only: bool) -> str:
    """[내 근무표만 보기] 버튼 글자(설계 9.2, 계획 5번). 고른 목록이 정확히 [내 근무표]면 ""(버튼 없음)."""
    if home is None or chosen == [home]:
        return ""
    if home in chosen:
        return "내 근무표만 보기"
    return "보기 전용 · 내 근무표로" if view_only else "내 근무표로"


def _board(request) -> Board:
    """팝업(/cell/·/memo/)의 근무표: 늘 하나(설계 9.4). ?board= 가 없으면 내 근무표, 둘 이상이면 404, 없는 code 는 404."""
    codes = [c for c in request.GET.getlist("board") if c]
    if len(codes) > 1:
        raise Http404
    return get_object_or_404(Board, code=codes[0]) if codes else boards.home(request.user)


def _prefix(user, board) -> str:
    """팝업 제목·성공 글 앞의 '<근무표 이름> · '(설계 9.4): 내가 바꿀 수 있는 근무표가 둘 이상일 때만."""
    return f"{board.name} · " if len(boards.edit_boards(user)) > 1 else ""


def _filters(request, board) -> tuple[list[str], list[str]]:
    """?dept=MEMS&dept=UI, ?type=직원 → 유효한 값만. 빈 목록 = 전체."""
    d, t, _ = prefs.clean(board, request.GET.getlist("dept"), request.GET.getlist("type"), [])
    return d, t


def _filtered(qs, depts: list[str], types: list[str]):
    qs = qs.filter(department_id__in=depts) if depts else qs
    return qs.filter(type__in=types) if types else qs


def _keeper(depts: list[str], types: list[str]):
    """라벨의 현재(마지막) 사람이 부서·유형 필터를 모두 통과하면 True인 함수."""
    info = {n: (d, t) for n, d, t in User.objects.values_list("name", "department_id", "type")} if depts or types else {}

    def keep(label: str) -> bool:
        d, t = info.get(label.split(">")[-1].strip().lstrip("+"), (None, None))
        return (not depts or d in depts) and (not types or t in types)

    return keep


def _shown(shifts: list[str]):
    """칸 키가 스케줄 필터를 통과하는지. 빈 목록 = 전체, 관제 10칸은 'slots' 하나로."""
    return lambda k: not shifts or (SLOT_GROUP if is_slot_cell(k) else k) in shifts


def _filter_ctx(board, defs, depts, types, shifts, history: bool = True, mine: bool = True) -> dict:
    return {
        "history": history,
        "filterable": mine,  # 내 근무표가 아니면 부서·유형·스케줄 필터를 그리지 않는다(늘 전체)
        "filter_on": bool(depts or types or shifts),
        "type_choices": [{"code": t, "name": t, "checked": not types or t in types} for t in (STAFF, DEVELOPER)]
        if prefs.has_types(defs) else [],
        "dept_choices": [
            {"code": d.code, "name": d.name, "checked": not depts or d.code in depts}
            for d in Department.objects.filter(board=board).order_by("order", "code")  # 그 근무표 부서만
        ],
        "shift_choices": _shift_choices(defs, shifts),
    }


def _shift_choices(defs, shifts) -> list[dict]:
    on = [x for x in defs if x.active]  # 선택지는 켜진 정의만(prefs.clean 의 boards.active_defs 와 같은 범위)
    return [{"code": c, "name": n, "checked": not shifts or c in shifts} for c, n in prefs.choices(on).items()]


def _active_members(board, depts: list[str] | None = None, types: list[str] | None = None):
    """근무 변경 창 To 후보: 그 근무표 부서의 재직자(필터가 비어도 다른 근무표 사람은 빠진다)."""
    qs = User.objects.roster().filter(department__board=board).select_related("department").order_by("name")
    return list(_filtered(qs, depts or [], types or []))


def _cell_context(defs, day, cell: str, d, depts: list[str] | None = None, types: list[str] | None = None, members=()):
    current = day.members[cell] if day else []
    qs = User.objects.filter(name__in=current).order_by("name")
    why = _why(day, cell)
    # To 목록에 그날 같은 종류 근무를 붙인다(맞교환이 기본이라 무엇과 바뀌는지 보이게). 점심당번 칸은 그날 근무조를
    want = SLOT if is_slot_cell(cell) else SHIFT
    kinds = [x.key for x in ordered(defs) if kind(x.key) == want]
    where = {}
    for k in kinds:
        for n in (day.members[k] if day else []):
            where[n] = f"{where[n]}·{cell_label(defs, k)}" if n in where else cell_label(defs, k)  # 관제 여러 칸이면 모두
    current_members = list(_filtered(qs, depts or [], types or []))
    for m in current_members:
        m.reason = why.get(m.name, "")  # 사유 선택의 지금 값 표시
    return {
        "d": d, "cell": cell, "label": cell_label(defs, cell), "slot": is_slot_cell(cell),
        "lunch": cell == LUNCH,  # 사유 선택 없음, 늘 교체
        # 근무조 칸: "점심당번도 같이 넘기기"(그 근무표에 켜진 점심당번 정의가 있을 때만)
        "carry": kind(cell) == SHIFT and any(x.key == LUNCH and x.active for x in defs),
        "current_members": current_members, "reason_choices": REASONS,
        "has_slots": any(kind(x.key) == SLOT and x.active for x in defs),  # 사유 안내의 "관제" 문구
        "to_options": [{"username": m.username, "name": m.name, "dept": m.department.name,
                        "where": where.get(m.name, "근무 없음")} for m in members if m.name not in current],
    }


LOW, HIGH = date(2000, 1, 1), date(2099, 12, 31)


def _month_shift(d: date, step: int) -> date:
    m = d.month - 1 + step
    return date(d.year + m // 12, m % 12 + 1, 1)


@login_required
def roster(request):
    names = split_names(request.GET.get("q", ""))[:3]  # 구버전 ?q=a,b,c
    names = [request.GET.get(f"q{i}", "").strip() or (names[i - 1] if i <= len(names) else "") for i in (1, 2, 3)]
    today = perms.today()
    chosen, home = _selection(request, remember=True)
    multi, sq = len(chosen) > 1, boards.selection_query(chosen, home)
    mine = home in chosen  # 부서·유형·스케줄 필터는 내 근무표 구역에만(설계 9.3). 목록에 없으면 필터 상자도 없다
    fboard = home if mine else chosen[0]  # 필터 상자를 그릴 근무표(mine 이 아니면 '보기' 칸만 그린다)
    pref = prefs.resolve(request.user, request.GET, fboard, mine=mine)
    view, depts, types, shifts, history = pref["view"], pref["depts"], pref["types"], pref["shifts"], pref["history"]
    anchor = date_param(request, "date") or today
    if not LOW <= anchor <= HIGH:  # 극단 날짜의 overflow 방지
        anchor = today
    keep, shown = _keeper(depts, types), _shown(shifts)

    def link(v: str, d: date) -> str | None:
        if not LOW <= d <= HIGH:
            return None  # 범위 밖으로 가는 링크는 만들지 않는다
        params = {"view": v, "date": d.isoformat(), **{f"q{i}": n for i, n in enumerate(names, 1) if n}, "dept": depts, "type": types, "shift": shifts}
        return (sq + "&" if sq else "?") + urlencode(params, doseq=True)

    if view == "week":
        monday = anchor - timedelta(days=anchor.weekday())
        weeks = [[monday + timedelta(days=i) for i in range(5)]]
        prev_d, next_d = monday - timedelta(days=7), monday + timedelta(days=7)
        title = f"{monday:%Y-%m-%d} ~ {monday + timedelta(days=4):%m-%d}"
    else:
        first = anchor.replace(day=1)
        cur = first - timedelta(days=first.weekday())
        weeks = []
        last = _month_shift(first, 1) - timedelta(days=1)
        while cur <= last:
            if cur + timedelta(days=4) >= first:  # 주말만 걸친 앞 주는 건너뜀
                weeks.append([cur + timedelta(days=i) for i in range(5)])
            cur += timedelta(days=7)
        prev_d, next_d = _month_shift(first, -1), _month_shift(first, 1)
        title = f"{first.year}년 {first.month}월"
    first_day, last_day = weeks[0][0], weeks[-1][-1]
    closed = holidays.closed(first_day, last_day)  # 휴장일은 모든 근무표 공통이라 날짜 칸에 한 번
    page_next = _page_next(request)
    dept_qs = "".join("&" + urlencode({k: v}) for k, vs in (("dept", depts), ("type", types)) for v in vs)

    def part(b: Board) -> dict:
        """근무표 하나의 구역 재료(설계 9.2 '한 길'). 쿼리는 근무표마다 몇 번뿐이고 날짜마다 묻지 않는다(계획 9번)."""
        is_home, bq = b == home, boards.link_query(home, b)
        bqa = "&" + bq[1:] if bq else ""
        admin = perms.is_board_admin(request.user, b)
        return {
            "defs": boards.defs(b),
            "keep": keep if is_home else _keeper([], []), "shown": shown if is_home else _shown([]),
            # 칸 링크 권한: 날짜마다 묻지 않고 지난 날·오늘 이후 두 번만 묻는다
            "edit_past": perms.can_edit(request.user, b, today - timedelta(days=1)),
            "edit_now": perms.can_edit(request.user, b, today),
            "by_date": {x.date: x for x in published_days(b, first_day, last_day)},
            "notes": memos.for_range(b, first_day, last_day),  # 메모는 회차가 아니라 (근무표, 날짜)에 붙는다
            "meta": {"name": b.name if multi else "", "code": b.code, "bq": bq, "bqa": bqa, "memo_admin": admin,
                     "view_only": b != boards.board_of(request.user) and not admin,
                     # 근무 변경 창 To 후보를 거를 부서·유형 꼬리도 내 근무표 구역만(계획 8번)
                     "filter_qs": (dept_qs if is_home else "") + bqa},
        }

    parts = [part(b) for b in chosen]

    def section(p: dict, d: date, other: bool) -> dict:
        found, keep_, shown_, defs = p["by_date"].get(d), p["keep"], p["shown"], p["defs"]
        cells = {
            x.key: {
                "key": x.key, "slot": is_slot_cell(x.key), "label": x.name,
                "lines": _lines(_visible([lb for lb in found.cells[x.key].labels if keep_(lb)], _why(found, x.key), history),
                                names, reasons=_why(found, x.key)) if found else [],
                "removed": _lines([lb for lb in found.cells[x.key].removed if keep_(lb)], names, True) if found and history else [],
            }
            for x in display_order(defs) if shown_(x.key)
        }
        note = p["notes"]["day"].get(d)
        no_work = bool(note and note.no_work)
        return {
            **p["meta"], "memo": note.text if note else "", "no_work": no_work, "empty": found is None,
            "week_memo": p["notes"]["week"].get(d),  # 월요일 칸에만 붙는다(week.0 = 그 주 월요일)
            # 배포된 근무표가 있는 날만, 근무 없음 날은 못 바꾼다
            "edit": (p["edit_past"] if d < today else p["edit_now"]) and not other and found is not None and not no_work,
            "commute": [cells[x.key] for x in shift_defs(defs) + lunch_defs(defs) if x.key in cells],  # 근무조 → 점심당번
            "duty": [{"time": cells[x.key]["label"][:5], **cells[x.key]} for x in slot_defs(defs) if x.key in cells],
        }

    def day_info(d: date) -> dict:
        other = view == "month" and d.month != anchor.month
        secs = [section(p, d, other) for p in parts]
        return {
            "date": d, "is_today": d == today, "other": other, "holiday": closed.get(d, ""), "sections": secs,
            # 팝업이 돌아올 주소. 둘 이상이면 그 날짜 칸으로(계획 4번)
            "nq": quote(page_next + (f"#d-{d.isoformat()}" if multi else "")),
            "wm_row": any(s["week_memo"] or s["memo_admin"] for s in secs),  # 월간: 그 주 메모 줄
        }

    days = [[day_info(d) for d in w] for w in weeks]
    months = sorted({d.replace(day=1) for w in weeks for d in w if view == "week" or d.month == anchor.month})
    all_boards = list(Board.objects.order_by("id"))
    view_only = all(p["meta"]["view_only"] for p in parts)
    ctx = {
        "view": view, "title": title, "names": names, "date": anchor, "today_link": (link(view, today) or f"?view={view}&date={today.isoformat()}") + "#today",
        "prev": link(view, prev_d), "next": link(view, next_d),
        "week_link": link("week", anchor), "month_link": link("month", anchor),
        # 근무표 고르기(설계 9.1): 근무표가 둘 이상일 때만, 내 근무표 먼저 id 순. 체크박스를 바꿔도 보내지 않고 [보기]로
        "pick_boards": [{"code": b.code, "name": b.name, "home": b == home, "on": b in chosen}
                        for b in boards.in_order(all_boards, home)] if len(all_boards) > 1 else [],
        "multi": multi, "bq": sq, "sel_codes": [b.code for b in chosen] if sq else [],
        "sel_names": " + ".join(b.name for b in chosen), "page_nq": quote(page_next),
        "view_only": view_only, "to_mine": _to_mine(chosen, home, view_only), "home_code": home.code if home else "",
        "can_click": any(s["edit"] for d in (days[0][0], days[0][4]) for s in d["sections"]),  # 범례 '칸을 누르면…'
        "weeks": days,
        "month_memos": [{"date": m, "memo": p["notes"]["month"].get(m), "p": p["meta"]} for m in months for p in parts],
    }
    ctx.update(_filter_ctx(fboard, parts[chosen.index(fboard)]["defs"], depts, types, shifts, history, mine))
    return render(request, "duty/roster.html", ctx)


@login_required
def cell(request, d, cell):
    board = _board(request)
    bq = boards.board_query(request.user, board)
    defs = boards.defs(board)
    if cell not in by_key(defs):
        raise Http404
    prefix = _prefix(request.user, board)
    fallback = reverse("day", args=[d]) + bq
    if request.method == "POST":
        reason_form = bool(request.POST.get("set_reason"))  # 근무조 칸의 사유 선택(같은 창의 두 번째 폼)
        try:
            if reason_form:
                pk = int_param(request.POST.get("member"))  # 위 폼과 option 값이 겹치지 않게 아이디 대신 번호
                member = User.objects.filter(pk=pk).first() if pk is not None else None
                if member is None:
                    raise DutyError("사유를 붙일 사람을 골라 주세요.")
                result = changes.set_reason(request.user, board, d, member, request.POST.get("reason", ""))
            else:
                # "+"·"-" = 없음(넣기만·빼기만). 기본은 둘 다 고른 맞교환
                before, after = request.POST.get("before"), request.POST.get("after")
                result = changes.exchange(request.user, board, d, cell, _member(None if before == "+" else before),
                                          _member(None if after == "-" else after),
                                          carry_lunch=request.POST.get("carry_lunch") == "1",
                                          keep_other=request.POST.get("keep_other") == "1")
        except DutyError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, prefix + ("사유를 저장했습니다." if reason_form else "변경했습니다."))
            for w in result:
                messages.warning(request, w)
        return redirect(safe_next(request, fallback))
    depts, types = _filters(request, board)
    ctx = _cell_context(defs, find_day(board, d), cell, d, depts, types, _active_members(board, depts, types))
    ctx.update(next=safe_next(request, fallback), bq=bq, prefix=prefix)
    return render(request, "duty/_cell_form.html", ctx)


def _neighbor(d, step: int):
    d = d + timedelta(days=step)
    while d.weekday() >= 5:
        d += timedelta(days=step)
    return d


def _day_part(request, board: Board, d: date, home, multi: bool, page_next: str, history: bool, flt) -> dict:
    """하루 화면의 근무표 하나(설계 9.4). flt = (부서, 유형, 스케줄): 내 근무표 구역만 받고 나머지는 빈 목록(= 전체)."""
    depts, types, shifts = flt
    defs = boards.defs(board)
    found = find_day(board, d)
    note = memos.for_range(board, d, d)["day"].get(d)
    no_work = bool(note and note.no_work)  # 근무 없음 날은 칸 대신 메모 글만, 바꾸기 없음
    admin = perms.is_board_admin(request.user, board)
    members = _active_members(board, depts, types)
    keep, shown = _keeper(depts, types), _shown(shifts)
    bq = boards.link_query(home, board)
    sections = []
    if found and not no_work:
        for k in filter(shown, [x.key for x in display_order(defs)]):  # 출근조 먼저, 관제는 뒤에 묶어서
            ctx = _cell_context(defs, found, k, d, depts, types, members)
            ctx.update(
                next=page_next + (f"#{board.code}-{k}" if multi else ""),  # 저장 뒤 이 화면 그대로(둘 이상이면 그 칸으로)
                items=_items(_visible([x for x in found.cells[k].labels if keep(x)], _why(found, k), history), [],
                             reasons=_why(found, k)),
                removed_items=_items([x for x in found.cells[k].removed if keep(x)], [], True) if history else [],
            )
            sections.append(ctx)
    return {"name": board.name, "code": board.code, "defs": defs, "bq": bq, "bqa": "&" + bq[1:] if bq else "",
            "memo_admin": admin, "view_only": board != boards.board_of(request.user) and not admin,
            "found": found, "note": note, "editable": perms.can_edit(request.user, board, d) and not no_work,
            "sections": sections}


@login_required
def day(request, d):
    chosen, home = _selection(request)  # 기억은 읽지 않는다(?board= 없는 알림 링크는 내 근무표)
    multi, sq = len(chosen) > 1, boards.selection_query(chosen, home)
    mine = home in chosen
    fboard = home if mine else chosen[0]
    pref = prefs.resolve(request.user, request.GET, fboard, with_view=False, mine=mine)
    depts, types, shifts, history = pref["depts"], pref["types"], pref["shifts"], pref["history"]
    page_next = _page_next(request)
    parts = [_day_part(request, b, d, home, multi, page_next, history,
                       (depts, types, shifts) if b == home else ([], [], [])) for b in chosen]
    view_only = all(p["view_only"] for p in parts)
    qs = "?" + urlencode([("board", b.code) for b in chosen if sq] + [("f", 1)] + [("dept", x) for x in depts]
                         + [("type", x) for x in types] + [("shift", x) for x in shifts])
    return render(request, "duty/day.html", {
        "d": d, "weekday": DAY_LABELS[d.weekday()], "parts": parts, "multi": multi,
        "holiday": holidays.closed(d, d).get(d, ""), "prev": _neighbor(d, -1), "next_day": _neighbor(d, 1), "qs": qs,
        "bq": sq, "sel_codes": [b.code for b in chosen] if sq else [], "page_nq": quote(page_next),
        "view_only": view_only, "to_mine": _to_mine(chosen, home, view_only), "home_code": home.code if home else "",
        **_filter_ctx(fboard, parts[chosen.index(fboard)]["defs"], depts, types, shifts, history, mine),
    })


@login_required
def memo(request, scope, d):
    """[메모] 팝업(근무 변경 창과 같은 방식). 근무표 관리 그룹만."""
    board = _board(request)
    if scope not in Memo.Scope.values or not perms.is_board_admin(request.user, board):
        raise Http404
    bq, prefix = boards.board_query(request.user, board), _prefix(request.user, board)
    d = memos.normalize(scope, d)
    fallback = (reverse("day", args=[d]) if scope == Memo.Scope.DAY else reverse("roster")) + bq
    if request.method == "POST":
        try:
            if request.POST.get("delete"):
                memos.delete(request.user, board, scope, d)
                msg = "메모를 지웠습니다."
            else:
                cleared = memos.save(request.user, board, scope, d, request.POST.get("text", ""),
                                     no_work=bool(request.POST.get("no_work")), confirm=int_param(request.POST.get("confirm")))
                msg = f"메모를 저장했습니다. {cleared}명의 근무를 지웠습니다." if cleared else "메모를 저장했습니다."
        except DutyError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, prefix + msg)
        return redirect(safe_next(request, fallback))
    return render(request, "duty/_memo_form.html", {
        "scope": scope, "d": d, "memo": memos.for_range(board, d, d)[scope].get(d), "next": safe_next(request, fallback),
        "title": prefix + {"day": f"{d:%Y-%m-%d} 메모", "week": f"{d.month}/{d.day} 주 메모", "month": f"{d.year}년 {d.month}월 메모"}[scope],
        "affected": memos.affected(board, d) if scope == Memo.Scope.DAY else 0, "bq": bq,
    })


@login_required
def me(request):
    member = request.user if request.user.department_id else None
    board = boards.home(request.user)  # 내 스케줄은 늘 내 근무표
    _, _, shifts = prefs.clean(board, [], [], request.GET.getlist("shift"))
    today = perms.today()
    rows = dict(member_schedule(board, member, today, _shown(shifts))) if member else {}
    days = boards.owners(board, today, None) if member else {}
    if days:  # 휴장일·근무 없음 날도 회색 줄로(근무 없는 보통 날은 뺀다)
        off = holidays.closed(today, max(days)) | {
            d: m.text or "근무 없음" for d, m in memos.for_range(board, today, max(days))["day"].items() if m.no_work}
        off = {d: why for d, why in off.items() if d in days and d not in rows}
    else:
        off = {}
    return render(request, "duty/me.html", {
        "member": member,
        "shift_choices": _shift_choices(boards.defs(board), shifts),
        "items": [{"date": d, "weekday": DAY_LABELS[d.weekday()], "labels": rows.get(d) or [off[d]], "off": d in off,
                   "today": d == today} for d in sorted(rows.keys() | off.keys())],
    })
