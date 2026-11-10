from datetime import date

import pytest

from duty.models import Commute, ControlDuty, Period

D = date(2026, 11, 10)


@pytest.fixture
def world(make_member, fixed_today):
    fixed_today(D)
    p = Period.objects.create(name="p", start_date=D, end_date=D, status=Period.Status.PUBLISHED)
    a, b = make_member("가", user=True), make_member("나", user=True)
    Commute.objects.create(period=p, date=D, member=a, shift="normal")
    Commute.objects.create(period=p, date=D, member=b, shift="dinner")
    ControlDuty.objects.create(period=p, date=D, slot=0, member=a)
    return a, b


def test_anonymous_redirected_to_login(client, db):
    r = client.get("/")
    assert r.status_code == 302 and r.url.startswith("/login/")


def test_roster_shows_names_and_highlight(client, world):
    a, _ = world
    client.force_login(a.user)
    r = client.get("/?q=가")
    body = r.content.decode()
    assert r.status_code == 200 and '<span class="hl1">가</span>' in body
    assert '<span class="hl1">나' not in body


def test_second_name_gets_hl2(client, world):
    a, _ = world
    client.force_login(a.user)
    body = client.get("/?q1=가&q2=나").content.decode()
    assert '<span class="hl1">가</span>' in body and '<span class="hl2">나</span>' in body


def test_name_inside_chain_highlights(client, world, make_member):
    a, _ = world
    c = make_member("다")
    client.force_login(a.user)
    client.post(f"/cell/{D}/normal/", {"before": a.code, "after": c.code})
    body = client.get("/?q3=다").content.decode()
    body = body.replace("&gt;", ">")
    assert '<span class="lb chg"><s>가</s>><span class="hl3">다</span></span>' in body
    assert "changed" not in body.split("<body")[1].split("<script")[0]  # 셀 배경 클래스 없음


def test_highlighted_struck_name_keeps_both(client, world, make_member):
    a, _ = world
    c = make_member("다")
    client.force_login(a.user)
    client.post(f"/cell/{D}/normal/", {"before": a.code, "after": c.code})
    body = client.get("/?q1=가").content.decode()
    assert '<span class="hl1"><s>가</s></span>' in body


def test_cells_use_nowrap_lines(client, world):
    a, _ = world
    client.force_login(a.user)
    assert '<div class="line">' in client.get("/").content.decode()


def test_week_view_default(client, world):
    a, _ = world
    client.force_login(a.user)
    body = client.get("/").content.decode()
    for d in range(9, 14):
        assert f"/day/2026-11-{d:02d}/" in body
    assert "새벽" in body and "석식교대" in body and "관제" in body and "08:30" in body and 'class="sec slot"' in body
    assert "<th scope=" not in body and body.count('class="sec"') == 5 * 4  # 행 라벨 열 없음, 날짜마다 4개 구역
    assert 'id="today"' in body and "/cell/2026-11-10/normal/" in body and "/cell/2026-11-10/slot0/" in body
    assert "/cell/2026-11-13/night/" in body  # 미래일도 편집 가능


def test_month_view(client, world):
    a, _ = world
    client.force_login(a.user)
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
    client.force_login(a.user)
    body = client.get(f"/?view={view}&date=2026-11-10&q1=가&q3=나").content.decode().replace("&amp;", "&")
    for d in (prev, nxt):
        assert f"?view={view}&date={d}&q1=%EA%B0%80&q3=%EB%82%98" in body


def test_past_cells_not_editable_for_member_in_week(client, world, fixed_today):
    a, _ = world
    fixed_today(date(2026, 11, 12))
    client.force_login(a.user)
    body = client.get("/?date=2026-11-10").content.decode()
    assert "/cell/2026-11-10/" not in body and "/cell/2026-11-12/slot3/" in body


def test_invalid_date_falls_back_to_today(client, world):
    a, _ = world
    client.force_login(a.user)
    assert "/day/2026-11-10/" in client.get("/?date=nope").content.decode()


def test_cell_form_partial(client, world):
    a, _ = world
    client.force_login(a.user)
    r = client.get(f"/cell/{D}/normal/")
    assert r.status_code == 200 and 'name="before"' in r.content.decode()


def test_change_via_post(client, world, make_member):
    a, _ = world
    c = make_member("다")
    client.force_login(a.user)
    r = client.post(f"/cell/{D}/normal/", {"before": a.code, "after": c.code, "next": "/"})
    assert r.status_code == 302 and r.url == "/"
    assert Commute.objects.filter(date=D, member=c, shift="normal").exists()


def test_past_date_change_forbidden_for_member(client, world, fixed_today, make_member):
    a, _ = world
    c = make_member("다")
    fixed_today(date(2026, 11, 11))
    client.force_login(a.user)
    r = client.post(f"/cell/{D}/normal/", {"before": a.code, "after": c.code})
    assert r.status_code == 403


def test_unknown_member_code_is_rejected(client, world):
    a, _ = world
    client.force_login(a.user)
    r = client.post(f"/cell/{D}/normal/", {"before": a.code, "after": "NO_SUCH"})
    assert r.status_code == 302
    assert Commute.objects.filter(date=D, member=a, shift="normal").exists()


def test_swap_via_post(client, world):
    a, b = world
    client.force_login(a.user)
    r = client.post(f"/swap/{D}/", {"a": f"normal|{a.code}", "b": f"dinner|{b.code}"})
    assert r.status_code == 302
    assert Commute.objects.get(date=D, member=a).shift == "dinner"


def test_day_page(client, world):
    a, _ = world
    client.force_login(a.user)
    body = client.get(f"/day/{D}/").content.decode()
    assert "08:30~09:30" in body and "맞교환" in body


