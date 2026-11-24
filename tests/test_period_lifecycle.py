from datetime import date

import pytest

from duty.errors import DutyError
from duty.models import Board, ChangeLog, Commute, DutyAssignment, Period, PeriodEvent
from duty.services import boards, periods
from duty.services.publish import publish, unpublish, unpublish_info
from duty.services.roster import find_day
from duty.shifts import weekdays
from tests.it_defs import OPS_STEPS
from tests.helpers import make_period, rows

S = Period.Status


def d(m, day):
    return date(2026, m, day)


# ── 배포 전 상태끼리 이동 ──

@pytest.mark.parametrize("to", [S.DRAFT, S.COLLECTING, S.CLOSED])
def test_move_from_generated_drops_control_duty_and_logs(make_member, admin_user, to):
    p = make_period("p", d(11, 9), d(11, 13), S.GENERATED, make_member("가"))
    p.seed = 3
    p.save()
    periods.move(p, to, by=admin_user)
    p.refresh_from_db()
    assert p.status == to and p.seed is None and p.generated_at is None
    assert not DutyAssignment.objects.filter(period=p).exists()
    assert Commute.objects.filter(period=p).count() == 5  # 출근표는 그대로
    ev = PeriodEvent.objects.get(period=p)
    assert (ev.from_status, ev.to_status, ev.by) == (S.GENERATED, to, admin_user)


def test_move_draft_to_closed_directly(it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=d(11, 9), end_date=d(11, 13))
    periods.move(p, S.CLOSED)
    assert Period.objects.get(pk=p.pk).status == S.CLOSED


@pytest.mark.parametrize("to", [S.GENERATED, S.PUBLISHED, "bogus"])
def test_move_rejects_targets_with_own_action(it_board, to):
    p = Period.objects.create(board=it_board, name="p", start_date=d(11, 9), end_date=d(11, 13), status=S.CLOSED)
    with pytest.raises(DutyError):
        periods.move(p, to)


def test_move_rejects_same_status_and_published(it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=d(11, 9), end_date=d(11, 13), status=S.CLOSED)
    with pytest.raises(DutyError):
        periods.move(p, S.CLOSED)
    p.status = S.PUBLISHED
    p.save()
    with pytest.raises(DutyError):
        periods.move(p, S.DRAFT)  # 배포된 회차는 배포 취소로만
    assert not PeriodEvent.objects.exists()


def test_draft_shrink_drops_commutes_outside(make_member):
    p = make_period("p", d(11, 9), d(11, 20), S.DRAFT, make_member("가"))
    DutyAssignment.objects.filter(period=p).delete()
    p.end_date = d(11, 13)
    periods.save_draft(p)
    assert sorted({x for x, *_ in rows(p)[0]}) == weekdays(d(11, 9), d(11, 13))


def test_create_and_generate_and_publish_are_logged(make_member, admin_user, it_board):
    p = periods.save_draft(Period(board=it_board, name="p", start_date=d(11, 9), end_date=d(11, 13)), by=admin_user)
    assert list(PeriodEvent.objects.values_list("from_status", "to_status")) == [("", S.DRAFT)]
    p2 = make_period("q", d(11, 16), d(11, 20), S.GENERATED, make_member("가"))
    publish(p2, d(11, 16), by=admin_user)
    ev = PeriodEvent.objects.filter(period=p2).get()
    assert (ev.from_status, ev.to_status) == (S.GENERATED, S.PUBLISHED) and "2026-11-16" in ev.note


# ── 배포 취소 ──

@pytest.fixture
def abc(make_member):
    ga, na, da = make_member("가"), make_member("나"), make_member("다")
    a = make_period("A", d(11, 2), d(11, 27), S.GENERATED, ga)
    b = make_period("B", d(11, 16), d(12, 11), S.GENERATED, na)
    c = make_period("C", d(12, 7), d(12, 18), S.GENERATED, da)
    return a, b, c


def test_unpublish_restores_previous_rows(abc, admin_user):
    a, b, _ = abc
    publish(a, d(11, 2))
    before_a, before_b = rows(a), rows(b)
    publish(b, d(11, 18))
    assert find_day(boards.it_board(), d(11, 19)).period_id == b.pk
    unpublish(b, by=admin_user)
    b.refresh_from_db()
    assert b.status == S.GENERATED and b.published_at is None and b.overwrite_from is None
    assert rows(a) == before_a and rows(b) == before_b
    assert find_day(boards.it_board(), d(11, 19)).period_id == a.pk
    assert find_day(boards.it_board(), d(12, 1)) is None
    assert PeriodEvent.objects.filter(period=b, to_status=S.GENERATED, from_status=S.PUBLISHED).exists()


