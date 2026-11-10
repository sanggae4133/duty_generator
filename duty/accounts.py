import secrets

from django.contrib.auth.models import User
from django.db import transaction

from .models import Member


@transaction.atomic
def issue_account(member: Member) -> str:
    """로그인 계정을 만들거나 비밀번호를 초기화하고 임시 비밀번호를 돌려준다(한 번만 표시)."""
    password = secrets.token_urlsafe(9)
    if member.user is None:
        member.user = User.objects.create_user(username=member.code, password=password)
    else:
        member.user.set_password(password)
        member.user.save()
    member.must_change_password = True
    member.save()
    return password
