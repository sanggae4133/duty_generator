"""관리 화면(슈퍼유저 전용): 근무표·근무 정의 편집과 설계 4.3 검증, 그룹 관리자 지정(3단계). 이름은 모두 가상."""
from datetime import time

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.urls import reverse

from duty.admin import DepartmentForm
from duty.models import Board, BoardShift, Department, GroupKeeper

ADD = reverse("admin:duty_board_add")


@pytest.fixture
def su(admin_user):
    admin_user.is_superuser = True
    admin_user.save()
    return admin_user


@pytest.fixture
def su_client(client, su):
    client.force_login(su)
    return client


def row(i, key, name, start="", end="", pk="", board="", **more):
    """근무 정의 인라인 한 줄(prefix "shifts"). 체크박스는 켤 때만 보낸다(active 는 기본 켬)."""
    data = {f"shifts-{i}-id": pk, f"shifts-{i}-board": board, f"shifts-{i}-key": key, f"shifts-{i}-name": name,
            f"shifts-{i}-start": start, f"shifts-{i}-end": end}
    if more.pop("active", True):
        data[f"shifts-{i}-active"] = "on"
    for k, v in more.items():
        data[f"shifts-{i}-{k}"] = v
    return data


def form(rows, initial=0, **board):
    data = {"shifts-TOTAL_FORMS": str(len(rows)), "shifts-INITIAL_FORMS": str(initial), **board}
    for r in rows:
        data.update(r)
    return data


def three(board=""):
    return [row(0, "dawn", "이른", "07:30", "16:30", board=board), row(1, "normal", "가운데", "09:00", "18:00", board=board),
            row(2, "dinner", "늦은", "11:00", "20:00", board=board)]


@pytest.fixture
def ops(it_board):
    """가짜 직접 입력 근무표 '운영팀'(근무조 둘)."""
    board = Board.objects.create(code="ops", name="운영팀", input_mode=Board.InputMode.DIRECT)
    a = BoardShift.objects.create(board=board, key="dawn", name="이른", start=time(7, 30), end=time(16, 30))
    b = BoardShift.objects.create(board=board, key="dinner", name="늦은", start=time(11), end=time(20))
    return board, a, b


def change(board, shifts, *extra, **fields):
    """지금 정의를 그대로 보내고(필요하면 fields 로 바꾼 값) extra 줄을 더한다."""
    rows = [row(i, **{"key": s.key, "name": s.name, "start": f"{s.start:%H:%M}" if s.start else "",
                      "end": f"{s.end:%H:%M}" if s.end else "", "pk": s.pk, "board": board.pk, "active": s.active,
                      **fields.get(s.key, {})}) for i, s in enumerate(shifts)]
    rows += [{k.replace("shifts-0-", f"shifts-{len(rows) + j}-"): v for k, v in r.items()} for j, r in enumerate(extra)]
    return form(rows, initial=len(shifts), name=board.name)


def errors(r):
    return r.content.decode() if r.status_code == 200 else ""


# ── 근무표 추가 ──

def test_add_board_with_definitions(su_client, it_board):
    r = su_client.post(ADD, form(three(), code="ops", name="운영팀", input_mode="direct"))
    assert r.status_code == 302, errors(r)
    board = Board.objects.get(code="ops")
    assert board.admin_group.name == "운영팀 근무표 관리"
    assert list(BoardShift.objects.filter(board=board).order_by("start").values_list("key", "name")) == [
        ("dawn", "이른"), ("normal", "가운데"), ("dinner", "늦은")]


@pytest.mark.parametrize("code", ["운영", "Ops", "1ops", "ops-team", "a" * 17])
def test_add_board_code_must_be_short_ascii(su_client, it_board, code):
    r = su_client.post(ADD, form(three(), code=code, name="운영팀", input_mode="direct"))
    assert r.status_code == 200 and "코드는 영문 소문자로 시작하는 영문 소문자·숫자 16자 이내입니다" in r.content.decode()
    assert not Board.objects.filter(name="운영팀").exists()


def test_add_board_needs_a_shift(su_client, it_board):
    r = su_client.post(ADD, form([row(0, "lunch", "점심당번")], code="ops", name="운영팀", input_mode="direct"))
    assert r.status_code == 200 and "켜진 근무조가 하나 이상 있어야 합니다." in r.content.decode()
    assert not Board.objects.filter(code="ops").exists()


def test_add_board_group_name_clash(su_client, it_board):
    Group.objects.create(name="운영팀 근무표 관리")
    r = su_client.post(ADD, form(three(), code="ops", name="운영팀", input_mode="direct"))
    assert r.status_code == 200 and "같은 이름의 그룹이 이미 있습니다: 운영팀 근무표 관리" in r.content.decode()


