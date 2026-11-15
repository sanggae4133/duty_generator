"""근무표 단위 회차·배포·배포 취소(설계 6.1)와 회차·이력·통계 화면 권한(설계 7·9절). 이름은 모두 가상."""
from datetime import date, time

import pytest

from duty.errors import DutyError
from duty.models import Board, BoardShift, ChangeLog, Commute, Department, DutyAssignment, Period, User
from duty.services import collect, periods
from duty.services.publish import preview_publish, publish, unpublish, unpublish_info
from duty.shifts import weekdays

S = Period.Status


def d(m, day):
    return date(2026, m, day)


@pytest.fixture
def ops(it_board):
    """가짜 두 번째 근무표 '운영팀'(관리 그룹은 Board.save 가 만든다)과 그 부서 하나."""
    board = Board.objects.create(code="ops", name="운영팀", input_mode="direct")
    BoardShift.objects.create(board=board, key="normal", name="주간", start=time(9), end=time(18))
    return board, Department.objects.create(code="OPS", name="운영", shifts="normal", board=board)


def ops_member(dept, name="운영가"):
    return User.objects.create_user(f"OPS{User.objects.count() + 1:03d}", password=None, name=name,
                                    department=dept, part="", type="직원")


def make_period(board, name, start, end, status, member, slots=True):
    p = Period.objects.create(board=board, name=name, start_date=start, end_date=end, status=status)
    for x in weekdays(start, end):
        Commute.objects.create(period=p, date=x, member=member, shift="normal")
        if slots:
            DutyAssignment.objects.create(period=p, date=x, cell="slot0", member=member)
    return p


def rows(p):
    c = sorted(Commute.objects.filter(period=p).values_list("date", "member_id", "shift"))
    a = sorted(DutyAssignment.objects.filter(period=p).values_list("date", "member_id", "cell"))
    return c, a


@pytest.fixture
def two(it_board, ops, make_member):
    board, dept = ops
    it = make_period(it_board, "IT회차", d(11, 2), d(11, 27), S.GENERATED, make_member("가"))
    op = make_period(board, "운영회차", d(11, 16), d(12, 11), S.GENERATED, ops_member(dept), slots=False)
    return it, op


# ── 배포·미리보기·배포 취소는 근무표 안에서만 ──

def test_publish_other_board_keeps_it_rows(two):
    it, op = two
    publish(it, d(11, 2))
    before = rows(it)
    publish(op, d(11, 18))
    assert rows(it) == before
    op.refresh_from_db()
    assert op.publish_undo and all(r[1] == op.pk for r in op.publish_undo)  # 지운 행은 이 회차의 S 이전 행뿐


def test_preview_ignores_other_board(two):
    it, op = two
    publish(it, d(11, 2))
    m = Commute.objects.filter(period=it).first().member
    ChangeLog.objects.create(period=it, date=d(11, 19), cell="normal", before=m, after=None)
    pv = preview_publish(op, d(11, 18))
    assert (pv.periods, pv.discarded_changes) == ([], 0)


def test_preview_uses_owner_even_without_rows(it_board, make_member):
    a = make_period(it_board, "A", d(11, 2), d(11, 27), S.GENERATED, make_member("가"))
    b = make_period(it_board, "B", d(11, 16), d(12, 11), S.GENERATED, make_member("나"))
    publish(a, d(11, 2))
    m = Commute.objects.filter(period=a).first().member
    Commute.objects.filter(period=a, date=d(11, 19)).delete()  # 그날 배정을 다 비워도 주인은 A
    DutyAssignment.objects.filter(period=a, date=d(11, 19)).delete()
    ChangeLog.objects.create(period=a, date=d(11, 19), cell="normal", before=m, after=None)
    pv = preview_publish(b, d(11, 18))
    assert (pv.periods, pv.discarded_changes) == (["A"], 1)


def test_unpublish_order_is_per_board(two):
    it, op = two
    publish(it, d(11, 2))
    publish(op, d(11, 18))  # 다른 근무표가 나중에 배포됐어도
    assert unpublish_info(it).blocker is None
    unpublish(it)
    it.refresh_from_db()
    op.refresh_from_db()
    assert (it.status, op.status) == (S.GENERATED, S.PUBLISHED)


# ── 겹침·빈 날·입력 현황은 근무표 안에서만 ──

def test_unpublished_overlap_checked_per_board(it_board, ops):
    board, _ = ops
    periods.save_draft(Period(board=it_board, name="IT", start_date=d(11, 9), end_date=d(11, 30)))
    p = periods.save_draft(Period(board=board, name="운영", start_date=d(11, 20), end_date=d(12, 31)))
    assert p.pk
    with pytest.raises(DutyError, match="겹칩니다: 운영"):
        periods.save_draft(Period(board=board, name="운영2", start_date=d(12, 1), end_date=d(12, 4)))


def test_missing_and_progress_only_own_departments(it_board, ops, depts):
    board, dept = ops
    p = Period.objects.create(board=board, name="운영", start_date=d(11, 9), end_date=d(11, 10))
    Commute.objects.create(period=p, date=d(11, 9), member=ops_member(dept), shift="normal")
    assert periods.missing_dates(p) == {"OPS": [d(11, 10)]}
    assert collect.progress(p) == {"OPS": (1, 2)}
    it = Period.objects.create(board=it_board, name="IT", start_date=d(11, 9), end_date=d(11, 9))
    assert "OPS" not in periods.missing_dates(it) and "OPS" not in collect.progress(it)
    assert set(collect.progress(it)) == {"MEMS", "TMCH", "MD", "UI"}
