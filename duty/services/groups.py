"""그룹 화면(설계 7절): 그룹 관리자(GroupKeeper)가 맡은 그룹의 멤버를 넣고 뺀다. 넣고 빼면 그 권한이 바로 바뀐다."""
import logging

from django.core.exceptions import PermissionDenied
from django.db import transaction

from .. import perms
from ..errors import DutyError
from ..models import Board

log = logging.getLogger(__name__)


def _require_keeper(by, group) -> None:
    if not perms.kept_groups(by).filter(pk=group.pk).exists():
        raise PermissionDenied("이 그룹을 맡고 있지 않습니다.")


@transaction.atomic
def add_member(by, group, member) -> None:
    _require_keeper(by, group)
    if not member.is_active:
        raise DutyError(f"퇴사한 사람은 넣을 수 없습니다: {member.name}")
    if group.user_set.filter(pk=member.pk).exists():
        raise DutyError(f"이미 이 그룹에 있습니다: {member.name}")
    group.user_set.add(member)
    log.info("group %s: %s added by %s", group.pk, member.username, by.username)  # 실명 대신 아이디(멤버 코드)


@transaction.atomic
def remove_member(by, group, member) -> str:
    """빼고, 근무표 관리 그룹이 비게 되면 경고 문구를 돌려준다(막지는 않는다, 설계 7절). 아니면 빈 글자."""
    _require_keeper(by, group)
    if not group.user_set.filter(pk=member.pk).exists():
        raise DutyError(f"이 그룹에 없는 사람입니다: {member.name}")
    group.user_set.remove(member)
    log.info("group %s: %s removed by %s", group.pk, member.username, by.username)
    board = Board.objects.filter(admin_group=group).first()
    if board and not group.user_set.exists():
        return f"{board.name} 근무표 관리자가 아무도 없습니다. 회차·배포를 할 사람이 없으니 다른 사람을 넣으세요."
    return ""
