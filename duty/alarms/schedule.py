"""알림 발송 시각 계산. ORM 없음, Asia/Seoul naive datetime."""
from datetime import date, datetime, time, timedelta

def bizdays_back(d: date, n: int) -> date:
    while n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d

def send_at(timing: str, offset: int, at_minute: int, day: date, start: datetime) -> datetime:
    if timing == "before_start":
        return start - timedelta(minutes=offset)
    base = day - timedelta(days=offset) if timing == "days" else bizdays_back(day, offset)
    return datetime.combine(base, time(at_minute // 60, at_minute % 60))
