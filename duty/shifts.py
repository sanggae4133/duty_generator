"""칸 키와 근무 정의(Def) 헬퍼. ORM 없음.

칸 키(KEYS)는 고정 목록이고 키 글자가 성격을 정한다: dawn·normal·dinner·night = 근무조, slot* = 장중관제,
lunch = 점심당번.
이름·시각·자격은 근무표마다 DB(BoardShift)에 있고, 아래 헬퍼는 그 정의 목록(defs)을 인자로 받는다(기본값 없음).
"""

from dataclasses import dataclass
from datetime import date, time, timedelta

SHIFT_KEYS = ("dawn", "normal", "dinner", "night")  # 근무조 키(한 사람 하루 하나)
SLOT_KEYS = tuple(f"slot{i}" for i in range(10))  # 장중관제 칸 키(자동 생성, 칸당 1명)
# 점심당번: 혼자인 당번 칸. 그 근무표의 가장 이른 근무조에 근무로 친 사람이 기본, 인원 제한 없음.
# 정의에는 시각이 없고(화면은 "점심당번"만) 알림·캘린더 시각은 사람 부서의 Department.lunch_start/end
LUNCH = "lunch"
DUTY_KEYS = (*SLOT_KEYS, LUNCH)  # 당번 칸 키(DutyAssignment.cell)
# 근무표가 쓸 수 있는 키 전부. 순서 = 알림·캘린더 칸 순회 순서(바꾸면 알림 hash 가 달라져 다시 나간다). lunch 는 2단계에 끝에 붙였다
KEYS: list[str] = ["dawn", "normal", "dinner", *SLOT_KEYS, "night", LUNCH]
SLOT_GROUP, SLOT_GROUP_NAME, SLOT_GROUP_SHORT = "slots", "장중관제", "관제"  # 장중관제 묶음 키·이름·짧은 이름
SHIFT, SLOT, SOLO = "shift", "slot", "solo"  # 키의 성격: 근무조 / 묶음 당번 칸(장중관제) / 혼자인 당번 칸(점심당번)

DEVELOPER = "개발자"
STAFF = "직원"
DAY_LABELS = "월화수목금토일"
REASONS = ("휴가", "출장", "교육")  # 사유: 붙으면 그날 근무로 치지 않는다(설계 2절). 표·CSV 에는 "이름(휴가)"


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


def is_slot_cell(cell: str) -> bool:
    return cell.startswith("slot")


def kind(key: str) -> str:
    """키의 성격(SHIFT·SLOT·SOLO). 같은 성격끼리만 맞교환하고, 알림 문구 틀도 이것으로 고른다."""
    return SLOT if is_slot_cell(key) else SOLO if key == LUNCH else SHIFT


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


def josa(word: str, pair: str) -> str:
    """word 뒤 조사(pair = "은/는"·"을/를"·"으로/로")를 받침으로 고른다(바꿀 수 있는 이름 뒤 글, 설계 5.4).
    한글로 끝나지 않으면 '은(는)'·'(으)로' 꼴."""
    a, b = pair.split("/")
    c = word[-1:]
    if not "가" <= c <= "힣":
        return f"({a[0]}){b}" if a == "으로" else f"{a}({b})"
    jong = (ord(c) - ord("가")) % 28
    if a == "으로":
        return b if jong in (0, 8) else a  # 받침 없음·ㄹ 받침은 '로'
    return a if jong else b


def gen_help(defs: list[Def]) -> dict | None:
    """회차 화면 [생성 방식] 상자의 숫자·자격 문장(설계 6.1): 켜진 관제 정의에서 만든다. 관제가 없으면 None.
    가장 많은 칸이 쓰는 자격 근무조는 '나머지 칸', 다른 칸은 시작 시각으로 적는다."""
    slots = slot_defs(defs)
    if not slots:
        return None
    order = [x.key for x in shift_defs(defs)]
    names = {x.key: x.name for x in defs}

    def joined(keys):
        return "·".join(names[k] for k in order if k in keys)

    sets = [frozenset(x.eligible_shifts) for x in slots]
    common = max(sets, key=sets.count)  # 같은 수면 먼저 나온 것
    rest = joined(common) + (" 둘 다" if len(common) == 2 else " 모두" if len(common) > 2 else "만")
    rule = [f"{x.start:%H:%M} 칸은 {joined(s)}" for x, s in zip(slots, sets) if s != common]
    rule.append(f"{'나머지 칸' if rule else '모든 칸'}은 {rest} 됩니다.")
    if len({frozenset(x.eligible_types) for x in slots}) == 1:
        types = "·".join(slots[0].eligible_types)  # 비면 구분 없이 누구나
        who = types or "사람"
    else:  # 칸마다 유형이 다르거나 일부만 누구나: 합치면 틀린 문장이 된다
        types, who = "칸마다 정한 구분", "사람"
    return {"count": len(slots), "start": min(x.start for x in slots), "end": max(x.end for x in slots), "types": types,
            "who": who, "whom": who + josa(who, "을/를"), "rule": ", ".join(rule)}


def day_spans(days) -> str:
    """날짜들을 이어진 평일끼리 묶어 '11/16~11/20, 11/24' 꼴로(금 → 월도 이어진 것으로). 긴 빈 날 목록을 줄인다."""
    runs: list[list[date]] = []
    for d in sorted(days):
        if runs and d == runs[-1][1] + timedelta(days=3 if runs[-1][1].weekday() == 4 else 1):
            runs[-1][1] = d
        else:
            runs.append([d, d])
    return ", ".join(f"{a.month}/{a.day}" + (f"~{b.month}/{b.day}" if b != a else "") for a, b in runs)


def lunch_defs(defs: list[Def]) -> list[Def]:
    """점심당번 정의(없으면 빈 목록)."""
    return [x for x in defs if x.key == LUNCH]


def display_order(defs: list[Def]) -> list[Def]:
    """화면 순서: 근무조(시작 시각 순) → 점심당번 → 장중관제(키 순)."""
    return shift_defs(defs) + lunch_defs(defs) + slot_defs(defs)


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


def two_week_rotation(base: dict[date, dict[str, str]], names: list[str], keys: list[str]) -> dict[str, str]:
    """[2주 전 기준으로 채우기](설계 6.2): 사람마다 이번 주에 넣을 근무조 {이름: 키}.
    keys = [이른, 가운데, 늦은] 근무조(시작 시각 순), base = 2주 전 그 주의 {날짜: {이름: 근무조}}(근무로 친 날만).
    대표 근무조 = 가장 많이 나온 근무조, 같으면 그 주에 먼저 나온 것(한 사람은 하루 한 근무조라 첫 날이 겹치지 않아
    설계의 세 번째 기준 '시작 시각'까지 갈 일이 없다). 이른 → 늦은, 늦은 → 이른, 나머지·2주 전 근무가 없던 사람 → 가운데."""
    early, mid, late = keys
    out = {}
    for name in names:
        seen = [day[name] for _, day in sorted(base.items()) if name in day]
        top = max(map(seen.count, seen), default=0)
        rep = next((k for k in seen if seen.count(k) == top), None)
        out[name] = {early: late, late: early}.get(rep, mid)
    return out
