"""새 휴장일이 켜지면 그날(오늘 이후) 배포된 근무를 근무 없음처럼 비운다: 지운 것마다 ChangeLog(바꾼 사람 없음 = 자동),
변경 알림이 당사자에게 간다. 이름은 모두 가상."""
from datetime import date, datetime, timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from duty.models import ChangeLog, Commute, DutyAssignment, Holiday, Period, User
from duty.services import alarm_settings, change_notice, holidays

S = Period.Status
TODAY = date(2026, 11, 16)
D = date(2026, 11, 18)  # 수: 임시공휴일


@pytest.fixture
def world(make_member, fixed_today, it_board):
    fixed_today(TODAY)
    p = Period.objects.create(board=it_board, name="p", start_date=TODAY, end_date=date(2026, 11, 20),
                              status=S.PUBLISHED, overwrite_from=TODAY)
    a, b = make_member("가", user=True), make_member("나", user=True)
    Commute.objects.create(period=p, date=D, member=a, shift="normal")
    DutyAssignment.objects.create(period=p, date=D, member=b, cell="slot0")
    Commute.objects.create(period=p, date=date(2026, 11, 19), member=b, shift="normal")
    return p, a, b


def test_clear_day_logs_each_row_without_actor(world):
    p, a, b = world
    assert holidays.clear_day(D) == 2
    assert not Commute.objects.filter(date=D).exists() and not DutyAssignment.objects.filter(date=D).exists()
    assert sorted(ChangeLog.objects.values_list("cell", "before__name", "after", "by")) == [
        ("normal", "가", None, None), ("slot0", "나", None, None)]
    assert Commute.objects.filter(date=date(2026, 11, 19)).exists()  # 다른 날은 그대로


def test_clear_day_skips_past_and_unpublished(world, it_board):
    p, a, b = world
    Commute.objects.create(period=p, date=TODAY - timedelta(days=0), member=a, shift="dawn")
    q = Period.objects.create(board=it_board, name="q", start_date=date(2026, 11, 23), end_date=date(2026, 11, 27),
                              status=S.COLLECTING)
    Commute.objects.create(period=q, date=date(2026, 11, 24), member=a, shift="normal")
    assert holidays.clear_day(date(2026, 11, 13)) == 0  # 지난 날은 그대로(기록)
    assert holidays.clear_day(date(2026, 11, 24)) == 0  # 배포 전 회차의 입력은 그대로(만드는 도구가 건너뛴다)
    assert Commute.objects.filter(date=date(2026, 11, 24)).exists() and not ChangeLog.objects.exists()


def test_sync_clears_newly_added_holiday(world, monkeypatch):
    monkeypatch.setattr("duty.market_days.holidays_for", lambda y: {D: "임시공휴일"} if y == 2026 else {})
    holidays.sync(TODAY)
    assert not Commute.objects.filter(date=D).exists()
    holidays.sync(TODAY)  # 이미 있는 휴장일은 다시 보지 않는다
    assert ChangeLog.objects.count() == 2


@pytest.fixture
def superuser_client(client, it_board):
    su = User.objects.create_superuser("root", password="unused-Pw-123", name="최고")
    client.force_login(su)
    return client


def test_admin_add_holiday_clears_day(world, superuser_client):
    url = f"/{settings.ADMIN_PATH}/duty/holiday/add/"
    r = superuser_client.post(url, {"date": D.isoformat(), "name": "임시공휴일", "active": "on"}, follow=True)
    assert Holiday.objects.filter(date=D, active=True).exists()
    assert not Commute.objects.filter(date=D).exists()
    assert "2명의 근무를 지웠습니다" in r.content.decode()


def test_admin_turning_holiday_on_clears_but_off_does_not_restore(world, superuser_client):
    h = Holiday.objects.create(date=D, name="임시공휴일", active=False, source=Holiday.Source.MANUAL)
    url = f"/{settings.ADMIN_PATH}/duty/holiday/{h.pk}/change/"
    superuser_client.post(url, {"name": "임시공휴일", "active": "on"})
    assert not Commute.objects.filter(date=D).exists()
    superuser_client.post(url, {"name": "임시공휴일"})  # 끄기
    assert not Commute.objects.filter(date=D).exists() and ChangeLog.objects.count() == 2


def test_change_notice_says_automatic(world, monkeypatch):
    p, a, b = world
    conf = alarm_settings.current()
    conf.telegram_bot_token = "1234567890:" + "FAKE" + "x" * 31
    alarm_settings.save(conf)
    from duty.models import TelegramAlarmProfile
    now = timezone.make_aware(datetime(2026, 11, 16, 9, 0))
    TelegramAlarmProfile.objects.create(user=a, chat_id="11", verified_at=now)
    sent = []
    monkeypatch.setattr("duty.alarms.senders.telegram_send", lambda cfg, chat, text: sent.append((chat, text)) or {})
    Holiday.objects.create(date=D, name="임시공휴일", source=Holiday.Source.MANUAL)
    holidays.clear_day(D)
    change_notice.tick(now)
    assert sent and "가 빠짐" in sent[0][1] and "바꾼 사람: 자동(휴장일)" in sent[0][1]
