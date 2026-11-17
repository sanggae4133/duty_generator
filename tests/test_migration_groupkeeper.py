"""0024: 그룹 관리자(GroupKeeper) 표 지우기(근무표 통합 설계 10.2). 거꾸로는 빈 표. 이름은 모두 가상."""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0023_board_steps")]
AFTER = [("duty", "0024_delete_groupkeeper")]


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_apps():
    yield _migrate(BEFORE)
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())  # 다른 테스트를 위해 최신 스키마로


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_groupkeeper_rows_go_and_reverse_gives_empty_table(old_apps):
    group = old_apps.get_model("duty", "Board").objects.get(code="it").admin_group
    user = old_apps.get_model("duty", "User").objects.create(username="keep01", name="가상관리")
    old_apps.get_model("duty", "GroupKeeper").objects.create(group_id=group.pk, user=user)
    apps = _migrate(AFTER)
    with pytest.raises(LookupError):
        apps.get_model("duty", "GroupKeeper")
    assert "duty_groupkeeper" not in connection.introspection.table_names()
    assert apps.get_model("duty", "User").objects.filter(username="keep01").exists()  # 사람·그룹은 그대로
    assert apps.get_model("auth", "Group").objects.filter(pk=group.pk).exists()
    back = _migrate(BEFORE)
    assert not back.get_model("duty", "GroupKeeper").objects.exists()
