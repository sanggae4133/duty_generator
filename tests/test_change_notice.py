"""내 근무가 바뀌면 알림: 작업자가 새 ChangeLog 를 보고 바뀐 당사자(From·To)에게 보낸다."""
from datetime import date, datetime, timedelta

import pytest
from django.utils import timezone

from duty.alarms import messages as m
from duty.models import ChangeLog, Commute, Period, PushAlarmSubscription, TelegramAlarmProfile, User
from duty.services import alarm_settings, change_notice, changes

D = date(2026, 11, 10)
NOW = timezone.make_aware(datetime(2026, 11, 10, 9, 0))


@pytest.fixture
def world(make_member, fixed_today, monkeypatch):
    fixed_today(D)
    conf = alarm_settings.current()
    conf.telegram_bot_token = "1234567890:" + "FAKE" + "x" * 31
    alarm_settings.save(conf)
    alarm_settings.ensure_push_keys()  # 푸시도 켜진 상태
    p = Period.objects.create(name="p", start_date=D, end_date=D + timedelta(days=3), status=Period.Status.PUBLISHED)
    a, b, c = make_member("가", user=True), make_member("나", user=True), make_member("다", user=True)
    for u, chat in ((a, "11"), (b, "22"), (c, "33")):
        TelegramAlarmProfile.objects.create(user=u, chat_id=chat, verified_at=NOW)
    Commute.objects.create(period=p, date=D, member=a, shift="normal")
    Commute.objects.create(period=p, date=D, member=b, shift="dinner")
    sent = []
    monkeypatch.setattr("duty.alarms.senders.telegram_send", lambda cfg, chat, text: sent.append((chat, text)) or {})
    monkeypatch.setattr("duty.alarms.senders.push_send", lambda cfg, sub, title, body, url, ttl: sent.append((f"push:{sub.pk}", body)))
    return p, a, b, c, sent


def test_swap_notifies_both_once_but_not_actor(world):
    p, a, b, c, sent = world
    changes.exchange(c, D, "normal", a, b)  # 다가 가·나 를 맞바꿈(기록 2건)
    change_notice.tick(NOW)
    assert sorted(x for x, _ in sent) == ["11", "22"]  # 한 사람에 한 통으로 합친다
    assert all("맞교환" in t and "정상" in t and "석식교대" in t for _, t in sent)
    assert not ChangeLog.objects.filter(notified=False).exists()
    sent.clear()
    change_notice.tick(NOW)
    assert sent == []  # 한 번만


def test_actor_is_not_notified(world):
    p, a, b, c, sent = world
    changes.exchange(a, D, "normal", a, c)  # 본인이 다에게 넘김
    change_notice.tick(NOW)
    assert [x for x, _ in sent] == ["33"]


def test_opt_out_and_push(world):
    p, a, b, c, sent = world
    User.objects.filter(pk=b.pk).update(notify_changes=False)
    sub = PushAlarmSubscription.objects.create(user=a, endpoint="https://fcm.googleapis.com/x", p256dh="p", auth="a")
    changes.exchange(c, D, "normal", a, b)
    change_notice.tick(NOW)
    assert sorted(x for x, _ in sent) == ["11", f"push:{sub.pk}"]


def test_old_or_past_changes_are_skipped(world, fixed_today):
    p, a, b, c, sent = world
    changes.exchange(c, D, "normal", a, c)
    ChangeLog.objects.update(at=NOW - timedelta(days=2))  # 하루 넘게 밀린 기록
    change_notice.tick(NOW)
    assert sent == [] and not ChangeLog.objects.filter(notified=False).exists()


def test_message_text():
    title, text = m.change_notice(D, "slot0", "가", "나", "관리자")
    assert title == "근무 변경" and "11/10(화)" in text and "장중관제 08:30~09:30" in text
    assert "가 → 나" in text and "관리자" in text
    assert "+나" in m.change_notice(D, "normal", None, "나", "관리자")[1]


def test_toggle_view(client, world):
    p, a, *_ = world
    client.force_login(a)
    assert "내 근무가 바뀌면 바로 알림" in client.get("/alarms/").content.decode()
    client.post("/alarms/changes/", {})
    assert not User.objects.get(pk=a.pk).notify_changes
    client.post("/alarms/changes/", {"on": "1"})
    assert User.objects.get(pk=a.pk).notify_changes


def test_undone_or_overwritten_changes_are_not_sent(world):
    from duty.services.publish import unpublish
    p, a, b, c, sent = world
    p.publish_undo, p.published_at = [], NOW - timedelta(hours=1)  # 실제 배포처럼
    p.save()
    changes.exchange(c, D, "normal", a, c)
    p.refresh_from_db()
    from duty.models import PeriodEvent
    PeriodEvent.objects.create(period=p, from_status="generated", to_status="published")
    unpublish(p)  # 배포 취소 → 이 기록은 근무표에서 숨는다
    change_notice.tick(NOW)
    assert sent == [] and not ChangeLog.objects.filter(notified=False).exists()


def test_marked_before_sending(world, monkeypatch):
    """보내는 도중 작업자가 죽어도 같은 알림이 다시 가지 않게 먼저 표시한다(최대 한 번)."""
    p, a, b, c, sent = world
    seen = []
    monkeypatch.setattr("duty.alarms.senders.telegram_send",
                        lambda cfg, chat, text: seen.append(ChangeLog.objects.filter(notified=False).count()) or {})
    changes.exchange(a, D, "normal", a, c)
    change_notice.tick(NOW)
    assert seen == [0]


def test_past_date_uses_perms_today(world, fixed_today):
    p, a, b, c, sent = world
    changes.exchange(c, D, "normal", a, c)
    fixed_today(D + timedelta(days=1))  # 작업 라운드가 자정을 넘긴 경우
    change_notice.tick(NOW)
    assert sent == []
