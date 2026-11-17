"""[근무표 설정] 화면(근무표 통합 설계 7·8절): 들어가기·칸 바로가기·칸 안 메시지·관리자·입력 담당자. 이름은 모두 가상."""
import pytest
from django.contrib.auth.models import Group

from duty.models import Department, User

URL = "/settings/"


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


def _admins(board):
    return set(board.admin_group.user_set.values_list("username", flat=True))


# ── 들어가기 ──

def test_menu_and_access(client, ops_board, ops_admin, make_member, admin_user):
    member = make_member("가상가", user=True)
    client.force_login(member)
    assert 'href="/settings/"' not in client.get("/").content.decode()
    assert client.get(URL).status_code == 403  # 관리자가 아니면(다른 관리자 화면과 같다)
    su = User.objects.create_superuser("root", password=None, name="가상슈퍼")
    client.force_login(su)
    assert client.get(URL).status_code == 403  # 슈퍼유저라도 관리 그룹에 없으면
    client.force_login(ops_admin)
    assert '<a href="/settings/" aria-current="page">근무표 설정</a>' in client.get(URL).content.decode()
    assert client.get(URL + "?board=it").status_code == 404  # 관리하지 않는 근무표
    assert client.get(URL + "?board=nope").status_code == 404
    client.logout()
    assert client.get(URL).status_code == 302  # 로그인 화면으로


def test_title_board_links_and_jump_bar(client, ops_board, admin_user):
    client.force_login(admin_user)
    body = client.get(URL).content.decode()
    assert "<h3>근무표 설정 · IT 당번표</h3>" in body and 'class="seg"' not in body  # 관리하는 근무표가 하나면 링크 없음
    for anchor in ("#admins", "#assignees"):
        assert f'href="{anchor}"' in body
    ops_board.admin_group.user_set.add(admin_user)
    body = client.get(URL + "?board=ops").content.decode()
    assert "<h3>근무표 설정 · 운영팀</h3>" in body
    assert '<a href="/settings/?board=it">IT 당번표</a>' in body and '<a href="/settings/?board=ops" aria-current="page">운영팀</a>' in body
    assert "<h3>근무표 설정 · IT 당번표</h3>" in client.get(URL).content.decode()  # ?board 없으면 내 근무표


def test_unknown_action_and_bad_ids_are_404(ops_client):
    assert ops_client.post(URL + "?board=ops", {"do": "nope"}).status_code == 404
    assert ops_client.post(URL + "?board=ops", {"do": "add_admin", "user": "x"}).status_code == 404
    assert ops_client.post(URL + "?board=ops", {"do": "add_assignee", "dept": "ZZ", "user": "1"}).status_code == 404


# ── 관리자 ──

def test_add_admin_message_inside_section(ops_client, ops_board):
    m = _ops_member("가상하나", "OPS801")
    r = ops_client.post(URL + "?board=ops", {"do": "add_admin", "user": m.pk})
    assert r.status_code == 302 and r["Location"] == "/settings/?board=ops#admins"
    body = ops_client.get(URL + "?board=ops").content.decode()
    msg = '<div class="msg success" role="status">가상하나를 관리자로 넣었습니다.</div>'
    assert body.index('<section id="admins"') < body.index(msg) < body.index('<section id="assignees"')  # 맨 위가 아니라 그 칸 안
    assert _admins(ops_board) == {"opsadm", "OPS801"}


def test_admin_rows(ops_client, ops_board, ops_admin):
    body = ops_client.get(URL + "?board=ops").content.decode()
    assert "마지막 관리자" in body and 'value="remove_admin"' not in body  # 재직 관리자가 나 하나
    other, gone = _ops_member("가상하나", "OPS801"), _ops_member("가상퇴사", "OPS802", active=False)
    ops_board.admin_group.user_set.add(other, gone)
    body = ops_client.get(URL + "?board=ops").content.decode()
    assert "가상퇴사 (퇴사)" in body and "빼기는 슈퍼유저에게" in body and "마지막 관리자" not in body
    assert body.count('value="remove_admin"') == 2  # 나와 퇴사자만
    admins = body[body.index('<section id="admins"'):body.index('<section id="assignees"')]
    assert f'<option value="{other.pk}">' not in admins  # 이미 관리자는 넣기 후보가 아니다


def test_cannot_remove_other_active_admin_or_add_outsider(ops_client, ops_board, make_member):
    other = _ops_member("가상하나", "OPS801")
    ops_board.admin_group.user_set.add(other)
    assert ops_client.post(URL + "?board=ops", {"do": "remove_admin", "user": other.pk}).status_code == 404
    it_person = make_member("가상아이티")
    assert ops_client.post(URL + "?board=ops", {"do": "add_admin", "user": it_person.pk}).status_code == 404
    assert _admins(ops_board) == {"opsadm", "OPS801"}


def test_remove_self(ops_client, ops_board, ops_admin):
    r = ops_client.post(URL + "?board=ops", {"do": "remove_admin", "user": ops_admin.pk}, follow=True)
    assert "재직 중인 관리자가 아무도 남지 않습니다" in r.content.decode()  # 마지막 재직 관리자
    ops_board.admin_group.user_set.add(_ops_member("가상하나", "OPS801"))
    r = ops_client.post(URL + "?board=ops", {"do": "remove_admin", "user": ops_admin.pk})
    assert r.status_code == 302 and r["Location"] == "/"  # 더 관리하는 근무표가 없으면 근무표 화면으로
    assert _admins(ops_board) == {"OPS801"}


# ── 입력 담당자 ──

def test_assignees(ops_client, ops_board):
    body = ops_client.get(URL + "?board=ops").content.decode()
    assert "담당자 없음 — 근무표 관리자만 입력합니다" in body
    a = _ops_member("가상하나", "OPS801")
    r = ops_client.post(URL + "?board=ops", {"do": "add_assignee", "dept": "OPS", "user": a.pk})
    assert r["Location"] == "/settings/?board=ops#assignees"
    dept = Department.objects.get(code="OPS")
    assert list(dept.input_group.user_set.all()) == [a]
    body = ops_client.get(URL + "?board=ops").content.decode()
    assert body.index('<section id="assignees"') < body.index("가상하나를 운영 입력 담당자로 넣었습니다.")
    assert "담당자 없음" not in body
    ops_client.post(URL + "?board=ops", {"do": "remove_assignee", "dept": "OPS", "user": a.pk})
    assert not dept.input_group.user_set.exists()


def test_assignee_other_board_dept_is_404(ops_client, depts, make_member):
    it_person = make_member("가상아이티")
    a = _ops_member("가상하나", "OPS801")
    assert ops_client.post(URL + "?board=ops", {"do": "add_assignee", "dept": "MEMS", "user": a.pk}).status_code == 404
    assert ops_client.post(URL + "?board=ops", {"do": "add_assignee", "dept": "OPS", "user": it_person.pk}).status_code == 404
    assert not depts["MEMS"].input_group.user_set.exists()


def test_assignee_group_name_clash_shown_in_section(ops_client):
    Group.objects.create(name="운영 출근표 입력")
    a = _ops_member("가상하나", "OPS801")
    r = ops_client.post(URL + "?board=ops", {"do": "add_assignee", "dept": "OPS", "user": a.pk}, follow=True)
    body = r.content.decode()
    assert body.index('<section id="assignees"') < body.index("같은 이름의 그룹이 이미 있습니다: 운영 출근표 입력. 슈퍼유저에게")
