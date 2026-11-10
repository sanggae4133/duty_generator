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


def _csv(body):
    return SimpleUploadedFile("a.csv", ("date,새벽,정상,석식교대,야간\n" + body).encode("utf-8-sig"))


def test_upload_too_large(client, ctx):
    p, mgr = ctx
    client.force_login(mgr.user)
    big = SimpleUploadedFile("a.csv", b"x" * 1_000_001)
    r = client.post(f"/collect/{p.pk}/MEMS/upload/", {"file": big}, follow=True)
    assert "파일이 너무 큽니다" in r.content.decode()
    assert not Commute.objects.exists()


def test_manager_of_other_department_forbidden(client, ctx):
    p, mgr = ctx
    client.force_login(mgr.user)
    base = f"/collect/{p.pk}/TMCH/"
    assert client.get(base).status_code == 403
    assert client.post(base, {"c_2026-11-10_normal": "가"}).status_code == 403
    assert client.post(base + "upload/", {"file": _csv("")}).status_code == 403
    assert client.get(base + "export.csv").status_code == 403
    assert not Commute.objects.exists()


def test_closed_period_saves_nothing(client, ctx):
    p, mgr = ctx
    Period.objects.filter(pk=p.pk).update(status=Period.Status.DRAFT)
    client.force_login(mgr.user)
    r = client.post(f"/collect/{p.pk}/MEMS/", {"c_2026-11-10_normal": "가"}, follow=True)
    assert "취합 중인 회차가 아닙니다" in r.content.decode()
    r = client.post(f"/collect/{p.pk}/MEMS/upload/", {"file": _csv("2026-11-09,가,,,\n")}, follow=True)
    assert "취합 중인 회차가 아닙니다" in r.content.decode()
    assert not Commute.objects.exists()
    assert 'name="file"' not in r.content.decode() and "표 저장" not in r.content.decode()


def test_past_row_unchanged_ok_changed_rejected(client, ctx, fixed_today):
    p, mgr = ctx
    member = mgr.__class__.objects.get(name="가")
    Commute.objects.create(period=p, date=date(2026, 11, 9), member=member, shift="normal")
    fixed_today(date(2026, 11, 10))
    client.force_login(mgr.user)
    r = client.post(f"/collect/{p.pk}/MEMS/", {"c_2026-11-09_normal": "가", "c_2026-11-10_dawn": "가"})
    assert r.status_code == 302 and Commute.objects.count() == 2
    r = client.post(f"/collect/{p.pk}/MEMS/", {"c_2026-11-09_dawn": "가", "c_2026-11-10_dawn": "가"})
    assert r.status_code == 400 and "지난 날짜는 어드민만 수정할 수 있습니다." in r.content.decode()
    assert set(Commute.objects.values_list("date", "shift")) == {(date(2026, 11, 9), "normal"), (date(2026, 11, 10), "dawn")}


def test_garbage_upload_is_400(client, ctx):
    p, mgr = ctx
    client.force_login(mgr.user)
    f = SimpleUploadedFile("a.csv", bytes([0x81, 0xFF, 0xFE, 0x00, 0x80]) * 20)
    r = client.post(f"/collect/{p.pk}/MEMS/upload/", {"file": f})
    assert r.status_code == 400 and "CSV" in r.content.decode()
