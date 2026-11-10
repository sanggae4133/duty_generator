"""알림 발송 시각 계산. ORM 없음, Asia/Seoul naive datetime."""
from datetime import date, datetime, time, timedelta

from ..shifts import cell_label, cell_start, cells_of

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


def _topic(word: str) -> str:
    """'새벽·정상' + 은/는 (마지막 글자 받침 기준)."""
    c = word[-1]
    return word + ("는" if "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 == 0 else "은")


def same_day_notice(kind: str, timing: str, offset: int, at_minute: int, shifts: list[str]) -> str | None:
    """당일 발송 규칙에서 발송 시각이 근무 시작 이후라 빠지는 칸 안내. 없으면 None."""
    if timing != "days" or offset != 0:
        return None
    cells = cells_of(shifts)
    starts = {c: cell_start(c).hour * 60 + cell_start(c).minute for c in cells}
    if kind == "report":
        return "현재 선택으로는 보고서가 발송되지 않습니다." if at_minute >= max(starts.values()) else None
    late = [c for c in cells if at_minute >= starts[c]]
    if not late:
        return None
    if len(late) == len(cells):
        return "현재 선택으로는 발송되는 근무가 없습니다."
    return f"{_topic('·'.join(map(cell_label, late)))} 발송 시각이 근무 시작 이후라 제외됩니다."
