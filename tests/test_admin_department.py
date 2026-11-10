import pytest
from django.urls import reverse

from duty.admin import DepartmentForm


@pytest.fixture
def su_client(client, admin_user):
    admin_user.is_superuser = True
    admin_user.save()
    client.force_login(admin_user)
    return client


def _data(dept, shifts):
    return {"code": dept.code, "name": dept.name, "shifts": shifts, "managers": []}


def test_form_shows_current_shifts_checked(depts):
    form = DepartmentForm(instance=depts["UI"])
    assert form.initial["shifts"] == ["normal", "dinner", "night"]


def test_form_saves_in_display_order(depts):
    form = DepartmentForm(_data(depts["UI"], ["night", "dawn"]), instance=depts["UI"])
    assert form.is_valid(), form.errors
    assert form.save().shifts == "dawn,night"


@pytest.mark.parametrize("bad", [[], ["nomal"]])
def test_form_rejects_empty_or_unknown(depts, bad):
    form = DepartmentForm(_data(depts["UI"], bad), instance=depts["UI"])
    assert not form.is_valid() and "shifts" in form.errors


def test_change_page_renders_korean_checkboxes(su_client, depts):
    html = su_client.get(reverse("admin:duty_department_change", args=["UI"])).content.decode()
    assert 'type="checkbox"' in html and "석식교대" in html


def test_changelist_shows_labels_count_and_managers(su_client, make_member):
    m = make_member("가", dept="UI")
    make_member("나", dept="UI")
    m.department.managers.add(m)
    html = su_client.get(reverse("admin:duty_department_changelist")).content.decode()
    assert "정상·석식교대·야간" in html
    assert ">2<" in html  # UI 인원
    assert ">가<" in html  # 담당자
