from datetime import date, timedelta
from urllib.parse import quote, urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .. import perms, xlsx
from ..csv_io import split_names
from ..errors import DutyError
from ..models import Board, Department, Memo, RosterPref, User
from ..services import boards, changes, holidays, memo_notice, memos, prefs
from ..services.roster import export_rows, find_day, member_schedule, published_days
from ..shifts import (
    DAY_LABELS, DEVELOPER, LUNCH, REASONS, SHIFT, SLOT, SLOT_GROUP, STAFF, by_key, cell_label, display_order, is_slot_cell,
    kind, lunch_defs, ordered, shift_defs, slot_defs,
)
from .common import HIGH, LOW, date_param, int_param, safe_next


def last_name(label: str) -> str:
    """라벨(A, A>B>C, +B)의 지금(마지막) 사람."""
    return label.split(">")[-1].strip().lstrip("+")


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
    return [last_name(lb) for lb in labels]


def _visible(labels: list[str], why: dict[str, str], history: bool) -> list[str]:
    """변경 내역 표시를 끄면 지금 사람만 남기고, 사유 있는 사람도 빠진 사람처럼 숨긴다."""
    return labels if history else [n for n in _latest(labels) if n not in why]


def _member(value: str | None) -> User | None:
    """근무 변경 창의 From/To 값(사람 번호). 로그인 아이디는 보기 전용 사용자에게도 가는 목록이라 쓰지 않는다."""
    if not value:
        return None
    pk = int_param(value)
    m = User.objects.filter(pk=pk).first() if pk is not None else None
    if m is None:
        raise DutyError("없는 멤버입니다.")  # 조작된 코드가 '삭제'로 해석되지 않게
    return m


def _selection(request, memory: bool = False) -> tuple[list[Board], Board | None]:
    """고른 근무표와 내 근무표(근무표 통합 설계 9.1). 순서 = 내 근무표 먼저, 나머지 id 순(boards.in_order).
    ?board=a&board=b(중복·빈 값은 버리고 없는 code 는 404) → (근무표 화면만, memory=True) pick=1 이면 내 근무표만,
    아니면 기억한 목록(없는 code 는 버림) → 내 근무표. 읽기만 한다: 기억은 POST /prefs/ 가 남긴다(roster_prefs).
    /day/ 는 기억을 읽지 않는다: ?board= 없는 알림 링크는 늘 내 근무표다."""
    user, home = request.user, boards.home(request.user)
    codes = [c for c in dict.fromkeys(request.GET.getlist("board")) if c]
    if codes:
        chosen = list(Board.objects.filter(code__in=codes))
        if len(chosen) != len(codes):
            raise Http404
    elif memory and not request.GET.get("pick"):
        pref = RosterPref.objects.filter(user=user).first()
        chosen = list(Board.objects.filter(code__in=pref.boards)) if pref else []
    else:
        chosen = []
    return boards.in_order(chosen or [home], home), home


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
        d, t = info.get(last_name(label), (None, None))
        return (not depts or d in depts) and (not types or t in types)

    return keep


def _shown(shifts: list[str]):
    """칸 키가 스케줄 필터를 통과하는지. 빈 목록 = 전체, 관제 10칸은 'slots' 하나로."""
    return lambda k: not shifts or (SLOT_GROUP if is_slot_cell(k) else k) in shifts


def _filter_ctx(board, defs, depts, types, shifts, history: bool = True, filterable: bool = True, dims=None) -> dict:
    dims = dims or {}
    dim = lambda k, code: code in (dims.get(k) or [])  # noqa: E731  흐리게(보임 목록 안에서만 뜻이 있다)
    return {
        "history": history, "hist_dim": history and bool(dims.get("hist")),
        "filterable": filterable,  # 내 근무표가 아니면 부서·유형·스케줄 필터를 그리지 않는다(늘 전체)
        "filter_on": bool(depts or types or shifts),
        "type_choices": [{"code": t, "name": t, "checked": not types or t in types, "dim": dim("type", t)} for t in (STAFF, DEVELOPER)]
        if prefs.has_types(defs) else [],
        "dept_choices": [
            {"code": d.code, "name": d.name, "checked": not depts or d.code in depts, "dim": dim("dept", d.code)}
            for d in Department.objects.filter(board=board).order_by("order", "code")  # 그 근무표 부서만
        ],
        "shift_choices": [{**c, "dim": dim("shift", c["code"])} for c in _shift_choices(defs, shifts)],
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
        "to_options": [{"pk": m.pk, "name": m.name, "dept": m.department.name,
                        "where": where.get(m.name, "근무 없음")} for m in members if m.name not in current],
    }




