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
from ..models import Member
from ..services import changes
from ..services.roster import DEPT_VIEWS, department_table, find_day, member_schedule, published_days
from ..shifts import CELLS, DAY_LABELS, cell_label, is_slot_cell
from .common import date_param, safe_next


def _hl(label: str, names: list[str]) -> int:
    """라벨(A, A>B>C, +B)에 속한 이름 중 검색어 번호(1..3, 낮은 쪽 우선). 없으면 0."""
    parts = [p.strip().lstrip("+") for p in label.split(">")]
    return next((i for i, n in enumerate(names, 1) if n in parts), 0)


def _lines(labels: list[str], names: list[str], per_line: int = 3) -> list[list[dict]]:
    items = [{"text": lb, "hl": _hl(lb, names)} for lb in labels]
    return [items[i:i + per_line] for i in range(0, len(items), per_line)]


def _member(code: str | None) -> Member | None:
    if not code:
        return None
    m = Member.objects.filter(code=code).first()
    if m is None:
        raise DutyError("없는 멤버입니다.")  # 조작된 코드가 '삭제'로 해석되지 않게
    return m


def _active_members():
    return list(Member.objects.filter(is_active=True).select_related("department").order_by("name"))


def _cell_context(day, cell: str, d):
    current = day.members[cell] if day else []
    return {
        "d": d, "cell": cell, "label": cell_label(cell), "slot": is_slot_cell(cell),
        "current_members": list(Member.objects.filter(name__in=current).order_by("name")),
    }


def _month_shift(d: date, step: int) -> date:
    m = d.month - 1 + step
    return date(d.year + m // 12, m % 12 + 1, 1)


@login_required
def roster(request):
    names = split_names(request.GET.get("q", ""))[:3]  # 구버전 ?q=a,b,c
    names = [request.GET.get(f"q{i}", "").strip() or (names[i - 1] if i <= len(names) else "") for i in (1, 2, 3)]
    today, admin = perms.today(), perms.is_admin(request.user)
    view = "month" if request.GET.get("view") == "month" else "week"
    anchor = date_param(request, "date") or today

    def link(v: str, d: date) -> str:
        params = {"view": v, "date": d.isoformat(), **{f"q{i}": n for i, n in enumerate(names, 1) if n}}
        return "?" + urlencode(params)

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
                "lines": _lines(found.cells[k].labels, names) if found else [],
                "removed": _lines(found.cells[k].removed, names) if found else [],
                "changed": bool(found and found.cells[k].changed),
            }
            for k in CELLS
        }

    def day_info(d: date) -> dict:
        cells = day_cells(d)
        return {
            "date": d, "weekday": DAY_LABELS[d.weekday()], "is_today": d == today,
            "editable": admin or d >= today, "cells": cells,
            "other": view == "month" and d.month != anchor.month,
            "commute": [cells[k] for k in CELLS if not is_slot_cell(k)],
            "duty": [{"time": cells[k]["label"][:5], **cells[k]} for k in CELLS if is_slot_cell(k)],
        }

    days = [[day_info(d) for d in w] for w in weeks]
    ctx = {
        "view": view, "title": title, "names": names, "date": anchor, "today_link": link(view, today) + "#today",
        "prev": link(view, prev_d), "next": link(view, next_d),
        "week_link": link("week", anchor), "month_link": link("month", anchor),
        "carry": [(f"q{i}", n) for i, n in enumerate(names, 1) if n],
    }
    if view == "week":
        ctx["days"] = days[0]
        ctx["rows"] = [
            {"label": cell_label(k), "slot": is_slot_cell(k), "cells": [{**dd["cells"][k], "d": dd} for dd in days[0]]} for k in CELLS
        ]
    else:
        ctx["weeks"] = days
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
            for w in result.warnings:
                messages.warning(request, w)
        return redirect(safe_next(request, fallback))
    ctx = _cell_context(find_day(d), cell, d)
    ctx.update(members=_active_members(), next=safe_next(request, fallback))
    return render(request, "duty/_cell_form.html", ctx)


def _neighbor(d, step: int):
    d = d + timedelta(days=step)
    while d.weekday() >= 5:
        d += timedelta(days=step)
    return d


@login_required
def day(request, d):
    found = find_day(d)
    editable = perms.is_admin(request.user) or d >= perms.today()
    members = _active_members()
    sections = []
    if found:
        for k in CELLS:
            ctx = _cell_context(found, k, d)
            ctx.update(
                members=members, next=request.path, labels=found.cells[k].labels,
                removed=found.cells[k].removed, changed=found.cells[k].changed,
            )
            sections.append(ctx)
    swap_options = [
        {"value": f"{s['cell']}|{m.code}", "text": f"{s['label']} · {m.name}"}
        for s in sections for m in s["current_members"]
    ]
    return render(request, "duty/day.html", {
        "d": d, "weekday": DAY_LABELS[d.weekday()], "found": found, "sections": sections,
        "editable": editable, "swap_options": swap_options, "prev": _neighbor(d, -1), "next_day": _neighbor(d, 1),
    })


@login_required
@require_POST
def swap(request, d):
    try:
        cell_a, code_a = request.POST["a"].split("|")
        cell_b, code_b = request.POST["b"].split("|")
        result = changes.swap(
            request.user, d, cell_a, Member.objects.get(code=code_a), cell_b, Member.objects.get(code=code_b)
        )
    except (KeyError, ValueError, Member.DoesNotExist):
        messages.error(request, "맞교환할 두 사람을 골라 주세요.")
    except DutyError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "맞교환했습니다.")
        for w in result.warnings:
            messages.warning(request, w)
    return redirect("day", d)


@login_required
def dept(request, key):
    if key not in DEPT_VIEWS:
        raise Http404
    title, header, rows = department_table(key, date_param(request, "from"), date_param(request, "to"))
    return render(request, "duty/dept.html", {
        "key": key, "title": title, "header": header, "rows": rows,
        "tabs": [(k, v[0]) for k, v in DEPT_VIEWS.items()],
    })


@login_required
def me(request):
    member = perms.member_of(request.user)
    items = member_schedule(member, perms.today()) if member else []
    return render(request, "duty/me.html", {
        "member": member,
        "items": [{"date": d, "weekday": DAY_LABELS[d.weekday()], "labels": labels} for d, labels in items],
    })
