"""메모(날·주·달)와 근무 없음(설계 4.8·6.5). 이름은 모두 가상."""
from datetime import date

import pytest
from django.core.exceptions import PermissionDenied

from duty.errors import DutyError
from duty.models import Board, ChangeLog, Commute, DutyAssignment, Memo, Period
from duty.services import memos

S = Period.Status
D = date(2026, 11, 18)  # 수요일


@pytest.fixture
def world(make_member, admin_user, fixed_today, it_board):
    fixed_today(date(2026, 11, 16))
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 16), end_date=date(2026, 11, 20),
                              status=S.PUBLISHED, overwrite_from=date(2026, 11, 16))
    m = {n: make_member(n, user=True) for n in ["가", "나", "다"]}
    Commute.objects.create(period=p, date=D, member=m["가"], shift="dawn")
    Commute.objects.create(period=p, date=D, member=m["나"], shift="normal")
    DutyAssignment.objects.create(period=p, date=D, cell="slot0", member=m["가"])
    Commute.objects.create(period=p, date=date(2026, 11, 19), member=m["다"], shift="normal")
    return p, m


# ── 저장·정규화·권한 ──

def test_save_normalizes_week_and_month(admin_user, it_board):
    memos.save(admin_user, it_board, "week", D, "  주말 근무: 가  ")
    memos.save(admin_user, it_board, "month", D, "본부 점심: 나")
    assert Memo.objects.get(scope="week").date == date(2026, 11, 16)
    assert Memo.objects.get(scope="week").text == "주말 근무: 가"
    assert Memo.objects.get(scope="month").date == date(2026, 11, 1)
    memos.save(admin_user, it_board, "week", date(2026, 11, 20), "고침")  # 같은 주 다른 날 = 같은 메모
    assert Memo.objects.filter(scope="week").count() == 1 and Memo.objects.get(scope="week").text == "고침"


def test_empty_text_deletes(admin_user, it_board):
    memos.save(admin_user, it_board, "day", D, "행사")
    memos.save(admin_user, it_board, "day", D, "  ")
    assert not Memo.objects.exists()


def test_no_work_only_for_day(admin_user, it_board):
    with pytest.raises(DutyError, match="날 메모"):
        memos.save(admin_user, it_board, "week", D, "x", no_work=True)


def test_too_long_rejected(admin_user, it_board):
    with pytest.raises(DutyError, match="500"):
        memos.save(admin_user, it_board, "day", D, "가" * 501)


def test_only_board_admin(world, it_board):
    _, m = world
    with pytest.raises(PermissionDenied):
        memos.save(m["가"], it_board, "day", D, "x")
    Memo.objects.create(board=it_board, scope="day", date=D, text="x")
    with pytest.raises(PermissionDenied):
        memos.delete(m["가"], it_board, "day", D)
    assert Memo.objects.exists()


def test_admin_of_other_board_cannot_edit(admin_user):
    other = Board.objects.create(code="ops", name="운영팀")
    with pytest.raises(PermissionDenied):
        memos.save(admin_user, other, "day", D, "x")


# ── 근무 없음: 배정 지우기 ──

def test_no_work_needs_confirm_when_people_assigned(world, admin_user, it_board):
    assert memos.affected(it_board, D) == 2
    with pytest.raises(DutyError, match="2명의 근무가 지워집니다"):
        memos.save(admin_user, it_board, "day", D, "임시 휴무", no_work=True)
    assert not Memo.objects.exists() and Commute.objects.filter(date=D).count() == 2


def test_no_work_clears_day_and_logs_each_row(world, admin_user, it_board):
    p, m = world
    assert memos.save(admin_user, it_board, "day", D, "임시 휴무", no_work=True, confirm=True) == 2
    assert not Commute.objects.filter(date=D).exists() and not DutyAssignment.objects.filter(date=D).exists()
    logs = list(ChangeLog.objects.order_by("id").values_list("period_id", "date", "cell", "before__name", "after", "by"))
    assert logs == [(p.pk, D, "dawn", "가", None, admin_user.pk), (p.pk, D, "normal", "나", None, admin_user.pk),
                    (p.pk, D, "slot0", "가", None, admin_user.pk)]
    assert Commute.objects.filter(date=date(2026, 11, 19)).count() == 1  # 다른 날은 그대로
    assert not ChangeLog.objects.filter(notified=True).exists()  # 변경 알림은 작업자가 평소처럼 보낸다


def test_no_work_clears_unpublished_rows_without_log(world, admin_user, it_board, make_member):
    q = Period.objects.create(board=it_board, name="q", start_date=D, end_date=D, status=S.COLLECTING)
    Commute.objects.create(period=q, date=D, member=world[1]["다"], shift="night")
    assert memos.affected(it_board, D) == 3
    memos.save(admin_user, it_board, "day", D, "", no_work=True, confirm=True)
    assert not Commute.objects.filter(period=q).exists()
    assert not ChangeLog.objects.filter(period=q).exists()


def test_no_work_does_not_touch_other_board(world, admin_user, it_board):
    other = Board.objects.create(code="ops", name="운영팀")
    o = Period.objects.create(board=other, name="o", start_date=D, end_date=D, status=S.PUBLISHED)
    Commute.objects.create(period=o, date=D, member=world[1]["다"], shift="normal")
    memos.save(admin_user, it_board, "day", D, "", no_work=True, confirm=True)
    assert Commute.objects.filter(period=o).exists()


def test_past_day_no_work_by_admin(world, admin_user, it_board, fixed_today):
    fixed_today(date(2026, 11, 20))
    memos.save(admin_user, it_board, "day", D, "", no_work=True, confirm=True)
    assert Memo.objects.get().no_work


def test_turning_no_work_off_leaves_empty_day(world, admin_user, it_board):
    memos.save(admin_user, it_board, "day", D, "휴무", no_work=True, confirm=True)
    memos.save(admin_user, it_board, "day", D, "휴무 취소", no_work=False)
    assert not Memo.objects.get().no_work and not Commute.objects.filter(date=D).exists()


# ── 읽기 ──

def test_no_work_days_and_for_range(admin_user, it_board):
    memos.save(admin_user, it_board, "day", D, "휴무", no_work=True)
    memos.save(admin_user, it_board, "day", date(2026, 11, 19), "행사")
    memos.save(admin_user, it_board, "week", D, "주 메모")
    memos.save(admin_user, it_board, "month", date(2026, 12, 3), "12월")
    memos.save(admin_user, it_board, "day", date(2026, 11, 13), "범위 밖")
    assert memos.no_work_days(it_board, date(2026, 11, 16), date(2026, 11, 20)) == {D}
    r = memos.for_range(it_board, date(2026, 11, 16), date(2026, 12, 4))
    assert set(r["day"]) == {D, date(2026, 11, 19)}
    assert set(r["week"]) == {date(2026, 11, 16)}
    assert set(r["month"]) == {date(2026, 12, 1)}
    memos.save(admin_user, it_board, "month", date(2026, 11, 5), "11월")
    assert set(memos.for_range(it_board, date(2026, 11, 2), date(2026, 11, 6))["month"]) == {date(2026, 11, 1)}