def _month_shift(d: date, step: int) -> date:
    m = d.month - 1 + step
    return date(d.year + m // 12, m % 12 + 1, 1)


@login_required
def roster(request):
    """근무표 화면. 부서·유형·스케줄·변경 내역·이름 강조는 서버가 거르지 않고 전부 그린 뒤 브라우저가 바로 숨기고 칠한다
    (duty/static/duty/roster.js, 결정 기록 2026-11-23). 그래서 이 화면의 응답은 필터와 상관없이 기간·근무표로만 정해진다."""
    names = split_names(request.GET.get("q", ""))[:3]  # 구버전 ?q=a,b,c
    names = [request.GET.get(f"q{i}", "").strip() or (names[i - 1] if i <= len(names) else "") for i in (1, 2, 3)]
    today, me = perms.today(), request.user.name
    chosen, home = _selection(request, memory=True)
    multi, sq = len(chosen) > 1, boards.selection_query(chosen, home)
    has_home = home in chosen  # 부서·유형·스케줄 필터는 내 근무표 구역에만(설계 9.3). 목록에 없으면 필터 상자도 없다
    fboard = home if has_home else chosen[0]  # 필터 상자를 그릴 근무표(내 근무표가 없으면 '보기' 칸만 그린다)
    pref = prefs.load(request.user, request.GET, fboard, mine=has_home)
    view, depts, types, shifts, history = pref["view"], pref["depts"], pref["types"], pref["shifts"], pref["history"]
    anchor = date_param(request, "date") or today
    # 필터용 표시: 라벨의 지금(마지막) 사람의 부서·유형. 내 근무표 구역에만 붙인다
    info = {n: (d or "", t) for n, d, t in User.objects.values_list("name", "department_id", "type")} if has_home else {}

    def link(v: str, d: date) -> str | None:
        if not LOW <= d <= HIGH:
            return None  # 범위 밖으로 가는 링크는 만들지 않는다
        params = {"view": v, "date": d.isoformat(), **{f"q{i}": n for i, n in enumerate(names, 1) if n}}
        return (sq + "&" if sq else "?") + urlencode(params)

    if view == "week":
        monday = anchor - timedelta(days=anchor.weekday())
        weeks = [[monday + timedelta(days=i) for i in range(7)]]
        prev_d, next_d = monday - timedelta(days=7), monday + timedelta(days=7)
        title = f"{monday:%Y-%m-%d} ~ {monday + timedelta(days=4):%m-%d}"
        export = (monday, monday + timedelta(days=4))
    else:
        first = anchor.replace(day=1)
        cur = first - timedelta(days=(first.weekday() + 1) % 7)  # 월간은 일요일부터(주간은 월요일부터)
        weeks = []
        last = _month_shift(first, 1) - timedelta(days=1)
        while cur <= last:
            weeks.append([cur + timedelta(days=i) for i in range(7)])  # 주말 칸도 그린다(메모용)
            cur += timedelta(days=7)
        prev_d, next_d = _month_shift(first, -1), _month_shift(first, 1)
        title = f"{first.year}년 {first.month}월"
        export = (first, last)  # 다른 달 날짜는 화면에 구역이 없다
    first_day, last_day = weeks[0][0], weeks[-1][-1]
    closed = holidays.closed(first_day, last_day)  # 휴장일은 모든 근무표 공통이라 날짜 칸에 한 번
    page_next = _page_next(request)

    def part(b: Board) -> dict:
        """근무표 하나의 구역 재료(설계 9.2 '한 길'). 쿼리는 근무표마다 몇 번뿐이고 날짜마다 묻지 않는다(계획 9번)."""
        bq = boards.link_query(home, b)
        bqa = "&" + bq[1:] if bq else ""
        admin = perms.is_board_admin(request.user, b)
        return {
            "defs": boards.defs(b), "filter": b == home,
            # 칸 링크 권한: 날짜마다 묻지 않고 지난 날·오늘 이후 두 번만 묻는다
            "edit_past": perms.can_edit(request.user, b, today - timedelta(days=1)),
            "edit_now": perms.can_edit(request.user, b, today),
            "by_date": {x.date: x for x in published_days(b, first_day, last_day)},
            "notes": memos.for_range(b, first_day, last_day),  # 메모는 회차가 아니라 (근무표, 날짜)에 붙는다
            "meta": {"name": b.name if multi else "", "code": b.code, "bq": bq, "bqa": bqa, "memo_admin": admin,
                     "view_only": b != boards.board_of(request.user) and not admin},
        }

    parts = [part(b) for b in chosen]

    def mark(items: list[dict], flt: bool) -> bool:
        """이름 토큰에 '나'를, 라벨에 부서·유형(필터용)을 붙이고 내가 지금 이 칸에 있는지 돌려준다(빠짐·사유는 아님)."""
        here = False
        for it in items:
            last = it["tokens"][-1]["name"]
            if flt:
                it["d"], it["t"] = info.get(last, ("", ""))
            for t in it["tokens"]:
                t["me"] = bool(me) and t["name"] == me and not t["struck"]
            here = here or (bool(me) and last == me and not it.get("rm") and not it["reason"])
        return here

    def section(p: dict, d: date, other: bool) -> dict:
        found, defs, flt = p["by_date"].get(d), p["defs"], p["filter"]
        note = p["notes"]["day"].get(d)
        no_work = bool(note and note.no_work)
        cells, here = {}, []
        for x in display_order(defs):
            why = _why(found, x.key)
            items = _items(found.cells[x.key].labels, names, reasons=why) if found else []
            gone = _items(found.cells[x.key].removed, names, True) if found and not no_work else []  # 근무 없음으로 지운 사람은 글이 대신한다
            for it in gone:
                it["rm"] = True
            items += gone
            if mark(items, flt):
                here.append(x.key)
            cells[x.key] = {"key": x.key, "slot": is_slot_cell(x.key), "label": x.name, "items": items,
                            "k": SLOT_GROUP if is_slot_cell(x.key) else x.key, "n": len(found.cells[x.key].labels) if found else 0}
        duty = [{"time": cells[x.key]["label"][:5], **cells[x.key]} for x in slot_defs(defs)]
        commute = [cells[x.key] for x in shift_defs(defs) + lunch_defs(defs)]  # 근무조 → 점심당번
        # 내 근무(날짜 옆 표시·'N월 내 근무'): 근무마다 하나. 내 근무표 구역은 스케줄 키를 붙여 roster.js 가 스케줄 체크로 거른다
        my_shifts = [{"k": c["k"] if flt else "", "label": c["label"]} for c in commute if c["key"] in here]
        if any(c["key"] in here for c in duty):
            my_shifts.append({"k": SLOT_GROUP if flt else "", "label": "관제"})
        return {
            **p["meta"], "memo": note.text if note else "", "no_work": no_work, "empty": found is None,
            "weekend": d.weekday() >= 5, "filter": flt,
            "week_memo": p["notes"]["week"].get(d),  # 월요일 칸에만 붙는다(week.0 = 그 주 월요일)
            # 근무 없음 날은 글 아래에 넣은 사람이 있을 때만 칸을 그린다(넣기는 하루 화면에서)
            "covered": no_work and not any(c["n"] for c in cells.values()),  # 지운 사람(취소선)만 있으면 덮는다
            "edit": (p["edit_past"] if d < today else p["edit_now"]) and not other and found is not None,  # 배포된 근무표가 있는 날만
            "commute": commute, "duty": duty, "slot_n": sum(c["n"] for c in duty),
            "mine": my_shifts, "my_slots": [c["time"] for c in duty if c["key"] in here],
        }

    def day_info(d: date) -> dict:
        other = view == "month" and d.month != anchor.month
        secs = [section(p, d, other) for p in parts]
        my = [m for s in secs for m in s["mine"]]  # 앞뒤 달 날짜도 보인다(같은 조회 범위). 'N월 내 근무'에는 안 센다
        for i, m in enumerate(my):
            m["more"] = i > 0  # 첫 것만 보인다(스케줄 체크로 앞의 것이 숨으면 roster.js 가 다음 것을 보인다)
        weekend = d.weekday() >= 5
        return {
            "date": d, "is_today": d == today, "other": other, "holiday": closed.get(d, ""), "sections": secs,
            "weekend": weekend, "my": my, "label": f"{d.month}월 {d.day}일 ({DAY_LABELS[d.weekday()]})",
            "has_memo": any(s["memo"] for s in secs),
            # 휴대폰 주간: 주말은 메모·휴장일이 있거나 메모를 쓸 수 있을 때만 카드로
            "we_empty": weekend and not closed.get(d) and not any(s["memo"] or s["memo_admin"] for s in secs),
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
        "sel_names": " + ".join(b.name for b in chosen), "page_nq": quote(page_next), "page_next": page_next,
        "view_only": view_only, "to_mine": _to_mine(chosen, home, view_only), "home_code": home.code if home else "",
        "can_click": any(s["edit"] for w in days for d in w for s in d["sections"]),  # 범례 '칸을 누르면…'
        "weeks": days, "export": export,
        "my_days": sum(1 for w in days for d in w if d["my"] and not d["other"]) if view == "month" and request.user.department_id else None,  # 근무표에 없는 계정은 표시 안 함  # 스케줄 체크를 따르는 값은 roster.js 가 다시 센다
        "dim_default": request.user.department_id is not None,  # 근무표에 든 사람만 '다른 사람 흐리게'가 처음부터 켜짐
        "month_memos": [{"date": m, "memo": p["notes"]["month"].get(m), "p": p["meta"]} for m in months for p in parts],
    }
    ctx.update(_filter_ctx(fboard, parts[chosen.index(fboard)]["defs"], depts, types, shifts, history, has_home, pref["dims"]))
    return render(request, "duty/roster.html", ctx)


@login_required
@require_POST
def roster_prefs(request):
    """보기 설정을 저장하는 유일한 길(GET 화면은 읽기만: 바깥 링크로 남의 설정을 바꾸지 못하게).
    roster.js(필터·흐리게·변경 내역), base.html 의 data-remember([주간]·[월간], 근무표 고르기, 내 근무표로, 하루 화면 필터 폼)가 보낸다.
    pick 이 있으면 board 목록을 기억한다(없는 code 는 버림, 하나도 없으면 내 근무표 = 기억 비움)."""
    user, home = request.user, boards.home(request.user)
    if home is None:  # 근무표가 하나도 없다
        return HttpResponse(status=204)
    prefs.save(user, request.POST, home, mine=request.POST.get("mine") != "0")
    if "pick" in request.POST:
        codes = request.POST.getlist("board")
        prefs.remember_boards(user, boards.in_order(list(Board.objects.filter(code__in=codes)) or [home], home), home)
    return HttpResponse(status=204)


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
                member = _member(request.POST.get("member"))
                if member is None:
                    raise DutyError("사유를 붙일 사람을 골라 주세요.")
                result = changes.set_reason(request.user, board, d, member, request.POST.get("reason", ""))
            else:
                # "+"·"-" = 없음(넣기만·빼기만). 기본은 둘 다 고른 맞교환
                before, after = request.POST.get("before"), request.POST.get("after")
                if not before:  # 비어 있으면 넣기만("+")으로 읽지 않는다
                    raise DutyError("From 을 골라 주세요.")
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
    history = history and not (note and note.no_work)  # 근무 없음으로 지운 사람(취소선)은 글이 대신한다
    admin = perms.is_board_admin(request.user, board)
    members = _active_members(board, depts, types)
    keep, shown = _keeper(depts, types), _shown(shifts)
    bq = boards.link_query(home, board)
    sections = []
    if found:  # 근무 없음 날도 글 아래에 칸(필요한 사람을 넣는다)
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
            "found": found, "note": note, "editable": perms.can_edit(request.user, board, d),
            "sections": sections}


