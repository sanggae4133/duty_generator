"""[근무표 설정] 서비스(근무표 통합 설계 6.2·8): 권한·근무표 범위(IDOR)·재직 관리자 한 명 이상·기록. 이름은 모두 가상."""
import logging

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied

from duty.errors import DutyError
from duty.models import Department, User
from duty.services import board_settings as bs
from duty.services import boards


@pytest.fixture
def ops_admin(ops_board):
    """운영팀 관리자 가상운영(부서 없는 계정)."""
    u = User.objects.create_user("opsadm", password=None, name="가상운영")
    ops_board.admin_group.user_set.add(u)
    return u


@pytest.fixture
def ops_dept(ops_board):
    return Department.objects.get(code="OPS")


def _ops_member(dept, name, username, active=True):
    return User.objects.create_user(username, password=None, name=name, department=dept, type="직원", is_active=active)


def _admins(board):
    return set(board.admin_group.user_set.values_list("username", flat=True))


# ── 권한: 그 근무표 관리자만 ──

@pytest.mark.parametrize("who", ["it_admin", "it_clerk", "superuser", "anonymous"])
def test_only_that_board_admin(who, ops_board, ops_admin, ops_dept, admin_user, make_member, depts):
    from django.contrib.auth.models import AnonymousUser
    clerk = make_member("가상담당")
    depts["MEMS"].input_group.user_set.add(clerk)
    su = User.objects.create_superuser("root", password=None, name="가상슈퍼")
    by = {"it_admin": admin_user, "it_clerk": clerk, "superuser": su, "anonymous": AnonymousUser()}[who]
    m = _ops_member(ops_dept, "가상하나", "OPS801")
    for call in (lambda: bs.add_admin(by, ops_board, m), lambda: bs.remove_admin(by, ops_board, ops_admin),
                 lambda: bs.add_assignee(by, ops_board, ops_dept, m), lambda: bs.remove_assignee(by, ops_board, ops_dept, m)):
        with pytest.raises(PermissionDenied):
            call()
    assert _admins(ops_board) == {"opsadm"} and Department.objects.get(code="OPS").input_group_id is None


# ── 관리자 넣기 ──

def test_add_admin_candidates(ops_board, ops_admin, ops_dept, make_member):
    m = _ops_member(ops_dept, "가상하나", "OPS801")
    nodept = User.objects.create_user("free1", password=None, name="가상무소속")
    gone = _ops_member(ops_dept, "가상퇴사", "OPS802", active=False)
    it_person = make_member("가상아이티")
    assert list(bs.admin_candidates(ops_board)) == [nodept, m]  # 이름 순, 이미 관리자인 가상운영은 빠진다
    bs.add_admin(ops_admin, ops_board, m)
    bs.add_admin(ops_admin, ops_board, nodept)
    assert _admins(ops_board) == {"opsadm", "OPS801", "free1"}
    for bad in (gone, it_person, m):  # 퇴사자·다른 근무표 사람·이미 관리자
        with pytest.raises(PermissionDenied):
            bs.add_admin(ops_admin, ops_board, bad)


# ── 관리자 빼기: 나 자신이나 퇴사한 관리자만, 재직 관리자 한 명 이상 ──

def test_remove_other_active_admin_is_superuser_job(ops_board, ops_admin, ops_dept):
    m = _ops_member(ops_dept, "가상하나", "OPS801")
    ops_board.admin_group.user_set.add(m)
    with pytest.raises(PermissionDenied):
        bs.remove_admin(ops_admin, ops_board, m)
    bs.remove_admin(ops_admin, ops_board, ops_admin)  # 나 자신은 된다(가상하나가 남는다)
    assert _admins(ops_board) == {"OPS801"}


def test_remove_departed_admin(ops_board, ops_admin, ops_dept):
    gone = _ops_member(ops_dept, "가상퇴사", "OPS802", active=False)
    ops_board.admin_group.user_set.add(gone)
    bs.remove_admin(ops_admin, ops_board, gone)
    assert _admins(ops_board) == {"opsadm"}


@pytest.mark.parametrize("with_departed", [False, True])
def test_last_active_admin_cannot_leave(ops_board, ops_admin, ops_dept, with_departed):
    if with_departed:  # 퇴사한 관리자만 남는 경우도 막는다
        ops_board.admin_group.user_set.add(_ops_member(ops_dept, "가상퇴사", "OPS802", active=False))
    with pytest.raises(DutyError, match="재직 중인 관리자가 아무도 남지 않습니다"):
        bs.remove_admin(ops_admin, ops_board, ops_admin)
    assert "opsadm" in _admins(ops_board)


def test_remove_admin_not_in_group(ops_board, ops_admin, ops_dept):
    with pytest.raises(PermissionDenied):
        bs.remove_admin(ops_admin, ops_board, _ops_member(ops_dept, "가상하나", "OPS801"))


