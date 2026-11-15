"""근무표가 둘일 때 알림 규칙·정기 알림·변경 알림·캘린더가 서로 영향 없음(1단계)."""
from datetime import date, datetime, time, timedelta

import pytest
from django.contrib import admin as dj_admin
from django.utils import timezone

from duty import accounts
from duty.admin import UserAdmin
from duty.alarms import senders
from duty.alarms.forms import RuleForm
from duty.errors import DutyError
from duty.models import (AlarmDelivery, AlarmRule, AlarmSettings, Board, BoardShift, ChangeLog, Commute, Department,
                         Period, PeriodEvent, TelegramAlarmProfile, User)
from duty.services import alarm_runner, alarms, calendar, change_notice

D = date(2026, 11, 16)  # 월
SUN = date(2026, 11, 15)
SUN18 = timezone.make_aware(datetime(2026, 11, 15, 18))
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


@pytest.fixture
def env(settings, fixed_today, monkeypatch, db):
    """텔레그램만 켜고 보낸 것을 (chat_id, 본문)으로 모은다(실제 호출 없음)."""
    AlarmSettings.objects.update_or_create(pk=1, defaults=dict(telegram_bot_token="t"))
    settings.SITE_URL = ""
    fixed_today(SUN)
    sent = []
    monkeypatch.setattr(senders, "telegram_send", lambda cfg, chat, text: sent.append((chat, text)) or {})
    monkeypatch.setattr(senders, "push_send", lambda *a, **k: pytest.fail("푸시는 보내지 않는다"))
    return sent


def person(name, dept, chat):
    """발급된 계정(기본 알림 규칙 포함) + 확인된 텔레그램."""
    u = User.objects.create_user(f"{dept.code}{chat}", password="unused-Pw-123", name=name, department=dept,
                                 type="직원")
    alarms.create_defaults(u)
    TelegramAlarmProfile.objects.create(user=u, chat_id=chat, verified_at=timezone.now())
    return u


def published(board, *rows):
    p = Period.objects.create(board=board, name=board.code, start_date=D, end_date=D, overwrite_from=D,
                              status=Period.Status.PUBLISHED, published_at=timezone.now())
    for member, shift in rows:
        Commute.objects.create(period=p, date=D, member=member, shift=shift)
    return p


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


def test_rule_types_only_on_board_with_slots(client, depts, it_board, ops, admin_user):
    """유형은 켜진 관제 정의가 있는 근무표에만(근무표 화면과 같은 규칙). 없는 근무표는 칸을 숨기고 보낸 값은 버린다."""
    board, _ = ops
    f = RuleForm({**FORM, "kind": "report", "board": str(board.pk), "types": ["직원"]})
    assert "types" not in f.fields and f.is_valid(), f.errors
    assert f.cleaned_data["rule"]["types"] == []
    assert "types" in RuleForm({**FORM, "kind": "report", "board": str(it_board.pk)}).fields
    assert alarms.save_rule(admin_user, report_base(board.pk, types=["직원"])).types == []
    client.force_login(admin_user)
    page = client.post("/alarms/rules/new/", {**FORM, "kind": "report", "board": str(board.pk), "redraw": "1"})
    assert "<legend>유형</legend>" not in page.content.decode()
    page = client.post("/alarms/rules/new/", {**FORM, "kind": "report", "board": str(it_board.pk), "redraw": "1"})
    assert "<legend>유형</legend>" in page.content.decode()


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


def test_rule_list_ignores_stored_types_on_board_without_slots(client, depts, ops, admin_user):
    """관제 없는 근무표의 보고서 규칙은 저장된 유형이 남아 있어도 목록에 '유형: 전부'."""
    board, _ = ops
    AlarmRule.objects.create(user=admin_user, kind="report", board=board, timing="days", offset=1,
                             at_minute=18 * 60, telegram=True, shifts=["dawn"], depts=[], types=["개발자"])
    client.force_login(admin_user)
    assert "유형: 전부" in client.get("/alarms/").content.decode()


# ---- 정기 알림 ----

def test_same_date_on_two_boards_no_cross_cancel(env, depts, it_board, ops):
    """같은 날짜에 다른 근무표가 있어도 IT 개인 규칙에 취소 알림이 나가지 않는다."""
    board, dept = ops
    it, op = person("가상아이", depts["MEMS"], "111"), person("가상운영", dept, "222")
    published(it_board, (it, "dawn"))
    published(board, (op, "dawn"))
    assert alarm_runner.tick(SUN18) == (2, 2, 0)
    assert sorted(env) == [("111", "[당번 알림] 11/16(월) 새벽 06:30~15:30\n가상아이님, 내일 새벽 당번입니다."),
                           ("222", "[당번 알림] 11/16(월) 오전 07:30~16:30\n가상운영님, 내일 오전 당번입니다.")]
    env.clear()
    assert alarm_runner.tick(SUN18 + timedelta(minutes=1)) == (0, 0, 0)
    assert env == []


def test_report_rule_reads_only_its_board(env, depts, it_board, ops, admin_user):
    board, dept = ops
    it, op = person("가상아이", depts["MEMS"], "111"), person("가상운영", dept, "222")
    AlarmRule.objects.filter(user__in=[it, op]).delete()
    published(it_board, (it, "dawn"))
    published(board, (op, "dawn"))
    AlarmRule.objects.create(user=admin_user, kind="report", board=board, timing="days", offset=1,
                             at_minute=18 * 60, telegram=True, shifts=[], depts=[], types=[])
    TelegramAlarmProfile.objects.create(user=admin_user, chat_id="999", verified_at=timezone.now())
    alarm_runner.tick(SUN18)
    assert env == [("999", "[출근표] 11/16(월)\n오전(07:30~) 가상운영\n주간(09:00~) -\n오후(11:00~) -")]


