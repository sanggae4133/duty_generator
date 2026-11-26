from datetime import date

import pytest

from duty.csv_io import CsvInvalid, export_commute_csv, parse_commute_csv, parse_date, split_names
from duty.shifts import by_key
from tests.it_defs import IT_DEFS


def _names(keys: list[str]) -> dict[str, str]:
    """IT 정의의 {키: 이름}(CSV 열 이름)."""
    return {k: by_key(IT_DEFS)[k].name for k in keys}


KEYS = _names(["dawn", "normal", "dinner", "night"])
SAMPLE = (
    'date,day,"새벽\n(06:30~15:30)",정상,석식교대,야간\n'
    '2026-11-09,월,"가, 나",다,라,마\n'
    "2026/11/10,화,가,,,\n"
    ",,,,,\n"
)


def test_parse_basic():
    t = parse_commute_csv(SAMPLE.encode("utf-8-sig"), KEYS)
    assert t[date(2026, 11, 9)]["dawn"] == ["가", "나"]
    assert t[date(2026, 11, 9)]["night"] == ["마"]
    assert t[date(2026, 11, 10)]["normal"] == []
    assert len(t) == 2  # 빈 행 무시


def test_binary_file_is_csv_invalid():
    with pytest.raises(CsvInvalid):
        parse_commute_csv(b"\xff\xfe\x00\x81\xff", KEYS)


def test_parse_cp949():
    t = parse_commute_csv(SAMPLE.encode("cp949"), KEYS)
    assert t[date(2026, 11, 9)]["normal"] == ["다"]


def test_date_formats():
    assert parse_date("2026-11-09") == date(2026, 11, 9)
    assert parse_date("2026/11/9") == date(2026, 11, 9)
    assert parse_date("2026. 11. 9.") == date(2026, 11, 9)
    assert parse_date("2026-02-30") is None
    assert parse_date("abc") is None


def test_split_names():
    assert split_names("가,\n나 , ") == ["가", "나"]
    assert split_names("") == []


def test_missing_column():
    raw = "date,정상,석식교대,야간\n2026-11-09,가,,\n".encode()
    with pytest.raises(CsvInvalid) as e:
        parse_commute_csv(raw, KEYS)
    [err] = e.value.errors
    assert (err.row, err.column) == (0, "첫 줄(열 제목)") and "필요한 열이 없습니다: 새벽." in err.reason


def test_ui_without_dawn_column_is_fine():
    raw = "date,정상,석식교대,야간\n2026-11-09,가,,\n".encode()
    t = parse_commute_csv(raw, _names(["normal", "dinner", "night"]))
    assert t[date(2026, 11, 9)]["normal"] == ["가"]


def test_bad_and_duplicate_dates():
    raw = "date,새벽,정상,석식교대,야간\nabc,,,,\n2026-11-09,,,,\n2026-11-09,,,,\n".encode()
    with pytest.raises(CsvInvalid) as e:
        parse_commute_csv(raw, KEYS)
    assert [x.row for x in e.value.errors] == [2, 4]


def test_export_roundtrip():
    table = {date(2026, 11, 9): {"dawn": ["가", "나"], "normal": ["다"]}}
    raw = export_commute_csv([date(2026, 11, 9), date(2026, 11, 10)], KEYS, table)
    assert raw.startswith("﻿".encode())
    back = parse_commute_csv(raw, KEYS)
    assert back[date(2026, 11, 9)] == {"dawn": ["가", "나"], "normal": ["다"], "dinner": [], "night": []}
    assert back[date(2026, 11, 10)] == {"dawn": [], "normal": [], "dinner": [], "night": []}


def test_columns_follow_given_names():
    names = {"dawn": "이른조", "night": "늦은조"}
    raw = export_commute_csv([date(2026, 11, 9)], names, {date(2026, 11, 9): {"dawn": ["가"]}})
    assert raw.decode("utf-8-sig").splitlines()[0] == "date,day,이른조,늦은조"
    assert parse_commute_csv(raw, names)[date(2026, 11, 9)] == {"dawn": ["가"], "night": []}


TIMES = {"a": "07:30", "b": "09:00", "c": "11:00"}  # 시간을 이름으로 쓴 근무 정의(시장운영실)


def test_time_header_without_leading_zero():
    """엑셀은 CSV 를 저장할 때 07:30 을 7:30 으로 바꾼다. 같은 열로 본다."""
    t = parse_commute_csv("date,day,7:30,9:00,11:00\n2026-11-30,월,가,나,다\n".encode(), TIMES)
    assert t[date(2026, 11, 30)] == {"a": ["가"], "b": ["나"], "c": ["다"]}


def test_missing_column_error_explains_what_to_fix():
    with pytest.raises(CsvInvalid) as e:
        parse_commute_csv("date,day,새벽,9:00\n".encode(), TIMES)
    [err] = e.value.errors
    assert err.row == 0 and err.column == "첫 줄(열 제목)"
    assert "07:30, 11:00" in err.reason  # 없는 열
    assert "date, day, 새벽, 9:00" in err.reason  # 파일에 있는 열
    assert "date, day, 07:30, 09:00, 11:00" in err.reason  # 있어야 하는 첫 줄
