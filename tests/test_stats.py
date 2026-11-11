from datetime import date

from duty.models import Commute, ControlDuty, Period
from duty.services.stats import member_stats, period_duty_counts

S = Period.Status
D1, D2 = date(2026, 11, 9), date(2026, 11, 10)


def setup_period(make_member, status=S.PUBLISHED):
    p = Period.objects.create(name="p", start_date=D1, end_date=D2, status=status)
    a, b = make_member("가"), make_member("나")
    make_member("직원", type="직원")
    Commute.objects.create(period=p, date=D1, member=a, shift="dawn")
    Commute.objects.create(period=p, date=D2, member=a, shift="night")
    ControlDuty.objects.create(period=p, date=D1, slot=0, member=b)
    ControlDuty.objects.create(period=p, date=D2, slot=0, member=b)
    ControlDuty.objects.create(period=p, date=D2, slot=1, member=a)
    return p


def test_member_stats(make_member):
    setup_period(make_member)
    rows, duty, total = member_stats(None, None)
    by = {r.name: r for r in rows}
    assert set(by) == {"가", "나"}  # 직원 제외
    assert (by["가"].duty, by["가"].dawn, by["가"].night, by["가"].total) == (1, 1, 1, 3)
    assert (by["나"].duty, by["나"].total) == (2, 2)
    assert duty.spread == 1 and duty.mean == 1.5
    assert total.spread == 1


def test_member_stats_date_range(make_member):
    setup_period(make_member)
    rows, _, _ = member_stats(D2, D2)
    assert {r.name: r.duty for r in rows} == {"가": 1, "나": 1}


def test_period_duty_counts(make_member):
    p = setup_period(make_member, status=S.GENERATED)
    Commute.objects.create(period=p, date=D1, member=make_member("다"), shift="normal")  # 자격 있지만 0회
    counts, spread, reached = period_duty_counts(p)
    assert counts == [("다", 0), ("가", 1), ("나", 2)] and spread == 2 and reached


def test_departed_member_history_stays_in_stats(make_member):
    setup_period(make_member)
    from duty.models import User
    User.objects.filter(name="나").update(is_active=False)
    by = {r.name: r for r in member_stats(None, None)[0]}
    assert by["나"].duty == 2
