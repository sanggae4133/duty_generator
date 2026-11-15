from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from .. import perms
from ..csv_io import split_names
from ..errors import DutyError
from ..models import Department, Memo, User
from ..services import boards, changes, holidays, memos, prefs
from ..services.roster import find_day, member_schedule, published_days
from ..shifts import (
    DAY_LABELS, DEVELOPER, SLOT_GROUP, STAFF, by_key, cell_label, display_order, is_slot_cell, ordered, shift_defs,
    slot_defs,
)
from .common import date_param, safe_next


def _item(label: str, names: list[str], removed: bool = False) -> dict:
    """라벨(A, A>B>C, +B)을 이름 토큰으로 나눈다. 마지막 이름 앞은 취소선, hl은 검색어 번호(1..3)."""
    parts = [p.strip().lstrip("+") for p in label.split(">")]
    tokens = [
        {"name": n, "struck": removed or k < len(parts) - 1, "hl": next((i for i, q in enumerate(names, 1) if q == n), 0)}
        for k, n in enumerate(parts)
    ]
    return {"tokens": tokens, "changed": len(parts) > 1 or label.startswith("+") or removed}


def _items(labels: list[str], names: list[str], removed: bool = False) -> list[dict]:
    return [_item(lb, names, removed) for lb in labels]


def _latest(labels: list[str]) -> list[str]:
    """변경 내역을 숨길 때: 'A>B>C'·'+C' → 'C'(지금 근무하는 사람만)."""
    return [lb.split(">")[-1].strip().lstrip("+") for lb in labels]


def _lines(labels: list[str], names: list[str], removed: bool = False, per_line: int = 3) -> list[list[dict]]:
    items = _items(labels, names, removed)
    return [items[i:i + per_line] for i in range(0, len(items), per_line)]


def _member(username: str | None) -> User | None:
    if not username:
        return None
    m = User.objects.filter(username=username).first()
    if m is None:
        raise DutyError("없는 멤버입니다.")  # 조작된 코드가 '삭제'로 해석되지 않게
    return m


def _board(user):
    """이 사용자가 보는 근무표. 1단계: 내 부서의 근무표, 없으면 IT(근무표 고르기는 2단계). 모든 뷰가 이것 하나를 쓴다."""
    return boards.board_of(user) or boards.it_board()


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


