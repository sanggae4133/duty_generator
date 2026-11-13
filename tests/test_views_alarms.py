from datetime import date, timedelta

import pytest
from django.utils import timezone

from duty.alarms import senders
from duty.models import AlarmDelivery, AlarmRule, AlarmSettings, TelegramAlarmProfile, User
from duty.services import alarm_settings

D = date(2026, 11, 10)


def set_alarm_settings(**kw):
    AlarmSettings.objects.update_or_create(pk=1, defaults=kw)


@pytest.fixture
def me(db, depts, client, fixed_today):
    fixed_today(D)
    u = User.objects.create_user("u1", password="unused-Pw-123", name="유1")
    client.force_login(u)
    return u


@pytest.fixture
def other(db):
    return User.objects.create_user("u2", password="unused-Pw-123", name="유2")


@pytest.fixture
def bot(settings, tmp_path, db):
    set_alarm_settings(telegram_bot_token="TOK", telegram_bot_username="duty_test_bot")
    settings.TELEGRAM_UPDATES_LOCK_PATH = str(tmp_path / "tg.lock")
    return settings


def msgs(r):
    return [str(m) for m in r.context["messages"]] if r.context else []


def post(client, url, data=None):
    return client.post(url, data or {}, follow=True)


def rule(user, **kw):
    base = dict(kind="personal", timing="days", offset=1, at_minute=18 * 60, telegram=True, push=False, shifts=[])
    return AlarmRule.objects.create(user=user, **{**base, **kw})


RULE_FORM = dict(enabled="on", kind="personal", timing="before_start", hours="2", minutes="30", telegram="on")


# ---- 기본 ----

def test_login_required(client, db):
    for url in ["/alarms/", "/help/telegram/", "/alarms/rules/new/"]:
        r = client.get(url)
        assert r.status_code == 302 and r.url.startswith("/login/")


def test_menu_link(client, me):
    assert 'href="/alarms/"' in client.get("/").content.decode()


def test_index_shows_rules_and_help_link(client, me, bot):
    rule(me, timing="before_start", offset=150, at_minute=0)
    rule(me, timing="before_start", offset=120, at_minute=0, shifts=["dawn"])
    rule(me, timing="before_start", offset=45, at_minute=0)
    rule(me, timing="days", offset=1, at_minute=18 * 60)
    rule(me, timing="days", offset=0, at_minute=5 * 60 + 15)
    rule(me, kind="report", timing="bizdays", offset=1, at_minute=17 * 60, depts=["MEMS"], types=["개발자"])
    body = client.get("/alarms/").content.decode()
    for s in ["시작 2시간 30분 전", "시작 2시간 전", "시작 45분 전", "1일 전 18:00", "당일 05:15", "1영업일 전 17:00",
              "매칭엔진실", "개발자", "전부", "새벽", 'href="/help/telegram/"', 'id="push"']:
        assert s in body, s


def test_others_rule_404(client, me, other):
    r = rule(other)
    assert client.get(f"/alarms/rules/{r.pk}/").status_code == 404
    assert client.post(f"/alarms/rules/{r.pk}/", RULE_FORM).status_code == 404
    assert client.post(f"/alarms/rules/{r.pk}/delete/").status_code == 404
    assert client.post(f"/alarms/rules/{r.pk}/toggle/").status_code == 404
    r.refresh_from_db()
    assert r.enabled and r.timing == "days"


# ---- 텔레그램 연결 해제 ----

def test_empty_clears_regardless_of_cooldown(client, me, bot):
    TelegramAlarmProfile.objects.create(user=me, chat_id="9", verified_at=timezone.now(), last_test_at=timezone.now())
    post(client, "/alarms/telegram/", {"chat_id": ""})
    p = TelegramAlarmProfile.objects.get(user=me)
    assert p.chat_id == "" and p.verified_at is None


# ---- 텔레그램 자동 연결 ----

def test_link_redirect(client, me, bot):
    r = client.post("/alarms/telegram/link/")
    p = TelegramAlarmProfile.objects.get(user=me)
    assert r.status_code == 302 and r.url == f"https://t.me/duty_test_bot?start={p.link_code}"
    assert timedelta(minutes=9) < p.link_expires_at - timezone.now() <= timedelta(minutes=10)
    old = p.link_code
    client.post("/alarms/telegram/link/")
    p.refresh_from_db()
    assert p.link_code != old  # 새 코드가 이전 코드를 무효화


def test_link_without_bot(client, me):
    set_alarm_settings(telegram_bot_token="TOK", telegram_bot_username="")
    r = post(client, "/alarms/telegram/link/")
    assert "텔레그램 봇이 설정되지 않았습니다." in msgs(r)


def upd(uid, text, chat_id, chat_type="private"):
    return {"update_id": uid, "message": {"text": text, "chat": {"id": chat_id, "type": chat_type}}}


