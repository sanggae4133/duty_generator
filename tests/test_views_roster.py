import re
from datetime import date, time

import pytest

from duty.models import Commute, DutyAssignment, Period
from duty.models import Board, BoardShift, Department, User
from tests.it_defs import OPS_STEPS

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


def publish_more(member, *days):
    """world 의 배포 회차에 날짜를 더한다(배포된 근무표가 있는 날만 편집 링크가 생긴다)."""
    p = Period.objects.get()
    p.start_date = min(p.start_date, *days)  # 기간 밖 행은 그날의 주인(설계 6.1)이 없어 보이지 않는다
    p.end_date = date(2026, 12, 31)
    p.save()
    for x in days:
        Commute.objects.create(period=p, date=x, member=member, shift="normal")


def test_anonymous_redirected_to_login(client, db):
    r = client.get("/")
    assert r.status_code == 302 and r.url.startswith("/login/")


def test_roster_shows_names_and_highlight(client, world):
    a, _ = world
    client.force_login(a)
    r = client.get("/?q=가")
    body = r.content.decode()
    assert r.status_code == 200 and '<span class="tk me hl1">가</span>' in body  # 로그인한 본인 = me
    assert '<span class="tk hl1">나' not in body


def test_second_name_gets_hl2(client, world):
    a, _ = world
    client.force_login(a)
    body = client.get("/?q1=가&q2=나").content.decode()
    assert '<span class="tk me hl1">가</span>' in body and '<span class="tk hl2">나</span>' in body


def test_name_inside_chain_highlights(client, world, make_member):
    a, _ = world
    c = make_member("다")
    client.force_login(a)
    client.post(f"/cell/{D}/normal/", {"before": a.username, "after": c.username})
    body = client.get("/?q3=다").content.decode()
    body = body.replace("&gt;", ">")
    assert '"><span class="tk old"><s>가</s></span><span class="ar">></span><span class="tk hl3">다</span></span>' in body
    assert '<span class="lb chg" data-d=' in body
    assert "changed" not in body.split("<body")[1].split("<script")[0]  # 셀 배경 클래스 없음


def test_highlighted_struck_name_keeps_both(client, world, make_member):
    a, _ = world
    c = make_member("다")
    client.force_login(a)
    client.post(f"/cell/{D}/normal/", {"before": a.username, "after": c.username})
    body = client.get("/?q1=가").content.decode()
    assert '<span class="tk old hl1"><s>가</s></span>' in body


def test_cells_use_nowrap_lines(client, world):
    a, _ = world
    client.force_login(a)
    assert '<div class="line">' in client.get("/").content.decode()


def test_week_view_default(client, world):
    a, _ = world
    publish_more(a, *[date(2026, 11, d) for d in (9, 11, 12, 13)])
    client.force_login(a)
    body = client.get("/").content.decode()
    for d in range(9, 14):
        assert f"/day/2026-11-{d:02d}/" in body
    assert "새벽" in body and "석식교대" in body and "관제" in body and "08:30" in body and 'class="sec slot k-slot"' in body
    assert "<th scope=" not in body and body.count('class="sec k-') == 5 * 4  # 행 라벨 열 없음, 날짜마다 4개 구역
    assert 'id="today"' in body and "/cell/2026-11-10/normal/" in body and "/cell/2026-11-10/slot0/" in body
    assert "/cell/2026-11-13/night/" in body  # 미래일도 편집 가능


def test_month_view(client, world):
    a, _ = world
    publish_more(a, date(2026, 11, 2), date(2026, 11, 30), date(2026, 12, 1))
    client.force_login(a)
    body = client.get("/?view=month&date=2026-11-10").content.decode()
    assert "2026년 11월" in body and "/day/2026-11-30/" in body and "/day/2026-11-02/" in body
    assert 'id="today"' in body and "08:30 " in body
    assert "/cell/2026-11-10/normal/?next=/%3Fview%3Dmonth" in body and "/cell/2026-11-30/night/" in body
    assert "/cell/2026-11-02/" not in body  # 지난 날은 일반 멤버 편집 불가
    dec = client.get("/?view=month&date=2026-12-10").content.decode()
    assert "/cell/2026-12-01/normal/" in dec and "/cell/2026-11-30/" not in dec  # 흐린 칸은 편집 불가


