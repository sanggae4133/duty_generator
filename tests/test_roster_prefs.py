import pytest

from datetime import date

from duty.models import Commute, ControlDuty, Period, RosterPref

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


@pytest.fixture
def two_depts(world, make_member):
    c = make_member("라", dept="UI")
    Commute.objects.create(period=Period.objects.get(), date=D, member=c, shift="normal")
    return world[0], c


def grid(client, q=""):
    return client.get("/" + q).content.decode().split("<tbody>")[1].split("</tbody>")[0]


def test_shift_filter_hides_unchecked_in_roster(client, world):
    client.force_login(world[0])
    g = grid(client, "?shift=normal")
    assert "<small>정상</small>" in g and "<small>석식교대</small>" not in g and "관제" not in g
    assert "<small>석식교대</small>" in grid(client, "?shift=dinner") and "<small>정상</small>" not in grid(client, "?shift=dinner")


def test_slots_toggle_is_all_control_cells(client, world):
    client.force_login(world[0])
    g = grid(client, "?shift=slots")
    assert "관제" in g and "<small>정상</small>" not in g and "08:30" in g


def test_invalid_shift_ignored(client, world):
    client.force_login(world[0])
    assert "<small>정상</small>" in grid(client, "?shift=bogus") and "관제" in grid(client, "?shift=bogus")


def test_fold_button_gone(client, world):
    client.force_login(world[0])
    body = client.get("/").content.decode()
    assert "slot-toggle" not in body and "slots-hidden" not in body and "localStorage" not in body


def test_shift_carried_in_links(client, world):
    client.force_login(world[0])
    body = client.get("/?shift=normal").content.decode().replace("&amp;", "&")
    assert "shift=normal" in body.split('class="cal-nav"')[1].split("</div>")[0]


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
    art = body.split('<article id="normal">')[1].split("</article>")[0]
    assert "라" in art and "가" not in art
    assert f'value="{c.username}"' in art and f'value="{a.username}"' not in art


def test_day_filter_form_and_nav_links(client, world):
    client.force_login(world[0])
    body = client.get(f"/day/{D}/?type=개발자").content.decode().replace("&amp;", "&")
    assert 'name="f" value="1"' in body and 'name="shift"' in body
    nav = body.split("<nav>")[2].split("</nav>")[0]
    assert "type=%EA%B0%9C%EB%B0%9C%EC%9E%90" in nav


def test_saved_and_loaded(client, two_depts):
    a, _ = two_depts
    client.force_login(a)
    client.get("/?dept=UI&type=개발자&shift=normal&view=month")
    p = RosterPref.objects.get(user=a)
    assert (p.depts, p.types, p.shifts, p.view) == (["UI"], ["개발자"], ["normal"], "month")
    body = client.get("/").content.decode()  # 파라미터 없음 → 저장값
    assert "라" in body and "<small>석식교대</small>" not in body and "2026년 11월" in body


def test_f1_without_boxes_means_all_and_saves(client, two_depts):
    a, _ = two_depts
    client.force_login(a)
    client.get("/?dept=UI&shift=normal")
    g = grid(client, "?f=1")
    assert "라" in g and "가" in g and "<small>석식교대</small>" in g
    assert RosterPref.objects.get(user=a).depts == []


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
    assert "<small>석식교대</small>" in grid(client)
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
    body = client.get("/").content.decode()
    assert body.count('type="checkbox"') == 11 and body.count(" checked") == 11
    assert not RosterPref.objects.exists()


def _swap_values(client, q=""):
    import re
    body = client.get(f"/day/{D}/{q}").content.decode()
    return re.findall(r'<option value="(\w+\|[^"]+)">', body.split('name="a"')[1].split("</select>")[0])


def test_swap_options_unfiltered(client, two_depts):
    a, c = two_depts
    client.force_login(a)
    full = _swap_values(client)
    assert f"slot0|{a.username}" in full and f"normal|{c.username}" in full
    assert _swap_values(client, "?f=1&shift=normal&dept=UI") == full


def test_stale_saved_prefs_fall_back_to_all(client, world):
    a, _ = world
    RosterPref.objects.create(user=a, depts=["GONE"], types=["외부"], shifts=["bogus"])
    client.force_login(a)
    body = client.get("/").content.decode()
    assert "<small>정상</small>" in body and body.count(" checked") == 11


def test_unchanged_get_does_not_write(client, world):
    a, _ = world
    client.force_login(a)
    client.get("/?view=month&shift=normal")
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    with CaptureQueriesContext(connection) as ctx:
        client.get("/?view=month&shift=normal")
    assert not [q for q in ctx.captured_queries if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE"))]