def test_board_name_must_be_unique(su_client, ops, it_board):
    r = su_client.post(ADD, form(three(), code="ops2", name="운영팀", input_mode="direct"))
    assert r.status_code == 200 and "같은 이름의 근무표가 이미 있습니다: 운영팀" in r.content.decode()
    board, a, b = ops
    data = change(board, [a, b])
    data["name"] = it_board.name
    r = su_client.post(reverse("admin:duty_board_change", args=[board.pk]), data)
    assert r.status_code == 200 and f"같은 이름의 근무표가 이미 있습니다: {it_board.name}" in r.content.decode()


@pytest.mark.parametrize("rows,message", [
    ([row(0, "dawn", "이른", "07:30", "16:30"), row(1, "dinner", "늦은", "07:30", "20:00")],
     "켜진 근무조끼리 시작 시각이 달라야 합니다"),
    ([row(0, "dawn", "이른", "16:30", "07:30")], "시작·끝 시각을 넣고 시작을 끝보다 이르게 하세요"),
    ([row(0, "dawn", "이른", "07:30", "16:30"), row(1, "lunch", "점심당번", "12:00", "13:00")], "점심당번은 시각을 비웁니다"),
    ([row(0, "dawn", "date", "07:30", "16:30")], "이름은 date·day 가 아니어야 하고"),
    ([row(0, "dawn", "이른(조)", "07:30", "16:30")], "이름은 date·day 가 아니어야 하고"),
    ([row(0, "dawn", "이른", "07:30", "16:30"), row(1, "slot0", "점검", "09:00", "10:00", eligible_shifts="night")],
     "점검: 자격 근무조는 이 근무표의 근무조여야 합니다."),
    ([row(0, "dawn", "이른", "07:30", "16:30"), row(1, "normal", "가운데", "09:00", "18:00", active=False),
      row(2, "slot0", "점검", "09:00", "10:00", eligible_shifts="normal")],
     "점검: 켜진 관제의 자격 근무조는 켜진 근무조여야 합니다."),
    ([row(0, "dawn", "이른", "07:30", "16:30", eligible_types="직원")], "자격 근무조·자격 구분은 장중관제 칸에만 씁니다."),
    ([row(0, "dawn", "이른", "07:30", "16:30"), row(1, "slot0", "점검", "09:00", "10:00", default_alarm="on")],
     "기본 알림 대상은 근무조에만 씁니다."),
    ([row(0, "dawn", "같음", "07:30", "16:30"), row(1, "dinner", "같음", "11:00", "20:00")], "근무 정의 이름이 겹칩니다: 같음"),
    ([row(0, "dawn", "이른", "07:30", "16:30"), row(1, "dawn", "늦은", "11:00", "20:00")], "키가 겹칩니다: 근무조 1"),
])
def test_definition_rules(su_client, it_board, rows, message):
    r = su_client.post(ADD, form(rows, code="ops", name="운영팀", input_mode="direct"))
    body = r.content.decode()
    assert r.status_code == 200 and message in body
    assert "Constraint" not in body and "제약" not in body and "name의" not in body and "key의" not in body
    assert not Board.objects.filter(code="ops").exists()


def test_slot_with_shift_eligibility_saves(su_client, it_board):
    rows = three() + [row(3, "slot0", "점검", "09:00", "10:00", eligible_shifts="normal", eligible_types="직원")]
    r = su_client.post(ADD, form(rows, code="ops", name="운영팀", input_mode="direct"))
    assert r.status_code == 302, errors(r)
    s = BoardShift.objects.get(board__code="ops", key="slot0")
    assert (s.eligible_shifts, s.eligible_types) == (["normal"], ["직원"])


# ── 근무표 고치기 ──

def test_change_page_locks_code_mode_keys_and_has_no_delete(su_client, ops):
    board, *_ = ops
    body = su_client.get(reverse("admin:duty_board_change", args=[board.pk])).content.decode()
    assert 'name="name"' in body and 'name="code"' not in body and 'name="input_mode"' not in body
    assert reverse("admin:auth_group_change", args=[board.admin_group_id]) in body  # 관리 그룹 링크(그룹 관리자 지정)
    assert 'name="shifts-0-active"' in body and 'name="shifts-0-DELETE"' not in body
    assert '<select name="shifts-0-key"' in body and "disabled" in body.split('name="shifts-0-key"')[1].split(">")[0]


def test_rename_board_and_add_definition(su_client, ops):
    board, a, b = ops
    data = change(board, [a, b], row(0, "normal", "가운데", "09:00", "18:00", board=board.pk))
    data["name"] = "운영팀2"
    r = su_client.post(reverse("admin:duty_board_change", args=[board.pk]), data)
    assert r.status_code == 302, errors(r)
    board.refresh_from_db()
    assert board.name == "운영팀2" and BoardShift.objects.filter(board=board).count() == 3