@pytest.mark.parametrize("view,prev,nxt", [("week", "2026-11-02", "2026-11-16"), ("month", "2026-10-01", "2026-12-01")])
def test_prev_next_links_keep_names(client, world, view, prev, nxt):
    a, _ = world
    client.force_login(a)
    body = client.get(f"/?view={view}&date=2026-11-10&q1=가&q3=나").content.decode().replace("&amp;", "&")
    for d in (prev, nxt):
        assert f"?view={view}&date={d}&q1=%EA%B0%80&q3=%EB%82%98" in body


def test_past_cells_not_editable_for_member_in_week(client, world, fixed_today):
    a, _ = world
    fixed_today(date(2026, 11, 12))
    publish_more(a, date(2026, 11, 12))
    client.force_login(a)
    body = client.get("/?date=2026-11-10").content.decode()
    assert "/cell/2026-11-10/" not in body and "/cell/2026-11-12/slot3/" in body


def test_invalid_date_falls_back_to_today(client, world):
    a, _ = world
    client.force_login(a)
    assert "/day/2026-11-10/" in client.get("/?date=nope").content.decode()


def test_cell_form_partial(client, world):
    a, _ = world
    client.force_login(a)
    r = client.get(f"/cell/{D}/normal/")
    assert r.status_code == 200 and 'name="before"' in r.content.decode()


def test_change_via_post(client, world, make_member):
    a, _ = world
    c = make_member("다")
    client.force_login(a)
    r = client.post(f"/cell/{D}/normal/", {"before": a.username, "after": c.username, "next": "/"})
    assert r.status_code == 302 and r.url == "/"
    assert Commute.objects.filter(date=D, member=c, shift="normal").exists()


def test_past_date_change_forbidden_for_member(client, world, fixed_today, make_member):
    a, _ = world
    c = make_member("다")
    fixed_today(date(2026, 11, 11))
    client.force_login(a)
    r = client.post(f"/cell/{D}/normal/", {"before": a.username, "after": c.username})
    assert r.status_code == 403


def test_unknown_member_code_is_rejected(client, world):
    a, _ = world
    client.force_login(a)
    r = client.post(f"/cell/{D}/normal/", {"before": a.username, "after": "NO_SUCH"})
    assert r.status_code == 302
    assert Commute.objects.filter(date=D, member=a, shift="normal").exists()


def test_swap_via_cell_dialog(client, world):
    """근무 변경 창에서 To 가 그날 다른 출근조면 맞교환된다(따로 있던 맞교환 화면은 없앴다)."""
    a, b = world  # 가=정상, 나=석식교대
    client.force_login(a)
    r = client.post(f"/cell/{D}/normal/", {"before": a.username, "after": b.username})
    assert r.status_code == 302
    assert Commute.objects.get(date=D, member=a).shift == "dinner" and Commute.objects.get(date=D, member=b).shift == "normal"
    assert client.get(f"/swap/{D}/").status_code == 404


def test_remove_only_with_sentinel(client, world):
    a, _ = world
    client.force_login(a)
    client.post(f"/cell/{D}/normal/", {"before": a.username, "after": "-"})
    assert not Commute.objects.filter(date=D, member=a).exists()


def test_day_page(client, world):
    a, _ = world
    client.force_login(a)
    body = client.get(f"/day/{D}/").content.decode()
    assert "08:30~09:30" in body and 'name="a"' not in body  # 따로 있던 맞교환 폼은 없다


def test_dept_page_removed(client, world):
    a, _ = world
    client.force_login(a)
    assert client.get("/dept/it/").status_code == 404
    assert "부서별" not in client.get("/").content.decode()


def test_me(client, world):
    a, _ = world
    client.force_login(a)
    body = client.get("/me/").content.decode()
    assert "정상" in body and "08:30~09:30" in body


@pytest.mark.parametrize("view", ["week", "month"])
@pytest.mark.parametrize("bad", ["9999-12-31", "0001-01-01", "1999-12-31", "2100-01-01"])
def test_extreme_dates_fall_back_to_today(client, world, view, bad):
    a, _ = world
    client.force_login(a)
    r = client.get(f"/?view={view}&date={bad}")
    assert r.status_code == 200 and "/day/2026-11-10/" in r.content.decode()


