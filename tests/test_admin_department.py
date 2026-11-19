import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import FieldDoesNotExist
from django.urls import reverse

from duty.admin import DepartmentForm
from duty.models import BoardShift
from duty.models import Board, Department
from tests.it_defs import OPS_STEPS


@pytest.fixture
def su_client(client, admin_user):
    admin_user.is_superuser = True
    admin_user.save()
    client.force_login(admin_user)
    return client


def _data(dept, shifts):
    return {"code": dept.code, "name": dept.name, "board": dept.board_id, "order": dept.order,
            "shifts": shifts, "managers": []}


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
    m.department.input_group.user_set.add(m)
    html = su_client.get(reverse("admin:duty_department_changelist")).content.decode()
    assert "정상·석식교대·야간" in html
    assert ">2<" in html  # UI 인원
    assert ">가<" in html  # 담당자


def test_shift_choices_and_labels_come_from_board_definitions(su_client, depts, it_board):
    BoardShift.objects.filter(board=it_board, key="dinner").update(name="늦은조")
    form = DepartmentForm(instance=depts["UI"])
    assert ("dinner", "늦은조") in form.fields["shifts"].choices
    html = su_client.get(reverse("admin:duty_department_changelist")).content.decode()
    assert "정상·늦은조·야간" in html


def test_managers_compat_removed(depts):
    """2단계 끝: 1단계 호환 property 를 지웠다. 입력 담당자 = 입력 그룹 멤버(관리 화면 폼 칸 이름만 managers)."""
    with pytest.raises(FieldDoesNotExist):
        Department._meta.get_field("managers")
    assert not hasattr(Department, "managers")
    direct = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
    dept = Department.objects.create(code="OPS", name="운영", shifts="normal", board=direct)
    assert dept.input_group_id is None and list(DepartmentForm(instance=dept).initial["managers"]) == []


def test_form_initial_managers_from_input_group(depts, make_member):
    a = make_member("가")
    depts["UI"].input_group.user_set.add(a)
    assert list(DepartmentForm(instance=depts["UI"]).initial["managers"]) == [a]


def test_save_sets_input_group_members(su_client, depts, make_member):
    a, b = make_member("가"), make_member("나")
    depts["UI"].input_group.user_set.add(a)
    r = su_client.post(reverse("admin:duty_department_change", args=["UI"]),
                       {**_data(depts["UI"], ["normal"]), "managers": [b.pk]})
    assert r.status_code == 302, r.content.decode()
    assert list(depts["UI"].input_group.user_set.all()) == [b]


def test_change_page_uses_filtered_select(su_client, depts):
    html = su_client.get(reverse("admin:duty_department_change", args=["UI"])).content.decode()
    assert 'name="managers"' in html and "selectfilter" in html
    assert 'name="board"' in html and 'name="order"' in html


def test_saved_department_board_is_read_only(depts):
    other = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
    form = DepartmentForm({**_data(depts["UI"], ["normal"]), "board": other.pk}, instance=depts["UI"])
    assert form.fields["board"].disabled and not DepartmentForm().fields["board"].disabled  # 새 부서만 고른다
    assert form.is_valid(), form.errors
    assert form.save().board_id == depts["UI"].board_id  # 보낸 근무표는 무시된다(옮기기는 별도 기능)


def test_new_department_input_group_name_clash(it_board, make_member):
    """첫 담당자를 골라 만들 입력 그룹 이름이 이미 있으면 500 대신 칸 오류. 담당자가 없으면 그룹을 만들지 않아 통과."""
    Group.objects.create(name="품질 출근표 입력")
    data = {"code": "QA", "name": "품질", "board": it_board.pk, "order": 9, "shifts": ["normal"],
            "managers": [make_member("가").pk]}
    form = DepartmentForm(data)
    assert not form.is_valid()
    assert "같은 이름의 그룹이 이미 있습니다: 품질 출근표 입력" in str(form.errors.get("name", ""))
    assert DepartmentForm({**data, "managers": []}).is_valid()


def test_rename_department_renames_input_group(su_client, depts):
    ui = depts["UI"]
    data = {**_data(ui, ["normal", "dinner", "night"]), "name": "화면개발"}
    r = su_client.post(reverse("admin:duty_department_change", args=["UI"]), data)
    assert r.status_code == 302, r.content.decode()[:2000]
    ui.refresh_from_db()
    assert ui.name == "화면개발" and ui.input_group.name == "화면개발 출근표 입력"


def test_rename_department_refused_when_group_name_taken(su_client, depts):
    ui = depts["UI"]
    Group.objects.create(name="화면개발 출근표 입력")
    data = {**_data(ui, ["normal"]), "name": "화면개발"}
    r = su_client.post(reverse("admin:duty_department_change", args=["UI"]), data)
    assert r.status_code == 200 and "같은 이름의 그룹이 이미 있습니다: 화면개발 출근표 입력" in r.content.decode()
    ui.refresh_from_db()
    assert (ui.name, ui.shifts, ui.input_group.name) == ("UI", "normal,dinner,night", "UI 출근표 입력")


def test_changelist_shifts_follow_current_start_times(su_client, depts, it_board):
    # 입력 표(collect.input_keys)와 같은 순서: 저장 순서가 아니라 지금 시작 시각 순
    BoardShift.objects.filter(board=it_board, key="normal").update(start="10:00")
    html = su_client.get(reverse("admin:duty_department_changelist")).content.decode()
    assert "석식교대·정상·야간" in html


def test_change_page_code_is_readonly(su_client, depts):
    """부서 코드는 기본키: 바꾸면 새 부서가 생기므로 만든 뒤에는 고칠 수 없다."""
    d = depts["UI"]
    url = reverse("admin:duty_department_change", args=[d.pk])
    assert 'name="code"' not in su_client.get(url).content.decode()
    n = Department.objects.count()
    data = {**_data(d, ["normal"]), "code": "ZZ"}
    su_client.post(url, data)
    assert Department.objects.count() == n and not Department.objects.filter(code="ZZ").exists()


def test_first_manager_creates_input_group(su_client, it_board, make_member):
    """마감을 끈 근무표의 부서도 담당자를 처음 고를 때 입력 그룹이 생긴다(근무표 통합 설계 5.3)."""
    ops = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
    BoardShift.objects.create(board=ops, key="normal", name="가운데", start="09:00", end="18:00")
    m = make_member("가", dept="UI")
    data = {"code": "OPS", "name": "운영", "board": ops.pk, "order": 9, "shifts": ["normal"], "managers": []}
    r = su_client.post(reverse("admin:duty_department_add"), data)
    assert r.status_code == 302, r.content.decode()[:2000]
    assert Department.objects.get(code="OPS").input_group_id is None  # 담당자 없이 만들면 그룹도 없다
    r = su_client.post(reverse("admin:duty_department_change", args=["OPS"]), {**data, "managers": [m.pk]})
    assert r.status_code == 302, r.content.decode()[:2000]
    dept = Department.objects.get(code="OPS")
    assert dept.input_group.name == "운영 출근표 입력" and list(dept.input_group.user_set.all()) == [m]
