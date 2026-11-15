"""칸 키와 근무 정의(Def) 헬퍼. ORM 없음.

칸 키(KEYS)는 고정 목록이고 키 글자가 성격을 정한다: dawn·normal·dinner·night = 근무조, slot* = 장중관제.
이름·시각·자격은 근무표마다 DB(BoardShift)에 있고, 아래 헬퍼는 그 정의 목록(defs)을 인자로 받는다(기본값 없음).
"""

from dataclasses import dataclass
from datetime import date, time, timedelta

SHIFT_KEYS = ("dawn", "normal", "dinner", "night")  # 근무조 키(한 사람 하루 하나)
SLOT_KEYS = tuple(f"slot{i}" for i in range(10))  # 장중관제 칸 키(자동 생성, 칸당 1명)
# 근무표가 쓸 수 있는 키 전부. 순서 = 알림·캘린더 칸 순회 순서(바꾸면 알림 hash 가 달라져 다시 나간다)
KEYS: list[str] = ["dawn", "normal", "dinner", *SLOT_KEYS, "night"]
CELLS = KEYS  # 1단계 동안 남기는 옛 이름
SLOT_GROUP, SLOT_GROUP_NAME, SLOT_GROUP_SHORT = "slots", "장중관제", "관제"  # 장중관제 묶음 키·이름·짧은 이름

DEVELOPER = "개발자"
STAFF = "직원"
TARGET_SPREAD = 2
MAX_SWAP_ITERATIONS = 10000
DAY_LABELS = "월화수목금토일"


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


def slot_cell(i: int) -> str:
    return f"slot{i}"


def is_slot_cell(cell: str) -> bool:
    return cell.startswith("slot")


def slot_index(cell: str) -> int:
    return int(cell[4:])


def by_key(defs: list[Def]) -> dict[str, Def]:
    return {x.key: x for x in defs}


def ordered(defs: list[Def]) -> list[Def]:
    """KEYS 순(알림·캘린더·published_days 순회 순서)."""
    return sorted(defs, key=lambda x: KEYS.index(x.key))


def shift_defs(defs: list[Def]) -> list[Def]:
    """근무조만, 시작 시각 순."""
    return sorted((x for x in defs if x.key in SHIFT_KEYS), key=lambda x: x.start)


def slot_defs(defs: list[Def]) -> list[Def]:
    """장중관제 칸만, 키 순."""
    return ordered([x for x in defs if is_slot_cell(x.key)])


def display_order(defs: list[Def]) -> list[Def]:
    """화면 순서: 근무조(시작 시각 순) → 장중관제(키 순)."""
    return shift_defs(defs) + slot_defs(defs)


def cell_label(defs: list[Def], cell: str) -> str:
    return by_key(defs)[cell].name


def cell_start(defs: list[Def], cell: str) -> time:
    return by_key(defs)[cell].start


def cell_end(defs: list[Def], cell: str) -> time:
    return by_key(defs)[cell].end


def cells_of(defs: list[Def], keys: list[str]) -> list[str]:
    """스케줄 키(근무조 키, "slots") → 칸 키. 빈 목록 = 전부. KEYS 순."""
    cells = [x.key for x in ordered(defs)]
    if not keys:
        return cells
    return [c for c in cells if (is_slot_cell(c) and SLOT_GROUP in keys) or c in keys]


def weekdays(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


# ---- 1단계 이행용 옛 상수. 변경·생성·통계·알림·캘린더 작업(Task 5·7·8)이 근무표 정의를 받게 되면 지운다 ----

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


def _legacy_defs() -> list[Def]:
    t = time.fromisoformat
    out = [Def(k, n, t(SHIFT_TIMES[k][0]), t(SHIFT_TIMES[k][1]), default_alarm=k in ("dawn", "dinner", "night"))
           for k, n in COMMUTE_SHIFTS.items()]
    for i, (label, allowed) in enumerate(CONTROL_SLOTS):
        a, b = label.split("~")
        out.append(Def(slot_cell(i), label, t(a), t(b), eligible_shifts=allowed, eligible_types=(DEVELOPER,)))
    return ordered(out)


LEGACY_DEFS: list[Def] = _legacy_defs()  # IT 정의와 같다(tests/test_shifts.py 가 IT_DEFS 와 비교)
