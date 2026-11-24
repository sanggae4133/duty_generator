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
from ..models import Board, ChangeLog, Department, DutyAssignment, Period
from ..services import boards, collect, generate, periods, stats
from ..services import publish as publishing
from ..shifts import LUNCH, by_key, cell_label, day_spans, gen_help, is_slot_cell, josa, slot_defs
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
    mine = list(perms.admin_boards(request.user))  # admin_required 를 지났으니 비어 있지 않다
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
        "periods": Period.objects.filter(board__in=mine).select_related("board").order_by("-start_date"), "boards": mine,
    })


def _empty_confirm(missing, has_slots) -> str:
    """빈 평일이 있을 때만 띄우는 생성 확인창(설계 6.1). 날 수 = 어느 부서든 출근표가 빈 평일."""
    n = len({d for ds in missing.values() for d in ds})
    tail = "고, 아무 부서도 넣지 않은 날은 장중관제도 만들지 않습니다." if has_slots else "습니다."
    return f"출근표가 비어 있는 부서가 있는 날이 {n}일 있습니다. 그날 그 부서는 근무자가 없{tail} 계속할까요?"


def _leave_what(period, active) -> str:
    """생성됨에서 나갈 때 지워지는 배정 이름(설계 5.4). 생성됨 회차는 그 회차에 실제로 있는 배정으로(정의를 꺼도 남은 배정이
    숨지 않게), 그 밖은 켜진 정의로(옮기기 상자 설명)."""
    if period.status == Period.Status.GENERATED:
        cells = set(DutyAssignment.objects.filter(period=period).values_list("cell", flat=True))
        slot, lunch = any(is_slot_cell(c) for c in cells), LUNCH in cells
    else:
        slot, lunch = bool(slot_defs(active)), LUNCH in by_key(active)
    return "·".join(name for name, on in (("장중관제", slot), ("점심당번", lunch)) if on)


def _render_detail(request, period, failures):
    counts, spread, reached = stats.period_duty_counts(period)
    board = period.board
    active = boards.active_defs(board)
    slot_names = [x.name for x in slot_defs(active)]  # generator 의 칸 번호 = 켜진 관제 정의 순서
    S = Period.Status
    targets = board.move_targets(period.status)
    missing = periods.missing_dates(period)
    names = dict(Department.objects.filter(board=board).values_list("code", "name"))
    leave = _leave_what(period, active)
    on = board.steps()
    return render(request, "duty/period_detail.html", {
        "period": period, "board": board, "S": S, "generated_label": board.step_name(S.GENERATED),
        "steps": [(s, board.step_name(s)) for s in on], "editable": board.editable(),
        # 2단계: 버튼 글자·[재생성]·생성 방식·배정 횟수 표는 켜진 관제 정의(데이터)로 정한다(1단계는 임시 기준)
        "buttons": board.step_buttons(bool(slot_names)), "gen_help": gen_help(active),
        "generated_ro": josa(board.step_name(S.GENERATED), "으로/로"),
        "movable": [(s, board.step_name(s)) for s in targets],
        "undo_to": targets[0] if len(targets) == 1 else "",
        "unused_step": period.status not in on,  # 끈 단계에 남은 회차(설계 6.1)
        # 생성됨에서 나가는 확인창은 하나([… 취소] 버튼과 '다른 상태로 옮기기' 상자, 설계 5.4)
        "leave_what": leave,
        "leave_generated_confirm": (f"생성 결과({leave} 배정)가 지워지고 출근표는 그대로 남습니다. 계속할까요?"
                                    if leave else "출근표는 그대로 남습니다. 계속할까요?"),
        "empty_confirm": _empty_confirm(missing, bool(slot_names)) if missing else "",
        "events": [(e, e.from_status and board.step_name(e.from_status), board.step_name(e.to_status))
                   for e in period.events.select_related("by")],
        "input_depts": Department.objects.filter(board=board).order_by("order", "code"),
        # 빈 평일 경고(설계 6.1): 켠 단계의 취합 중·마감에서 부서마다 빈 날 수와 날짜(이어진 평일은 묶어서).
        # '버튼은 누를 수 있지만'은 그 상태에서 생성할 수 있을 때만
        "empty": ([(names[c], len(ds), day_spans(ds)) for c, ds in missing.items()]
                  if period.status in {S.COLLECTING, S.CLOSED} and period.status in on else []),
        "can_generate_now": period.status == board.generate_from(),
        "undo": publishing.unpublish_info(period) if period.status == Period.Status.PUBLISHED else None,
        "progress": [(code, names[code], n, m) for code, (n, m) in collect.progress(period).items()], "missing": missing,
        "counts": counts, "spread": spread, "reached": reached,
        "failures": [{"date": f.date, "slot": slot_names[f.slot], "candidates": f.candidates} for f in failures],
    })


