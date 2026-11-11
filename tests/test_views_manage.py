from datetime import date

import pytest

from duty.models import ChangeLog, Commute, Period, User


@pytest.fixture
def member_client(client, make_member):
    m = make_member("가", user=True)
    client.force_login(m)
    return client


@pytest.mark.parametrize("url", ["/periods/", "/stats/", "/changes/"])
def test_admin_pages_forbidden_for_member(member_client, url):
    assert member_client.get(url).status_code == 403


def test_create_period(admin_client_ok):
    r = admin_client_ok.post("/periods/", {"name": "2027", "start_date": "2026-11-09", "end_date": "2026-11-13"})
    p = Period.objects.get(name="2027")
    assert r.status_code == 302 and r.url == f"/periods/{p.pk}/"


def test_full_flow(admin_client_ok, make_member, fixed_today):
    fixed_today(date(2026, 11, 1))
    c = admin_client_ok
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 10))
    c.post(f"/periods/{p.pk}/action/open/")
    devs = [make_member(f"D{i}", dept=["MEMS", "TMCH", "MD", "UI"][i % 4]) for i in range(12)]
    for d in p.dates():
        for m in devs:
            Commute.objects.create(period=p, date=d, member=m, shift="normal" if m.pk % 2 else "dinner")
    c.post(f"/periods/{p.pk}/action/close/")
    r = c.post(f"/periods/{p.pk}/action/generate/")
    p.refresh_from_db()
    assert r.status_code == 302 and p.status == Period.Status.GENERATED
    assert "편차" in c.get(f"/periods/{p.pk}/").content.decode()
    c.post(f"/periods/{p.pk}/publish/", {"from": "2026-11-09"})
    p.refresh_from_db()
    assert p.status == Period.Status.PUBLISHED


def test_generation_failure_is_shown(admin_client_ok, make_member):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 9), status=Period.Status.CLOSED)
    for code in ["MEMS", "TMCH", "MD", "UI"]:
        Commute.objects.create(period=p, date=date(2026, 11, 9), member=make_member(f"직{code}", dept=code, type="직원"), shift="normal")
    r = admin_client_ok.post(f"/periods/{p.pk}/action/generate/")
    assert r.status_code == 200 and "후보" in r.content.decode()


def test_stats_and_changes_pages(admin_client_ok, make_member):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 9), status=Period.Status.PUBLISHED)
    m = make_member("가")
    Commute.objects.create(period=p, date=date(2026, 11, 9), member=m, shift="dawn")
    ChangeLog.objects.create(period=p, date=date(2026, 11, 9), cell="dawn", before=None, after=m)
    assert "가" in admin_client_ok.get("/stats/").content.decode()
    assert "새벽" in admin_client_ok.get("/changes/?name=가").content.decode()


@pytest.mark.parametrize("url", ["/periods/", "/periods/1/", "/periods/1/publish/", "/periods/1/action/open/"])
def test_anonymous_redirected_to_login(client, url):
    r = client.get(url)
    assert r.status_code == 302 and r.url.startswith("/login/")


def test_action_get_is_405(admin_client_ok):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 9))
    assert admin_client_ok.get(f"/periods/{p.pk}/action/open/").status_code == 405


def _generated(make_member, start=date(2026, 11, 9), end=date(2026, 11, 11)):
    old = Period.objects.create(name="옛회차", start_date=date(2026, 11, 2), end_date=date(2026, 11, 10), status=Period.Status.PUBLISHED)
    m = make_member("가")
    Commute.objects.create(period=old, date=date(2026, 11, 10), member=m, shift="dawn")
    ChangeLog.objects.create(period=old, date=date(2026, 11, 10), cell="dawn", before=None, after=m)
    new = Period.objects.create(name="새회차", start_date=start, end_date=end, status=Period.Status.GENERATED)
    return old, new