@pytest.fixture
def tgapi(monkeypatch):
    """getUpdates 가짜: offset 이전 것은 확인 처리된 것으로 본다."""
    st = {"updates": [], "calls": [], "sent": [], "raise": None, "send_raise": None}

    def get_updates(cfg, offset=None, limit=100):
        assert cfg.telegram_token == "TOK"
        st["calls"].append(offset)
        if st["raise"]:
            raise st["raise"]
        got = [u for u in st["updates"] if offset is None or u["update_id"] >= offset]
        return got[:2]  # 한 묶음 2개로 잘라 여러 묶음 처리 확인

    def send(cfg, chat_id, text):
        st["sent"].append((chat_id, text))
        if st["send_raise"]:
            raise st["send_raise"]
        return {}

    monkeypatch.setattr(senders, "telegram_get_updates", get_updates)
    monkeypatch.setattr(senders, "telegram_send", send)
    return st


def code_of(user, client):
    client.post("/alarms/telegram/link/")
    return TelegramAlarmProfile.objects.get(user=user).link_code


def test_link_check_success_and_others(client, me, other, bot, tgapi):
    mine = code_of(me, client)
    from django.test import Client
    c2 = Client()
    c2.force_login(other)
    theirs = code_of(other, c2)
    tgapi["updates"] = [upd(10, "hello", 1), upd(11, f"/start {theirs}", 222),
                        upd(12, f"/start {mine}", 333, "group"), upd(13, f"/start {mine}", 111)]
    r = post(client, "/alarms/telegram/link/check/")
    p, q = TelegramAlarmProfile.objects.get(user=me), TelegramAlarmProfile.objects.get(user=other)
    assert (p.chat_id, p.link_code, p.link_expires_at) == ("111", None, None) and p.verified_at
    assert (q.chat_id, q.link_code) == ("222", None) and q.verified_at  # 남의 코드는 그 소유자에게
    assert tgapi["calls"] == [None, 12, 14]  # offset 전진, 빈 묶음까지
    assert {c for c, _ in tgapi["sent"]} == {"111", "222"}
    assert "[연결 완료] 당번 알림이 이 채팅으로 옵니다." in tgapi["sent"][0][1]
    assert any("연결되었습니다" in m for m in msgs(r))


def test_link_check_pending(client, me, bot, tgapi):
    code_of(me, client)
    tgapi["updates"] = [upd(1, "/start other", 5)]
    r = post(client, "/alarms/telegram/link/check/")
    assert "아직 확인되지 않았습니다. 텔레그램에서 [시작]을 눌렀는지 확인하고 다시 눌러 주세요." in msgs(r)
    assert TelegramAlarmProfile.objects.get(user=me).verified_at is None


def test_link_check_expired(client, me, bot, tgapi):
    code = code_of(me, client)
    TelegramAlarmProfile.objects.filter(user=me).update(link_expires_at=timezone.now() - timedelta(seconds=1))
    tgapi["updates"] = [upd(1, f"/start {code}", 5)]
    r = post(client, "/alarms/telegram/link/check/")
    assert "연결 코드가 만료되었습니다. 다시 [텔레그램 연결]을 눌러 주세요." in msgs(r)
    p = TelegramAlarmProfile.objects.get(user=me)
    assert p.chat_id == "" and p.link_code is None


def test_link_check_cooldown(client, me, bot, tgapi):
    code_of(me, client)
    post(client, "/alarms/telegram/link/check/")
    r = post(client, "/alarms/telegram/link/check/")
    assert "잠시 후 다시 시도하세요." in msgs(r) and len(tgapi["calls"]) == 1


