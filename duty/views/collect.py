from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .. import perms
from ..csv_io import CsvInvalid, split_names
from ..errors import DutyError
from ..models import Department, Period, User
from ..services import boards, collect
from ..shifts import DAY_LABELS

MAX_UPLOAD = 1_000_000


@login_required
def index(request):
    depts = list(perms.managed_departments(request.user))
    if not depts:
        raise PermissionDenied
    items = []
    mine = {d.board_id for d in depts}
    for p in Period.objects.filter(status=Period.Status.COLLECTING, board_id__in=mine).order_by("start_date"):
        prog = collect.progress(p)  # 그 회차 근무표의 부서만 있다
        items.append({"period": p, "depts": [(d, prog[d.code]) for d in depts if d.board_id == p.board_id]})
    # 목록이 비었을 때 문구: 근무표의 화면 단계 이름(취합 중 / 입력 중), 겹치는 이름은 한 번만
    waiting = "·".join(dict.fromkeys(d.board.step_name(Period.Status.COLLECTING) for d in depts))
    return render(request, "duty/collect_index.html", {"items": items, "waiting": waiting})


def _load(request, pid, code):
    period = get_object_or_404(Period, pk=pid)
    dept = get_object_or_404(Department, code=code)
    if not perms.can_input_department(request.user, dept):
        raise PermissionDenied
    if period.board_id != dept.board_id:  # 다른 근무표 부서의 표·CSV 는 없는 주소로(서비스는 같은 DutyError)
        raise Http404
    return period, dept


def _render_table(request, period, dept, table, errors, before=None):
    """before: 채우기 전 표(채우기 결과를 그릴 때만). 그것과 다른 칸을 색칠한다."""
    keys = collect.input_keys(dept)
    today, admin = perms.today(), perms.is_board_admin(request.user, period.board)
    skip = boards.skip_reasons(period)  # 건너뛰는 날: 칸을 잠그고(disabled 라 보내지 않는다) 까닭을 보인다
    if skip:  # 잠긴 칸은 POST 에 없으니 늘 DB 값을 보인다(채우기·오류 뒤 다시 그릴 때 비어 보이지 않게)
        saved = collect.load_table(period, dept)
        table = {**table, **{x: saved.get(x, {}) for x in skip}}
        if before is not None:
            before = {**before, **{x: saved.get(x, {}) for x in skip}}
    rows, weeks = [], set()
    for d in period.dates():
        monday = d - timedelta(days=d.weekday())
        cells = [{"name": f"c_{d.isoformat()}_{k}", "value": ", ".join(table.get(d, {}).get(k, [])),
                  "changed": before is not None
                  and sorted(table.get(d, {}).get(k, [])) != sorted(before.get(d, {}).get(k, []))} for k in keys]
        rows.append({"date": d, "weekday": DAY_LABELS[d.weekday()], "locked": d < today and not admin,
                     "closed": skip.get(d, ""), "cells": cells,
                     "week_start": None if monday in weeks else monday})  # 그 주 첫 줄에만: 그 주 월요일(회차가 주 중간에 시작해도)
        weeks.add(monday)
    is_open = period.status == Period.Status.COLLECTING
    return render(request, "duty/collect_table.html", {
        "period": period, "dept": dept, "rows": rows, "errors": errors,
        "shift_labels": list(collect.shift_names(dept).values()),
        "names": list(User.objects.roster().filter(department=dept).order_by("name").values_list("name", flat=True)),
        "is_open": is_open, "back_link": admin, "ncols": len(keys) + 2,  # 회차 화면 링크는 그 근무표 관리자에게만
        "collecting": period.board.step_name(Period.Status.COLLECTING),
        "show_fill": is_open, "can_rotate": collect.can_rotate(dept),  # 채우기 버튼(설계 6.1): 모든 근무표, 입력을 받는 동안
        "filled": before is not None, "changed": sum(c["changed"] for r in rows for c in r["cells"]),
    }, status=400 if errors else 200)


def _posted(request, period, dept):
    posted = {}
    for d in period.dates():
        day = {k: split_names(request.POST.get(f"c_{d.isoformat()}_{k}", "")) for k in collect.input_keys(dept)}
        if any(day.values()):
            posted[d] = day
    return posted


@login_required
def table(request, pid, code):
    period, dept = _load(request, pid, code)
    if request.method == "POST":
        posted = _posted(request, period, dept)
        if request.POST.get("fill"):  # 채우기: 저장하지 않고 그 주를 채운 표를 그려 보여 주기만 한다
            how, _, raw = request.POST["fill"].partition(":")
            try:
                day = date.fromisoformat(raw)
            except ValueError:
                raise Http404
            try:
                keep = None if perms.is_board_admin(request.user, period.board) else perms.today()  # 잠긴 지난 줄은 그대로
                filled = collect.fill_week(period, dept, posted, day, how, keep_before=keep)
            except DutyError as e:
                messages.error(request, str(e))
                return _render_table(request, period, dept, posted, [])
            return _render_table(request, period, dept, filled, [], before=posted)
        try:
            collect.apply_table(request.user, period, dept, posted)
        except CsvInvalid as e:
            return _render_table(request, period, dept, posted, e.errors)
        except DutyError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, "표를 저장했습니다.")
        return redirect("collect_table", pid, code)
    return _render_table(request, period, dept, collect.load_table(period, dept), [])


@login_required
@require_POST
def upload(request, pid, code):
    period, dept = _load(request, pid, code)
    f = request.FILES.get("file")
    if f is None:
        messages.error(request, "CSV 파일을 선택해 주세요.")
        return redirect("collect_table", pid, code)
    if f.size > MAX_UPLOAD:
        messages.error(request, "파일이 너무 큽니다 (최대 1MB).")
        return redirect("collect_table", pid, code)
    try:
        collect.apply_csv(request.user, period, dept, f.read())
    except CsvInvalid as e:
        return _render_table(request, period, dept, collect.load_table(period, dept), e.errors)
    except DutyError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "CSV를 반영했습니다.")
    return redirect("collect_table", pid, code)


@login_required
def export(request, pid, code):
    period, dept = _load(request, pid, code)
    resp = HttpResponse(collect.export_csv(period, dept), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{dept.code}_{period.start_date:%Y%m%d}.csv"'
    return resp
