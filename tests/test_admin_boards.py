"""관리 화면(슈퍼유저 전용): 근무표·근무 정의 편집과 설계 4.3 검증, 그룹 관리자 지정(3단계). 이름은 모두 가상."""
from datetime import time

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.urls import reverse

from duty.admin import STEP_FIELDS, BoardForm, DepartmentForm
from duty.models import Board, BoardShift, Department, GroupKeeper, User
from tests.it_defs import OPS_STEPS

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


def steps_form(board=None, **names):
    """근무표 폼의 단계 칸(체크박스는 켤 때만 보낸다). board 가 없으면 작성 중·마감을 끈 시장운영실 모양."""
    b = board or Board(**OPS_STEPS)
    data = {f: getattr(b, f) for f in STEP_FIELDS} | {f: "on" for f in ("use_draft", "use_close") if getattr(b, f)}
    return data | names


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
    board = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
    a = BoardShift.objects.create(board=board, key="dawn", name="이른", start=time(7, 30), end=time(16, 30))
    b = BoardShift.objects.create(board=board, key="dinner", name="늦은", start=time(11), end=time(20))
    return board, a, b


def _saved_extras(s):
    """자격·기본 알림도 저장값 그대로(체크박스는 켤 때만)."""
    out = {k: getattr(s, k) for k in ("eligible_shifts", "eligible_types") if getattr(s, k)}
    return {**out, "default_alarm": "on"} if s.default_alarm else out


def change(board, shifts, *extra, **fields):
    """지금 정의를 그대로 보내고(필요하면 fields 로 바꾼 값) extra 줄을 더한다."""
    rows = [row(i, **{"key": s.key, "name": s.name, "start": f"{s.start:%H:%M}" if s.start else "",
                      "end": f"{s.end:%H:%M}" if s.end else "", "pk": s.pk, "board": board.pk, "active": s.active,
                      **_saved_extras(s), **fields.get(s.key, {})}) for i, s in enumerate(shifts)]
    rows += [{k.replace("shifts-0-", f"shifts-{len(rows) + j}-"): v for k, v in r.items()} for j, r in enumerate(extra)]
    return form(rows, initial=len(shifts), name=board.name, **steps_form(board))


def errors(r):
    return r.content.decode() if r.status_code == 200 else ""


# ── 근무표 추가 ──

def test_add_board_with_definitions(su_client, it_board):
    r = su_client.post(ADD, form(three(), code="ops", name="운영팀", **steps_form()))
    assert r.status_code == 302, errors(r)
    board = Board.objects.get(code="ops")
    assert board.admin_group.name == "운영팀 근무표 관리"
    assert list(BoardShift.objects.filter(board=board).order_by("start").values_list("key", "name")) == [
        ("dawn", "이른"), ("normal", "가운데"), ("dinner", "늦은")]


@pytest.mark.parametrize("code", ["운영", "Ops", "1ops", "ops-team", "a" * 17])
def test_add_board_code_must_be_short_ascii(su_client, it_board, code):
    r = su_client.post(ADD, form(three(), code=code, name="운영팀", **steps_form()))
    assert r.status_code == 200 and "코드는 영문 소문자로 시작하는 영문 소문자·숫자 16자 이내입니다" in r.content.decode()
    assert not Board.objects.filter(name="운영팀").exists()


def test_add_board_needs_a_shift(su_client, it_board):
    r = su_client.post(ADD, form([row(0, "lunch", "점심당번")], code="ops", name="운영팀", **steps_form()))
    assert r.status_code == 200 and "켜진 근무조가 하나 이상 있어야 합니다." in r.content.decode()
    assert not Board.objects.filter(code="ops").exists()


def test_add_board_group_name_clash(su_client, it_board):
    Group.objects.create(name="운영팀 근무표 관리")
    r = su_client.post(ADD, form(three(), code="ops", name="운영팀", **steps_form()))
    assert r.status_code == 200 and "같은 이름의 그룹이 이미 있습니다: 운영팀 근무표 관리" in r.content.decode()