@pytest.mark.parametrize("date_,view,prev,nxt", [
    ("2026-12-15", "month", "2026-11-01", "2027-01-01"),
    ("2026-01-15", "month", "2025-12-01", "2026-02-01"),
    ("2026-03-31", "month", "2026-02-01", "2026-04-01"),
    ("2026-03-31", "week", "2026-03-23", "2026-04-06"),
])
def test_prev_next_date_math(client, world, date_, view, prev, nxt):
    a, _ = world
    client.force_login(a)
    body = client.get(f"/?view={view}&date={date_}").content.decode().replace("&amp;", "&")
    assert f'href="?view={view}&date={prev}"' in body and f'href="?view={view}&date={nxt}"' in body


def test_today_cell_only_in_current_month_view(client, world, fixed_today):
    a, _ = world
    fixed_today(date(2026, 11, 30))
    client.force_login(a)
    assert 'id="today"' not in client.get("/?view=month&date=2026-12-10").content.decode()  # 11/30은 12월 달력의 흐린 칸
    assert 'id="today"' in client.get("/?view=month&date=2026-11-20").content.decode()


@pytest.fixture
def two_depts(world, make_member):
    a, _ = world
    from duty.models import Commute, Period

    c = make_member("라", dept="UI")
    Commute.objects.create(period=Period.objects.get(), date=D, member=c, shift="normal")
    return a, c


def _lb(body: str, name: str) -> tuple[str, str] | None:
    """이름표의 필터 표시(data-d=부서, data-t=유형). 브라우저(roster.js)가 이 값으로 숨긴다."""
    m = re.search(r'<span class="lb[^"]*" data-d="([^"]*)" data-t="([^"]*)">(?:(?!</span></span>).)*?<span class="tk[^"]*">(?:<s>)?' + name + "<", body)
    return (m.group(1), m.group(2)) if m else None


@pytest.mark.parametrize("view", ["week", "month"])
def test_dept_filter_marks_instead_of_hiding(client, two_depts, view):
    """필터는 서버가 거르지 않는다: 모두 그리고 부서·유형을 붙인다. 체크 상태는 주소(그리고 저장값)를 따른다."""
    a, _ = two_depts
    client.force_login(a)
    body = client.get(f"/?view={view}&dept=UI").content.decode()
    grid = body.split("<tbody>")[1].split("</tbody>")[0]
    assert _lb(grid, "라") == ("UI", "개발자") and _lb(grid, "가") == ("MEMS", "개발자")
    assert [k for k, v in _checked(body).items() if v and k[0] == "dept"] == [("dept", "UI")]


def test_links_carry_only_view_date_and_names(client, two_depts):
    """◀ ▶·주간/월간 링크는 필터를 싣지 않는다(필터는 브라우저가 바꾸고 /prefs/ 로 저장, 링크는 저장값을 따른다)."""
    a, _ = two_depts
    client.force_login(a)
    body = client.get("/?dept=UI&dept=MD&q1=라").content.decode().replace("&amp;", "&")
    nav = body.split('class="cal-nav"')[1].split('id="flt-panel"')[0]
    assert "dept=" not in nav and "q1=%EB%9D%BC" in nav
    assert "dept=" not in body.split('id="roster-root"')[1]  # 팝업 URL 의 부서는 roster.js 가 지금 필터로 붙인다


@pytest.fixture
def mixed(world, make_member):
    from duty.models import Commute, Period

    a, _ = world
    c = make_member("라", dept="MEMS", type="직원")
    Commute.objects.create(period=Period.objects.get(), date=D, member=c, shift="normal")
    return a, c


@pytest.mark.parametrize("view", ["week", "month"])
def test_type_marked_and_combination_saved(client, mixed, view):
    a, _ = mixed
    client.force_login(a)
    body = client.get(f"/?view={view}&type=직원&dept=MEMS").content.decode()
    grid = body.split("<tbody>")[1].split("</tbody>")[0]
    assert _lb(grid, "라") == ("MEMS", "직원") and _lb(grid, "가") == ("MEMS", "개발자")
    assert [k for k, v in _checked(body).items() if v] == [("dept", "MEMS"), ("type", "직원")]


def test_popup_filtered_by_type(client, mixed):
    a, c = mixed
    client.force_login(a)
    popup = client.get(f"/cell/{D}/normal/?type=직원").content.decode()
    assert f'<option value="{c.username}">' in popup and f'<option value="{a.username}">' not in popup


def _checked(body: str) -> dict[tuple[str, str], bool]:
    found = re.findall(r'<input type="checkbox" name="(dept|type)" value="([^"]+)"( checked)?>', body)
    return {(n, v): bool(c) for n, v, c in found}


