"""근무표·근무 정의·그룹 모델(1단계)."""
from datetime import time

import pytest
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction

from duty.models import Board, BoardShift, Department, GroupKeeper
from duty.shifts import KEYS
from tests.it_defs import IT_DEFS2


def _bad(fn):
    with pytest.raises(IntegrityError), transaction.atomic():
        fn()


def test_it_defs_match_keys_order():
    assert [d.key for d in IT_DEFS2] == KEYS


def test_it_board_fixture_has_14_defs_and_admin_group(it_board):
    assert it_board.code == "it" and it_board.input_mode == "collect"
    assert sorted(it_board.shifts.values_list("key", flat=True)) == sorted(k for k in KEYS if k != "lunch")
    assert it_board.admin_group_id is not None


def test_board_save_creates_admin_group(db):
    b = Board.objects.create(code="ops", name="운영팀", input_mode=Board.InputMode.DIRECT)
    assert b.admin_group.name == "운영팀 근무표 관리"
    before = Group.objects.count()
    b.name = "운영팀2"
    b.save()  # 이미 있으면 새로 만들지 않는다
    assert Group.objects.count() == before and b.admin_group.name == "운영팀 근무표 관리"


def test_department_save_creates_input_group_for_collect_board(it_board):
    d = Department.objects.create(code="QA", name="품질", shifts="normal", board=it_board)
    assert d.input_group.name == "품질 출근표 입력"


def test_department_without_collect_board_has_no_input_group(db):
    ops = Board.objects.create(code="ops", name="운영팀", input_mode=Board.InputMode.DIRECT)
    assert Department.objects.create(code="OPS", name="운영", shifts="normal", board=ops).input_group is None


def test_depts_fixture_on_it_board_with_input_groups(depts, it_board):
    assert {d.board_id for d in depts.values()} == {it_board.id}
    assert all(d.input_group_id for d in depts.values())


def test_admin_user_in_it_admin_group(admin_user, it_board):
    assert admin_user.groups.filter(pk=it_board.admin_group_id).exists()


def test_board_constraints(it_board):
    _bad(lambda: Board.objects.create(code="it", name="중복"))
    _bad(lambda: Board.objects.create(code="x", name="x", input_mode="bogus"))


def test_boardshift_constraints(it_board):
    _bad(lambda: BoardShift.objects.create(board=it_board, key="dawn", name="중복", start=time(6), end=time(7)))
    ops = Board.objects.create(code="ops", name="운영팀")
    _bad(lambda: BoardShift.objects.create(board=ops, key="lunch", name="점심", start=time(11), end=time(12)))
    _bad(lambda: BoardShift.objects.create(board=ops, key="dawn", name="이른", start=time(9), end=time(8)))
    _bad(lambda: BoardShift.objects.create(board=ops, key="dawn", name="이른"))
    BoardShift.objects.create(board=ops, key="dawn", name="이른", start=time(7, 30), end=time(16, 30))


def test_boardshift_name_unique_per_board(it_board):
    ops = Board.objects.create(code="ops", name="운영팀")
    BoardShift.objects.create(board=ops, key="dawn", name="새벽", start=time(7), end=time(16))  # 다른 근무표와는 겹쳐도 된다
    _bad(lambda: BoardShift.objects.create(board=ops, key="normal", name="새벽", start=time(9), end=time(18)))


def test_groupkeeper_unique(admin_user, it_board):
    GroupKeeper.objects.create(group=it_board.admin_group, user=admin_user)
    _bad(lambda: GroupKeeper.objects.create(group=it_board.admin_group, user=admin_user))


def test_boardshift_key_labels_are_neutral():
    labels = dict(BoardShift._meta.get_field("key").choices)
    assert labels["dawn"] == "근무조 1" and labels["night"] == "근무조 4"
    assert labels["slot0"] == "관제 1" and labels["slot9"] == "관제 10"


def test_depts_fixture_order_matches_old_filter_order(depts):
    assert [d.code for d in sorted(depts.values(), key=lambda d: d.order)] == ["MEMS", "TMCH", "MD", "UI"]
