"""[근무표 설정](근무표 통합 설계 6.2): 근무표 관리자가 그 근무표의 관리자·입력 담당자·근무 정의와 부서·회차 단계를 고친다.
모든 함수는 그 근무표 관리자만 부르고(첫 줄 _require_admin), 받은 부서·사람이 그 근무표 것인지 다시 본다(아니면 PermissionDenied,
뷰는 404). 쓰기마다 로그 한 줄과 Django LogEntry 한 줄을 남긴다(아이디·부서 코드·근무표 code 만, 실명·비밀번호 없음)."""
import logging

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q

from .. import perms
from ..errors import DutyError
from ..models import Department, User
from . import boards

log = logging.getLogger(__name__)

NO_ADMIN_LEFT = "재직 중인 관리자가 아무도 남지 않습니다. 회차·배포·설정을 할 사람이 없으니 다른 사람을 먼저 넣으세요."


def _require_admin(by, board) -> None:
    if not perms.is_board_admin(by, board):
        raise PermissionDenied("이 근무표 관리자가 아닙니다.")


def _audit(by, board, obj, target: str, action: str) -> None:
    """로그 한 줄 + LogEntry 한 줄(관리 화면에서 그 사람·부서·근무표 편집 페이지의 [기록]에 보인다).
    Django 의 log_actions 는 object_repr 에 str(obj)(= 사람 실명)를 넣으므로 쓰지 않고 아이디·코드를 직접 넣는다."""
    log.info("board %s: %s %s by %s", board.code, action, target, by.username)
    LogEntry.objects.create(user=by, content_type=ContentType.objects.get_for_model(obj), object_id=str(obj.pk),
                            object_repr=target, action_flag=CHANGE, change_message=f"근무표 {board.code}: {action}")


def admin_candidates(board):
    """관리자 넣기 후보: 재직 중이고 그 근무표 부서 사람이거나 부서 없는 계정, 이미 관리자인 사람은 빼고, 이름 순.
    다른 근무표 사람은 넣지 않는다(필요하면 슈퍼유저가 관리 화면에서)."""
    return (User.objects.filter(is_active=True).filter(Q(department__board=board) | Q(department__isnull=True))
            .exclude(groups=board.admin_group_id).select_related("department").order_by("name"))


def assignee_candidates(board, dept):
    """입력 담당자 넣기 후보: 그 근무표 부서의 재직자, 이미 담당자인 사람은 빼고, 이름 순."""
    qs = User.objects.roster().filter(department__board=board).select_related("department")
    if dept.input_group_id:
        qs = qs.exclude(groups=dept.input_group_id)
    return qs.order_by("name")


def _dept(board, dept) -> Department:
    """트랜잭션 안에서 부서를 다시 읽고 그 근무표 부서인지 본다(IDOR)."""
    dept = Department.objects.select_related("input_group").get(pk=dept.pk)
    if dept.board_id != board.pk:
        raise PermissionDenied("이 근무표의 부서가 아닙니다.")
    return dept


@transaction.atomic
def add_admin(by, board, user) -> None:
    _require_admin(by, board)
    if not admin_candidates(board).filter(pk=user.pk).exists():
        raise PermissionDenied("관리자로 넣을 수 없는 사람입니다.")
    board.admin_group.user_set.add(user)
    _audit(by, board, user, user.username, "관리자 넣기")


@transaction.atomic
def remove_admin(by, board, user) -> None:
    """나 자신이나 퇴사한 관리자만 뺀다. 재직 중인 다른 관리자 빼기는 슈퍼유저(관리 화면): 빼고 나서 그 계정을 다루는 우회를 막는다."""
    _require_admin(by, board)
    user = User.objects.get(pk=user.pk)  # 재직 여부는 DB 에서
    if not board.admin_group.user_set.filter(pk=user.pk).exists():
        raise PermissionDenied("이 근무표 관리자가 아닙니다.")
    if user.pk != by.pk and user.is_active:
        raise PermissionDenied("재직 중인 다른 관리자는 슈퍼유저가 관리 화면에서 뺍니다.")
    if board in boards.left_without_admin([user]):
        raise DutyError(NO_ADMIN_LEFT)
    board.admin_group.user_set.remove(user)
    _audit(by, board, user, user.username, "관리자 빼기")


@transaction.atomic
def add_assignee(by, board, dept, user) -> None:
    """부서 입력 그룹에 넣는다. 첫 담당자면 그룹을 만든다(이름이 겹치면 DutyError)."""
    _require_admin(by, board)
    dept = _dept(board, dept)
    if not assignee_candidates(board, dept).filter(pk=user.pk).exists():
        raise PermissionDenied("입력 담당자로 넣을 수 없는 사람입니다.")
    dept.ensure_input_group().user_set.add(user)
    _audit(by, board, user, user.username, f"{dept.code} 입력 담당자 넣기")


@transaction.atomic
def remove_assignee(by, board, dept, user) -> None:
    """부서 입력 그룹에서 뺀다(퇴사자도). 담당자가 하나도 없으면 그 부서는 근무표 관리자만 입력한다."""
    _require_admin(by, board)
    dept = _dept(board, dept)
    if not (dept.input_group_id and dept.input_group.user_set.filter(pk=user.pk).exists()):
        raise PermissionDenied("이 부서의 입력 담당자가 아닙니다.")
    dept.input_group.user_set.remove(user)
    _audit(by, board, user, user.username, f"{dept.code} 입력 담당자 빼기")
