from datetime import date

import pytest
from django.core.exceptions import PermissionDenied

from duty.csv_io import CsvInvalid
from duty.errors import DutyError
from duty.models import BoardShift, Commute, Period
from duty.services import collect

S = Period.Status
CSV = 'date,새벽,정상,석식교대,야간\n2026-11-09,가,"나,다",,\n'


@pytest.fixture
def setup(depts, make_member, fixed_today, it_board):
    fixed_today(date(2026, 11, 1))
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13), status=S.COLLECTING)
    mgr = make_member("담당", user=True)
    depts["MEMS"].input_group.user_set.add(mgr)
    for n in ["가", "나", "다"]:
        make_member(n)
    make_member("타부서", dept="MD")
    return p, depts["MEMS"], mgr


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
    assert "근무조가 없습니다" in reasons(e)


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
        collect.apply_csv(other, p, dept, CSV.encode())


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


def test_unchanged_date_skips_member_check(setup, make_member):
    p, dept, user = setup
    collect.apply_csv(user, p, dept, CSV.encode())
    from duty.models import User
    User.objects.filter(name="가").update(is_active=False)
    same_plus = 'date,새벽,정상,석식교대,야간\n2026-11-09,가,"나,다",,\n2026-11-10,,나,,\n'.encode()
    assert collect.apply_csv(user, p, dept, same_plus) == 4
    changed = 'date,새벽,정상,석식교대,야간\n2026-11-09,가,나,,\n'.encode()
    with pytest.raises(CsvInvalid) as e:
        collect.apply_csv(user, p, dept, changed)
    assert "재직 멤버가 아닙니다" in reasons(e)


def test_csv_columns_follow_board_definitions(setup, it_board):
    p, dept, user = setup
    assert collect.shift_names(dept) == {"dawn": "새벽", "normal": "정상", "dinner": "석식교대", "night": "야간"}
    BoardShift.objects.filter(board=it_board, key="dinner").update(name="늦은조")
    assert collect.export_csv(p, dept).decode("utf-8-sig").splitlines()[0] == "date,day,새벽,정상,늦은조,야간"
    raw = 'date,새벽,정상,늦은조,야간\n2026-11-09,가,,나,\n'.encode()
    assert collect.apply_csv(user, p, dept, raw) == 2


def test_shift_removed_from_department_cleared_on_save(setup):
    """부서 출근조에서 뺀 근무조(정의는 켜짐)의 옛 행은 저장 때 지운다(예전과 같음). 보존은 꺼진 정의만."""
    p, dept, user = setup
    collect.apply_csv(user, p, dept, 'date,새벽,정상,석식교대,야간\n2026-11-09,가,나,,\n'.encode())
    dept.shifts = "normal,dinner,night"
    dept.save()
    collect.apply_csv(user, p, dept, 'date,정상,석식교대,야간\n2026-11-09,가,,\n'.encode())
    assert dict(Commute.objects.filter(period=p).values_list("member__name", "shift")) == {"가": "normal"}


def test_inactive_shift_left_out_of_input_but_kept_on_save(setup, it_board, client):
    p, dept, user = setup
    collect.apply_csv(user, p, dept, 'date,새벽,정상,석식교대,야간\n2026-11-09,가,나,,\n'.encode())
    BoardShift.objects.filter(board=it_board, key="dawn").update(active=False)
    assert collect.input_keys(dept) == ["normal", "dinner", "night"] == list(collect.shift_names(dept))
    assert collect.export_csv(p, dept).decode("utf-8-sig").splitlines()[0] == "date,day,정상,석식교대,야간"
    client.force_login(user)
    assert 'name="c_2026-11-09_dawn"' not in client.get(f"/collect/{p.pk}/MEMS/").content.decode()  # 입력 칸 없음
    collect.apply_csv(user, p, dept, 'date,정상,석식교대,야간\n2026-11-09,다,,\n'.encode())
    # 입력 키(정상·석식교대·야간)의 행만 바뀌고, 꺼진 새벽의 기존 배정은 지워지지 않는다
    assert dict(Commute.objects.filter(period=p).values_list("member__name", "shift")) == {"가": "dawn", "다": "normal"}
    # 꺼진 근무조에 남은 사람을 그날 켜진 근무조에 다시 넣으면 검증 오류(하루 한 출근 제약에 걸리기 전에)
    with pytest.raises(CsvInvalid) as e:
        collect.apply_csv(user, p, dept, 'date,정상,석식교대,야간\n2026-11-09,가,,\n'.encode())
    assert any("이미 사용하지 않는 근무조에 배정돼 있습니다" in err.reason for err in e.value.errors)


def test_input_order_follows_current_start_times(setup, it_board):
    # 부서 출근조는 저장한 순서가 아니라 지금 정의의 시작 시각 순으로 입력 표·CSV 열에 놓인다(설계: 시작 시각 순)
    p, dept, _ = setup
    BoardShift.objects.filter(board=it_board, key="dawn").update(start="10:00")
    assert dept.shifts == "dawn,normal,dinner,night"  # 저장값은 그대로
    assert collect.input_keys(dept) == ["normal", "dinner", "dawn", "night"] == list(collect.shift_names(dept))
    assert collect.export_csv(p, dept).decode("utf-8-sig").splitlines()[0] == "date,day,정상,석식교대,새벽,야간"