def test_link_check_locked(client, me, bot, tgapi):
    import fcntl
    code_of(me, client)
    with open(bot.TELEGRAM_UPDATES_LOCK_PATH, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        r = post(client, "/alarms/telegram/link/check/")
    assert "다른 연결 확인이 진행 중입니다. 잠시 후 다시 시도하세요." in msgs(r)
    assert tgapi["calls"] == [] and TelegramAlarmProfile.objects.get(user=me).last_test_at is None


def test_link_check_409(client, me, bot, tgapi):
    code_of(me, client)
    tgapi["raise"] = senders.Permanent(409)
    r = post(client, "/alarms/telegram/link/check/")
    assert "텔레그램 봇 설정 오류입니다. 관리자에게 알려 주세요." in msgs(r)


def test_link_survives_send_failure(client, me, bot, tgapi):
    code = code_of(me, client)
    tgapi["updates"] = [upd(1, f"/start {code}", 7)]
    tgapi["send_raise"] = senders.Permanent(403)
    post(client, "/alarms/telegram/link/check/")
    assert TelegramAlarmProfile.objects.get(user=me).chat_id == "7"


# ---- 도움말 ----

def test_help_page(client, me, bot):
    body = client.get("/help/telegram/").content.decode()
    assert "@duty_test_bot" in body and "https://t.me/duty_test_bot" in body
    assert "연결 코드는 10분 동안 유효하고" in body and "chat_id 직접 입력" not in body and "TOK" not in body


# ---- 규칙 ----

def test_create_rule_minutes_and_normalize(client, me):
    post(client, "/alarms/rules/new/", {**RULE_FORM, "shifts": ["night", "dawn"]})
    r = AlarmRule.objects.get(user=me)
    assert (r.timing, r.offset, r.at_minute, r.shifts) == ("before_start", 150, 0, ["dawn", "night"])


def test_create_days_rule(client, me):
    post(client, "/alarms/rules/new/", dict(kind="report", timing="bizdays", days="1", at_time="17:00", push="on",
                                            depts=["MEMS", "UI", "TMCH", "MD"], types=["직원"]))
    r = AlarmRule.objects.get(user=me)
    assert (r.kind, r.offset, r.at_minute, r.depts, r.types, r.push, r.telegram, r.enabled) == \
        ("report", 1, 17 * 60, [], ["직원"], True, False, False)


def test_personal_drops_depts(client, me):
    r = post(client, "/alarms/rules/new/", {**RULE_FORM, "depts": ["MEMS"], "types": ["직원"]})
    assert r.redirect_chain
    x = AlarmRule.objects.get(user=me)
    assert x.depts == [] and x.types == []


def test_duplicate_rule(client, me):
    rule(me, timing="before_start", offset=150, at_minute=0, push=True)
    r = post(client, "/alarms/rules/new/", RULE_FORM)
    assert "같은 규칙이 이미 있습니다." in r.content.decode()
    assert AlarmRule.objects.filter(user=me).count() == 1


def test_no_channel(client, me):
    r = post(client, "/alarms/rules/new/", {k: v for k, v in RULE_FORM.items() if k != "telegram"})
    assert "텔레그램이나 푸시 중 하나 이상 선택하세요." in r.content.decode()
    assert not AlarmRule.objects.filter(user=me).exists()


@pytest.mark.parametrize("h,m", [("0", "0"), ("168", "1")])
def test_before_start_range(client, me, h, m):
    post(client, "/alarms/rules/new/", {**RULE_FORM, "hours": h, "minutes": m})
    assert not AlarmRule.objects.filter(user=me).exists()


def test_edit_initial(client, me):
    r = rule(me, timing="before_start", offset=150, at_minute=0)
    body = client.get(f"/alarms/rules/{r.pk}/").content.decode()
    assert 'name="hours" value="2"' in body and 'name="minutes" value="30"' in body


def delivery(r, d):
    return AlarmDelivery.objects.create(rule=r, date=d, cell="dawn", channel="telegram", destination="1",
                                        status="sent", content_hash="h")


@pytest.mark.parametrize("change,kept", [
    ({"hours": "3", "minutes": "0"}, False),
    ({"kind": "report"}, False),
    ({"enabled": "", "push": "on"}, True),
])
def test_edit_clears_future_deliveries(client, me, change, kept):
    r = rule(me, timing="before_start", offset=150, at_minute=0)
    delivery(r, D - timedelta(days=1)), delivery(r, D), delivery(r, D + timedelta(days=1))
    data = {**RULE_FORM, **change}
    post(client, f"/alarms/rules/{r.pk}/", {k: v for k, v in data.items() if v})
    assert AlarmDelivery.objects.filter(rule=r).count() == (3 if kept else 1)
    r.refresh_from_db()
    if kept:
        assert not r.enabled and r.push


def test_delete_and_toggle(client, me):
    r = rule(me)
    post(client, f"/alarms/rules/{r.pk}/toggle/")
    r.refresh_from_db()
    assert not r.enabled
    post(client, f"/alarms/rules/{r.pk}/delete/")
    assert not AlarmRule.objects.filter(pk=r.pk).exists()


def test_same_day_notice_partial(client, me):
    r = post(client, "/alarms/rules/new/", {**RULE_FORM, "timing": "days", "days": "0", "at_time": "08:30",
                                            "shifts": ["dawn", "normal", "dinner"]})
    assert "새벽·정상은 발송 시각이 근무 시작 이후라 제외됩니다." in msgs(r)


def test_same_day_notice_all(client, me):
    r = post(client, "/alarms/rules/new/", {**RULE_FORM, "timing": "days", "days": "0", "at_time": "23:00"})
    assert "현재 선택으로는 발송되는 근무가 없습니다." in msgs(r)


def test_same_day_notice_report(client, me):
    data = {**RULE_FORM, "kind": "report", "timing": "days", "days": "0", "shifts": ["dawn", "normal"]}
    r = post(client, "/alarms/rules/new/", {**data, "at_time": "07:00"})
    assert not any("발송" in m for m in msgs(r))
    r = post(client, "/alarms/rules/new/", {**data, "at_time": "08:00"})
    assert "현재 선택으로는 보고서가 발송되지 않습니다." in msgs(r)


# ---- Fix round 1 ----

def test_csrf_enforced(me):
    from django.test import Client
    c = Client(enforce_csrf_checks=True)
    c.force_login(me)
    assert c.post("/alarms/telegram/", {"chat_id": ""}).status_code == 403


def _other_client(other):
    from django.test import Client
    c = Client()
    c.force_login(other)
    return c


def test_disconnect_invalidates_pending_code(client, me, other, bot, tgapi):
    code = code_of(me, client)
    TelegramAlarmProfile.objects.filter(user=me).update(chat_id="9", verified_at=timezone.now())
    post(client, "/alarms/telegram/", {"chat_id": ""})
    p = TelegramAlarmProfile.objects.get(user=me)
    assert (p.chat_id, p.verified_at, p.link_code, p.link_expires_at) == ("", None, None, None)
    c2 = _other_client(other)
    code_of(other, c2)
    tgapi["updates"] = [upd(1, f"/start {code}", 555)]
    post(c2, "/alarms/telegram/link/check/")
    assert TelegramAlarmProfile.objects.get(user=me).chat_id == ""


def test_expired_relink_for_connected_user(client, me, bot, tgapi):
    TelegramAlarmProfile.objects.create(user=me, chat_id="9", verified_at=timezone.now() - timedelta(days=3))
    code_of(me, client)
    TelegramAlarmProfile.objects.filter(user=me).update(link_expires_at=timezone.now() - timedelta(seconds=1))
    r = post(client, "/alarms/telegram/link/check/")
    assert "연결 코드가 만료되었습니다. 다시 [텔레그램 연결]을 눌러 주세요." in msgs(r)
    assert tgapi["calls"] == []


def test_connected_without_code(client, me, bot, tgapi):
    TelegramAlarmProfile.objects.create(user=me, chat_id="9", verified_at=timezone.now() - timedelta(days=3))
    r = post(client, "/alarms/telegram/link/check/")
    assert "이미 연결되어 있습니다(기존 연결 유지)." in msgs(r) and tgapi["calls"] == []


def test_many_batches_until_empty(client, me, bot, tgapi):
    code = code_of(me, client)
    tgapi["updates"] = [upd(i, "hi", 1) for i in range(1, 6)] + [upd(6, f"/start {code}", 42)]
    post(client, "/alarms/telegram/link/check/")
    assert tgapi["calls"] == [None, 3, 5, 7]
    assert TelegramAlarmProfile.objects.get(user=me).chat_id == "42"


def test_batch_cap_acks_and_reports(client, me, bot, tgapi, monkeypatch):
    from duty.services import alarms as svc
    monkeypatch.setattr(svc, "MAX_BATCHES", 2)
    code_of(me, client)
    tgapi["updates"] = [upd(i, "hi", 1) for i in range(1, 10)]
    r = post(client, "/alarms/telegram/link/check/")
    assert "처리할 메시지가 남았습니다. 잠시 후 다시 시도하세요." in msgs(r)
    assert tgapi["calls"] == [None, 3, 5]  # 마지막 묶음까지 확인 처리


def test_linked_notified_even_if_later_batch_fails(client, me, bot, tgapi, monkeypatch):
    code = code_of(me, client)
    real = senders.telegram_get_updates

    def flaky(cfg, offset=None, limit=100):
        if offset is not None:
            raise senders.Temporary(502)
        return real(cfg, offset, limit)
    tgapi["updates"] = [upd(1, f"/start {code}", 42)]
    monkeypatch.setattr(senders, "telegram_get_updates", flaky)
    r = post(client, "/alarms/telegram/link/check/")
    assert "텔레그램 서버에 연결하지 못했습니다. 잠시 후 다시 시도하세요." in msgs(r)
    assert TelegramAlarmProfile.objects.get(user=me).chat_id == "42"
    assert [c for c, _ in tgapi["sent"]] == ["42"]


def test_no_username_asks_admin_and_allows_disconnect(client, me):
    set_alarm_settings(telegram_bot_token="TOK", telegram_bot_username="")
    TelegramAlarmProfile.objects.create(user=me, chat_id="9", verified_at=timezone.now())
    body = client.get("/alarms/").content.decode()
    assert "봇 사용자명이 설정되지 않아" in body and "연결 해제" in body and "텔레그램 연결</button>" not in body
    set_alarm_settings(telegram_bot_token="")
    body = client.get("/alarms/").content.decode()
    assert "연결 해제" in body and "저장 및 테스트" not in body
    assert "관리자가 관리 화면 → 알림 설정에서 텔레그램 봇 토큰을 넣으면 [텔레그램 연결] 버튼이 나타납니다." in body


def test_reorder_only_keeps_deliveries(client, me):
    r = rule(me, timing="before_start", offset=150, at_minute=0, shifts=["night", "dawn"])
    delivery(r, D)
    post(client, f"/alarms/rules/{r.pk}/", {**RULE_FORM, "shifts": ["dawn", "night"]})
    assert AlarmDelivery.objects.filter(rule=r).count() == 1


def test_all_selected_stored_keeps_deliveries(client, me):
    r = rule(me, kind="report", timing="before_start", offset=150, at_minute=0,
             shifts=["dawn", "normal", "dinner", "night", "slots"], depts=["MEMS", "TMCH", "MD", "UI"])
    delivery(r, D)
    post(client, f"/alarms/rules/{r.pk}/", {**RULE_FORM, "kind": "report", "push": "on"})
    assert AlarmDelivery.objects.filter(rule=r).count() == 1


def test_integrity_error_other_than_duplicate_reraised(me):
    from django.db import IntegrityError

    from duty.services import alarms as svc
    data = dict(enabled=True, kind="personal", timing="before_start", offset=0, at_minute=0,
                telegram=True, push=False, shifts=[], depts=[], types=[])
    with pytest.raises(IntegrityError):
        svc.save_rule(me, data)


def test_same_day_notice_collapses_slots():
    from duty.alarms.schedule import same_day_notice
    assert same_day_notice("personal", "days", 0, 10 * 60, []) == \
        "새벽·정상·석식교대·장중관제 08:30~10:30은 발송 시각이 근무 시작 이후라 제외됩니다."


def test_batch_cap_exact_drain_is_ok(client, me, bot, tgapi, monkeypatch):
    from duty.services import alarms as svc
    monkeypatch.setattr(svc, "MAX_BATCHES", 2)
    code = code_of(me, client)
    tgapi["updates"] = [upd(1, "hi", 1), upd(2, "hi", 1), upd(3, "hi", 1), upd(4, f"/start {code}", 42)]
    r = post(client, "/alarms/telegram/link/check/")
    assert tgapi["calls"] == [None, 3, 5]
    assert not any("처리할 메시지" in m for m in msgs(r))
    assert any("연결되었습니다" in m for m in msgs(r))


# ---- 웹 푸시 (Task 7) ----

import json  # noqa: E402

from duty.models import PushAlarmSubscription  # noqa: E402
from duty.services import alarms as alarm_svc  # noqa: E402

EP = "https://fcm.googleapis.com/fcm/send/abc123"
P256 = "B" + "a" * 86   # 87자 base64url
AUTH = "c" * 22
UA_ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36"


@pytest.fixture
def vapid(db):
    set_alarm_settings(vapid_public_key="BPub" + "x" * 83, vapid_private_key="priv")
    return alarm_settings.current()


def sub_json(client, endpoint=EP, p256dh=P256, auth=AUTH, ua=UA_ANDROID, **extra):
    body = {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}, **extra}
    return client.post("/alarms/push/subscribe/", json.dumps(body),
                       content_type="application/json", HTTP_USER_AGENT=ua)


