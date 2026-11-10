"""장중관제 당번 생성. 기존 Apps Script(InMarketControlDutyGenerator.gs) 이식.

Phase 1 Greedy: 자격자가 적은 slot부터, 그날 미배정 자격자 중 누적 배정이 가장 적은 사람.
Phase 2 Swap:   최다 배정자의 slot을 최소 배정자(그 slot 자격 있고 그날 미배정)에게 넘김.
차이점: 카운트 풀을 '기간 중 한 번이라도 자격이 있는 개발자'로 한정한다.
기존 JS는 전체 멤버(직원 포함)를 넣어 최소값이 항상 0인 직원이 되어 Phase 2가 즉시 종료되었다.
"""

import random
from dataclasses import dataclass
from datetime import date

from .shifts import CONTROL_SLOTS, MAX_SWAP_ITERATIONS, TARGET_SPREAD


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


def _eligible(day: dict[str, set[str]], developers: set[str]) -> list[set[str]]:
    return [{m for s in shifts for m in day.get(s, ()) if m in developers} for _, shifts in CONTROL_SLOTS]


def generate_control_duty(
    dates: list[date],
    commutes: dict[date, dict[str, set[str]]],
    developers: set[str],
    seed: int,
) -> GenerationOutput:
    rng = random.Random(seed)
    eligible = {d: _eligible(commutes.get(d, {}), developers) for d in dates}
    counts = {m: 0 for m in sorted({m for d in dates for slot in eligible[d] for m in slot})}
    assignments: dict[date, list[str]] = {}
    failures: list[SlotFailure] = []

    for d in dates:
        slots = eligible[d]
        picked: list[str | None] = [None] * len(slots)
        used: set[str] = set()
        for i in sorted(range(len(slots)), key=lambda i: len(slots[i])):
            candidates = sorted(m for m in slots[i] if m not in used)  # set 순서는 해시에 따라 바뀌므로 정렬 후 섞는다
            if not candidates:
                failures.append(SlotFailure(d, i, len(slots[i])))
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
