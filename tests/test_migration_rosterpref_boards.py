"""0025: 기억한 근무표 RosterPref.board → boards 목록(근무표 통합 설계 10.2, 5단계). 이름은 모두 가상."""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0024_delete_groupkeeper")]
AFTER = [("duty", "0025_rosterpref_boards")]


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_apps():
    yield _migrate(BEFORE)
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())  # 다른 테스트를 위해 최신 스키마로


def _ops(apps):
    group = apps.get_model("auth", "Group").objects.create(name="운영팀 근무표 관리")
    return apps.get_model("duty", "Board").objects.create(code="ops", name="운영팀", admin_group=group, use_draft=False,
                                                          use_close=False, step_collecting="입력 중", step_generated="확정")


def _user(apps, username):
    return apps.get_model("duty", "User").objects.create(username=username, name=f"가상{username}")


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_board_becomes_list_and_back(old_apps):
    ops = _ops(old_apps)
    Old = old_apps.get_model("duty", "RosterPref")
    a = Old.objects.create(user=_user(old_apps, "u1"), board=ops, depts=["OPS"], view="month")  # 남의 근무표를 기억
    b = Old.objects.create(user=_user(old_apps, "u2"))  # 내 근무표(기억 없음 = NULL)
    apps = _migrate(AFTER)
    New = apps.get_model("duty", "RosterPref")
    assert New.objects.get(pk=a.pk).boards == ["ops"] and New.objects.get(pk=b.pk).boards == []
    assert (New.objects.get(pk=a.pk).depts, New.objects.get(pk=a.pk).view) == (["OPS"], "month")  # 다른 값은 그대로
    assert "board" not in {f.name for f in New._meta.fields}
    back = _migrate(BEFORE)  # 하나짜리만 있으면 거꾸로 돈다
    Back = back.get_model("duty", "RosterPref")
    assert Back.objects.get(pk=a.pk).board_id == ops.pk and Back.objects.get(pk=b.pk).board_id is None


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_no_reverse_when_two_boards_remembered(old_apps):
    _ops(old_apps)
    apps = _migrate(AFTER)
    row = apps.get_model("duty", "RosterPref").objects.create(user=_user(apps, "u3"), boards=["it", "ops"])
    with pytest.raises(RuntimeError, match="백업"):
        _migrate(BEFORE)
    row.delete()  # 다른 테스트의 픽스처가 최신으로 다시 올라갈 수 있게
