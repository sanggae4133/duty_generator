from datetime import date

import pytest

from duty.models import ChangeLog, Commute, Period


@pytest.fixture
def member_client(client, make_member):
    m = make_member("가", user=True)
    client.force_login(m.user)
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
    assert "덮어쓰기" in c.get(f"/periods/{p.pk}/publish/?from=2026-11-09").content.decode()
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
