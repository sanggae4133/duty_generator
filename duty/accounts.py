import secrets
from datetime import timedelta

from axes.utils import reset
from django.db import transaction
from django.utils import timezone

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


SUPERUSER_SESSION_AGE = 12 * 3600  # 관리 화면(비밀번호 초기화·봇 토큰·그룹 권한)이 열리는 세션은 90일이 아니라 12시간
TEMP_PASSWORD_DAYS = 7  # 임시 비밀번호는 발급 뒤 7일 안에 첫 로그인해야 쓸 수 있다(지나면 다시 발급)


def on_login(sender, request, user, **kwargs) -> None:
    """로그인할 때마다: 다시 보지 않기를 안 눌렀으면 이번 로그인의 첫 화면에 사용법 팝업. 슈퍼유저는 세션을 짧게."""
    if not user.help_dismissed:
        request.session["show_help"] = True
    if user.is_superuser:
        request.session.set_expiry(SUPERUSER_SESSION_AGE)


def temp_password_expired(user: User) -> bool:
    """첫 로그인 대기인데 임시 비밀번호를 발급한 지 TEMP_PASSWORD_DAYS 가 지났다. 발급 시각이 없으면(관리 화면에서 칸만 켠 경우) 만료로 보지 않는다."""
    issued = user.temp_password_issued_at
    return user.must_change_password and issued is not None and timezone.now() - issued > timedelta(days=TEMP_PASSWORD_DAYS)


ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"  # 헷갈리는 0·o·1·l·i 를 뺐다(근무표 통합 설계 5.7)


def temp_password() -> str:
    """임시 비밀번호 10자(띄어쓰기 없음). 관리 화면 액션과 [근무표 설정]이 함께 쓴다."""
    return "".join(secrets.choice(ALPHABET) for _ in range(10))


def _revoke_links(user: User) -> None:
    """세션과 무관한 연결(캘린더 구독·텔레그램·푸시)을 끊는다. 본인이 다시 연결하면 된다."""
    calendar.revoke(user)
    alarms.clear_telegram(user)
    alarms.delete_all_subscriptions(user)


@transaction.atomic
def issue_account(user: User, revoke_links: bool = True) -> str:
    """임시 비밀번호를 정하고 돌려준다(한 번만 표시). 비밀번호가 바뀌어 모든 기기의 로그인이 끊기고 로그인 잠금이 풀린다.
    첫 발급(쓸 수 있는 비밀번호가 없고 로그인한 적도 없음)이면 기본 알림 규칙을 만든다. 퇴사 뒤 다시 재직한 사람은 첫 발급이 아니다.
    초기화는 revoke_links 일 때 연결도 끊는다: 관리 화면 액션(탈취 의심)은 끊고, [근무표 설정]의 초기화(비밀번호 분실)는 남긴다."""
    first = not user.has_usable_password() and user.last_login is None
    password = temp_password()
    user.set_password(password)
    user.must_change_password = True
    user.temp_password_issued_at = timezone.now()
    user.save()
    reset(username=user.username)
    if first:
        alarms.create_defaults(user)
    elif revoke_links:
        _revoke_links(user)
    return password


@transaction.atomic
def deactivate(user: User) -> None:
    """퇴사: 재직 끄기 + 쓸 수 없는 비밀번호(모든 기기 로그인이 끊긴다) + 연결 끊기."""
    user.is_active = False
    user.set_unusable_password()
    user.save(update_fields=["is_active", "password"])
    _revoke_links(user)


@transaction.atomic
def reactivate(user: User) -> None:
    """다시 재직: 퇴사와 같은 정리(관리 화면에서 재직만 끈 사람의 옛 비밀번호·연결도 끊는다) 뒤 재직만 켠다.
    로그인하려면 [계정 발급]을 다시 한다(계정 열이 '발급 전'으로 보인다)."""
    deactivate(user)
    User.objects.filter(pk=user.pk).update(is_active=True)
    user.is_active = True


def on_department_change(user: User, old_department_id) -> None:
    """부서를 바꿔 근무표가 달라졌으면 개인 규칙의 오늘 이후 발송 기록을 지운다(옛 근무표의 기록이 남으면
    새 근무표에서 그 칸을 못 찾아 취소 알림이 나간다). 보고서 규칙은 근무표가 정해져 있어 그대로 둔다."""
    old = Department.objects.filter(pk=old_department_id).values_list("board_id", flat=True).first()
    new = user.department.board_id if user.department_id else None
    if old != new:
        AlarmDelivery.objects.filter(rule__user=user, rule__kind="personal", date__gte=perms.today()).delete()
