from datetime import date

from duty.shifts import CELLS, cell_label, is_slot_cell, slot_index, weekdays


def test_cells_order_matches_combined_view():
    assert CELLS[:3] == ["dawn", "normal", "dinner"]
    assert CELLS[3:13] == [f"slot{i}" for i in range(10)]
    assert CELLS[-1] == "night"


def test_cell_labels_roundtrip():
    assert cell_label("slot0") == "08:30~09:30"
    assert cell_label("slot9") == "17:00~18:00"
    assert cell_label("night") == "야간"


def test_slot_helpers():
    assert is_slot_cell("slot3") and not is_slot_cell("dawn")
    assert slot_index("slot7") == 7


def test_weekdays_skip_weekend():
    # 2026-11-06 금, 11-09 월
    assert weekdays(date(2026, 11, 6), date(2026, 11, 10)) == [
        date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 10)
    ]


def test_cell_times():
    from datetime import time
    from duty.shifts import cell_end, cell_start
    assert cell_start("dawn") == time(6, 30) and cell_end("dawn") == time(15, 30)
    assert cell_start("dinner") == time(9, 0) and cell_start("night") == time(13, 30)
    assert cell_start("slot0") == time(8, 30) and cell_end("slot8") == time(17, 0)


def test_cells_of():
    from duty.shifts import CELLS, cells_of
    assert cells_of([]) == CELLS
    assert cells_of(["night", "dawn"]) == ["dawn", "night"]
    assert cells_of(["slots"]) == [f"slot{i}" for i in range(10)]
