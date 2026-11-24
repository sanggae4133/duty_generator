"""권한 규칙. 다른 모듈은 `from . import perms` 후 `perms.today()` 형태로 호출한다(테스트 monkeypatch 용).

관리자 판정은 그룹으로 한다(근무표 관리 그룹 = Board.admin_group, 부서 입력 그룹 = Department.input_group).
스태프·슈퍼유저 표시는 쓰지 않는다(슈퍼유저도 그룹에 들어가야 근무표를 다룬다).
"""

from datetime import date

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils import timezone

from .models import Board, Department


def today() -> date:
    return timezone.localdate()


def admin_boards(user):
    """내가 관리 그룹 멤버인 근무표들."""
    if not user.is_authenticated:
        return Board.objects.none()
    return Board.objects.filter(admin_group__user=user)


def is_board_admin(user, board) -> bool:
    return admin_boards(user).filter(pk=board.pk).exists()


def is_admin(user) -> bool:
    """어느 근무표든 관리자(메뉴·영상용)."""
    return admin_boards(user).exists()


def stats_boards(user):
    """통계를 볼 수 있는 근무표: 내가 관리하고 장중관제(slot*) 정의가 있는 근무표(설계 7절)."""
    return admin_boards(user).filter(shifts__key__startswith="slot").distinct()


def managed_departments(user):
    """출근표를 입력할 수 있는 부서: 입력 그룹 멤버인 부서 ∪ 내가 관리하는 근무표의 모든 부서."""
    if not user.is_authenticated:
        return Department.objects.none()
    return Department.objects.filter(Q(input_group__user=user) | Q(board__admin_group__user=user)).distinct()


def can_input_department(user, dept: Department) -> bool:
    return managed_departments(user).filter(pk=dept.pk).exists()


def assert_can_edit(user, board, d: date) -> None:
    """근무표 board 의 날짜 d 를 바꿀 수 있는가: 그 근무표 관리 그룹, 또는 그 근무표 부서 사람(오늘 이후만)."""
    if is_board_admin(user, board):
        return
    if not (user.is_authenticated and user.department_id and user.department.board_id == board.pk):
        raise PermissionDenied("이 근무표를 바꿀 권한이 없습니다.")
    if d < today():
        raise PermissionDenied("지난 날짜는 관리자만 수정할 수 있습니다.")


def can_edit(user, board, d: date) -> bool:
    try:
        assert_can_edit(user, board, d)
    except PermissionDenied:
        return False
    return True