def test_popup_members_filtered_by_dept(client, two_depts):
    a, c = two_depts  # 가(MEMS)·라(UI) 모두 정상 칸 소속
    client.force_login(a)
    popup = client.get(f"/cell/{D}/normal/?dept=UI").content.decode()
    assert popup.count(f'<option value="{c.username}"') == 1 and f'<option value="{a.username}"' not in popup  # From 만(같은 칸 사람은 To 에서 뺀다)
    full = client.get(f"/cell/{D}/normal/").content.decode()
    assert f'<option value="{a.username}"' in full and f'<option value="{c.username}"' in full


@pytest.mark.parametrize("q", ["", "?dept=NOPE&type=외부", "?dept=&type="])
def test_empty_or_invalid_selection_shows_everyone(client, two_depts, q):
    a, _ = two_depts
    client.force_login(a)
    body = client.get("/" + q).content.decode()
    grid = body.split("<tbody>")[1].split("</tbody>")[0]
    assert "가" in grid and "라" in grid
    boxes = _checked(body)
    assert len(boxes) == 6 and all(boxes.values())


def test_selected_checkboxes_reflect_params(client, two_depts):
    a, _ = two_depts
    client.force_login(a)
    boxes = _checked(client.get("/?dept=UI&type=직원").content.decode())
    assert [k for k, v in boxes.items() if v] == [("dept", "UI"), ("type", "직원")]
    assert "모두 숨기면 전체 표시" in client.get("/").content.decode() and "→ ☐ 숨김" in client.get("/").content.decode()


def test_unknown_values_are_ignored_next_to_valid(client, two_depts):
    a, _ = two_depts
    client.force_login(a)
    body = client.get("/?dept=UI&dept=NOPE&type=외부").content.decode()
    assert "NOPE" not in body.split('class="cal-nav"')[1].split("</div>")[0]
    assert _checked(body)[("type", "직원")] and _checked(body)[("dept", "UI")]  # 잘못된 type만 줬으니 유형은 전체
    assert not _checked(body)[("dept", "MEMS")]


def test_removed_label_marked_by_its_department(client, two_depts):
    a, c = two_depts
    client.force_login(a)
    client.post(f"/cell/{D}/normal/", {"before": a.username, "after": ""})  # 가(MEMS) 제거 → 취소선(변경 내역)
    grid = client.get("/").content.decode().split("<tbody>")[1].split("</tbody>")[0]
    assert '<span class="lb chg rm" data-d="MEMS" data-t="개발자"><span class="tk old"><s>가</s></span></span>' in grid


def test_edge_dates_hide_prev_next(client, world):
    a, _ = world
    client.force_login(a)
    assert 'aria-label="이전 달"' not in client.get("/?view=month&date=2000-01-15").content.decode()
    assert 'aria-label="다음 달"' not in client.get("/?view=month&date=2099-12-15").content.decode()
    assert 'aria-label="이전 달"' in client.get("/?view=month&date=2000-02-15").content.decode()


def test_separate_move_and_search_buttons(client, world):
    a, _ = world
    client.force_login(a)
    body = client.get("/").content.decode()
    assert "<button>날짜로 이동</button>" in body and 'name="q1"' in body and "Today" not in body  # 이름 강조는 입력하면 바로


def test_today_link_survives_out_of_range_today(client, world, fixed_today):
    a, _ = world
    fixed_today(date(2100, 6, 1))
    client.force_login(a)
    r = client.get("/")
    assert r.status_code == 200 and 'href="?view=week&date=2100-06-01#today"' in r.content.decode().replace("&amp;", "&")


def test_candidates_exclude_departed_and_no_department(client, world, make_member, admin_user):
    a, b = world
    gone = make_member("퇴사", active=False)
    client.force_login(a)
    b.is_active = False  # 나: 퇴사했지만 기존 배정은 보인다
    b.save()
    popup = client.get(f"/cell/{D}/dinner/").content.decode()
    to = popup.split('name="after"')[1]
    assert f'value="{b.username}"' in popup.split('name="after"')[0]  # From 에는 기존 배정자
    for u in (b, gone, admin_user):
        assert f'value="{u.username}"' not in to
    assert f'value="{a.username}"' in to
    assert '<span class="tk hl1">나</span>' in client.get("/?q1=나").content.decode()  # 근무표 조회엔 그대로


