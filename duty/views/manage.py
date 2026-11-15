from datetime import date

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .. import perms
from ..csv_io import join_reason
from ..errors import DutyError
from ..generator import GenerationError
from ..models import Board, ChangeLog, Period
from ..services import boards, collect, generate, periods, stats
from ..services import publish as publishing
from ..shifts import cell_label, slot_defs
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


def _new_board(post, mine: list[Board]) -> Board:
    """새 회차의 근무표: 관리하는 근무표가 하나면 그것, 여럿이면 폼에서 고른 것(내 근무표 중에서만)."""
    if len(mine) == 1:
        return mine[0]
    picked = [b for b in mine if str(b.pk) == post.get("board", "")]
    if not picked:
        raise ValueError("근무표를 고르세요.")
    return picked[0]


def _period(request, pid) -> Period:
    """회차 뷰 공통: 내가 관리하는 근무표의 회차만. 아니면 없는 회차처럼 404(설계 9절)."""
    period = get_object_or_404(Period.objects.select_related("board"), pk=pid)
    if not perms.is_board_admin(request.user, period.board):
        raise Http404
    return period


@admin_required
def period_list(request):
    mine = list(perms.admin_boards(request.user).order_by("id"))  # admin_required 를 지났으니 비어 있지 않다
    if request.method == "POST":
        try:
            period = _form_period(request.POST)
            period.board = _new_board(request.POST, mine)
            p = periods.save_draft(period, by=request.user)
        except (KeyError, ValueError):
            messages.error(request, "이름과 기간을 확인해 주세요.")
        except DutyError as e:
            messages.error(request, str(e))
        else:
            return redirect("period_detail", p.pk)
        return redirect("periods")
    return render(request, "duty/periods.html", {
        "periods": Period.objects.filter(board__in=mine).order_by("-start_date"), "boards": mine,
    })


def _render_detail(request, period, failures):
    counts, spread, reached = stats.period_duty_counts(period)
    slot_names = [x.name for x in slot_defs(boards.active_defs(period.board))]  # generator 의 칸 번호 = 켜진 관제 정의 순서
    return render(request, "duty/period_detail.html", {
        "period": period, "S": Period.Status,
        "steps": Period.Status.choices, "movable": [] if period.status == Period.Status.PUBLISHED
        else [(s, Period.Status(s).label) for s in periods.MOVABLE if s != period.status],
        "events": period.events.select_related("by"),
        "undo": publishing.unpublish_info(period) if period.status == Period.Status.PUBLISHED else None,
        "progress": collect.progress(period), "missing": periods.missing_dates(period),
        "counts": counts, "spread": spread, "reached": reached,
        "failures": [{"date": f.date, "slot": slot_names[f.slot], "candidates": f.candidates} for f in failures],
    })


@admin_required
def period_detail(request, pid):
    period = _period(request, pid)
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
    period = _period(request, pid)
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
def period_delete(request, pid):
    period = _period(request, pid)
    try:
        periods.delete(period)
    except DutyError as e:
        messages.error(request, str(e))
        return redirect("period_detail", pid)
    messages.success(request, f"회차 '{period.name}'을(를) 지웠습니다.")
    return redirect("periods")


@admin_required
@require_POST
def period_move(request, pid):
    period = _period(request, pid)
    try:
        periods.move(period, request.POST.get("to", ""), by=request.user)
    except DutyError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "상태를 바꿨습니다.")
    return redirect("period_detail", pid)


@admin_required
def period_publish(request, pid):
    period = _period(request, pid)
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
    board = perms.stats_boards(request.user).order_by("id").first()  # 관제가 있는 내 근무표 중 첫 것(고르기는 2단계)
    if board is None:
        raise PermissionDenied
    rows, duty_summary, total_summary = stats.member_stats(board, start, end)
    return render(request, "duty/stats.html", {
        "rows": rows, "duty": duty_summary, "total": total_summary, "start": start, "end": end,
    })


@admin_required
def change_log(request):
    qs = (ChangeLog.objects.filter(period__board__in=perms.admin_boards(request.user))  # 내가 관리하는 근무표만(설계 9절)
          .select_related("by", "before", "after", "period").order_by("-at", "-id"))
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
        qs = qs.filter(Q(by__username=by) | Q(by__name=by))
    defs = {b.pk: boards.defs(b) for b in Board.objects.all()}  # 근무표마다 한 번만 읽는다
    logs = [
        {
            "at": log.at, "by": (log.by.name or log.by.username) if log.by else "시트 가져오기", "date": log.date,
            "cell": cell_label(defs[log.period.board_id], log.cell),
            "before": join_reason(log.before.name, log.reason_before) if log.before else "",
            "after": join_reason(log.after.name, log.reason_after) if log.after else "", "period": log.period.name,
        }
        for log in qs[:500]
    ]
    return render(request, "duty/changes.html", {"logs": logs, "name": name, "by": by, "start": start, "end": end})

