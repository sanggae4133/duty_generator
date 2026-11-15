"""0015: managers M2M 을 지우기 전에, 0011 뒤 근무표 없이 생긴 부서를 IT 로 옮기고 담당자를 입력 그룹에 복사한다."""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0014_delete_controlduty")]
AFTER = [("duty", "0015_remove_department_managers")]


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
def test_null_board_department_moves_to_it_with_managers(old_apps):
    Board = old_apps.get_model("duty", "Board")
    Group = old_apps.get_model("auth", "Group")
    it = Board.objects.filter(code="it").first() or Board.objects.create(
        code="it", name="IT 당번표", input_mode="collect", admin_group=Group.objects.create(name="IT 근무표 관리"))
    mgr = old_apps.get_model("duty", "User").objects.create(username="MGR001", name="담당가")
    dept = old_apps.get_model("duty", "Department").objects.create(code="ZZ", name="무소속부서", shifts="normal")
    dept.managers.add(mgr)

    apps = _migrate(AFTER)
    d = apps.get_model("duty", "Department").objects.get(code="ZZ")
    assert d.board_id == it.pk and d.input_group.name == "무소속부서 출근표 입력"
    assert list(d.input_group.user_set.values_list("username", flat=True)) == ["MGR001"]
    _migrate(BEFORE)  # 되돌리기: M2M 이 다시 생긴다(채운 board·입력 그룹은 그대로)