def test_me_shift_filter(client, world):
    a, _ = world
    client.force_login(a)
    body = client.get("/me/?shift=slots").content.decode()  # 스케줄은 브라우저가 거른다: 다 그리고 체크만 주소대로
    assert ('<span class="what"><span class="w f" data-k="normal">정상 08:00~17:00</span>'
            '<span class="w" data-k="slots">장중관제 08:30~09:30</span></span>') in body
    assert re.search(r'value="slots" checked', body) and not re.search(r'value="normal" checked', body)
    assert 'id="me-empty"' in body and "requestSubmit" not in body  # 다 숨으면 보일 안내, 체크로 다시 부르지 않는다


def test_me_shows_holiday_and_no_work_days_gray(client, world, admin_user, it_board):
    from duty.models import Holiday
    from duty.services import memos
    a, _ = world
    publish_more(a, date(2026, 11, 13))  # 11/11·11/12 는 휴장일·근무 없음, 11/13 근무
    Holiday.objects.create(date=date(2026, 11, 11), name="임시 휴장일")
    it_board.admin_group.user_set.add(admin_user)
    memos.save(admin_user, it_board, "day", date(2026, 11, 12), "전산 점검", no_work=True)
    memos.save(admin_user, it_board, "day", date(2026, 12, 1), "", no_work=True)
    client.force_login(a)
    body = client.get("/me/").content.decode()
    assert '<li class="off"><a href="/day/2026-11-11/"><span class="when">11/11 (수)</span><span class="what">임시 휴장일</span>' in body
    assert '<span class="when">11/12 (목)</span><span class="what">전산 점검</span>' in body
    assert '<span class="when">12/1 (화)</span><span class="what">근무 없음</span>' in body
    assert body.index("11/11 (수)") < body.index("11/12 (목)") < body.index("11/13 (금)") < body.index("12/1 (화)")
    assert "12/2 (수)" not in body  # 근무 없는 보통 평일은 그대로 빠진다


def test_nav_brand_active_and_repo_link(client, world, settings):
    a, _ = world
    client.force_login(a)
    settings.REPO_URL = ""
    body = client.get("/me/").content.decode()
    assert "NXT 당번표" in body and "IT 당번표" not in body
    assert re.search(r'<a href="/me/" aria-current="page">내 근무</a>', body)
    assert 'aria-current="page">근무표' not in body
    assert "github" not in body.lower()
    settings.REPO_URL = "https://github.com/example/duty"
    body = client.get("/day/2026-11-10/").content.decode()
    assert re.search(r'<a href="/" aria-current="page">근무표</a>', body)  # 일자 화면도 근무표 메뉴
    assert 'href="https://github.com/example/duty"' in body and 'rel="noopener"' in body


def test_unpublished_day_has_no_edit_links(client, world):
    """배포된 근무표가 없는 날은 '근무표 없음'만, 편집 링크 없음(눌러도 저장 때 오류였다)."""
    a, _ = world
    client.force_login(a)
    body = client.get("/?view=week&date=2026-11-10").content.decode()
    assert body.count("근무표 없음") == 4  # 같은 주 월·수·목·금
    assert "/cell/2026-11-11/" not in body and "/cell/2026-11-10/" in body


def test_cell_form_defaults_to_swap(client, world, make_member):
    """기본은 맞교환: From 은 이 칸 사람, To 는 사람 선택(그날 근무 표시), 넣기·빼기는 맨 끝 + 확인창."""
    a, b = world  # 가=정상, 나=석식교대
    make_member("다", user=True)
    client.force_login(a)
    body = client.get(f"/cell/{D}/normal/").content.decode()
    before = body.split('name="before"')[1].split("</select>")[0]
    after = body.split('name="after"')[1].split("</select>")[0]
    assert before.strip().startswith(">") and f'<option value="{a.username}">가</option>' in before  # 첫 사람이 기본
    assert before.rstrip().endswith('<option value="+">(없음 — 새로 넣기만)</option>')
    assert '<option value="" disabled selected>바꿀 사람 선택</option>' in after
    assert re.search(r'<option value="[^"]+">나 · [^<]*\(석식교대\)</option>', after)
    assert re.search(r'<option value="[^"]+">다 · [^<]*\(근무 없음\)</option>', after)
    assert after.rstrip().endswith('<option value="-">(없음 — 빼기만)</option>')
    assert "맞바꿉니다" in body and "confirm(" in body and "<button>저장</button>" in body
    slot = client.get(f"/cell/{D}/slot0/").content.decode()
    assert 'value="+"' not in slot and 'value="-"' not in slot  # 관제 칸은 넣기·빼기 없음


