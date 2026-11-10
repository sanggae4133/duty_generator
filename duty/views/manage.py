from datetime import date

from django.apps import apps
from django.contrib import messages
from django.db import connection
from django.db.models import CheckConstraint, Q, UniqueConstraint
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
            p = periods.save_draft(_form_period(request.POST))
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
        "open": periods.open_collecting,
        "close": periods.close_collecting,
        "generate": generate.run_generation,
    }
    if action not in actions:
        raise Http404
    try:
        actions[action](period)
    except GenerationError as e:
        return _render_detail(request, period, e.failures)
    except DutyError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "완료했습니다.")
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
            publishing.publish(period, start)
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


MODEL_DESC = {
    "Department": "부서와 부서별 출근조 구성",
    "Member": "멤버(이름·소속·유형·재직, 로그인 계정 연결)",
    "Period": "근무 회차와 상태",
    "Commute": "날짜별 출근조 배정",
    "ControlDuty": "날짜별 장중관제 칸 배정",
    "ChangeLog": "근무 변경 이력(교체·추가·제거)",
}


def _default(f) -> str:
    if not f.has_default():
        return "-"
    return "함수" if callable(f.default) else repr(f.default)


def _column(f) -> dict:
    rel = f.remote_field
    return {
        "name": f.name, "column": f.column, "type": f.db_type(connection), "null": f.null,
        "pk": f.primary_key, "unique": f.unique and not f.primary_key,
        "fk": f"{f.related_model._meta.db_table} ({rel.on_delete.__name__})" if rel else "",
        "default": _default(f),
        "choices": ", ".join(f"{v}={l}" for v, l in f.choices) if f.choices else "",
    }


def _model_info(m) -> dict:
    o = m._meta
    constraints = []
    for c in o.constraints:
        if isinstance(c, UniqueConstraint):
            constraints.append({"name": c.name, "kind": "UNIQUE", "fields": ", ".join(c.fields), "condition": str(c.condition or "")})
        elif isinstance(c, CheckConstraint):
            constraints.append({"name": c.name, "kind": "CHECK", "fields": "", "condition": str(getattr(c, "condition", None) or "")})
        else:
            constraints.append({"name": c.name, "kind": type(c).__name__, "fields": "", "condition": ""})
    constraints += [{"name": "unique_together", "kind": "UNIQUE", "fields": ", ".join(t), "condition": ""} for t in o.unique_together]
    return {
        "name": m.__name__, "table": o.db_table, "desc": MODEL_DESC.get(m.__name__, ""),
        "columns": [_column(f) for f in o.concrete_fields],
        "m2m": [
            {"name": f.name, "table": f.remote_field.through._meta.db_table,
             "cols": f"{f.m2m_column_name()}, {f.m2m_reverse_name()}"}
            for f in o.many_to_many
        ],
        "constraints": constraints,
        "indexes": [{"name": i.name, "fields": ", ".join(i.fields)} for i in o.indexes],
    }


@admin_required
def schema(request):
    return render(request, "duty/schema.html", {"models": [_model_info(m) for m in apps.get_app_config("duty").get_models()]})