def test_sw_js_anonymous(client, db):
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert r["Content-Type"].startswith("application/javascript") and r["Service-Worker-Allowed"] == "/"
    body = r.content.decode()
    for s in ["showNotification", "notificationclick", "openWindow", "navigate", "waitUntil", "notification.close()"]:
        assert s in body, s


def test_manifest_anonymous(client, db):
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200 and r["Content-Type"].startswith("application/manifest+json")
    m = json.loads(r.content)
    assert m["name"] == "NXT 당번표" and m["start_url"] == "/" and m["display"] == "standalone"
    assert {i["sizes"] for i in m["icons"]} == {"192x192", "512x512"}


def test_icons_exist(client, db):
    from django.contrib.staticfiles import finders
    for n in (192, 512):
        path = finders.find(f"duty/icon-{n}.png")
        assert path
        with open(path, "rb") as f:
            assert f.read(8) == b"\x89PNG\r\n\x1a\n"


def test_manifest_link_in_base(client, me):
    assert 'rel="manifest" href="/manifest.webmanifest"' in client.get("/").content.decode()


def test_push_login_required(client, db):
    for url in ["/help/push/"]:
        r = client.get(url)
        assert r.status_code == 302 and r.url.startswith("/login/")
    for url in ["/alarms/push/subscribe/", "/alarms/push/unsubscribe/", "/alarms/push/1/delete/",
                "/alarms/push/delete-all/", "/alarms/push/test/"]:
        r = client.post(url)
        assert r.status_code == 302 and r.url.startswith("/login/"), url


