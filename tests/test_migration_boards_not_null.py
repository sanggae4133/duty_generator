"""회차·부서의 근무표 NOT NULL(설계 10절 1단계 3번): 근무표 없는 회차는 IT 로 채우고, 근무표 없는 부서가 남아 있으면 멈춘다(0015 가 옮겼어야 한다). 이름은 모두 가상."""
from datetime import date

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from duty.models import Department, Period

BEFORE = [("duty", "0015_remove_department_managers")]
AFTER = [("duty", "0016_boards_not_null")]


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()  # 앞선 migrate 로 바뀐 적용 기록을 다시 읽는다
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_apps():
    apps = _migrate(BEFORE)
    yield apps
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())  # 다른 테스트를 위해 최신 스키마로


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_null_board_rows_become_it_and_reverse(old_apps):
    Board = old_apps.get_model("duty", "Board")
    Group = old_apps.get_model("auth", "Group")
    it = Board.objects.filter(code="it").first() or Board.objects.create(
        code="it", name="IT 당번표", input_mode="collect", admin_group=Group.objects.create(name="IT 근무표 관리"))
    pid = old_apps.get_model("duty", "Period").objects.create(
        name="근무표없음", start_date=date(2026, 12, 7), end_date=date(2026, 12, 11)).pk

    apps = _migrate(AFTER)
    assert apps.get_model("duty", "Period").objects.get(pk=pid).board_id == it.pk
    _migrate(BEFORE)  # 되돌리기: 다시 null 허용(채운 값은 그대로)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_null_board_department_stops(old_apps):
    Department = old_apps.get_model("duty", "Department")
    Department.objects.create(code="ZZ", name="무소속부서", shifts="normal")
    with pytest.raises(RuntimeError, match="ZZ"):  # 입력 그룹·담당자 복사는 0015 몫이라 여기서 조용히 채우지 않는다
        _migrate(AFTER)
    Department.objects.filter(code="ZZ").delete()  # fixture 가 최신 스키마로 다시 올릴 수 있게


def test_board_is_required(db):
    with pytest.raises(IntegrityError), transaction.atomic():
        Period.objects.create(name="근무표없음", start_date=date(2026, 12, 7), end_date=date(2026, 12, 11))
    with pytest.raises(IntegrityError), transaction.atomic():
        Department.objects.create(code="ZZ", name="무소속부서", shifts="normal")
