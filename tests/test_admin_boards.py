"""관리 화면(슈퍼유저 전용): 근무표·근무 정의·그룹 관리자는 1단계에서 보기만. 그룹 화면은 권한 칸만 숨긴다."""
import pytest
from django.urls import reverse

from duty.models import GroupKeeper


@pytest.fixture
def su(admin_user):
    admin_user.is_superuser = True
    admin_user.save()
    return admin_user


@pytest.fixture
def su_client(client, su):
    client.force_login(su)
    return client


def test_board_add_not_allowed(su_client, it_board):
    assert su_client.get(reverse("admin:duty_board_add")).status_code == 403  # 근무표 추가는 3단계
    assert reverse("admin:duty_board_add") not in su_client.get(reverse("admin:duty_board_changelist")).content.decode()


def test_board_fields_read_only(su_client, it_board):
    body = su_client.get(reverse("admin:duty_board_change", args=[it_board.pk])).content.decode()
    assert it_board.name in body and it_board.admin_group.name in body  # 이름·관리 그룹은 글자로 보인다
    assert 'name="name"' not in body and 'name="code"' not in body and 'name="input_mode"' not in body


def test_shift_definitions_read_only(su_client, it_board):
    body = su_client.get(reverse("admin:duty_board_change", args=[it_board.pk])).content.decode()
    assert "석식교대" in body and "근무조 1" in body and "관제 10" in body  # 키는 중립 이름으로 보인다
    assert 'name="shifts-0-name"' not in body and 'name="shifts-0-DELETE"' not in body
    assert 'name="shifts-0-active"' not in body


def test_board_cannot_be_changed(su_client, it_board):
    name, url = it_board.name, reverse("admin:duty_board_change", args=[it_board.pk])
    r = su_client.post(url, {"name": "바뀐 이름", "shifts-TOTAL_FORMS": "0", "shifts-INITIAL_FORMS": "0"})
    assert r.status_code == 403  # 수정 권한 없음(근무표 편집은 3단계)
    assert su_client.post(reverse("admin:duty_board_delete", args=[it_board.pk]), {"post": "yes"}).status_code == 403
    it_board.refresh_from_db()
    assert it_board.name == name


def test_group_page_hides_permissions_and_keepers_read_only(su_client, it_board, admin_user):
    GroupKeeper.objects.create(group=it_board.admin_group, user=admin_user)
    html = su_client.get(reverse("admin:auth_group_change", args=[it_board.admin_group.pk])).content.decode()
    assert 'name="name"' in html and 'name="permissions"' not in html
    assert 'name="members"' not in html  # 멤버는 사용자 화면의 '그룹' 칸에서 넣는다
    assert 'name="keepers-0-user"' not in html and admin_user.name in html  # 그룹 관리자는 보기만(편집은 3단계)
