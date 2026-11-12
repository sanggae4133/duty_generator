import secrets

from axes.utils import reset
from django.db import transaction

from .models import User
from .services import alarms


def password_changed(user: User) -> None:
    """본인이 비밀번호를 바꿨다: 첫 로그인 강제 변경 표시를 끈다."""
    if user.must_change_password:
        user.must_change_password = False
        user.save(update_fields=["must_change_password"])


def dismiss_help(user: User) -> None:
    """첫 로그인 사용법 팝업을 다시 띄우지 않는다(도움말 메뉴에서는 계속 볼 수 있다)."""
    User.objects.filter(pk=user.pk).update(help_dismissed=True)


def on_login(sender, request, user, **kwargs) -> None:
    """로그인할 때마다: 다시 보지 않기를 안 눌렀으면 이번 로그인의 첫 화면에 사용법 팝업."""
    if not user.help_dismissed:
        request.session["show_help"] = True


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
