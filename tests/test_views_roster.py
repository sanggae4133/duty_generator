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
    assert r.status_code == 200 and 'class="today"' in body and '<span class="hl1">가</span>' in body
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
    assert '<span class="hl3">가>다</span>' in body.replace("&gt;", ">")


def test_cells_use_nowrap_lines(client, world):
    a, _ = world
    client.force_login(a.user)
    assert '<div class="line">' in client.get("/").content.decode()


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
