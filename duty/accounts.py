import secrets

from axes.utils import reset
from django.db import transaction

from . import perms
from .models import AlarmDelivery, Department, User
from .services import alarms, calendar


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
    else:  # 초기화(탈취 의심 포함): 세션과 무관한 연결도 끊는다. 본인이 다시 연결하면 된다
        calendar.revoke(user)
        alarms.clear_telegram(user)
        alarms.delete_all_subscriptions(user)
    return password


def on_department_change(user: User, old_department_id) -> None:
    """부서를 바꿔 근무표가 달라졌으면 개인 규칙의 오늘 이후 발송 기록을 지운다(옛 근무표의 기록이 남으면
    새 근무표에서 그 칸을 못 찾아 취소 알림이 나간다). 보고서 규칙은 근무표가 정해져 있어 그대로 둔다."""
    old = Department.objects.filter(pk=old_department_id).values_list("board_id", flat=True).first()
    new = user.department.board_id if user.department_id else None
    if old != new:
        AlarmDelivery.objects.filter(rule__user=user, rule__kind="personal", date__gte=perms.today()).delete()
