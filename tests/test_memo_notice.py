"""메모 알림(근무표마다 관리자가 켬): 관리자가 메모를 새로 달거나 고치면, 그 근무표 소속 모두에게 작업자가 한 번 보낸다.
쓴 사람은 받지 않는다. 메모 글은 자르지 않고 전부."""
from datetime import date, datetime, timedelta

import pytest
from django.utils import timezone

from duty.models import Board, Memo, PushAlarmSubscription, TelegramAlarmProfile
from duty.services import alarm_settings, board_settings, memo_notice, memos

D = date(2026, 11, 10)
NOW = timezone.make_aware(datetime(2026, 11, 10, 9, 0))


@pytest.fixture
def world(make_member, admin_user, monkeypatch, it_board, ops_board):
    conf = alarm_settings.current()
    conf.telegram_bot_token = "1234567890:" + "FAKE" + "x" * 31
    alarm_settings.save(conf)
    alarm_settings.ensure_push_keys()
    a, b = make_member("가", user=True), make_member("나", user=True)
    for u, chat in ((a, "11"), (b, "22"), (admin_user, "99")):
        TelegramAlarmProfile.objects.create(user=u, chat_id=chat, verified_at=NOW)
    Board.objects.filter(pk=it_board.pk).update(notify_memos=True)
    sent = []
    monkeypatch.setattr("duty.alarms.senders.telegram_send", lambda cfg, chat, text: sent.append((chat, text)) or {})
    monkeypatch.setattr("duty.alarms.senders.push_send", lambda cfg, sub, title, body, url, ttl: sent.append((f"push:{sub.pk}", body)))
    return a, b, admin_user, sent


def tick():
    return memo_notice.tick(timezone.now())


def test_board_on_notifies_all_members_once(world, it_board):
    a, b, admin, sent = world
    memos.save(admin, it_board, "day", D, "점검 있음")
    assert tick() == 2
    assert sorted(c for c, _ in sent) == ["11", "22"]  # 그 근무표 사람 모두, 쓴 사람(관리자)은 빼고
    assert "[메모] IT 당번표 · 11/10(화)" in sent[0][1] and "점검 있음" in sent[0][1] and "쓴 사람: 관리자" in sent[0][1]
    sent.clear()
    assert tick() == 0 and sent == []  # 한 번만


def test_board_off_sends_nothing(world, it_board):
    _, _, admin, sent = world
    Board.objects.filter(pk=it_board.pk).update(notify_memos=False)
    memos.save(admin, it_board, "day", D, "점검 있음")
    assert tick() == 0 and sent == [] and not Memo.objects.filter(notice_pending=True).exists()


def test_full_memo_text_in_telegram_and_push(world, it_board):
    a, _, admin, sent = world
    sub = PushAlarmSubscription.objects.create(user=a, endpoint="https://fcm.googleapis.com/x", p256dh="p", auth="a")
    text = "\n".join(f"{i}번째 줄 공지 내용입니다" for i in range(1, 40))[:500]  # 메모 최대 500자
    memos.save(admin, it_board, "week", D, text)
    tick()
    got = dict(sent)
    assert text in got["11"] and text in got[f"push:{sub.pk}"]  # 자르지 않는다
    assert got[f"push:{sub.pk}"].startswith("[메모] IT 당번표 · 11/9(월) 주")


def test_edit_notifies_but_same_text_does_not(world, it_board):
    _, _, admin, sent = world
    memos.save(admin, it_board, "week", D, "주 메모")
    tick()
    sent.clear()
    memos.save(admin, it_board, "week", D, "주 메모")  # 그대로 저장: 알림 없음
    assert tick() == 0
    memos.save(admin, it_board, "week", D, "주 메모 고침")
    tick()
    assert len(sent) == 2 and "주 메모 고침" in sent[0][1]


def test_other_board_members_and_stale_rows_skipped(world, ops_board, it_board):
    _, _, admin, sent = world
    Board.objects.filter(pk=ops_board.pk).update(notify_memos=True)
    ops_board.admin_group.user_set.add(admin)
    memos.save(admin, ops_board, "month", D, "운영 달 메모")  # 가·나는 IT 소속
    assert tick() == 0
    memos.save(admin, it_board, "day", D, "오래된 메모")
    Memo.objects.filter(text="오래된 메모").update(edited_at=timezone.now() - timedelta(days=2))  # 작업자가 오래 꺼져 있었다
    assert tick() == 0 and not Memo.objects.filter(notice_pending=True).exists()


def test_weekend_memo_cannot_be_no_work(world, it_board):
    from duty.errors import DutyError
    _, _, admin, _ = world
    with pytest.raises(DutyError):
        memos.save(admin, it_board, "day", date(2026, 11, 14), "", no_work=True)
    memos.save(admin, it_board, "day", date(2026, 11, 14), "주말 출근")  # 글만은 된다


def test_admin_toggles_on_board_settings(client, world, it_board):
    a, _, admin, _ = world
    with pytest.raises(Exception):
        board_settings.set_memo_notice(a, it_board, False)  # 관리자만
    client.force_login(admin)
    body = client.get("/settings/").content.decode()
    assert 'id="notices"' in body and "메모 알림" in body
    client.post("/settings/", {"do": "memo_notice"})  # 체크 해제 = 끔
    assert not Board.objects.get(pk=it_board.pk).notify_memos
    client.post("/settings/", {"do": "memo_notice", "on": "1"})
    assert Board.objects.get(pk=it_board.pk).notify_memos


def test_alarms_page_shows_board_setting_not_switch(client, world, it_board):
    a, _, _, _ = world
    client.force_login(a)
    body = client.get("/alarms/").content.decode()
    assert "/alarms/memos/" not in body and "메모 알림: 켜짐" in body
