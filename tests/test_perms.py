from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied

from duty import perms
from duty.models import Board, Department, User


def test_past_date_is_admin_only(fixed_today, make_member, admin_user, it_board):
    fixed_today(date(2026, 11, 10))
    m = make_member("가", user=True)
    perms.assert_can_edit(m, it_board, date(2026, 11, 10))  # 오늘은 누구나
    with pytest.raises(PermissionDenied):
        perms.assert_can_edit(m, it_board, date(2026, 11, 9))
    perms.assert_can_edit(admin_user, it_board, date(2026, 11, 9))


def test_can_input_department(depts, make_member, admin_user):
    m = make_member("가", user=True)
    depts["MEMS"].input_group.user_set.add(m)
    assert perms.can_input_department(m, depts["MEMS"])
    assert not perms.can_input_department(m, depts["MD"])
    assert perms.can_input_department(admin_user, depts["MD"])


def test_managed_departments(depts, make_member, admin_user):
    m = make_member("가", user=True)
    depts["MD"].input_group.user_set.add(m)
    assert list(perms.managed_departments(m)) == [depts["MD"]]
    assert perms.managed_departments(admin_user).count() == 4
    assert perms.managed_departments(AnonymousUser()).count() == 0


@pytest.fixture
def ops(it_board):
    """두 번째 근무표(가짜 '운영팀', 직접 입력)와 그 부서 하나. 관리 그룹은 Board.save 가 만든다."""
    board = Board.objects.create(code="ops", name="운영팀", input_mode="direct")
    return board, Department.objects.create(code="OPS", name="운영", shifts="normal", board=board)


def test_admin_is_group_member_not_staff_or_superuser(it_board, ops, make_member):
    staff = User.objects.create_user("st", name="스태프", is_staff=True)
    root = User.objects.create_superuser("root", password="unused-Pw-123", name="루트")
    m = make_member("가")
    for u in (staff, root, m, AnonymousUser()):
        assert not perms.is_admin(u) and not perms.admin_boards(u).exists()
    it_board.admin_group.user_set.add(m)
    assert list(perms.admin_boards(m)) == [it_board]
    assert perms.is_admin(m) and perms.is_board_admin(m, it_board) and not perms.is_board_admin(m, ops[0])


def test_managed_departments_is_input_groups_plus_admin_boards(it_board, ops, depts, make_member):
    m = make_member("가")
    depts["MD"].input_group.user_set.add(m)          # 입력 그룹
    ops[0].admin_group.user_set.add(m)   # 운영팀 관리자 → 운영팀의 모든 부서
    assert list(perms.managed_departments(m)) == [depts["MD"], ops[1]]
    assert perms.can_input_department(m, ops[1]) and not perms.can_input_department(m, depts["UI"])
    it_board.admin_group.user_set.add(m)
    assert perms.managed_departments(m).count() == 5  # 입력 그룹과 관리 근무표가 겹쳐도 한 번씩


def test_can_edit_own_board_only(fixed_today, it_board, ops, make_member):
    fixed_today(date(2026, 11, 10))
    today, past = date(2026, 11, 10), date(2026, 11, 9)
    m = make_member("가")  # IT 부서
    o = User.objects.create_user("OPS001", name="운영가", department=ops[1], type="직원")
    nodept = User.objects.create_user("x", name="무소속")
    root = User.objects.create_superuser("root", password="unused-Pw-123", name="루트")
    assert perms.can_edit(m, it_board, today) and not perms.can_edit(m, it_board, past)
    assert not perms.can_edit(m, ops[0], today)  # 남의 근무표는 보기만
    assert perms.can_edit(o, ops[0], today) and not perms.can_edit(o, it_board, today)
    for u in (nodept, root, AnonymousUser()):
        assert not perms.can_edit(u, it_board, today)
    with pytest.raises(PermissionDenied, match="이 근무표를 바꿀 권한이 없습니다"):
        perms.assert_can_edit(m, ops[0], today)
    with pytest.raises(PermissionDenied, match="지난 날짜는 어드민만"):
        perms.assert_can_edit(m, it_board, past)


def test_board_admin_edits_past_of_that_board_only(fixed_today, it_board, ops):
    fixed_today(date(2026, 11, 10))
    a = User.objects.create_user("adm2", name="운영관리")
    ops[0].admin_group.user_set.add(a)
    assert perms.can_edit(a, ops[0], date(2026, 11, 9))  # 부서가 없어도 관리 그룹이면
    assert not perms.can_edit(a, it_board, date(2026, 11, 10))
