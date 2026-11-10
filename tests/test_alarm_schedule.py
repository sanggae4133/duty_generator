from datetime import date, datetime
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
