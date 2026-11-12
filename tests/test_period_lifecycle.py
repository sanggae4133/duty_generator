from datetime import date

import pytest

from duty.errors import DutyError
from duty.models import ChangeLog, Commute, ControlDuty, Period, PeriodEvent
from duty.services import periods
from duty.services.publish import publish, unpublish, unpublish_info
from duty.services.roster import find_day
from duty.shifts import weekdays

S = Period.Status


def d(m, day):
    return date(2026, m, day)


def make_period(name, start, end, status, member):
    p = Period.objects.create(name=name, start_date=start, end_date=end, status=status)
    for x in weekdays(start, end):
        Commute.objects.create(period=p, date=x, member=member, shift="normal")
        ControlDuty.objects.create(period=p, date=x, slot=0, member=member)
    return p


def rows(p):
    c = sorted(Commute.objects.filter(period=p).values_list("date", "member_id", "shift"))
    k = sorted(ControlDuty.objects.filter(period=p).values_list("date", "member_id", "slot"))
    return c, k


# ── 배포 전 상태끼리 이동 ──

@pytest.mark.parametrize("to", [S.DRAFT, S.COLLECTING, S.CLOSED])
def test_move_from_generated_drops_control_duty_and_logs(make_member, admin_user, to):
    p = make_period("p", d(11, 9), d(11, 13), S.GENERATED, make_member("가"))
    p.seed = 3
    p.save()
    periods.move(p, to, by=admin_user)
    p.refresh_from_db()
    assert p.status == to and p.seed is None and p.generated_at is None
    assert not ControlDuty.objects.filter(period=p).exists()
    assert Commute.objects.filter(period=p).count() == 5  # 출근표는 그대로
    ev = PeriodEvent.objects.get(period=p)
    assert (ev.from_status, ev.to_status, ev.by) == (S.GENERATED, to, admin_user)


def test_move_draft_to_closed_directly(db):
    p = Period.objects.create(name="p", start_date=d(11, 9), end_date=d(11, 13))
    periods.move(p, S.CLOSED)
    assert Period.objects.get(pk=p.pk).status == S.CLOSED


@pytest.mark.parametrize("to", [S.GENERATED, S.PUBLISHED, "bogus"])
def test_move_rejects_targets_with_own_action(db, to):
    p = Period.objects.create(name="p", start_date=d(11, 9), end_date=d(11, 13), status=S.CLOSED)
    with pytest.raises(DutyError):
        periods.move(p, to)


def test_move_rejects_same_status_and_published(db):
    p = Period.objects.create(name="p", start_date=d(11, 9), end_date=d(11, 13), status=S.CLOSED)
    with pytest.raises(DutyError):
        periods.move(p, S.CLOSED)
    p.status = S.PUBLISHED
    p.save()
    with pytest.raises(DutyError):
        periods.move(p, S.DRAFT)  # 배포된 회차는 배포 취소로만
    assert not PeriodEvent.objects.exists()


def test_draft_shrink_drops_commutes_outside(make_member):
    p = make_period("p", d(11, 9), d(11, 20), S.DRAFT, make_member("가"))
    ControlDuty.objects.filter(period=p).delete()
    p.end_date = d(11, 13)
    periods.save_draft(p)
    assert sorted({x for x, *_ in rows(p)[0]}) == weekdays(d(11, 9), d(11, 13))


def test_create_and_generate_and_publish_are_logged(make_member, admin_user):
    p = periods.save_draft(Period(name="p", start_date=d(11, 9), end_date=d(11, 13)), by=admin_user)
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
    assert find_day(d(11, 19)).period_id == b.pk
    unpublish(b, by=admin_user)
    b.refresh_from_db()
    assert b.status == S.GENERATED and b.published_at is None and b.overwrite_from is None
    assert rows(a) == before_a and rows(b) == before_b
    assert find_day(d(11, 19)).period_id == a.pk
    assert find_day(d(12, 1)) is None
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
    changes.change_cell(admin_user, d(11, 19), "normal", na, other)
    info = unpublish_info(b)
    assert info.later_changes == 1 and info.restored_rows > 0 and info.blocker is None
    unpublish(b)
    assert Commute.objects.filter(period=b, date=d(11, 19), member=other).exists()  # 수정은 회차 데이터에 남는다
    assert ChangeLog.objects.filter(period=b).count() == 1


def test_unpublish_without_snapshot_refused(db):
    p = Period.objects.create(name="old", start_date=d(11, 9), end_date=d(11, 13), status=S.PUBLISHED)
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


def test_stale_collect_rejected(make_member, admin_user):
    from duty.services import collect
    m = make_member("가")
    p = Period.objects.create(name="p", start_date=d(11, 9), end_date=d(11, 9), status=S.COLLECTING)
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
    changes.change_cell(admin_user, d(11, 19), "normal", na, None)  # 제거
    assert find_day(d(11, 19)).cells["normal"].removed == [na.name]
    unpublish(b)
    Commute.objects.create(period=b, date=d(11, 19), member=na, shift="normal")  # 다시 입력
    publish(b, d(11, 16))
    cell = find_day(d(11, 19)).cells["normal"]
    assert cell.removed == [] and not cell.changed and cell.labels == [na.name]
    assert ChangeLog.objects.filter(period=b).count() == 1  # 기록은 남는다


def test_period_with_events_cannot_be_deleted(db):
    from django.db.models import ProtectedError
    p = periods.save_draft(Period(name="p", start_date=d(11, 9), end_date=d(11, 13)))
    with pytest.raises(ProtectedError):
        p.delete()


def test_unpublish_cutoff_ignores_clock(abc, admin_user):
    """배포 취소 이전 기록은 시각이 아니라 기록 번호로 가른다(시계가 뒤로 가도)."""
    from datetime import timedelta
    from duty.services import changes
    _, b, _ = abc
    publish(b, d(11, 16))
    m = Commute.objects.filter(period=b, date=d(11, 19)).first().member
    changes.change_cell(admin_user, d(11, 19), "normal", m, None)
    unpublish(b)
    Commute.objects.create(period=b, date=d(11, 19), member=m, shift="normal")
    publish(b, d(11, 16))
    changes.change_cell(admin_user, d(11, 20), "normal", m, None)  # 새 주기의 변경
    ChangeLog.objects.filter(date=d(11, 20)).update(at=ChangeLog.objects.get(date=d(11, 19)).at - timedelta(days=1))
    assert find_day(d(11, 20)).cells["normal"].removed == [m.name]  # 시각이 과거여도 보인다
    assert find_day(d(11, 19)).cells["normal"].removed == []
