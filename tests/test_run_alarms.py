import fcntl
import logging
from datetime import date, datetime, timedelta

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from duty.alarms import senders
from duty.models import (AlarmDelivery, AlarmRule, Commute, Period, PushAlarmSubscription,
                         TelegramAlarmProfile)
from duty.services import alarm_runner, alarms

D = date(2026, 11, 16)  # 월
SUN = date(2026, 11, 15)
NAME = "가상인물"
REAL_PUSH_SEND = senders.push_send


def at(y, mo, d, h=0, mi=0, s=0):
    return timezone.make_aware(datetime(y, mo, d, h, mi, s))


SUN18 = at(2026, 11, 15, 18)
EXPIRES = at(2026, 11, 16, 6, 30)


@pytest.fixture
def env(settings, tmp_path, fixed_today):
    settings.TELEGRAM_BOT_TOKEN = "t"
    settings.VAPID_PUBLIC_KEY = settings.VAPID_PRIVATE_KEY = "k"
    settings.SITE_URL = ""
    settings.ALARMS_LOCK_PATH = str(tmp_path / "alarms.lock")
    fixed_today(SUN)
    return settings


class Fake:
    """가짜 sender. fail[목적지] = 던질 예외(또는 목록이면 차례로)."""

    def __init__(self, monkeypatch):
        self.sent, self.fail, self.during = [], {}, {}
        monkeypatch.setattr(senders, "telegram_send", self.tg)
        monkeypatch.setattr(senders, "push_send", self.push)

    def _go(self, dest, payload):
        if dest in self.during:  # 발송 도중 웹에서 일어나는 일
            self.during.pop(dest)()
        err = self.fail.get(dest)
        if isinstance(err, list):
            err = err.pop(0) if err else None
        if err:
            raise err
        self.sent.append((dest, payload))

    def tg(self, chat_id, text):
        self._go(chat_id, text)
        return {}

    def push(self, sub, title, body, url, ttl):
        self._go(f"sub:{sub.id}", dict(title=title, body=body, url=url, ttl=ttl))

    def dests(self):
        out = [d for d, _ in self.sent]
        self.sent.clear()
        return out


@pytest.fixture
def fake(monkeypatch):
    return Fake(monkeypatch)


@pytest.fixture
def member(make_member, env):
    m = make_member(NAME, user=True)
    p = Period.objects.create(name="p", start_date=D, end_date=D, status=Period.Status.PUBLISHED)
    Commute.objects.create(period=p, date=D, member=m, shift="dawn")
    return m


def verify(user, chat="111"):
    TelegramAlarmProfile.objects.create(user=user, chat_id=chat, verified_at=timezone.now())


def push_only(user, n=2):
    AlarmRule.objects.filter(user=user).update(telegram=False, push=True)
    return [PushAlarmSubscription.objects.create(user=user, endpoint=f"e{i}", p256dh="p", auth="a") for i in range(n)]


def test_default_rule_sends_once(member, fake):
    verify(member.user)
    assert alarm_runner.tick(SUN18) == (1, 1, 0)
    [(dest, text)] = fake.sent
    assert dest == "111" and f"{NAME}님, 내일 새벽 당번" in text
    assert alarm_runner.tick(SUN18 + timedelta(minutes=1)) == (0, 0, 0)
    row = AlarmDelivery.objects.get()
    assert row.status == "sent" and row.last_sent_hash == row.content_hash and row.attempts == 0


def test_unverified_or_no_token(member, fake, env):
    TelegramAlarmProfile.objects.create(user=member.user, chat_id="111")
    assert alarm_runner.tick(SUN18) == (0, 0, 0)
    TelegramAlarmProfile.objects.update(verified_at=timezone.now())
    env.TELEGRAM_BOT_TOKEN = ""
    assert alarm_runner.tick(SUN18) == (0, 0, 0)
    assert fake.sent == []


def test_push_one_device_backoff(member, fake):
    s1, s2 = push_only(member.user)
    fake.fail[f"sub:{s1.id}"] = [senders.Temporary(500), senders.Temporary(500)]
    assert alarm_runner.tick(SUN18) == (2, 1, 1)
    assert fake.dests() == [f"sub:{s2.id}"]
    alarm_runner.tick(SUN18 + timedelta(seconds=30))
    assert fake.sent == []  # backoff 1분
    alarm_runner.tick(SUN18 + timedelta(minutes=1))
    assert fake.sent == []  # 두 번째 실패
    row = AlarmDelivery.objects.get(destination=f"sub:{s1.id}")
    assert row.attempts == 2 and row.next_attempt_at == SUN18 + timedelta(minutes=3) and row.last_sent_hash is None
    alarm_runner.tick(SUN18 + timedelta(minutes=3))
    assert fake.dests() == [f"sub:{s1.id}"]
    row.refresh_from_db()
    assert row.status == "sent" and row.attempts == 0 and row.next_attempt_at is None