def test_theme_switch_in_topbar(client, world):
    a, _ = world
    client.force_login(a)
    body = client.get("/me/").content.decode()
    head = body.split("</head>")[0]
    assert "duty-theme" in head.split('<link rel="stylesheet"')[0]  # 스타일보다 먼저 적용(깜빡임 없게)
    assert 'id="theme-btn"' in body and 'aria-label="화면 모드' in body
    assert "duty-theme" in client.get("/login/").content.decode()  # 로그인 화면도


def test_labels_and_cells_come_from_board_definitions(client, world, it_board):
    a, _ = world
    BoardShift.objects.filter(board=it_board, key="dinner").update(name="늦은조")
    BoardShift.objects.filter(board=it_board, key="slot0").update(name="08:31~09:30")
    client.force_login(a)
    week = client.get(f"/?view=week&date={D}").content.decode()
    assert "늦은조" in week and "08:31" in week
    day = client.get(f"/day/{D}/").content.decode()
    assert "<strong>늦은조</strong>" in day and "<strong>08:31~09:30</strong>" in day
    assert "석식교대" not in day
    assert "늦은조" in client.get("/me/").content.decode()  # 스케줄 선택지
    assert client.get(f"/cell/{D}/lunch/").status_code == 404  # 정의에 없는 칸


def _dept_codes(body: str) -> list[str]:
    return re.findall(r'name="dept" value="(\w+)"', body.split('id="xl-panel"')[0])  # 필터 상자만(엑셀 상자 빼고)


def test_views_use_own_board_departments_and_definitions(client, world, it_board):
    a, _ = world
    ops = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
    BoardShift.objects.create(board=ops, key="dawn", name="이른조", start=time(7), end=time(16))
    ops_dept = Department.objects.create(code="OPS", name="운영부서", shifts="dawn", board=ops)
    Department.objects.filter(code="UI").update(order=-1)
    client.force_login(a)
    assert _dept_codes(client.get("/").content.decode()) == ["UI", "MEMS", "TMCH", "MD"]  # 그 근무표 부서만, order 순
    assert _dept_codes(client.get(f"/day/{D}/").content.decode()) == ["UI", "MEMS", "TMCH", "MD"]
    Department.objects.create(code="AA", name="가", shifts="normal", board=it_board)  # 순서 칸을 비운 새 부서
    assert _dept_codes(client.get("/").content.decode())[-1] == "AA"  # 기본 99라 맨 뒤(옛 DEPT_ORDER 밖 부서와 같다)
    o = User.objects.create_user("OPS001", name="운영", department=ops_dept, part="", type="직원")
    client.force_login(o)
    week = client.get("/").content.decode()
    assert _dept_codes(week) == ["OPS"] and "이른조" in week and "석식교대" not in week
    me = client.get("/me/").content.decode()
    assert "이른조" in me and "석식교대" not in me
    assert client.get(f"/cell/{D}/dinner/").status_code == 404  # 운영팀 정의에 없는 칸
    client.force_login(a)
    assert "OPS001" not in client.get(f"/cell/{D}/normal/").content.decode()  # IT 칸 To 후보에 운영팀 사람 없음


@pytest.mark.parametrize("who,editable", [("it_admin", True), ("staff", False), ("ops_admin", False)])
def test_past_edit_follows_board_admin_group(client, world, fixed_today, it_board, who, editable):
    a, _ = world
    fixed_today(date(2026, 11, 12))
    if who == "it_admin":
        it_board.admin_group.user_set.add(a)
    elif who == "staff":
        a.is_staff = True
        a.save()
    else:  # 다른 근무표의 관리자라고 IT 근무표의 지난 날을 고칠 수는 없다
        Board.objects.create(code="ops", name="운영팀", **OPS_STEPS).admin_group.user_set.add(a)
    client.force_login(a)
    assert ("/cell/2026-11-10/" in client.get("/?date=2026-11-10").content.decode()) == editable
    assert ("바꾸기</summary>" in client.get("/day/2026-11-10/").content.decode()) == editable


