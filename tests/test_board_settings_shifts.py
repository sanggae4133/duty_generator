"""[근무표 설정] 근무 정의와 부서·회차 단계 저장(근무표 통합 설계 6.2·7.2·7.3). 이름은 모두 가상."""
from datetime import date, time, timedelta

import pytest
from django.contrib.admin.models import LogEntry
from django.core.exceptions import PermissionDenied
from django.utils.datastructures import MultiValueDict

from duty.errors import DutyError
from duty.forms import StepsForm, shift_forms
from duty.models import Board, BoardShift, Commute, Department, DutyAssignment, Period, User
from duty.services import board_settings as bs
from duty.services import collect

S = Period.Status
MON = date(2026, 11, 16)


@pytest.fixture
def ops_admin(ops_board):
    u = User.objects.create_user("opsadm", password=None, name="가상운영")
    ops_board.admin_group.user_set.add(u)
    return u


def shift_data(board, change=None, extra=None, depts=None):
    """설정 화면이 보내는 것과 같은 값: 지금 근무 정의·부서 그대로에 change(키별)·extra(새 줄)·depts(부서 코드별)를 덮는다.
    체크박스는 켤 때만 보낸다(None = 끔)."""
    shifts = list(BoardShift.objects.filter(board=board).order_by("id"))
    data = {"shifts-TOTAL_FORMS": [str(len(shifts) + 1)], "shifts-INITIAL_FORMS": [str(len(shifts))]}

    def put(prefix, row):
        for k, v in row.items():
            if v not in (None, "", []):
                data[f"{prefix}-{k}"] = v if isinstance(v, list) else [str(v)]
    for i, s in enumerate(shifts):
        put(f"shifts-{i}", {"id": s.pk, "board": board.pk, "key": s.key, "name": s.name,
                            "start": s.start and f"{s.start:%H:%M}", "end": s.end and f"{s.end:%H:%M}",
                            "eligible_shifts": s.eligible_shifts, "eligible_types": s.eligible_types,
                            "default_alarm": "on" if s.default_alarm else None, "active": "on" if s.active else None,
                            **(change or {}).get(s.key, {})})
    put(f"shifts-{len(shifts)}", extra or {"active": "on"})  # 손대지 않은 빈 추가 줄(브라우저는 켜진 '사용'을 보낸다)
    for d in board.departments.all():
        put(f"d-{d.code}", {"shifts": d.shift_keys(), "lunch_start": d.lunch_start and f"{d.lunch_start:%H:%M}",
                            "lunch_end": d.lunch_end and f"{d.lunch_end:%H:%M}", **(depts or {}).get(d.code, {})})
    return MultiValueDict(data)


def save(by, board, data, confirm=None):
    formset, dept_forms = shift_forms(board, data)
    return bs.save_shifts(by, board, formset, dept_forms, confirm), formset, dept_forms


def _dept():
    return Department.objects.get(code="OPS")


# ── 근무 정의와 부서를 한 번에 ──

def test_saves_definitions_and_departments_together(ops_board, ops_admin):
    data = shift_data(ops_board, change={"normal": {"name": "중간"}},
                      depts={"OPS": {"shifts": ["dinner", "dawn"], "lunch_start": "11:30", "lunch_end": "12:30"}})
    assert save(ops_admin, ops_board, data)[0] == []
    assert BoardShift.objects.get(board=ops_board, key="normal").name == "중간"
    d = _dept()
    assert (d.shifts, d.lunch_start, d.lunch_end) == ("dawn,dinner", time(11, 30), time(12, 30))  # 시작 시각 순
    assert LogEntry.objects.get().change_message == "근무표 ops: 근무 정의·부서 저장"


