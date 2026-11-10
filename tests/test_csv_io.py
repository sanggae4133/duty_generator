from datetime import date

import pytest

from duty.csv_io import CsvInvalid, export_commute_csv, parse_commute_csv, parse_date, split_names

KEYS = ["dawn", "normal", "dinner", "night"]
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
    assert [(x.row, x.column) for x in e.value.errors] == [(1, "새벽")]


def test_ui_without_dawn_column_is_fine():
    raw = "date,정상,석식교대,야간\n2026-11-09,가,,\n".encode()
    t = parse_commute_csv(raw, ["normal", "dinner", "night"])
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