def no_push_keys(monkeypatch):
    def boom():
        raise ValueError("x")
    monkeypatch.setattr(alarm_settings, "_new_push_keys", boom)


def test_push_keys_made_on_first_view(client, me):
    body = client.get("/alarms/").content.decode()
    s = AlarmSettings.objects.get()
    from django.utils.html import escapejs
    assert s.push_on and escapejs(s.vapid_public_key) in body and "이 기기에서 푸시 받기" in body
    assert s.vapid_private_key not in body


def test_push_key_generation_failed(client, me, monkeypatch):
    no_push_keys(monkeypatch)
    body = client.get("/alarms/").content.decode()
    assert "웹 푸시 키를 만들지 못했습니다. 관리자에게 알려 주세요." in body and "이 기기에서 푸시 받기" not in body
    assert 'href="/help/push/"' in body


def test_push_area(client, me, vapid):
    PushAlarmSubscription.objects.create(user=me, endpoint=EP, p256dh=P256, auth=AUTH, label="Chrome / Android")
    body = client.get("/alarms/").content.decode()
    for s in ["이 기기에서 푸시 받기", "이 기기 해제", "테스트 푸시", "모든 기기 해제", "Chrome / Android",
              "로그아웃해도 알림은 계속 오고", "iOS 16.4 이상", "이 브라우저는 푸시를 지원하지 않습니다.",
              vapid.vapid_public_key, 'href="/help/push/"']:
        assert s in body, s
    assert "priv" not in body.replace("private", "")