def test_only_latest_publish_can_be_undone(abc):
    a, b, c = abc
    snap = rows(a), rows(b)
    publish(a, d(11, 2))
    publish(b, d(11, 18))
    publish(c, d(12, 9))
    with pytest.raises(DutyError, match="C"):
        unpublish(b)
    unpublish(c)
    unpublish(b)
    unpublish(a)
    assert (rows(a), rows(b)) == snap
    assert not Period.objects.filter(status=S.PUBLISHED).exists()


def test_unpublish_keeps_edits_and_counts_them(abc, admin_user):
    a, b, _ = abc
    publish(a, d(11, 2))
    publish(b, d(11, 18))
    from duty.services import changes
    na = Commute.objects.filter(period=b).first().member
    other = Commute.objects.filter(period=a).first().member
    changes.change_cell(admin_user, boards.it_board(), d(11, 19), "normal", na, other)
    info = unpublish_info(b)
    assert info.later_changes == 1 and info.restored_rows > 0 and info.blocker is None
    unpublish(b)
    assert Commute.objects.filter(period=b, date=d(11, 19), member=other).exists()  # 수정은 회차 데이터에 남는다
    assert ChangeLog.objects.filter(period=b).count() == 1


def test_unpublish_without_snapshot_refused(it_board):
    p = Period.objects.create(board=it_board, name="old", start_date=d(11, 9), end_date=d(11, 13), status=S.PUBLISHED)
    assert unpublish_info(p).blocker
    with pytest.raises(DutyError):
        unpublish(p)


def test_unpublish_requires_published(abc):
    a, *_ = abc
    with pytest.raises(DutyError):
        unpublish(a)


# ── Codex 리뷰: 오래된 객체·순서·이력 ──

def test_stale_period_objects_are_rechecked(abc, admin_user):
    from duty.services.generate import run_generation
    a, *_ = abc
    stale = Period.objects.get(pk=a.pk)
    publish(a, d(11, 2))
    undo = Period.objects.get(pk=a.pk).publish_undo
    with pytest.raises(DutyError):
        publish(stale, d(11, 2))  # 이미 배포됨: 보관한 행을 빈 값으로 덮지 않는다
    with pytest.raises(DutyError):
        periods.move(stale, S.DRAFT)
    with pytest.raises(DutyError):
        run_generation(stale)
    p = Period.objects.get(pk=a.pk)
    assert p.status == S.PUBLISHED and p.publish_undo == undo


def test_stale_collect_rejected(make_member, admin_user, it_board):
    from duty.services import collect
    m = make_member("가")
    p = Period.objects.create(board=it_board, name="p", start_date=d(11, 9), end_date=d(11, 9), status=S.COLLECTING)
    stale = Period.objects.get(pk=p.pk)
    periods.move(p, S.CLOSED)
    with pytest.raises(DutyError):
        collect.apply_table(admin_user, stale, m.department, {d(11, 9): {"normal": [m.name]}})
    assert not Commute.objects.filter(period=p).exists()


def test_latest_publish_by_order_not_clock(abc):
    a, b, _ = abc
    publish(a, d(11, 2))
    publish(b, d(11, 18))
    Period.objects.filter(pk__in=[a.pk, b.pk]).update(published_at=Period.objects.get(pk=a.pk).published_at)
    with pytest.raises(DutyError, match="B"):
        unpublish(a)


def test_changes_before_unpublish_not_replayed(abc, admin_user):
    from duty.services import changes
    a, b, _ = abc
    publish(b, d(11, 16))
    na = Commute.objects.filter(period=b, date=d(11, 19)).first().member
    changes.change_cell(admin_user, boards.it_board(), d(11, 19), "normal", na, None)  # 제거
    assert find_day(boards.it_board(), d(11, 19)).cells["normal"].removed == [na.name]
    unpublish(b)
    Commute.objects.create(period=b, date=d(11, 19), member=na, shift="normal")  # 다시 입력
    publish(b, d(11, 16))
    cell = find_day(boards.it_board(), d(11, 19)).cells["normal"]
    assert cell.removed == [] and not cell.changed and cell.labels == [na.name]
    assert ChangeLog.objects.filter(period=b).count() == 1  # 기록은 남는다


