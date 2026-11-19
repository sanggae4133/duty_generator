"""직접 입력 근무표의 회차 흐름(설계 6.1·6.3): 입력 중 → 확정 → 배포됨. 이름은 모두 가상."""
from datetime import date, time

import pytest

from duty.errors import DutyError
from duty.models import Board, BoardShift, Commute, Department, DutyAssignment, Period, PeriodEvent, User
from duty.services import collect, periods
from duty.services.generate import run_generation
from tests.it_defs import OPS_STEPS

S = Period.Status
MON, FRI = date(2026, 11, 16), date(2026, 11, 20)


@pytest.fixture
def ops(it_board):
    """가짜 직접 입력 근무표 '운영팀': 근무조 셋(이른·가운데·늦은) + 점심당번, 부서 하나."""
    board = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
    for key, name, h in (("dawn", "이른", 7), ("normal", "가운데", 9), ("dinner", "늦은", 11)):
        BoardShift.objects.create(board=board, key=key, name=name, start=time(h, 30), end=time(h + 9, 30))
    BoardShift.objects.create(board=board, key="lunch", name="점심당번")
    dept = Department.objects.create(code="OPS", name="운영", shifts="dawn,normal,dinner", board=board)
    return board, dept


def ops_member(dept, name):
    return User.objects.create_user(f"OPS{User.objects.count() + 1:03d}", password=None, name=name,
                                    department=dept, part="", type="직원")


def new_period(board, start=MON, end=FRI):
    return periods.save_draft(Period(board=board, name="운영 11월", start_date=start, end_date=end))


def test_new_direct_period_starts_in_input(ops, admin_user):
    p = periods.save_draft(Period(board=ops[0], name="운영 11월", start_date=MON, end_date=FRI), by=admin_user)
    assert p.status == S.COLLECTING and p.status_label == "입력 중"
    ev = PeriodEvent.objects.get(period=p)
    assert (ev.from_status, ev.to_status, ev.by) == ("", S.COLLECTING, admin_user)


def test_new_collect_period_still_draft(it_board):
    p = new_period(it_board)
    assert p.status == S.DRAFT and p.status_label == "작성 중"


def test_direct_dates_editable_while_input(ops):
    board, dept = ops
    p = new_period(board)
    m = ops_member(dept, "가상가")
    for x in p.dates():
        Commute.objects.create(period=p, date=x, member=m, shift="dawn")
    p.end_date = date(2026, 11, 18)
    periods.save_draft(p)
    assert sorted(Commute.objects.filter(period=p).values_list("date", flat=True)) == [MON, date(2026, 11, 17), date(2026, 11, 18)]


def test_direct_dates_locked_after_confirm(ops):
    p = new_period(ops[0])
    Period.objects.filter(pk=p.pk).update(status=S.GENERATED)
    p.end_date = date(2026, 11, 18)
    with pytest.raises(DutyError, match="기간은 '입력 중' 단계에서만 고칠 수 있습니다"):
        periods.save_draft(p)


def test_collect_dates_still_draft_only(it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=MON, end_date=FRI, status=S.COLLECTING)
    with pytest.raises(DutyError, match="기간은 '작성 중' 단계에서만 고칠 수 있습니다"):
        periods.save_draft(p)


def test_confirm_fills_lunch_and_warns_empty_days(ops, admin_user):
    board, dept = ops
    p = new_period(board)
    a, b = ops_member(dept, "가상가"), ops_member(dept, "가상나")
    for x in p.dates()[:4]:  # 금요일은 비워 둔다
        Commute.objects.create(period=p, date=x, member=a, shift="dawn")
        Commute.objects.create(period=p, date=x, member=b, shift="dinner")
    out = run_generation(p, by=admin_user)
    p.refresh_from_db()
    assert p.status == S.GENERATED and p.status_label == "확정"
    assert out.warnings[0] == "출근표가 비어 있는 날이 있습니다: 운영 1일(11/20). 그날 그 부서는 근무자가 없습니다."
    assert set(DutyAssignment.objects.filter(period=p).values_list("cell", "member")) == {("lunch", a.pk)}
    assert PeriodEvent.objects.filter(period=p).last().to_status == S.GENERATED


def test_confirm_without_empty_days_has_no_warning(ops):
    board, dept = ops
    p = new_period(board)
    a = ops_member(dept, "가상가")
    for x in p.dates():
        Commute.objects.create(period=p, date=x, member=a, shift="dawn")
    assert run_generation(p).warnings == []