def test_report_ignores_stored_types_on_board_without_slots(env, depts, it_board, ops, admin_user):
    """관제 없는 근무표에선 저장된 유형이 남아 있어도 모든 유형을 넣는다."""
    board, dept = ops
    op = person("가상운영", dept, "222")
    AlarmRule.objects.filter(user=op).delete()
    published(board, (op, "dawn"))
    AlarmRule.objects.create(user=admin_user, kind="report", board=board, timing="days", offset=1,
                             at_minute=18 * 60, telegram=True, shifts=[], depts=[], types=["개발자"])
    TelegramAlarmProfile.objects.create(user=admin_user, chat_id="999", verified_at=timezone.now())
    alarm_runner.tick(SUN18)
    assert env == [("999", "[출근표] 11/16(월)\n오전(07:30~) 가상운영\n주간(09:00~) -\n오후(11:00~) -")]


def test_owned_day_without_rows_sends_no_report(env, depts, it_board, admin_user):
    """그날의 주인은 있어도 배정이 하나도 없는 날은 정기 알림에 넘기지 않는다(빈 보고서 방지)."""
    published(it_board)
    AlarmRule.objects.create(user=admin_user, kind="report", board=it_board, timing="days", offset=1,
                             at_minute=18 * 60, telegram=True, shifts=[], depts=[], types=[])
    TelegramAlarmProfile.objects.create(user=admin_user, chat_id="999", verified_at=timezone.now())
    assert alarm_runner.tick(SUN18) == (0, 0, 0)


# ---- 변경 알림 ----

def test_change_notice_uses_period_board_names(env, depts, ops):
    board, dept = ops
    a, b = person("가상운영", dept, "222"), person("가상운영둘", dept, "333")
    p = published(board, (b, "dawn"))
    ChangeLog.objects.create(period=p, date=D, cell="dawn", before=a, after=b)
    change_notice.tick(timezone.now())
    assert sorted(env) == [(c, "[근무 변경] 11/16(월) 오전\n가상운영 → 가상운영둘\n바꾼 사람: -") for c in ("222", "333")]


def test_change_notice_sent_when_period_owns_empty_day(env, depts, it_board):
    """배정이 다 빠진 날도 그 회차가 그날의 주인이면 보낸다."""
    a = person("가상아이", depts["MEMS"], "111")
    p = published(it_board)
    ChangeLog.objects.create(period=p, date=D, cell="dawn", before=a, after=None)
    change_notice.tick(timezone.now())
    assert env == [("111", "[근무 변경] 11/16(월) 새벽\n가상아이 빠짐\n바꾼 사람: -")]


def test_change_notice_skipped_when_newer_period_owns_day(env, depts, it_board):
    a = person("가상아이", depts["MEMS"], "111")
    old, new = published(it_board, (a, "dawn")), published(it_board, (a, "dawn"))
    PeriodEvent.objects.create(period=old, from_status="generated", to_status="published")
    PeriodEvent.objects.create(period=new, from_status="generated", to_status="published")
    ChangeLog.objects.create(period=old, date=D, cell="dawn", before=a, after=None)
    change_notice.tick(timezone.now())
    assert env == []


# ---- 캘린더 ----

def test_calendar_uses_member_board_definitions(env, depts, it_board, ops):
    board, dept = ops
    it, op = person("가상아이", depts["MEMS"], "111"), person("가상운영", dept, "222")
    published(it_board, (it, "normal"))
    published(board, (op, "normal"))
    [e] = calendar._events(op)
    assert (e.summary, e.start.time(), e.end.time(), e.uid) == (
        "주간 출근 09:00~18:00", time(9), time(18), f"20261116-normal-{op.pk}@duty-generator")
    [e] = calendar._events(it)
    assert e.summary == "정상 출근 08:00~17:00"


# ---- 부서 이동 ----

def _deliveries(u, it_board):
    personal = AlarmRule.objects.filter(user=u).first()
    report = AlarmRule.objects.create(user=u, kind="report", board=it_board, timing="days", offset=2,
                                      at_minute=9 * 60, telegram=True, shifts=[], depts=[], types=[])
    for r, cell in ((personal, "dawn"), (report, "report")):
        for d in (SUN - timedelta(days=1), D):
            AlarmDelivery.objects.create(rule=r, date=d, cell=cell, channel="telegram", destination="111",
                                         status="sent", content_hash="h")
    return personal, report


def test_department_change_to_other_board_clears_personal_deliveries(env, depts, it_board, ops):
    _, dept = ops
    u = person("가상아이", depts["MEMS"], "111")
    personal, report = _deliveries(u, it_board)
    old, u.department = u.department_id, depts["UI"]
    u.save()
    accounts.on_department_change(u, old)  # 같은 근무표(IT) 안 이동 → 그대로
    assert AlarmDelivery.objects.count() == 4
    old, u.department = u.department_id, dept
    u.save()
    accounts.on_department_change(u, old)
    assert sorted((x.rule_id, x.date) for x in AlarmDelivery.objects.all()) == sorted(
        [(personal.id, SUN - timedelta(days=1)), (report.id, SUN - timedelta(days=1)), (report.id, D)])


def test_admin_user_save_calls_department_change(env, depts, it_board, ops, rf, admin_user):
    _, dept = ops
    u = person("가상아이", depts["MEMS"], "111")
    _deliveries(u, it_board)
    u = User.objects.get(pk=u.pk)
    u.department = dept
    request = rf.post("/")
    request.user = admin_user
    UserAdmin(User, dj_admin.site).save_model(request, u, form=None, change=True)
    assert not AlarmDelivery.objects.filter(rule__kind="personal", date__gte=SUN).exists()
    assert AlarmDelivery.objects.filter(rule__kind="report").count() == 2