def test_new_shift_is_saved_and_not_yet_in_department(ops_board, ops_admin):
    data = shift_data(ops_board, extra={"key": "night", "name": "밤", "start": "13:00", "end": "22:00", "active": "on"})
    save(ops_admin, ops_board, data)
    assert BoardShift.objects.get(board=ops_board, key="night").name == "밤"
    assert _dept().shifts == "dawn,normal,dinner"  # 새 근무조는 저장한 뒤 부서 칸에 생긴다(한 번 더 저장)


def test_turn_off_shift_and_move_department_in_same_save(ops_board, ops_admin):
    Department.objects.filter(code="OPS").update(shifts="dawn")
    data = shift_data(ops_board, change={"dawn": {"active": None}}, depts={"OPS": {"shifts": ["normal"]}})
    save(ops_admin, ops_board, data)
    assert not BoardShift.objects.get(board=ops_board, key="dawn").active
    assert _dept().shifts == "normal"  # 그린 때 켜져 있어 체크박스로 보였고, 체크를 풀었으니 뺀다


def test_turned_off_shift_comes_back_in_department(ops_board, ops_admin):
    """화면에는 켜진 근무조만 나오지만, 꺼진 근무조의 부서 키는 다른 저장에도 남아 다시 켜면 입력 표 칸이 돌아온다."""
    save(ops_admin, ops_board, shift_data(ops_board, change={"dinner": {"active": None}}))
    save(ops_admin, ops_board, shift_data(ops_board, change={"normal": {"name": "중간"}},
                                         depts={"OPS": {"shifts": ["dawn", "normal"]}}))  # 상관없는 저장(체크박스는 켜진 둘뿐)
    assert _dept().shifts == "dawn,normal,dinner"
    # 다시 켠다: 부서 덩어리에는 아직 체크박스가 없어(그린 때 꺼져 있었다) 켜진 둘만 보낸다
    save(ops_admin, ops_board, shift_data(ops_board, change={"dinner": {"active": "on"}}, depts={"OPS": {"shifts": ["dawn", "normal"]}}))
    assert collect.input_keys(_dept()) == ["dawn", "normal", "dinner"]


def test_department_left_without_active_shift_is_refused(ops_board, ops_admin):
    Department.objects.filter(code="OPS").update(shifts="dawn")
    formset, dept_forms = shift_forms(ops_board, shift_data(ops_board, change={"dawn": {"active": None}}))
    with pytest.raises(DutyError, match="저장하지 않았습니다"):
        bs.save_shifts(ops_admin, ops_board, formset, dept_forms)
    assert formset.non_form_errors() == ["운영 부서에 켜진 근무조가 하나도 남지 않습니다. 아래 부서에서 켜진 근무조를 하나 이상 체크하세요."]
    assert BoardShift.objects.get(board=ops_board, key="dawn").active


@pytest.mark.parametrize("dept,msg", [
    ({"lunch_start": "11:30"}, "점심 시각은 둘 다 비우거나, 둘 다 넣고 시작을 끝보다 이르게 하세요."),
    ({"lunch_start": "12:30", "lunch_end": "11:30"}, "점심 시각은 둘 다 비우거나, 둘 다 넣고 시작을 끝보다 이르게 하세요."),
    ({"shifts": []}, "출근조를 하나 이상 선택하세요."),
])
def test_department_checks(ops_board, ops_admin, dept, msg):
    formset, dept_forms = shift_forms(ops_board, shift_data(ops_board, change={"normal": {"name": "중간"}}, depts={"OPS": dept}))
    with pytest.raises(DutyError, match="저장하지 않았습니다"):
        bs.save_shifts(ops_admin, ops_board, formset, dept_forms)
    assert msg in str(dept_forms[0].errors)
    assert BoardShift.objects.get(board=ops_board, key="normal").name == "가운데"  # 근무 정의도 저장하지 않는다


