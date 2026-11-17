"""[근무표 설정] 사람 칸(근무표 통합 설계 7.2 의 1번·8절): 읽기 표·고치기·사람 추가·퇴사·다시 재직·계정 발급과 결과 상자.
이름은 모두 가상. 임시 비밀번호는 응답에서 읽어 쓰고 테스트에 적지 않는다."""
import logging
import re
from datetime import date

import pytest
from django.contrib.admin.models import LogEntry

from duty.accounts import issue_account
from duty.models import Commute, Department, Period, User

URL = "/settings/"
OPS = URL + "?board=ops"


@pytest.fixture
def ops_admin(ops_board):
    u = User.objects.create_user("opsadm", password=None, name="가상운영")
    ops_board.admin_group.user_set.add(u)
    return u


@pytest.fixture
def ops_client(client, ops_admin):
    client.force_login(ops_admin)
    return client


def _ops_member(name, username, active=True):
    return User.objects.create_user(username, password=None, name=name, department=Department.objects.get(code="OPS"),
                                    type="직원", is_active=active)


def _in_use(name, username):
    """계정 '사용 중'(발급 뒤 첫 로그인 비밀번호 변경까지 마친 사람)."""
    u = _ops_member(name, username)
    issue_account(u)
    User.objects.filter(pk=u.pk).update(must_change_password=False)
    return u


def _row(body, user) -> str:
    """표에서 그 사람 줄(<tr id="p-…"> … </tr>)."""
    i = body.index(f'<tr id="p-{user.pk}">')
    return body[i:body.index("</tr>", i)]


# ── 읽기 표 ──

def test_people_section_first_with_states(ops_client, ops_board, it_board):
    a = _ops_member("가상하나", "ops01")
    b = _ops_member("가상두리", "ops02")
    issue_account(b)
    c = _in_use("가상세찬", "ops03")
    e = _ops_member("가상겸직", "ops09")
    it_board.admin_group.user_set.add(e)  # 다른 근무표 관리자 = 관리자 계정
    body = ops_client.get(OPS).content.decode()
    assert body.index('<a href="#people">사람</a>') < body.index('<a href="#admins">관리자</a>')
    assert body.index('<section id="people"') < body.index('<section id="admins"')
    assert "발급 전" in _row(body, a) and "첫 로그인 대기" in _row(body, b) and "사용 중" in _row(body, c)
    assert "<details>" in _row(body, a) and '<input name="name" value="가상하나"' in _row(body, a)
    assert "관리자 계정은 슈퍼유저에게" in _row(body, e) and "<details" not in _row(body, e)
    assert "<th>구분</th>" not in body  # 장중관제가 없는 근무표
    assert '<input name="username" value="ops04"' in body  # 다음 빈 번호
    assert '<input type="hidden" name="dept" value="OPS">' in body  # 부서가 하나면 숨김
    assert "아이디에는 실명을 쓰지 않습니다" in body and "인사이동은 슈퍼유저에게 부탁하세요" in body


def test_it_board_people_have_type_and_dept_choice(admin_client_ok, depts):
    body = admin_client_ok.get(URL).content.decode()
    assert "<th>구분</th>" in body and '<select name="dept" required>' in body
    r = admin_client_ok.post(URL, {"do": "add_person", "name": "가상하나", "username": "it01", "dept": "MEMS"})
    assert r.status_code == 200 and "구분(직원·개발자)을 고르세요." in r.content.decode()
    r = admin_client_ok.post(URL, {"do": "add_person", "name": "가상하나", "username": "it01", "dept": "MEMS", "type": "개발자"})
    assert r.status_code == 302 and User.objects.get(username="it01").type == "개발자"


# ── 사람 추가·고치기 ──

def test_add_person(ops_client, ops_board):
    r = ops_client.post(OPS, {"do": "add_person", "name": "가상하나", "username": "Ops01", "dept": "OPS"})
    body = r.content.decode()
    assert r.status_code == 200 and "아이디는 영문 소문자로 시작하고" in body  # redirect 없이 다시 그린다
    assert '<input name="name" value="가상하나"' in body and '<input name="username" value="Ops01"' in body  # 보낸 값 그대로
    assert not User.objects.filter(name="가상하나").exists()
    r = ops_client.post(OPS, {"do": "add_person", "name": "가상하나", "username": "ops01", "dept": "OPS"})
    assert r.status_code == 302 and r.url == OPS + "#people"
    u = User.objects.get(username="ops01")
    assert (u.name, u.type, u.has_usable_password()) == ("가상하나", "직원", False)
    body = ops_client.get(r.url).content.decode()
    assert "가상하나를 추가했습니다(아이디 ops01). 표에서 [계정 발급]을 눌러 임시 비밀번호를 주세요." in body
    assert "발급 전" in _row(body, u) and '<input name="username" value="ops02"' in body


def test_edit_person_row(ops_client, ops_board):
    a = _ops_member("가상하나", "ops01")
    _ops_member("가상두리", "ops02")
    r = ops_client.post(OPS, {"do": "set_person", "user": a.pk, "name": "가상두리"})
    row = _row(r.content.decode(), a)
    assert r.status_code == 200 and "<details open>" in row and "이름: 같은 이름이 이미 있습니다" in row  # 오류는 그 줄 안에
    assert '<input name="name" value="가상두리"' in row  # 보낸 값 그대로
    r = ops_client.post(OPS, {"do": "set_person", "user": a.pk, "name": "가상새이름"})
    assert r.status_code == 302 and User.objects.get(pk=a.pk).name == "가상새이름"
    assert "가상새이름을 저장했습니다." in ops_client.get(r.url).content.decode()


def test_my_own_row_points_to_password_menu(ops_client, ops_admin, it_board):
    User.objects.filter(pk=ops_admin.pk).update(department=Department.objects.get(code="OPS"), type="직원")
    other = _ops_member("가상겸직", "ops09")
    it_board.admin_group.user_set.add(other)
    body = ops_client.get(OPS).content.decode()
    mine = _row(body, ops_admin)
    assert "내 비밀번호는 메뉴 [비밀번호]에서" in mine and "<details" not in mine and "관리자 계정은" not in mine
    assert "관리자 계정은 슈퍼유저에게" in _row(body, other)
