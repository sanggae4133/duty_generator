"""[근무표 설정](근무표 통합 설계 7절): 근무표 관리자가 그 근무표의 사람·관리자·입력 담당자·근무 정의와 부서·회차 단계를 고치는
한 화면(/settings/?board=<code>). 칸마다 따로 저장하고 저장 뒤 그 칸(#앵커)으로 돌아온다. 결과 메시지는 extra_tags 에 칸 id 를
넣어 그 칸 제목 바로 아래에 그린다(base.html 맨 위에는 칸 태그가 없는 메시지만). DB 쓰기는 services/board_settings.py."""
import re

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from .. import accounts, perms
from ..errors import DutyError
from ..forms import StepsForm, shift_forms
from ..models import Board, Department, Period, User
from ..services import board_settings, boards, prefs
from ..shifts import DEVELOPER, STAFF, josa, shift_defs, slot_defs
from .common import admin_required, int_param


def _mine(request) -> list[Board]:
    return list(perms.admin_boards(request.user))  # admin_required 를 지났으니 비어 있지 않다


def _board(request) -> Board:
    """?board=<code> 의 근무표: 내가 관리하는 근무표만(아니면 404, 회차 화면과 같은 방식). 없으면 내 근무표(관리할 때) → 관리하는 첫 근무표."""
    mine, code = _mine(request), request.GET.get("board")
    if code:
        board = next((b for b in mine if b.code == code), None)
        if board is None:
            raise Http404
        return board
    home = boards.home(request.user)
    return next((b for b in mine if b.pk == getattr(home, "pk", None)), mine[0])


def _here(board) -> str:
    return f"{reverse('board_settings')}?board={board.code}"


def _user(request) -> User:
    pid = int_param(request.POST.get("user"))
    user = User.objects.filter(pk=pid).first() if pid is not None else None
    if user is None:
        raise Http404
    return user


def _dept(request) -> Department:
    dept = Department.objects.filter(pk=request.POST.get("dept", "")).first()
    if dept is None:
        raise Http404
    return dept


def _add_admin(request, board):
    user = _user(request)
    board_settings.add_admin(request.user, board, user)
    return f"{user.name}{josa(user.name, '을/를')} 관리자로 넣었습니다."


def _remove_admin(request, board):
    user = _user(request)
    board_settings.remove_admin(request.user, board, user)
    if user.pk == request.user.pk:  # 나를 뺐다: 이 근무표 설정에는 더 들어올 수 없다
        messages.success(request, f"{board.name} 관리자에서 나를 뺐습니다.")
        return redirect("board_settings" if perms.is_admin(request.user) else "roster")
    return f"{user.name}{josa(user.name, '을/를')} 관리자에서 뺐습니다."


def _add_assignee(request, board):
    dept, user = _dept(request), _user(request)
    board_settings.add_assignee(request.user, board, dept, user)
    return f"{user.name}{josa(user.name, '을/를')} {dept.name} 입력 담당자로 넣었습니다."


def _remove_assignee(request, board):
    dept, user = _dept(request), _user(request)
    board_settings.remove_assignee(request.user, board, dept, user)
    return f"{user.name}{josa(user.name, '을/를')} {dept.name} 입력 담당자에서 뺐습니다."


def _add_person(request, board):
    p, dept = request.POST, _dept(request)
    try:
        user = board_settings.add_person(request.user, board, p.get("username", "").strip(), p.get("name", ""), dept,
                                         p.get("type"))
    except DutyError as e:  # 보낸 값 그대로 다시 그리고 오류는 폼 바로 위에(설계 7.3)
        return _render(request, board, add={k: p.get(k, "") for k in ("name", "username", "dept", "type")} | {"error": str(e)})
    return (f"{user.name}{josa(user.name, '을/를')} 추가했습니다(아이디 {user.username}). "
            "표에서 [계정 발급]을 눌러 임시 비밀번호를 주세요.")


def _set_person(request, board):
    user, p = _user(request), request.POST
    try:
        board_settings.set_person(request.user, board, user, p.get("name", ""), p.get("type"))
    except DutyError as e:  # 그 줄을 펼친 채 보낸 값과 오류를 그 줄 안에
        return _render(request, board, edit={"pk": user.pk, "name": p.get("name", ""), "type": p.get("type", ""),
                                             "error": str(e)})
    name = p.get("name", "").strip()
    return f"{name}{josa(name, '을/를')} 저장했습니다."


