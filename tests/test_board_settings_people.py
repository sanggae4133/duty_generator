"""[근무표 설정] 사람 서비스(근무표 통합 설계 5.7·6.2·8): 추가·고치기·퇴사(두 번째 확인)·다시 재직·계정 발급/초기화,
대상 규칙, 기록. 이름은 모두 가상. 비밀번호 문자열은 적지 않고 발급 결과를 그대로 쓴다."""
import logging
from datetime import date

import pytest
from django.contrib.admin.models import LogEntry
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from duty.errors import DutyError
from duty.models import AlarmRule, CalendarFeed, Commute, Department, DutyAssignment, Period, User
from duty.services import board_settings as bs

S = Period.Status
TODAY = date(2026, 12, 2)  # 수요일


@pytest.fixture
def ops_admin(ops_board):
    """운영팀 관리자 가상운영(부서 없는 계정)."""
    u = User.objects.create_user("opsadm", password=None, name="가상운영")
    ops_board.admin_group.user_set.add(u)
    return u


@pytest.fixture
def ops_dept(ops_board):
    return Department.objects.get(code="OPS")


def _ops_member(dept, name, username, active=True):
    return User.objects.create_user(username, password=None, name=name, department=dept, type="직원", is_active=active)


# ── 권한: 그 근무표 관리자만 ──

@pytest.mark.parametrize("who", ["it_admin", "superuser", "anonymous"])
def test_people_functions_only_that_board_admin(who, ops_board, ops_admin, ops_dept, admin_user):
    from django.contrib.auth.models import AnonymousUser
    su = User.objects.create_superuser("root", password=None, name="가상슈퍼")
    by = {"it_admin": admin_user, "superuser": su, "anonymous": AnonymousUser()}[who]
    m = _ops_member(ops_dept, "가상하나", "ops01")
    for call in (lambda: bs.add_person(by, ops_board, "ops02", "가상두리", ops_dept),
                 lambda: bs.set_person(by, ops_board, m, "가상새이름"),
                 lambda: bs.set_active(by, ops_board, m, False),
                 lambda: bs.issue(by, ops_board, [m])):
        with pytest.raises(PermissionDenied):
            call()
    m.refresh_from_db()
    assert (m.name, m.is_active, m.has_usable_password()) == ("가상하나", True, False)
    assert not User.objects.filter(username="ops02").exists()


# ── 대상: 그 근무표 부서 사람 중 슈퍼유저·나 자신·관리자 계정(어느 근무표든)이 아닌 사람 ──

def test_people_targets(it_board, ops_board, ops_dept, make_member):
    me = _ops_member(ops_dept, "가상나관리", "ops08")  # 부서가 있는 이 근무표 관리자(나 자신)
    ops_board.admin_group.user_set.add(me)
    other_admin = _ops_member(ops_dept, "가상겸직", "ops09")  # 이 근무표 사람이지만 IT 관리자(관리자 계정)
    it_board.admin_group.user_set.add(other_admin)
    su = User.objects.create_superuser("root", password=None, name="가상슈퍼", department=ops_dept, type="직원")
    it_person = make_member("가상아이티")  # 다른 근무표 사람
    nodept = User.objects.create_user("free1", password=None, name="가상무소속")  # 부서 없는 계정
    targets = [me, other_admin, su, it_person, nodept]
    for t in targets:
        for call in (lambda: bs.set_person(me, ops_board, t, "가상새이름"),
                     lambda: bs.set_active(me, ops_board, t, False),
                     lambda: bs.issue(me, ops_board, [t])):
            with pytest.raises(PermissionDenied):
                call()
    assert not User.objects.filter(name="가상새이름").exists()
    assert all(u.is_active for u in User.objects.filter(pk__in=[t.pk for t in targets]))
    assert bs.locked_ids() >= {me.pk, other_admin.pk, su.pk} and it_person.pk not in bs.locked_ids()


# ── 추가·고치기 ──

def test_add_person_checks(ops_board, ops_admin, ops_dept, depts):
    for bad in ("Ops01", "가상01", "1ops", "o", "ops-01", "ops 01"):  # 실명·대문자 아이디가 로그·기록에 남지 않게
        with pytest.raises(DutyError, match="아이디는 영문 소문자로 시작하고"):
            bs.add_person(ops_admin, ops_board, bad, "가상하나", ops_dept)
    _ops_member(ops_dept, "가상하나", "OPS01")
    with pytest.raises(DutyError, match="같은 아이디가 이미 있습니다"):
        bs.add_person(ops_admin, ops_board, "ops01", "가상두리", ops_dept)  # 대소문자만 다른 아이디
    with pytest.raises(DutyError, match="^이름: 같은 이름이 이미 있습니다"):
        bs.add_person(ops_admin, ops_board, "ops02", "가상하나", ops_dept)
    for name in ("=가상", "가상(휴가)", " "):  # 이름 규칙(validate_member_name)·빈 이름
        with pytest.raises(DutyError, match="^이름: "):
            bs.add_person(ops_admin, ops_board, "ops02", name, ops_dept)
    with pytest.raises(PermissionDenied):
        bs.add_person(ops_admin, ops_board, "ops02", "가상두리", depts["MEMS"])  # 다른 근무표 부서
    u = bs.add_person(ops_admin, ops_board, "ops02", " 가상두리 ", ops_dept, "개발자")
    u.refresh_from_db()
    # 장중관제가 없는 근무표: 구분은 늘 직원(보낸 구분은 무시), 비밀번호는 쓸 수 없는 값(발급 전)
    assert (u.name, u.department_id, u.type, u.is_active, u.has_usable_password()) == ("가상두리", "OPS", "직원", True, False)


