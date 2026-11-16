"""그룹 화면(설계 7절): 그룹 관리자(GroupKeeper)가 맡은 그룹의 멤버를 넣고 뺀다. 이름은 모두 가상."""
import pytest
from django.core.exceptions import PermissionDenied

from duty.errors import DutyError
from duty.models import GroupKeeper
from duty.services import groups


@pytest.fixture
def keeper(make_member, it_board, depts):
    """IT 근무표 관리 그룹과 매칭엔진실 입력 그룹을 맡은 가상관리."""
    k = make_member("가상관리", user=True)
    GroupKeeper.objects.create(group=it_board.admin_group, user=k)
    GroupKeeper.objects.create(group=depts["MEMS"].input_group, user=k)
    return k


# ── 서비스 ──

def test_keeper_adds_and_removes(keeper, it_board, make_member):
    m = make_member("가상가")
    groups.add_member(keeper, it_board.admin_group, m)
    assert it_board.admin_group.user_set.filter(pk=m.pk).exists()
    assert groups.remove_member(keeper, it_board.admin_group, m) == "IT 당번표 근무표 관리자가 아무도 없습니다. 회차·배포를 할 사람이 없으니 다른 사람을 넣으세요."
    assert not it_board.admin_group.user_set.exists()


def test_no_warning_while_admins_remain_or_for_input_group(keeper, it_board, depts, admin_user, make_member):
    m = make_member("가상가")
    groups.add_member(keeper, it_board.admin_group, m)
    assert groups.remove_member(keeper, it_board.admin_group, m) == ""  # admin_user 가 남아 있다
    group = depts["MEMS"].input_group
    groups.add_member(keeper, group, m)
    assert groups.remove_member(keeper, group, m) == ""  # 입력 그룹은 비어도 경고하지 않는다


def test_only_keeper_of_that_group(keeper, depts, make_member):
    m = make_member("가상가")
    with pytest.raises(PermissionDenied):
        groups.add_member(keeper, depts["TMCH"].input_group, m)
    with pytest.raises(PermissionDenied):
        groups.add_member(m, depts["MEMS"].input_group, m)


def test_rules(keeper, depts, make_member):
    group = depts["MEMS"].input_group
    gone = make_member("가상퇴사", active=False)
    with pytest.raises(DutyError, match="퇴사한 사람은 넣을 수 없습니다"):
        groups.add_member(keeper, group, gone)
    m = make_member("가상가")
    groups.add_member(keeper, group, m)
    with pytest.raises(DutyError, match="이미 이 그룹에 있습니다"):
        groups.add_member(keeper, group, m)
    with pytest.raises(DutyError, match="이 그룹에 없는 사람입니다"):
        groups.remove_member(keeper, group, gone)


# ── 화면 ──

def test_menu_and_page_only_for_keepers(client, keeper, make_member):
    other = make_member("가상가", user=True)
    client.force_login(other)
    assert ">그룹</a>" not in client.get("/").content.decode()
    assert client.get("/groups/").status_code == 403
    client.force_login(keeper)
    assert 'href="/groups/"' in client.get("/").content.decode()
    assert client.get("/groups/").status_code == 200


def test_page_lists_kept_groups_members_and_candidates(client, keeper, it_board, depts, admin_user, make_member):
    gone = make_member("가상퇴사", active=False)
    depts["MEMS"].input_group.user_set.add(gone)
    make_member("가상후보")
    client.force_login(keeper)
    body = client.get("/groups/").content.decode()
    assert "<strong>IT 근무표 관리</strong>" in body and "<strong>매칭엔진실 출근표 입력</strong>" in body and "매매지원실 출근표 입력" not in body
    assert "IT 당번표 근무표 관리자(회차·배포·메모·지난 날짜 수정)" in body and "매칭엔진실 출근표 입력 담당" in body
    assert "가상퇴사 (퇴사)" in body  # 퇴사자도 보여 뺄 수 있게
    assert body.count(">가상후보 · 매칭엔진실</option>") == 2  # 두 그룹 모두 후보
    assert ">가상퇴사 · 매칭엔진실</option>" not in body  # 퇴사자는 넣을 후보가 아니다
    assert f'<option value="{admin_user.pk}">관리자</option>' in body  # 부서 없는 계정도 후보(입력 그룹 후보)


def test_post_add_remove_and_warning(client, keeper, it_board, admin_user, make_member):
    m = make_member("가상가")
    client.force_login(keeper)
    g = it_board.admin_group.pk
    r = client.post("/groups/", {"group": g, "member": m.pk, "do": "add"}, follow=True)
    assert "가상가을(를) IT 근무표 관리에 넣었습니다." in r.content.decode()  # 그룹 이름은 마이그레이션 0011 이 정했다
    client.post("/groups/", {"group": g, "member": m.pk, "do": "remove"})
    r = client.post("/groups/", {"group": g, "member": admin_user.pk, "do": "remove"}, follow=True)
    assert "근무표 관리자가 아무도 없습니다" in r.content.decode()
    assert not it_board.admin_group.user_set.exists()


def test_post_to_group_not_kept_is_404(client, keeper, depts, make_member):
    m = make_member("가상가")
    client.force_login(keeper)
    assert client.post("/groups/", {"group": depts["TMCH"].input_group.pk, "member": m.pk, "do": "add"}).status_code == 404
    assert client.post("/groups/", {"group": depts["MEMS"].input_group.pk, "member": "x", "do": "add"}).status_code == 404