def test_left_without_admin_counts_only_active(it_board, ops_board, ops_admin, admin_user):
    assert boards.left_without_admin([ops_admin]) == [ops_board]
    assert boards.left_without_admin([admin_user, ops_admin]) == [it_board, ops_board]
    ops_admin.is_active = False
    ops_admin.save()
    assert boards.left_without_admin([ops_admin]) == []  # 이미 재직 관리자가 없는 근무표에서 퇴사자 빼기는 막지 않는다


# ── 입력 담당자: 첫 담당자를 넣을 때 그룹이 생긴다 ──

def test_first_assignee_makes_input_group(ops_board, ops_admin, ops_dept):
    a, b = _ops_member(ops_dept, "가상하나", "OPS801"), _ops_member(ops_dept, "가상두리", "OPS802")
    assert list(bs.assignee_candidates(ops_board, ops_dept)) == [b, a]  # 이름 순
    bs.add_assignee(ops_admin, ops_board, ops_dept, a)
    dept = Department.objects.get(code="OPS")
    assert dept.input_group.name == "운영 출근표 입력" and list(dept.input_group.user_set.all()) == [a]
    assert list(bs.assignee_candidates(ops_board, dept)) == [b]  # 이미 든 사람은 빠진다
    with pytest.raises(PermissionDenied):
        bs.add_assignee(ops_admin, ops_board, dept, a)
    bs.remove_assignee(ops_admin, ops_board, dept, a)
    assert not dept.input_group.user_set.exists()  # 빈 그룹 = 관리자만 입력(그룹은 남는다)


def test_assignee_group_name_clash(ops_board, ops_admin, ops_dept):
    Group.objects.create(name="운영 출근표 입력")
    with pytest.raises(DutyError, match="같은 이름의 그룹이 이미 있습니다: 운영 출근표 입력. 슈퍼유저에게"):
        bs.add_assignee(ops_admin, ops_board, ops_dept, _ops_member(ops_dept, "가상하나", "OPS801"))
    assert Department.objects.get(code="OPS").input_group_id is None


def test_assignee_scope(ops_board, ops_admin, ops_dept, depts, make_member):
    """다른 근무표의 부서·사람은 PermissionDenied, 아무것도 바뀌지 않는다. 퇴사자는 넣지 않고 빼기는 된다."""
    it_person = make_member("가상아이티")
    gone = _ops_member(ops_dept, "가상퇴사", "OPS802", active=False)
    with pytest.raises(PermissionDenied):
        bs.add_assignee(ops_admin, ops_board, depts["MEMS"], _ops_member(ops_dept, "가상하나", "OPS801"))
    for bad in (it_person, gone):
        with pytest.raises(PermissionDenied):
            bs.add_assignee(ops_admin, ops_board, ops_dept, bad)
    assert not depts["MEMS"].input_group.user_set.exists() and Department.objects.get(code="OPS").input_group_id is None
    ops_dept.ensure_input_group().user_set.add(gone)
    bs.remove_assignee(ops_admin, ops_board, ops_dept, gone)
    with pytest.raises(PermissionDenied):
        bs.remove_assignee(ops_admin, ops_board, depts["MEMS"], it_person)


# ── 기록: 로그 한 줄 + LogEntry 한 줄, 실명 없음 ──

def test_every_write_logs_once_without_names(ops_board, ops_admin, ops_dept, caplog):
    m = _ops_member(ops_dept, "가상하나", "OPS801")
    caplog.set_level(logging.INFO, logger="duty.services.board_settings")
    bs.add_admin(ops_admin, ops_board, m)
    bs.add_assignee(ops_admin, ops_board, ops_dept, m)
    bs.remove_assignee(ops_admin, ops_board, ops_dept, m)
    bs.remove_admin(m, ops_board, m)  # 재직 중인 다른 관리자는 못 빼니 스스로
    assert [r.getMessage() for r in caplog.records] == [
        "board ops: 관리자 넣기 OPS801 by opsadm", "board ops: OPS 입력 담당자 넣기 OPS801 by opsadm",
        "board ops: OPS 입력 담당자 빼기 OPS801 by opsadm", "board ops: 관리자 빼기 OPS801 by OPS801"]
    rows = list(LogEntry.objects.order_by("id").values_list("user__username", "object_id", "object_repr", "change_message"))
    assert rows == [("opsadm", str(m.pk), "OPS801", "근무표 ops: 관리자 넣기"),
                    ("opsadm", str(m.pk), "OPS801", "근무표 ops: OPS 입력 담당자 넣기"),
                    ("opsadm", str(m.pk), "OPS801", "근무표 ops: OPS 입력 담당자 빼기"),
                    ("OPS801", str(m.pk), "OPS801", "근무표 ops: 관리자 빼기")]
    assert "가상" not in caplog.text and not LogEntry.objects.filter(object_repr__contains="가상").exists()
