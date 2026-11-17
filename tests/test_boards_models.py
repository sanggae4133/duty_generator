"""근무표·근무 정의·그룹 모델(1단계)."""
from datetime import time

import pytest
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction

from duty.errors import DutyError
from duty.models import Board, BoardShift, Department, GroupKeeper
from duty.shifts import KEYS
from tests.it_defs import IT_DEFS2, OPS_STEPS


def _bad(fn):
    with pytest.raises(IntegrityError), transaction.atomic():
        fn()


def test_it_defs_match_keys_order():
    assert [d.key for d in IT_DEFS2] == KEYS


def test_it_board_fixture_has_14_defs_and_admin_group(it_board):
    assert it_board.code == "it" and it_board.steps() == ["draft", "collecting", "closed", "generated", "published"]
    assert sorted(it_board.shifts.values_list("key", flat=True)) == sorted(k for k in KEYS if k != "lunch")
    assert it_board.admin_group_id is not None


def test_board_save_creates_admin_group(db):
    b = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
    assert b.admin_group.name == "운영팀 근무표 관리"
    before = Group.objects.count()
    b.name = "운영팀2"
    b.save()  # 이미 있으면 새로 만들지 않고, 이름만 따라 바꾼다
    b.refresh_from_db()
    assert Group.objects.count() == before and b.admin_group.name == "운영팀2 근무표 관리"


def test_department_save_makes_no_input_group(it_board):
    """입력 그룹은 첫 입력 담당자를 넣을 때 만든다(근무표 통합 설계 5.3). 마감을 쓰는 근무표도 같다."""
    assert Department.objects.create(code="QA", name="품질", shifts="normal", board=it_board).input_group is None


def test_ensure_input_group_makes_it_once(it_board):
    d = Department.objects.create(code="QA", name="품질", shifts="normal", board=it_board)
    g = d.ensure_input_group()
    assert g.name == "품질 출근표 입력" and Department.objects.get(pk="QA").input_group_id == g.pk
    assert d.ensure_input_group() == g and Group.objects.filter(name="품질 출근표 입력").count() == 1


def test_ensure_input_group_name_clash(it_board):
    Group.objects.create(name="품질 출근표 입력")
    d = Department.objects.create(code="QA", name="품질", shifts="normal", board=it_board)
    with pytest.raises(DutyError, match="같은 이름의 그룹이 이미 있습니다: 품질 출근표 입력. 슈퍼유저에게 그 그룹 이름을"):
        d.ensure_input_group()
    assert Department.objects.get(pk="QA").input_group_id is None


def test_board_without_close_can_have_many_departments(it_board):
    """'직접 입력 근무표는 부서 하나' 규칙은 없다(근무표 통합 설계 5.3)."""
    ops = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
    for code in ("OPS", "OP2"):
        Department(code=code, name=f"운영{code}", shifts="normal", board=ops).full_clean()
        Department.objects.create(code=code, name=f"운영{code}", shifts="normal", board=ops)


def test_depts_fixture_on_it_board_with_input_groups(depts, it_board):
    assert {d.board_id for d in depts.values()} == {it_board.id}
    assert all(d.input_group_id for d in depts.values())


def test_admin_user_in_it_admin_group(admin_user, it_board):
    assert admin_user.groups.filter(pk=it_board.admin_group_id).exists()


def test_board_constraints(it_board):
    _bad(lambda: Board.objects.create(code="it", name="중복"))
    _bad(lambda: Board.objects.create(code="x", name="x", step_closed=""))


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


def test_board_save_without_rename_keeps_admin_group_name(it_board):
    """마이그레이션 0011 이 만든 IT 근무표(이름 'IT 당번표', 그룹 'IT 근무표 관리'): 이름을 안 바꾼 저장은 그룹을 건드리지 않는다."""
    Group.objects.filter(pk=it_board.admin_group_id).update(name="IT 근무표 관리")
    board = Board.objects.get(pk=it_board.pk)
    board.save()
    board.refresh_from_db()
    assert board.name == "IT 당번표" and board.admin_group.name == "IT 근무표 관리"


def test_department_save_without_rename_keeps_input_group_name(it_board):
    d = Department.objects.create(code="QA", name="품질", shifts="normal", board=it_board)
    d.ensure_input_group()
    Group.objects.filter(pk=d.input_group_id).update(name="옛 품질 그룹")
    d = Department.objects.get(pk="QA")
    d.order = 5
    d.save()
    d.refresh_from_db()
    assert d.input_group.name == "옛 품질 그룹"
    d.name = "품질관리"
    d.save()
    d.refresh_from_db()
    assert d.input_group.name == "품질관리 출근표 입력"


@pytest.mark.parametrize("names,bad", [
    ({}, []),
    (OPS_STEPS, []),
    ({"step_generated": "배포…됨"}, ["배포…"]),                               # 생성 글자가 [배포…]와 같다
    ({"step_generated": "재생성됨"}, []),                                     # 관제 없는 화면엔 [재생성]이 없다
    ({"step_collecting": "장중관제 중", "step_closed": "생성"}, ["장중관제 생성"]),  # 관제 있을 때만 겹친다
    ({"step_collecting": "장중관제 중", "step_closed": "생성", "use_close": False}, []),  # 마감을 끄면 그 버튼이 없다
])
def test_bad_buttons(names, bad):
    """켠 단계의 버튼 글자 중 비거나 겹치는 것(관제 있을 때·없을 때 둘 다, 설계 5.4)."""
    assert Board(code="x", name="x", **names).bad_buttons() == bad