def _filter_ctx(board, defs, depts, types, shifts, history: bool = True) -> dict:
    return {
        "history": history,
        "filter_on": bool(depts or types or shifts),
        "type_choices": [{"code": t, "name": t, "checked": not types or t in types} for t in (STAFF, DEVELOPER)],
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
    # To 목록에 그날 같은 종류 근무를 붙인다(맞교환이 기본이라 무엇과 바뀌는지 보이게)
    kinds = [x.key for x in ordered(defs) if is_slot_cell(x.key) == is_slot_cell(cell)]
    where = {}
    for k in kinds:
        for n in (day.members[k] if day else []):
            where[n] = f"{where[n]}·{cell_label(defs, k)}" if n in where else cell_label(defs, k)  # 관제 여러 칸이면 모두
    return {
        "d": d, "cell": cell, "label": cell_label(defs, cell), "slot": is_slot_cell(cell),
        "current_members": list(_filtered(qs, depts or [], types or [])),
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
    board = _board(request.user)
    defs = boards.defs(board)
    # 칸 링크 권한: 날짜마다 묻지 않고 지난 날·오늘 이후 두 번만 묻는다
    edit_past, edit_now = (perms.can_edit(request.user, board, x) for x in (today - timedelta(days=1), today))
    pref = prefs.resolve(request.user, request.GET, board)
    view, depts, types, shifts, history = pref["view"], pref["depts"], pref["types"], pref["shifts"], pref["history"]
    show = (lambda x: x) if history else _latest
    anchor = date_param(request, "date") or today
    if not LOW <= anchor <= HIGH:  # 극단 날짜의 overflow 방지
        anchor = today
    keep, shown = _keeper(depts, types), _shown(shifts)

    def link(v: str, d: date) -> str | None:
        if not LOW <= d <= HIGH:
            return None  # 범위 밖으로 가는 링크는 만들지 않는다
        params = {"view": v, "date": d.isoformat(), **{f"q{i}": n for i, n in enumerate(names, 1) if n}, "dept": depts, "type": types, "shift": shifts}
        return "?" + urlencode(params, doseq=True)

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
    by_date = {d.date: d for d in published_days(board, first_day, last_day)}
    closed = holidays.closed(first_day, last_day)  # 휴장일 이름은 회차·배정과 상관없이 칸 맨 위에
    notes = memos.for_range(board, first_day, last_day)  # 메모도 회차가 아니라 (근무표, 날짜)에 붙는다

    def day_cells(d: date) -> dict:
        found = by_date.get(d)
        return {
            x.key: {
                "key": x.key, "slot": is_slot_cell(x.key), "label": x.name,
                "lines": _lines(show([lb for lb in found.cells[x.key].labels if keep(lb)]), names) if found else [],
                "removed": _lines([lb for lb in found.cells[x.key].removed if keep(lb)], names, True) if found and history else [],
            }
            for x in display_order(defs) if shown(x.key)
        }

    def day_info(d: date) -> dict:
        cells = day_cells(d)
        other = view == "month" and d.month != anchor.month
        note = notes["day"].get(d)
        no_work = bool(note and note.no_work)
        return {
            "date": d, "is_today": d == today, "other": other, "empty": d not in by_date, "holiday": closed.get(d, ""),
            "memo": note.text if note else "", "no_work": no_work,
            "week_memo": notes["week"].get(d),  # 월요일 칸에만 붙는다(week.0 = 그 주 월요일)
            # 배포된 근무표가 있는 날만, 근무 없음 날은 못 바꾼다
            "edit": (edit_past if d < today else edit_now) and not other and d in by_date and not no_work,
            "commute": [cells[x.key] for x in shift_defs(defs) if x.key in cells],
            "duty": [{"time": cells[x.key]["label"][:5], **cells[x.key]} for x in slot_defs(defs) if x.key in cells],
        }

    days = [[day_info(d) for d in w] for w in weeks]
    months = sorted({d.replace(day=1) for w in weeks for d in w if view == "week" or d.month == anchor.month})
    ctx = {
        "view": view, "title": title, "names": names, "date": anchor, "today_link": (link(view, today) or f"?view={view}&date={today.isoformat()}") + "#today",
        "prev": link(view, prev_d), "next": link(view, next_d),
        "week_link": link("week", anchor), "month_link": link("month", anchor),
        "filter_qs": "".join("&" + urlencode({k: v}) for k, vs in (("dept", depts), ("type", types)) for v in vs),
    }
    ctx.update(_filter_ctx(board, defs, depts, types, shifts, history), weeks=days,
               memo_admin=perms.is_board_admin(request.user, board),
               month_memos=[{"date": m, "memo": notes["month"].get(m)} for m in months])
    return render(request, "duty/roster.html", ctx)


@login_required
def cell(request, d, cell):
    board = _board(request.user)
    defs = boards.defs(board)
    if cell not in by_key(defs):
        raise Http404
    fallback = reverse("day", args=[d])
    if request.method == "POST":
        try:
            # "+"·"-" = 없음(넣기만·빼기만). 기본은 둘 다 고른 맞교환
            before, after = request.POST.get("before"), request.POST.get("after")
            result = changes.exchange(request.user, board, d, cell, _member(None if before == "+" else before),
                                      _member(None if after == "-" else after))
        except DutyError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, "변경했습니다.")
            for w in result:
                messages.warning(request, w)
        return redirect(safe_next(request, fallback))
    depts, types = _filters(request, board)
    ctx = _cell_context(defs, find_day(board, d), cell, d, depts, types, _active_members(board, depts, types))
    ctx.update(next=safe_next(request, fallback))
    return render(request, "duty/_cell_form.html", ctx)


def _neighbor(d, step: int):
    d = d + timedelta(days=step)
    while d.weekday() >= 5:
        d += timedelta(days=step)
    return d


@login_required
def day(request, d):
    board = _board(request.user)
    defs = boards.defs(board)
    pref = prefs.resolve(request.user, request.GET, board, with_view=False)
    depts, types, shifts, history = pref["depts"], pref["types"], pref["shifts"], pref["history"]
    show = (lambda x: x) if history else _latest
    found = find_day(board, d)
    note = memos.for_range(board, d, d)["day"].get(d)
    no_work = bool(note and note.no_work)  # 근무 없음 날은 칸 대신 메모 글만, 바꾸기 없음
    editable = perms.can_edit(request.user, board, d) and not no_work
    members = _active_members(board, depts, types)
    keep, shown = _keeper(depts, types), _shown(shifts)
    sections = []
    if found and not no_work:
        for k in filter(shown, [x.key for x in display_order(defs)]):  # 출근조 먼저, 관제는 뒤에 묶어서
            ctx = _cell_context(defs, found, k, d, depts, types, members)
            ctx.update(
                next=request.path,
                items=_items(show([x for x in found.cells[k].labels if keep(x)]), []),
                removed_items=_items([x for x in found.cells[k].removed if keep(x)], [], True) if history else [],
            )
            sections.append(ctx)
    qs = "?" + urlencode({"f": 1, "dept": depts, "type": types, "shift": shifts}, doseq=True)
    return render(request, "duty/day.html", {
        "d": d, "weekday": DAY_LABELS[d.weekday()], "found": found, "sections": sections,
        "holiday": holidays.closed(d, d).get(d, ""), "note": note,
        "memo_admin": perms.is_board_admin(request.user, board),
        "editable": editable, "prev": _neighbor(d, -1), "next_day": _neighbor(d, 1),
        "qs": qs, **_filter_ctx(board, defs, depts, types, shifts, history),
    })


@login_required
def memo(request, scope, d):
    """[메모] 팝업(근무 변경 창과 같은 방식). 근무표 관리 그룹만."""
    board = _board(request.user)
    if scope not in Memo.Scope.values or not perms.is_board_admin(request.user, board):
        raise Http404
    d = memos.normalize(scope, d)
    fallback = reverse("day", args=[d]) if scope == Memo.Scope.DAY else reverse("roster")
    if request.method == "POST":
        try:
            if request.POST.get("delete"):
                memos.delete(request.user, board, scope, d)
                msg = "메모를 지웠습니다."
            else:
                cleared = memos.save(request.user, board, scope, d, request.POST.get("text", ""),
                                     no_work=bool(request.POST.get("no_work")), confirm=bool(request.POST.get("confirm")))
                msg = f"메모를 저장했습니다. {cleared}명의 근무를 지웠습니다." if cleared else "메모를 저장했습니다."
        except DutyError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, msg)
        return redirect(safe_next(request, fallback))
    return render(request, "duty/_memo_form.html", {
        "scope": scope, "d": d, "memo": memos.for_range(board, d, d)[scope].get(d), "next": safe_next(request, fallback),
        "title": {"day": f"{d:%Y-%m-%d} 메모", "week": f"{d.month}/{d.day} 주 메모", "month": f"{d.year}년 {d.month}월 메모"}[scope],
        "affected": memos.affected(board, d) if scope == Memo.Scope.DAY else 0,
    })


@login_required
def me(request):
    member = request.user if request.user.department_id else None
    board = _board(request.user)
    _, _, shifts = prefs.clean(board, [], [], request.GET.getlist("shift"))
    items = member_schedule(board, member, perms.today(), _shown(shifts)) if member else []
    return render(request, "duty/me.html", {
        "member": member,
        "shift_choices": _shift_choices(boards.defs(board), shifts),
        "items": [{"date": d, "weekday": DAY_LABELS[d.weekday()], "labels": labels, "today": d == perms.today()} for d, labels in items],
    })
