"""근무표 고르기·보기 전용·?board= 링크 규칙·이력 근무표 열·알림 규칙 화면(설계 7·8.1). 이름은 모두 가상."""
from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from duty.alarms.forms import RuleForm
from duty.alarms.plan import RuleSpec, plan
from duty.models import AlarmRule, ChangeLog, Commute, Memo, Period, RosterPref, User
from duty.services import alarm_runner, boards, change_notice
from duty.services.roster import Day
from duty.shifts import KEYS
from tests.it_defs import IT_DEFS
from tests.test_alarm_boards import FORM, D, SUN18, env, ops, person, published  # noqa: F401 (env·ops 는 픽스처)

WEEK = f"/?view=week&date={D.isoformat()}"


def member(username, name, dept):
    return User.objects.create_user(username, password="unused-Pw-123", name=name, department=dept, type="직원")


@pytest.fixture
def two(depts, it_board, ops, fixed_today):
    """IT 근무표(가상다 새벽)와 운영팀 근무표(가상나 오전)가 D 에 배포. 로그인하는 사람은 IT 의 가상가. 오늘 = D 앞 금요일."""
    fixed_today(D - timedelta(days=3))
    board, dept = ops
    ga, da = member("it01", "가상가", depts["MEMS"]), member("it02", "가상다", depts["MEMS"])
    na = member("op01", "가상나", dept)
    published(it_board, (da, "dawn"))
    published(board, (na, "dawn"))
    return board, ga, na


# ── 보일 근무표 ──

def test_home_and_board_query(two, it_board, admin_user):
    board, ga, na = two
    assert boards.home(ga) == it_board and boards.board_query(ga, it_board) == ""
    assert boards.board_query(ga, board) == "?board=ops" and boards.board_query(na, it_board) == "?board=it"
    keeper = User.objects.create_user("opadm", password=None, name="가상관리")  # 부서 없음, 운영팀 관리 그룹
    keeper.groups.add(board.admin_group)
    assert boards.home(keeper) == board  # 내가 관리하는 첫 근무표
    assert boards.home(admin_user) == it_board
    assert boards.home(User.objects.create_user("nobody", password=None, name="가상무")) == it_board  # 첫 근무표


def test_roster_board_order_and_memory(client, two):
    board, ga, _ = two
    client.force_login(ga)
    assert "가상다" in client.get(WEEK).content.decode()
    body = client.get(WEEK + "&board=ops").content.decode()
    assert "가상나" in body and "가상다" not in body
    assert RosterPref.objects.get(user=ga).board == board
    assert "가상나" in client.get(WEEK).content.decode()  # ?board= 가 없으면 기억한 근무표
    assert "가상다" in client.get(WEEK + "&board=it").content.decode()
    assert RosterPref.objects.get(user=ga).board is None  # 내 근무표를 고르면 기억을 비운다
    assert client.get("/?board=nope").status_code == 404


def test_board_buttons_only_with_two_boards(client, depts, request):
    client.force_login(member("it01", "가상가", depts["MEMS"]))
    assert 'aria-label="근무표"' not in client.get("/").content.decode()  # 근무표가 하나면 그리지 않는다
    request.getfixturevalue("ops")
    body = client.get("/").content.decode()
    assert 'aria-label="근무표"' in body
    assert body.index('aria-current="page">IT 당번표</a>') < body.index(">운영팀</a>") < body.index(">주간</a>")  # id 순, 주간/월간 앞
    assert "?board=ops&amp;view=week&amp;date=" in body


# ── 보기 전용·필터 ──

def test_view_only_other_board(client, two):
    _, ga, _ = two
    client.force_login(ga)
    body = client.get(WEEK + "&board=ops").content.decode()
    assert "보기 전용" in body and 'class="cell"' not in body and "칸을 누르면" not in body
    day = client.get(f"/day/{D}/?board=ops").content.decode()
    assert "보기 전용" in day and "가상나" in day and "바꾸기</summary>" not in day
    mine = client.get(WEEK + "&board=it").content.decode()
    assert "보기 전용" not in mine and 'class="cell"' in mine


