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
    assert "지금 비밀번호와 다른 비밀번호" in r.content.decode()
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
@pytest.mark.parametrize("active", [True, False])
def test_inactive_user_cannot_login(client, make_member, staff, active):
    m = make_member("가", user=True, active=active)
    m.is_staff = staff
    m.save()
    client.post(reverse("login"), {"username": m.username, "password": "unused-Pw-123"})
    assert ("_auth_user_id" in client.session) == active  # 같은 비밀번호: 재직이면 로그인, 퇴사면 거부


def test_issue_account_lifts_lockout_by_linked_username(make_member):
    from unittest import mock

    m = make_member("가", user=True)
    m.username = "custom"
    m.save()
    with mock.patch("duty.accounts.reset") as r:
        issue_account(m)
    r.assert_called_once_with(username="custom")


def test_user_can_change_own_password_anytime(client, make_member):
    m = make_member("가", user=True)
    client.force_login(m)
    assert 'href="/password/"' in client.get("/me/").content.decode()  # 메뉴에서 언제든
    r = client.post(reverse("password_change"), {
        "old_password": "unused-Pw-123", "new_password1": "unused-Pw-123", "new_password2": "unused-Pw-123"}, follow=True)
    assert "지금 비밀번호와 다른" in r.content.decode()
    r = client.post(reverse("password_change"), {
        "old_password": "unused-Pw-123", "new_password1": "Tr0ub4dor&3-xyz", "new_password2": "Tr0ub4dor&3-xyz"}, follow=True)
    m.refresh_from_db()
    assert m.check_password("Tr0ub4dor&3-xyz") and "비밀번호를 바꿨습니다" in r.content.decode()
    assert client.get("/me/").status_code == 200  # 바꾼 뒤에도 로그인 유지


def test_issue_accounts_lists_one_person_per_line(su_client, make_member):
    a, b = make_member("가"), make_member("나")
    body = su_client.post(reverse("admin:duty_user_changelist"),
                          {"action": "issue_accounts", "_selected_action": [a.pk, b.pk]}, follow=True).content.decode()
    assert f"<br>가({a.username}): " in body and f"<br>나({b.username}): " in body


def test_issue_accounts_escapes_names(su_client, make_member):
    a = make_member("가<b>&</b>")  # 이름 검사는 폼에서만: DB 에 들어온 특수문자도 결과 글에서 글자 그대로
    body = su_client.post(reverse("admin:duty_user_changelist"),
                          {"action": "issue_accounts", "_selected_action": [a.pk]}, follow=True).content.decode()
    assert f"<br>가&lt;b&gt;&amp;&lt;/b&gt;({a.username}): " in body and "<b>&</b>" not in body


# ── 근무표 통합 4단계: 임시 비밀번호·초기화의 연결·첫 발급·퇴사(설계 5.7) ──

def _links(u):
    """캘린더 구독·텔레그램·푸시 연결 하나씩(가짜 값)."""
    from django.utils import timezone

    from duty.models import CalendarFeed, PushAlarmSubscription, TelegramAlarmProfile
    CalendarFeed.objects.create(user=u, token_hash="h" * 64, issued_at=timezone.now())
    TelegramAlarmProfile.objects.create(user=u, chat_id="9", verified_at=timezone.now())
    PushAlarmSubscription.objects.create(user=u, endpoint="https://push.example/1", p256dh="p", auth="a")


def _has_links(u) -> tuple[bool, bool, bool]:
    from duty.models import CalendarFeed, PushAlarmSubscription, TelegramAlarmProfile
    return (CalendarFeed.objects.filter(user=u).exists(), TelegramAlarmProfile.objects.get(user=u).chat_id != "",
            PushAlarmSubscription.objects.filter(user=u).exists())


def test_temp_password_shape():
    from duty.accounts import ALPHABET, temp_password
    assert len(ALPHABET) == len(set(ALPHABET)) == 31 and set(ALPHABET).isdisjoint("0o1li")
    got = {temp_password() for _ in range(50)}
    assert len(got) == 50 and all(len(p) == 10 and set(p) <= set(ALPHABET) for p in got)  # 띄어쓰기도 없다


def test_issue_account_uses_temp_password(make_member):
    from duty.accounts import ALPHABET
    pw = issue_account(make_member("가"))
    assert len(pw) == 10 and set(pw) <= set(ALPHABET)


