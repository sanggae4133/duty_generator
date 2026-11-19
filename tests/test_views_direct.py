"""직접 입력 근무표의 회차 화면(설계 7절): 입력 중 → 확정 → 배포됨, [표 입력]·[확정]·[확정 취소], 확정 경고. 이름은 모두 가상."""
from datetime import date, time

import pytest

from duty.models import Board, BoardShift, Commute, Department, Period, User
from tests.it_defs import OPS_STEPS

S = Period.Status
MON, FRI = date(2026, 11, 16), date(2026, 11, 20)


@pytest.fixture
def ops(it_board, admin_user):
    """가짜 직접 입력 근무표 '운영팀'(근무조 셋 + 점심당번, 부서 하나). admin_user 는 IT·운영팀 둘 다 관리한다."""
    board = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
    for key, name, h in (("dawn", "이른", 7), ("normal", "가운데", 9), ("dinner", "늦은", 11)):
        BoardShift.objects.create(board=board, key=key, name=name, start=time(h, 30), end=time(h + 9, 30))
    BoardShift.objects.create(board=board, key="lunch", name="점심당번")
    dept = Department.objects.create(code="OPS", name="운영", shifts="dawn,normal,dinner", board=board)
    board.admin_group.user_set.add(admin_user)
    return board, dept


def ops_member(dept, name):
    return User.objects.create_user(f"OPS{User.objects.count() + 1:03d}", password=None, name=name,
                                    department=dept, part="", type="직원")


def fill(p, member, days):
    for x in days:
        Commute.objects.create(period=p, date=x, member=member, shift="dawn")


def test_create_direct_period_from_list(admin_client_ok, ops):
    r = admin_client_ok.post("/periods/", {"board": ops[0].pk, "name": "운영 11월",
                                           "start_date": "2026-11-16", "end_date": "2026-11-20"})
    p = Period.objects.get(name="운영 11월")
    assert r.status_code == 302 and p.status == S.COLLECTING
    body = admin_client_ok.get("/periods/").content.decode()
    assert '<span class="pill st-collecting">입력 중</span>' in body


def test_input_page_shows_direct_steps_and_buttons(admin_client_ok, ops):
    board, dept = ops
    p = Period.objects.create(board=board, name="p", start_date=MON, end_date=FRI, status=S.COLLECTING)
    fill(p, ops_member(dept, "가상가"), p.dates()[:3])
    body = admin_client_ok.get(f"/periods/{p.pk}/").content.decode()
    assert "<small>(입력 중)</small>" in body
    assert body.index(">입력 중<") < body.index(">확정<") < body.index(">배포됨<")
    assert "취합 중" not in body and "작성 중" not in body and "마감" not in body
    assert f'href="/collect/{p.pk}/OPS/">표 입력</a>' in body
    assert f'action="/periods/{p.pk}/action/generate/"' in body and ">확정</button>" in body
    assert 'name="start_date"' in body  # 입력 중에도 기간을 고친다
    assert "⚠ 출근표가 비어 있는 날: 운영 2일(11/19~11/20). [확정] 버튼은 누를 수 있지만 그날 그 부서는 근무자가 없습니다." in body
    assert "부서별 입력 현황" in body and "운영: 3 / 5일" in body  # 입력 현황은 모든 근무표, 부서 이름으로(근무표 통합 2단계)
    assert "생성 방식" not in body and "다른 상태로 옮기기" not in body


def test_confirmed_page_shows_publish_and_cancel(admin_client_ok, ops):
    board, dept = ops
    p = Period.objects.create(board=board, name="p", start_date=MON, end_date=FRI, status=S.GENERATED)
    body = admin_client_ok.get(f"/periods/{p.pk}/").content.decode()
    assert "<small>(확정)</small>" in body and "배포…</a>" in body
    assert f'action="/periods/{p.pk}/move/"' in body and 'name="to" value="collecting"' in body and "확정 취소" in body
    assert 'name="start_date"' not in body and ">표 입력</a>" not in body
    assert "생성 방식" not in body  # 직접 입력에는 생성 규칙 설명이 없다


def test_confirm_shows_empty_day_warning(admin_client_ok, ops):
    board, dept = ops
    p = Period.objects.create(board=board, name="p", start_date=MON, end_date=FRI, status=S.COLLECTING)
    fill(p, ops_member(dept, "가상가"), p.dates()[:4])
    r = admin_client_ok.post(f"/periods/{p.pk}/action/generate/", follow=True)
    body = r.content.decode()
    assert "출근표가 비어 있는 날이 있습니다: 운영 1일(11/20). 그날 그 부서는 근무자가 없습니다." in body
    assert "<small>(확정)</small>" in body
    assert "확정 → 확정" not in body and "입력 중 → 확정" in body  # 상태 기록도 화면 이름으로


def test_cancel_confirm_returns_to_input(admin_client_ok, ops):
    board, dept = ops
    p = Period.objects.create(board=board, name="p", start_date=MON, end_date=FRI, status=S.GENERATED)
    admin_client_ok.post(f"/periods/{p.pk}/move/", {"to": "collecting"})
    p.refresh_from_db()
    assert p.status == S.COLLECTING