def _cells(request, board, user, cells) -> list[tuple[str, str]]:
    """남은 근무 목록 (링크, 글 "12/3 정상 — 12월 회차(배포됨)"): 배포된 날은 하루 화면, 배포 전 회차의 출근표 칸은 그 사람 부서의
    입력 표, 생성된 회차의 당번 칸(점심당번·장중관제, 입력 표에 없다)은 회차 화면."""
    q = boards.board_query(request.user, board)
    shifts = {x.name for x in shift_defs(boards.defs(board))}

    def url(d, cell, p):
        if p.status == Period.Status.PUBLISHED:
            return reverse("day", args=[d]) + q
        if cell in shifts:
            return reverse("collect_table", args=[p.pk, user.department_id])
        return reverse("period_detail", args=[p.pk])
    return [(url(d, cell, p), f"{d.month}/{d.day} {cell} — {p.name}({step})") for d, cell, p, step in cells]


def _leave(request, board):
    user, confirm = _user(request), int_param(request.POST.get("confirm"))
    try:
        cells = board_settings.set_active(request.user, board, user, False, confirm)
    except board_settings.NeedsConfirm as e:  # 오늘 이후 근무가 남았다: 그 줄 아래에 목록과 [그래도 퇴사 처리](본 칸 수)
        rows = _cells(request, board, user, board_settings.future_cells(board, user))
        return _render(request, board, leave={"pk": user.pk, "cells": rows, "msg": str(e), "n": len(rows)})
    messages.success(request, f"{user.name}{josa(user.name, '을/를')} 퇴사 처리했습니다. [다시 재직]으로 되돌릴 수 있습니다.",
                     extra_tags="people")
    if cells:  # 퇴사 뒤에도 남은 근무를 링크로(설계 7.2). format_html 이라 회차 이름은 이스케이프된다
        messages.warning(request, format_html(
            "남은 근무 {}칸 — 근무표·입력 표에서 다른 사람으로 바꾸세요.<ul>{}</ul>", len(cells),
            format_html_join("", '<li><a href="{}">{}</a></li>', _cells(request, board, user, cells))), extra_tags="people")
    return redirect(f"{_here(board)}#people")


def _rejoin(request, board):
    user = _user(request)
    board_settings.set_active(request.user, board, user, True)
    return f"{user.name}{josa(user.name, '을/를')} 다시 재직으로 돌렸습니다. 로그인하려면 [계정 발급]을 다시 누르세요."


def _issue(request, board):
    ids = set(request.POST.getlist("users"))  # 같은 사람을 두 번 보내도 한 번만 발급(두 번째 비밀번호가 첫 번째를 덮지 않게)
    users = list(User.objects.filter(pk__in=[i for i in map(int_param, ids) if i is not None]))
    if len(users) != len(ids):  # 없는 id 가 섞였다
        raise Http404
    issued = board_settings.issue(request.user, board, users)
    # 임시 비밀번호는 이 응답 본문에만: redirect·messages(세션)·로그에 싣지 않는다(설계 7.2)
    return _render(request, board, issued=sorted(issued, key=lambda x: x[0].name))


