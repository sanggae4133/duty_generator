from duty.models import BoardShift
from duty.services import boards
from duty.shifts import KEYS, by_key
from tests.it_defs import IT_DEFS


def test_it_board_defs_match_it_definitions(it_board):
    assert boards.it_board() == it_board
    got = boards.defs(it_board)
    assert [d.key for d in got] == [k for k in KEYS if k != "lunch"]
    assert by_key(got) == by_key(IT_DEFS)


def test_defs_include_inactive_and_use_tuples(it_board):
    BoardShift.objects.filter(board=it_board, key="night").update(active=False)
    got = by_key(boards.defs(it_board))
    assert got["night"].name == "야간" and not got["night"].active  # 꺼도 지난 행·기록의 이름은 찾는다
    assert "night" not in [x.key for x in boards.active_defs(it_board)]  # 새 입력 선택지에서는 빠진다
    assert got["slot0"].eligible_shifts == ("normal",)
    assert got["slot0"].eligible_types == ("개발자",)


def test_board_of(make_member, admin_user, it_board):
    assert boards.board_of(make_member("가")) == it_board
    assert boards.board_of(admin_user) is None  # 부서 없는 계정
