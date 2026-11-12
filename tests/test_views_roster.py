import re
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


def publish_more(member, *days):
    """world 의 배포 회차에 날짜를 더한다(배포된 근무표가 있는 날만 편집 링크가 생긴다)."""
    p = Period.objects.get()
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
    assert r.status_code == 200 and '<span class="hl1">가</span>' in body
    assert '<span class="hl1">나' not in body


def test_second_name_gets_hl2(client, world):
    a, _ = world
    client.force_login(a)
    body = client.get("/?q1=가&q2=나").content.decode()
    assert '<span class="hl1">가</span>' in body and '<span class="hl2">나</span>' in body


def test_name_inside_chain_highlights(client, world, make_member):
    a, _ = world
    c = make_member("다")
    client.force_login(a)
    client.post(f"/cell/{D}/normal/", {"before": a.username, "after": c.username})
    body = client.get("/?q3=다").content.decode()
    body = body.replace("&gt;", ">")
    assert '<span class="lb chg"><s>가</s>><span class="hl3">다</span></span>' in body
    assert "changed" not in body.split("<body")[1].split("<script")[0]  # 셀 배경 클래스 없음


def test_highlighted_struck_name_keeps_both(client, world, make_member):
    a, _ = world
    c = make_member("다")
    client.force_login(a)
    client.post(f"/cell/{D}/normal/", {"before": a.username, "after": c.username})
    body = client.get("/?q1=가").content.decode()
    assert '<span class="hl1"><s>가</s></span>' in body


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
    assert "새벽" in body and "석식교대" in body and "관제" in body and "08:30" in body and 'class="sec slot"' in body
    assert "<th scope=" not in body and body.count('class="sec"') == 5 * 4  # 행 라벨 열 없음, 날짜마다 4개 구역
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


def test_swap_via_post(client, world):
    a, b = world
    client.force_login(a)
    r = client.post(f"/swap/{D}/", {"a": f"normal|{a.username}", "b": f"dinner|{b.username}"})
    assert r.status_code == 302
    assert Commute.objects.get(date=D, member=a).shift == "dinner"


def test_day_page(client, world):
    a, _ = world
    client.force_login(a)
    body = client.get(f"/day/{D}/").content.decode()
    assert "08:30~09:30" in body and "맞교환" in body


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


@pytest.mark.parametrize("view", ["week", "month"])
def test_dept_filter_hides_other_departments(client, two_depts, view):
    a, _ = two_depts
    client.force_login(a)

    def grid(q):
        return client.get(f"/?view={view}{q}").content.decode().split("<tbody>")[1].split("</tbody>")[0]

    assert "라" in grid("&dept=UI") and "가" not in grid("&dept=UI")
    assert "라" in grid("") and "가" in grid("")


def test_dept_carried_through_links_and_popup_url(client, two_depts):
    a, _ = two_depts
    client.force_login(a)
    body = client.get("/?dept=UI&dept=MD").content.decode().replace("&amp;", "&")
    assert "dept=UI&dept=MD" in body.split('class="cal-nav"')[1].split("</div>")[0]
    assert "dept=UI&dept=MD" in body.split("</form>")[1]  # next=… 와 &dept= 가 팝업 URL에 실린다


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
    client.force_login(a)

    def grid(q):
        return client.get(f"/?view={view}{q}").content.decode().split("<tbody>")[1].split("</tbody>")[0]

    assert "라" in grid("&type=직원") and "가" not in grid("&type=직원")
    assert "가" in grid("&type=개발자") and "라" not in grid("&type=개발자")
    assert "가" not in grid("&type=직원&dept=UI") and "라" not in grid("&type=직원&dept=UI")  # 둘 다 통과해야 표시
    assert "라" in grid("&type=직원&dept=MEMS")