def test_saved_definition_key_and_delete_ignored_but_can_be_turned_off(su_client, ops):
    board, a, b = ops
    url = reverse("admin:duty_board_change", args=[board.pk])
    data = change(board, [a, b], dawn={"key": "normal", "active": False})  # 키는 잠겨 있어 보낸 값이 무시된다
    data["shifts-0-DELETE"] = "on"  # 지우기 칸이 없다
    data["shifts-1-name"] = "늦은조"
    r = su_client.post(url, data)
    assert r.status_code == 302, errors(r)
    assert sorted(BoardShift.objects.filter(board=board).values_list("key", "name", "active")) == [
        ("dawn", "이른", False), ("dinner", "늦은조", True)]


def test_turning_off_last_input_shift_of_a_department_is_refused(su_client, ops):
    board, a, b = ops
    Department.objects.create(code="OPS", name="운영", shifts="dawn", board=board)
    r = su_client.post(reverse("admin:duty_board_change", args=[board.pk]), change(board, [a, b], dawn={"active": False}))
    assert r.status_code == 200 and "운영 부서에 켜진 근무조가 하나도 남지 않습니다" in r.content.decode()
    a.refresh_from_db()
    assert a.active


def test_board_cannot_be_deleted(su_client, ops):
    board, *_ = ops
    assert su_client.post(reverse("admin:duty_board_delete", args=[board.pk]), {"post": "yes"}).status_code == 403
    assert Board.objects.filter(pk=board.pk).exists()


# ── 모델에서도 막는다(관리 화면을 거치지 않는 길) ──

def test_model_refuses_key_change_and_delete(ops):
    board, a, b = ops
    a.key = "normal"
    with pytest.raises(ValidationError, match="저장한 근무 정의의 키·근무표는 바꿀 수 없습니다"):
        a.full_clean()
    a.refresh_from_db()
    with pytest.raises(ValidationError, match="저장한 근무 정의는 지울 수 없습니다"):
        a.delete()
    assert BoardShift.objects.filter(pk=a.pk).exists()


def test_model_refuses_bad_code_on_create(it_board):
    with pytest.raises(ValidationError, match="코드는 영문 소문자로"):
        Board(code="운영", name="운영팀").full_clean()


def test_direct_board_has_one_department(ops, it_board):
    board, *_ = ops
    Department.objects.create(code="OPS", name="운영", shifts="dawn", board=board)
    data = {"code": "OPS2", "name": "운영2", "board": board.pk, "order": 1, "shifts": ["dawn"], "managers": []}
    f = DepartmentForm(data)
    assert not f.is_valid() and "직접 입력 근무표에는 부서를 하나만 둘 수 있습니다." in str(f.errors["board"])
    with pytest.raises(ValidationError, match="부서를 하나만"):
        Department(code="OPS3", name="운영3", shifts="dawn", board=board).full_clean()
    it = DepartmentForm({**data, "board": it_board.pk, "shifts": ["dawn"]})
    assert it.is_valid(), it.errors  # 부서별 취합 근무표는 여러 부서


# ── 그룹 관리자 ──

def test_group_page_hides_permissions_and_edits_keepers(su_client, it_board, admin_user, make_member):
    group = it_board.admin_group
    html = su_client.get(reverse("admin:auth_group_change", args=[group.pk])).content.decode()
    assert 'name="name"' in html and 'name="permissions"' not in html and 'name="members"' not in html
    keeper = make_member("가상관리", user=True)
    r = su_client.post(reverse("admin:auth_group_change", args=[group.pk]), {
        "name": group.name, "keepers-TOTAL_FORMS": "1", "keepers-INITIAL_FORMS": "0",
        "keepers-0-group": group.pk, "keepers-0-user": keeper.pk,
    })
    assert r.status_code == 302, errors(r)
    assert list(GroupKeeper.objects.values_list("group", "user")) == [(group.pk, keeper.pk)]


# ── 새 부서: 근무표의 근무조만 ──

def test_new_department_shifts_checked_against_chosen_board(su_client, ops):
    board, *_ = ops
    url = reverse("admin:duty_department_add")
    assert "근무조 1" in su_client.get(url).content.decode()  # 근무표를 고르기 전이라 중립 이름
    data = {"code": "OPS", "name": "운영", "board": board.pk, "order": 1, "shifts": ["dawn", "normal"], "managers": []}
    r = su_client.post(url, data)
    assert r.status_code == 200 and "이 근무표에 켜진 근무조가 아닙니다: 근무조 2" in r.content.decode()
    r = su_client.post(url, {**data, "shifts": ["dinner", "dawn"]})
    assert r.status_code == 302, errors(r)
    assert Department.objects.get(code="OPS").shifts == "dawn,dinner"  # 시작 시각 순
