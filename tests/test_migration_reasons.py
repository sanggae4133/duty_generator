"""0020 은 사유 칸(Commute.reason, ChangeLog.reason_before/after)을 빈 값으로 더한다(설계 10절 2단계).
이름 사전 검사는 0018 맨 앞(tests/test_migration_holidays.py). 이름은 모두 가상."""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0019_memo")]
AFTER = [("duty", "0020_reasons")]


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_apps():
    apps = _migrate(BEFORE)
    yield apps
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())  # 다른 테스트를 위해 최신 스키마로


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_adds_empty_reason(old_apps):
    old_apps.get_model("duty", "User").objects.create(username="T002", name="가상이(A)")
    apps = _migrate(AFTER)
    assert apps.get_model("duty", "User").objects.filter(name="가상이(A)").exists()
    assert {f.name for f in apps.get_model("duty", "Commute")._meta.fields} >= {"reason"}
    assert {f.name for f in apps.get_model("duty", "ChangeLog")._meta.fields} >= {"reason_before", "reason_after"}
