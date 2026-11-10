from datetime import date
from io import BytesIO

import openpyxl
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from duty.importer import diff_cell, parse_chains, run_import
from duty.models import ChangeLog, Commute, ControlDuty, Member, Period
from duty.services.roster import api_assignments
from duty.shifts import CELLS, cell_label

D = date(2026, 11, 9)
DEVS = [f"d{i}" for i in range(12)]


def _bytes(wb):
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def maker():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "tb_member"
    ws.append(["id", "department", "name", "part", "type", "is_id_dup", "is_active"])
    ws.append(["MEE01", "매칭엔진실", "직원가", "매칭엔진", "직원", False, True])
    for i, n in enumerate(DEVS):
        ws.append([f"MED{i:02d}", "매칭엔진실", n, "매칭엔진", "개발자", False, True])
    return _bytes(wb)


BASE = {"dawn": "직원가", "normal": ",".join(DEVS[:6]) + "\n" + ",".join(DEVS[6:10]), "dinner": "", "night": "",
        **{f"slot{i}": DEVS[i] for i in range(10)}}


def deploy(final_overrides):
    wb = openpyxl.Workbook()
    a = wb.active
    a.title = "view_all_combine"
    a.append(["날짜", "요일", *[cell_label(c) for c in CELLS]])
    a.append([D, "월", *[BASE[c] for c in CELLS]])
    b = wb.create_sheet("근무표")
    b.append(["검색", "."])
    b.append(["날짜", "요일", *[cell_label(c) for c in CELLS]])
    final = {**BASE, **final_overrides}
    b.append([D, "월", *[final[c] for c in CELLS]])
    return _bytes(wb)


def test_parse_chains_handles_arrows_and_newlines():
    assert parse_chains("가,\n나\n> 다, 라->마") == [["가"], ["나", "다"], ["라", "마"]]


def test_diff_cell_pairs_overwrites_as_replacement():
    final, logs = diff_cell(["가", "나"], "가, 다")
    assert final == ["가", "다"] and logs == [("나", "다")]


def test_diff_cell_many_changes_are_not_guessed():
    final, logs = diff_cell(["가", "나"], "다, 라")
    assert final == ["다", "라"] and logs == [("가", None), ("나", None), (None, "다"), (None, "라")]


def test_diff_cell_chain():
    final, logs = diff_cell(["가"], "가>나>다")
    assert final == ["다"] and logs == [("가", "나"), ("나", "다")]


def test_import_applies_changes(db):
    overrides = {"normal": BASE["normal"].replace("d0", "d0>d10"), "slot0": "d0 -> d11"}
    report = run_import(maker(), deploy(overrides), dry_run=False)
    assert report.errors == []
    p = Period.objects.get(name="시트 이관")
    assert p.status == Period.Status.PUBLISHED
    assert Member.objects.count() == 13
    assert Commute.objects.filter(member__name="d10", shift="normal").exists()
    assert not Commute.objects.filter(member__name="d0").exists()
    assert ControlDuty.objects.get(slot=0).member.name == "d11"
    assert ChangeLog.objects.count() == 2
    rows = api_assignments(None, None)
    assert {"date": "2026-11-09", "shift": "정상", "name": "d10", "replaced": "d0"} in rows


def test_unknown_name_aborts(db):
    report = run_import(maker(), deploy({"dawn": "없는사람"}), dry_run=False)
    assert any("없는사람" in e for e in report.errors)
    assert not Period.objects.exists()


def test_double_commute_aborts(db):
    report = run_import(maker(), deploy({"night": "d1"}), dry_run=False)
    assert any("중복" in e for e in report.errors)
    assert not Period.objects.exists() and not Member.objects.exists()


def test_dry_run_writes_nothing(db):
    report = run_import(maker(), deploy({}), dry_run=True)
    assert report.errors == [] and report.dates == 1 and report.duties == 10
    assert not Member.objects.exists()


def test_missing_column_aborts(db):
    wb = openpyxl.load_workbook(BytesIO(deploy({})))
    wb["근무표"].cell(row=2, column=3).value = "엉뚱한 열"
    report = run_import(maker(), _bytes(wb), dry_run=False)
    assert report.errors and not Member.objects.exists()


def test_second_import_refused(db):
    run_import(maker(), deploy({}), dry_run=False)
    assert run_import(maker(), deploy({}), dry_run=False).errors


def test_non_date_row_is_error(db):
    wb = openpyxl.load_workbook(BytesIO(deploy({})))
    wb["근무표"].append(["2026-11-1o", "화"])
    report = run_import(maker(), _bytes(wb), dry_run=False)
    assert any("날짜가 아닙니다" in e for e in report.errors) and not Member.objects.exists()


def test_missing_sheet_is_error(db):
    wb = openpyxl.load_workbook(BytesIO(deploy({})))
    del wb["근무표"]
    report = run_import(maker(), _bytes(wb), dry_run=False)
    assert any("근무표" in e for e in report.errors) and not Member.objects.exists()


def test_non_xlsx_is_error(db):
    report = run_import(b"not xlsx", deploy({}), dry_run=False)
    assert report.errors and not Member.objects.exists()


def test_bad_member_rows_are_errors(db):
    wb = openpyxl.load_workbook(BytesIO(maker()))
    wb["tb_member"].append(["MEX01", "매칭엔진실", None, "매칭엔진", "개발자", False, True])
    wb["tb_member"].append(["MEX02", "매칭엔진실", "x", "매칭엔진", "외부", False, True])
    report = run_import(_bytes(wb), deploy({}), dry_run=True)
    assert any("비어 있는 값" in e for e in report.errors) and any("구분" in e for e in report.errors)


def test_empty_plan_is_error(db):
    wb = openpyxl.Workbook()
    wb.active.title = "view_all_combine"
    wb.active.append(["날짜", "요일", *[cell_label(c) for c in CELLS]])
    b = wb.create_sheet("근무표")
    b.append(["검색", "."])
    b.append(["날짜", "요일", *[cell_label(c) for c in CELLS]])
    report = run_import(maker(), _bytes(wb), dry_run=False)
    assert any("가져올 날짜가 없습니다" in e for e in report.errors)


def test_command_missing_file_is_command_error(db, tmp_path):
    with pytest.raises(CommandError, match="읽지 못했습니다"):
        call_command("import_sheets", maker_xlsx=str(tmp_path / "nope.xlsx"), deploy_xlsx=str(tmp_path / "nope2.xlsx"))


def test_command_non_xlsx_is_command_error(db, tmp_path):
    f = tmp_path / "a.xlsx"
    f.write_text("<html>")
    with pytest.raises(CommandError, match="xlsx가 아닙니다"):
        call_command("import_sheets", maker_xlsx=str(f), deploy_xlsx=str(f))
