"""0019: 메모가 있으면 되돌리지 않는다(2단계 되돌리기는 백업 복원으로만, 설계 10절). 이름은 모두 가상."""
from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0018_holidays")]
AFTER = [("duty", "0019_memo")]


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def at_0019():
    apps = _migrate(AFTER)
    yield apps
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_reverse_refuses_when_memos_exist(at_0019):
    Board = at_0019.get_model("duty", "Board")
    Memo = at_0019.get_model("duty", "Memo")
    it = Board.objects.get(code="it") if Board.objects.filter(code="it").exists() else None
    if it is None:
        Group = at_0019.get_model("auth", "Group")
        it = Board.objects.create(code="it", name="IT 당번표", input_mode="collect",
                                  admin_group=Group.objects.create(name="IT 근무표 관리"))
    Memo.objects.create(board=it, scope="day", date=date(2026, 12, 7), text="가상 행사")
    with pytest.raises(RuntimeError, match="백업"):
        _migrate(BEFORE)
    assert at_0019.get_model("duty", "Memo").objects.count() == 1
    Memo.objects.all().delete()  # 정리해야 픽스처가 최신 스키마로 올릴 수 있다
