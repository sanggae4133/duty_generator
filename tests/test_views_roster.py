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
    assert "새벽" in body and "석식교대" in body and "08:30~09:30" in body and 'class="slot"' in body
    assert 'id="today"' in body and "hx-get" in body


def test_month_view(client, world):
    a, _ = world
    client.force_login(a.user)
    body = client.get("/?view=month&date=2026-11-10").content.decode()
    assert "2026년 11월" in body and "/day/2026-11-30/" in body and "/day/2026-11-02/" in body
    assert "hx-get" not in body and 'id="today"' in body and "08:30 " in body


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
    assert "/cell/2026-11-10/" not in body and "/cell/2026-11-12/" in body


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


def test_dept_views(client, world):
    a, _ = world
    client.force_login(a.user)
    for key in ["it", "md", "ui"]:
        assert client.get(f"/dept/{key}/").status_code == 200
    assert client.get("/dept/nope/").status_code == 404


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