def test_period_with_events_cannot_be_deleted(it_board):
    from django.db.models import ProtectedError
    p = periods.save_draft(Period(board=it_board, name="p", start_date=d(11, 9), end_date=d(11, 13)))
    with pytest.raises(ProtectedError):
        p.delete()


def test_unpublish_cutoff_ignores_clock(abc, admin_user):
    """배포 취소 이전 기록은 시각이 아니라 기록 번호로 가른다(시계가 뒤로 가도)."""
    from datetime import timedelta
    from duty.services import changes
    _, b, _ = abc
    publish(b, d(11, 16))
    m = Commute.objects.filter(period=b, date=d(11, 19)).first().member
    changes.change_cell(admin_user, boards.it_board(), d(11, 19), "normal", m, None)
    unpublish(b)
    Commute.objects.create(period=b, date=d(11, 19), member=m, shift="normal")
    publish(b, d(11, 16))
    changes.change_cell(admin_user, boards.it_board(), d(11, 20), "normal", m, None)  # 새 주기의 변경
    ChangeLog.objects.filter(date=d(11, 20)).update(at=ChangeLog.objects.get(date=d(11, 19)).at - timedelta(days=1))
    assert find_day(boards.it_board(), d(11, 20)).cells["normal"].removed == [m.name]  # 시각이 과거여도 보인다
    assert find_day(boards.it_board(), d(11, 19)).cells["normal"].removed == []


# ── 회차 삭제 ──

@pytest.mark.parametrize("status", [S.DRAFT, S.COLLECTING, S.CLOSED, S.GENERATED])
def test_delete_unpublished_period(make_member, admin_user, status):
    p = make_period("p", d(11, 9), d(11, 13), status, make_member("가"))
    periods.record(p, "", admin_user)
    periods.delete(p)
    assert not Period.objects.filter(pk=p.pk).exists()
    assert not Commute.objects.exists() and not DutyAssignment.objects.exists() and not PeriodEvent.objects.exists()


def test_delete_refuses_published_and_logged(abc, admin_user):
    from duty.services import changes
    a, b, _ = abc
    publish(b, d(11, 16))
    with pytest.raises(DutyError, match="배포"):
        periods.delete(Period.objects.get(pk=b.pk))
    m = Commute.objects.filter(period=b, date=d(11, 19)).first().member
    changes.change_cell(admin_user, boards.it_board(), d(11, 19), "normal", m, None)
    unpublish(b)
    with pytest.raises(DutyError, match="기록"):
        periods.delete(Period.objects.get(pk=b.pk))
    assert Period.objects.filter(pk=b.pk).exists()


def test_delete_rechecks_stale_object(make_member):
    p = make_period("p", d(11, 9), d(11, 13), S.GENERATED, make_member("가"))
    stale = Period.objects.get(pk=p.pk)
    Period.objects.filter(pk=p.pk).update(status=S.PUBLISHED)
    with pytest.raises(DutyError):
        periods.delete(stale)


# ── 옮기기 오류 글(근무표 통합 1단계가 순서를 바꿔도 네 글자는 그대로, 설계 6.1) ──

@pytest.mark.parametrize("status,to,msg", [
    (S.PUBLISHED, S.COLLECTING, "배포된 회차는 배포 취소로만 되돌릴 수 있습니다."),
    (S.COLLECTING, S.COLLECTING, "이미 그 상태입니다."),
    (S.DRAFT, S.GENERATED, "옮길 수 없는 상태입니다."),
])
def test_move_messages(it_board, status, to, msg):
    p = Period.objects.create(board=it_board, name="p", start_date=d(11, 9), end_date=d(11, 13), status=status)
    with pytest.raises(DutyError) as e:
        periods.move(p, to)
    assert str(e.value) == msg


def test_move_message_for_board_without_draft_and_close(it_board):
    ops = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
    p = Period.objects.create(board=ops, name="p", start_date=d(11, 9), end_date=d(11, 13), status=S.GENERATED)
    with pytest.raises(DutyError) as e:
        periods.move(p, S.DRAFT)
    assert str(e.value) == "'입력 중'(으)로만 옮길 수 있습니다."  # 근무표 통합 2단계: 켠 단계 이름으로