def test_push_payload_ttl(member, fake):
    push_only(member.user, 1)
    AlarmRule.objects.filter(timing="days").delete()
    AlarmRule.objects.update(offset=1)  # before_start 1분 → 06:29부터
    alarm_runner.tick(at(2026, 11, 16, 6, 29, 50))
    [(_, p)] = fake.sent
    assert p["ttl"] == 10 and p["url"] == "/day/2026-11-16/" and p["title"] == "당번 알림"


def test_ttl_30_days(member, fake, fixed_today):
    push_only(member.user, 1)
    AlarmRule.objects.filter(timing="before_start").delete()
    AlarmRule.objects.update(offset=30, at_minute=6 * 60 + 30)
    fixed_today(date(2026, 10, 17))
    alarm_runner.tick(at(2026, 10, 17, 6, 30))
    assert fake.sent[0][1]["ttl"] == 30 * 86400


def test_content_change_skips_backoff(member, fake):
    [s] = push_only(member.user, 1)
    fake.fail[f"sub:{s.id}"] = [senders.Temporary(), senders.Temporary()]
    alarm_runner.tick(SUN18)
    member.name = "가상인물2"
    member.save()
    alarm_runner.tick(SUN18 + timedelta(seconds=30))  # backoff 중이지만 내용이 바뀜
    row = AlarmDelivery.objects.get()
    assert row.attempts == 1 and row.next_attempt_at == SUN18 + timedelta(seconds=90)
    alarm_runner.tick(SUN18 + timedelta(seconds=90))
    assert "가상인물2" in fake.sent[0][1]["body"]


def test_retry_later_and_permanent(member, fake):
    s1, s2 = push_only(member.user)
    AlarmRule.objects.filter(timing="before_start").delete()
    fake.fail[f"sub:{s1.id}"] = [senders.RetryLater(120, 429), senders.RetryLater(0, 429), senders.RetryLater(None, 429)]
    fake.fail[f"sub:{s2.id}"] = senders.Permanent(400)
    alarm_runner.tick(SUN18)
    r1 = AlarmDelivery.objects.get(destination=f"sub:{s1.id}")
    r2 = AlarmDelivery.objects.get(destination=f"sub:{s2.id}")
    assert r1.next_attempt_at == SUN18 + timedelta(seconds=120)
    assert r2.next_attempt_at == EXPIRES and r2.status == "failed"
    t = SUN18 + timedelta(seconds=120)
    alarm_runner.tick(t)
    r1.refresh_from_db()
    assert r1.next_attempt_at == t and r1.attempts == 2  # 0초 → 다음 tick
    alarm_runner.tick(t)
    r1.refresh_from_db()
    assert r1.next_attempt_at == t + timedelta(minutes=4)  # None → Temporary 규칙(2**(3-1))
    # 근무 시작 직전까지 Permanent는 다시 시도하지 않음
    assert alarm_runner.tick(at(2026, 11, 16, 6, 29)) == (1, 1, 0)
    assert fake.dests() == [f"sub:{s1.id}"]


def test_retry_later_past_expiry_gives_up(member, fake):
    [s] = push_only(member.user, 1)
    AlarmRule.objects.filter(timing="before_start").delete()
    fake.fail[f"sub:{s.id}"] = senders.RetryLater(86400, 429)
    alarm_runner.tick(SUN18)
    assert AlarmDelivery.objects.get().next_attempt_at >= EXPIRES
    assert alarm_runner.tick(at(2026, 11, 16, 6, 29)) == (0, 0, 0)


def test_gone_deletes_subscription(member, fake):
    s1, s2 = push_only(member.user)
    fake.fail[f"sub:{s1.id}"] = senders.Gone(410)
    alarm_runner.tick(SUN18)
    assert not PushAlarmSubscription.objects.filter(id=s1.id).exists()
    assert list(AlarmDelivery.objects.values_list("destination", flat=True)) == [f"sub:{s2.id}"]


def test_unexpected_exception_is_temporary(member, fake, caplog):
    [s] = push_only(member.user, 1)
    fake.fail[f"sub:{s.id}"] = ValueError("secret-key-material")
    with caplog.at_level(logging.INFO):
        assert alarm_runner.tick(SUN18) == (1, 0, 1)
    row = AlarmDelivery.objects.get()
    assert row.status == "failed" and row.next_attempt_at == SUN18 + timedelta(minutes=1)
    assert "ValueError" in caplog.text and "secret-key-material" not in caplog.text


