from datetime import date

import pytest

from duty.generator import GenerationError, SlotFailure, generate_control_duty
from duty.shifts import CONTROL_SLOTS, weekdays

DATES = weekdays(date(2026, 11, 9), date(2026, 11, 27))  # 15일
NORMAL = [f"N{i}" for i in range(7)]
DINNER = [f"D{i}" for i in range(7)]
DEVS = set(NORMAL) | set(DINNER) | {"X"}


def commutes():
    return {d: {"normal": set(NORMAL), "dinner": set(DINNER), "dawn": {"X"}} for d in DATES}


def test_every_slot_is_eligible_and_unique_per_day():
    c = commutes()
    out = generate_control_duty(DATES, c, DEVS, seed=1)
    assert list(out.assignments) == DATES
    for d, picked in out.assignments.items():
        assert len(picked) == 10 and len(set(picked)) == 10
        for i, m in enumerate(picked):
            allowed = set().union(*(c[d][s] for s in CONTROL_SLOTS[i][1]))
            assert m in allowed


def test_never_eligible_developer_is_not_in_pool():
    out = generate_control_duty(DATES, commutes(), DEVS, seed=1)
    assert "X" not in out.counts  # 새벽 출근 개발자는 풀에서 제외 (기존 JS 버그 수정)


def test_non_developers_are_excluded():
    out = generate_control_duty(DATES, commutes(), DEVS - {"N0"}, seed=1)
    assert "N0" not in out.counts
    assert all("N0" not in p for p in out.assignments.values())


def test_same_seed_same_result():
    a = generate_control_duty(DATES, commutes(), DEVS, seed=7)
    b = generate_control_duty(DATES, commutes(), DEVS, seed=7)
    assert a.assignments == b.assignments


def test_spread_reaches_target():
    out = generate_control_duty(DATES, commutes(), DEVS, seed=3)
    assert out.reached and out.spread <= 2
    assert sum(out.counts.values()) == len(DATES) * 10


def test_failure_lists_slots_without_candidates():
    c = commutes()
    c[DATES[0]]["normal"] = set()
    with pytest.raises(GenerationError) as e:
        generate_control_duty(DATES, c, DEVS, seed=1)
    assert SlotFailure(DATES[0], 0, 0) in e.value.failures
