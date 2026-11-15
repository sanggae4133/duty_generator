"""휴장일 자동 계산(순수 모듈). 확인 값은 설계 5절(2025~2026)."""
from datetime import date

from duty.market_days import holidays_for


def test_2025_includes_temporary_and_election_days():
    h = holidays_for(2025)
    assert h[date(2025, 1, 27)] == "임시공휴일"
    assert date(2025, 6, 3) in h  # 대통령 선거일
    assert date(2025, 10, 8) in h  # 추석 대체 휴일


def test_2026_includes_labor_day_and_constitution_day():
    h = holidays_for(2026)
    assert date(2026, 5, 1) in h and date(2026, 7, 17) in h
    assert date(2026, 2, 17) in h  # 설날


def test_year_end_is_added_every_year():
    assert holidays_for(2026)[date(2026, 12, 31)] == "연말 휴장"
    assert holidays_for(2031)[date(2031, 12, 31)] == "연말 휴장"


def test_only_that_year_and_no_plain_weekday():
    h = holidays_for(2026)
    assert all(d.year == 2026 for d in h)
    assert date(2026, 11, 16) not in h  # 평범한 월요일