def test_subscribe_ok_and_label(client, me, vapid):
    r = sub_json(client)
    assert r.status_code == 200
    s = PushAlarmSubscription.objects.get()
    assert (s.user, s.endpoint, s.p256dh, s.auth, s.label) == (me, EP, P256, AUTH, "Chrome / Android")
    # 같은 사용자의 재구독은 키 갱신
    assert sub_json(client, p256dh="B" + "z" * 86).status_code == 200
    assert PushAlarmSubscription.objects.get().p256dh == "B" + "z" * 86


@pytest.mark.parametrize("endpoint", [
    "http://fcm.googleapis.com/fcm/send/x",
    "https://fcm.googleapis.com:443/fcm/send/x",
    "https://u:p@fcm.googleapis.com/fcm/send/x",
    "https://@fcm.googleapis.com/fcm/send/x",
    "https://142.250.1.1/fcm/send/x",
    "https://[::1]/x",
    "https://evilfcm.googleapis.com/x",
    "https://example.com/x",
    "https://wns2-par02p.notify.windows.com/w/?token=x",
    "https://fcm.googleapis.com:99999/x",
    "https://fcm.googleapis.com:abc/x",
    "https://[bad/x",
    "https://fcm.googleapis.com/" + "a" * 500,
    "",
    " " + EP,
    EP + " ",
    "https://fcm.googleapis\n.com/x",
    "https://fcm.googleapis.com/x\ty",
    "https://evil.example\\.fcm.googleapis.com/x",
    "https://evil.example%5c.fcm.googleapis.com/x",
    "https://evil%2eexample.fcm.googleapis.com/x",
    "https://FCM.googleapis.com/fcm/send/y",
    "https://.fcm.googleapis.com/x",
    "https://fcm.googleapis.com./x",
    "https://evil..fcm.googleapis.com/x",
    EP + "#a",
    EP + "#",
])
def test_subscribe_bad_endpoint(client, me, vapid, endpoint):
    r = sub_json(client, endpoint=endpoint)
    assert r.status_code == 400 and r.json()["error"]
    assert not PushAlarmSubscription.objects.exists()


def test_subscribe_host_ok(client, me, vapid):
    for i, ep in enumerate(["https://updates.push.services.mozilla.com/wpush/v2/gAAAAABx-_y",
                            "https://web.push.apple.com/QGx-Ab_9", "https://fcm.googleapis.com/fcm/send/dX:APA91b-y_z"]):
        assert sub_json(client, endpoint=ep).status_code == 200, ep
    assert PushAlarmSubscription.objects.count() == 3


def test_subscribe_unsupported_message(client, me, vapid):
    assert sub_json(client, endpoint="https://example.com/x").json()["error"] == "지원하지 않는 푸시 서비스입니다."


@pytest.mark.parametrize("p256dh,auth", [
    ("B" * 79, AUTH), ("B" * 101, AUTH), ("B" * 86 + "+", AUTH), (P256, "c" * 15), (P256, "c" * 33), (P256, "c" * 21 + "/"),
])
def test_subscribe_bad_keys(client, me, vapid, p256dh, auth):
    assert sub_json(client, p256dh=p256dh, auth=auth).status_code == 400


@pytest.mark.parametrize("raw", ["not json", "[]", '{"endpoint": 1}', '{"endpoint": "%s", "keys": "x"}' % EP, '{"endpoint": "%s"}' % EP])
def test_subscribe_bad_body(client, me, vapid, raw):
    r = client.post("/alarms/push/subscribe/", raw, content_type="application/json")
    assert r.status_code == 400 and r.json()["error"]


def test_subscribe_other_users_endpoint(client, me, other, vapid):
    old = PushAlarmSubscription.objects.create(user=other, endpoint=EP, p256dh=P256, auth=AUTH)
    assert sub_json(client, auth="d" * 22).status_code == 409
    assert PushAlarmSubscription.objects.get().user == other
    assert sub_json(client).status_code == 200  # 키가 같으면 이동
    new = PushAlarmSubscription.objects.get()
    assert new.user == me and new.pk != old.pk  # 새 행(옛 sub:<id> 계획이 새 소유자에게 가지 않게)