def test_input_table_links_back_and_names_closed_state(admin_client_ok, ops):
    board, dept = ops
    p = Period.objects.create(board=board, name="p", start_date=MON, end_date=FRI, status=S.GENERATED)
    body = admin_client_ok.get(f"/collect/{p.pk}/OPS/").content.decode()
    assert f'href="/periods/{p.pk}/"' in body and "'입력 중'인 회차가 아니라 저장할 수 없습니다" in body


def test_collect_period_page_unchanged(admin_client_ok, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=MON, end_date=FRI, status=S.COLLECTING)
    body = admin_client_ok.get(f"/periods/{p.pk}/").content.decode()
    assert "<small>(취합 중)</small>" in body and "취합 마감" in body and "부서별 입력 현황" in body
    assert ">표 입력</a>" not in body and ">확정</button>" not in body


def test_published_page_names_confirmed_state_in_unpublish(admin_client_ok, ops):
    board, dept = ops
    from duty.services.publish import publish
    p = Period.objects.create(board=board, name="p", start_date=MON, end_date=FRI, status=S.GENERATED)
    publish(p, MON)
    body = admin_client_ok.get(f"/periods/{p.pk}/").content.decode()
    assert "<small>(배포됨)</small>" in body
    assert "이 회차를 확정으로 되돌릴까요?" in body and "이 회차는 확정으로 돌아갑니다" in body and "생성됨" not in body


def test_publish_error_names_confirm(ops):
    from duty.errors import DutyError
    from duty.services.publish import publish
    p = Period.objects.create(board=ops[0], name="p", start_date=MON, end_date=FRI, status=S.COLLECTING)
    with pytest.raises(DutyError, match="'확정'인 회차만 배포할 수 있습니다"):
        publish(p, MON)


def test_empty_input_list_names_input_state(client, ops, admin_user, it_board):
    it_board.admin_group.user_set.remove(admin_user)  # 운영팀(직접 입력)만 관리
    client.force_login(admin_user)
    assert "<p>입력 중인 회차가 없습니다.</p>" in client.get("/collect/").content.decode()


@pytest.mark.parametrize("status", [S.DRAFT, S.CLOSED])
def test_direct_period_in_odd_state_can_move_to_input(admin_client_ok, ops, status):
    """입력 방식이 바뀌어 작성 중·마감에 남은 직접 입력 회차도 입력 중으로 옮길 수 있다."""
    p = Period.objects.create(board=ops[0], name="p", start_date=MON, end_date=FRI, status=status)
    body = admin_client_ok.get(f"/periods/{p.pk}/").content.decode()
    assert "다른 상태로 옮기기" in body and '<option value="collecting">' in body
    assert '<option value="draft">' not in body and '<option value="closed">' not in body


def test_only_first_input_button_is_primary(admin_client_ok, ops):
    board, _ = ops
    Department.objects.create(code="OP2", name="운영2", shifts="dawn", board=board, order=100)
    p = Period.objects.create(board=board, name="p", start_date=MON, end_date=FRI, status=S.COLLECTING)
    body = admin_client_ok.get(f"/periods/{p.pk}/").content.decode()
    assert f'<a role="button" href="/collect/{p.pk}/OPS/">' in body
    assert f'<a role="button" class="outline" href="/collect/{p.pk}/OP2/">' in body


SHRINK = "기간을 줄이면 바깥 날짜의 출근표가 지워집니다. 저장할까요?"


def test_period_save_confirms_only_when_shrinking(admin_client_ok, ops, it_board):
    """기간 저장: 지금 기간(data-start/end)보다 좁힐 때만 확인 창(바깥 날짜 행이 지워진다). 모든 근무표(근무표 통합 2단계)."""
    p = Period.objects.create(board=ops[0], name="p", start_date=MON, end_date=FRI, status=S.COLLECTING)
    body = admin_client_ok.get(f"/periods/{p.pk}/").content.decode()
    assert 'data-start="2026-11-16" data-end="2026-11-20"' in body
    assert ("this.start_date.value &gt; this.dataset.start || this.end_date.value &lt; this.dataset.end" in body
            and SHRINK in body)
    draft = Period.objects.create(board=it_board, name="d", start_date=MON, end_date=FRI, status=S.DRAFT)
    assert SHRINK in admin_client_ok.get(f"/periods/{draft.pk}/").content.decode()  # 되돌아온 작성 중 회차는 행이 있을 수 있다


def test_confirm_message_says_what_happened(admin_client_ok, ops):
    board, dept = ops
    p = Period.objects.create(board=board, name="p", start_date=MON, end_date=FRI, status=S.COLLECTING)
    fill(p, ops_member(dept, "가상가"), p.dates())
    body = admin_client_ok.post(f"/periods/{p.pk}/action/generate/", follow=True).content.decode()
    assert "&#x27;확정&#x27; 상태로 바꿨습니다. 근무표 화면에는 배포한 뒤에 보입니다." in body and "완료했습니다" not in body