def _shifts(request, board):
    # 그 근무표 밖의 근무 정의 id·부서 칸을 섞어 보내면 404(설계 6.2 범위 검사. 폼도 그 근무표 것만 만든다)
    ids = {str(pk) for pk in board.shifts.values_list("pk", flat=True)}
    codes = set(board.departments.values_list("code", flat=True))
    for k, v in request.POST.items():
        other_shift = re.fullmatch(r"shifts-\d+-id", k) and v and v not in ids
        other_dept = k.startswith("d-") and k[2:].rsplit("-", 1)[0] not in codes
        if other_shift or other_dept:
            raise Http404
    formset, dept_forms = shift_forms(board, request.POST)
    try:
        warnings = board_settings.save_shifts(request.user, board, formset, dept_forms,
                                              int_param(request.POST.get("confirm")))
    except board_settings.Stale as e:  # 보낸 값은 낡았다: 다시 그리면 [저장]이 같은 낡은 값으로 맴도니 새로 읽은 화면으로
        messages.error(request, str(e), extra_tags="shifts")
        return redirect(f"{_here(board)}#shifts")
    except board_settings.NeedsConfirm as e:  # 저장하지 않았다: 보낸 값 그대로 다시 그리고 [그래도 저장]
        messages.warning(request, str(e), extra_tags="shifts")
        return _render(request, board, shifts=(formset, dept_forms), ask=e.rows)
    except DutyError as e:  # 칸 오류: 보낸 값 그대로 다시 그린다(다른 칸의 입력은 건드리지 않는다)
        messages.error(request, str(e), extra_tags="shifts")
        return _render(request, board, shifts=(formset, dept_forms))
    done = "근무 정의와 부서를 저장했습니다."
    if _unassigned(board):  # 경고 상자는 카드 아래에 있어 안 보일 수 있으니 결과 글에도(설계 7.2 두 번 저장)
        done += " 아래 부서에서 새 근무조를 체크하고 [부서 저장]을 한 번 더 누르세요."
    messages.success(request, done, extra_tags="shifts")
    for w in warnings:
        messages.warning(request, w, extra_tags="shifts")
    return redirect(f"{_here(board)}#shifts")


def _steps(request, board):
    form = StepsForm(request.POST, instance=Board.objects.get(pk=board.pk))  # 오류로 다시 그릴 때 화면의 board 가 바뀌지 않게 새로 읽는다
    try:
        warning = board_settings.save_steps(request.user, board, form)
    except DutyError as e:
        messages.error(request, str(e), extra_tags="steps")
        return _render(request, board, steps=form)
    if warning:  # 끈 단계에 회차가 남았다: 성공 대신 안내
        messages.warning(request, warning, extra_tags="steps")
    else:
        messages.success(request, "회차 단계를 저장했습니다.", extra_tags="steps")
    return redirect(f"{_here(board)}#steps")


def _memo_notice(request, board):
    on = bool(request.POST.get("on"))
    board_settings.set_memo_notice(request.user, board, on)
    return "메모 알림을 " + ("켰습니다. 메모를 새로 달거나 고치면 이 근무표 사람 모두에게 갑니다." if on else "껐습니다.")


ACTIONS = {  # POST do → (칸 id, 처리). 처리는 결과 글(성공 메시지)이나 응답(다시 그리기·다른 곳으로)을 돌려준다
    "add_person": ("people", _add_person), "set_person": ("people", _set_person),
    "leave": ("people", _leave), "rejoin": ("people", _rejoin), "issue": ("people", _issue),
    "add_admin": ("admins", _add_admin), "remove_admin": ("admins", _remove_admin),
    "add_assignee": ("assignees", _add_assignee), "remove_assignee": ("assignees", _remove_assignee),
    "shifts": ("shifts", _shifts), "steps": ("steps", _steps), "memo_notice": ("notices", _memo_notice),
}


def _state(u) -> str:
    """계정 열(설계 7.2): 쓸 수 있는 비밀번호가 없으면 발급 전, 첫 로그인 비밀번호 변경 전이면 첫 로그인 대기
    (유효 기간이 지났으면 임시 비밀번호 만료: [비밀번호 초기화]로 다시 발급)."""
    if not u.has_usable_password():
        return "발급 전"
    if accounts.temp_password_expired(u):
        return "임시 비밀번호 만료"
    return "첫 로그인 대기" if u.must_change_password else "사용 중"


def _people(board, edit=None, leave=None) -> list[dict]:
    """사람 칸 줄: 그 근무표 부서 사람(퇴사자 포함), 부서 순 → 이름 순. locked = 사람 함수의 대상이 아닌 계정
    (관리자 계정·슈퍼유저, board_settings.locked_ids): 체크박스·[고치기]·동작 없이 안내 글만.
    edit = 고치기 오류로 다시 그릴 때 그 줄의 보낸 값과 오류, leave = 퇴사 확인으로 다시 그릴 때 그 줄의 남은 근무."""
    locked = board_settings.locked_ids()
    rows = []
    for u in (User.objects.filter(department__board=board).select_related("department")
              .order_by("department__order", "department__code", "name")):
        e = edit if edit and edit["pk"] == u.pk else {}
        lv = leave if leave and leave["pk"] == u.pk else None
        rows.append({"u": u, "locked": u.pk in locked, "state": _state(u), "name": e.get("name", u.name),
                     "type": e.get("type", u.type), "error": e.get("error"), "leave": lv, "open": bool(e or lv)})
    return rows