def test_type_carried_and_popup_filtered(client, mixed):
    a, c = mixed
    client.force_login(a)
    body = client.get("/?type=직원").content.decode().replace("&amp;", "&")
    assert "type=%EC%A7%81%EC%9B%90" in body.split('class="cal-nav"')[1].split("</div>")[0]
    assert "&type=%EC%A7%81%EC%9B%90" in body.split("</form>")[1]
    popup = client.get(f"/cell/{D}/normal/?type=직원").content.decode()
    assert f'<option value="{c.username}">' in popup and f'<option value="{a.username}">' not in popup


def _checked(body: str) -> dict[tuple[str, str], bool]:
    found = re.findall(r'<input type="checkbox" name="(dept|type)" value="([^"]+)"( checked)?>', body)
    return {(n, v): bool(c) for n, v, c in found}


def test_popup_members_filtered_by_dept(client, two_depts):
    a, c = two_depts  # 가(MEMS)·라(UI) 모두 정상 칸 소속
    client.force_login(a)
    popup = client.get(f"/cell/{D}/normal/?dept=UI").content.decode()
    assert popup.count(f'<option value="{c.username}"') == 2 and f'<option value="{a.username}"' not in popup  # From, To(To 는 이미 출근조라 막힘)
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
    assert "모두 해제하면 전체 표시" in client.get("/").content.decode()


def test_unknown_values_are_ignored_next_to_valid(client, two_depts):
    a, _ = two_depts
    client.force_login(a)
    body = client.get("/?dept=UI&dept=NOPE&type=외부").content.decode()
    grid = body.split("<tbody>")[1].split("</tbody>")[0]
    nav = body.split('class="cal-nav"')[1].split("</div>")[0]
    assert "라" in grid and "가" not in grid and "NOPE" not in nav and "dept=UI" in nav
    assert _checked(body)[("type", "직원")] and _checked(body)[("dept", "UI")]  # 잘못된 type만 줬으니 유형은 전체


def test_removed_label_filtered_by_its_department(client, two_depts):
    a, c = two_depts
    client.force_login(a)
    client.post(f"/cell/{D}/normal/", {"before": a.username, "after": ""})  # 가(MEMS) 제거 → 취소선
    grid = lambda q: client.get(f"/?{q}").content.decode().split("<tbody>")[1].split("</tbody>")[0]
    assert "<s>가</s>" in grid("dept=MEMS") and "<s>가</s>" not in grid("dept=UI")


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
    assert "<button>이동</button>" in body and "<button>검색</button>" in body and "Today" not in body


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
    assert '<span class="hl1">나</span>' in client.get("/?q1=나").content.decode()  # 근무표 조회엔 그대로


def test_me_shift_filter(client, world):
    a, _ = world
    client.force_login(a)
    body = client.get("/me/?shift=slots").content.decode()
    assert '<span class="what">장중관제 08:30~09:30</span>' in body
    assert re.search(r'value="slots" checked', body) and not re.search(r'value="normal" checked', body)
    assert "예정된 근무가 없습니다" in client.get("/me/?shift=dinner").content.decode()
    assert '<span class="what">정상 · 장중관제 08:30~09:30</span>' in client.get("/me/").content.decode()


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


def test_cell_form_guides_and_blocks_busy(client, world, make_member):
    """출근조 칸: 그날 이미 다른 출근조인 사람은 고를 수 없게(저장 뒤 오류 대신), 사용법 안내, 버튼 '저장'."""
    a, b = world  # 가=정상, 나=석식교대
    make_member("다", user=True)
    client.force_login(a)
    body = client.get(f"/cell/{D}/dawn/").content.decode()
    assert "From만 고르면 빼기" in body and "<button>저장</button>" in body
    assert re.search(r'<option value="[^"]+" disabled>나 · ', body)  # 석식교대 중
    assert re.search(r'<option value="[^"]+">다 · ', body)
    slot = client.get(f"/cell/{D}/slot0/").content.decode()
    assert "disabled>" not in slot and "바꾸기만" in slot  # 관제는 경고만, 막지 않는다
