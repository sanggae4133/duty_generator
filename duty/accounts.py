import secrets

from axes.utils import reset
from django.db import transaction

from .models import User
from .services import alarms


@transaction.atomic
def issue_account(user: User) -> str:
    """임시 비밀번호를 정하고 돌려준다(한 번만 표시). 최초 발급일 때만 기본 알림 규칙을 만든다."""
    first = not user.has_usable_password()
    password = secrets.token_urlsafe(9)
    user.set_password(password)
    user.must_change_password = True
    user.save()
    reset(username=user.username)
    if first:
        alarms.create_defaults(user)
    return password
