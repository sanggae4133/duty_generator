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
    assert RosterPref.objects.get(user=ga).boards == ["ops"]
    assert "가상나" in client.get(WEEK).content.decode()  # ?board= 가 없으면 기억한 근무표
    assert "가상다" in client.get(WEEK + "&board=it").content.decode()
    assert RosterPref.objects.get(user=ga).boards == []  # 내 근무표를 고르면 기억을 비운다
    assert client.get("/?board=nope").status_code == 404


def test_board_picker_only_with_two_boards(client, depts, request):
    client.force_login(member("it01", "가상가", depts["MEMS"]))
    assert 'class="board-pick"' not in client.get("/").content.decode()  # 근무표가 하나면 그리지 않는다
    request.getfixturevalue("ops")
    body = client.get("/").content.decode()
    assert 'class="board-pick"' in body and body.index('class="board-pick"') < body.index(">주간</a>")


# ── 보기 전용·필터 ──

def test_view_only_other_board(client, two):
    _, ga, _ = two
    client.force_login(ga)
    body = client.get(WEEK + "&board=ops").content.decode()
    assert "보기 전용" in body and 'class="cell"' not in body and "칸을 누르면" not in body
    day = client.get(f"/day/{D}/?board=ops").content.decode()
    assert "보기 전용" in day and "가상나" in day and "바꾸기</summary>" not in day
    assert '<a class="to-mine" role="button" href="/?board=it">보기 전용 · 내 근무표로</a>' in body  # 크게, 내 근무표로 돌아가기
    assert f'<a class="to-mine" role="button" href="/?board=it&amp;date={D}">보기 전용 · 내 근무표로</a>' in day
    mine = client.get(WEEK + "&board=it").content.decode()
    assert "보기 전용" not in mine and 'class="cell"' in mine
    assert RosterPref.objects.get(user=ga).boards == []  # 그 링크(?board=내 근무표)는 기억한 근무표를 비운다


def test_view_only_home_board_has_no_back_link(client, two):
    client.force_login(User.objects.create_user("nobody", password=None, name="가상무"))  # 부서 없음: 내 근무표 = 첫 근무표(IT)
    body = client.get(WEEK).content.decode()
    assert "보기 전용" in body and 'class="to-mine"' not in body  # 지금이 내 근무표면 돌아갈 곳이 없다
    assert 'class="to-mine"' in client.get(WEEK + "&board=ops").content.decode()


def test_other_board_admin_gets_board_links(client, two):
    board, ga, _ = two
    ga.groups.add(board.admin_group)  # IT 사람이면서 운영팀 관리자: 편집은 되지만 내 근무표는 아니다
    client.force_login(ga)
    body = client.get(WEEK + "&board=ops").content.decode()
    assert "보기 전용" not in body
    assert f'href="/day/{D}/?board=ops#dawn"' in body  # 칸 링크
    assert f'hx-get="/cell/{D}/dawn/?next=' in body and "&amp;board=ops" in body  # htmx 주소
    assert f'href="/memo/day/{D}/?board=ops"' in body
    assert 'type="hidden" name="board" value="ops"' in body  # 필터 폼(드롭다운 체크박스와 구분)
    assert "?board=ops&amp;view=week&amp;date=2026-11-09" in body  # 날짜 이동
    mine = client.get(WEEK + "&board=it").content.decode()
    assert f'href="/day/{D}/#dawn"' in mine and 'type="hidden" name="board"' not in mine  # 내 근무표는 ?board= 없이 그대로


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


def test_memo_delete_form_keeps_board_query(client, two, it_board):
    """두 근무표 관리자가 남의 근무표 메모 창에서 지우면 그 근무표 메모만 지운다(지우기 폼 주소에도 ?board=)."""
    import re
    board, ga, _ = two
    ga.groups.add(board.admin_group, it_board.admin_group)
    Memo.objects.create(board=it_board, scope="day", date=D, text="IT 메모")
    Memo.objects.create(board=board, scope="day", date=D, text="운영 메모")
    client.force_login(ga)
    page = client.get(f"/memo/day/{D}/?board=ops").content.decode()
    action = re.findall(r'<form method="post" action="([^"]+)"', page)[-1]  # 위험 구역의 지우기 폼
    assert action == f"/memo/day/{D}/?board=ops"
    client.post(action, {"delete": "1"})
    assert list(Memo.objects.values_list("board__code", flat=True)) == ["it"]


def test_member_cannot_edit_other_board_by_forged_query(client, two, it_board):
    """일반 멤버가 ?board=<남의 근무표>를 붙여 보내도 근무 변경·사유·메모 저장·지우기는 아무것도 바꾸지 않는다."""
    from duty.models import DutyAssignment
    board, ga, na = two
    da = Commute.objects.get(period__board=it_board, date=D).member
    Memo.objects.create(board=it_board, scope="day", date=D, text="IT 메모")

    def counts():
        return [x.objects.count() for x in (Commute, DutyAssignment, ChangeLog, Memo)], \
            list(Commute.objects.values_list("member_id", "reason").order_by("pk")), list(Memo.objects.values_list("text"))

    before = counts()
    client.force_login(na)
    r = client.post(f"/cell/{D}/dawn/?board=it", {"before": da.username, "after": ga.username})
    assert r.status_code == 403
    r = client.post(f"/cell/{D}/dawn/?board=it", {"set_reason": "1", "member": str(da.pk), "reason": "휴가"})
    assert r.status_code == 403
    assert client.post(f"/memo/day/{D}/?board=it", {"text": "가짜"}).status_code == 404
    assert client.post(f"/memo/day/{D}/?board=it", {"delete": "1"}).status_code == 404
    assert counts() == before


def test_change_notice_home_once_per_recipient(env, depts, ops, monkeypatch):
    """변경 알림 링크의 내 근무표는 받는 사람마다 한 번만 찾는다(기록마다 다시 조회하지 않게)."""
    board, dept = ops
    a, b = person("가상운영", dept, "222"), person("가상운영둘", dept, "333")
    p = published(board, (b, "dawn"))
    for cell in ("dawn", "normal", "dinner"):
        ChangeLog.objects.create(period=p, date=D, cell=cell, before=a, after=b)
    calls = []
    real = boards.home
    monkeypatch.setattr(boards, "home", lambda u: calls.append(u.pk) or real(u))
    change_notice.tick(timezone.now())
    assert sorted(calls) == sorted([a.pk, b.pk]) and len(env) == 6


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


def test_week_head_weekday_and_cell_form_without_slots(client, two):
    """좁은 화면은 요일 머리가 숨으니 날짜 옆에 요일을, 관제가 없는 근무표의 사유 안내에는 '관제'를 빼고(4단계 점검)."""
    board, ga, na = two
    client.force_login(na)
    assert "11/16 (월)" in client.get(WEEK + "&board=ops").content.decode()
    form = client.get(f"/cell/{D}/dawn/?board=ops").content.decode()
    assert "(알림·캘린더에서 빠짐)" in form and "관제" not in form
