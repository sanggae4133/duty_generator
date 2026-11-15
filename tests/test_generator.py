from datetime import date

import pytest

from duty.generator import GenerationError, SlotFailure, generate_control_duty
from duty.shifts import TARGET_SPREAD, weekdays
from tests.it_defs import IT_SLOTS

DATES = weekdays(date(2026, 11, 9), date(2026, 11, 27))  # 15일
NORMAL = [f"N{i}" for i in range(7)]
DINNER = [f"D{i}" for i in range(7)]
DEVS = set(NORMAL) | set(DINNER) | {"X"}


def commutes():
    return {d: {"normal": set(NORMAL), "dinner": set(DINNER), "dawn": {"X"}} for d in DATES}


def test_every_slot_is_eligible_and_unique_per_day():
    c = commutes()
    out = generate_control_duty(DATES, c, {"개발자": DEVS}, seed=1, slots=IT_SLOTS)
    assert list(out.assignments) == DATES
    for d, picked in out.assignments.items():
        assert len(picked) == 10 and len(set(picked)) == 10
        for i, m in enumerate(picked):
            allowed = set().union(*(c[d][s] for s in IT_SLOTS[i][1]))
            assert m in allowed


def test_never_eligible_developer_is_not_in_pool():
    out = generate_control_duty(DATES, commutes(), {"개발자": DEVS}, seed=1, slots=IT_SLOTS)
    assert "X" not in out.counts  # 새벽 출근 개발자는 풀에서 제외 (기존 JS 버그 수정)


def test_non_developers_are_excluded():
    out = generate_control_duty(DATES, commutes(), {"개발자": DEVS - {"N0"}}, seed=1, slots=IT_SLOTS)
    assert "N0" not in out.counts
    assert all("N0" not in p for p in out.assignments.values())


def test_same_seed_same_result():
    a = generate_control_duty(DATES, commutes(), {"개발자": DEVS}, seed=7, slots=IT_SLOTS)
    b = generate_control_duty(DATES, commutes(), {"개발자": DEVS}, seed=7, slots=IT_SLOTS)
    assert a.assignments == b.assignments


def test_spread_reaches_target():
    out = generate_control_duty(DATES, commutes(), {"개발자": DEVS}, seed=3, slots=IT_SLOTS)
    assert out.reached and out.spread <= 2
    assert sum(out.counts.values()) == len(DATES) * 10


def test_failure_lists_slots_without_candidates():
    c = commutes()
    c[DATES[0]]["normal"] = set()
    with pytest.raises(GenerationError) as e:
        generate_control_duty(DATES, c, {"개발자": DEVS}, seed=1, slots=IT_SLOTS)
    assert SlotFailure(DATES[0], 0, 0) in e.value.failures


def test_failure_reports_eligible_count_when_all_used_elsewhere():
    d = DATES[0]
    c = {d: {"normal": {"N0"}}}
    with pytest.raises(GenerationError) as e:
        generate_control_duty([d], c, {"개발자": {"N0"}}, seed=1, slots=IT_SLOTS)
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
        out = generate_control_duty([d], c, {"개발자": normal | dinner}, seed=seed, slots=IT_SLOTS)
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
    out = generate_control_duty(SWAP_DATES, SWAP_COMMUTES, {"개발자": SWAP_DEVS}, seed=38, slots=IT_SLOTS)
    assert out.reached and out.spread <= TARGET_SPREAD
    for d, picked in out.assignments.items():
        assert len(picked) == 10 and len(set(picked)) == 10
        for i, m in enumerate(picked):
            allowed = set().union(*(SWAP_COMMUTES[d][s] for s in IT_SLOTS[i][1]))
            assert m in allowed


def test_it_slots_are_old_control_slots():
    both = ("normal", "dinner")
    middle = ["09:30~10:30", "10:30~11:30", "11:30~12:30", "12:30~13:30",
              "13:30~14:30", "14:30~15:30", "15:30~16:30", "16:30~17:00"]
    dev = ("개발자",)
    assert IT_SLOTS == [("08:30~09:30", ("normal",), dev), *[(x, both, dev) for x in middle],
                        ("17:00~18:00", ("dinner",), dev)]


def test_slots_argument_decides_cells_and_is_required():
    slots = [("A", ("normal",), ("개발자",)), ("B", ("dinner",), ("개발자",))]
    out = generate_control_duty(DATES, commutes(), {"개발자": DEVS}, seed=1, slots=slots)
    for picked in out.assignments.values():
        assert len(picked) == 2 and picked[0] in NORMAL and picked[1] in DINNER
    with pytest.raises(TypeError):
        generate_control_duty(DATES, commutes(), {"개발자": DEVS}, seed=1)  # 기본값 없음


def test_each_slot_filters_its_own_types():
    staff = {"S0", "S1"}
    slots = [("개발", ("normal",), ("개발자",)), ("직원", ("normal",), ("직원",)), ("전원", ("dinner",), ())]
    c = {d: {"normal": set(NORMAL) | staff, "dinner": set(DINNER)} for d in DATES}
    out = generate_control_duty(DATES, c, {"개발자": set(NORMAL), "직원": staff | set(DINNER)}, seed=1, slots=slots)
    for picked in out.assignments.values():
        assert picked[0] in NORMAL and picked[1] in staff and picked[2] in DINNER  # 칸마다 그 칸의 유형만, 빈 튜플 = 전원
