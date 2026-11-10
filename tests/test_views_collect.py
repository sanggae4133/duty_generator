from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from duty.models import Commute, Period


@pytest.fixture
def ctx(depts, make_member, fixed_today):
    fixed_today(date(2026, 11, 1))
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 10), status=Period.Status.COLLECTING)
    mgr = make_member("담당", user=True)
    depts["MEMS"].managers.add(mgr)
    make_member("가")
    return p, mgr


def test_index_lists_managed_departments(client, ctx):
    p, mgr = ctx
    client.force_login(mgr.user)
    body = client.get("/collect/").content.decode()
    assert "매칭엔진실" in body and "정보분배" not in body


def test_non_manager_forbidden(client, ctx, make_member):
    p, _ = ctx
    other = make_member("남", user=True)
    client.force_login(other.user)
    assert client.get("/collect/").status_code == 403
    assert client.get(f"/collect/{p.pk}/MEMS/").status_code == 403


def test_upload_csv(client, ctx):
    p, mgr = ctx
    client.force_login(mgr.user)
    f = SimpleUploadedFile("a.csv", "date,새벽,정상,석식교대,야간\n2026-11-09,가,,,\n".encode("utf-8-sig"))
    r = client.post(f"/collect/{p.pk}/MEMS/upload/", {"file": f})
    assert r.status_code == 302
    assert Commute.objects.filter(period=p, shift="dawn").count() == 1


def test_upload_errors_are_listed(client, ctx):
    p, mgr = ctx
    client.force_login(mgr.user)
    f = SimpleUploadedFile("a.csv", "date,새벽,정상,석식교대,야간\n2026-11-09,없는사람,,,\n".encode())
    r = client.post(f"/collect/{p.pk}/MEMS/upload/", {"file": f})
    assert r.status_code == 400 and "없는사람" in r.content.decode()


def test_table_form_save(client, ctx):
    p, mgr = ctx
    client.force_login(mgr.user)
    r = client.post(f"/collect/{p.pk}/MEMS/", {"c_2026-11-10_normal": "가"})
    assert r.status_code == 302
    assert Commute.objects.get(period=p).date == date(2026, 11, 10)


def test_export(client, ctx):
    p, mgr = ctx
    client.force_login(mgr.user)
    r = client.get(f"/collect/{p.pk}/MEMS/export.csv")
    assert r.status_code == 200 and r["Content-Type"].startswith("text/csv")
    assert r.content.decode("utf-8-sig").splitlines()[0] == "date,day,새벽,정상,석식교대,야간"