def _unassigned(board) -> list[str]:
    """켜진 근무조 가운데 어느 부서에도 없는 것(새로 더한 근무조): 부서에서 체크해야 입력 표에 칸이 생긴다(설계 7.2)."""
    assigned = {k for d in board.departments.all() for k in d.shift_keys()}
    return [x.name for x in shift_defs(boards.active_defs(board)) if x.key not in assigned]


def _buttons(board, has_slots) -> list[str]:
    """미리보기: 켠 단계에서 회차 화면에 나오는 버튼 글자(설계 5.4, 회차 화면과 같은 step_buttons), 진행 순서대로."""
    b = board.step_buttons(has_slots)
    return ([b["open"]] * board.use_draft + [b["close"]] * board.use_close + [b["generate"]]
            + [x for x in (b["undo"], b["regenerate"]) if x] + ["배포…"])


def _render(request, board, shifts=None, steps=None, ask=None, add=None, edit=None, leave=None, issued=None):
    me = request.user
    admins = sorted(board.admin_group.user_set.select_related("department"), key=lambda u: u.name)
    active_n = sum(u.is_active for u in admins)
    # 빼기: 나 자신(재직 관리자가 나 말고도 있을 때)과 퇴사한 관리자만. 다른 재직 관리자는 슈퍼유저(설계 7.2)
    admin_rows = [(u, "remove" if not u.is_active or (u.pk == me.pk and active_n > 1)
                   else "last" if u.pk == me.pk else "superuser") for u in admins]
    depts = [{"dept": d, "members": sorted(d.input_group.user_set.select_related("department"), key=lambda u: u.name)
              if d.input_group_id else [], "candidates": board_settings.assignee_candidates(board, d)}
             for d in board.departments.select_related("input_group").order_by("order", "code")]
    formset, dept_forms = shifts or shift_forms(board)
    active = boards.active_defs(board)
    steps = steps or StepsForm(instance=board)
    on = board.steps()
    rows = _people(board, edit, leave)
    return render(request, "duty/board_settings.html", {
        "board": board, "boards": _mine(request), "here": _here(board),
        "people": [r for r in rows if r["u"].is_active], "departed": [r for r in rows if not r["u"].is_active],
        "can_issue": any(r["u"].is_active and not r["locked"] and r["state"] == "발급 전" for r in rows),
        "has_types": prefs.has_types(active), "types": [STAFF, DEVELOPER],
        "people_depts": list(board.departments.order_by("order", "code")),
        "add": add or {"username": board_settings.next_username(board)}, "issued": issued,
        "admin_rows": admin_rows, "admin_candidates": board_settings.admin_candidates(board), "depts": depts,
        "formset": formset, "dept_forms": dept_forms, "ask": ask,
        "unassigned": _unassigned(board),
        "steps_form": steps, "step_rows": [(steps[f"step_{s}"], s not in on) for s in Period.Status.values],
        "step_line": " → ".join(board.step_name(s) for s in on), "buttons": _buttons(board, bool(slot_defs(active))),
        "open_steps": steps.is_bound or any(m.extra_tags == "steps" for m in messages.get_messages(request)),
    })


@admin_required
def index(request):
    board = _board(request)
    if request.method == "POST":
        if request.POST.get("do") not in ACTIONS:
            raise Http404
        section, act = ACTIONS[request.POST["do"]]
        try:
            out = act(request, board)
        except PermissionDenied:  # 그 근무표 밖의 부서·사람, 대상이 아닌 사람: 없는 것처럼
            raise Http404 from None
        except DutyError as e:
            messages.error(request, str(e), extra_tags=section)
        else:
            if not isinstance(out, str):
                return out
            messages.success(request, out, extra_tags=section)
        return redirect(f"{_here(board)}#{section}")
    return _render(request, board)
