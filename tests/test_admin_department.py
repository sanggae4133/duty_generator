import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import FieldDoesNotExist
from django.urls import reverse

from duty.admin import DepartmentForm
from duty.models import BoardShift
from duty.models import Board, Department


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
    direct = Board.objects.create(code="ops", name="운영팀", input_mode="direct")
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
    other = Board.objects.create(code="ops", name="운영팀", input_mode="direct")
    form = DepartmentForm({**_data(depts["UI"], ["normal"]), "board": other.pk}, instance=depts["UI"])
    assert form.fields["board"].disabled and not DepartmentForm().fields["board"].disabled  # 새 부서만 고른다
    assert form.is_valid(), form.errors
    assert form.save().board_id == depts["UI"].board_id  # 보낸 근무표는 무시된다(옮기기는 별도 기능)


def test_new_department_input_group_name_clash(it_board):
    """Department.save 가 만들 입력 그룹 이름이 이미 있으면 500 대신 칸 오류."""
    Group.objects.create(name="품질 출근표 입력")
    data = {"code": "QA", "name": "품질", "board": it_board.pk, "order": 9, "shifts": ["normal"], "managers": []}
    form = DepartmentForm(data)
    assert not form.is_valid()
    assert "같은 이름의 그룹이 이미 있습니다: 품질 출근표 입력" in str(form.errors.get("name", ""))
