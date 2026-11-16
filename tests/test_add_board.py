"""manage.py add_board: 직접 입력 근무표를 한 번에 만든다(OPERATIONS '근무표 추가하기'). 이름은 모두 가상."""
import io
from datetime import date, time

import pytest
from django.core.management import CommandError, call_command

from django.contrib.auth.models import Group

from duty.models import Board, BoardShift, Department, Period, User
from duty.services import collect, periods

SHIFTS = "07:30-16:30,09:00-18:00,11:00-20:00"
NAMES = ["가상가", "가상나", "가상다"]


@pytest.fixture
def people(tmp_path):
    def write(lines):
        f = tmp_path / "people.txt"
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(f)

    return write


def run(*args, **kw):
    out = io.StringIO()
    call_command("add_board", *args, stdout=out, stderr=out, **kw)
    return out.getvalue()


def counts():
    return (Board.objects.count(), BoardShift.objects.count(), Department.objects.count(), User.objects.count(),
            Group.objects.count())


def test_happy_path(it_board, people):
    boss = User.objects.create_user("boss", password=None, name="가상장")
    out = run("mops", "시장운영실", "--shifts", SHIFTS, "--lunch", "11:30-12:30",
              "--people", people(NAMES), "--admin", "boss")

    board = Board.objects.get(code="mops")
    assert board.name == "시장운영실" and board.input_mode == Board.InputMode.DIRECT
    rows = {s.key: s for s in BoardShift.objects.filter(board=board)}
    assert set(rows) == {"dawn", "normal", "dinner", "lunch"}
    assert [(rows[k].name, rows[k].start, rows[k].end, rows[k].default_alarm) for k in ("dawn", "normal", "dinner")] == [
        ("07:30", time(7, 30), time(16, 30), True), ("09:00", time(9), time(18), True),
        ("11:00", time(11), time(20), True)]
    lunch = rows["lunch"]
    assert (lunch.name, lunch.start, lunch.end, lunch.default_alarm) == ("점심당번", None, None, False)

    dept = Department.objects.get(board=board)
    assert (dept.code, dept.name, dept.shifts) == ("mops", "시장운영실", "dawn,normal,dinner")
    assert (dept.lunch_start, dept.lunch_end) == (time(11, 30), time(12, 30))
    assert dept.input_group_id is None

    users = list(User.objects.filter(department=dept).order_by("username"))
    assert [(u.username, u.name, u.type, u.part, u.is_active) for u in users] == [
        ("mops01", "가상가", "직원", "", True), ("mops02", "가상나", "직원", "", True), ("mops03", "가상다", "직원", "", True)]
    assert not any(u.has_usable_password() for u in users)
    assert boss.groups.filter(pk=board.admin_group_id).exists()

    assert "mops01~mops03" in out and "3명" in out and "계정 발급 / 비밀번호 초기화" in out
    assert not any(n in out for n in NAMES)  # 명단의 이름은 요약에 남기지 않는다


def test_works_with_existing_flows(it_board, people):
    run("mops", "시장운영실", "--shifts", "11:00-20:00,07:30-16:30", "--people", people(NAMES))
    board = Board.objects.get(code="mops")
    dept = Department.objects.get(board=board)
    assert collect.input_keys(dept) == ["normal", "dawn"]  # 시작 시각 순(07:30 = normal 이 먼저)
    assert (dept.lunch_start, dept.lunch_end) == (None, None)
    p = periods.save_draft(Period(board=board, name="11월", start_date=date(2026, 11, 16), end_date=date(2026, 11, 20)))
    assert p.status == Period.Status.COLLECTING


def test_existing_code_refused(it_board, people):
    before = counts()
    with pytest.raises(CommandError, match="이미 있는 근무표 코드"):
        run("it", "다른표", "--shifts", SHIFTS, "--people", people(NAMES))
    assert counts() == before


@pytest.mark.parametrize("shifts", ["07:30-16:30,0900-1800", "16:30-07:30", "07:30-25:00", "09:00-18:00,09:00-19:00"])
def test_bad_time(it_board, people, shifts):
    before = counts()
    with pytest.raises(CommandError):
        run("mops", "시장운영실", "--shifts", shifts, "--people", people(NAMES))
    assert counts() == before


