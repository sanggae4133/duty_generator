"""근무조와 장중관제 시간대 정의. 바뀔 일이 드물어 코드 상수로 둔다."""

from datetime import date, time, timedelta

COMMUTE_SHIFTS: dict[str, str] = {  # 순서 = 화면 표시 순서
    "dawn": "새벽",
    "normal": "정상",
    "dinner": "석식교대",
    "night": "야간",
}

_BOTH = ("normal", "dinner")
CONTROL_SLOTS: list[tuple[str, tuple[str, ...]]] = [  # (라벨, 자격 출근조)
    ("08:30~09:30", ("normal",)),
    ("09:30~10:30", _BOTH),
    ("10:30~11:30", _BOTH),
    ("11:30~12:30", _BOTH),
    ("12:30~13:30", _BOTH),
    ("13:30~14:30", _BOTH),
    ("14:30~15:30", _BOTH),
    ("15:30~16:30", _BOTH),
    ("16:30~17:00", _BOTH),
    ("17:00~18:00", ("dinner",)),
]

SHIFT_TIMES: dict[str, tuple[str, str]] = {  # 9시=석식교대, 저녁=야간
    "dawn": ("06:30", "15:30"),
    "normal": ("08:00", "17:00"),
    "dinner": ("09:00", "18:00"),
    "night": ("13:30", "21:30"),
}

DEVELOPER = "개발자"
STAFF = "직원"
TARGET_SPREAD = 2
MAX_SWAP_ITERATIONS = 10000
DAY_LABELS = "월화수목금토일"


def slot_cell(i: int) -> str:
    return f"slot{i}"


def is_slot_cell(cell: str) -> bool:
    return cell.startswith("slot")


def slot_index(cell: str) -> int:
    return int(cell[4:])


CELLS: list[str] = ["dawn", "normal", "dinner", *[slot_cell(i) for i in range(len(CONTROL_SLOTS))], "night"]


def cell_label(cell: str) -> str:
    return CONTROL_SLOTS[slot_index(cell)][0] if is_slot_cell(cell) else COMMUTE_SHIFTS[cell]




def _span(cell: str) -> tuple[str, str]:
    if is_slot_cell(cell):
        a, b = CONTROL_SLOTS[slot_index(cell)][0].split("~")
        return a, b
    return SHIFT_TIMES[cell]


def cell_start(cell: str) -> time:
    return time.fromisoformat(_span(cell)[0])


def cell_end(cell: str) -> time:
    return time.fromisoformat(_span(cell)[1])


def cells_of(keys: list[str]) -> list[str]:
    """스케줄 키(dawn..night, slots) → 칸 키. 빈 목록 = 전부. CELLS 순서."""
    if not keys:
        return list(CELLS)
    return [c for c in CELLS if (is_slot_cell(c) and "slots" in keys) or c in keys]


def weekdays(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out
