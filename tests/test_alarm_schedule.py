from datetime import date, datetime

import pytest
from duty.alarms.schedule import bizdays_back, send_at

MON = date(2026, 11, 16)

def test_bizdays_back():
    assert bizdays_back(MON, 1) == date(2026, 11, 13)      # 금
    assert bizdays_back(date(2026, 11, 18), 2) == MON       # 수 → 월
    assert bizdays_back(MON, 6) == date(2026, 11, 6)

def test_send_at():
    start = datetime(2026, 11, 16, 6, 30)
    assert send_at("before_start", 120, 0, MON, start) == datetime(2026, 11, 16, 4, 30)
    assert send_at("before_start", 1500, 0, MON, start) == datetime(2026, 11, 15, 5, 30)
    assert send_at("days", 1, 18 * 60, MON, start) == datetime(2026, 11, 15, 18, 0)   # 일요일도 셈
    assert send_at("days", 0, 5 * 60 + 15, MON, start) == datetime(2026, 11, 16, 5, 15)
    assert send_at("bizdays", 1, 17 * 60, MON, start) == datetime(2026, 11, 13, 17, 0)


def test_invalid_inputs_raise():
    start = datetime(2026, 11, 16, 6, 30)
    with pytest.raises(ValueError):
        bizdays_back(MON, -1)
    with pytest.raises(ValueError):
        send_at("weird", 1, 0, MON, start)


def test_bizdays_skip_closed_days():
    """영업일 기준은 휴장일을 영업일에서 뺀다(설계 5·8.1). 휴장일 집합은 인자로(순수 모듈)."""
    fri, thu = date(2026, 11, 13), date(2026, 11, 12)
    assert bizdays_back(MON, 1, {fri}) == thu
    assert bizdays_back(MON, 2, {fri, date(2026, 11, 14)}) == date(2026, 11, 11)  # 주말 휴장일은 영향 없음
    start = datetime(2026, 11, 16, 6, 30)
    assert send_at("bizdays", 1, 17 * 60, MON, start, {fri}) == datetime(2026, 11, 12, 17, 0)
    assert send_at("days", 1, 18 * 60, MON, start, {date(2026, 11, 15)}) == datetime(2026, 11, 15, 18, 0)  # 날 기준은 그대로