@login_required
def day(request, d):
    chosen, home = _selection(request)  # 기억은 읽지 않는다(?board= 없는 알림 링크는 내 근무표)
    multi, sq = len(chosen) > 1, boards.selection_query(chosen, home)
    has_home = home in chosen
    fboard = home if has_home else chosen[0]
    pref = prefs.load(request.user, request.GET, fboard, with_view=False, mine=has_home)
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
        **_filter_ctx(fboard, parts[chosen.index(fboard)]["defs"], depts, types, shifts, history, has_home),
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
                                     no_work=bool(request.POST.get("no_work")), confirm=int_param(request.POST.get("confirm")),
                                     notify=bool(request.POST.get("notify")))
                msg = f"메모를 저장했습니다. {cleared}명의 근무를 지웠습니다." if cleared else "메모를 저장했습니다."
        except DutyError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, prefix + msg)
        return redirect(safe_next(request, fallback))
    return render(request, "duty/_memo_form.html", {
        "scope": scope, "d": d, "memo": memos.for_range(board, d, d)[scope].get(d), "next": safe_next(request, fallback),
        "title": prefix + {"day": f"{d:%Y-%m-%d} 메모", "week": f"{d.month}/{d.day} 주 메모", "month": f"{d.year}년 {d.month}월 메모"}[scope],
        "affected": memos.affected(board, d) if scope == Memo.Scope.DAY and not memos.no_work_days(board, d, d) else 0,
        "bq": bq,  # 이미 근무 없음인 날은 다시 비우지 않는다(memos.save)
        "notice_to": memo_notice.recipients(board, request.user).count() if board.notify_memos else None,
    })


