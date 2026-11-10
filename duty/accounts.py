import secrets

from axes.utils import reset
from django.contrib.auth.models import User
from django.db import transaction

from .errors import DutyError
from .models import Member


@transaction.atomic
def issue_account(member: Member) -> str:
    """로그인 계정을 만들거나 비밀번호를 초기화하고 임시 비밀번호를 돌려준다(한 번만 표시)."""
    password = secrets.token_urlsafe(9)
    if member.user is None:
        if User.objects.filter(username=member.code).exists():
            raise DutyError(f"{member.code} 아이디의 계정이 이미 있으며 이 멤버와 연결되어 있지 않습니다.")
        member.user = User.objects.create_user(username=member.code, password=password)
    else:
        member.user.set_password(password)
        member.user.save()
    reset(username=member.user.username)
    member.must_change_password = True
    member.save()
    return password
