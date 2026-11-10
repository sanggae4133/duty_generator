from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone

from duty.alarms import senders
from duty.models import AlarmDelivery, AlarmRule, TelegramAlarmProfile

D = date(2026, 11, 10)
BOT = dict(TELEGRAM_BOT_TOKEN="TOK", TELEGRAM_BOT_USERNAME="duty_test_bot")


@pytest.fixture
def me(db, depts, client, fixed_today):
    fixed_today(D)
    u = User.objects.create_user("u1", password="unused-Pw-123")
    AlarmRule.objects.filter(user=u).delete()  # 기본 규칙 제거
    client.force_login(u)
    return u


@pytest.fixture
def other(db):
    return User.objects.create_user("u2", password="unused-Pw-123")


@pytest.fixture
def bot(settings, tmp_path):
    settings.TELEGRAM_BOT_TOKEN = "TOK"
    settings.TELEGRAM_BOT_USERNAME = "duty_test_bot"
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


# ---- 텔레그램 직접 입력 ----

@pytest.mark.parametrize("v", ["0", "-5", str(2**63), "abc", "1.5"])
def test_chat_id_range(client, me, bot, monkeypatch, v):
    monkeypatch.setattr(senders, "telegram_check", lambda c: pytest.fail("호출되면 안 됨"))
    r = post(client, "/alarms/telegram/", {"chat_id": v})
    assert "개인 채팅 chat_id(양수 숫자)만 입력하세요." in msgs(r)
    assert not TelegramAlarmProfile.objects.filter(user=me, chat_id=v).exists()


def test_chat_id_saved_when_private(client, me, bot, monkeypatch):
    monkeypatch.setattr(senders, "telegram_check", lambda c: "private")
    post(client, "/alarms/telegram/", {"chat_id": str(2**63 - 1)})
    p = TelegramAlarmProfile.objects.get(user=me)
    assert p.chat_id == str(2**63 - 1) and p.verified_at is not None


@pytest.mark.parametrize("result,text", [("group", "개인 채팅이 아닙니다."),
                                         (senders.Permanent(400), "테스트 발송 실패: 봇에게 먼저 /start를 보냈는지 확인하세요.")])
def test_chat_id_not_saved(client, me, bot, monkeypatch, result, text):
    def fake(c):
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(senders, "telegram_check", fake)
    r = post(client, "/alarms/telegram/", {"chat_id": "123"})
    assert text in msgs(r)
    assert not TelegramAlarmProfile.objects.filter(user=me, chat_id="123").exists()


def test_bot_not_configured(client, me, settings):
    settings.TELEGRAM_BOT_TOKEN = ""
    r = post(client, "/alarms/telegram/", {"chat_id": "123"})
    assert "텔레그램 봇이 설정되지 않았습니다." in msgs(r)


def test_telegram_cooldown(client, me, bot, monkeypatch):
    n = []
    monkeypatch.setattr(senders, "telegram_check", lambda c: n.append(c) or "group")
    post(client, "/alarms/telegram/", {"chat_id": "123"})
    r = post(client, "/alarms/telegram/", {"chat_id": "123"})
    assert "잠시 후 다시 시도하세요." in msgs(r) and len(n) == 1
    TelegramAlarmProfile.objects.filter(user=me).update(last_test_at=timezone.now() - timedelta(seconds=31))
    post(client, "/alarms/telegram/", {"chat_id": "123"})
    assert len(n) == 2


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


def test_link_without_bot(client, me, settings):
    settings.TELEGRAM_BOT_USERNAME = ""
    settings.TELEGRAM_BOT_TOKEN = "TOK"
    r = post(client, "/alarms/telegram/link/")
    assert "텔레그램 봇이 설정되지 않았습니다." in msgs(r)


def upd(uid, text, chat_id, chat_type="private"):
    return {"update_id": uid, "message": {"text": text, "chat": {"id": chat_id, "type": chat_type}}}


@pytest.fixture
def tgapi(monkeypatch):
    """getUpdates 가짜: offset 이전 것은 확인 처리된 것으로 본다."""
    st = {"updates": [], "calls": [], "sent": [], "raise": None, "send_raise": None}

    def get_updates(offset=None, limit=100):
        st["calls"].append(offset)
        if st["raise"]:
            raise st["raise"]
        got = [u for u in st["updates"] if offset is None or u["update_id"] >= offset]
        return got[:2]  # 한 묶음 2개로 잘라 여러 묶음 처리 확인

    def send(chat_id, text):
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
    assert "연결 코드는 10분 동안 유효하고" in body and "고급" in body and "TOK" not in body


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


def test_direct_entry_invalidates_pending_code(client, me, bot, monkeypatch):
    code_of(me, client)
    monkeypatch.setattr(senders, "telegram_check", lambda c: "private")
    post(client, "/alarms/telegram/", {"chat_id": "77"})
    p = TelegramAlarmProfile.objects.get(user=me)
    assert p.chat_id == "77" and p.link_code is None and p.link_expires_at is None


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

    def flaky(offset=None, limit=100):
        if offset is not None:
            raise senders.Temporary(502)
        return real(offset, limit)
    tgapi["updates"] = [upd(1, f"/start {code}", 42)]
    monkeypatch.setattr(senders, "telegram_get_updates", flaky)
    r = post(client, "/alarms/telegram/link/check/")
    assert "텔레그램 서버에 연결하지 못했습니다. 잠시 후 다시 시도하세요." in msgs(r)
    assert TelegramAlarmProfile.objects.get(user=me).chat_id == "42"
    assert [c for c, _ in tgapi["sent"]] == ["42"]


def test_no_username_still_allows_direct_entry_and_disconnect(client, me, settings):
    settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_BOT_USERNAME = "TOK", ""
    TelegramAlarmProfile.objects.create(user=me, chat_id="9", verified_at=timezone.now())
    body = client.get("/alarms/").content.decode()
    assert "저장 및 테스트" in body and "연결 해제" in body and "텔레그램 연결</button>" not in body
    settings.TELEGRAM_BOT_TOKEN = ""
    body = client.get("/alarms/").content.decode()
    assert "연결 해제" in body and "저장 및 테스트" not in body


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
        "새벽·정상·석식교대·장중당번 08:30~10:30은 발송 시각이 근무 시작 이후라 제외됩니다."