@pytest.mark.parametrize("status", [S.DRAFT, S.CLOSED, S.PUBLISHED])
def test_confirm_only_from_input_or_confirmed(ops, status):
    p = Period.objects.create(board=ops[0], name="p", start_date=MON, end_date=FRI, status=status)
    with pytest.raises(DutyError, match="'입력 중'인 회차만 확정할 수 있습니다"):
        run_generation(p)


def test_collect_generation_still_needs_closed(it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=MON, end_date=FRI, status=S.COLLECTING)
    with pytest.raises(DutyError, match="'마감'인 회차만 장중관제 생성할 수 있습니다"):
        run_generation(p)


def test_cancel_confirm_goes_back_to_input(ops, admin_user):
    board, dept = ops
    p = new_period(board)
    a = ops_member(dept, "가상가")
    for x in p.dates():
        Commute.objects.create(period=p, date=x, member=a, shift="dawn")
    run_generation(p)
    periods.move(p, S.COLLECTING, by=admin_user)
    p.refresh_from_db()
    assert p.status == S.COLLECTING and not DutyAssignment.objects.filter(period=p).exists()
    assert Commute.objects.filter(period=p).count() == 5  # 출근표는 그대로


@pytest.mark.parametrize("to", [S.DRAFT, S.CLOSED])
def test_direct_moves_only_to_input(ops, to):
    p = Period.objects.create(board=ops[0], name="p", start_date=MON, end_date=FRI, status=S.GENERATED)
    with pytest.raises(DutyError, match=r"'입력 중'\(으\)로만 옮길 수 있습니다"):
        periods.move(p, to)


def test_input_closed_message_uses_direct_name(ops, admin_user):
    board, dept = ops
    board.admin_group.user_set.add(admin_user)
    p = Period.objects.create(board=board, name="p", start_date=MON, end_date=FRI, status=S.GENERATED)
    with pytest.raises(DutyError, match="입력 중인 회차가 아닙니다"):
        collect.apply_table(admin_user, p, dept, {})


def test_stale_object_cannot_restore_old_status(ops, admin_user):
    """확정 상태로 읽어 둔 객체를 다른 곳에서 확정 취소한 뒤 저장해도 상태·seed 를 되돌리지 않는다."""
    board, dept = ops
    p = new_period(board)
    fill_all = ops_member(dept, "가상가")
    for x in p.dates():
        Commute.objects.create(period=p, date=x, member=fill_all, shift="dawn")
    run_generation(p)
    stale = Period.objects.get(pk=p.pk)  # GENERATED, seed 있음
    periods.move(Period.objects.get(pk=p.pk), S.COLLECTING, by=admin_user)
    stale.name, stale.end_date = "새 이름", date(2026, 11, 18)
    periods.save_draft(stale)
    fresh = Period.objects.get(pk=p.pk)
    assert (fresh.status, fresh.seed, fresh.generated_at) == (S.COLLECTING, None, None)
    assert (fresh.name, fresh.end_date) == ("새 이름", date(2026, 11, 18))


def test_confirm_with_slot_def_and_empty_weekday(ops):
    """관제 정의가 있는 직접 입력 근무표도 빈 평일은 경고만 하고 확정한다(설계 6.3)."""
    board, dept = ops
    BoardShift.objects.create(board=board, key="slot3", name="점검", start=time(10), end=time(11),
                              eligible_shifts=["dawn"], eligible_types=["직원"])
    p = new_period(board)
    a = ops_member(dept, "가상가")
    for x in p.dates()[:4]:
        Commute.objects.create(period=p, date=x, member=a, shift="dawn")
    out = run_generation(p, seed=1)
    p.refresh_from_db()
    assert p.status == S.GENERATED and "운영 1일(11/20)" in out.warnings[0]
    assert sorted(DutyAssignment.objects.filter(period=p, cell="slot3").values_list("date", flat=True)) == p.dates()[:4]


def test_confirm_with_slot_def_and_all_weekdays_empty(ops):
    """평일이 모두 비어도 관제 정의가 있는 직접 입력 회차는 경고만 하고 확정한다(관제 칸은 없음)."""
    board, dept = ops
    BoardShift.objects.create(board=board, key="slot3", name="점검", start=time(10), end=time(11),
                              eligible_shifts=["dawn"], eligible_types=["직원"])
    p = new_period(board)
    out = run_generation(p, seed=1)
    p.refresh_from_db()
    assert p.status == S.GENERATED and out.warnings
    assert not DutyAssignment.objects.filter(period=p).exists()
