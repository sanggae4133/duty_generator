from datetime import date, time

from duty.shifts import (
    KEYS, Def, by_key, cell_end, cell_label, cell_start, cells_of, display_order, is_slot_cell,
    ordered, shift_defs, slot_defs, slot_index, weekdays,
)
from tests.it_defs import IT_DEFS


def test_cells_order_matches_combined_view():
    cells = [d.key for d in ordered(IT_DEFS)]
    assert cells[:3] == ["dawn", "normal", "dinner"]
    assert cells[3:13] == [f"slot{i}" for i in range(10)]
    assert cells[-1] == "night"


def test_cell_labels_roundtrip():
    assert cell_label(IT_DEFS, "slot0") == "08:30~09:30"
    assert cell_label(IT_DEFS, "slot9") == "17:00~18:00"
    assert cell_label(IT_DEFS, "night") == "야간"


def test_slot_helpers():
    assert is_slot_cell("slot3") and not is_slot_cell("dawn")
    assert slot_index("slot7") == 7


def test_weekdays_skip_weekend():
    # 2026-11-06 금, 11-09 월
    assert weekdays(date(2026, 11, 6), date(2026, 11, 10)) == [
        date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 10)
    ]


def test_cell_times():
    assert cell_start(IT_DEFS, "dawn") == time(6, 30) and cell_end(IT_DEFS, "dawn") == time(15, 30)
    assert cell_start(IT_DEFS, "dinner") == time(9, 0) and cell_start(IT_DEFS, "night") == time(13, 30)
    assert cell_start(IT_DEFS, "slot0") == time(8, 30) and cell_end(IT_DEFS, "slot8") == time(17, 0)


def test_cells_of():
    assert cells_of(IT_DEFS, []) == KEYS
    assert cells_of(IT_DEFS, ["night", "dawn"]) == ["dawn", "night"]
    assert cells_of(IT_DEFS, ["slots"]) == [f"slot{i}" for i in range(10)]


# ---- 정의 목록 헬퍼 ----

SLOTS = [f"slot{i}" for i in range(10)]


def test_display_helpers_with_it_defs():
    assert [d.key for d in shift_defs(IT_DEFS)] == ["dawn", "normal", "dinner", "night"]
    assert [d.key for d in slot_defs(IT_DEFS)] == SLOTS
    assert [d.key for d in display_order(IT_DEFS)] == ["dawn", "normal", "dinner", "night", *SLOTS]
    assert by_key(IT_DEFS)["dinner"].name == "석식교대"


def test_helpers_read_only_given_defs():
    # 근무조 3개, 키 순서와 시작 시각 순서가 다른 근무표(관제 없음)
    defs = [Def("dawn", "가운데", time(9), time(18)), Def("night", "늦은", time(11), time(20)),
            Def("dinner", "이른", time(7, 30), time(16, 30))]
    assert [d.name for d in shift_defs(defs)] == ["이른", "가운데", "늦은"]
    assert [d.key for d in display_order(defs)] == ["dinner", "dawn", "night"]
    assert [d.key for d in ordered(defs)] == ["dawn", "dinner", "night"]
    assert slot_defs(defs) == []
    assert cells_of(defs, []) == ["dawn", "dinner", "night"]
    assert cells_of(defs, ["slots"]) == []
    assert cell_label(defs, "dinner") == "이른" and cell_start(defs, "night") == time(11)
