"""관리 화면 '사용자'(duty.User)."""
import pytest
from django.urls import reverse

from duty.admin import DepartmentForm
from duty.models import AlarmRule, User


@pytest.fixture
def su_client(client, admin_user):
    admin_user.is_superuser = True
    admin_user.save()
    client.force_login(admin_user)
    return client


def test_changelist(su_client, make_member):
    make_member("가상가", dept="UI", type="직원")
    body = su_client.get(reverse("admin:duty_user_changelist") + "?q=가상가").content.decode()
    assert "가상가" in body and "UI001" in body and "관리자" not in body


def test_add_without_password_sets_unusable(su_client, depts):
    r = su_client.post(reverse("admin:duty_user_add"), {
        "username": "NEW01", "name": "새사람", "department": "MD", "part": "", "type": "개발자",
    })
    assert r.status_code == 302, r.content.decode()
    u = User.objects.get(username="NEW01")
    assert u.name == "새사람" and u.department_id == "MD" and not u.has_usable_password()
    assert not AlarmRule.objects.filter(user=u).exists()


def test_add_rejects_type_without_department(su_client, db):
    r = su_client.post(reverse("admin:duty_user_add"), {"username": "NEW02", "name": "새", "type": "개발자"})
    assert r.status_code == 200 and "부서가 없으면 구분을 비워 두세요" in r.content.decode()
    assert not User.objects.filter(username="NEW02").exists()


def test_change_page_renders(su_client, make_member):
    m = make_member("가")
    body = su_client.get(reverse("admin:duty_user_change", args=[m.pk])).content.decode()
    assert "근무표" in body and 'name="department"' in body


def test_department_manager_choices_are_roster(depts, make_member, admin_user):
    a = make_member("가")
    make_member("나", active=False)
    assert list(DepartmentForm(instance=depts["UI"]).fields["managers"].queryset) == [a]


def test_department_keeps_current_manager_outside_roster(depts, make_member):
    a, gone = make_member("가"), make_member("나", active=False)
    depts["UI"].managers.add(gone)
    assert set(DepartmentForm(instance=depts["UI"]).fields["managers"].queryset) == {a, gone}
    assert list(DepartmentForm(instance=depts["MD"]).fields["managers"].queryset) == [a]


def test_username_label(su_client, make_member):
    m = make_member("가")
    for url in (reverse("admin:duty_user_changelist"), reverse("admin:duty_user_add"),
                reverse("admin:duty_user_change", args=[m.pk])):
        body = su_client.get(url).content.decode()
        assert "아이디" in body and "사용자 이름" not in body, url
