"""관리자·사용자 실수 방지: 지난 날 배포 경고, 메모 알림 안내·지난 메모 무알림·알림 없이 저장,
근무 변경 From 미리 고르지 않기, 마감 회차 입력 표 잠금, 변경 이력 500건 안내, 통계 근무표 이름·열 이름. 이름은 모두 가상."""
from datetime import date, datetime

from django.utils import timezone

from duty.models import Board, BoardShift, ChangeLog, Commute, Memo, Period
from duty.services import memo_notice, memos

S = Period.Status


def test_publish_warns_when_overwriting_past_days(admin_client_ok, fixed_today, it_board):
    fixed_today(date(2026, 11, 11))
    p = Period.objects.create(board=it_board, name="새", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13),
                              status=S.GENERATED)
    html = admin_client_ok.get(f"/periods/{p.pk}/publish/?from=2026-11-09").content.decode()
    assert html.count("오늘 이전 2일") == 2  # 미리보기와 배포 확인창
    assert "오늘 이전" not in admin_client_ok.get(f"/periods/{p.pk}/publish/?from=2026-11-11").content.decode()


def test_memo_form_says_who_gets_notice(admin_client_ok, make_member, it_board):
    make_member("가", user=True)
    make_member("나", user=True)
    assert "알림" not in admin_client_ok.get("/memo/day/2026-11-18/").content.decode()  # 메모 알림이 꺼져 있으면 안내 없음
    Board.objects.filter(pk=it_board.pk).update(notify_memos=True)
    body = admin_client_ok.get("/memo/day/2026-11-18/").content.decode()
    assert "2명에게 텔레그램·푸시로 보냅니다" in body and 'name="notify"' in body


def test_memo_save_without_notice(admin_user, it_board):
    memos.save(admin_user, it_board, "day", date(2026, 11, 18), "오타", notify=False)
    assert not Memo.objects.get().notice_pending
    memos.save(admin_user, it_board, "day", date(2026, 11, 18), "오타 고침")
    assert Memo.objects.get().notice_pending
    # 아직 안 나간 알림이 있으면 바로 이어 오타만 고쳐(알림 끔) 저장해도 그 알림은 살아 있다(고친 글로 나간다)
    memos.save(admin_user, it_board, "day", date(2026, 11, 18), "오타 고침.", notify=False)
    assert Memo.objects.get().notice_pending


def test_memo_post_without_notify_box(admin_client_ok, it_board):
    Board.objects.filter(pk=it_board.pk).update(notify_memos=True)
    admin_client_ok.post("/memo/day/2026-11-18/", {"text": "x"})  # 체크 해제 = 보내지 않음
    assert not Memo.objects.get().notice_pending
    admin_client_ok.post("/memo/day/2026-11-18/", {"text": "y", "notify": "1"})
    assert Memo.objects.get().notice_pending


def test_past_memo_is_not_notified(admin_user, make_member, it_board, monkeypatch):
    make_member("가", user=True)
    Board.objects.filter(pk=it_board.pk).update(notify_memos=True)
    sent = []
    monkeypatch.setattr("duty.services.memo_notice._send", lambda *a: sent.append(a) or 1)
    memos.save(admin_user, it_board, "week", date(2026, 11, 10), "지난주 기록")  # 11/9 ~ 11/15 주
    memos.save(admin_user, it_board, "day", date(2026, 11, 16), "오늘")
    now = timezone.make_aware(datetime(2026, 11, 16, 9, 0))
    assert memo_notice.tick(now) == 1 and "오늘" in sent[0][3]


def test_cell_form_from_not_preselected_and_blank_rejected(admin_client_ok, make_member, fixed_today, it_board):
    fixed_today(date(2026, 11, 1))
    d = date(2026, 11, 9)
    p = Period.objects.create(board=it_board, name="p", start_date=d, end_date=d, status=S.PUBLISHED, overwrite_from=d)
    a, b, c = make_member("가"), make_member("나"), make_member("다")
    for m in (a, b):
        Commute.objects.create(period=p, date=d, member=m, shift="normal")
    body = admin_client_ok.get(f"/cell/{d}/normal/").content.decode()
    assert body.count("바뀔 사람 선택") == 1 and body.count("사유를 붙일 사람 선택") == 1
    r = admin_client_ok.post(f"/cell/{d}/normal/", {"before": "", "after": c.pk}, follow=True)
    assert "From 을 골라 주세요." in r.content.decode()
    assert not ChangeLog.objects.exists()


def test_collect_table_readonly_when_not_open(client, depts, make_member, fixed_today, it_board):
    fixed_today(date(2026, 11, 1))
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 9),
                              status=S.CLOSED)
    mgr = make_member("담당", user=True)
    depts["MEMS"].input_group.user_set.add(mgr)
    client.force_login(mgr)
    body = client.get(f"/collect/{p.pk}/MEMS/").content.decode()
    assert 'name="c_2026-11-09_dawn" rows="2" readonly' in body


def test_change_log_says_when_cut(admin_client_ok, make_member, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 9),
                              status=S.PUBLISHED)
    m = make_member("가")
    ChangeLog.objects.bulk_create(
        [ChangeLog(period=p, date=date(2026, 11, 9), cell="dawn", before=None, after=m) for _ in range(500)])
    assert "최근 500건만" not in admin_client_ok.get("/changes/").content.decode()
    ChangeLog.objects.create(period=p, date=date(2026, 11, 9), cell="dawn", before=None, after=m)
    body = admin_client_ok.get("/changes/").content.decode()
    assert "최근 500건만" in body and "(예전 기록)" in body


def test_stats_shows_board_and_shift_names(admin_client_ok, it_board):
    BoardShift.objects.filter(board=it_board, key="dawn").update(name="첫차")
    body = admin_client_ok.get("/stats/").content.decode()
    assert "근무 통계 · IT 당번표" in body and "<th>첫차</th>" in body
