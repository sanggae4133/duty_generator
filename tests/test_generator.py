from datetime import date

import pytest

from duty.generator import GenerationError, SlotFailure, generate_control_duty
from duty.shifts import CONTROL_SLOTS, TARGET_SPREAD, weekdays

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


def test_failure_reports_eligible_count_when_all_used_elsewhere():
    d = DATES[0]
    c = {d: {"normal": {"N0"}}}
    with pytest.raises(GenerationError) as e:
        generate_control_duty([d], c, {"N0"}, seed=1)
    # slot 0은 N0이 배정되고, slot 1..8은 자격자 1명(N0)이 전부 다른 칸에 쓰여 실패
    for i in range(1, 9):
        assert SlotFailure(d, i, 1) in e.value.failures
    assert SlotFailure(d, 9, 0) in e.value.failures


def test_most_constrained_slot_first_keeps_dinner_slot_fillable():
    d = DATES[0]
    normal = {f"N{i}" for i in range(8)}
    dinner = {"D0", "D1"}
    c = {d: {"normal": normal, "dinner": dinner}}
    for seed in range(20):
        out = generate_control_duty([d], c, normal | dinner, seed=seed)
        assert out.assignments[d][9] in dinner


# greedy 단독이면 spread 3, swap 후 2가 되는 층 (seed 38, 11명, 5일)
SWAP_DATES = [date(2026, 11, k) for k in range(9, 14)]
SWAP_DEVS = {f"P{i}" for i in range(11)}
SWAP_COMMUTES = {
    SWAP_DATES[0]: {
        "normal": {"P0", "P1", "P2", "P3", "P4", "P5", "P7", "P8", "P10"},
        "dinner": {"P0", "P1", "P2", "P3", "P5", "P6", "P7", "P8", "P9", "P10"},
    },
    SWAP_DATES[1]: {
        "normal": {"P0", "P2", "P3", "P5", "P7", "P8", "P10"},
        "dinner": {"P0", "P1", "P2", "P3", "P4", "P5", "P7", "P8", "P9", "P10"},
    },
    SWAP_DATES[2]: {
        "normal": {"P0", "P2", "P3", "P5", "P7", "P8", "P9"},
        "dinner": {"P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10"},
    },
    SWAP_DATES[3]: {
        "normal": {"P0", "P1", "P2", "P3", "P4", "P5", "P7", "P8", "P9", "P10"},
        "dinner": {"P1", "P2", "P3", "P4", "P5", "P7", "P8", "P9"},
    },
    SWAP_DATES[4]: {
        "normal": {"P0", "P1", "P2", "P3", "P5", "P6", "P8", "P10"},
        "dinner": {"P0", "P1", "P2", "P3", "P4", "P5", "P7", "P8", "P10"},
    },
}


def test_swap_phase_brings_spread_within_target():
    out = generate_control_duty(SWAP_DATES, SWAP_COMMUTES, SWAP_DEVS, seed=38)
    assert out.reached and out.spread <= TARGET_SPREAD
    for d, picked in out.assignments.items():
        assert len(picked) == 10 and len(set(picked)) == 10
        for i, m in enumerate(picked):
            allowed = set().union(*(SWAP_COMMUTES[d][s] for s in CONTROL_SLOTS[i][1]))
            assert m in allowed
