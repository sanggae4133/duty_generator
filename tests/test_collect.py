from datetime import date

import pytest
from django.core.exceptions import PermissionDenied

from duty.csv_io import CsvInvalid
from duty.errors import DutyError
from duty.models import Period
from duty.services import collect

S = Period.Status
CSV = 'date,새벽,정상,석식교대,야간\n2026-11-09,가,"나,다",,\n'


@pytest.fixture
def setup(depts, make_member, fixed_today):
    fixed_today(date(2026, 11, 1))
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13), status=S.COLLECTING)
    mgr = make_member("담당", user=True)
    depts["MEMS"].managers.add(mgr)
    for n in ["가", "나", "다"]:
        make_member(n)
    make_member("타부서", dept="MD")
    return p, depts["MEMS"], mgr.user


def reasons(exc):
    return " / ".join(e.reason for e in exc.value.errors)


def test_apply_csv_writes_rows(setup):
    p, dept, user = setup
    assert collect.apply_csv(user, p, dept, CSV.encode()) == 3
    t = collect.load_table(p, dept)
    assert t[date(2026, 11, 9)] == {"dawn": ["가"], "normal": ["나", "다"]}


def test_apply_replaces_whole_department(setup):
    p, dept, user = setup
    collect.apply_csv(user, p, dept, CSV.encode())
    collect.apply_csv(user, p, dept, "date,새벽,정상,석식교대,야간\n2026-11-10,,가,,\n".encode())
    assert collect.load_table(p, dept) == {date(2026, 11, 10): {"normal": ["가"]}}


def test_rejects_other_department_member(setup):
    p, dept, user = setup
    with pytest.raises(CsvInvalid) as e:
        collect.apply_csv(user, p, dept, "date,새벽,정상,석식교대,야간\n2026-11-09,타부서,,,\n".encode())
    assert "재직 멤버가 아닙니다" in reasons(e)


def test_rejects_double_shift(setup):
    p, dept, user = setup
    with pytest.raises(CsvInvalid) as e:
        collect.apply_csv(user, p, dept, "date,새벽,정상,석식교대,야간\n2026-11-09,가,,,가\n".encode())
    assert "중복" in reasons(e)


def test_rejects_weekend_and_out_of_period(setup):
    p, dept, user = setup
    with pytest.raises(CsvInvalid) as e:
        collect.apply_csv(user, p, dept, "date,새벽,정상,석식교대,야간\n2026-11-14,가,,,\n2026-11-16,나,,,\n".encode())
    assert len(e.value.errors) == 2


def test_rejects_shift_department_does_not_have(setup, depts, make_member, admin_user):
    p, _, _ = setup
    make_member("유아이", dept="UI")
    table = {date(2026, 11, 9): {"dawn": ["유아이"]}}
    with pytest.raises(CsvInvalid) as e:
        collect.apply_table(admin_user, p, depts["UI"], table)
    assert "출근조가 없습니다" in reasons(e)


def test_errors_mean_nothing_is_written(setup):
    p, dept, user = setup
    collect.apply_csv(user, p, dept, CSV.encode())
    with pytest.raises(CsvInvalid):
        collect.apply_csv(user, p, dept, "date,새벽,정상,석식교대,야간\n2026-11-10,없는사람,,,\n".encode())
    assert date(2026, 11, 9) in collect.load_table(p, dept)


def test_non_manager_forbidden(setup, make_member):
    p, dept, _ = setup
    other = make_member("남", user=True)
    with pytest.raises(PermissionDenied):
        collect.apply_csv(other.user, p, dept, CSV.encode())


def test_requires_collecting(setup):
    p, dept, user = setup
    p.status = S.CLOSED
    p.save()
    with pytest.raises(DutyError):
        collect.apply_csv(user, p, dept, CSV.encode())


def test_past_dates_locked_for_manager_not_admin(setup, fixed_today, admin_user):
    p, dept, user = setup
    collect.apply_csv(user, p, dept, CSV.encode())
    fixed_today(date(2026, 11, 11))
    changed = "date,새벽,정상,석식교대,야간\n2026-11-09,나,가,,\n".encode()
    with pytest.raises(CsvInvalid) as e:
        collect.apply_csv(user, p, dept, changed)
    assert "지난 날짜" in reasons(e)
    removed_past = "date,새벽,정상,석식교대,야간\n2026-11-12,가,,,\n".encode()
    with pytest.raises(CsvInvalid):
        collect.apply_csv(user, p, dept, removed_past)  # 11/9 를 지우는 것도 수정
    assert collect.apply_csv(admin_user, p, dept, changed) == 2


def test_export_has_current_values(setup):
    p, dept, user = setup
    collect.apply_csv(user, p, dept, CSV.encode())
    text = collect.export_csv(p, dept).decode("utf-8-sig")
    assert "2026-11-09,월,가,\"나, 다\",," in text
    assert text.count("\n") == 6  # 헤더 + 평일 5일


def test_progress(setup):
    p, dept, user = setup
    collect.apply_csv(user, p, dept, CSV.encode())
    pr = collect.progress(p)
    assert pr["MEMS"] == (1, 5) and pr["UI"] == (0, 5)
