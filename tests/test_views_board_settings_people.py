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


# ── 퇴사·다시 재직 ──

def test_leave_confirm_then_list_then_rejoin(ops_client, ops_board, fixed_today):
    fixed_today(date(2026, 12, 2))
    m = _ops_member("가상하나", "ops01")
    done = Period.objects.create(board=ops_board, name="12월 회차", start_date=date(2026, 11, 30), end_date=date(2026, 12, 4),
                                 status="published")
    Commute.objects.create(period=done, date=date(2026, 12, 3), member=m, shift="normal")
    nxt = Period.objects.create(board=ops_board, name="1월 회차", start_date=date(2027, 1, 4), end_date=date(2027, 1, 15),
                                status="collecting")
    Commute.objects.create(period=nxt, date=date(2027, 1, 5), member=m, shift="dawn")
    body = ops_client.get(OPS).content.decode()
    assert "을(를) 퇴사 처리할까요? 로그인할 수 없고 캘린더·텔레그램·푸시 연결이 모두 끊깁니다." in _row(body, m)
    r = ops_client.post(OPS, {"do": "leave", "user": m.pk})  # 남은 근무가 있다: 저장하지 않고 그 줄 아래에서 묻는다
    row = _row(r.content.decode(), m)
    assert r.status_code == 200 and "<details open>" in row and User.objects.get(pk=m.pk).is_active
    assert "12/3 가운데 — 12월 회차(배포됨)" in row and "1/5 이른 — 1월 회차(입력 중)" in row
    assert "이 근무 2칸은 그대로 남습니다. 근무표·입력 표에서 다른 사람으로 바꾸세요." in row
    assert '<button class="danger-btn" name="confirm" value="2">그래도 퇴사 처리</button>' in row
    r = ops_client.post(OPS, {"do": "leave", "user": m.pk, "confirm": "2"})
    assert r.status_code == 302 and r.url == OPS + "#people" and not User.objects.get(pk=m.pk).is_active
    body = ops_client.get(r.url).content.decode()
    assert "가상하나를 퇴사 처리했습니다. [다시 재직]으로 되돌릴 수 있습니다." in body
    assert '<a href="/day/2026-12-03/">12/3 가운데 — 12월 회차(배포됨)</a>' in body  # 운영팀이 이 관리자의 내 근무표
    assert f'<a href="/collect/{nxt.pk}/OPS/">1/5 이른 — 1월 회차(입력 중)</a>' in body
    assert f'<tr id="p-{m.pk}">' not in body  # 표에서 빠지고
    departed = body[body.index('<details id="departed"'):]
    assert "퇴사한 사람 1명" in departed and "가상하나" in departed and ">다시 재직</button>" in departed
    r = ops_client.post(OPS, {"do": "rejoin", "user": m.pk})
    assert r.status_code == 302 and User.objects.get(pk=m.pk).is_active
    body = ops_client.get(r.url).content.decode()
    assert "가상하나를 다시 재직으로 돌렸습니다. 로그인하려면 [계정 발급]을 다시 누르세요." in body
    assert "발급 전" in _row(body, m)


def test_leave_links_generated_duty_to_period_page(ops_client, ops_board, fixed_today):
    """생성된 회차의 당번 칸(DutyAssignment)은 입력 표에 없으니 회차 화면으로, 출근표 칸은 입력 표로."""
    from duty.models import DutyAssignment
    fixed_today(date(2026, 12, 2))
    m = _ops_member("가상하나", "ops01")
    gen = Period.objects.create(board=ops_board, name="1월 회차", start_date=date(2027, 1, 4), end_date=date(2027, 1, 15),
                                status="generated")
    Commute.objects.create(period=gen, date=date(2027, 1, 5), member=m, shift="dawn")
    DutyAssignment.objects.create(period=gen, date=date(2027, 1, 5), cell="lunch", member=m)
    r = ops_client.post(OPS, {"do": "leave", "user": m.pk, "confirm": "2"})
    assert r.status_code == 302
    body = ops_client.get(r.url).content.decode()
    assert f'<a href="/collect/{gen.pk}/OPS/">1/5 이른 — 1월 회차(' in body
    assert f'<a href="/periods/{gen.pk}/">1/5 점심당번 — 1월 회차(' in body
