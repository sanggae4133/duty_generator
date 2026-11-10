from datetime import date

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from duty.errors import DutyError
from duty.accounts import issue_account
from duty.models import Commute, Period

D = date(2026, 11, 10)


def test_issue_account_creates_user(make_member):
    m = make_member("가")
    pw = issue_account(m)
    m.refresh_from_db()
    assert m.user.username == m.code and m.user.check_password(pw) and m.must_change_password
    pw2 = issue_account(m)
    m.user.refresh_from_db()
    assert pw2 != pw and m.user.check_password(pw2)


def test_force_password_change(client, make_member):
    m = make_member("가")
    issue_account(m)
    client.force_login(m.user)
    r = client.get("/me/")
    assert r.status_code == 302 and r.url == reverse("password_change")
    assert client.get(reverse("password_change")).status_code == 200


def test_password_change_clears_flag(client, make_member):
    m = make_member("가")
    pw = issue_account(m)
    client.force_login(m.user)
    r = client.post(reverse("password_change"), {
        "old_password": pw, "new_password1": "Tr0ub4dor&3-xyz", "new_password2": "Tr0ub4dor&3-xyz",
    })
    assert r.status_code == 302
    m.refresh_from_db()
    assert not m.must_change_password


def test_login_lockout_after_five_failures(client, db):
    User.objects.create_user("u1", password="Correct-Horse-9")
    for _ in range(5):
        client.post(reverse("login"), {"username": "u1", "password": "wrong"})
    r = client.post(reverse("login"), {"username": "u1", "password": "Correct-Horse-9"})
    assert r.status_code == 429
    assert "15분간 잠겼습니다" in r.content.decode()
    assert "_auth_user_id" not in client.session


def test_login_success_redirects_home(client, db):
    User.objects.create_user("u2", password="Correct-Horse-9")
    r = client.post(reverse("login"), {"username": "u2", "password": "Correct-Horse-9"})
    assert r.status_code == 302 and r.url == "/"


@pytest.fixture
def published(make_member):
    p = Period.objects.create(name="p", start_date=D, end_date=D, status=Period.Status.PUBLISHED)
    Commute.objects.create(period=p, date=D, member=make_member("가"), shift="dawn")
    return p


def test_api_requires_token(client, published):
    assert client.get("/api/assignments").status_code == 401
    assert client.get("/api/assignments", HTTP_AUTHORIZATION="Bearer nope").status_code == 401


def test_api_returns_assignments(client, published):
    r = client.get("/api/assignments?from=2026-11-10&to=2026-11-10", HTTP_AUTHORIZATION="Bearer test-token")
    assert r.status_code == 200
    assert r.json() == [{"date": "2026-11-10", "shift": "새벽", "name": "가", "replaced": None}]


def test_api_bad_date(client, published):
    r = client.get("/api/assignments?from=nope", HTTP_AUTHORIZATION="Bearer test-token")
    assert r.status_code == 400


def test_password_change_rejects_same_password(client, make_member):
    m = make_member("가")
    pw = issue_account(m)
    client.force_login(m.user)
    r = client.post(reverse("password_change"), {"old_password": pw, "new_password1": pw, "new_password2": pw})
    assert r.status_code == 200
    assert "임시 비밀번호와 다른 비밀번호" in r.content.decode()
    m.refresh_from_db()
    assert m.must_change_password


def test_issue_account_lifts_lockout(make_member):
    from unittest import mock

    m = make_member("가")
    with mock.patch("duty.accounts.reset") as r:
        issue_account(m)
    r.assert_called_once_with(username=m.code)


def test_issue_account_username_conflict(make_member):
    m = make_member("가")
    User.objects.create_user(m.code, password="x")
    with pytest.raises(DutyError, match="이미"):
        issue_account(m)
