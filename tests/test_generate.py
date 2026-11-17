from datetime import date

import pytest

from duty.errors import DutyError
from duty.generator import GenerationError
from duty.models import Commute, DutyAssignment, Period
from duty.services.generate import run_generation

S = Period.Status


@pytest.fixture
def closed_period(make_member, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13), status=S.CLOSED)
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
    assert DutyAssignment.objects.filter(period=closed_period).count() == 5 * 10
    assert not DutyAssignment.objects.filter(period=closed_period, member__type="직원").exists()
    assert out.reached


def test_regenerate_replaces(closed_period):
    run_generation(closed_period, seed=1)
    run_generation(closed_period, seed=2)
    assert DutyAssignment.objects.filter(period=closed_period).count() == 50


def test_missing_department_dates_only_warn(closed_period):
    """빈 평일은 IT 도 막지 않고 경고만(근무표 통합 2단계). 다른 부서 사람이 있는 날은 관제도 채운다."""
    Commute.objects.filter(period=closed_period, member__department="UI", date=date(2026, 11, 13)).delete()
    out = run_generation(closed_period, seed=5)
    assert out.warnings[0] == "출근표가 비어 있는 날이 있습니다: UI 1일(11/13). 그날 그 부서는 근무자가 없습니다."
    assert DutyAssignment.objects.filter(period=closed_period, date=date(2026, 11, 13)).count() == 10


def test_wrong_status(closed_period):
    closed_period.status = S.COLLECTING
    closed_period.save()
    with pytest.raises(DutyError, match="'마감'인 회차만 장중관제 생성할 수 있습니다"):
        run_generation(closed_period)


def test_no_candidates_raises_generation_error(closed_period):
    Commute.objects.filter(period=closed_period, date=date(2026, 11, 9), shift="dinner").update(shift="night")
    with pytest.raises(GenerationError):
        run_generation(closed_period, seed=1)
    closed_period.refresh_from_db()
    assert closed_period.status == S.CLOSED