def test_member_without_department_cannot_edit(client, world, admin_user):
    """부서 없는 계정은 근무표가 없어 보기만 한다(관리 그룹이면 고친다). 오늘 날짜도 같다."""
    nodept = User.objects.create_user("x", password="unused-Pw-123", name="무소속")
    client.force_login(nodept)
    assert "/cell/2026-11-10/" not in client.get("/?date=2026-11-10").content.decode()
    assert "바꾸기</summary>" not in client.get("/day/2026-11-10/").content.decode()
    client.force_login(admin_user)
    assert "바꾸기</summary>" in client.get("/day/2026-11-10/").content.decode()


def test_slot_popup_offers_keep_other_and_post_takes_both(client, world, make_member):
    a, b = world  # 가=slot0
    p = Period.objects.get()
    DutyAssignment.objects.create(period=p, date=D, cell="slot1", member=b)
    client.force_login(a)
    popup = client.get(f"/cell/{D}/slot0/").content.decode()
    assert 'name="keep_other"' in popup
    assert 'name="keep_other"' not in client.get(f"/cell/{D}/normal/").content.decode()  # 근무조 칸에는 없다
    client.post(f"/cell/{D}/slot0/", {"before": a.username, "after": b.username, "keep_other": "1"})
    assert set(DutyAssignment.objects.filter(member=b).values_list("cell", flat=True)) == {"slot0", "slot1"}


def test_my_chips_carry_schedule_key_for_browser_filter(client, world):
    """날짜 옆 내 근무 표시는 근무마다 하나씩(스케줄 키 data-k), roster.js 가 스케줄 체크로 거르고 첫 것만 보인다."""
    a, _ = world  # 가: 11/10 정상 + 관제 08:30
    client.force_login(a)
    body = client.get(f"/?date={D}").content.decode()
    assert '<span class="mychip" data-k="normal" title="내 근무: 정상">정<span class="sx">상</span></span>' in body
    assert '<span class="mychip x" data-k="slots" title="내 근무: 관제">관<span class="sx">제</span></span>' in body  # 둘째부터 숨김
    month = client.get(f"/?view=month&date={D}").content.decode()
    assert '<b id="mydays">1일</b>' in month


def test_month_starts_on_sunday_week_on_monday(client, world):
    a, _ = world
    client.force_login(a)
    head = lambda b: re.findall(r"<th[^>]*>(.)</th>", b.split("<thead>")[1].split("</thead>")[0])
    month = client.get(f"/?view=month&date={D}").content.decode()
    assert head(month) == list("일월화수목금토")
    assert month.split("<tbody>")[1].index("/day/2026-11-01/") < month.split("<tbody>")[1].index("/day/2026-11-02/")  # 11/1 일요일이 첫 칸
    assert "/day/2026-10-26/" not in month  # 월요일 시작이면 들어가던 앞 주
    assert head(client.get(f"/?view=week&date={D}").content.decode()) == list("월화수목금토일")


def test_today_has_blue_tag_distinct_from_my_days(client, world):
    """오늘은 파란 테두리 + '오늘' 꼬리표(내 근무 날의 분홍·빨강과 색과 글자로 구분)."""
    a, _ = world
    client.force_login(a)
    body = client.get(f"/?date={D}").content.decode()
    assert body.count('<span class="today-tag">오늘</span>') == 1
    assert 'id="today" class="today-col mine"' in body


def test_month_shows_adjacent_month_days_read_only(client, world):
    """월간의 앞뒤 달 날짜도 같은 조회 범위라 명단을 보인다(옅게, 칸은 못 바꾸고 'N월 내 근무'에 안 센다)."""
    a, _ = world
    publish_more(a, date(2026, 12, 1))
    client.force_login(a)
    body = client.get(f"/?view=month&date={D}").content.decode()
    other = body.split('data-day="/day/2026-12-01/"')[1].split("</td>")[0]
    assert '<span class="tk me">가</span>' in other and "/cell/2026-12-01/" not in body
    assert '<b id="mydays">1일</b>' in body  # 11/10 만(12/1 은 다른 달)


def test_swipe_nav_links_marked(client, world):
    a, _ = world
    client.force_login(a)
    body = client.get(f"/?date={D}").content.decode()
    assert 'data-nav="prev"' in body and 'data-nav="next"' in body  # roster.js 가 좌우 밀기로 누른다


def test_my_days_hidden_for_account_without_department(client, world, admin_user):
    client.force_login(admin_user)  # 부서 없는 관리자
    assert 'id="mydays"' not in client.get(f"/?view=month&date={D}").content.decode()
