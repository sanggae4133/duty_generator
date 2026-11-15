"""근무표가 둘일 때 알림 규칙·정기 알림·변경 알림·캘린더가 서로 영향 없음(1단계)."""
from datetime import date, time

import pytest

from duty.alarms.forms import RuleForm
from duty.errors import DutyError
from duty.models import AlarmDelivery, AlarmRule, Board, BoardShift, Department, User
from duty.services import alarms

D = date(2026, 11, 16)  # 월
SUN = date(2026, 11, 15)
OPS_DEFS = [("dawn", "오전", time(7, 30), time(16, 30)), ("normal", "주간", time(9), time(18)),
            ("dinner", "오후", time(11), time(20))]
FORM = dict(enabled="on", timing="before_start", hours="2", minutes="0", telegram="on")


@pytest.fixture
def ops(it_board):
    """가짜 두 번째 근무표 '운영팀'(관리 그룹은 Board.save 가 만든다): 근무조 셋(모두 기본 알림), 관제 없음."""
    board = Board.objects.create(code="ops", name="운영팀", input_mode="direct")
    for key, name, start, end in OPS_DEFS:
        BoardShift.objects.create(board=board, key=key, name=name, start=start, end=end, default_alarm=True)
    dept = Department.objects.create(code="OPS", name="운영팀", shifts="dawn,normal,dinner", board=board, order=0)
    return board, dept


def report_base(board_id, **kw):
    return {**dict(enabled=True, kind="report", timing="days", offset=1, at_minute=18 * 60, telegram=True,
                   push=False, shifts=["dawn"], depts=[], types=[], board_id=board_id), **kw}


# ---- 규칙 ----

def test_create_defaults_uses_board_default_alarm(depts, ops):
    _, dept = ops
    it = User.objects.create_user("it1", password=None, name="가상아이", department=depts["MEMS"], type="직원")
    op = User.objects.create_user("op1", password=None, name="가상운영", department=dept, type="직원")
    alarms.create_defaults(it)
    alarms.create_defaults(op)
    assert [r.shifts for r in AlarmRule.objects.filter(user=it)] == [["dawn", "dinner", "night"]] * 2
    assert [r.shifts for r in AlarmRule.objects.filter(user=op)] == [["dawn", "normal", "dinner"]] * 2
    assert not AlarmRule.objects.filter(board__isnull=False).exists()  # 기본 규칙은 개인 규칙


def test_normalize_by_board(depts, ops):
    board, _ = ops
    assert alarms.normalize("report", ["dinner", "dawn"], ["OPS"], [], board) == (["dawn", "dinner"], [], [])
    with pytest.raises(DutyError):
        alarms.normalize("report", ["night"], [], [], board)  # 운영팀에 없는 키
    with pytest.raises(DutyError):
        alarms.normalize("report", [], ["MEMS"], [], board)  # 다른 근무표의 부서


def test_report_rules_by_board_and_board_change_clears(fixed_today, depts, it_board, ops, admin_user):
    fixed_today(SUN)
    board, _ = ops
    a = alarms.save_rule(admin_user, report_base(it_board.pk))
    b = alarms.save_rule(admin_user, report_base(board.pk, shifts=["normal"]))
    assert (a.board_id, b.board_id) == (it_board.pk, board.pk)
    with pytest.raises(DutyError, match="같은 규칙이 이미 있습니다."):
        alarms.save_rule(admin_user, report_base(board.pk, shifts=["normal"]))
    with pytest.raises(DutyError, match="근무표를 고르세요."):
        alarms.save_rule(admin_user, report_base(None))
    assert alarms.save_rule(admin_user, report_base(board.pk, kind="personal")).board_id is None
    AlarmDelivery.objects.create(rule=b, date=D, cell="report", channel="telegram", destination="1",
                                 status="sent", content_hash="h")
    alarms.save_rule(admin_user, report_base(it_board.pk, shifts=["normal"]), b)  # 근무표만 바꿈
    assert not AlarmDelivery.objects.filter(rule=b).exists()


def test_rule_form_single_board(depts, it_board):
    f = RuleForm({**FORM, "kind": "report"})
    assert "board" not in f.fields and f.is_valid(), f.errors
    assert f.cleaned_data["rule"]["board_id"] == it_board.pk
    assert [c for c, _ in f.fields["depts"].choices] == ["MD", "MEMS", "TMCH", "UI"]


def test_rule_form_two_boards(depts, it_board, ops):
    board, _ = ops
    f = RuleForm({**FORM, "kind": "report", "board": str(board.pk)})
    assert "board" in f.fields and f.is_valid(), f.errors
    assert f.cleaned_data["rule"]["board_id"] == board.pk
    assert [c for c, _ in f.fields["shifts"].choices] == ["dawn", "normal", "dinner"]  # 고른 근무표의 스케줄
    f = RuleForm({**FORM, "kind": "report", "board": str(board.pk), "shifts": ["night"]})
    assert not f.is_valid() and "shifts" in f.errors  # 운영팀에 없는 키는 폼이 막는다(normalize DutyError 까지 안 감)
    f = RuleForm({**FORM, "kind": "report", "board": str(it_board.pk), "shifts": ["night"]})
    assert f.is_valid(), f.errors
    f = RuleForm({**FORM, "kind": "personal", "board": str(board.pk)})
    assert f.is_valid() and f.cleaned_data["rule"]["board_id"] is None
    op = User.objects.create_user("op2", password=None, name="가상운영", department=ops[1], type="직원")
    f = RuleForm({**FORM, "kind": "personal"}, user=op)
    assert [c for c, _ in f.fields["shifts"].choices] == ["dawn", "normal", "dinner"]  # 개인 = 주인의 근무표


def test_rule_page_board_field_only_with_two_boards(client, depts, request):
    client.force_login(User.objects.create_user("u9", password="unused-Pw-123", name="가상구"))
    assert "<legend>근무표</legend>" not in client.get("/alarms/rules/new/").content.decode()
    request.getfixturevalue("ops")
    assert "<legend>근무표</legend>" in client.get("/alarms/rules/new/").content.decode()


def test_rule_list_names_shifts_by_rule_board(client, depts, ops, admin_user):
    """규칙 목록의 스케줄 이름은 그 규칙의 근무표 정의로(보고서 = 규칙의 근무표)."""
    board, _ = ops
    AlarmRule.objects.create(user=admin_user, kind="report", board=board, timing="days", offset=1,
                             at_minute=18 * 60, telegram=True, shifts=["dawn"], depts=[], types=[])
    client.force_login(admin_user)
    assert "스케줄: 오전" in client.get("/alarms/").content.decode()
