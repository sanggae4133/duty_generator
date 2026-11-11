from datetime import date

from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .. import perms
from ..errors import DutyError
from ..generator import GenerationError
from ..models import ChangeLog, Period
from ..services import collect, generate, periods, stats
from ..services import publish as publishing
from ..shifts import CONTROL_SLOTS, cell_label
from .common import admin_required, date_param


def _form_period(post, period: Period | None = None) -> Period:
    name = post.get("name", "").strip()
    if not name:
        raise ValueError("이름이 비어 있습니다.")
    period = period or Period()
    period.name = name
    period.start_date = date.fromisoformat(post["start_date"])
    period.end_date = date.fromisoformat(post["end_date"])
    return period


@admin_required
def period_list(request):
    if request.method == "POST":
        try:
            p = periods.save_draft(_form_period(request.POST), by=request.user)
        except (KeyError, ValueError):
            messages.error(request, "이름과 기간을 확인해 주세요.")
        except DutyError as e:
            messages.error(request, str(e))
        else:
            return redirect("period_detail", p.pk)
        return redirect("periods")
    return render(request, "duty/periods.html", {"periods": Period.objects.order_by("-start_date")})


def _render_detail(request, period, failures):
    counts, spread, reached = stats.period_duty_counts(period)
    return render(request, "duty/period_detail.html", {
        "period": period, "S": Period.Status,
        "steps": Period.Status.choices, "movable": [] if period.status == Period.Status.PUBLISHED
        else [(s, Period.Status(s).label) for s in periods.MOVABLE if s != period.status],
        "events": period.events.select_related("by"),
        "undo": publishing.unpublish_info(period) if period.status == Period.Status.PUBLISHED else None,
        "progress": collect.progress(period), "missing": periods.missing_dates(period),
        "counts": counts, "spread": spread, "reached": reached,
        "failures": [{"date": f.date, "slot": CONTROL_SLOTS[f.slot][0], "candidates": f.candidates} for f in failures],
    })


@admin_required
def period_detail(request, pid):
    period = get_object_or_404(Period, pk=pid)
    if request.method == "POST":
        try:
            periods.save_draft(_form_period(request.POST, period))
        except (KeyError, ValueError):
            messages.error(request, "이름과 기간을 확인해 주세요.")
        except DutyError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, "저장했습니다.")
        return redirect("period_detail", pid)
    return _render_detail(request, period, [])


@admin_required
@require_POST
def period_action(request, pid, action):
    period = get_object_or_404(Period, pk=pid)
    actions = {
        "open": lambda p, by: periods.move(p, Period.Status.COLLECTING, by),
        "close": lambda p, by: periods.move(p, Period.Status.CLOSED, by),
        "generate": lambda p, by: generate.run_generation(p, by=by),
        "unpublish": publishing.unpublish,
    }
    if action not in actions:
        raise Http404
    try:
        actions[action](period, by=request.user)
    except GenerationError as e:
        return _render_detail(request, period, e.failures)
    except DutyError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "완료했습니다.")
    return redirect("period_detail", pid)


@admin_required
@require_POST
def period_move(request, pid):
    period = get_object_or_404(Period, pk=pid)
    try:
        periods.move(period, request.POST.get("to", ""), by=request.user)
    except DutyError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "상태를 바꿨습니다.")
    return redirect("period_detail", pid)


@admin_required
def period_publish(request, pid):
    period = get_object_or_404(Period, pk=pid)
    raw = request.POST.get("from") or request.GET.get("from")
    default = min(max(perms.today(), period.start_date), period.end_date)
    try:
        start = date.fromisoformat(raw) if raw else default
    except ValueError:
        start = default
    if request.method == "POST" and (not raw or start is default):
        messages.error(request, "덮어쓰기 시작일이 올바르지 않습니다.")
        return redirect("period_detail", pid)
    try:
        if request.method == "POST":
            publishing.publish(period, start, by=request.user)
            messages.success(request, "배포했습니다.")
            return redirect("period_detail", pid)
        preview = publishing.preview_publish(period, start)
    except DutyError as e:
        messages.error(request, str(e))
        return redirect("period_detail", pid)
    return render(request, "duty/publish.html", {"period": period, "preview": preview})


@admin_required
def stats_view(request):
    start, end = date_param(request, "from"), date_param(request, "to")
    rows, duty_summary, total_summary = stats.member_stats(start, end)
    return render(request, "duty/stats.html", {
        "rows": rows, "duty": duty_summary, "total": total_summary, "start": start, "end": end,
    })


@admin_required
def change_log(request):
    qs = ChangeLog.objects.select_related("by", "before", "after", "period").order_by("-at", "-id")
    start, end = date_param(request, "from"), date_param(request, "to")
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    name = request.GET.get("name", "").strip()
    if name:
        qs = qs.filter(Q(before__name=name) | Q(after__name=name))
    by = request.GET.get("by", "").strip()
    if by:
        qs = qs.filter(by__username=by)
    logs = [
        {
            "at": log.at, "by": log.by.username if log.by else "import", "date": log.date,
            "cell": cell_label(log.cell), "before": log.before.name if log.before else "",
            "after": log.after.name if log.after else "", "period": log.period.name,
        }
        for log in qs[:500]
    ]
    return render(request, "duty/changes.html", {"logs": logs, "name": name, "by": by, "start": start, "end": end})

