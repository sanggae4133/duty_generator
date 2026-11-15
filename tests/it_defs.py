"""테스트 전용 IT 근무 정의. 1단계 전 duty/shifts.py 상수(COMMUTE_SHIFTS·CONTROL_SLOTS·SHIFT_TIMES)와 같은 값."""
from datetime import time

from duty.shifts import Def, slot_defs

_BOTH = ("normal", "dinner")
_DEV = ("개발자",)
_SLOTS = [  # (시작, 끝, 자격 근무조)
    ("08:30", "09:30", ("normal",)),
    ("09:30", "10:30", _BOTH),
    ("10:30", "11:30", _BOTH),
    ("11:30", "12:30", _BOTH),
    ("12:30", "13:30", _BOTH),
    ("13:30", "14:30", _BOTH),
    ("14:30", "15:30", _BOTH),
    ("15:30", "16:30", _BOTH),
    ("16:30", "17:00", _BOTH),
    ("17:00", "18:00", ("dinner",)),
]

IT_DEFS: list[Def] = [  # KEYS 순. active 는 기본값 True(IT 정의는 모두 켜짐, boards.defs 결과와 같다)
    Def("dawn", "새벽", time(6, 30), time(15, 30), default_alarm=True),
    Def("normal", "정상", time(8, 0), time(17, 0)),
    Def("dinner", "석식교대", time(9, 0), time(18, 0), default_alarm=True),
    *[Def(f"slot{i}", f"{a}~{b}", time.fromisoformat(a), time.fromisoformat(b), eligible_shifts=e, eligible_types=_DEV)
      for i, (a, b, e) in enumerate(_SLOTS)],
    Def("night", "야간", time(13, 30), time(21, 30), default_alarm=True),
]

IT_SLOTS = [(x.name, x.eligible_shifts, x.eligible_types) for x in slot_defs(IT_DEFS)]  # generator 칸 목록(옛 CONTROL_SLOTS 의 값·순서 + 개발자)