def test_board_name_must_be_unique(su_client, ops, it_board):
    r = su_client.post(ADD, form(three(), code="ops2", name="운영팀", **steps_form()))
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
    r = su_client.post(ADD, form(rows, code="ops", name="운영팀", **steps_form()))
    body = r.content.decode()
    assert r.status_code == 200 and message in body
    assert "Constraint" not in body and "제약" not in body and "name의" not in body and "key의" not in body
    assert not Board.objects.filter(code="ops").exists()


def test_slot_with_shift_eligibility_saves(su_client, it_board):
    rows = three() + [row(3, "slot0", "점검", "09:00", "10:00", eligible_shifts="normal", eligible_types="직원")]
    r = su_client.post(ADD, form(rows, code="ops", name="운영팀", **steps_form()))
    assert r.status_code == 302, errors(r)
    s = BoardShift.objects.get(board__code="ops", key="slot0")
    assert (s.eligible_shifts, s.eligible_types) == (["normal"], ["직원"])


# ── 근무표 고치기 ──

def test_change_page_locks_code_steps_keys_and_has_no_delete(su_client, ops):
    board, *_ = ops
    body = su_client.get(reverse("admin:duty_board_change", args=[board.pk])).content.decode()
    assert 'name="name"' in body and 'name="code"' not in body and 'name="input_mode"' not in body
    assert "회차 단계" in body and 'name="use_close"' not in body and 'name="step_collecting"' not in body  # 1단계: 읽기 전용
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


def test_board_without_close_takes_second_department(ops, it_board):
    """부서 수 제한은 없다(근무표 통합 설계 5.3)."""
    board, *_ = ops
    Department.objects.create(code="OPS", name="운영", shifts="dawn", board=board)
    f = DepartmentForm({"code": "OPS2", "name": "운영2", "board": board.pk, "order": 1, "shifts": ["dawn"], "managers": []})
    assert f.is_valid(), f.errors


# ── 회차 단계 칸(근무표 통합 설계 5.1) ──

def test_add_board_saves_steps(su_client, it_board):
    r = su_client.post(ADD, form(three(), code="ops", name="운영팀", **steps_form()))
    assert r.status_code == 302, errors(r)
    b = Board.objects.get(code="ops")
    assert (b.use_draft, b.use_close, b.step_collecting, b.step_generated) == (False, False, "입력 중", "확정")
    assert "입력 중 → 확정 → 배포됨" in su_client.get(reverse("admin:duty_board_changelist")).content.decode()


@pytest.mark.parametrize("names,msg", [
    ({"step_generated": "입력 중"}, "단계 이름이 겹칩니다: 입력 중"),
    ({"step_closed": "마\n감"}, "단계 이름에 줄바꿈을 쓸 수 없습니다."),
    ({"step_draft": ""}, "필수 항목입니다."),
    ({"step_generated": "됨"}, "버튼 이름이 비거나 다른 버튼과 같아집니다: []"),            # 생성 버튼 글자가 빈다
    ({"use_close": "on", "step_generated": "입력 마감됨"}, "버튼 이름이 비거나 다른 버튼과 같아집니다: [입력 마감]"),
])
def test_step_names_checked(su_client, it_board, names, msg):
    r = su_client.post(ADD, form(three(), code="ops", name="운영팀", **steps_form(**names)))
    assert r.status_code == 200 and msg in r.content.decode()
    assert not Board.objects.filter(code="ops").exists()


@pytest.mark.parametrize("data,field,label", [
    # 관제 있을 때의 [장중관제 생성]과 겹친다: 생성됨 이름을 고쳐도 남으니 취합 중 이름 칸에(설계 5.4)
    ({"use_close": "on", "step_collecting": "장중관제 중", "step_closed": "생성", "step_generated": "장중관제 생성됨"},
     "step_collecting", "장중관제 생성"),
    # 마감 글자가 열기 글자와 같다: 마감 이름 칸에
    ({"use_draft": "on", "use_close": "on", "step_closed": "열기"}, "step_closed", "입력 열기"),
    ({"name": "", "step_generated": "됨"}, "step_generated", ""),  # 다른 칸 오류가 있어도 버튼 글자는 본다
    ({"use_draft": "on", "step_generated": "됨"}, "step_generated", ""),  # 옮길 곳이 둘이라 취소 글자가 비어도
])
def test_bad_button_error_field(it_board, data, field, label):
    f = BoardForm({"code": "ops", "name": "운영팀"} | steps_form() | data)
    assert not f.is_valid()
    assert f.errors[field] == [f"버튼 이름이 비거나 다른 버튼과 같아집니다: [{label}]"]


