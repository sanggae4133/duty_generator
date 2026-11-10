from datetime import date

import pytest

from duty.errors import DutyError
from duty.models import ChangeLog, Commute, ControlDuty, Period
from duty.services.publish import preview_publish, publish
from duty.shifts import weekdays

S = Period.Status


def d(m, day):
    return date(2026, m, day)


def make_period(name, start, end, status, member):
    p = Period.objects.create(name=name, start_date=start, end_date=end, status=status)
    for x in weekdays(start, end):
        Commute.objects.create(period=p, date=x, member=member, shift="normal")
        ControlDuty.objects.create(period=p, date=x, slot=0, member=member)
    return p


def dates_of(p):
    return sorted(set(Commute.objects.filter(period=p).values_list("date", flat=True)))


@pytest.fixture
def ab(make_member):
    a = make_period("A", d(11, 2), d(11, 27), S.PUBLISHED, make_member("가"))
    b = make_period("B", d(11, 16), d(12, 11), S.GENERATED, make_member("나"))
    return a, b


def test_publish_overwrites_from_selected_date(ab):
    a, b = ab
    publish(b, d(11, 18))
    b.refresh_from_db()
    assert b.status == S.PUBLISHED and b.overwrite_from == d(11, 18)
    assert dates_of(a)[-1] == d(11, 17)
    assert dates_of(b)[0] == d(11, 18)
    assert not ControlDuty.objects.filter(period=a, date__gte=d(11, 18)).exists()


def test_publish_inside_keeps_tail_of_old(make_member):
    a = make_period("A", d(11, 2), d(11, 27), S.PUBLISHED, make_member("가"))
    b = make_period("B", d(11, 16), d(11, 20), S.GENERATED, make_member("나"))
    publish(b, d(11, 16))
    assert d(11, 23) in dates_of(a) and d(11, 16) not in dates_of(a)


def test_preview_counts_discarded_changes(ab):
    a, b = ab
    m = Commute.objects.filter(period=a).first().member
    ChangeLog.objects.create(period=a, date=d(11, 19), cell="normal", before=m, after=None)
    ChangeLog.objects.create(period=a, date=d(11, 10), cell="normal", before=m, after=None)
    pv = preview_publish(b, d(11, 18))
    assert pv.discarded_changes == 1
    assert pv.periods == ["A"]
    assert (pv.overwrite_from, pv.overwrite_to) == (d(11, 18), d(12, 11))


def test_requires_generated(ab):
    _, b = ab
    b.status = S.CLOSED
    b.save()
    with pytest.raises(DutyError):
        publish(b, d(11, 16))


def test_overwrite_from_must_be_in_period(ab):
    _, b = ab
    with pytest.raises(DutyError):
        publish(b, d(11, 13))
