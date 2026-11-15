"""휴장일 표·자동 채우기와 부르는 곳(설계 5절). 이름은 모두 가상."""
from datetime import date

import pytest
from django.db import IntegrityError, transaction

from duty.errors import DutyError
from duty.models import Commute, Holiday, Period
from duty.services import holidays, periods
from duty.services.generate import run_generation

TODAY = date(2026, 11, 16)


def _years():
    return sorted({d.year for d in Holiday.objects.values_list("date", flat=True)})


def test_source_must_be_known(db):
    with pytest.raises(IntegrityError), transaction.atomic():
        Holiday.objects.create(date=date(2026, 11, 20), name="가짜", source="other")


def test_date_is_unique(db):
    Holiday.objects.create(date=date(2026, 11, 20), name="가짜")
    with pytest.raises(IntegrityError), transaction.atomic():
        Holiday.objects.create(date=date(2026, 11, 20), name="또")


def test_new_period_skips_holidays_by_default(it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 12, 7), end_date=date(2026, 12, 11))
    assert p.skip_holidays is True


def test_sync_without_periods_fills_this_and_next_year(db):
    added = holidays.sync(TODAY)
    assert _years() == [2026, 2027] and added == Holiday.objects.count()
    h = Holiday.objects.get(date=date(2026, 12, 31))
    assert h.name == "연말 휴장" and h.source == "auto" and h.active
    assert Holiday.objects.get(date=date(2027, 1, 1)).source == "auto"


def test_sync_range_follows_oldest_and_latest_period(it_board):
    Period.objects.create(board=it_board, name="옛", start_date=date(2024, 12, 30), end_date=date(2025, 1, 3))
    Period.objects.create(board=it_board, name="먼", start_date=date(2028, 3, 6), end_date=date(2028, 3, 10))
    holidays.sync(TODAY)
    assert _years() == [2024, 2025, 2026, 2027, 2028]


def test_sync_is_idempotent_and_keeps_existing_rows(db):
    Holiday.objects.create(date=date(2026, 12, 25), name="직접 고친 이름", source="manual", active=False)
    Holiday.objects.create(date=date(2026, 11, 20), name="임시 휴장")
    first = holidays.sync(TODAY)
    assert holidays.sync(TODAY) == 0 and Holiday.objects.count() == first + 2
    xmas = Holiday.objects.get(date=date(2026, 12, 25))
    assert (xmas.name, xmas.source, xmas.active) == ("직접 고친 이름", "manual", False)


def test_sync_does_not_delete_dates_gone_from_library(db):
    Holiday.objects.create(date=date(2026, 11, 18), name="옛 자동", source="auto")
    holidays.sync(TODAY)
    assert Holiday.objects.filter(date=date(2026, 11, 18)).exists()


def test_closed_returns_active_only_in_range(db):
    Holiday.objects.create(date=date(2026, 12, 24), name="꺼짐", active=False)
    Holiday.objects.create(date=date(2026, 12, 25), name="성탄")
    Holiday.objects.create(date=date(2027, 1, 1), name="신정")
    assert holidays.closed(date(2026, 12, 21), date(2026, 12, 31)) == {date(2026, 12, 25): "성탄"}


def test_save_draft_syncs_after_saving_so_its_year_is_covered(it_board, fixed_today):
    fixed_today(TODAY)
    periods.save_draft(Period(board=it_board, name="먼", start_date=date(2029, 1, 8), end_date=date(2029, 1, 12)))
    assert _years() == [2026, 2027, 2028, 2029]


def test_editing_dates_syncs(it_board, fixed_today):
    fixed_today(TODAY)
    p = periods.save_draft(Period(board=it_board, name="p", start_date=date(2026, 12, 7), end_date=date(2026, 12, 11)))
    p.end_date = date(2028, 1, 7)
    periods.save_draft(p)
    assert 2028 in _years()


def test_generation_syncs(make_member, it_board, fixed_today):
    fixed_today(TODAY)
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 12, 7), end_date=date(2026, 12, 7),
                              status=Period.Status.CLOSED)
    crew = [(make_member(f"정{i}", dept="MEMS"), "normal") for i in range(5)]  # 관제 10칸을 채울 개발자 10명
    crew += [(make_member(f"석{i}", dept="TMCH"), "dinner") for i in range(5)]
    crew += [(make_member("엠", dept="MD", type="직원"), "normal"), (make_member("유", dept="UI", type="직원"), "normal")]
    for m, shift in crew:
        Commute.objects.create(period=p, date=p.start_date, member=m, shift=shift)
    run_generation(p, seed=1)
    assert _years() == [2026, 2027]


def test_failed_save_draft_adds_nothing(it_board, fixed_today):
    fixed_today(TODAY)
    with pytest.raises(DutyError):
        periods.save_draft(Period(board=it_board, name="주말", start_date=date(2026, 11, 21), end_date=date(2026, 11, 22)))
    assert not Holiday.objects.exists()