@admin_required
def period_detail(request, pid):
    period = _period(request, pid)
    if request.method == "POST":
        try:
            periods.save_draft(_form_period(request.POST, period), by=request.user)
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
        result = actions[action](period, by=request.user)
    except GenerationError as e:
        return _render_detail(request, period, e.failures)
    except DutyError as e:
        messages.error(request, str(e))
    else:
        period.refresh_from_db()
        done = f"'{period.board.step_name(period.status)}' 상태로 바꿨습니다."
        if action == "generate":
            done += " 근무표 화면에는 배포한 뒤에 보입니다."
        messages.success(request, done)
        for w in getattr(result, "warnings", ()):  # 생성: 점심당번을 못 채운 날
            messages.warning(request, w)
    return redirect("period_detail", pid)


@admin_required
@require_POST
def period_delete(request, pid):
    period = _period(request, pid)
    try:
        periods.delete(period, by=request.user)
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
    try:
        start = date.fromisoformat(raw) if raw else None
    except ValueError:
        start = None
    if request.method == "POST" and start is None:
        messages.error(request, "덮어쓰기 시작일이 올바르지 않습니다.")
        return redirect("period_detail", pid)
    start = start or min(max(perms.today(), period.start_date), period.end_date)
    try:
        if request.method == "POST":
            publishing.publish(period, start, by=request.user)
            messages.success(request, "배포했습니다.")
            return redirect("period_detail", pid)
        preview = publishing.preview_publish(period, start)
    except DutyError as e:
        messages.error(request, str(e))
        return redirect("period_detail", pid)
    past = (perms.today() - start).days  # 이미 지난 날도 덮어쓰면 경고(막지는 않는다)
    return render(request, "duty/publish.html", {"period": period, "preview": preview, "past_days": max(past, 0)})


@admin_required
def stats_view(request):
    start, end = date_param(request, "from"), date_param(request, "to")
    # ponytail: 관제가 있는 내 근무표 중 id 가 가장 작은 것 하나. 관제 있는 근무표가 둘째로 생기면 근무표 select
    board = perms.stats_boards(request.user).order_by("id").first()
    if board is None:
        raise PermissionDenied
    rows, duty_summary, total_summary = stats.member_stats(board, start, end)
    names = {d.key: d.name for d in boards.defs(board)}
    return render(request, "duty/stats.html", {
        "board": board, "dawn": names.get("dawn", "새벽"), "night": names.get("night", "야간"),
        "rows": rows, "duty": duty_summary, "total": total_summary, "start": start, "end": end,
    })


LOG_LIMIT = 500  # 변경 이력 한 화면에 보이는 최대 건수


@admin_required
def change_log(request):
    mine = list(perms.admin_boards(request.user))
    qs = (ChangeLog.objects.filter(period__board__in=mine)  # 내가 관리하는 근무표만(설계 9절)
          .select_related("by", "before", "after", "period__board").order_by("-at", "-id"))
    board_code = request.GET.get("board", "")
    if board_code:  # 근무표 필터(내가 관리하는 근무표가 둘 이상일 때 보인다). 남의 근무표 코드는 빈 결과
        qs = qs.filter(period__board__code=board_code)
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
            "at": log.at, "by": (log.by.name or log.by.username) if log.by else "(예전 기록)", "date": log.date,
            "cell": cell_label(defs[log.period.board_id], log.cell),
            "before": join_reason(log.before.name, log.reason_before) if log.before else "",
            "after": join_reason(log.after.name, log.reason_after) if log.after else "", "period": log.period.name,
            "board": log.period.board.name,
        }
        for log in qs[:LOG_LIMIT + 1]
    ]
    return render(request, "duty/changes.html", {"logs": logs[:LOG_LIMIT], "cut": len(logs) > LOG_LIMIT, "name": name, "by": by, "start": start, "end": end,
                                                 "board_choices": mine if len(mine) > 1 else [], "board_code": board_code})