def test_type_only_on_boards_with_slots(it_board, admin_user, depts):
    with pytest.raises(DutyError, match="구분"):
        bs.add_person(admin_user, it_board, "it01", "가상하나", depts["MEMS"])
    u = bs.add_person(admin_user, it_board, "it01", "가상하나", depts["MEMS"], "개발자")
    assert u.type == "개발자"
    bs.set_person(admin_user, it_board, u, "가상하나", "직원")
    assert User.objects.get(pk=u.pk).type == "직원"


def test_set_person_keeps_type_where_no_types(ops_board, ops_admin, ops_dept):
    m = User.objects.create_user("ops01", password=None, name="가상하나", department=ops_dept, type="개발자")
    _ops_member(ops_dept, "가상두리", "ops02")
    with pytest.raises(DutyError, match="^이름: 같은 이름이 이미 있습니다"):
        bs.set_person(ops_admin, ops_board, m, "가상두리")
    bs.set_person(ops_admin, ops_board, m, " 가상새이름 ", "직원")
    m.refresh_from_db()
    assert (m.name, m.type) == ("가상새이름", "개발자")  # 구분 칸이 없는 근무표: 구분은 그대로


def test_next_username(ops_board, ops_dept):
    assert bs.next_username(ops_board) == "ops01"
    _ops_member(ops_dept, "가상하나", "ops01")
    _ops_member(ops_dept, "가상두리", "OPS02")  # 대소문자만 달라도 쓴 번호
    _ops_member(ops_dept, "가상세찬", "ops04", active=False)
    assert bs.next_username(ops_board) == "ops03"
    _ops_member(ops_dept, "가상네모", "ops03")
    assert bs.next_username(ops_board) == "ops05"  # 퇴사자 번호(ops04)도 다시 쓰지 않는다


def test_set_person_ignores_unrelated_legacy_fields(ops_board, ops_admin, ops_dept):
    """이름·구분만 검사한다: 지금 규칙에 맞지 않는 옛 값(띄어쓰기 든 아이디·전자우편 모양이 아닌 값)이 고치기를 막지 않는다."""
    m = User.objects.create_user("ops 01", password=None, name="가상하나", department=ops_dept, type="직원",
                                 email="not-an-email")
    bs.set_person(ops_admin, ops_board, m, "가상새이름")
    assert User.objects.get(pk=m.pk).name == "가상새이름"


# ── 남은 근무·퇴사(두 번째 확인)·다시 재직 ──

@pytest.fixture
def busy(ops_board, ops_dept, fixed_today):
    """오늘(12/2) 이후 칸이 셋인 가상하나: 배포 근무 12/3(근무조·점심당번), 입력 중 회차 1/5."""
    fixed_today(TODAY)
    m = _ops_member(ops_dept, "가상하나", "ops01")
    old = Period.objects.create(board=ops_board, name="옛 회차", start_date=date(2026, 11, 30), end_date=date(2026, 12, 4),
                                status=S.PUBLISHED)
    Commute.objects.create(period=old, date=date(2026, 12, 3), member=m, shift="dinner")  # 뒤 배포에 덮였다: 빠진다
    done = Period.objects.create(board=ops_board, name="12월 회차", start_date=date(2026, 11, 30), end_date=date(2026, 12, 4),
                                 status=S.PUBLISHED)
    Commute.objects.create(period=done, date=date(2026, 12, 1), member=m, shift="normal")  # 어제: 빠진다
    Commute.objects.create(period=done, date=date(2026, 12, 3), member=m, shift="normal")
    DutyAssignment.objects.create(period=done, date=date(2026, 12, 3), member=m, cell="lunch")
    nxt = Period.objects.create(board=ops_board, name="1월 회차", start_date=date(2027, 1, 4), end_date=date(2027, 1, 15),
                                status=S.COLLECTING)
    Commute.objects.create(period=nxt, date=date(2027, 1, 5), member=m, shift="dawn")
    return m