def test_no_cancel_after_failed_first(member, fake):
    [s] = push_only(member.user, 1)
    fake.fail[f"sub:{s.id}"] = senders.Permanent(400)
    alarm_runner.tick(SUN18)
    Commute.objects.all().delete()
    del fake.fail[f"sub:{s.id}"]
    assert alarm_runner.tick(SUN18 + timedelta(minutes=1)) == (0, 0, 0)


def test_unpublish_cancels_only_successful(member, fake):
    s1, s2 = push_only(member.user)
    fake.fail[f"sub:{s2.id}"] = senders.Permanent(400)
    alarm_runner.tick(SUN18)
    fake.dests()
    Period.objects.update(status=Period.Status.GENERATED)
    alarm_runner.tick(SUN18 + timedelta(minutes=1))
    [(dest, p)] = fake.sent
    assert dest == f"sub:{s1.id}" and p["title"] == "당번 변경"


def test_naive_now():
    with pytest.raises(ValueError):
        alarm_runner.tick(datetime(2026, 11, 15, 18))


def test_cleanup_by_work_date(member, fake):
    r = AlarmRule.objects.filter(user=member.user).first()
    for d in (SUN - timedelta(days=8), SUN - timedelta(days=7)):
        AlarmDelivery.objects.create(rule=r, date=d, cell="dawn", channel="telegram", destination="1",
                                     status="sent", content_hash="h")
    alarm_runner.tick(SUN18)
    assert list(AlarmDelivery.objects.values_list("date", flat=True)) == [SUN - timedelta(days=7)]


def test_failure_log_has_no_name(member, fake, caplog):
    verify(member.user, "98765")
    fake.fail["98765"] = senders.Temporary(502)
    with caplog.at_level(logging.INFO):
        alarm_runner.tick(SUN18)
    assert "alarm send failed" in caplog.text and "alarms tick: due=1 sent=0 failed=1" in caplog.text
    assert NAME not in caplog.text and "98765" not in caplog.text and "당번" not in caplog.text


def test_telegram_link_and_limit(env):
    env.SITE_URL = "https://duty.example"
    t = alarm_runner.telegram_text("본문", "/day/2026-11-16/")
    assert t == "본문\nhttps://duty.example/day/2026-11-16/"
    long = alarm_runner.telegram_text("가" * 4000, "/day/2026-11-16/")
    assert len(long) == 4000 and long.endswith("\nhttps://duty.example/day/2026-11-16/")
    assert "이하 생략" in long
    env.SITE_URL = ""
    assert alarm_runner.telegram_text("가" * 4000, "/x/") == "가" * 4000


def test_telegram_send_includes_link(member, fake, env):
    env.SITE_URL = "https://duty.example/"
    verify(member.user)
    alarm_runner.tick(SUN18)
    assert fake.sent[0][1].endswith("\nhttps://duty.example/day/2026-11-16/")


