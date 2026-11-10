from itertools import count

import pytest
from django.contrib.auth.models import User

from duty.models import Department, Member

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
        m = Member.objects.create(
            code=f"{dept}{next(seq):03d}", name=name, department=depts[dept],
            part="", type=type, is_active=active,
        )
        if user:
            m.user = User.objects.create_user(username=m.code, password="unused-Pw-123")
            m.save()
        return m

    return make


@pytest.fixture
def admin_user(db):
    return User.objects.create_user("admin", password="unused-Pw-123", is_staff=True)


@pytest.fixture
def fixed_today(monkeypatch):
    def set_today(d):
        monkeypatch.setattr("duty.perms.today", lambda: d)

    return set_today


@pytest.fixture
def admin_client_ok(client, admin_user):
    client.force_login(admin_user)
    return client