MAX_DAYS = 365  # 엑셀 다운로드 기간 한도(1년)


def _xlsx(rows, filename: str) -> HttpResponse:
    r = HttpResponse(xlsx.build(rows), content_type=xlsx.MIME)
    r["Content-Disposition"] = xlsx.disposition(filename)
    r["Cache-Control"] = "no-store"  # 이름이 든 파일: 브라우저·중간 서버에 남기지 않는다
    return r


@login_required
def roster_export(request):
    """근무표 엑셀: ?start=&end=(1년까지)&board=…(없으면 내 근무표)&dept=&type=&shift=.
    화면과 같은 재료(배포된 날·고른 근무표, 필터는 내 근무표 구역만)이고 아무것도 기억하지 않는다."""
    chosen, home = _selection(request)
    start, end = date_param(request, "start"), date_param(request, "end")
    error = ""
    if not (start and end):
        error = "시작일과 종료일을 넣어 주세요."
    elif start > end:
        error = "시작일이 종료일보다 늦습니다."
    elif (end - start).days > MAX_DAYS:
        error = "기간은 1년까지 고를 수 있습니다."
    if error:
        messages.error(request, error)
        return redirect(safe_next(request, reverse("roster")))
    g = request.GET.getlist
    depts, types, shifts = prefs.clean(home, g("dept"), g("type"), g("shift")) if home in chosen else ([], [], [])
    rows = []
    for b in chosen:
        mine = b == home
        rows += export_rows(b, start, end, _keeper(depts if mine else [], types if mine else []),
                            _shown(shifts if mine else []))
    rows.sort(key=lambda r: r[0])  # 날짜순, 같은 날은 화면처럼 근무표 순서 그대로(안정 정렬)
    return _xlsx(rows, f"당번표_{start}_{end}.xlsx")


