import pytest
from django.urls import reverse

from duty.accounts import issue_account
from duty.models import AlarmRule, User


def test_issue_account_sets_password(make_member):
    m = make_member("가")
    assert not m.has_usable_password()  # 발급 전에는 로그인 불가
    pw = issue_account(m)
    m.refresh_from_db()
    assert m.check_password(pw) and m.must_change_password
    pw2 = issue_account(m)
    m.refresh_from_db()
    assert pw2 != pw and m.check_password(pw2)


def test_default_rules_only_on_first_issue(make_member):
    m = make_member("가")
    issue_account(m)
    assert AlarmRule.objects.filter(user=m).count() == 2
    AlarmRule.objects.filter(user=m).delete()
    issue_account(m)  # 비밀번호 초기화는 규칙을 건드리지 않는다
    assert not AlarmRule.objects.filter(user=m).exists()


def test_reset_of_already_usable_account_makes_no_rules(make_member):
    m = make_member("가", user=True)
    issue_account(m)
    assert not AlarmRule.objects.exists()


def test_force_password_change(client, make_member):
    m = make_member("가")
    issue_account(m)
    client.force_login(m)
    r = client.get("/me/")
    assert r.status_code == 302 and r.url == reverse("password_change")
    assert client.get(reverse("password_change")).status_code == 200


def test_password_change_clears_flag(client, make_member):
    m = make_member("가")
    pw = issue_account(m)
    client.force_login(m)
    r = client.post(reverse("password_change"), {
        "old_password": pw, "new_password1": "Tr0ub4dor&3-xyz", "new_password2": "Tr0ub4dor&3-xyz",
    })
    assert r.status_code == 302
    m.refresh_from_db()
    assert not m.must_change_password


def test_login_lockout_after_five_failures(client, db):
    User.objects.create_user("u1", password="Correct-Horse-9", name="유1")
    for _ in range(5):
        client.post(reverse("login"), {"username": "u1", "password": "wrong"})
    r = client.post(reverse("login"), {"username": "u1", "password": "Correct-Horse-9"})
    assert r.status_code == 429
    assert "15분간 잠겼습니다" in r.content.decode()
    assert "_auth_user_id" not in client.session


def test_login_success_redirects_home(client, db):
    User.objects.create_user("u2", password="Correct-Horse-9", name="유2")
    r = client.post(reverse("login"), {"username": "u2", "password": "Correct-Horse-9"})
    assert r.status_code == 302 and r.url == "/"


def test_api_removed(client, db):
    assert client.get("/api/assignments").status_code == 404


def test_password_change_rejects_same_password(client, make_member):
    m = make_member("가")
    pw = issue_account(m)
    client.force_login(m)
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
    r.assert_called_once_with(username=m.username)


@pytest.fixture
def su_client(client, admin_user):
    admin_user.is_superuser = True
    admin_user.save()
    client.force_login(admin_user)
    return client


def test_issue_accounts_action(su_client, make_member):
    a, b = make_member("가"), make_member("나")
    r = su_client.post(reverse("admin:duty_user_changelist"),
                       {"action": "issue_accounts", "_selected_action": [a.pk, b.pk]}, follow=True)
    assert "임시 비밀번호" in r.content.decode()
    for u in (a, b):
        u.refresh_from_db()
        assert u.has_usable_password() and u.must_change_password
        assert AlarmRule.objects.filter(user=u).count() == 2


def test_issue_accounts_action_rolls_back_on_error(su_client, make_member, monkeypatch):
    a, b = make_member("가"), make_member("나")
    import duty.admin
    real = duty.admin.issue_account

    def flaky(u):
        if u.pk == b.pk:
            raise RuntimeError("boom")
        return real(u)

    monkeypatch.setattr(duty.admin, "issue_account", flaky)
    su_client.raise_request_exception = False
    r = su_client.post(reverse("admin:duty_user_changelist"),
                       {"action": "issue_accounts", "_selected_action": [a.pk, b.pk]})
    assert r.status_code == 500
    a.refresh_from_db()
    assert not a.has_usable_password() and not a.must_change_password
    assert not AlarmRule.objects.exists()


def test_inactive_user_session_becomes_anonymous(client, make_member):
    m = make_member("가", user=True)
    client.force_login(m)
    assert client.get("/me/").status_code == 200
    m.is_active = False
    m.save()
    r = client.get("/me/")
    assert r.status_code == 302 and r["Location"].startswith("/login/")


@pytest.mark.parametrize("staff", [False, True])
def test_inactive_user_cannot_login(client, make_member, staff):
    m = make_member("가", user=True, active=False)
    m.is_staff = staff
    m.save()
    client.post(reverse("login"), {"username": m.username, "password": "unused-Pw-123"})
    assert "_auth_user_id" not in client.session


def test_issue_account_lifts_lockout_by_linked_username(make_member):
    from unittest import mock

    m = make_member("가", user=True)
    m.username = "custom"
    m.save()
    with mock.patch("duty.accounts.reset") as r:
        issue_account(m)
    r.assert_called_once_with(username="custom")
