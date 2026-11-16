"""장중관제 당번 생성. 기존 Apps Script(InMarketControlDutyGenerator.gs) 이식.

Phase 1 Greedy: 자격자가 적은 slot부터, 그날 미배정 자격자 중 누적 배정이 가장 적은 사람.
Phase 2 Swap:   최다 배정자의 slot을 최소 배정자(그 slot 자격 있고 그날 미배정)에게 넘김.
차이점: 카운트 풀을 '기간 중 한 번이라도 자격이 있는 개발자'로 한정한다.
기존 JS는 전체 멤버(직원 포함)를 넣어 최소값이 항상 0인 직원이 되어 Phase 2가 즉시 종료되었다.
"""

import random
from dataclasses import dataclass, field
from datetime import date

from .shifts import MAX_SWAP_ITERATIONS, TARGET_SPREAD

Slots = list[tuple[str, tuple[str, ...], tuple[str, ...]]]  # (라벨, 자격 근무조, 자격 유형 — 빈 튜플 = 전원). 인덱스 = 칸 번호, 키 변환은 services/generate.py


@dataclass(frozen=True)
class SlotFailure:
    date: date
    slot: int
    candidates: int


class GenerationError(Exception):
    def __init__(self, failures: list[SlotFailure]):
        super().__init__(f"배정할 수 없는 칸 {len(failures)}개")
        self.failures = failures


@dataclass
class GenerationOutput:
    assignments: dict[date, list[str]]
    counts: dict[str, int]
    spread: int
    reached: bool
    warnings: list[str] = field(default_factory=list)  # 생성은 했지만 알려야 할 것(점심당번을 못 채운 날 등)


def _allowed(members_by_type: dict[str, set[str]], types: tuple[str, ...]) -> set[str]:
    """칸의 자격 유형에 드는 사람. 빈 튜플 = 전원."""
    return set().union(*(members_by_type.get(t, ()) for t in (types or members_by_type)))


def _eligible(day: dict[str, set[str]], allowed: list[set[str]], slots: Slots) -> list[set[str]]:
    # 칸별 자격 = 그 칸 자격 근무조에 출근 ∧ 그 칸 자격 유형
    return [{m for s in shifts for m in day.get(s, ()) if m in ok} for (_, shifts, _), ok in zip(slots, allowed)]


def generate_control_duty(
    dates: list[date],
    commutes: dict[date, dict[str, set[str]]],
    members_by_type: dict[str, set[str]],
    seed: int,
    slots: Slots,
) -> GenerationOutput:
    rng = random.Random(seed)
    allowed = [_allowed(members_by_type, types) for _, _, types in slots]
    eligible = {d: _eligible(commutes.get(d, {}), allowed, slots) for d in dates}
    counts = {m: 0 for m in sorted({m for d in dates for slot in eligible[d] for m in slot})}
    assignments: dict[date, list[str]] = {}
    failures: list[SlotFailure] = []

    for d in dates:
        pools = eligible[d]
        picked: list[str | None] = [None] * len(pools)
        used: set[str] = set()
        for i in sorted(range(len(pools)), key=lambda i: len(pools[i])):
            candidates = sorted(m for m in pools[i] if m not in used)  # set 순서는 해시에 따라 바뀌므로 정렬 후 섞는다
            if not candidates:
                # 그날 이 칸의 전체 자격자 수(다른 칸에 이미 배정된 사람 포함). 0이면 자격자 없음, N>0이면 N명 전원이 다른 칸에 사용됨.
                failures.append(SlotFailure(d, i, len(pools[i])))
                continue
            rng.shuffle(candidates)
            pick = min(candidates, key=lambda m: counts[m])  # 동점이면 섞인 순서의 첫 번째
            picked[i] = pick
            used.add(pick)
            counts[pick] += 1
        assignments[d] = picked

    if failures:
        raise GenerationError(failures)

    _balance(assignments, eligible, counts)
    spread = max(counts.values()) - min(counts.values()) if counts else 0
    return GenerationOutput(assignments, counts, spread, spread <= TARGET_SPREAD)


def _balance(assignments, eligible, counts) -> None:
    if not counts:  # 관제를 만들 날이 없다(직접 입력 회차의 평일이 모두 빔)
        return
    for _ in range(MAX_SWAP_ITERATIONS):
        hi, lo = max(counts.values()), min(counts.values())
        if hi - lo <= TARGET_SPREAD:
            return
        maxs = sorted(m for m, c in counts.items() if c == hi)
        mins = sorted(m for m, c in counts.items() if c == lo)
        if not _swap_once(assignments, eligible, counts, maxs, mins):
            return


def _swap_once(assignments, eligible, counts, maxs, mins) -> bool:
    for hi_m in maxs:
        for lo_m in mins:
            for d, picked in assignments.items():
                if hi_m not in picked or lo_m in picked:
                    continue
                i = picked.index(hi_m)
                if lo_m not in eligible[d][i]:
                    continue
                picked[i] = lo_m
                counts[hi_m] -= 1
                counts[lo_m] += 1
                return True
    return False
