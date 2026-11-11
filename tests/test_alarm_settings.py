"""알림 설정(AlarmSettings, 한 행): 서비스·0002 데이터 이전·관리 화면."""
import importlib
import logging

import pytest
from django.apps import apps as django_apps
from django.contrib.admin.models import LogEntry
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from duty.models import AlarmSettings, PushAlarmSubscription, TelegramAlarmProfile, User
from duty.services import alarm_settings

TOKEN = "1234567890:" + "FAKE" + "x" * 31  # 가짜(비밀 탐지기에 걸리지 않게 실행 중에 만든다)
TOKEN2 = "1234567891:" + "FAKE" + "y" * 31


def test_current_creates_single_row(db):
    s = alarm_settings.current()
    assert s.pk == 1 and s.telegram_bot_token == "" and s.vapid_subject == "mailto:admin@localhost"
    assert alarm_settings.current().pk == 1 and AlarmSettings.objects.count() == 1
    assert not s.telegram_on and not s.bot_ready and not s.push_on


def test_only_pk_1(db):
    with pytest.raises(IntegrityError), transaction.atomic():
        AlarmSettings.objects.create(pk=2)


def test_flags(db):
    s = AlarmSettings(telegram_bot_token="t", vapid_public_key="a", vapid_private_key="")
    assert s.telegram_on and not s.bot_ready and not s.push_on
    s.telegram_bot_username, s.vapid_private_key = "bot", "b"
    assert s.bot_ready and s.push_on
    cfg = s.sender_config()
    assert (cfg.telegram_token, cfg.vapid_private_key, cfg.vapid_subject) == ("t", "b", "mailto:admin@localhost")


# ---- 0002 데이터 이전 ----

SEED_ENV = {"DUTY_TELEGRAM_BOT_TOKEN": TOKEN, "DUTY_TELEGRAM_BOT_USERNAME": "@duty_bot",
            "DUTY_VAPID_PUBLIC_KEY": "PUB", "DUTY_VAPID_PRIVATE_KEY": "PRIV",
            "DUTY_VAPID_SUBJECT": "mailto:ops@example.com", "DUTY_OPS_CHAT_ID": "12345"}


def seed():
    importlib.import_module("duty.migrations.0002_alarmsettings").seed_from_env(django_apps, None)


def test_seed_from_env(db, monkeypatch):
    for k, v in SEED_ENV.items():
        monkeypatch.setenv(k, v)
    seed()
    s = AlarmSettings.objects.get()
    assert (s.telegram_bot_token, s.telegram_bot_username, s.vapid_public_key, s.vapid_private_key,
            s.vapid_subject, s.ops_chat_id) == (TOKEN, "duty_bot", "PUB", "PRIV", "mailto:ops@example.com", 12345)


def test_seed_without_env(db, monkeypatch):
    for k in SEED_ENV:
        monkeypatch.delenv(k, raising=False)
    seed()
    assert not AlarmSettings.objects.exists()


def test_seed_ignores_bad_chat_id(db, monkeypatch):
    for k in SEED_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DUTY_TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("DUTY_OPS_CHAT_ID", "-100")
    seed()
    s = AlarmSettings.objects.get()
    assert s.telegram_bot_token == TOKEN and s.ops_chat_id is None and s.vapid_subject == "mailto:admin@localhost"


# ---- 푸시 키 자동 생성 ----

def test_push_keys_generated_once(db):
    s = alarm_settings.ensure_push_keys()
    assert s.push_on and len(s.vapid_public_key) == 87 and len(s.vapid_private_key) == 43
    again = alarm_settings.ensure_push_keys()
    assert (again.vapid_public_key, again.vapid_private_key) == (s.vapid_public_key, s.vapid_private_key)
    assert AlarmSettings.objects.get().vapid_private_key == s.vapid_private_key


def test_push_keys_usable_by_pywebpush(db):
    from py_vapid import Vapid01
    s = alarm_settings.ensure_push_keys()
    Vapid01.from_string(s.vapid_private_key)  # pywebpush 가 쓰는 형식으로 읽혀야 한다


def test_push_keys_failure(db, monkeypatch, caplog):
    def boom():
        raise ValueError("x")
    monkeypatch.setattr(alarm_settings, "_new_push_keys", boom)
    s = alarm_settings.ensure_push_keys()
    assert not s.push_on and "push key generation failed" in caplog.text


def test_regenerate_push_keys_deletes_subscriptions(db, make_member):
    m = make_member("가상인물")
    old = alarm_settings.ensure_push_keys()
    PushAlarmSubscription.objects.create(user=m, endpoint="https://fcm.googleapis.com/x", p256dh="p", auth="a")
    s = alarm_settings.current()
    alarm_settings.save(s, regenerate_push_keys=True)
    s.refresh_from_db()
    assert s.push_on and s.vapid_private_key != old.vapid_private_key
    assert not PushAlarmSubscription.objects.exists()


# ---- 봇 변경 시 텔레그램 확인 초기화 ----