def test_other_board_admin_gets_board_links(client, two):
    board, ga, _ = two
    ga.groups.add(board.admin_group)  # IT 사람이면서 운영팀 관리자: 편집은 되지만 내 근무표는 아니다
    client.force_login(ga)
    body = client.get(WEEK + "&board=ops").content.decode()
    assert "보기 전용" not in body
    assert f'href="/day/{D}/?board=ops#dawn"' in body  # 칸 링크
    assert f'hx-get="/cell/{D}/dawn/?next=' in body and "&amp;board=ops" in body  # htmx 주소
    assert f'href="/memo/day/{D}/?board=ops"' in body
    assert 'name="board" value="ops"' in body  # 필터 폼
    assert "?board=ops&amp;view=week&amp;date=2026-11-09" in body  # 날짜 이동
    mine = client.get(WEEK + "&board=it").content.decode()
    assert f'href="/day/{D}/#dawn"' in mine and 'name="board"' not in mine  # 내 근무표는 ?board= 없이 그대로


def test_other_board_shows_all_and_keeps_my_filters(client, two):
    board, ga, _ = two
    ga.groups.add(board.admin_group)  # 관리자라도 내 근무표가 아니면 필터 없이
    client.force_login(ga)
    client.get(WEEK + "&f=1&dept=MEMS")
    assert RosterPref.objects.get(user=ga).depts == ["MEMS"]
    body = client.get(WEEK + "&board=ops&f=1&dept=TMCH&hist=0").content.decode()
    assert "가상나" in body and "<legend>부서</legend>" not in body and "<legend>보기</legend>" in body
    p = RosterPref.objects.get(user=ga)
    assert p.depts == ["MEMS"] and p.history is False  # 필터는 그대로, 변경 내역 표시는 따른다
    assert "<legend>부서</legend>" in client.get(WEEK + "&board=it").content.decode()


def test_board_without_slots_has_no_type_filter(client, two):
    """유형 필터는 켜진 관제 정의가 있는 근무표에만(Codex 계획 리뷰). 관제 없는 근무표에서는 저장된 유형 값을 무시한다."""
    board, _, na = two
    RosterPref.objects.create(user=na, types=["개발자"])  # 가상나는 직원: 이 값이 먹으면 가상나가 숨는다
    client.force_login(na)
    body = client.get(WEEK).content.decode()
    assert "<legend>부서</legend>" in body and "<legend>유형</legend>" not in body and "가상나" in body
    assert "가상나" in client.get(f"/day/{D}/").content.decode()
    assert "가상나" in client.get(WEEK + "&f=1&type=개발자").content.decode()  # 요청 값도 무시


# ── /day/·/cell/·/memo/ ──

def test_day_cell_memo_use_board_query(client, two):
    board, ga, na = two
    ga.groups.add(board.admin_group)
    nb = member("op02", "가상라", na.department)
    client.force_login(ga)
    client.get(WEEK + "&board=ops")  # 근무표 화면의 기억은 /day/ 가 읽지 않는다(알림 링크는 늘 내 근무표)
    assert "가상다" in client.get(f"/day/{D}/").content.decode()
    body = client.get(f"/day/{D}/?board=ops").content.decode()
    assert f'action="/cell/{D}/dawn/?board=ops"' in body
    assert 'href="/day/2026-11-13/?board=ops&amp;f=1' in body  # 앞 날짜
    assert f'value="/day/{D}/?board=ops"' in body  # 저장 뒤 돌아올 주소
    r = client.post(f"/cell/{D}/dawn/?board=ops", {"before": na.username, "after": nb.username})
    assert r.url == f"/day/{D}/?board=ops"
    assert Commute.objects.get(period__board=board, date=D).member == nb
    assert client.get(f"/memo/day/{D}/").status_code == 404  # IT 관리자는 아니다
    assert f'action="/memo/day/{D}/?board=ops"' in client.get(f"/memo/day/{D}/?board=ops").content.decode()
    r = client.post(f"/memo/day/{D}/?board=ops", {"text": "가상 메모"})
    assert r.url == f"/day/{D}/?board=ops" and Memo.objects.get().board == board


# ── 알림 링크 ──

def test_plan_link_query_keeps_hash():
    day = Day(D, 1, {}, {**{c: [] for c in KEYS}, "dawn": ["가상가"]}, {})
    now = datetime(2026, 11, 15, 18)  # plan 은 naive 시각
    base = RuleSpec(1, None, "report", "days", 1, 18 * 60, ("telegram",), (), (), ())
    dues = [plan(IT_DEFS, [r], [day], {}, {}, now, destinations={(1, "telegram"): ["9"]})[0]
            for r in (base, RuleSpec(**{**base.__dict__, "query": "?board=ops"}))]
    assert [x.url for x in dues] == [f"/day/{D}/", f"/day/{D}/?board=ops"]
    assert dues[0].content_hash == dues[1].content_hash and dues[0].text == dues[1].text


