"""관리 화면 "휴장일"(슈퍼유저): 임시공휴일 추가·끄기(설계 5절). 이름은 모두 가상."""
from datetime import date

import pytest
from django.urls import reverse

from duty.models import Holiday


@pytest.fixture
def su_client(client, admin_user):
    admin_user.is_superuser = True
    admin_user.save()
    client.force_login(admin_user)
    return client


def test_admin_adds_manual_holiday(su_client):
    r = su_client.post(reverse("admin:duty_holiday_add"), {"date": "2026-11-20", "name": "임시 휴장", "active": "on"})
    assert r.status_code == 302
    h = Holiday.objects.get(date=date(2026, 11, 20))
    assert (h.name, h.source, h.active) == ("임시 휴장", "manual", True)


def test_admin_turns_off_but_cannot_move_or_delete(su_client):
    h = Holiday.objects.create(date=date(2026, 12, 25), name="성탄", source="auto")
    url = reverse("admin:duty_holiday_change", args=[h.pk])
    body = su_client.get(url).content.decode()
    assert 'name="date"' not in body and 'name="source"' not in body and 'name="active"' in body
    su_client.post(url, {"name": "성탄"})  # 체크 해제 = 끄기
    h.refresh_from_db()
    assert h.active is False and h.source == "auto"
    assert su_client.get(reverse("admin:duty_holiday_delete", args=[h.pk])).status_code == 403


def test_admin_holiday_list_needs_superuser(client, admin_user):
    client.force_login(admin_user)  # 근무표 관리자(스태프)지만 슈퍼유저 아님
    assert client.get(reverse("admin:duty_holiday_changelist")).status_code in (302, 403)