def test_dept_page_removed(client, world):
    a, _ = world
    client.force_login(a.user)
    assert client.get("/dept/it/").status_code == 404
    assert "부서별" not in client.get("/").content.decode()


def test_me(client, world):
    a, _ = world
    client.force_login(a.user)
    body = client.get("/me/").content.decode()
    assert "정상" in body and "08:30~09:30" in body


@pytest.mark.parametrize("view", ["week", "month"])
@pytest.mark.parametrize("bad", ["9999-12-31", "0001-01-01", "1999-12-31", "2100-01-01"])
def test_extreme_dates_fall_back_to_today(client, world, view, bad):
    a, _ = world
    client.force_login(a.user)
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
    client.force_login(a.user)
    body = client.get(f"/?view={view}&date={date_}").content.decode().replace("&amp;", "&")
    assert f'href="?view={view}&date={prev}"' in body and f'href="?view={view}&date={nxt}"' in body


def test_today_cell_only_in_current_month_view(client, world, fixed_today):
    a, _ = world
    fixed_today(date(2026, 11, 30))
    client.force_login(a.user)
    assert 'id="today"' not in client.get("/?view=month&date=2026-12-10").content.decode()  # 11/30은 12월 달력의 흐린 칸
    assert 'id="today"' in client.get("/?view=month&date=2026-11-20").content.decode()


@pytest.fixture
def two_depts(world, make_member):
    a, _ = world
    from duty.models import Commute, Period

    c = make_member("라", dept="UI")
    Commute.objects.create(period=Period.objects.get(), date=D, member=c, shift="normal")
    return a, c


@pytest.mark.parametrize("view", ["week", "month"])
def test_dept_filter_hides_other_departments(client, two_depts, view):
    a, _ = two_depts
    client.force_login(a.user)

    def grid(q):
        return client.get(f"/?view={view}{q}").content.decode().split("<tbody>")[1].split("</tbody>")[0]

    assert "라" in grid("&dept=UI") and "가" not in grid("&dept=UI")
    assert "라" in grid("") and "가" in grid("")


def test_dept_carried_through_links_and_popup_url(client, two_depts):
    a, _ = two_depts
    client.force_login(a.user)
    body = client.get("/?dept=UI&dept=MD").content.decode().replace("&amp;", "&")
    assert "dept=UI&dept=MD" in body.split('class="cal-nav"')[1].split("</div>")[0]
    assert "dept=UI&dept=MD" in body.split("</form>")[1]  # next=… 와 &dept= 가 팝업 URL에 실린다
    assert "&dept=UI&dept=MD" in body.split("</form>")[1]


@pytest.fixture
def mixed(world, make_member):
    from duty.models import Commute, Period

    a, _ = world
    c = make_member("라", dept="MEMS", type="직원")
    Commute.objects.create(period=Period.objects.get(), date=D, member=c, shift="normal")
    return a, c


@pytest.mark.parametrize("view", ["week", "month"])
def test_type_filter_and_combination(client, mixed, view):
    a, _ = mixed
    client.force_login(a.user)

    def grid(q):
        return client.get(f"/?view={view}{q}").content.decode().split("<tbody>")[1].split("</tbody>")[0]

    assert "라" in grid("&type=직원") and "가" not in grid("&type=직원")
    assert "가" in grid("&type=개발자") and "라" not in grid("&type=개발자")
    assert "가" not in grid("&type=직원&dept=UI") and "라" not in grid("&type=직원&dept=UI")  # 둘 다 통과해야 표시
    assert "라" in grid("&type=직원&dept=MEMS")


def test_type_carried_and_popup_filtered(client, mixed):
    a, _ = mixed
    client.force_login(a.user)
    body = client.get("/?type=직원").content.decode().replace("&amp;", "&")
    assert "type=%EC%A7%81%EC%9B%90" in body.split('class="cal-nav"')[1].split("</div>")[0]
    assert "&type=%EC%A7%81%EC%9B%90" in body.split("</form>")[1]
    popup = client.get(f"/cell/{D}/normal/?type=직원").content.decode().split("<form")[1]
    assert "라" in popup and "가" not in popup.replace("From", "")
    assert client.get("/").content.decode().count('name="type"') == 2


def test_popup_members_filtered_by_dept(client, two_depts):
    a, _ = two_depts
    client.force_login(a.user)
    body = client.get(f"/cell/{D}/normal/?dept=UI").content.decode()
    assert "라" in body and "가" not in body.split("<form")[1].split("</form>")[0].replace("From", "")
    assert "가" in client.get(f"/cell/{D}/normal/").content.decode().split("<form")[1]


def test_dept_checkboxes_all_checked_by_default(client, two_depts):
    a, _ = two_depts
    client.force_login(a.user)
    body = client.get("/").content.decode()
    assert body.count('name="dept"') == 4 and body.count(" checked>") == 6  # 부서 4 + 유형 2
    assert client.get("/?dept=UI").content.decode().count(" checked>") == 3


def test_edge_dates_hide_prev_next(client, world):
    a, _ = world
    client.force_login(a.user)
    assert "◀ 이전" not in client.get("/?view=month&date=2000-01-15").content.decode()
    assert "다음 ▶" not in client.get("/?view=month&date=2099-12-15").content.decode()
    assert "◀ 이전" in client.get("/?view=month&date=2000-02-15").content.decode()


def test_separate_move_and_search_buttons(client, world):
    a, _ = world
    client.force_login(a.user)
    body = client.get("/").content.decode()
    assert "<button>이동</button>" in body and "<button>검색</button>" in body and "Today" not in body