def test_once_locked_exits_1(env, db):
    with open(env.ALARMS_LOCK_PATH, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        with pytest.raises(CommandError, match="다른 run_alarms가 실행 중입니다.") as e:
            call_command("run_alarms", "--once")
        assert e.value.returncode == 1
        with pytest.raises(CommandError):
            call_command("run_alarms", "--dry-run")


def test_once_runs_tick(member, fake, monkeypatch):
    verify(member.user)
    monkeypatch.setattr(timezone, "now", lambda: SUN18)
    call_command("run_alarms", "--once")
    assert len(fake.sent) == 1


def test_dry_run(member, fake, monkeypatch, capsys):
    verify(member.user)
    push_only(member.user, 1)
    AlarmRule.objects.filter(timing="days").update(telegram=True)
    monkeypatch.setattr(timezone, "now", lambda: SUN18)
    call_command("run_alarms", "--dry-run")
    out = capsys.readouterr().out
    assert "telegram=1" in out and "push=1" in out and NAME not in out
    assert fake.sent == [] and not AlarmDelivery.objects.exists()


def test_telegram_link_too_long_is_dropped(env):
    env.SITE_URL = "https://duty.example/" + "x" * 4000
    t = alarm_runner.telegram_text("가" * 5000, "/day/2026-11-16/")
    assert len(t) == 4000 and "https://" not in t
    # 경계: 링크+줄바꿈 뒤에 생략 표시(CUT) 자리까지 있어야 링크 포함
    from duty.alarms.messages import CUT
    url = "/day/2026-11-16/"
    for room, has_link in ((len(CUT), True), (len(CUT) - 1, False), (0, False)):
        env.SITE_URL = "h" * (3999 - room - len(url))
        t = alarm_runner.telegram_text("가" * 5000, url)
        assert len(t) == 4000 and t.endswith(CUT if not has_link else "\n" + env.SITE_URL + url)
        assert ("h" in t) == has_link


def test_long_site_url_warns_once_without_url(member, fake, env, caplog):
    env.SITE_URL = "https://secret-host.example/" + "x" * 4000
    verify(member.user)
    AlarmRule.objects.filter(timing="days").update(push=True)
    PushAlarmSubscription.objects.create(user=member.user, endpoint="e", p256dh="p", auth="a")
    with caplog.at_level(logging.WARNING):
        alarm_runner.tick(SUN18)
    assert len(fake.sent) == 2 and len(fake.sent[0][1]) <= 4000
    assert caplog.text.count("SITE_URL") == 1 and "secret-host" not in caplog.text


def test_failure_keeps_last_sent_hash(member, fake):
    verify(member.user)
    alarm_runner.tick(SUN18)
    old = AlarmDelivery.objects.get().last_sent_hash
    member.name = "가상인물2"
    member.save()
    fake.fail["111"] = senders.Temporary(502)
    alarm_runner.tick(SUN18 + timedelta(minutes=1))
    row = AlarmDelivery.objects.get()
    assert row.status == "failed" and row.attempts == 1
    assert row.last_sent_hash == old and row.content_hash != old and row.content_hash.startswith("in:")


def test_log_has_no_token_or_endpoint(member, monkeypatch, env, caplog):
    import requests
    from pywebpush import WebPushException

    token = "1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
    endpoint = "https://fcm.googleapis.com/fcm/send/secret-endpoint-abc"
    env.TELEGRAM_BOT_TOKEN = token
    verify(member.user)
    AlarmRule.objects.filter(timing="days").update(push=True)
    PushAlarmSubscription.objects.create(user=member.user, endpoint=endpoint, p256dh="p", auth="a")

    def boom_url(*a, **kw):
        raise OSError(f"connect failed {a[0].full_url}")

    def boom_push(*a, **kw):
        resp = requests.Response()
        resp.status_code = 500
        raise WebPushException(f"push failed {endpoint}", response=resp)

    monkeypatch.setattr("urllib.request.urlopen", boom_url)
    monkeypatch.setattr(senders, "webpush", boom_push)
    with caplog.at_level(logging.DEBUG):
        assert alarm_runner.tick(SUN18) == (2, 0, 2)
    assert token not in caplog.text and "secret-endpoint" not in caplog.text and NAME not in caplog.text


def test_recheck_failure_deletes_subscription(member, fake, monkeypatch):
    # 저장된 endpoint가 현재 검사에 걸리면 보내지 않고 Gone처럼 구독을 지운다
    s1, s2 = push_only(member.user)
    PushAlarmSubscription.objects.filter(id=s1.id).update(endpoint="https://evil.example\\.fcm.googleapis.com/x")
    monkeypatch.setattr(senders, "push_send", REAL_PUSH_SEND)
    monkeypatch.setattr(senders, "webpush", lambda **kw: pytest.fail("발송되면 안 됨"))
    PushAlarmSubscription.objects.filter(id=s2.id).delete()
    alarm_runner.tick(SUN18)
    assert not PushAlarmSubscription.objects.filter(id=s1.id).exists()


def test_duty_info_logs_reach_console(settings):
    """운영 로그 파일(systemd가 stderr를 붙임)에 'alarms tick:' INFO 줄이 시각·레벨과 함께 정확히 한 번 찍혀야 한다."""
    import os
    import subprocess
    import sys
    code = "import django, logging; django.setup(); logging.getLogger('duty.x').info('hello')"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                       env={**os.environ, "DJANGO_SETTINGS_MODULE": "config.test_settings"},
                       cwd=settings.BASE_DIR)
    import re
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d INFO duty\.x hello\n", r.stderr), r.stderr