def _me_query(request) -> dict:
    """[내 근무]의 조건: 내 근무표, 스케줄, 시작일(기본 오늘)·종료일(비면 끝까지)."""
    member = request.user if request.user.department_id else None
    board = boards.home(request.user)  # 내 스케줄은 늘 내 근무표
    _, _, shifts = prefs.clean(board, [], [], request.GET.getlist("shift"))
    today = perms.today()
    start, end = date_param(request, "start") or today, date_param(request, "end")
    return {"member": member, "board": board, "shifts": shifts, "today": today, "start": start, "end": end,
            "error": "시작일이 종료일보다 늦습니다." if end and start > end else ""}


@login_required
def me(request):
    q = _me_query(request)
    member, board, today, start, end = q["member"], q["board"], q["today"], q["start"], q["end"]
    ok = member and not q["error"]
    rows = dict(member_schedule(board, member, start, end=end)) if ok else {}  # 스케줄은 브라우저가 거른다
    days = boards.owners(board, start, end) if ok else {}
    if days:  # 휴장일·근무 없음 날도 회색 줄로(근무 없는 보통 날은 뺀다)
        off = holidays.closed(start, max(days)) | {
            d: m.text or "근무 없음" for d, m in memos.for_range(board, start, max(days))["day"].items() if m.no_work}
        off = {d: why for d, why in off.items() if d in days and d not in rows}
    else:
        off = {}
    return render(request, "duty/me.html", {
        "member": member, "start": start, "end": end, "error": q["error"],
        "shift_choices": _shift_choices(boards.defs(board), q["shifts"]),
        "items": [{"date": d, "weekday": DAY_LABELS[d.weekday()], "labels": rows.get(d, []), "why": off.get(d, ""), "off": d in off,
                   "today": d == today} for d in sorted(rows.keys() | off.keys())],
    })


@login_required
def me_export(request):
    """[내 근무] 엑셀: 화면과 같은 조건(시작일·종료일·스케줄), 내 이름 줄만."""
    q = _me_query(request)
    if q["error"]:
        messages.error(request, q["error"])
        return redirect(reverse("me") + "?" + request.GET.urlencode())
    member, start, end = q["member"], q["start"], q["end"]
    rows = export_rows(q["board"], start, end, lambda n: n == member.name, _shown(q["shifts"])) if member else []
    return _xlsx(rows, f"내근무_{start}_{end or (rows[-1][0] if rows else start)}.xlsx")