def test_issue_accounts_action_uses_new_password_shape(su_client, make_member):
    """관리 화면 액션도 같은 함수라 모양이 같이 바뀐다."""
    import re

    from duty.accounts import ALPHABET
    a = make_member("가")
    body = su_client.post(reverse("admin:duty_user_changelist"),
                          {"action": "issue_accounts", "_selected_action": [a.pk]}, follow=True).content.decode()
    pw = re.search(rf"<br>가\({a.username}\): ([^<\s]+)", body)[1]
    a.refresh_from_db()
    assert len(pw) == 10 and set(pw) <= set(ALPHABET) and a.check_password(pw)


def test_reset_can_keep_links_but_still_logs_out(client, make_member):
    m = make_member("가")
    issue_account(m)
    _links(m)
    client.force_login(m)
    issue_account(m, revoke_links=False)  # [근무표 설정]의 초기화('비밀번호를 잊었어요')
    assert _has_links(m) == (True, True, True)
    assert client.get("/me/")["Location"].startswith("/login/")  # 비밀번호가 바뀌어 로그인은 끊긴다
    issue_account(m)  # 관리 화면 액션(기본): 지금처럼 끊는다
    assert _has_links(m) == (False, False, False)


def test_first_issue_needs_no_last_login(make_member):
    """퇴사 뒤 다시 재직한 사람(쓸 수 있는 비밀번호 없음 + 로그인한 적 있음)은 첫 발급이 아니다: 지운 기본 규칙이 되살아나지 않는다."""
    from django.utils import timezone
    m = make_member("가")
    issue_account(m)
    AlarmRule.objects.filter(user=m).delete()  # 본인이 지운 기본 규칙
    m.last_login = timezone.now()
    m.set_unusable_password()  # 퇴사(deactivate)가 만드는 상태
    m.save()
    issue_account(m, revoke_links=False)
    assert not AlarmRule.objects.filter(user=m).exists()


def test_deactivate_cuts_login_and_links(client, make_member):
    from duty.accounts import deactivate
    m = make_member("가", user=True)
    _links(m)
    client.force_login(m)
    deactivate(m)
    m.refresh_from_db()
    assert not m.is_active and not m.has_usable_password()
    assert _has_links(m) == (False, False, False)
    assert client.get("/me/")["Location"].startswith("/login/")


# ---- 3단계: Funnel·nginx 가 넘겨 주는 실제 접속 IP 로 잠금(아이디 + IP) ----
# tailscaled 는 X-Forwarded-For 를 실제 IP 하나로 덮어쓰고, nginx 는 그 값을 하나로 넘긴다(127.0.0.1 에서 온 요청만 믿는다)

def _fail(client, ip, n=5):
    for _ in range(n):
        client.post(reverse("login"), {"username": "u1", "password": "wrong"}, REMOTE_ADDR="127.0.0.1",
                    HTTP_X_FORWARDED_FOR=ip)


def test_lockout_is_per_ip_so_others_cannot_lock_my_account(client, db):
    User.objects.create_user("u1", password="Correct-Horse-9", name="유1")
    _fail(client, "203.0.113.7")  # 문서용 IP(실제 주소 아님)
    r = client.post(reverse("login"), {"username": "u1", "password": "Correct-Horse-9"}, REMOTE_ADDR="127.0.0.1",
                    HTTP_X_FORWARDED_FOR="198.51.100.9")
    assert r.status_code == 302  # 다른 곳에서는 그대로 로그인된다
    r = client.post(reverse("login"), {"username": "u1", "password": "Correct-Horse-9"}, REMOTE_ADDR="127.0.0.1",
                    HTTP_X_FORWARDED_FOR="203.0.113.7")
    assert r.status_code == 429  # 틀린 곳은 잠긴다


def test_client_ip_trusts_forwarded_only_from_local_proxy(rf):
    from duty.client_ip import client_ip
    assert client_ip(rf.get("/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="203.0.113.7")) == "203.0.113.7"
    assert client_ip(rf.get("/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.7")) == "203.0.113.7"
    assert client_ip(rf.get("/", REMOTE_ADDR="198.51.100.9", HTTP_X_FORWARDED_FOR="203.0.113.7")) == "198.51.100.9"
    assert client_ip(rf.get("/", REMOTE_ADDR="127.0.0.1")) == "127.0.0.1"
