from datetime import date

import pytest

from duty.errors import DutyError
from duty.models import Commute, ControlDuty, Period
from duty.services import periods

S = Period.Status


def d(m, day):
    return date(2026, m, day)


def test_unpublished_periods_cannot_overlap(db):
    periods.save_draft(Period(name="a", start_date=d(11, 9), end_date=d(11, 30)))
    with pytest.raises(DutyError):
        periods.save_draft(Period(name="b", start_date=d(11, 20), end_date=d(12, 31)))


def test_overlap_with_published_is_allowed(db):
    Period.objects.create(name="a", start_date=d(11, 2), end_date=d(11, 30), status=S.PUBLISHED)
    p = periods.save_draft(Period(name="b", start_date=d(11, 16), end_date=d(12, 31)))
    assert p.pk


def test_start_after_end_rejected(db):
    with pytest.raises(DutyError):
        periods.save_draft(Period(name="a", start_date=d(11, 30), end_date=d(11, 9)))


def test_weekend_only_period_rejected(db):
    with pytest.raises(DutyError):
        periods.save_draft(Period(name="a", start_date=d(11, 14), end_date=d(11, 15)))


def test_dates_editable_only_in_draft(db):
    p = Period.objects.create(name="a", start_date=d(11, 9), end_date=d(11, 30), status=S.COLLECTING)
    p.end_date = d(12, 4)
    with pytest.raises(DutyError):
        periods.save_draft(p)


def test_open_close_and_reopen_deletes_duties(make_member):
    p = Period.objects.create(name="a", start_date=d(11, 9), end_date=d(11, 13))
    periods.open_collecting(p)
    assert p.status == S.COLLECTING
    periods.close_collecting(p)
    assert p.status == S.CLOSED
    p.status, p.seed = S.GENERATED, 1
    p.save()
    ControlDuty.objects.create(period=p, date=d(11, 9), slot=0, member=make_member("가"))
    periods.open_collecting(p)
    assert p.status == S.COLLECTING and p.seed is None
    assert not ControlDuty.objects.filter(period=p).exists()


def test_close_requires_collecting(db):
    p = Period.objects.create(name="a", start_date=d(11, 9), end_date=d(11, 13))
    with pytest.raises(DutyError):
        periods.close_collecting(p)


def test_open_rejected_when_published(db):
    p = Period.objects.create(name="a", start_date=d(11, 9), end_date=d(11, 13), status=S.PUBLISHED)
    with pytest.raises(DutyError):
        periods.open_collecting(p)


def test_missing_dates(make_member):
    p = Period.objects.create(name="a", start_date=d(11, 9), end_date=d(11, 10))
    Commute.objects.create(period=p, date=d(11, 9), member=make_member("가", dept="MEMS"), shift="normal")
    missing = periods.missing_dates(p)
    assert missing["MEMS"] == [d(11, 10)]
    assert missing["UI"] == [d(11, 9), d(11, 10)]
