"""[근무표 설정] 화면(근무표 통합 설계 7·8절): 들어가기·칸 바로가기·칸 안 메시지·관리자·입력 담당자. 이름은 모두 가상."""
from datetime import date

import pytest
from django.contrib.auth.models import Group

from duty.models import BoardShift, Commute, Department, Period, User
from tests.test_board_settings_shifts import shift_data

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


# ── 근무 정의와 부서 ──

def _post_shifts(client, board, **kw):
    confirm = kw.pop("confirm", None)
    data = dict(shift_data(board, **kw).lists()) | {"do": "shifts"} | ({"confirm": confirm} if confirm else {})
    return client.post(f"{URL}?board={board.code}", data)


def test_shifts_section_shows_cards_and_departments(ops_client, ops_board):
    body = ops_client.get(URL + "?board=ops").content.decode()
    for name in ("이른", "가운데", "늦은", "점심당번"):
        assert f"<legend>{name}</legend>" in body
    assert "<legend>새 근무 정의(더할 때만 채웁니다)</legend>" in body and "<legend>운영</legend>" in body
    assert "이른 07:30~16:30" in body  # 부서 출근조 체크박스: 이름과 시각
    assert '<input type="hidden" name="d-OPS-shown" value="dawn,normal,dinner">' in body  # 그린 때 보인 체크박스(저장 때 남길 키)
    assert "아직 부서에 배정되지 않은 근무조" not in body and ">부서 저장</button>" not in body


def test_new_shift_then_check_it_in_department(ops_client, ops_board):
    r = _post_shifts(ops_client, ops_board, extra={"key": "night", "name": "밤", "start": "13:00", "end": "22:00", "active": "on"})
    assert r.status_code == 302 and r["Location"] == "/settings/?board=ops#shifts"
    body = ops_client.get(URL + "?board=ops").content.decode()
    assert body.index('<section id="shifts"') < body.index(
        "근무 정의와 부서를 저장했습니다. 아래 부서에서 새 근무조를 체크하고 [부서 저장]을 한 번 더 누르세요.")
    assert "아직 부서에 배정되지 않은 근무조: 밤. 아래 부서에서 체크하고 [부서 저장]을 누르세요." in body
    assert '<button class="wide">부서 저장</button>' in body
    _post_shifts(ops_client, ops_board, depts={"OPS": {"shifts": ["dawn", "normal", "dinner", "night"]}})
    body = ops_client.get(URL + "?board=ops").content.decode()
    assert "아직 부서에 배정되지 않은 근무조" not in body and Department.objects.get(code="OPS").shifts == "dawn,normal,dinner,night"
    assert "[부서 저장]을 한 번 더 누르세요" not in body  # 다 배정했으면 결과 글도 짧게


def test_shift_errors_redraw_with_sent_values(ops_client, ops_board):
    r = _post_shifts(ops_client, ops_board, change={"normal": {"name": "중간"}}, depts={"OPS": {"lunch_start": "11:30"}})
    body = r.content.decode()
    assert r.status_code == 200 and 'value="중간"' in body  # 보낸 값 그대로
    assert body.index('<section id="shifts"') < body.index("저장하지 않았습니다. 빨간 글씨로 표시한 칸을 고쳐 주세요.")
    assert "점심 시각은 둘 다 비우거나, 둘 다 넣고 시작을 끝보다 이르게 하세요." in body


def test_shift_removal_confirm_flow(ops_client, ops_board):
    m = _ops_member("가상하나", "OPS801")
    p = Period.objects.create(board=ops_board, name="이번 회차", start_date=date(2026, 11, 16), end_date=date(2026, 11, 16),
                              status=Period.Status.COLLECTING)
    Commute.objects.create(period=p, date=p.start_date, member=m, shift="dinner")
    r = _post_shifts(ops_client, ops_board, depts={"OPS": {"shifts": ["dawn", "normal"]}})
    body = r.content.decode()
    assert r.status_code == 200 and "그 근무조 출근표 1행이 다음 표 저장 때 지워집니다" in body
    assert 'name="confirm" value="1">그래도 저장</button>' in body and 'type="hidden" name="confirm"' not in body
    r = _post_shifts(ops_client, ops_board, depts={"OPS": {"shifts": ["dawn", "normal"]}})  # 위 [저장](확인 값 없음)은 다시 묻는다
    assert r.status_code == 200 and "그 근무조 출근표 1행이 다음 표 저장 때 지워집니다" in r.content.decode()
    assert Department.objects.get(code="OPS").shifts == "dawn,normal,dinner"
    r = _post_shifts(ops_client, ops_board, depts={"OPS": {"shifts": ["dawn", "normal"]}}, confirm="1")
    assert r.status_code == 302 and Department.objects.get(code="OPS").shifts == "dawn,normal"


