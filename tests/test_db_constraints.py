"""DB 수준 정합성 제약: 앱을 거치지 않은 쓰기(shell, SQL)도 막는다."""
from datetime import date

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from duty.models import ChangeLog, Commute, ControlDuty, Period, RosterPref, User

D = date(2026, 11, 9)


@pytest.fixture
def period(db):
    return Period.objects.create(name="p", start_date=D, end_date=date(2026, 11, 13))


def _bad(fn):
    with pytest.raises(IntegrityError), transaction.atomic():
        fn()


def test_member_type(depts):
    _bad(lambda: User.objects.create(username="X1", name="가", department=depts["MEMS"], type="외주"))


def test_period_status_and_dates(db):
    _bad(lambda: Period.objects.create(name="p", start_date=D, end_date=D, status="bogus"))
    _bad(lambda: Period.objects.create(name="p", start_date=D, end_date=date(2026, 11, 1)))
    Period.objects.create(name="ok", start_date=D, end_date=D)  # 하루짜리 회차는 허용


def test_commute_shift(period, make_member):
    m = make_member("가")
    _bad(lambda: Commute.objects.create(period=period, date=D, member=m, shift="lunch"))


def test_control_slot_range(period, make_member):
    m = make_member("가")
    _bad(lambda: ControlDuty.objects.create(period=period, date=D, slot=10, member=m))
    ControlDuty.objects.create(period=period, date=D, slot=9, member=m)


def test_changelog_cell_and_nonempty(period, make_member):
    m = make_member("가")
    _bad(lambda: ChangeLog.objects.create(period=period, date=D, cell="slot10", after=m))
    _bad(lambda: ChangeLog.objects.create(period=period, date=D, cell="dawn"))
    ChangeLog.objects.create(period=period, date=D, cell="slot9", before=m)


def test_rosterpref_view(db):
    u = User.objects.create_user("u", password="unused-Pw-123", name="유")
    _bad(lambda: RosterPref.objects.create(user=u, view="year"))


def test_period_with_changelog_cannot_be_deleted(period, make_member):
    ChangeLog.objects.create(period=period, date=D, cell="dawn", after=make_member("가"))
    with pytest.raises(ProtectedError):
        period.delete()
