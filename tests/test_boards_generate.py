"""근무표 단위 관제 생성·출근표 취합·통계(설계 6.2·6.3·8.3). 이름은 모두 가상."""
from datetime import date, time

import pytest

from duty.csv_io import CsvInvalid
from duty.errors import DutyError
from duty.models import Board, BoardShift, Commute, Department, DutyAssignment, Period, User
from duty.services import boards, collect
from duty.services.generate import run_generation
from duty.services.stats import member_stats, period_duty_counts
from duty.shifts import slot_defs
from tests.it_defs import IT_SLOTS

S = Period.Status
NOV9, NOV13 = date(2026, 11, 9), date(2026, 11, 13)
CSV = 'date,새벽,정상,석식교대,야간\n2026-11-09,가,"나,다",,\n'


@pytest.fixture
def ops(it_board):
    """가짜 두 번째 근무표 '운영팀'(관리 그룹은 Board.save 가 만든다)과 그 부서 하나. 장중관제 정의 없음."""
    board = Board.objects.create(code="ops", name="운영팀", input_mode="direct")
    BoardShift.objects.create(board=board, key="normal", name="주간", start=time(9), end=time(18))
    return board, Department.objects.create(code="OPS", name="운영", shifts="normal", board=board)


def ops_member(dept, name="운영가", type="직원"):
    return User.objects.create_user(f"OPS{User.objects.count() + 1:03d}", password=None, name=name,
                                    department=dept, part="", type=type)


def ops_period(board, member, status=S.CLOSED):
    p = Period.objects.create(board=board, name="운영회차", start_date=NOV9, end_date=NOV13, status=status)
    for x in p.dates():
        Commute.objects.create(period=p, date=x, member=member, shift="normal")
    return p


# ── 생성(6.3) ──

@pytest.fixture
def closed_period(make_member, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=NOV9, end_date=NOV13, status=S.CLOSED)
    for i in range(7):
        n, dn = make_member(f"N{i}", dept="MEMS"), make_member(f"D{i}", dept="TMCH")
        for x in p.dates():
            Commute.objects.create(period=p, date=x, member=n, shift="normal")
            Commute.objects.create(period=p, date=x, member=dn, shift="dinner")
    for code in ["MD", "UI"]:
        m = make_member(f"직{code}", dept=code, type="직원")
        for x in p.dates():
            Commute.objects.create(period=p, date=x, member=m, shift="normal")
    return p


def test_it_slot_definitions_are_generator_list(it_board):
    # 같은 씨앗이면 관제 결과가 그대로: 생성기에 넘기는 IT 칸 목록이 옛 CONTROL_SLOTS 와 같다
    assert [(x.name, x.eligible_shifts, x.eligible_types) for x in slot_defs(boards.defs(it_board))] == IT_SLOTS


def test_candidates_come_from_period_board_only(closed_period, ops):
    outsider = ops_member(ops[1], "운영개발", type="개발자")
    for x in closed_period.dates():
        Commute.objects.create(period=closed_period, date=x, member=outsider, shift="normal")
    out = run_generation(closed_period, seed=5)
    assert outsider.username not in out.counts
    assert not DutyAssignment.objects.filter(member=outsider).exists()


def test_board_without_slots_generates_nothing(ops):
    board, dept = ops
    p = ops_period(board, ops_member(dept))
    out = run_generation(p, seed=1)
    p.refresh_from_db()
    assert p.status == S.GENERATED and (out.counts, out.reached) == ({}, True)
    assert not DutyAssignment.objects.filter(period=p).exists()


def test_slot_keys_and_types_come_from_definitions(ops):
    board, dept = ops
    BoardShift.objects.create(board=board, key="slot3", name="점검", start=time(10), end=time(11),
                              eligible_shifts=["normal"], eligible_types=["직원"])
    m = ops_member(dept)
    p = ops_period(board, m)
    run_generation(p, seed=1)
    assert set(DutyAssignment.objects.filter(period=p).values_list("cell", "member")) == {("slot3", m.pk)}
    assert DutyAssignment.objects.filter(period=p).count() == 5