def test_lock_defaults_follow_db_dir(monkeypatch, tmp_path):
    """잠금 기본 경로는 DB 폴더(서비스 사용자가 반드시 쓸 수 있음). 환경변수가 있으면 그 값."""
    import importlib

    import config.settings as cs
    monkeypatch.setenv("DUTY_DB_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.delenv("DUTY_ALARMS_LOCK", raising=False)
    monkeypatch.delenv("DUTY_TELEGRAM_LOCK", raising=False)
    try:
        importlib.reload(cs)
        assert cs.ALARMS_LOCK_PATH == str(tmp_path / ".alarms.lock")
        assert cs.TELEGRAM_UPDATES_LOCK_PATH == str(tmp_path / ".telegram-updates.lock")
        assert cs.DATABASES["default"]["NAME"] == str(tmp_path / "db.sqlite3")
        monkeypatch.setenv("DUTY_ALARMS_LOCK", "/x/a.lock")
        importlib.reload(cs)
        assert cs.ALARMS_LOCK_PATH == "/x/a.lock"
    finally:
        monkeypatch.undo()
        importlib.reload(cs)


def report_rule(user):
    AlarmRule.objects.filter(user=user).delete()
    return AlarmRule.objects.create(user=user, kind="report", timing="days", offset=1, at_minute=18 * 60,
                                    telegram=True, push=False, shifts=["dawn"], depts=[], types=[])


@pytest.mark.parametrize("staff", [False, True])
def test_inactive_member_report_rule(member, fake, staff):
    report_rule(member.user)
    verify(member.user)
    member.is_active = False
    member.save()
    member.user.is_staff = staff
    member.user.save()
    alarm_runner.tick(SUN18)
    assert len(fake.sent) == (1 if staff else 0)


def test_invalid_rule_does_not_stop_tick(member, fake, make_member, caplog):
    from django.db import connection
    verify(member.user)
    bad = make_member("가상둘", user=True)
    verify(bad.user, "222")
    with connection.cursor() as c:
        c.execute("PRAGMA ignore_check_constraints = ON")
        try:
            AlarmRule.objects.filter(user=bad.user).update(timing="weird")
        finally:
            c.execute("PRAGMA ignore_check_constraints = OFF")
    with caplog.at_level(logging.WARNING):
        alarm_runner.tick(SUN18)
    assert fake.dests() == ["111"]
    assert "가상둘" not in caplog.text and "invalid" in caplog.text


def two_users(member, make_member):
    verify(member.user)
    other = make_member("가상둘", user=True)
    Commute.objects.create(period=Period.objects.get(), date=D, member=other, shift="dawn")
    verify(other.user, "222")
    return AlarmRule.objects.get(user=member.user, timing="days")


@pytest.mark.parametrize("change", ["toggle", "save", "delete"])
def test_rule_changed_during_send(member, fake, make_member, change):
    """첫 발송 도중 규칙이 바뀌면 그 규칙의 남은 발송은 건너뛰고 기록도 남기지 않는다. 다른 규칙은 계속."""
    rule = two_users(member, make_member)
    AlarmRule.objects.filter(id=rule.id).update(push=True)
    [s] = PushAlarmSubscription.objects.bulk_create(
        [PushAlarmSubscription(user=member.user, endpoint="e0", p256dh="p", auth="a")])
    acts = {"toggle": lambda: alarms.toggle_rule(AlarmRule.objects.get(id=rule.id)),
            "save": lambda: alarms.save_rule(member.user, dict(
                kind="personal", timing="days", offset=1, at_minute=17 * 60, telegram=True, push=True,
                shifts=["dawn", "dinner", "night"], depts=[], types=[]), AlarmRule.objects.get(id=rule.id)),
            "delete": lambda: alarms.delete_rule(AlarmRule.objects.get(id=rule.id))}
    fake.during["111"] = acts[change]
    alarm_runner.tick(SUN18)
    assert fake.dests() == ["111", "222"]  # push(sub)는 건너뜀
    assert not AlarmDelivery.objects.filter(rule_id=rule.id).exists()
    assert AlarmDelivery.objects.filter(destination="222", status="sent").exists()


def test_failed_record_skipped_when_rule_deleted(member, fake, make_member):
    rule = two_users(member, make_member)

    def boom():
        alarms.delete_rule(AlarmRule.objects.get(id=rule.id))
        raise senders.Temporary(500)
    fake.during["111"] = boom
    alarm_runner.tick(SUN18)
    assert fake.dests() == ["222"]
    assert list(AlarmDelivery.objects.values_list("destination", flat=True)) == ["222"]


def test_push_owner_changed_during_send(member, fake, make_member):
    rule = AlarmRule.objects.get(user=member.user, timing="days")
    AlarmRule.objects.filter(id=rule.id).update(push=True)
    verify(member.user)
    [s] = PushAlarmSubscription.objects.bulk_create(
        [PushAlarmSubscription(user=member.user, endpoint="e0", p256dh="p", auth="a")])
    other = make_member("가상둘", user=True)
    fake.during["111"] = lambda: PushAlarmSubscription.objects.filter(id=s.id).update(user=other.user)
    alarm_runner.tick(SUN18)
    assert fake.dests() == ["111"]
    assert not AlarmDelivery.objects.filter(destination=f"sub:{s.id}").exists()
