"""알림 발송 시각 계산. ORM 없음, Asia/Seoul naive datetime. 칸 시각·이름은 근무표 정의 목록(defs)에서."""
from datetime import date, datetime, time, timedelta

from ..shifts import LUNCH, SLOT_GROUP_NAME, cell_end, cell_label, cell_start, cells_of, is_slot_cell


def bizdays_back(d: date, n: int, closed=frozenset()) -> date:
    """d 에서 n 영업일 전. 영업일 = 평일 중 closed(휴장일 날짜 집합)에 없는 날."""
    if n < 0:
        raise ValueError("영업일 수는 0 이상이어야 합니다.")
    while n:
        d -= timedelta(days=1)
        if d.weekday() < 5 and d not in closed:
            n -= 1
    return d


def send_at(timing: str, offset: int, at_minute: int, day: date, start: datetime, closed=frozenset()) -> datetime:
    if timing == "before_start":
        return start - timedelta(minutes=offset)
    if timing == "days":
        base = day - timedelta(days=offset)
    elif timing == "bizdays":
        base = bizdays_back(day, offset, closed)
    else:
        raise ValueError("알 수 없는 발송 시점입니다.")
    return datetime.combine(base, time(at_minute // 60, at_minute % 60))


def _topic(word: str) -> str:
    """'새벽·정상' + 은/는 (마지막 글자 받침 기준)."""
    c = word[-1]
    return word + ("는" if "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 == 0 else "은")


def same_day_notice(defs, kind: str, timing: str, offset: int, at_minute: int, shifts: list[str],
                    lunch: time | None = None) -> str | None:
    """당일 발송 규칙에서 발송 시각이 근무 시작 이후라 빠지는 칸 안내. 없으면 None.
    lunch: 개인 규칙 주인 부서의 점심 시각(plan 과 같게: 없으면 점심당번은 그날 끝까지 가므로 빠지지 않는다)."""
    if timing != "days" or offset != 0:
        return None
    # 보고서의 발송 창은 시각 있는 칸으로만 정한다(점심당번 제외). 개인 규칙은 점심당번도 따진다
    cells = [c for c in cells_of(defs, shifts) if c != LUNCH or kind != "report"]
    if not cells:  # 이 근무표에 없는 키만 골랐다(plan 도 조용히 무시한다)
        return None
    starts = {c: (lunch.hour * 60 + lunch.minute if lunch else 24 * 60) if c == LUNCH
              else cell_start(defs, c).hour * 60 + cell_start(defs, c).minute for c in cells}
    if kind == "report":
        return "현재 선택으로는 보고서가 발송되지 않습니다." if at_minute >= max(starts.values()) else None
    late = [c for c in cells if at_minute >= starts[c]]
    if not late:
        return None
    if len(late) == len(cells):
        return "현재 선택으로는 발송되는 근무가 없습니다."
    names = [cell_label(defs, c) for c in late if not is_slot_cell(c)]
    slots = [c for c in late if is_slot_cell(c)]  # 시작 순서라 항상 앞쪽부터 연속
    if slots:
        whole = len(slots) == sum(map(is_slot_cell, cells))
        names.append(SLOT_GROUP_NAME if whole else
                     f"{SLOT_GROUP_NAME} {cell_start(defs, slots[0]):%H:%M}~{cell_end(defs, slots[-1]):%H:%M}")
    return f"{_topic('·'.join(names))} 발송 시각이 근무 시작 이후라 제외됩니다."
