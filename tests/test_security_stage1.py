"""보안 점검 1단계(설정·짧은 코드). 번호는 점검 보고서의 항목 번호."""
import json
import os
import subprocess
import sys
from datetime import date

import pytest
from django.urls import reverse

from duty.errors import DutyError
from duty.models import AlarmRule, User
from duty.services import alarms


def _prod_settings(tmp_path) -> dict:
    """운영과 같은 DEBUG=0 으로 설정을 읽어 본다(테스트 설정은 DEBUG=1)."""
    code = ("import json, config.settings as s; print(json.dumps({'hsts': s.SECURE_HSTS_SECONDS, "
            "'script': s.FORCE_SCRIPT_NAME, 'axes': s.AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT, "
            "'disallowed': s.LOGGING['loggers'].get('django.security.DisallowedHost')}))")
    env = {**os.environ, "DUTY_ENV_FILE": "", "DUTY_DEBUG": "0", "DUTY_SECRET_KEY": "x" * 50,
           "DUTY_DATA_DIR": str(tmp_path)}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True,
                         cwd=os.path.dirname(os.path.dirname(__file__)))
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_prod_settings(tmp_path):
    s = _prod_settings(tmp_path)
    assert s["hsts"] >= 86400                       # #14 HSTS
    assert s["script"] == ""                        # #21 클라이언트 SCRIPT_NAME 무시
    assert s["axes"] is False                       # #3·#7 잠긴 동안의 시도로 잠금 연장·기록 누적 안 함
    assert s["disallowed"]["handlers"] == ["null"]  # #4 잘못된 Host 로그 증폭 끔


def test_disallowed_host_not_logged(client, db):
    """#4: 잘못된 Host 는 400 이고 루트(로그 파일)로 올라가지 않는다(pytest 는 자기 수집 핸들러를 직접 붙이므로 propagate 로 확인)."""
    import logging
    r = client.get("/login/", HTTP_HOST="x" * 300)
    assert r.status_code == 400
    assert logging.getLogger("django.security.DisallowedHost").propagate is False


def test_client_script_name_ignored(client, make_member):
    """#21: SCRIPT_NAME: /calendar 로 경로 앞부분을 바꿔 강제 비밀번호 변경을 건너뛰지 못한다."""
    from duty.accounts import issue_account
    u = make_member("가")
    issue_account(u)  # must_change_password
    client.force_login(u)
    r = client.get("/me/", SCRIPT_NAME="/calendar")
    assert r.status_code == 302 and reverse("password_change") in r.url


def test_alarm_rule_cap(make_member):
    """#5: 사람당 알림 규칙 수 상한."""
    u = make_member("가", user=True)
    AlarmRule.objects.filter(user=u).delete()
    base = dict(enabled=True, kind="personal", timing="days", offset=1, telegram=True, push=False,
                shifts=[], depts=[], types=[])
    for i in range(alarms.MAX_RULES):
        alarms.save_rule(u, {**base, "at_minute": i})
    with pytest.raises(DutyError, match=str(alarms.MAX_RULES)):
        alarms.save_rule(u, {**base, "at_minute": 999})
    r = AlarmRule.objects.filter(user=u).first()
    alarms.save_rule(u, {**base, "at_minute": 1000}, r)  # 기존 규칙 수정은 된다


def test_admin_site_superuser_only(client, admin_user):
    """#8: 관리 화면은 슈퍼유저만(스태프에게 모델 권한을 줘도)."""
    from django.contrib.auth.models import Permission
    admin_user.user_permissions.add(Permission.objects.get(codename="view_user"))
    client.force_login(admin_user)  # 스태프, 슈퍼유저 아님
    r = client.get(reverse("admin:duty_user_changelist"))
    assert r.status_code == 302 and "login" in r.url


def test_issue_action_skips_self(client, make_member):
    """#20: 일괄 발급에 자기 계정이 섞여도 자기 비밀번호는 바꾸지 않는다."""
    su = User.objects.create_superuser("root", password="Root-pw-12345", name="최고")
    m = make_member("가")
    client.force_login(su)
    r = client.post(reverse("admin:duty_user_changelist"),
                    {"action": "issue_accounts", "_selected_action": [su.pk, m.pk]}, follow=True)
    su.refresh_from_db()
    assert su.check_password("Root-pw-12345")
    assert "자기 계정" in r.content.decode()
    m.refresh_from_db()
    assert m.has_usable_password()


def test_safe_next_rejects_http_on_https(client, make_member):
    """#22: https 로 들어온 요청의 next 는 http:// 같은 호스트도 거절."""
    from django.test import RequestFactory
    from duty.views.common import safe_next
    req = RequestFactory().get("/", {"next": "http://testserver/x"}, secure=True)
    assert safe_next(req, "/fallback/") == "/fallback/"
    assert safe_next(RequestFactory().get("/", {"next": "/me/"}, secure=True), "/f/") == "/me/"


def test_push_test_cooldown(client, make_member, monkeypatch):
    """#27: 테스트 푸시는 30초에 한 번."""
    calls = []
    monkeypatch.setattr(alarms, "test_push", lambda u: calls.append(u) or (0, 0))
    u = make_member("가", user=True)
    client.force_login(u)
    client.post("/alarms/push/test/")
    r = client.post("/alarms/push/test/", follow=True)
    assert len(calls) == 1 and "잠시 후" in r.content.decode()


@pytest.mark.parametrize("d", ["0001-01-01", "9999-12-31", "1999-12-31", "2100-01-01"])
def test_extreme_day_is_404(client, make_member, d):
    """#28: 범위 밖 날짜는 500 대신 404."""
    client.force_login(make_member("가", user=True))
    assert client.get(f"/day/{d}/").status_code == 404


@pytest.mark.parametrize("name", ["=HYPERLINK(1)", "-가", "@가", "\t가", "+가"])
def test_member_name_rejects_formula_start(name):
    """#25: 엑셀 수식으로 해석되는 첫 글자 금지."""
    from django.core.exceptions import ValidationError
    from duty.models import validate_member_name
    with pytest.raises(ValidationError):
        validate_member_name(name)


def test_admin_site_needs_staff_too(client, db):
    """슈퍼유저라도 스태프 권한을 끄면 관리 화면에 못 들어온다(Django 기본 의미 유지)."""
    su = User.objects.create_superuser("root", password="Root-pw-12345", name="최고")
    su.is_staff = False
    su.save()
    client.force_login(su)
    r = client.get(reverse("admin:duty_user_changelist"))
    assert r.status_code == 302 and "login" in r.url
