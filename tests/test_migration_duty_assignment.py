"""ControlDuty → DutyAssignment 데이터 이전(설계 10절 1단계, 12절 마이그레이션 테스트). 가상의 이름만 쓴다."""
from datetime import date, datetime, timezone

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from duty.models import Commute, DutyAssignment, Period
from duty.services.publish import unpublish

BEFORE = [("duty", "0012_dutyassignment")]
AFTER = [("duty", "0013_controlduty_to_assignment")]
D = date(2026, 11, 9)


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()  # 앞선 migrate 로 바뀐 적용 기록을 다시 읽는다
    executor.migrate(target)
    return executor.loader.project_state(target).apps


def _leaf():
    return MigrationExecutor(connection).loader.graph.leaf_nodes()


@pytest.fixture
def old_apps():
    apps = _migrate(BEFORE)
    yield apps
    _migrate(_leaf())  # 다른 테스트를 위해 최신 스키마로


def _seed(apps):
    """p: 배포됨(관제 slot0=가, slot9=나, publish_undo 에 q 의 c·k 행), q: 생성됨(publish_undo 없음)."""
    Group = apps.get_model("auth", "Group")
    Board = apps.get_model("duty", "Board")
    Period_ = apps.get_model("duty", "Period")
    User = apps.get_model("duty", "User")
    ControlDuty = apps.get_model("duty", "ControlDuty")
    # 마이그레이션 0011 이 만든 IT 근무표가 있으면 그것을, flush 된 DB 면 새로(이력 모델엔 Board.save 가 없어 그룹을 직접)
    board = Board.objects.filter(code="it").first() or Board.objects.create(
        code="it", name="IT 당번표", input_mode="collect", admin_group=Group.objects.create(name="이전 시험 관리"))
    a = User.objects.create(username="T001", name="가상가")
    b = User.objects.create(username="T002", name="가상나")
    q = Period_.objects.create(name="q", start_date=D, end_date=D, status="generated", board=board)
    p = Period_.objects.create(name="p", start_date=D, end_date=D, status="published", board=board,
                               published_at=datetime(2026, 11, 6, tzinfo=timezone.utc), publish_undo=[
        ["c", q.pk, "2026-11-09", a.pk, "normal"], ["k", q.pk, "2026-11-09", b.pk, 3]])
    ControlDuty.objects.create(period=p, date=D, slot=0, member=a)
    ControlDuty.objects.create(period=p, date=D, slot=9, member=b)
    return p.pk, q.pk, a.pk, b.pk


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_controlduty_to_assignment_and_back(old_apps):
    p, q, a, b = _seed(old_apps)

    apps = _migrate(AFTER)
    DA = apps.get_model("duty", "DutyAssignment")
    P = apps.get_model("duty", "Period")
    assert sorted(DA.objects.values_list("period_id", "date", "cell", "member_id")) == [
        (p, D, "slot0", a), (p, D, "slot9", b)]
    assert not apps.get_model("duty", "ControlDuty").objects.exists()
    assert P.objects.get(pk=p).publish_undo == [
        ["c", q, "2026-11-09", a, "normal"], ["a", q, "2026-11-09", b, "slot3"]]
    assert P.objects.get(pk=q).publish_undo is None

    apps = _migrate(BEFORE)  # 되돌리기
    CD = apps.get_model("duty", "ControlDuty")
    assert sorted(CD.objects.values_list("period_id", "date", "slot", "member_id")) == [
        (p, D, 0, a), (p, D, 9, b)]
    assert not apps.get_model("duty", "DutyAssignment").objects.exists()
    assert apps.get_model("duty", "Period").objects.get(pk=p).publish_undo == [
        ["c", q, "2026-11-09", a, "normal"], ["k", q, "2026-11-09", b, 3]]


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_unpublish_after_conversion_restores_assignment(old_apps):
    """옛 k 행이 a 행으로 바뀐 회차를 배포 취소하면 관제 칸이 되살아난다(설계 12절 '변환 뒤 배포 취소')."""
    p, q, a, b = _seed(old_apps)
    _migrate(_leaf())
    unpublish(Period.objects.get(pk=p))
    assert Commute.objects.filter(period_id=q, date=D, member_id=a, shift="normal").exists()
    assert DutyAssignment.objects.filter(period_id=q, date=D, cell="slot3", member_id=b).exists()