def test_saved_board_steps_are_read_only(su_client, ops):
    """1단계: 저장된 근무표의 단계는 관리 화면에서 바꾸지 않는다(보낸 값은 무시, 설계 5.1). 3단계에서 연다."""
    board, a, b = ops
    data = change(board, [a, b]) | steps_form(board, use_draft="on", step_collecting="모으는 중")
    r = su_client.post(reverse("admin:duty_board_change", args=[board.pk]), data)
    assert r.status_code == 302, errors(r)
    board.refresh_from_db()
    assert (board.use_draft, board.step_collecting) == (False, "입력 중")


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


# ── 관리 화면은 슈퍼유저만 ──

def test_staff_with_model_permissions_cannot_use_board_admin(client, ops):
    from django.contrib.auth.models import Permission
    board, a, b = ops
    staff = User.objects.create_user("staff1", password="unused-Pw-123", name="스태프", is_staff=True)
    staff.user_permissions.set(Permission.objects.filter(content_type__app_label="duty",
                                                         codename__in=["change_board", "view_board", "change_boardshift",
                                                                       "add_boardshift", "view_boardshift"]))
    client.force_login(staff)
    url = reverse("admin:duty_board_change", args=[board.pk])
    login = reverse("admin:login")
    r = client.get(url)
    assert r.status_code == 302 and r.url.startswith(login)
    data = change(board, [a, b], dawn={"name": "바뀜"})
    data["name"] = "바뀐 운영팀"
    r = client.post(url, data)
    assert r.status_code == 302 and r.url.startswith(login)
    board.refresh_from_db()
    a.refresh_from_db()
    assert board.name == "운영팀" and a.name == "이른"


# ── 이름을 바꾸면 관리 그룹 이름도 ──

def test_rename_board_renames_admin_group(su_client, ops):
    board, a, b = ops
    data = change(board, [a, b])
    data["name"] = "운영본부"
    r = su_client.post(reverse("admin:duty_board_change", args=[board.pk]), data)
    assert r.status_code == 302, errors(r)
    board.refresh_from_db()
    assert board.name == "운영본부" and board.admin_group.name == "운영본부 근무표 관리"


def test_rename_board_refused_when_group_name_taken(su_client, ops):
    board, a, b = ops
    other = Group.objects.create(name="운영본부 근무표 관리")
    data = change(board, [a, b], dawn={"name": "바뀜"})
    data["name"] = "운영본부"
    r = su_client.post(reverse("admin:duty_board_change", args=[board.pk]), data)
    assert r.status_code == 200 and "같은 이름의 그룹이 이미 있습니다: 운영본부 근무표 관리" in r.content.decode()
    board.refresh_from_db()
    a.refresh_from_db()
    assert board.name == "운영팀" and board.admin_group.name == "운영팀 근무표 관리" and a.name == "이른"
    assert Group.objects.get(pk=other.pk).name == "운영본부 근무표 관리"


# ── 배포된 회차가 있는 정의를 고쳐도 근무표·캘린더·배포 취소가 그대로(회귀) ──

