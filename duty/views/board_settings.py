"""[근무표 설정](근무표 통합 설계 7절): 근무표 관리자가 그 근무표의 관리자·입력 담당자·근무 정의와 부서·회차 단계를 고치는
한 화면(/settings/?board=<code>). 칸마다 따로 저장하고 저장 뒤 그 칸(#앵커)으로 돌아온다. 결과 메시지는 extra_tags 에 칸 id 를
넣어 그 칸 제목 바로 아래에 그린다(base.html 맨 위에는 칸 태그가 없는 메시지만). DB 쓰기는 services/board_settings.py."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from .. import perms
from ..errors import DutyError
from ..models import Department, User
from ..services import board_settings, boards
from ..shifts import josa
from .common import admin_required


def _board(request):
    """?board=<code> 의 근무표: 내가 관리하는 근무표만(아니면 404, 회차 화면과 같은 방식). 없으면 내 근무표(관리할 때) → 관리하는 첫 근무표."""
    mine = list(perms.admin_boards(request.user).order_by("id"))  # admin_required 를 지났으니 비어 있지 않다
    code = request.GET.get("board")
    if code:
        board = next((b for b in mine if b.code == code), None)
        if board is None:
            raise Http404
    else:
        home = boards.home(request.user)
        board = next((b for b in mine if b.pk == getattr(home, "pk", None)), mine[0])
    return board, mine


def _here(board) -> str:
    return f"{reverse('board_settings')}?board={board.code}"


def _user(request) -> User:
    pid = request.POST.get("user", "")
    user = User.objects.filter(pk=pid).first() if pid.isdigit() else None
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


ACTIONS = {  # POST do → (칸 id, 처리). 처리는 결과 글(성공 메시지)이나 응답(다시 그리기·다른 곳으로)을 돌려준다
    "add_admin": ("admins", _add_admin), "remove_admin": ("admins", _remove_admin),
    "add_assignee": ("assignees", _add_assignee), "remove_assignee": ("assignees", _remove_assignee),
}


def _render(request, board, mine):
    me = request.user
    admins = sorted(board.admin_group.user_set.select_related("department"), key=lambda u: u.name)
    active_n = sum(u.is_active for u in admins)
    # 빼기: 나 자신(재직 관리자가 나 말고도 있을 때)과 퇴사한 관리자만. 다른 재직 관리자는 슈퍼유저(설계 7.2)
    admin_rows = [(u, "remove" if not u.is_active or (u.pk == me.pk and active_n > 1)
                   else "last" if u.pk == me.pk else "superuser") for u in admins]
    depts = [{"dept": d, "members": sorted(d.input_group.user_set.select_related("department"), key=lambda u: u.name)
              if d.input_group_id else [], "candidates": board_settings.assignee_candidates(board, d)}
             for d in board.departments.select_related("input_group").order_by("order", "code")]
    return render(request, "duty/board_settings.html", {
        "board": board, "boards": mine, "here": _here(board),
        "admin_rows": admin_rows, "admin_candidates": board_settings.admin_candidates(board), "depts": depts,
    })


@admin_required
def index(request):
    board, mine = _board(request)
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
    return _render(request, board, mine)
