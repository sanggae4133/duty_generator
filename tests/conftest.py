from itertools import count

import pytest

from duty.models import Department, User

DEPTS = [
    ("MEMS", "매칭엔진실", "dawn,normal,dinner,night"),
    ("TMCH", "매매지원실", "dawn,normal,dinner,night"),
    ("MD", "정보분배", "dawn,normal,dinner,night"),
    ("UI", "UI", "normal,dinner,night"),
]


@pytest.fixture
def depts(db):
    return {c: Department.objects.create(code=c, name=n, shifts=s) for c, n, s in DEPTS}


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
def admin_user(db):
    return User.objects.create_user("admin", password="unused-Pw-123", name="관리자", is_staff=True)


@pytest.fixture
def fixed_today(monkeypatch):
    def set_today(d):
        monkeypatch.setattr("duty.perms.today", lambda: d)

    return set_today


@pytest.fixture
def admin_client_ok(client, admin_user):
    client.force_login(admin_user)
    return client
