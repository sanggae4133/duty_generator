"""메모 알림: 관리자가 메모를 새로 달거나 고치면, 켠 사람(그 근무표 소속)에게 작업자가 한 번 보낸다. 쓴 사람은 받지 않는다."""
from datetime import date, datetime, timedelta

import pytest
from django.utils import timezone

from duty.models import Memo, TelegramAlarmProfile, User
from duty.services import alarm_settings, memo_notice, memos

D = date(2026, 11, 10)
NOW = timezone.make_aware(datetime(2026, 11, 10, 9, 0))


@pytest.fixture
def world(make_member, admin_user, monkeypatch, it_board, ops_board):
    conf = alarm_settings.current()
    conf.telegram_bot_token = "1234567890:" + "FAKE" + "x" * 31
    alarm_settings.save(conf)
    a, b = make_member("가", user=True), make_member("나", user=True)
    User.objects.filter(pk__in=[a.pk, admin_user.pk]).update(notify_memos=True)  # 나는 끔(기본)
    for u, chat in ((a, "11"), (b, "22"), (admin_user, "99")):
        TelegramAlarmProfile.objects.create(user=u, chat_id=chat, verified_at=NOW)
    sent = []
    monkeypatch.setattr("duty.alarms.senders.telegram_send", lambda cfg, chat, text: sent.append((chat, text)) or {})
    return a, b, admin_user, sent


def test_new_memo_notifies_opted_in_members_once(world, it_board):
    a, b, admin, sent = world
    memos.save(admin, it_board, "day", D, "점검 있음")
    assert memo_notice.tick(timezone.now()) == 1
    assert [c for c, _ in sent] == ["11"]  # 켠 사람만, 쓴 사람(관리자)은 빼고
    assert "[메모] IT 당번표 · 11/10(화)" in sent[0][1] and "점검 있음" in sent[0][1] and "쓴 사람: 관리자" in sent[0][1]
    sent.clear()
    assert memo_notice.tick(timezone.now()) == 0 and sent == []  # 한 번만


def test_edit_notifies_but_same_text_does_not(world, it_board):
    a, _, admin, sent = world
    memos.save(admin, it_board, "week", D, "주 메모")
    memo_notice.tick(timezone.now())
    sent.clear()
    memos.save(admin, it_board, "week", D, "주 메모")  # 그대로 저장: 알림 없음
    assert memo_notice.tick(timezone.now()) == 0
    memos.save(admin, it_board, "week", D, "주 메모 고침")
    memo_notice.tick(timezone.now())
    assert len(sent) == 1 and "11/9(월) 주" in sent[0][1] and "주 메모 고침" in sent[0][1]


def test_other_board_members_and_stale_rows_skipped(world, ops_board, it_board):
    a, _, admin, sent = world
    ops_board.admin_group.user_set.add(admin)
    memos.save(admin, ops_board, "month", D, "운영 달 메모")  # 가는 IT 소속
    assert memo_notice.tick(timezone.now()) == 0
    memos.save(admin, it_board, "day", D, "오래된 메모")
    Memo.objects.filter(text="오래된 메모").update(edited_at=timezone.now() - timedelta(days=2))  # 작업자가 오래 꺼져 있었다
    assert memo_notice.tick(timezone.now()) == 0 and not Memo.objects.filter(notice_pending=True).exists()


def test_weekend_memo_cannot_be_no_work(world, it_board):
    from duty.errors import DutyError
    _, _, admin, _ = world
    with pytest.raises(DutyError):
        memos.save(admin, it_board, "day", date(2026, 11, 14), "", no_work=True)
    memos.save(admin, it_board, "day", date(2026, 11, 14), "주말 출근")  # 글만은 된다


def test_toggle_on_alarms_page(client, world):
    _, b, _, _ = world
    client.force_login(b)
    assert "메모가 달리거나 바뀌면 알림" in client.get("/alarms/").content.decode()
    client.post("/alarms/memos/", {"on": "1"})
    b.refresh_from_db()
    assert b.notify_memos
    client.post("/alarms/memos/", {})
    b.refresh_from_db()
    assert not b.notify_memos
