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


@pytest.fixture
def at_0020():
    apps = _migrate(AFTER)
    yield apps
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())


@pytest.mark.parametrize("where", ["commute", "changelog"])
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_reverse_refuses_when_reasons_exist(at_0020, where):
    """사유가 있으면 되돌리지 않는다(Django 기본 되돌리기는 사유 칸을 말없이 지운다)."""
    from datetime import date
    Board, Period = at_0020.get_model("duty", "Board"), at_0020.get_model("duty", "Period")
    Commute, ChangeLog = at_0020.get_model("duty", "Commute"), at_0020.get_model("duty", "ChangeLog")
    member = at_0020.get_model("duty", "User").objects.create(username="T003", name="가상삼(A)")
    board = Board.objects.filter(code="it").first()
    if board is None:
        board = Board.objects.create(code="it", name="IT 당번표", input_mode="collect",
                                     admin_group=at_0020.get_model("auth", "Group").objects.create(name="IT 근무표 관리"))
    period = Period.objects.create(board=board, name="가상 회차", start_date=date(2026, 12, 1), end_date=date(2026, 12, 31))
    if where == "commute":
        Commute.objects.create(period=period, date=date(2026, 12, 7), member=member, shift="normal", reason="휴가")
    else:
        ChangeLog.objects.create(period=period, date=date(2026, 12, 7), cell="normal", before=member, after=member,
                                 reason_after="출장")
    with pytest.raises(RuntimeError, match="백업"):
        _migrate(BEFORE)
    assert {f.name for f in at_0020.get_model("duty", "Commute")._meta.fields} >= {"reason"}
    ChangeLog.objects.all().delete()  # 정리해야 픽스처가 최신 스키마로 올릴 수 있다
    Commute.objects.all().delete()
    Period.objects.all().delete()


def _undo_period(apps, undo):
    from datetime import date
    Board, Period = apps.get_model("duty", "Board"), apps.get_model("duty", "Period")
    board = Board.objects.filter(code="it").first()
    if board is None:
        board = Board.objects.create(code="it", name="IT 당번표", input_mode="collect",
                                     admin_group=apps.get_model("auth", "Group").objects.create(name="IT 근무표 관리"))
    return Period.objects.create(board=board, name="가상 회차", start_date=date(2026, 12, 1), end_date=date(2026, 12, 31),
                                 status="published", publish_undo=undo)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_reverse_refuses_when_undo_has_reason(at_0020):
    """배포 취소 정보(publish_undo)의 c 행 여섯째 칸에 사유가 있어도 되돌리지 않는다."""
    p = _undo_period(at_0020, [["c", 1, "2026-12-07", 1, "normal", "휴가"]])
    with pytest.raises(RuntimeError, match="백업"):
        _migrate(BEFORE)
    p.delete()


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_reverse_strips_empty_reason_from_undo(at_0020):
    """사유 없는 여섯째 칸은 떼어 옛 코드가 읽는 다섯 칸으로 되돌린다."""
    pk = _undo_period(at_0020, [["c", 1, "2026-12-07", 1, "normal", ""], ["c", 1, "2026-12-08", 1, "dawn"],
                                ["a", 1, "2026-12-07", 1, "slot0"]]).pk
    old = _migrate(BEFORE)
    assert old.get_model("duty", "Period").objects.get(pk=pk).publish_undo == [
        ["c", 1, "2026-12-07", 1, "normal"], ["c", 1, "2026-12-08", 1, "dawn"], ["a", 1, "2026-12-07", 1, "slot0"]]
    old.get_model("duty", "Period").objects.all().delete()
