"""근무조와 장중관제 시간대 정의. 바뀔 일이 드물어 코드 상수로 둔다."""

from dataclasses import dataclass
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


SHIFT_KEYS = ("dawn", "normal", "dinner", "night")  # 근무조 키(한 사람 하루 하나)
SLOT_KEYS = tuple(slot_cell(i) for i in range(10))  # 장중관제 칸 키(자동 생성, 칸당 1명)
# 근무표가 쓸 수 있는 키 전부. 순서 = 알림·캘린더 칸 순회 순서(바꾸면 알림 hash 가 달라져 다시 나간다)
KEYS: list[str] = ["dawn", "normal", "dinner", *SLOT_KEYS, "night"]
CELLS = KEYS  # 1단계 동안 남기는 옛 이름


@dataclass(frozen=True)
class Def:
    """근무 정의 하나(BoardShift 를 ORM 없이 다루는 값)."""
    key: str
    name: str
    start: time | None
    end: time | None
    eligible_shifts: tuple[str, ...] = ()
    eligible_types: tuple[str, ...] = ()
    default_alarm: bool = False
    active: bool = True  # 꺼진 정의: 새 입력·생성·선택지에서 빠지고(boards.active_defs) 이름 찾기에는 남는다(boards.defs)


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