def test_invalid_department_hides_admin_only_message(ops_board, ops_admin):
    """부서 칸이 틀리면 표 검사에 저장된 부서 출근조를 쓰지 않는다: 관리 화면용 '부서의 출근조를 먼저 바꾸세요'가 나오지 않게."""
    Department.objects.filter(code="OPS").update(shifts="dawn")
    formset, dept_forms = shift_forms(ops_board, shift_data(ops_board, change={"dawn": {"active": None}},
                                                            depts={"OPS": {"shifts": ["normal"], "lunch_start": "11:30"}}))
    with pytest.raises(DutyError, match="저장하지 않았습니다"):
        bs.save_shifts(ops_admin, ops_board, formset, dept_forms)
    assert "먼저 바꾸세요" not in str(formset.non_form_errors())


# ── 부서에서 근무조를 뺄 때: 배포 전 회차 출근표가 있으면 확인 ──

@pytest.fixture
def rows(ops_board):
    m = User.objects.create_user("OPS801", password=None, name="가상하나", department=_dept(), type="직원")
    open_ = Period.objects.create(board=ops_board, name="이번 회차", start_date=MON, end_date=MON, status=S.COLLECTING)
    done = Period.objects.create(board=ops_board, name="지난 회차", start_date=MON, end_date=MON, status=S.PUBLISHED)
    for p in (open_, done):
        Commute.objects.create(period=p, date=MON, member=m, shift="dinner")
    return open_


def test_removing_department_shift_with_rows_asks_again(ops_board, ops_admin, rows):
    data = shift_data(ops_board, depts={"OPS": {"shifts": ["dawn", "normal"]}})
    msg = ("운영 부서에서 '늦은'을 빼면 배포 전 회차(이번 회차)의 그 근무조 출근표 1행이 다음 표 저장 때 지워집니다. "
           "그래도 저장하려면 [그래도 저장]을 누르세요.")
    for confirm in (None, 2):  # 확인 없이, 또는 본 행 수가 지금과 다르면(그사이 바뀜) 다시 묻는다
        with pytest.raises(bs.NeedsConfirm) as e:
            save(ops_admin, ops_board, data, confirm)
        assert (str(e.value), e.value.rows) == (msg, 1)
        assert _dept().shifts == "dawn,normal,dinner"
    save(ops_admin, ops_board, data, confirm=1)
    assert _dept().shifts == "dawn,normal"


def test_turning_shift_off_does_not_ask(ops_board, ops_admin, rows):
    """꺼진 근무조의 출근표는 표 저장 때 남으므로(collect._kept_keys) 끄면서 빼면 묻지 않는다."""
    save(ops_admin, ops_board, shift_data(ops_board, change={"dinner": {"active": None}},
                                         depts={"OPS": {"shifts": ["dawn", "normal"]}}))
    assert _dept().shifts == "dawn,normal"


# ── 생성됨 회차에 배정이 남은 관제 정의를 끄면 경고 ──

def test_turning_off_slot_with_generated_rows_warns(it_board, depts, admin_user, make_member):
    m = make_member("가상가")
    p = Period.objects.create(board=it_board, name="가상 회차", start_date=MON, end_date=MON + timedelta(days=1),
                              status=S.GENERATED)
    for d in p.dates():
        DutyAssignment.objects.create(period=p, date=d, cell="slot0", member=m)
    warnings, *_ = save(admin_user, it_board, shift_data(it_board, change={"slot0": {"active": None}}))
    assert warnings == ["생성됨 회차(가상 회차)에 '08:30~09:30' 배정 2개가 남아 있습니다. "
                        "다시 생성하거나 다른 상태로 옮기면 지워지고, 그대로 배포하면 근무표에 나옵니다."]
    assert not BoardShift.objects.get(board=it_board, key="slot0").active


# ── 범위(IDOR)·권한 ──