def test_bad_lunch_and_code(it_board, people):
    with pytest.raises(CommandError, match="점심"):
        run("mops", "시장운영실", "--shifts", SHIFTS, "--lunch", "12:30-11:30", "--people", people(NAMES))
    with pytest.raises(CommandError, match="영문 소문자"):
        run("Mops", "시장운영실", "--shifts", SHIFTS, "--people", people(NAMES))
    assert not Board.objects.exclude(code="it").exists()


def test_too_many_shifts(it_board, people):
    with pytest.raises(CommandError, match="4개"):
        run("mops", "시장운영실", "--shifts", "06:00-07:00,07:00-08:00,08:00-09:00,09:00-10:00,10:00-11:00",
            "--people", people(NAMES))
    assert not Board.objects.filter(code="mops").exists()


def test_invalid_name_is_atomic(it_board, people):
    boss = User.objects.create_user("boss", password=None, name="가상장")
    boss_groups = set(boss.groups.values_list("pk", flat=True))
    before = counts()
    with pytest.raises(CommandError) as e:
        run("mops", "시장운영실", "--shifts", SHIFTS, "--people", people(["가상가", "", "가상나(휴가)", "가,상"]),
            "--admin", "boss")
    msg = str(e.value)
    assert "3번째 줄: 이름이 (휴가)·(출장)·(교육)으로 끝날 수 없습니다" in msg and "4번째 줄" in msg
    assert "가상나" not in msg and "가,상" not in msg  # 명단의 이름은 오류에도 남기지 않는다
    assert counts() == before
    assert not Board.objects.filter(code="mops").exists()
    assert not Group.objects.filter(name="시장운영실 근무표 관리").exists()
    assert set(boss.groups.values_list("pk", flat=True)) == boss_groups


def test_duplicate_names_and_existing_name(it_board, people):
    User.objects.create_user("x", password=None, name="가상나")
    before = counts()
    with pytest.raises(CommandError) as e:
        run("mops", "시장운영실", "--shifts", SHIFTS, "--people", people(["가상가", "가상나", "가상가"]))
    assert "2번째 줄" in str(e.value) and "3번째 줄" in str(e.value)
    assert "가상" not in str(e.value)
    assert counts() == before


def test_username_collision(it_board, people):
    User.objects.create_user("MOPS02", password=None, name="가상옛")  # 대소문자만 다른 아이디도 막는다
    before = counts()
    with pytest.raises(CommandError, match="mops02"):
        run("mops", "시장운영실", "--shifts", SHIFTS, "--people", people(NAMES))
    assert counts() == before


def test_missing_admin(it_board, people):
    with pytest.raises(CommandError, match="nobody"):
        run("mops", "시장운영실", "--shifts", SHIFTS, "--people", people(NAMES), "--admin", "nobody")
    assert not Board.objects.filter(code="mops").exists()


def test_blank_and_comment_lines(it_board, people):
    run("mops", "시장운영실", "--shifts", "09:00-18:00", "--people",
        people(["# 시장운영실 명단", "", "  가상가  ", "   ", "#가상주석", "가상나"]))
    assert list(User.objects.filter(department__code="mops").order_by("username").values_list("username", "name")) == [
        ("mops01", "가상가"), ("mops02", "가상나")]


def test_three_digit_usernames(it_board, people):
    run("mops", "시장운영실", "--shifts", "09:00-18:00", "--people", people([f"가상{i}" for i in range(100)]))
    names = list(User.objects.filter(department__code="mops").order_by("username").values_list("username", flat=True))
    assert names[0] == "mops001" and names[-1] == "mops100"


def test_empty_people_refused(it_board, people):
    with pytest.raises(CommandError, match="이름"):
        run("mops", "시장운영실", "--shifts", SHIFTS, "--people", people(["# 비어 있음"]))
    assert not Board.objects.filter(code="mops").exists()


def test_people_from_stdin(it_board):
    out = run("mops", "시장운영실", "--shifts", SHIFTS, "--people", "-", stdin=io.StringIO("가상가\n# 주석\n가상나\n"))
    assert "mops01~mops02" in out
    assert list(User.objects.filter(department__code="mops").order_by("username").values_list("name", flat=True)) == [
        "가상가", "가상나"]