def test_future_cells(busy, ops_board):
    assert [(d, cell, p.name, step) for d, cell, p, step in bs.future_cells(ops_board, busy)] == [
        (date(2026, 12, 3), "가운데", "12월 회차", "배포됨"), (date(2026, 12, 3), "점심당번", "12월 회차", "배포됨"),
        (date(2027, 1, 5), "이른", "1월 회차", "입력 중")]


def test_leave_asks_with_count_then_cuts(busy, ops_board, ops_admin):
    with pytest.raises(bs.NeedsConfirm) as e:
        bs.set_active(ops_admin, ops_board, busy, False)
    assert e.value.rows == 3 and str(e.value) == "이 근무 3칸은 그대로 남습니다. 근무표·입력 표에서 다른 사람으로 바꾸세요."
    with pytest.raises(bs.NeedsConfirm):
        bs.set_active(ops_admin, ops_board, busy, False, confirm=2)  # 본 칸 수와 다르면(그사이 바뀜) 다시 묻는다
    assert User.objects.get(pk=busy.pk).is_active
    assert len(bs.set_active(ops_admin, ops_board, busy, False, confirm=3)) == 3  # 퇴사 뒤 목록을 돌려준다
    busy.refresh_from_db()
    assert not busy.is_active and not busy.has_usable_password()
    with pytest.raises(DutyError, match="이미 퇴사"):
        bs.set_active(ops_admin, ops_board, busy, False, confirm=3)
    assert bs.set_active(ops_admin, ops_board, busy, True) == []
    busy.refresh_from_db()
    assert busy.is_active and not busy.has_usable_password()  # 다시 재직: 계정은 '발급 전'(다시 발급해야 로그인)


def test_leave_without_future_cells_is_one_step(ops_board, ops_admin, ops_dept):
    m = _ops_member(ops_dept, "가상하나", "ops01")
    assert bs.set_active(ops_admin, ops_board, m, False) == []
    assert not User.objects.get(pk=m.pk).is_active


# ── 계정 발급·초기화 ──

def test_issue_many_all_or_nothing_and_keeps_links(ops_board, ops_admin, ops_dept, make_member):
    a, b = _ops_member(ops_dept, "가상하나", "ops01"), _ops_member(ops_dept, "가상두리", "ops02")
    gone = _ops_member(ops_dept, "가상퇴사", "ops05", active=False)
    with pytest.raises(PermissionDenied):
        bs.issue(ops_admin, ops_board, [a, make_member("가상아이티")])  # 하나라도 대상이 아니면 아무것도 안 한다
    with pytest.raises(DutyError, match="퇴사한 사람은 먼저 \\[다시 재직\\]"):
        bs.issue(ops_admin, ops_board, [a, gone])
    with pytest.raises(DutyError, match="고르세요"):
        bs.issue(ops_admin, ops_board, [])
    assert not User.objects.get(pk=a.pk).has_usable_password()
    out = bs.issue(ops_admin, ops_board, [a, b])
    assert [u.username for u, _ in out] == ["ops01", "ops02"]
    for u, pw in out:
        u = User.objects.get(pk=u.pk)
        assert u.check_password(pw) and u.must_change_password
    assert AlarmRule.objects.filter(user=a).count() == 2  # 첫 발급: 기본 알림 규칙
    CalendarFeed.objects.create(user=a, token_hash="h" * 64, issued_at=timezone.now())
    [(_, pw)] = bs.issue(ops_admin, ops_board, [a])  # 초기화: 연결은 남긴다(비밀번호 분실 길)
    assert User.objects.get(pk=a.pk).check_password(pw) and CalendarFeed.objects.filter(user=a).exists()


# ── 기록: 로그 한 줄 + LogEntry 한 줄, 실명·비밀번호 없음 ──

def test_people_writes_log_without_names_or_passwords(ops_board, ops_admin, ops_dept, caplog):
    caplog.set_level(logging.DEBUG)  # 모든 로거
    u = bs.add_person(ops_admin, ops_board, "ops01", "가상하나", ops_dept)
    bs.set_person(ops_admin, ops_board, u, "가상하나둘")
    [(_, pw1)] = bs.issue(ops_admin, ops_board, [u])
    [(_, pw2)] = bs.issue(ops_admin, ops_board, [u])
    bs.set_active(ops_admin, ops_board, u, False)
    bs.set_active(ops_admin, ops_board, u, True)
    actions = ["사람 추가", "이름·구분 고치기", "계정 발급", "비밀번호 초기화", "퇴사", "다시 재직"]
    assert [r.getMessage() for r in caplog.records if r.name == "duty.services.board_settings"] == [
        f"board ops: {a} ops01 by opsadm" for a in actions]
    rows = list(LogEntry.objects.order_by("id").values_list("user__username", "object_id", "object_repr", "change_message"))
    assert rows == [("opsadm", str(u.pk), "ops01", f"근무표 ops: {a}") for a in actions]
    traces = caplog.text + str(rows)
    assert "가상" not in traces and pw1 not in traces and pw2 not in traces
