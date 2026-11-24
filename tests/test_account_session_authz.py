"""검토 4번: 계정·세션·서비스 권한(임시 비밀번호 보관·유효 기간, 슈퍼유저 세션, 관리 화면 비밀번호 칸, 회차 서비스 권한, 로그인 잠금 IP)."""
from datetime import date, timedelta

import pytest
from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from duty.accounts import TEMP_PASSWORD_DAYS, issue_account
from duty.client_ip import client_ip
from duty.models import Period, User
from duty.services import generate, periods, publish


@pytest.fixture
def su_client(client, admin_user):
    admin_user.is_superuser = True
    admin_user.save()
    client.force_login(admin_user)
    return client


# ── 관리 화면 액션의 임시 비밀번호는 응답 본문에만(세션 DB 에 남기지 않는다) ──

def test_issue_action_keeps_password_out_of_session(su_client, make_member):
    a = make_member("가")
    r = su_client.post(reverse("admin:duty_user_changelist"), {"action": "issue_accounts", "_selected_action": [a.pk]})
    assert r.status_code == 200 and "임시 비밀번호" in r.content.decode()
    a.refresh_from_db()
    pw = r.content.decode().split(f"가({a.username}): ")[1][:10]
    assert a.check_password(pw)
    assert not any(pw in str(s.get_decoded()) for s in Session.objects.all())


# ── 임시 비밀번호 유효 기간 ──

def _login(client, u, pw):
    return client.post(reverse("login"), {"username": u.username, "password": pw})


def test_temp_password_works_within_days(client, make_member):
    m = make_member("가")
    pw = issue_account(m)
    _login(client, m, pw)
    assert "_auth_user_id" in client.session


def test_expired_temp_password_is_refused(client, make_member):
    m = make_member("가")
    pw = issue_account(m)
    User.objects.filter(pk=m.pk).update(
        temp_password_issued_at=timezone.now() - timedelta(days=TEMP_PASSWORD_DAYS, minutes=1))
    r = _login(client, m, pw)
    assert "_auth_user_id" not in client.session
    assert "다시 발급" in r.content.decode()


def test_expiry_does_not_apply_after_change(client, make_member):
    """비밀번호를 바꾼 사람(must_change_password 꺼짐)은 발급 시각과 무관하다."""
    m = make_member("가", user=True)
    User.objects.filter(pk=m.pk).update(temp_password_issued_at=timezone.now() - timedelta(days=365))
    _login(client, m, "unused-Pw-123")
    assert "_auth_user_id" in client.session


# ── 슈퍼유저 세션은 짧게 ──

def test_superuser_session_is_short(client, admin_user):
    admin_user.is_superuser = True
    admin_user.save()
    _login(client, admin_user, "unused-Pw-123")
    assert client.session.get_expiry_age() == 12 * 3600


def test_normal_session_keeps_90_days(client, make_member):
    m = make_member("가", user=True)
    _login(client, m, "unused-Pw-123")
    assert client.session.get_expiry_age() == settings.SESSION_COOKIE_AGE


# ── 관리 화면 사용자 편집에 Django 비밀번호 칸(초기화 버튼)이 없다 ──

def test_admin_user_change_has_no_password_field(su_client, make_member):
    m = make_member("가", user=True)
    body = su_client.get(reverse("admin:duty_user_change", args=[m.pk])).content.decode()
    assert "../password/" not in body and 'name="must_change_password"' in body


# ── 회차·생성·배포 서비스도 근무표 관리자인지 본다 ──

@pytest.fixture
def other_admin(ops_board):
    u = User.objects.create_user("opsadmin", password="unused-Pw-123", name="다른관리자")
    u.groups.add(ops_board.admin_group)
    return u


@pytest.fixture
def it_period(it_board):
    return Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13),
                                 status=Period.Status.COLLECTING)


@pytest.mark.parametrize("call", [
    lambda p, by: periods.save_draft(p, by=by),
    lambda p, by: periods.move(p, Period.Status.CLOSED, by=by),
    lambda p, by: periods.delete(p, by=by),
    lambda p, by: generate.run_generation(p, by=by),
    lambda p, by: publish.publish(p, p.start_date, by=by),
    lambda p, by: publish.unpublish(p, by=by),
])
def test_period_services_refuse_other_board_admin(it_period, other_admin, call):
    with pytest.raises(PermissionDenied):
        call(it_period, other_admin)
    assert Period.objects.filter(pk=it_period.pk, status=Period.Status.COLLECTING).exists()


def test_period_service_allows_board_admin(it_period, admin_user):
    periods.move(it_period, Period.Status.CLOSED, by=admin_user)
    assert Period.objects.get(pk=it_period.pk).status == Period.Status.CLOSED


# ── 로그인 잠금 IP: IPv6 는 /64 로 묶는다 ──

def _ip(remote, xff=""):
    return client_ip(RequestFactory().get("/", REMOTE_ADDR=remote, HTTP_X_FORWARDED_FOR=xff))


def test_client_ip_groups_ipv6_by_64():
    assert _ip("127.0.0.1", "2001:db8:1:2:aaaa::1") == _ip("127.0.0.1", "2001:db8:1:2:bbbb::9") == "2001:db8:1:2::"
    assert _ip("127.0.0.1", "2001:db8:1:3::1") == "2001:db8:1:3::"
    assert _ip("127.0.0.1", "203.0.113.7") == "203.0.113.7"
    assert _ip("203.0.113.8", "198.51.100.1") == "203.0.113.8"  # 127.0.0.1 이 아니면 헤더를 믿지 않는다


def test_axes_access_log_off():
    assert settings.AXES_DISABLE_ACCESS_LOG is True
