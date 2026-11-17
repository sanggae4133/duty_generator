from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .. import perms
from ..csv_io import join_reason
from ..errors import DutyError
from ..generator import GenerationError
from ..models import Board, ChangeLog, Department, Period, User
from ..services import boards, collect, generate, periods, stats
from ..services import groups as group_service
from ..services import publish as publishing
from ..shifts import cell_label, josa, slot_defs
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
        "periods": Period.objects.filter(board__in=mine).select_related("board").order_by("-start_date"), "boards": mine,
    })


def _render_detail(request, period, failures):
    counts, spread, reached = stats.period_duty_counts(period)
    board = period.board
    active = boards.active_defs(board)
    slot_names = [x.name for x in slot_defs(active)]  # generator 의 칸 번호 = 켜진 관제 정의 순서
    legacy = boards.legacy_admin_entry(board)  # 1단계 임시 기준: 옛 직접 입력의 [표 입력]·빈 평일 경고·확인창(2단계에서 지운다)
    S = Period.Status
    targets = board.move_targets(period.status)
    # 1단계: 버튼 글자·[재생성]은 main 처럼 임시 기준으로(옛 직접 입력 = [확정], 그 밖 = [장중관제 생성]·[재생성]).
    # 관제 정의가 켜진 옛 직접 입력 근무표도 지금 화면 그대로다. 2단계에서 관제 정의(데이터) 기준으로 바꾼다
    buttons = board.step_buttons(not legacy)
    gen, undo_label = buttons["generate"], targets and board.step_name(targets[0])
    return render(request, "duty/period_detail.html", {
        "period": period, "board": board, "S": S, "legacy": legacy, "generated_label": board.step_name(S.GENERATED),
        "steps": [(s, board.step_name(s)) for s in board.steps()], "editable": board.editable(),
        "buttons": buttons, "generate_topic": gen + josa(gen, "은/는"),
        "generated_ro": josa(board.step_name(S.GENERATED), "으로/로"),
        "movable": [(s, board.step_name(s)) for s in targets],
        "undo_to": targets[0] if len(targets) == 1 else "",
        "undo_confirm": (f"{gen}{josa(gen, '을/를')} 취소하고 {undo_label}{josa(undo_label, '으로/로')} 돌아갈까요? "
                         "출근표는 그대로 남습니다.") if len(targets) == 1 else "",
        "events": [(e, e.from_status and board.step_name(e.from_status), board.step_name(e.to_status))
                   for e in period.events.select_related("by")],
        "input_depts": Department.objects.filter(board=board).order_by("order", "code") if legacy else [],
        "empty_days": periods.empty_days(period) if legacy and period.status == S.COLLECTING else [],
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
        result = actions[action](period, by=request.user)
    except GenerationError as e:
        return _render_detail(request, period, e.failures)
    except DutyError as e:
        messages.error(request, str(e))
    else:
        period.refresh_from_db()
        done = f"'{period.board.step_name(period.status)}' 상태로 바꿨습니다."
        if action == "generate" and boards.legacy_admin_entry(period.board):
            done = "확정했습니다. 근무표 화면에는 배포한 뒤에 보입니다. 아래 경고를 확인하고 [배포…]를 누르세요."
        messages.success(request, done)
        for w in getattr(result, "warnings", ()):  # 생성: 점심당번을 못 채운 날
            messages.warning(request, w)
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
    mine = list(perms.admin_boards(request.user).order_by("id"))
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
            "at": log.at, "by": (log.by.name or log.by.username) if log.by else "시트 가져오기", "date": log.date,
            "cell": cell_label(defs[log.period.board_id], log.cell),
            "before": join_reason(log.before.name, log.reason_before) if log.before else "",
            "after": join_reason(log.after.name, log.reason_after) if log.after else "", "period": log.period.name,
            "board": log.period.board.name,
        }
        for log in qs[:500]
    ]
    return render(request, "duty/changes.html", {"logs": logs, "name": name, "by": by, "start": start, "end": end,
                                                 "board_choices": mine if len(mine) > 1 else [], "board_code": board_code})


def _about(group) -> str:
    """그룹이 무슨 권한인지 한 줄(나이 든 관리자가 그룹 이름만 보고 헷갈리지 않게)."""
    board = getattr(group, "admin_board", None)
    if board:
        return f"{board.name} 근무표 관리자(회차·배포·메모·지난 날짜 수정)"
    dept = getattr(group, "input_department", None)
    return f"{dept.name} 출근표 입력 담당" if dept else ""


@login_required
def groups(request):
    """그룹 화면(설계 7절): 내가 그룹 관리자인 그룹의 멤버를 보고 넣고 뺀다. 그룹 관리자가 아니면 403."""
    kept = list(perms.kept_groups(request.user).order_by("name").prefetch_related("user_set__department"))
    if not kept:
        raise PermissionDenied
    if request.method == "POST":
        group = next((g for g in kept if str(g.pk) == request.POST.get("group")), None)
        pid = request.POST.get("member", "")
        member = User.objects.filter(pk=pid).first() if pid.isdigit() else None
        do = request.POST.get("do")
        if group is None or member is None or do not in ("add", "remove"):  # 맡지 않은 그룹·없는 사람·모르는 동작
            raise Http404
        try:
            if do == "remove":
                warning = group_service.remove_member(request.user, group, member)
                messages.success(request, f"{member.name}을(를) {group.name}에서 뺐습니다.")
                if warning:
                    messages.warning(request, warning)
            else:
                group_service.add_member(request.user, group, member)
                messages.success(request, f"{member.name}을(를) {group.name}에 넣었습니다.")
        except DutyError as e:
            messages.error(request, str(e))
        return redirect("groups")
    active = list(User.objects.filter(is_active=True).select_related("department").order_by("name"))
    items = []
    for g in kept:
        members = sorted(g.user_set.all(), key=lambda u: u.name)
        ids = {u.pk for u in members}
        items.append({"group": g, "about": _about(g), "members": members,
                      "candidates": [u for u in active if u.pk not in ids]})  # 후보 = 재직 계정(퇴사자는 넣지 않는다)
    return render(request, "duty/groups.html", {"items": items})
