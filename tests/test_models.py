from datetime import date

import pytest
from django.db import IntegrityError

from duty.models import Commute, DutyAssignment, Period


def test_department_shift_keys(depts):
    assert depts["UI"].shift_keys() == ["normal", "dinner", "night"]


def test_period_dates_are_weekdays():
    p = Period(name="p", start_date=date(2026, 11, 6), end_date=date(2026, 11, 10))
    assert p.dates() == [date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 10)]


def test_period_default_status_is_draft(it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
    assert p.status == Period.Status.DRAFT


def test_one_commute_per_member_per_day(make_member, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
    m = make_member("가")
    Commute.objects.create(period=p, date=date(2026, 11, 9), member=m, shift="dawn")
    with pytest.raises(IntegrityError):
        Commute.objects.create(period=p, date=date(2026, 11, 9), member=m, shift="night")


def test_one_member_per_duty_slot(make_member, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
    a, b = make_member("가"), make_member("나")
    DutyAssignment.objects.create(period=p, date=date(2026, 11, 9), cell="slot0", member=a)
    with pytest.raises(IntegrityError):
        DutyAssignment.objects.create(period=p, date=date(2026, 11, 9), cell="slot0", member=b)


def test_member_may_hold_several_duty_slots_per_day(make_member, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
    a = make_member("가")
    DutyAssignment.objects.create(period=p, date=date(2026, 11, 9), cell="slot0", member=a)
    DutyAssignment.objects.create(period=p, date=date(2026, 11, 9), cell="slot1", member=a)


@pytest.mark.parametrize("bad", ["가>나", "가,나", "+가", "가\n나"])
def test_member_name_rejects_label_syntax(make_member, bad):
    from django.core.exceptions import ValidationError

    m = make_member("정상")
    m.name = bad
    with pytest.raises(ValidationError, match="쓸 수 없고"):
        m.full_clean(exclude=["department", "user"])
