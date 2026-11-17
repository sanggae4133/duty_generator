"""0023: 입력 방식(input_mode) → 단계 설정(근무표 통합 설계 10.2). 이름은 모두 가상."""
from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0022_lunch_data")]
AFTER = [("duty", "0023_board_steps")]
STEPS = ("use_draft", "use_close", "step_draft", "step_collecting", "step_closed", "step_generated", "step_published")
IT = (True, True, "작성 중", "취합 중", "마감", "생성됨", "배포됨")
OPS = (False, False, "작성 중", "입력 중", "마감", "확정", "배포됨")


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_apps():
    apps = _migrate(BEFORE)  # 마이그레이션이 만든 IT 근무표만 있어 내려갈 수 있다
    yield apps
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())  # 다른 테스트를 위해 최신 스키마로


def _ops(apps):
    group = apps.get_model("auth", "Group").objects.create(name="운영팀 근무표 관리")
    return apps.get_model("duty", "Board").objects.create(code="ops", name="운영팀", input_mode="direct", admin_group=group)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_input_mode_becomes_steps(old_apps):
    ops = _ops(old_apps)
    dept = old_apps.get_model("duty", "Department").objects.create(code="OPS", name="운영", shifts="dawn", board=ops)
    Period = old_apps.get_model("duty", "Period")
    for st in ("draft", "collecting", "closed", "generated", "published"):
        Period.objects.create(board=ops, name=st, start_date=date(2026, 11, 16), end_date=date(2026, 11, 20), status=st)
    apps = _migrate(AFTER)
    Board = apps.get_model("duty", "Board")
    assert Board.objects.filter(code="it").values_list(*STEPS).get() == IT
    assert Board.objects.filter(code="ops").values_list(*STEPS).get() == OPS
    assert sorted(apps.get_model("duty", "Period").objects.filter(board__code="ops").values_list("name", "status")) == sorted(
        (st, st) for st in ("draft", "collecting", "closed", "generated", "published"))  # 회차 상태는 그대로
    assert apps.get_model("duty", "Department").objects.get(pk=dept.pk).input_group_id is None  # 그룹을 만들지 않는다
