import hashlib
import re

import pytest
from django.contrib.auth.models import User
from django.test import Client

from duty.models import CalendarFeed
from duty.services import calendar

SITE = "https://duty.example"
TOKEN = re.compile(r"/calendar/([A-Za-z0-9_-]{43})\.ics")
REISSUE = "기존 구독은 더 이상 갱신되지 않습니다. 캘린더 앱에서 기존 구독을 지우고 새 주소를 등록하세요."


@pytest.fixture
def me(settings, make_member, client, fixed_today):
    from datetime import date
    fixed_today(date(2026, 11, 11))
    settings.SITE_URL = SITE
    m = make_member("가상일", user=True)
    client.force_login(m.user)
    return m


def issue(client):
    r = client.post("/alarms/calendar/issue/")
    assert r.status_code == 200
    body = r.content.decode()
    tokens = TOKEN.findall(body)
    assert len(tokens) == 1, tokens
    return r, body, tokens[0]


def test_issue_shows_url_once(client, me):
    r, body, token = issue(client)
    assert r["Cache-Control"] == "private, no-store" and r["Referrer-Policy"] == "no-referrer"
    assert f'value="{SITE}/calendar/{token}.ics"' in body and "readonly" in body and "복사" in body
    assert not re.search(r'<a [^>]*href="[^"]*' + re.escape(token), body)
    row = CalendarFeed.objects.get(user=me.user)
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(dict(client.session))
    assert not list(r.context["messages"])
    # 이후 GET: 토큰 없이 발급일만
    later = client.get("/alarms/").content.decode()
    assert token not in later and "발급일" in later and REISSUE in later
    assert "구독 끄기" in later and "구독 주소 만들기" not in later


def test_unissued_shows_issue_button(client, me):
    body = client.get("/alarms/").content.decode()
    assert "구독 주소 만들기" in body and "구독 끄기" not in body and 'href="/help/calendar/"' in body


def test_no_site_url(client, me, settings):
    settings.SITE_URL = ""
    r = client.post("/alarms/calendar/issue/")
    assert r.status_code == 200 and calendar.NO_SITE_URL in r.content.decode()
    assert not CalendarFeed.objects.exists()


def test_reissue_invalidates_old(client, me):
    _, _, old = issue(client)
    _, _, new = issue(client)
    assert old != new
    assert client.get(f"/calendar/{old}.ics").status_code == 404
    assert client.get(f"/calendar/{new}.ics").status_code == 200


def test_revoke(client, me):
    _, _, token = issue(client)
    r = client.post("/alarms/calendar/revoke/")
    assert r.status_code == 302 and r.url == "/alarms/"
    assert not CalendarFeed.objects.exists()
    assert client.get(f"/calendar/{token}.ics").status_code == 404


def test_unlinked_member(client, me):
    issue(client)
    me.user = None
    me.save()
    body = client.get("/alarms/").content.decode()
    assert calendar.NO_MEMBER in body and "구독 주소 만들기" not in body and "구독 끄기" in body
    r = client.post("/alarms/calendar/issue/")
    assert calendar.NO_MEMBER in r.content.decode() and not TOKEN.search(r.content.decode())
    client.post("/alarms/calendar/revoke/")
    assert not CalendarFeed.objects.exists()


def test_never_linked_user_rejected(client, db, settings):
    settings.SITE_URL = SITE
    u = User.objects.create_user("x1", password="unused-Pw-123")
    client.force_login(u)
    body = client.get("/alarms/").content.decode()
    assert calendar.NO_MEMBER in body and "구독 끄기" not in body
    client.post("/alarms/calendar/issue/")
    assert not CalendarFeed.objects.exists()


def test_auth_method_csrf(client, me):
    assert client.get("/alarms/calendar/issue/").status_code == 405
    assert client.get("/alarms/calendar/revoke/").status_code == 405
    c = Client(enforce_csrf_checks=True)
    c.force_login(me.user)
    assert c.post("/alarms/calendar/issue/").status_code == 403
    assert c.post("/alarms/calendar/revoke/").status_code == 403
    anon = Client()
    for url in ["/alarms/calendar/issue/", "/alarms/calendar/revoke/", "/help/calendar/"]:
        r = anon.post(url) if "help" not in url else anon.get(url)
        assert r.status_code == 302 and r.url.startswith("/login/")
    assert not CalendarFeed.objects.exists()


def test_help_and_menu(client, me):
    body = client.get("/help/calendar/").content.decode()
    for s in ["즉시 반영되지 않을 수", "비밀번호", "URL로 추가", "새 구독을 추가할 수 없습니다", "구독 캘린더 추가",
              "웹에서 구독", "지난 90일", "주소 재발급", 'href="/help/telegram/"', 'href="/help/push/"',
              "구독 주소 만들기", "복사"]:
        assert s in body, s
    assert "알림·캘린더" in client.get("/").content.decode()
