"""근무표(Board)와 근무 정의 읽기. 1단계는 IT 근무표 하나."""
from ..models import Board, BoardShift
from ..shifts import Def, ordered


def it_board() -> Board:
    return Board.objects.get(code="it")


def defs(board: Board) -> list[Def]:
    """그 근무표의 근무 정의 전부(꺼진 것 포함: 표시·라벨·지난 행·기록의 이름을 찾는다). KEYS 순."""
    return ordered([
        Def(s.key, s.name, s.start, s.end, tuple(s.eligible_shifts), tuple(s.eligible_types), s.default_alarm, s.active)
        for s in BoardShift.objects.filter(board=board)
    ])


def active_defs(board: Board) -> list[Def]:
    """켜진 정의만(설계 4.3 '끄면 새 입력에서만 빠진다'): 입력 표·CSV 열, 부서 출근조·스케줄·알림 규칙 선택지, 생성."""
    return [x for x in defs(board) if x.active]


def board_of(user) -> Board | None:
    dept = getattr(user, "department", None)  # 익명·부서 없는 계정은 근무표가 없다
    return dept.board if dept else None
