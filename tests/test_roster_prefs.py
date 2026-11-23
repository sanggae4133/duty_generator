import pytest

from datetime import date

from duty.models import Commute, DutyAssignment, Period, RosterPref
from duty.services import prefs
from duty.shifts import is_slot_cell
from tests.it_defs import IT_DEFS

D = date(2026, 11, 10)


@pytest.fixture
def world(make_member, fixed_today, it_board):
    fixed_today(D)
    p = Period.objects.create(board=it_board, name="p", start_date=D, end_date=D, status=Period.Status.PUBLISHED)
    a, b = make_member("가", user=True), make_member("나", user=True)
    Commute.objects.create(period=p, date=D, member=a, shift="normal")
    Commute.objects.create(period=p, date=D, member=b, shift="dinner")
    DutyAssignment.objects.create(period=p, date=D, cell="slot0", member=a)
    return a, b


@pytest.fixture
def two_depts(world, make_member):
    c = make_member("라", dept="UI")
    Commute.objects.create(period=Period.objects.get(), date=D, member=c, shift="normal")
    return world[0], c


def grid(client, q=""):
    return client.get("/" + q).content.decode().split("<tbody>")[1].split("</tbody>")[0]


def flt(body):
    """필터 상자(브라우저가 거르는 기준)만."""
    return body.split('id="flt"')[1].split('id="xl-panel"')[0]


def test_shift_filter_marks_rows_and_checks_boxes(client, world):
    """스케줄 필터는 서버가 지우지 않고 칸마다 data-k 를 붙인다. 체크 상태는 주소를 따른다(roster.js 가 숨긴다)."""
    client.force_login(world[0])
    body = client.get("/?shift=normal").content.decode()
    g = body.split("<tbody>")[1].split("</tbody>")[0]
    assert 'class="sec k-normal" data-k="normal"' in g and 'class="sec k-dinner" data-k="dinner"' in g and 'data-k="slots"' in g
    assert 'value="normal" checked' in flt(body) and 'value="dinner" checked' not in flt(body)


def test_slots_toggle_is_all_control_cells(client, world):
    client.force_login(world[0])
    body = client.get("/?shift=slots").content.decode()
    assert '<details class="sec slot k-slot" data-k="slots">' in body and "08:30" in body
    assert 'value="slots" checked' in flt(body) and 'value="normal" checked' not in flt(body)


def test_invalid_shift_ignored(client, world):
    client.force_login(world[0])
    assert flt(client.get("/?shift=bogus").content.decode()).count(" checked") == 12


def test_fold_button_gone(client, world):
    client.force_login(world[0])
    body = client.get("/").content.decode()
    assert "slot-toggle" not in body and "slots-hidden" not in body  # 예전 관제 접기 버튼(localStorage 는 이제 화면 모드가 쓴다)


def test_links_do_not_carry_filters_and_keep_saved(client, world):
    """이동 링크는 보기·날짜만 싣는다. 그 링크(view 가 있다)를 눌러도 저장된 필터는 그대로다."""
    client.force_login(world[0])
    body = client.get("/?shift=normal").content.decode().replace("&amp;", "&")
    assert "shift=" not in body.split('class="cal-nav"')[1].split('id="flt-panel"')[0]
    client.get("/?view=month&date=2026-12-01")
    p = RosterPref.objects.get(user=world[0])
    assert p.shifts == ["normal"] and p.view == "month"


def test_prefs_endpoint_saves_filters_and_history(client, two_depts):
    a, _ = two_depts
    client.force_login(a)
    r = client.post("/prefs/", {"f": "1", "dept": "UI", "shift": "normal", "hist": ["0", "1"]})
    assert r.status_code == 204
    p = RosterPref.objects.get(user=a)
    assert (p.depts, p.shifts, p.history, p.view) == (["UI"], ["normal"], True, "week")
    client.post("/prefs/", {"hist": "0"})  # 필터 없이 변경 내역만: 필터는 그대로
    p.refresh_from_db()
    assert (p.depts, p.history) == (["UI"], False)
    assert client.get("/prefs/").status_code == 405


def test_prefs_endpoint_requires_login(client, db):
    assert client.post("/prefs/", {"f": "1"}).status_code == 302