def test_shift_forms_of_other_board_refused(ops_board, ops_admin, it_board, depts, admin_user):
    it_formset, it_depts = shift_forms(it_board, shift_data(it_board))
    ops_formset, ops_depts = shift_forms(ops_board, shift_data(ops_board))
    for formset, dept_forms in ((it_formset, ops_depts), (ops_formset, it_depts)):
        with pytest.raises(PermissionDenied):
            bs.save_shifts(ops_admin, ops_board, formset, dept_forms)
    with pytest.raises(PermissionDenied):  # IT 관리자는 운영팀 근무표를 고치지 못한다
        bs.save_shifts(admin_user, ops_board, ops_formset, ops_depts)
    assert not LogEntry.objects.exists()


# ── 회차 단계 ──

def _steps(board, **over):
    data = {f: getattr(board, f) for f in ("step_draft", "step_collecting", "step_closed", "step_generated", "step_published")}
    data |= {f: "on" for f in ("use_draft", "use_close") if getattr(board, f)}
    return StepsForm({k: v for k, v in (data | over).items() if v is not None}, instance=Board.objects.get(pk=board.pk))


def test_save_steps_writes_only_step_fields(ops_board, ops_admin):
    """단계 저장은 단계 칸만 쓴다: 폼을 만든 뒤 바뀐 이름(다른 칸)을 되돌리지 않는다(설계 6.2)."""
    form = _steps(ops_board, step_draft="준비 중")
    other = Board.objects.get(pk=ops_board.pk)  # 다른 화면에서 이름을 바꿨다(관리 그룹 이름도 함께 바뀐다)
    other.name = "운영팀2"
    other.save()
    bs.save_steps(ops_admin, ops_board, form)
    b = Board.objects.get(pk=ops_board.pk)
    assert (b.name, b.step_draft) == ("운영팀2", "준비 중")
    assert b.admin_group.name == "운영팀2 근무표 관리"  # 낡은 이름으로 관리 그룹 이름을 되돌리지 않는다


def test_department_save_keeps_input_group_set_meanwhile(ops_board, ops_admin):
    """부서 저장은 출근조·점심 칸만 쓴다: 화면을 그린 뒤 생긴 입력 그룹 연결을 지우지 않는다."""
    formset, dept_forms = shift_forms(ops_board, shift_data(ops_board, depts={"OPS": {"lunch_start": "11:30", "lunch_end": "12:30"}}))
    group = _dept().ensure_input_group()
    bs.save_shifts(ops_admin, ops_board, formset, dept_forms)
    assert _dept().input_group_id == group.pk and _dept().lunch_start == time(11, 30)


def test_save_steps(ops_board, ops_admin):
    assert bs.save_steps(ops_admin, ops_board, _steps(ops_board, use_draft="on", step_draft="준비 중")) == ""
    ops_board.refresh_from_db()
    assert ops_board.steps()[:2] == ["draft", "collecting"] and ops_board.step_draft == "준비 중"
    assert LogEntry.objects.get().change_message == "근무표 ops: 회차 단계 저장"


def test_save_steps_warns_about_stranded_periods(it_board, admin_user):
    Period.objects.create(board=it_board, name="가상", start_date=MON, end_date=MON, status=S.CLOSED)
    assert (bs.save_steps(admin_user, it_board, _steps(it_board, use_close=None))
            == "'마감' 단계에 회차 1개가 남아 있습니다. 회차 화면에서 다른 단계로 옮기세요.")


def test_save_steps_refuses_bad_names_and_other_board(ops_board, ops_admin, it_board):
    form = _steps(ops_board, step_generated="됨")
    with pytest.raises(DutyError, match="저장하지 않았습니다"):
        bs.save_steps(ops_admin, ops_board, form)
    assert form.errors["step_generated"] == ["버튼 이름이 비거나 다른 버튼과 같아집니다: []"]
    with pytest.raises(PermissionDenied):
        bs.save_steps(ops_admin, ops_board, _steps(it_board))  # 다른 근무표의 단계 폼
    ops_board.refresh_from_db()
    assert ops_board.step_generated == "확정" and not LogEntry.objects.exists()
