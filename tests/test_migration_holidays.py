"""0018: 이름이 (휴가)·(출장)·(교육)으로 끝나는 계정이 있으면 아무것도 적용하지 않고 멈춘다.
기존 회차는 휴장일 건너뛰기 거짓, 휴장일 표는 비어 있다(설계 10절 2단계). 이름은 모두 가상."""
from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0017_alarmrule_board_rules")]
AFTER = [("duty", "0018_holidays")]


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
def test_existing_periods_do_not_skip_holidays(old_apps):
    Board = old_apps.get_model("duty", "Board")
    Group = old_apps.get_model("auth", "Group")
    it = Board.objects.filter(code="it").first() or Board.objects.create(
        code="it", name="IT 당번표", input_mode="collect", admin_group=Group.objects.create(name="IT 근무표 관리"))
    pid = old_apps.get_model("duty", "Period").objects.create(
        board=it, name="옛 회차", start_date=date(2026, 12, 7), end_date=date(2026, 12, 11)).pk

    apps = _migrate(AFTER)
    Period = apps.get_model("duty", "Period")
    assert Period.objects.get(pk=pid).skip_holidays is False
    assert Period.objects.create(board_id=it.pk, name="새 회차", start_date=date(2026, 12, 14),
                                 end_date=date(2026, 12, 18)).skip_holidays is True
    assert not apps.get_model("duty", "Holiday").objects.exists()  # 마이그레이션은 채우지 않는다


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_stops_before_anything_when_name_ends_with_reason(old_apps):
    User = old_apps.get_model("duty", "User")
    u = User.objects.create(username="T001", name="가상일(휴가)")
    User.objects.create(username="T002", name="가상이(A)")  # 괄호가 있어도 사유가 아니면 통과
    with pytest.raises(RuntimeError, match=r"가상일\(휴가\)") as e:
        _migrate(AFTER)
    assert "가상이" not in str(e.value)
    with connection.cursor() as c:  # 0018 이 통째로 되돌려져 표도 칸도 없다
        assert "duty_holiday" not in connection.introspection.table_names(c)
    User.objects.filter(pk=u.pk).delete()  # 정리해야 픽스처가 최신 스키마로 올릴 수 있다


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_reverse_refuses_when_holidays_exist(old_apps):
    """2단계부터 되돌리기는 백업 복원으로만(설계 10절): 휴장일이 있으면 0017로 되돌리지 않고 멈춘다."""
    apps = _migrate(AFTER)
    apps.get_model("duty", "Holiday").objects.create(date=date(2026, 12, 25), name="가상 휴일")
    with pytest.raises(RuntimeError, match="백업"):
        _migrate(BEFORE)
    assert MigrationExecutor(connection).loader.applied_migrations.get(("duty", "0018_holidays"))
