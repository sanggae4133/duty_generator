from datetime import date

import pytest

from duty.errors import DutyError
from duty.generator import GenerationError
from duty.models import Commute, ControlDuty, Period
from duty.services.generate import run_generation

S = Period.Status


@pytest.fixture
def closed_period(make_member):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13), status=S.CLOSED)
    normal = [make_member(f"N{i}", dept="MEMS") for i in range(7)]
    dinner = [make_member(f"D{i}", dept="TMCH") for i in range(7)]
    md = make_member("엠", dept="MD", type="직원")
    ui = make_member("유", dept="UI", type="직원")
    for d in p.dates():
        for m in normal + [md, ui]:
            Commute.objects.create(period=p, date=d, member=m, shift="normal")
        for m in dinner:
            Commute.objects.create(period=p, date=d, member=m, shift="dinner")
    return p


def test_generation_writes_duties(closed_period):
    out = run_generation(closed_period, seed=5)
    closed_period.refresh_from_db()
    assert closed_period.status == S.GENERATED and closed_period.seed == 5
    assert ControlDuty.objects.filter(period=closed_period).count() == 5 * 10
    assert not ControlDuty.objects.filter(period=closed_period, member__type="직원").exists()
    assert out.reached


def test_regenerate_replaces(closed_period):
    run_generation(closed_period, seed=1)
    run_generation(closed_period, seed=2)
    assert ControlDuty.objects.filter(period=closed_period).count() == 50


def test_missing_department_dates_block_generation(closed_period):
    Commute.objects.filter(period=closed_period, member__department="UI", date=date(2026, 11, 13)).delete()
    with pytest.raises(DutyError) as e:
        run_generation(closed_period)
    assert "UI" in str(e.value)


def test_wrong_status(closed_period):
    closed_period.status = S.COLLECTING
    closed_period.save()
    with pytest.raises(DutyError):
        run_generation(closed_period)


def test_no_candidates_raises_generation_error(closed_period):
    Commute.objects.filter(period=closed_period, date=date(2026, 11, 9), shift="dinner").update(shift="night")
    with pytest.raises(GenerationError):
        run_generation(closed_period, seed=1)
    closed_period.refresh_from_db()
    assert closed_period.status == S.CLOSED