def test_publish_preview_content(admin_client_ok, make_member):
    _, p = _generated(make_member)
    html = admin_client_ok.get(f"/periods/{p.pk}/publish/?from=2026-11-10").content.decode()
    assert "2026-11-10 ~ 2026-11-11" in html
    assert "옛회차" in html
    assert "사라지는 근무 변경: 1건" in html
    assert "버립니다" in html
    assert "버립니다" not in admin_client_ok.get(f"/periods/{p.pk}/publish/?from=2026-11-09").content.decode()


def test_publish_post_rejects_bad_from(admin_client_ok, make_member):
    _, p = _generated(make_member)
    for data in ({}, {"from": "garbage"}, {"from": "2027-01-01"}):
        r = admin_client_ok.post(f"/periods/{p.pk}/publish/", data, follow=True)
        p.refresh_from_db()
        assert p.status == Period.Status.GENERATED
    r = admin_client_ok.post(f"/periods/{p.pk}/publish/", {"from": "garbage"}, follow=True)
    assert "덮어쓰기 시작일이 올바르지 않습니다." in r.content.decode()
    r = admin_client_ok.post(f"/periods/{p.pk}/publish/", {"from": "2027-01-01"}, follow=True)
    assert "시작일은 회차 기간 안" in r.content.decode()


def test_publish_post_past_start_inside_period_ok(admin_client_ok, make_member, fixed_today):
    fixed_today(date(2026, 11, 11))
    _, p = _generated(make_member)
    admin_client_ok.post(f"/periods/{p.pk}/publish/", {"from": "2026-11-10"})
    p.refresh_from_db()
    assert p.status == Period.Status.PUBLISHED and p.overwrite_from == date(2026, 11, 10)


def test_change_log_filters(admin_client_ok, make_member):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 10), status=Period.Status.PUBLISHED)
    a, b = make_member("가", user=True), make_member("나")
    ChangeLog.objects.create(period=p, date=date(2026, 11, 9), cell="dawn", before=None, after=a, by=a)
    ChangeLog.objects.create(period=p, date=date(2026, 11, 10), cell="night", before=None, after=b)
    c = admin_client_ok

    def get(q):
        r = c.get("/changes/" + q)
        assert r.status_code == 200
        return r.content.decode()

    assert "garbage" not in get("?from=garbage") and "새벽" in get("?from=garbage") and "야간" in get("?from=garbage")
    h = get("?from=2026-11-10")
    assert "야간" in h and "새벽" not in h
    h = get("?to=2026-11-09")
    assert "새벽" in h and "야간" not in h
    h = get("?name=나")
    assert "야간" in h and "새벽" not in h
    h = get(f"?by={a.username}")
    assert "새벽" in h and "야간" not in h


def test_schema_page(admin_client_ok):
    body = admin_client_ok.get("/schema/").content.decode()
    assert "duty_commute" in body and "commute_one_shift_per_day" in body and "duty_one_member_per_slot" in body
    assert "duty_one_slot_per_member" not in body


def test_schema_forbidden_for_member(member_client):
    assert member_client.get("/schema/").status_code == 403


def test_schema_anonymous_redirected(client, db):
    assert client.get("/schema/").status_code == 302


def test_admin_nav_link_superuser_only(client, admin_user, make_member):
    link = '<a href="/admin/">관리</a>'
    root = User.objects.create_superuser("root", password="unused-Pw-123", name="루트")
    client.force_login(root)
    assert link in client.get("/").content.decode()
    client.force_login(admin_user)  # staff only
    assert "관리</a>" not in client.get("/").content.decode()
    client.force_login(make_member("가", user=True))
    assert "관리</a>" not in client.get("/").content.decode()


def test_generate_has_detail_dialog(admin_client_ok):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13),
                              status=Period.Status.CLOSED)
    body = admin_client_ok.get(f"/periods/{p.pk}/").content.decode()
    assert 'id="gen-help"' in body and "showModal()" in body
    assert "자격자가 적은 칸부터" in body and "편차" in body