def test_day_shift_filter(client, world):
    client.force_login(world[0])
    body = client.get(f"/day/{D}/?shift=normal").content.decode()
    assert 'id="normal"' in body and 'id="dinner"' not in body and 'id="slot0"' not in body
    body = client.get(f"/day/{D}/?shift=slots").content.decode()
    assert 'id="slot0"' in body and 'id="slot9"' in body and 'id="normal"' not in body


def test_day_dept_filter_names_and_cell_form(client, two_depts):
    a, c = two_depts
    client.force_login(a)
    body = client.get(f"/day/{D}/?dept=UI&shift=normal").content.decode()
    art = body.split('<article id="normal" class="dcell">')[1].split("</article>")[0]
    assert '<span class="lb"><span class="tk">라</span></span>' in art and '<span class="tk me">가</span>' not in art
    assert f'value="{c.username}"' in art and f'value="{a.username}"' not in art


def test_day_filter_form_and_nav_links(client, world):
    client.force_login(world[0])
    body = client.get(f"/day/{D}/?type=개발자").content.decode().replace("&amp;", "&")
    assert 'name="f" value="1"' in body and 'name="shift"' in body
    nav = body.split('<nav aria-label="날짜 이동">')[1].split("</nav>")[0]
    assert "type=%EA%B0%9C%EB%B0%9C%EC%9E%90" in nav


def test_saved_and_loaded(client, two_depts):
    a, _ = two_depts
    client.force_login(a)
    client.get("/?dept=UI&type=개발자&shift=normal&view=month")
    p = RosterPref.objects.get(user=a)
    assert (p.depts, p.types, p.shifts, p.view) == (["UI"], ["개발자"], ["normal"], "month")
    body = client.get("/").content.decode()  # 파라미터 없음 → 저장값
    assert "라" in body and 'value="normal" checked' in flt(body) and 'value="dinner" checked' not in flt(body) and "2026년 11월" in body


def test_f1_without_boxes_means_all_and_saves(client, two_depts):
    a, _ = two_depts
    client.force_login(a)
    client.get("/?dept=UI&shift=normal")
    body = client.get("/?f=1").content.decode()
    assert flt(body).count(" checked") == 12 and RosterPref.objects.get(user=a).depts == []


def test_all_checked_stored_as_empty(client, two_depts):
    a, _ = two_depts
    client.force_login(a)
    client.get("/?f=1&dept=MEMS&dept=TMCH&dept=MD&dept=UI")
    assert RosterPref.objects.get(user=a).depts == []


def test_per_user_isolation(client, world):
    a, b = world
    client.force_login(a)
    client.get("/?shift=normal")
    client.force_login(b)
    assert 'value="dinner" checked' in flt(client.get("/").content.decode())
    assert RosterPref.objects.get(user=a).shifts == ["normal"]


def test_day_does_not_overwrite_view_but_shares_filters(client, world):
    a, _ = world
    client.force_login(a)
    client.get("/?view=month")
    client.get(f"/day/{D}/?shift=dinner&view=week")
    p = RosterPref.objects.get(user=a)
    assert p.view == "month" and p.shifts == ["dinner"]
    body = client.get(f"/day/{D}/").content.decode()
    assert 'id="dinner"' in body and 'id="normal"' not in body


def test_defaults_without_prefs(client, world):
    client.force_login(world[0])
    body = flt(client.get("/").content.decode())  # 필터 상자만(엑셀 상자·흐리게 스위치 빼고)
    assert body.count('type="checkbox"') == 12 and body.count(" checked") == 12
    assert not RosterPref.objects.exists()


def test_stale_saved_prefs_fall_back_to_all(client, world):
    a, _ = world
    RosterPref.objects.create(user=a, depts=["GONE"], types=["외부"], shifts=["bogus"])
    client.force_login(a)
    body = client.get("/").content.decode()
    assert 'data-k="normal"' in body and flt(body).count(" checked") == 12  # 엑셀 상자 빼고