@pytest.fixture
def linked(db, make_member):
    s = alarm_settings.current()
    s.telegram_bot_token, s.telegram_bot_username = TOKEN, "duty_bot"
    s.save()
    a, b = make_member("가상가"), make_member("가상나")
    TelegramAlarmProfile.objects.create(user=a, chat_id="111", verified_at=timezone.now())
    TelegramAlarmProfile.objects.create(user=b, link_code="code", link_expires_at=timezone.now())
    return s


@pytest.mark.parametrize("field,value", [("telegram_bot_token", TOKEN2), ("telegram_bot_username", "other_bot")])
def test_bot_change_resets_telegram(linked, field, value):
    setattr(linked, field, value)
    assert alarm_settings.save(linked) == 2
    assert not TelegramAlarmProfile.objects.filter(verified_at__isnull=False).exists()
    assert not TelegramAlarmProfile.objects.filter(link_code__isnull=False).exists()
    assert TelegramAlarmProfile.objects.filter(chat_id="111").exists()  # chat_id 는 남긴다(직접 입력 재확인용)


def test_other_change_keeps_telegram(linked):
    linked.ops_chat_id = 5
    assert alarm_settings.save(linked) == 0
    assert TelegramAlarmProfile.objects.filter(verified_at__isnull=False).count() == 1


# ---- 관리 화면 ----

@pytest.fixture
def su(client, admin_user):
    admin_user.is_superuser = True
    admin_user.save()
    client.force_login(admin_user)
    return client


def change_url():
    return reverse("admin:duty_alarmsettings_change", args=[1])


def form(**kw):
    return {"telegram_bot_token": "", "telegram_bot_username": "duty_bot", "ops_chat_id": "",
            "vapid_subject": "mailto:admin@localhost", **kw}


def test_admin_superuser_only(client, admin_user):
    client.force_login(admin_user)  # 스태프지만 슈퍼유저 아님
    alarm_settings.current()
    assert client.get(change_url()).status_code == 403


def test_admin_changelist_goes_to_single_row(su):
    r = su.get(reverse("admin:duty_alarmsettings_changelist"))
    assert r.status_code == 302 and r.url == change_url()
    assert AlarmSettings.objects.count() == 1
    assert su.get(reverse("admin:duty_alarmsettings_add")).status_code == 403
    assert su.get(reverse("admin:duty_alarmsettings_delete", args=[1])).status_code == 403


def test_admin_page_hides_token(su):
    s = alarm_settings.current()
    s.telegram_bot_token = TOKEN
    s.save()
    body = su.get(change_url()).content.decode()
    assert TOKEN not in body and TOKEN[:20] not in body and "…" + TOKEN[-4:] in body
    assert 'type="password"' in body and "토큰 지우기" in body and "푸시 키 다시 만들기" in body


def test_admin_blank_keeps_new_replaces_clear_empties(su, linked):
    r = su.post(change_url(), form(telegram_bot_token=""))
    assert r.status_code == 302, r.content.decode()
    assert AlarmSettings.objects.get().telegram_bot_token == TOKEN
    assert TelegramAlarmProfile.objects.filter(verified_at__isnull=False).count() == 1  # 안 바뀜 → 유지
    r = su.post(change_url(), form(telegram_bot_token=TOKEN2), follow=True)
    assert AlarmSettings.objects.get().telegram_bot_token == TOKEN2
    body = r.content.decode()
    assert "2명의 텔레그램 연결 확인을 비웠습니다" in body and TOKEN2 not in body
    assert not TelegramAlarmProfile.objects.filter(verified_at__isnull=False).exists()
    su.post(change_url(), form(telegram_bot_token="", clear_token="on"))
    assert AlarmSettings.objects.get().telegram_bot_token == ""
    for e in LogEntry.objects.all():
        assert TOKEN not in e.change_message and TOKEN2 not in e.change_message


@pytest.mark.parametrize("data,err", [
    (dict(telegram_bot_token="not a token"), "봇 토큰 형식이 아닙니다"),
    (dict(telegram_bot_username="bad name!"), "봇 사용자명은 영문·숫자·_ 5~32자입니다."),
    (dict(ops_chat_id="0"), "1"),
])
def test_admin_validation(su, data, err):
    alarm_settings.current()
    r = su.post(change_url(), form(**data))
    body = r.content.decode()
    assert r.status_code == 200 and "errornote" in body and err in body


def test_admin_username_strips_at(su):
    alarm_settings.current()
    su.post(change_url(), form(telegram_bot_username="@duty_bot2"))
    assert AlarmSettings.objects.get().telegram_bot_username == "duty_bot2"


def test_admin_regenerate_push_keys(su, make_member):
    old = alarm_settings.ensure_push_keys().vapid_public_key
    PushAlarmSubscription.objects.create(user=make_member("가상인물"), endpoint="https://fcm.googleapis.com/x",
                                         p256dh="p", auth="a")
    su.post(change_url(), form(regenerate_push_keys="on"))
    assert AlarmSettings.objects.get().vapid_public_key != old
    assert not PushAlarmSubscription.objects.exists()


def test_admin_save_logs_no_token(su, caplog):
    alarm_settings.current()
    with caplog.at_level(logging.DEBUG):
        su.post(change_url(), form(telegram_bot_token=TOKEN))
    assert TOKEN not in caplog.text
    assert User.objects.filter(is_superuser=True).exists()
