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
    depts["UI"].input_group.user_set.add(gone)
    assert set(DepartmentForm(instance=depts["UI"]).fields["managers"].queryset) == {a, gone}
    assert list(DepartmentForm(instance=depts["MD"]).fields["managers"].queryset) == [a]


def test_username_label(su_client, make_member):
    m = make_member("가")
    for url in (reverse("admin:duty_user_changelist"), reverse("admin:duty_user_add"),
                reverse("admin:duty_user_change", args=[m.pk])):
        body = su_client.get(url).content.decode()
        assert "아이디" in body and "사용자 이름" not in body, url


def test_add_rejects_username_differing_only_in_case(su_client, make_member):
    m = make_member("가")  # MEMS001
    r = su_client.post(reverse("admin:duty_user_add"), {
        "username": m.username.lower(), "name": "새사람", "department": "MD", "part": "", "type": "개발자"})
    assert r.status_code == 200 and "같은 아이디가 이미 있습니다" in r.content.decode()
    assert User.objects.count() == 2  # 관리자 + 가


def test_change_form_has_help_and_notice_checkboxes(su_client, make_member):
    """관리자가 '사용법 팝업 다시 보지 않기'를 되돌리거나(다시 띄우기) 변경 알림을 끌 수 있다."""
    m = make_member("가상다", user=True)
    body = su_client.get(reverse("admin:duty_user_change", args=[m.pk])).content.decode()
    assert 'name="help_dismissed"' in body and 'name="notify_changes"' in body
    assert "사용법 팝업 다시 보지 않기" in body


def test_changelist_shows_groups_not_staff(su_client, it_board):
    body = su_client.get(reverse("admin:duty_user_changelist")).content.decode()
    assert f'<td class="field-group_names">{it_board.admin_group.name}</td>' in body  # 목록의 그룹 칸(admin_user)
    assert "groups__id__exact" in body and "is_staff__exact" not in body


def test_change_page_hides_user_permissions(su_client, make_member):
    m = make_member("가")
    body = su_client.get(reverse("admin:duty_user_change", args=[m.pk])).content.decode()
    assert 'name="groups"' in body and 'name="user_permissions"' not in body


# ── 재직 관리자 한 명 이상(근무표 통합 설계 7.4) ──

def _user_data(u, **over):
    """사용자 편집 폼에 지금 값을 그대로 보낸다(체크박스는 켤 때만)."""
    data = {"username": u.username, "name": u.name, "department": u.department_id or "", "part": u.part, "type": u.type,
            "groups": [g.pk for g in u.groups.all()], "date_joined_0": f"{u.date_joined:%Y-%m-%d}",
            "date_joined_1": f"{u.date_joined:%H:%M:%S}"}
    data |= {f: "on" for f in ("is_active", "is_staff", "is_superuser", "help_dismissed", "notify_changes",
                               "must_change_password") if getattr(u, f)}
    return {k: v for k, v in (data | over).items() if v is not None}


@pytest.fixture
def ops_only_admin(ops_board):
    u = User.objects.create_user("opsadm", password=None, name="가상운영")
    ops_board.admin_group.user_set.add(u)
    return u


@pytest.mark.parametrize("change", [{"groups": []}, {"is_active": None}])
def test_last_active_admin_kept_in_user_form(su_client, ops_only_admin, change):
    url = reverse("admin:duty_user_change", args=[ops_only_admin.pk])
    r = su_client.post(url, _user_data(ops_only_admin, **change))
    assert r.status_code == 200 and "운영팀 근무표에 재직 중인 관리자가 남지 않습니다. 먼저 다른 관리자를 넣으세요." in r.content.decode()
    ops_only_admin.refresh_from_db()
    assert ops_only_admin.is_active and ops_only_admin.groups.exists()


def test_user_form_allows_when_another_admin_stays(su_client, ops_board, ops_only_admin, make_member):
    ops_board.admin_group.user_set.add(make_member("가상둘째", user=True))
    r = su_client.post(reverse("admin:duty_user_change", args=[ops_only_admin.pk]), _user_data(ops_only_admin, groups=[]))
    assert r.status_code == 302, r.content.decode()[:3000]
    assert not ops_only_admin.groups.exists()


def test_delete_refused_for_last_active_admin(su_client, ops_only_admin, make_member):
    r = su_client.post(reverse("admin:duty_user_delete", args=[ops_only_admin.pk]), {"post": "yes"})
    assert r.status_code == 200 and "운영팀 근무표에 재직 중인 관리자가 남지 않습니다" in r.content.decode()
    r = su_client.post(reverse("admin:duty_user_changelist"),
                       {"action": "delete_selected", "_selected_action": [ops_only_admin.pk], "post": "yes"})
    assert r.status_code == 200 and "운영팀 근무표에 재직 중인 관리자가 남지 않습니다" in r.content.decode()
    assert User.objects.filter(pk=ops_only_admin.pk).exists()
    other = make_member("가상기록없음")  # 관리자가 아니면 그대로 지운다
    r = su_client.post(reverse("admin:duty_user_delete", args=[other.pk]), {"post": "yes"})
    assert r.status_code == 302 and not User.objects.filter(pk=other.pk).exists()
