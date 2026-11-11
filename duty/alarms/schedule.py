"""알림 발송 시각 계산. ORM 없음, Asia/Seoul naive datetime."""
from datetime import date, datetime, time, timedelta

from ..shifts import cell_end, cell_label, cell_start, cells_of, is_slot_cell

def bizdays_back(d: date, n: int) -> date:
    if n < 0:
        raise ValueError("영업일 수는 0 이상이어야 합니다.")
    while n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d

def send_at(timing: str, offset: int, at_minute: int, day: date, start: datetime) -> datetime:
    if timing == "before_start":
        return start - timedelta(minutes=offset)
    if timing == "days":
        base = day - timedelta(days=offset)
    elif timing == "bizdays":
        base = bizdays_back(day, offset)
    else:
        raise ValueError("알 수 없는 발송 시점입니다.")
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
    names = [cell_label(c) for c in late if not is_slot_cell(c)]
    slots = [c for c in late if is_slot_cell(c)]  # 시작 순서라 항상 앞쪽부터 연속
    if slots:
        whole = len(slots) == sum(map(is_slot_cell, cells))
        names.append("장중당번" if whole else
                     f"장중당번 {cell_start(slots[0]):%H:%M}~{cell_end(slots[-1]):%H:%M}")
    return f"{_topic('·'.join(names))} 발송 시각이 근무 시작 이후라 제외됩니다."