def test_unchanged_get_does_not_write(client, world):
    a, _ = world
    client.force_login(a)
    client.get("/?view=month&shift=normal")
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    with CaptureQueriesContext(connection) as ctx:
        client.get("/?view=month&shift=normal")
    assert not [q for q in ctx.captured_queries if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE"))]


# ── 변경 내역 표시 켬/끔 ──

@pytest.fixture
def changed(world, make_member):
    from duty.services import boards, changes
    a, b = world
    c = make_member("다", user=True)
    changes.change_cell(a, boards.it_board(), D, "normal", a, c)       # 가>다
    changes.change_cell(a, boards.it_board(), D, "dinner", b, None)    # 나 빠짐(취소선)
    return a


def test_history_shown_by_default(client, changed):
    client.force_login(changed)
    g = grid(client)
    assert "&gt;" in g and "<s>" in g and "chg" in g


def roots(client, q=""):
    return client.get("/" + q).content.decode().split('<div id="roster-root"')[1].split(">")[0]


def test_history_off_hides_by_class_and_is_saved(client, changed):
    """변경 내역을 끄면 표 전체에 nohist(CSS 가 A>· 취소선·사유를 숨긴다). 내용은 그대로 그린다."""
    client.force_login(changed)
    assert roots(client, "?f=1&hist=0") == ' class="nohist"'
    assert "&gt;" in grid(client) and RosterPref.objects.get(user=changed).history is False
    assert roots(client) == ' class="nohist"'  # 저장값
    day = client.get(f"/day/{D}/").content.decode()
    assert "<s>" not in day.split('<h4 class="grp">')[1]  # 하루 화면은 서버가 거른다
    assert roots(client, "?f=1&hist=0&hist=1") == ""  # 체크하면 hidden 0 뒤에 1 이 온다


def test_history_kept_when_link_has_no_hist(client, changed):
    client.force_login(changed)
    client.get("/?f=1&hist=0")
    assert roots(client, "?f=1&dept=MEMS") == ' class="nohist"'  # 날짜 이동 등 hist 없는 주소


def test_schedule_choices_follow_definitions():
    assert prefs.choices(IT_DEFS) == {
        "dawn": "새벽", "normal": "정상", "dinner": "석식교대", "night": "야간", "slots": "장중관제",
    }
    assert list(prefs.choices(IT_DEFS)) == ["dawn", "normal", "dinner", "night", "slots"]  # 화면 순서
    no_slots = [d for d in IT_DEFS if not is_slot_cell(d.key)]
    assert list(prefs.choices(no_slots)) == ["dawn", "normal", "dinner", "night"]  # 관제 없는 근무표엔 묶음 없음


# ── 흐리게(보임 / 흐리게 / 숨김): 부서·유형·스케줄·변경 내역 ──

def test_dim_saved_via_prefs_and_rendered(client, two_depts):
    """roster.js 가 fd=1 과 흐리게 값(ddim·tdim·sdim·hdim)을 보낸다. 흐리게도 '보임' 목록에 든다(엑셀·하루 화면은 보임으로)."""
    a, _ = two_depts
    client.force_login(a)
    client.post("/prefs/", {"f": "1", "fd": "1", "dept": ["MEMS", "UI"], "ddim": ["UI", "NOPE"], "sdim": "normal",
                            "hist": ["0", "1"], "hdim": "1"})
    p = RosterPref.objects.get(user=a)
    assert p.dims == {"dept": ["UI"], "type": [], "shift": ["normal"], "hist": True}  # 없는 값은 버린다
    body = client.get("/").content.decode()
    box = flt(body)
    assert 'name="dept" value="UI" checked data-state="dim"' in box and 'name="dept" value="MEMS" checked>' in box
    assert 'name="shift" value="normal" checked data-state="dim"' in box
    assert 'name="hist" value="1" checked data-state="dim"' in box
    assert '<div id="roster-root" class="histdim">' in body


def test_filter_form_without_fd_keeps_dims(client, two_depts):
    """하루 화면의 필터 폼(흐리게를 모른다)은 흐리게 값을 지우지 않는다."""
    a, _ = two_depts
    client.force_login(a)
    client.post("/prefs/", {"f": "1", "fd": "1", "sdim": "normal"})
    client.get(f"/day/{D}/?f=1&shift=normal&shift=dinner")
    p = RosterPref.objects.get(user=a)
    assert p.dims["shift"] == ["normal"] and p.shifts == ["normal", "dinner"]