def test_unsubscribe_own_only(client, me, other, vapid):
    PushAlarmSubscription.objects.create(user=other, endpoint=EP, p256dh=P256, auth=AUTH)
    r = client.post("/alarms/push/unsubscribe/", json.dumps({"endpoint": EP}), content_type="application/json")
    assert r.status_code == 200 and PushAlarmSubscription.objects.exists()
    PushAlarmSubscription.objects.update(user=me)
    client.post("/alarms/push/unsubscribe/", json.dumps({"endpoint": EP}), content_type="application/json")
    assert not PushAlarmSubscription.objects.exists()


def test_delete_own_only(client, me, other, vapid):
    mine = PushAlarmSubscription.objects.create(user=me, endpoint=EP, p256dh=P256, auth=AUTH)
    theirs = PushAlarmSubscription.objects.create(user=other, endpoint=EP + "2", p256dh=P256, auth=AUTH)
    assert client.post(f"/alarms/push/{theirs.pk}/delete/").status_code == 404
    post(client, f"/alarms/push/{mine.pk}/delete/")
    assert list(PushAlarmSubscription.objects.all()) == [theirs]


def test_delete_all_own_only(client, me, other, vapid):
    for i in range(2):
        PushAlarmSubscription.objects.create(user=me, endpoint=f"{EP}{i}", p256dh=P256, auth=AUTH)
    theirs = PushAlarmSubscription.objects.create(user=other, endpoint=EP + "x", p256dh=P256, auth=AUTH)
    post(client, "/alarms/push/delete-all/")
    assert list(PushAlarmSubscription.objects.all()) == [theirs]


def test_test_push_broken_subject_no_500(client, me, monkeypatch):
    """연락처(subject) 형식이 틀린 채 저장돼 있어도 [테스트 푸시]는 500 이 아니라 실패 건수로 끝난다(실제 서명 단계)."""
    import pywebpush
    monkeypatch.setattr(pywebpush.requests, "post", lambda *a, **k: pytest.fail("네트워크 호출 금지"))
    s = alarm_settings.ensure_push_keys()
    s.vapid_subject = "admin"
    s.save()
    PushAlarmSubscription.objects.create(user=me, endpoint=EP, p256dh=P256, auth=AUTH)
    r = post(client, "/alarms/push/test/")
    assert r.status_code == 200 and "성공 0 / 실패 1" in " ".join(msgs(r))


def test_test_push(client, me, other, vapid, monkeypatch):
    for i in range(3):
        PushAlarmSubscription.objects.create(user=me, endpoint=f"{EP}{i}", p256dh=P256, auth=AUTH)
    PushAlarmSubscription.objects.create(user=other, endpoint=EP + "x", p256dh=P256, auth=AUTH)
    calls = []

    def fake(cfg, sub, title, body, url, ttl):
        assert cfg.vapid_private_key == "priv"  # DB 설정값으로 보낸다
        calls.append(sub.endpoint)
        if sub.endpoint.endswith("1"):
            raise senders.Gone(410)
        if sub.endpoint.endswith("2"):
            raise senders.Temporary(500)
    monkeypatch.setattr(senders, "push_send", fake)
    r = post(client, "/alarms/push/test/")
    assert sorted(calls) == [EP + "0", EP + "1", EP + "2"]
    assert "성공 1 / 실패 2" in " ".join(msgs(r))
    assert not PushAlarmSubscription.objects.filter(endpoint=EP + "1").exists()
    assert PushAlarmSubscription.objects.filter(endpoint=EP + "2").exists()


def test_test_push_not_configured(client, me, monkeypatch):
    no_push_keys(monkeypatch)
    monkeypatch.setattr(senders, "push_send", lambda *a: pytest.fail("no send"))
    assert "웹 푸시 키를 만들지 못했습니다. 관리자에게 알려 주세요." in " ".join(msgs(post(client, "/alarms/push/test/")))


def test_push_csrf(me, vapid):
    from django.test import Client
    c = Client(enforce_csrf_checks=True)
    c.force_login(me)
    sub = PushAlarmSubscription.objects.create(user=me, endpoint=EP, p256dh=P256, auth=AUTH)
    for url in ["/alarms/push/subscribe/", "/alarms/push/unsubscribe/", "/alarms/push/delete-all/", "/alarms/push/test/",
                f"/alarms/push/{sub.pk}/delete/"]:
        assert c.post(url, "{}", content_type="application/json").status_code == 403, url


def test_push_help_page(client, me):
    body = client.get("/help/push/").content.decode()
    for s in ["안드로이드", "Chrome", "Firefox", "홈 화면에 추가", "iOS 16.4", "다시 허용", "테스트 푸시"]:
        assert s in body, s
    assert "Edge" not in body