def test_editing_definitions_keeps_published_rows(su_client, client, it_board, make_member, fixed_today, settings):
    from datetime import date

    from duty.models import Commute, DutyAssignment, Period
    from duty.services import calendar
    from duty.services.publish import publish, unpublish
    from duty.shifts import weekdays
    from tests.test_calendar_feed import vevents

    settings.SITE_URL = "https://duty.example"
    fixed_today(date(2026, 11, 11))
    me = make_member("가상일", user=True)
    d1, d2 = date(2026, 11, 12), date(2026, 11, 13)
    a = Period.objects.create(board=it_board, name="A", start_date=d1, end_date=d2, status=Period.Status.GENERATED)
    for x in weekdays(d1, d2):
        Commute.objects.create(period=a, date=x, member=me, shift="dawn")
        DutyAssignment.objects.create(period=a, date=x, cell="slot0", member=me)
    b = Period.objects.create(board=it_board, name="B", start_date=d2, end_date=d2, status=Period.Status.GENERATED)
    Commute.objects.create(period=b, date=d2, member=me, shift="normal")
    publish(a, d1)
    publish(b, d2)

    # 새벽(출근)·08:30 관제 칸의 이름·시작 시각을 바꾸고 끈다. 나머지 칸은 지금 값 그대로 보낸다
    shifts = list(BoardShift.objects.filter(board=it_board).order_by("pk"))
    data = change(it_board, shifts, dawn={"name": "새벽2", "start": "07:00", "active": False},
                  slot0={"name": "첫 관제", "start": "08:40", "active": False})
    for i, s in enumerate(shifts):
        data[f"shifts-{i}-eligible_shifts"] = s.eligible_shifts
        data[f"shifts-{i}-eligible_types"] = s.eligible_types
        if s.default_alarm:
            data[f"shifts-{i}-default_alarm"] = "on"
    r = su_client.post(reverse("admin:duty_board_change", args=[it_board.pk]), data)
    assert r.status_code == 302, errors(r)
    assert BoardShift.objects.get(board=it_board, key="slot0").eligible_shifts == ["normal"]  # 다른 칸은 그대로

    # 근무표: 꺼진 정의의 행도 바뀐 이름으로 보인다(설계 4.3 '끄면 새 입력에서만 빠진다')
    client.force_login(me)
    body = client.get(f"/day/{d1}/").content.decode()
    assert "새벽2" in body and "첫 관제" in body and "가상일" in body

    # 캘린더: 바뀐 이름·시작 시각(KST 07:00 = UTC 전날 22:00, 08:40 = UTC 23:40)
    token = calendar.issue(me).rsplit("/", 1)[1].removesuffix(".ics")
    evs = {e["DTSTART"]: e["SUMMARY"] for e in vevents(client.get(f"/calendar/{token}.ics"))}
    assert evs["20261111T220000Z"].startswith("새벽2") and evs["20261111T234000Z"] == "장중관제 첫 관제"

    # 배포 취소: B 가 덮어쓴 A 의 13일 행(꺼진 정의의 행)이 되살아난다
    unpublish(b)
    assert sorted(Commute.objects.filter(period=a).values_list("date", "shift")) == [(d1, "dawn"), (d2, "dawn")]
    assert DutyAssignment.objects.filter(period=a, cell="slot0").count() == 2


def test_it_board_save_without_rename_keeps_admin_group(su_client, it_board):
    """IT 근무표 그룹 이름은 'IT 근무표 관리'(마이그레이션 0011). 근무 정의만 고친 저장은 그룹 이름을 바꾸지 않는다."""
    Group.objects.filter(pk=it_board.admin_group_id).update(name="IT 근무표 관리")
    Group.objects.create(name="IT 당번표 근무표 관리")  # 이름을 안 바꾸면 겹침 검사도 하지 않는다
    shifts = list(it_board.shifts.order_by("id"))
    data = change(it_board, shifts, normal={"name": "정상근무"})
    r = su_client.post(reverse("admin:duty_board_change", args=[it_board.pk]), data)
    assert r.status_code == 302, errors(r)
    it_board.refresh_from_db()
    assert it_board.admin_group.name == "IT 근무표 관리"
    assert it_board.shifts.get(key="normal").name == "정상근무"


def test_active_slot_needs_eligible_shift(su_client, ops):
    board, a, b = ops
    data = change(board, [a, b], row(2, "slot1", "관제", "09:00", "15:30", board=board.pk))
    r = su_client.post(reverse("admin:duty_board_change", args=[board.pk]), data)
    assert r.status_code == 200 and "장중관제 칸은 자격 근무조를 하나 이상 골라야 합니다." in r.content.decode()
    assert not board.shifts.filter(key="slot1").exists()
