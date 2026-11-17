from datetime import time
from itertools import count

import pytest

from duty.models import Board, BoardShift, Department, User
from duty.shifts import LUNCH
from tests.it_defs import IT_DEFS

DEPTS = [
    ("MEMS", "매칭엔진실", "dawn,normal,dinner,night"),
    ("TMCH", "매매지원실", "dawn,normal,dinner,night"),
    ("MD", "정보분배", "dawn,normal,dinner,night"),
    ("UI", "UI", "normal,dinner,night"),
]


@pytest.fixture
def it_board(db):
    # 마이그레이션이 만든 IT 근무표가 있으면 그것을, flush 된 DB(transaction=True 테스트 뒤)면 새로 만든다
    board, _ = Board.objects.get_or_create(code="it", defaults={"name": "IT 당번표", "input_mode": Board.InputMode.COLLECT})
    for d in IT_DEFS:
        BoardShift.objects.get_or_create(board=board, key=d.key, defaults=dict(
            name=d.name, start=d.start, end=d.end, eligible_shifts=list(d.eligible_shifts),
            eligible_types=list(d.eligible_types), default_alarm=d.default_alarm))
    # 마이그레이션 0022 가 넣은 점심당번 정의는 뺀다: 기본 테스트는 1단계 IT 정의로 돌고, 점심당번 테스트는 lunch 픽스처로 켠다
    BoardShift.objects.filter(board=board, key=LUNCH).delete()
    return board


@pytest.fixture
def ops_board(it_board):
    """가짜 '운영팀' 근무표(시장운영실과 같은 모양): 작성 중·마감 없음, 근무조 셋 + 점심당번, 부서 하나, 장중관제 없음."""
    board = Board.objects.create(code="ops", name="운영팀", input_mode=Board.InputMode.DIRECT)
    for key, name, h in (("dawn", "이른", 7), ("normal", "가운데", 9), ("dinner", "늦은", 11)):
        BoardShift.objects.create(board=board, key=key, name=name, start=time(h, 30), end=time(h + 9, 30), default_alarm=True)
    BoardShift.objects.create(board=board, key=LUNCH, name="점심당번")
    Department.objects.create(code="OPS", name="운영", shifts="dawn,normal,dinner", board=board)
    return board


@pytest.fixture
def lunch(it_board):
    """IT 근무표에 점심당번 정의(시각 없음, 운영 마이그레이션 0022 와 같은 값)."""
    return BoardShift.objects.create(board=it_board, key=LUNCH, name="점심당번")


@pytest.fixture
def depts(it_board):
    # order = 지금 근무표 부서 필터 순서(views/roster.py DEPT_ORDER: MEMS·TMCH·MD·UI = DEPTS 순서)
    return {c: Department.objects.create(code=c, name=n, shifts=s, board=it_board, order=i)
            for i, (c, n, s) in enumerate(DEPTS)}


@pytest.fixture
def make_member(depts):
    seq = count(1)

    def make(name, dept="MEMS", type="개발자", user=False, active=True):
        # user=True: 로그인 가능한 계정(발급됨), False: 발급 전(사용할 수 없는 비밀번호)
        return User.objects.create_user(
            f"{dept}{next(seq):03d}", password="unused-Pw-123" if user else None, name=name,
            department=depts[dept], part="", type=type, is_active=active,
        )

    return make


@pytest.fixture
def admin_user(it_board):
    user = User.objects.create_user("admin", password="unused-Pw-123", name="관리자", is_staff=True)
    user.groups.add(it_board.admin_group)
    return user


@pytest.fixture
def fixed_today(monkeypatch):
    def set_today(d):
        monkeypatch.setattr("duty.perms.today", lambda: d)

    return set_today


@pytest.fixture
def admin_client_ok(client, admin_user):
    client.force_login(admin_user)
    return client