def test_report_link_has_board_only_for_other_board(env, settings, depts, it_board, ops):
    settings.SITE_URL = "https://duty.example"
    board, dept = ops
    it, op = person("가상아이", depts["MEMS"], "111"), person("가상운영", dept, "222")
    AlarmRule.objects.filter(user__in=[it, op]).delete()
    published(it_board, (it, "dawn"))
    published(board, (op, "dawn"))
    for b in (it_board, board):
        AlarmRule.objects.create(user=it, kind="report", board=b, timing="days", offset=1, at_minute=18 * 60,
                                 telegram=True, shifts=[], depts=[], types=[])
    alarm_runner.tick(SUN18)
    assert sorted(t.rsplit("\n", 1)[1] for _, t in env) == [
        "https://duty.example/day/2026-11-16/", "https://duty.example/day/2026-11-16/?board=ops"]


def test_change_notice_link_by_recipient_board(env, settings, depts, ops):
    settings.SITE_URL = "https://duty.example"
    board, dept = ops
    a, b = person("가상운영", dept, "222"), person("가상운영둘", dept, "333")
    p = published(board, (b, "dawn"))
    a.department = depts["MEMS"]  # IT 로 옮겨 간 사람에게는 운영팀 링크에 ?board=ops
    a.save()
    ChangeLog.objects.create(period=p, date=D, cell="dawn", before=a, after=b)
    change_notice.tick(timezone.now())
    assert sorted((c, t.rsplit("\n", 1)[1]) for c, t in env) == [
        ("222", "https://duty.example/day/2026-11-16/?board=ops"), ("333", "https://duty.example/day/2026-11-16/")]


# ── 이력 ──

def test_change_log_board_column_and_filter(admin_client_ok, admin_user, two, it_board):
    board, _, na = two
    da = User.objects.get(name="가상다")
    ChangeLog.objects.create(period=Period.objects.get(board=it_board), date=D, cell="dawn", before=da, after=None)
    ChangeLog.objects.create(period=Period.objects.get(board=board), date=D, cell="dawn", before=na, after=None)
    body = admin_client_ok.get("/changes/").content.decode()
    assert "<th>근무표</th>" not in body and "가상다" in body and "가상나" not in body  # IT 만 관리: 열·필터 없음
    admin_user.groups.add(board.admin_group)
    body = admin_client_ok.get("/changes/").content.decode()
    assert "<th>근무표</th>" in body and '<td class="nw">운영팀</td>' in body and '<option value="ops">운영팀</option>' in body
    body = admin_client_ok.get("/changes/?board=ops").content.decode()
    assert "가상나" in body and "가상다" not in body and '<option value="ops" selected>' in body


# ── 알림 규칙 화면 ──

def test_rule_initial_all_uses_owner_board(two):
    board, _, na = two
    rule = AlarmRule.objects.create(user=na, kind="personal", timing="before_start", offset=120, telegram=True,
                                    shifts=[], depts=[], types=[])
    init = RuleForm.initial_from(rule)
    assert init["board"] == board.pk and init["shifts"] == ["dawn", "normal", "dinner"] and init["depts"] == ["OPS"]
    assert [c for c, _ in RuleForm(initial=init, user=na).fields["shifts"].choices] == init["shifts"]


def test_rule_form_report_depts_follow_board(two):
    board, _, _ = two
    f = RuleForm({**FORM, "kind": "report", "board": str(board.pk)})
    assert [c for c, _ in f.fields["depts"].choices] == ["OPS"]
    assert not RuleForm({**FORM, "kind": "report", "board": str(board.pk), "depts": ["MEMS"]}).is_valid()


def test_rule_page_redraws_without_saving(client, two):
    board, ga, _ = two
    client.force_login(ga)
    r = client.post("/alarms/rules/new/", {**FORM, "kind": "report", "board": str(board.pk), "hours": "3",
                                           "shifts": ["night"], "redraw": "1"})
    assert r.status_code == 200 and not AlarmRule.objects.filter(kind="report").exists()
    init = r.context["form"].initial
    assert init["shifts"] == ["dawn", "normal", "dinner"] and init["depts"] == ["OPS"] and init["hours"] == "3"
    assert 'value="night"' not in r.content.decode()
