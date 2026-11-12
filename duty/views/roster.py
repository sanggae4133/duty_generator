from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .. import perms
from ..csv_io import split_names
from ..errors import DutyError
from ..models import Department, User
from ..services import changes, prefs
from ..services.roster import find_day, member_schedule, published_days
from ..shifts import CELLS, COMMUTE_SHIFTS, DAY_LABELS, DEVELOPER, STAFF, cell_label, is_slot_cell
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


DEPT_ORDER = ["MEMS", "TMCH", "MD", "UI"]


def _filters(request) -> tuple[list[str], list[str]]:
    """?dept=MEMS&dept=UI, ?type=직원 → 유효한 값만. 빈 목록 = 전체."""
    d, t, _ = prefs.clean(request.GET.getlist("dept"), request.GET.getlist("type"), [])
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
    return lambda k: not shifts or ("slots" if is_slot_cell(k) else k) in shifts


def _filter_ctx(depts, types, shifts) -> dict:
    return {
        "filter_on": bool(depts or types or shifts),
        "type_choices": [{"code": t, "name": t, "checked": not types or t in types} for t in (STAFF, DEVELOPER)],
        "dept_choices": [
            {"code": d.code, "name": d.name, "checked": not depts or d.code in depts}
            for d in sorted(Department.objects.all(), key=lambda d: DEPT_ORDER.index(d.code) if d.code in DEPT_ORDER else 99)
        ],
        "shift_choices": _shift_choices(shifts),
    }


def _shift_choices(shifts) -> list[dict]:
    return [{"code": c, "name": n, "checked": not shifts or c in shifts} for c, n in prefs.SHIFT_CHOICES.items()]


def _active_members(depts: list[str] | None = None, types: list[str] | None = None):
    qs = User.objects.roster().select_related("department").order_by("name")
    return list(_filtered(qs, depts or [], types or []))


def _cell_context(day, cell: str, d, depts: list[str] | None = None, types: list[str] | None = None):
    current = day.members[cell] if day else []
    qs = User.objects.filter(name__in=current).order_by("name")
    # 출근조 칸: 그날 이미 출근조가 있는 사람은 To 에서 고를 수 없다(한 사람 하루 출근조 하나). 관제는 경고만
    busy = set() if is_slot_cell(cell) or not day else {n for k in COMMUTE_SHIFTS for n in day.members[k]}
    return {
        "d": d, "cell": cell, "label": cell_label(cell), "slot": is_slot_cell(cell), "busy": busy,
        "current_members": list(_filtered(qs, depts or [], types or [])),
    }


LOW, HIGH = date(2000, 1, 1), date(2099, 12, 31)


def _month_shift(d: date, step: int) -> date:
    m = d.month - 1 + step
    return date(d.year + m // 12, m % 12 + 1, 1)


@login_required
def roster(request):
    names = split_names(request.GET.get("q", ""))[:3]  # 구버전 ?q=a,b,c
    names = [request.GET.get(f"q{i}", "").strip() or (names[i - 1] if i <= len(names) else "") for i in (1, 2, 3)]
    today, admin = perms.today(), perms.is_admin(request.user)
    pref = prefs.resolve(request.user, request.GET)
    view, depts, types, shifts = pref["view"], pref["depts"], pref["types"], pref["shifts"]
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
    by_date = {d.date: d for d in published_days(first_day, last_day)}

    def day_cells(d: date) -> dict:
        found = by_date.get(d)
        return {
            k: {
                "key": k, "slot": is_slot_cell(k), "label": cell_label(k),
                "lines": _lines([x for x in found.cells[k].labels if keep(x)], names) if found else [],
                "removed": _lines([x for x in found.cells[k].removed if keep(x)], names, True) if found else [],
            }
            for k in CELLS if shown(k)
        }

    def day_info(d: date) -> dict:
        cells = day_cells(d)
        other = view == "month" and d.month != anchor.month
        return {
            "date": d, "is_today": d == today, "other": other, "empty": d not in by_date,
            "edit": (admin or d >= today) and not other and d in by_date,  # 배포된 근무표가 있는 날만
            "commute": [cells[k] for k in CELLS if not is_slot_cell(k) and k in cells],
            "duty": [{"time": cells[k]["label"][:5], **cells[k]} for k in CELLS if is_slot_cell(k) and k in cells],
        }

    days = [[day_info(d) for d in w] for w in weeks]
    ctx = {
        "view": view, "title": title, "names": names, "date": anchor, "today_link": (link(view, today) or f"?view={view}&date={today.isoformat()}") + "#today",
        "prev": link(view, prev_d), "next": link(view, next_d),
        "week_link": link("week", anchor), "month_link": link("month", anchor),
        "filter_qs": "".join("&" + urlencode({k: v}) for k, vs in (("dept", depts), ("type", types)) for v in vs),
    }
    ctx.update(_filter_ctx(depts, types, shifts), weeks=days)
    return render(request, "duty/roster.html", ctx)


@login_required
def cell(request, d, cell):
    if cell not in CELLS:
        raise Http404
    fallback = reverse("day", args=[d])
    if request.method == "POST":
        try:
            result = changes.change_cell(
                request.user, d, cell, _member(request.POST.get("before")), _member(request.POST.get("after"))
            )
        except DutyError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, "변경했습니다.")
            for w in result:
                messages.warning(request, w)
        return redirect(safe_next(request, fallback))
    depts, types = _filters(request)
    ctx = _cell_context(find_day(d), cell, d, depts, types)
    ctx.update(members=_active_members(depts, types), next=safe_next(request, fallback))
    return render(request, "duty/_cell_form.html", ctx)