@pytest.mark.parametrize("ua,label", [
    (UA_ANDROID, "Chrome / Android"),
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1", "Safari / iPhone"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0", "Firefox / Windows"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 Edg/130.0", "Edge / Windows"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Chrome / macOS"),
    ("", "알 수 없는 기기"),
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148", "홈 화면 앱 / iPhone"),
    ("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148", "홈 화면 앱 / iPad"),
])
def test_ua_label(ua, label):
    assert alarm_svc.ua_label(ua) == label


def test_sw_and_manifest_skip_password_change_redirect(client, make_member):
    # 서비스 워커 갱신 요청이 리다이렉트되면 브라우저가 갱신을 실패로 처리한다
    m = make_member("가", user=True)
    m.must_change_password = True
    m.save()
    client.force_login(m)
    assert client.get("/alarms/").status_code == 302
    assert client.get("/sw.js").status_code == 200
    assert client.get("/manifest.webmanifest").status_code == 200


def test_sw_and_manifest_skip_inactive_member_redirect(client, make_member):
    m = make_member("가", user=True, active=False)
    client.force_login(m)
    for url in ["/sw.js", "/manifest.webmanifest"]:
        r = client.get(url)
        assert r.status_code == 200 and "Location" not in r, url


def test_sw_and_manifest_cache_headers(client, db):
    assert client.get("/sw.js")["Cache-Control"] == "no-cache, max-age=0, must-revalidate"
    assert client.get("/manifest.webmanifest")["Cache-Control"] == "max-age=3600"


def test_subscribe_device_cap(client, me, vapid):
    for i in range(alarm_svc.MAX_DEVICES):
        PushAlarmSubscription.objects.create(user=me, endpoint=f"{EP}{i}", p256dh=P256, auth=AUTH)
    r = sub_json(client)
    assert r.status_code == 400 and "최대 20대" in r.json()["error"]
    assert sub_json(client, endpoint=f"{EP}0").status_code == 200  # 기존 endpoint 재등록은 가능
    assert PushAlarmSubscription.objects.filter(user=me).count() == alarm_svc.MAX_DEVICES


def test_subscribe_replaces_old_endpoint(client, me, other, vapid):
    PushAlarmSubscription.objects.create(user=me, endpoint=EP + "old", p256dh=P256, auth=AUTH)
    PushAlarmSubscription.objects.create(user=me, endpoint=EP + "keep", p256dh=P256, auth=AUTH)
    PushAlarmSubscription.objects.create(user=other, endpoint=EP + "theirs", p256dh=P256, auth=AUTH)
    assert sub_json(client, replaces=EP + "old").status_code == 200
    assert sub_json(client, endpoint=EP + "2", replaces=EP + "theirs").status_code == 200
    assert sub_json(client, endpoint=EP + "3", replaces=EP + "3").status_code == 200  # 자기 자신은 지우지 않음
    assert set(PushAlarmSubscription.objects.filter(user=me).values_list("endpoint", flat=True)) == {
        EP, EP + "keep", EP + "2", EP + "3"}
    assert PushAlarmSubscription.objects.filter(user=other, endpoint=EP + "theirs").exists()


def test_subscribe_replaces_frees_cap(client, me, vapid):
    for i in range(alarm_svc.MAX_DEVICES):
        PushAlarmSubscription.objects.create(user=me, endpoint=f"{EP}{i}", p256dh=P256, auth=AUTH)
    assert sub_json(client, replaces=f"{EP}0").status_code == 200
    assert PushAlarmSubscription.objects.filter(user=me).count() == alarm_svc.MAX_DEVICES


def test_push_area_sends_replaces(client, me, vapid):
    body = client.get("/alarms/").content.decode()
    assert "replaces: last()" in body and "localStorage" in body


def test_push_test_button_only_with_devices(client, me, vapid):
    body = client.get("/alarms/").content.decode()
    assert "등록된 기기가 없습니다" in body and "테스트 푸시</button>" not in body
    assert '<button id="push-off" class="secondary js-push" hidden>' in body  # 이 기기 등록 여부는 브라우저가 확인해 보인다


def test_rule_edit_shows_all_selected_as_checked(client, me):
    """'전부'는 빈 목록으로 저장된다 → 수정 화면에서 전부 체크로 보여야 한다(초기화된 것처럼 보이지 않게)."""
    import re
    from duty.models import AlarmRule
    r = AlarmRule.objects.create(user=me, kind="report", timing="days", offset=2, at_minute=9 * 60,
                                 telegram=True, push=False, shifts=[], depts=[], types=[], enabled=True)
    body = client.get(f"/alarms/rules/{r.pk}/").content.decode()
    for name, n in (("shifts", 5), ("types", 2)):
        assert body.count(f'name="{name}"') == n and len(re.findall(rf'name="{name}"[^>]*checked', body)) == n, name
