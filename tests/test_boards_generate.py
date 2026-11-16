"""근무표 단위 관제 생성·출근표 취합·통계(설계 6.2·6.3·8.3). 이름은 모두 가상."""
from datetime import date, time

import pytest
from django.urls import reverse

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


def ops_period(board, member, status=S.COLLECTING):  # 직접 입력 근무표는 입력 중에서 확정한다(3단계)
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


# ── 출근표 취합(6.2) ──

@pytest.fixture
def collecting(depts, make_member, fixed_today, it_board):
    fixed_today(date(2026, 11, 1))
    p = Period.objects.create(board=it_board, name="p", start_date=NOV9, end_date=NOV13, status=S.COLLECTING)
    mgr = make_member("담당", user=True)
    depts["MEMS"].input_group.user_set.add(mgr)
    for n in ["가", "나", "다"]:
        make_member(n)
    return p, depts["MEMS"], mgr


def test_department_of_other_board_rejected(collecting, ops, make_member):
    p, _, _ = collecting
    board, dept = ops
    ops_admin = make_member("운영관리", user=True)
    board.admin_group.user_set.add(ops_admin)  # 운영팀 부서는 입력할 수 있다
    with pytest.raises(DutyError, match="이 회차의 근무표에 속한 부서가 아닙니다"):
        collect.apply_table(ops_admin, p, dept, {})
    with pytest.raises(DutyError):
        collect.apply_csv(ops_admin, p, dept, "date,주간\n".encode())


@pytest.fixture
def other_admin(collecting, ops, make_member):
    """운영팀 관리자이면서 IT 부서(MEMS) 입력 담당. IT 근무표 관리자는 아니다(is_admin 은 참)."""
    _, dept, _ = collecting
    u = make_member("남관리", user=True)
    ops[0].admin_group.user_set.add(u)
    dept.input_group.user_set.add(u)
    return u


def test_past_dates_need_this_board_admin(collecting, other_admin, fixed_today):
    p, dept, mgr = collecting
    collect.apply_csv(mgr, p, dept, CSV.encode())
    fixed_today(date(2026, 11, 11))
    with pytest.raises(CsvInvalid) as e:
        collect.apply_csv(other_admin, p, dept, "date,새벽,정상,석식교대,야간\n2026-11-09,나,가,,\n".encode())
    assert "지난 날짜" in " / ".join(x.reason for x in e.value.errors)


def test_past_rows_locked_for_other_board_admin(client, collecting, other_admin, fixed_today):
    p, _, _ = collecting
    fixed_today(date(2026, 11, 11))
    client.force_login(other_admin)
    body = client.get(f"/collect/{p.pk}/MEMS/").content.decode()
    assert 'name="c_2026-11-09_normal" rows="2" readonly' in body
    assert 'name="c_2026-11-11_normal" rows="2" ></textarea>' in body


def test_other_board_department_page_and_csv_are_404(client, collecting, ops, make_member):
    p, _, _ = collecting
    board, dept = ops
    u = make_member("운영관리", user=True)
    board.admin_group.user_set.add(u)  # 운영팀 부서는 입력할 수 있다
    client.force_login(u)
    assert client.get(f"/collect/{p.pk}/OPS/").status_code == 404  # IT 회차에 운영팀 부서 표는 없다
    assert client.get(f"/collect/{p.pk}/OPS/export.csv").status_code == 404
    with pytest.raises(DutyError, match="이 회차의 근무표에 속한 부서가 아닙니다"):
        collect.export_csv(p, dept)


# ── 통계(8.3) ──

def test_stats_board_without_slots_is_empty(ops):
    board, dept = ops
    p = ops_period(board, ops_member(dept, "운영개발", type="개발자"), status=S.PUBLISHED)
    assert member_stats(board, None, None) == ([], None, None)
    assert period_duty_counts(p) == ([], 0, True)


def test_stats_types_come_from_slot_definitions(ops):
    board, dept = ops
    BoardShift.objects.create(board=board, key="slot0", name="점검", start=time(10), end=time(11),
                              eligible_shifts=["normal"], eligible_types=["직원"])
    a, b = ops_member(dept, "운영가"), ops_member(dept, "운영나")
    p = ops_period(board, a, status=S.PUBLISHED)
    Commute.objects.create(period=p, date=NOV9, member=b, shift="normal")
    DutyAssignment.objects.create(period=p, date=NOV9, cell="slot0", member=a)
    assert {r.name: r.duty for r in member_stats(board, None, None)[0]} == {"운영나": 0, "운영가": 1}
    assert period_duty_counts(p) == ([("운영나", 0), ("운영가", 1)], 1, True)


def test_period_counts_keep_departed_commuter(make_member, it_board):
    """IT 불변(main 과 같다): 자격 출근이 있는 퇴사 개발자는 배정 0회여도 0으로 남는다."""
    p = Period.objects.create(board=it_board, name="p", start_date=NOV9, end_date=NOV13, status=S.PUBLISHED)
    gone = make_member("퇴사개발", active=False)
    Commute.objects.create(period=p, date=NOV9, member=gone, shift="normal")
    assert period_duty_counts(p) == ([("퇴사개발", 0)], 0, True)


def test_stats_empty_eligible_types_means_everyone(ops):
    """관제 칸 자격 구분이 비면(= 전원, 생성기와 같다) 유형을 거르지 않는다."""
    board, dept = ops
    BoardShift.objects.create(board=board, key="slot0", name="점검", start=time(10), end=time(11),
                              eligible_shifts=["normal"], eligible_types=[])
    ops_period(board, ops_member(dept, "운영기타", type="개발자"), status=S.PUBLISHED)
    assert {r.name: r.duty for r in member_stats(board, None, None)[0]} == {"운영기타": 0}


def test_failure_label_skips_inactive_slot(ops, admin_client_ok, admin_user):
    """꺼진 관제 정의가 앞에 있어도 실패 칸 이름은 생성기와 같은 순서(켜진 정의)로 찾는다."""
    board, dept = ops
    board.admin_group.user_set.add(admin_user)
    BoardShift.objects.create(board=board, key="slot0", name="꺼진칸", start=time(10), end=time(11),
                              eligible_shifts=["normal"], eligible_types=["직원"], active=False)
    BoardShift.objects.create(board=board, key="slot3", name="못채울칸", start=time(12), end=time(13),
                              eligible_shifts=["normal"], eligible_types=["없는유형"])
    p = ops_period(board, ops_member(dept))
    html = admin_client_ok.post(reverse("period_action", args=[p.pk, "generate"])).content.decode()
    assert "못채울칸" in html and "꺼진칸" not in html