def _neighbor(d, step: int):
    d = d + timedelta(days=step)
    while d.weekday() >= 5:
        d += timedelta(days=step)
    return d


@login_required
def day(request, d):
    pref = prefs.resolve(request.user, request.GET, with_view=False)
    depts, types, shifts = pref["depts"], pref["types"], pref["shifts"]
    found = find_day(d)
    editable = perms.is_admin(request.user) or d >= perms.today()
    members = _active_members(depts, types)
    keep, shown = _keeper(depts, types), _shown(shifts)
    sections = []
    if found:
        for k in filter(shown, [*COMMUTE_SHIFTS, *(c for c in CELLS if is_slot_cell(c))]):  # 출근조 먼저, 관제는 뒤에 묶어서
            ctx = _cell_context(found, k, d, depts, types)
            ctx.update(
                members=members, next=request.path,
                items=_items([x for x in found.cells[k].labels if keep(x)], []),
                removed_items=_items([x for x in found.cells[k].removed if keep(x)], [], True),
            )
            sections.append(ctx)
    swap_options = [
        {"value": f"{k}|{m.username}", "text": f"{cell_label(k)} · {m.name}"}  # 맞교환은 필터와 무관하게 전체
        for k in (CELLS if found else []) for m in _cell_context(found, k, d)["current_members"]
    ]
    qs = "?" + urlencode({"f": 1, "dept": depts, "type": types, "shift": shifts}, doseq=True)
    return render(request, "duty/day.html", {
        "d": d, "weekday": DAY_LABELS[d.weekday()], "found": found, "sections": sections,
        "editable": editable, "swap_options": swap_options, "prev": _neighbor(d, -1), "next_day": _neighbor(d, 1),
        "qs": qs, **_filter_ctx(depts, types, shifts),
    })


@login_required
@require_POST
def swap(request, d):
    try:
        cell_a, username_a = request.POST["a"].split("|")
        cell_b, username_b = request.POST["b"].split("|")
        result = changes.swap(
            request.user, d, cell_a, User.objects.get(username=username_a), cell_b, User.objects.get(username=username_b)
        )
    except (KeyError, ValueError, User.DoesNotExist):
        messages.error(request, "맞교환할 두 사람을 골라 주세요.")
    except DutyError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "맞교환했습니다.")
        for w in result:
            messages.warning(request, w)
    return redirect("day", d)


@login_required
def me(request):
    member = request.user if request.user.department_id else None
    _, _, shifts = prefs.clean([], [], request.GET.getlist("shift"))
    items = member_schedule(member, perms.today(), _shown(shifts)) if member else []
    return render(request, "duty/me.html", {
        "member": member,
        "shift_choices": _shift_choices(shifts),
        "items": [{"date": d, "weekday": DAY_LABELS[d.weekday()], "labels": labels, "today": d == perms.today()} for d, labels in items],
    })
