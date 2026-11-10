from datetime import date

import pytest
from django.db import IntegrityError

from duty.models import Commute, ControlDuty, Period


def test_department_shift_keys(depts):
    assert depts["UI"].shift_keys() == ["normal", "dinner", "night"]


def test_period_dates_are_weekdays():
    p = Period(name="p", start_date=date(2026, 11, 6), end_date=date(2026, 11, 10))
    assert p.dates() == [date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 10)]


def test_period_default_status_is_draft(db):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
    assert p.status == Period.Status.DRAFT


def test_one_commute_per_member_per_day(make_member):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
    m = make_member("가")
    Commute.objects.create(period=p, date=date(2026, 11, 9), member=m, shift="dawn")
    with pytest.raises(IntegrityError):
        Commute.objects.create(period=p, date=date(2026, 11, 9), member=m, shift="night")


def test_one_member_per_duty_slot(make_member):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
    a, b = make_member("가"), make_member("나")
    ControlDuty.objects.create(period=p, date=date(2026, 11, 9), slot=0, member=a)
    with pytest.raises(IntegrityError):
        ControlDuty.objects.create(period=p, date=date(2026, 11, 9), slot=0, member=b)


def test_member_once_per_day_in_duty(make_member):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
    a = make_member("가")
    ControlDuty.objects.create(period=p, date=date(2026, 11, 9), slot=0, member=a)
    with pytest.raises(IntegrityError):
        ControlDuty.objects.create(period=p, date=date(2026, 11, 9), slot=1, member=a)