def test_shift_ids_of_other_board_are_404(ops_client, ops_board, it_board, depts):
    it_shift = BoardShift.objects.filter(board=it_board).first()
    data = dict(shift_data(ops_board).lists()) | {"do": "shifts"}
    assert ops_client.post(URL + "?board=ops", data | {"shifts-0-id": [str(it_shift.pk)]}).status_code == 404
    assert ops_client.post(URL + "?board=ops", data | {"d-MEMS-shifts": ["dawn"]}).status_code == 404
    assert BoardShift.objects.get(pk=it_shift.pk).board_id == it_board.pk


# ── 회차 단계 ──

def _steps_post(board, **over):
    data = {f: getattr(board, f) for f in ("step_draft", "step_collecting", "step_closed", "step_generated", "step_published")}
    data |= {f: "on" for f in ("use_draft", "use_close") if getattr(board, f)}
    return {k: v for k, v in (data | over | {"do": "steps"}).items() if v is not None}


def test_steps_section_preview_and_folded(ops_client, ops_board, admin_user, client):
    body = ops_client.get(URL + "?board=ops").content.decode()
    assert '<section id="steps" class="cfg">\n  <details>' in body  # 접혀 있다
    assert "저장된 단계: <strong>입력 중 → 확정 → 배포됨</strong>" in body
    assert '<span class="btn-name">[확정]</span> <span class="btn-name">[확정 취소]</span> <span class="btn-name">[배포…]</span>' in body
    assert "작성 중 이름 <small>(쓰지 않음 · 남은 회차·기록 표시용)</small>" in body
    assert "return confirm('진행 중인 회차의 단계 이름과 버튼이 바로 바뀝니다. 계속할까요?')" in body
    client.force_login(admin_user)
    body = client.get(URL).content.decode()
    assert "[취합 열기]</span> <span class=\"btn-name\">[취합 마감]</span> <span class=\"btn-name\">[장중관제 생성]</span> " \
           "<span class=\"btn-name\">[재생성]</span> <span class=\"btn-name\">[배포…]" in body


def test_save_steps_from_page(ops_client, ops_board):
    r = ops_client.post(URL + "?board=ops", _steps_post(ops_board, use_close="on", step_closed="마감"))
    assert r["Location"] == "/settings/?board=ops#steps"
    body = ops_client.get(URL + "?board=ops").content.decode()
    assert "<details open>" in body and body.index('<section id="steps"') < body.index("회차 단계를 저장했습니다.")
    assert "저장된 단계: <strong>입력 중 → 마감 → 확정 → 배포됨</strong>" in body
    ops_board.refresh_from_db()
    assert ops_board.use_close


def test_bad_step_names_redraw(ops_client, ops_board):
    r = ops_client.post(URL + "?board=ops", _steps_post(ops_board, step_generated="됨"))
    body = r.content.decode()
    assert r.status_code == 200 and "<details open>" in body and "버튼 이름이 비거나 다른 버튼과 같아집니다: []" in body
    assert "저장된 단계: <strong>입력 중 → 확정 → 배포됨</strong>" in body  # 미리보기는 저장된 값


def test_groups_menu_and_page_are_gone(admin_client_ok):
    """[그룹] 화면은 [근무표 설정]으로 바뀌었다(근무표 통합 3단계)."""
    assert admin_client_ok.get("/groups/").status_code == 404
    body = admin_client_ok.get("/").content.decode()
    assert ">그룹</a>" not in body and 'href="/settings/"' in body
