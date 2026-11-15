"""0022: IT 점심당번 정의·부서 점심 시각, 오늘 이후 배포됨·생성됨 회차의 새벽 근무자로 점심당번 채우기(설계 10절 2단계).
되돌리기는 없다(점심당번이 쓰인 DB 는 멈춘다). 이름은 모두 가상."""
from datetime import date, time

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0021_lunch")]
AFTER = [("duty", "0022_lunch_data")]
TODAY = date(2026, 11, 16)  # 월. 마이그레이션의 "오늘"


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_apps(monkeypatch):
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *a, **kw: TODAY)
    apps = _migrate(BEFORE)  # 테스트 DB 에는 점심당번 배정이 없어 내려갈 수 있다
    yield apps
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())  # 다른 테스트를 위해 최신 스키마로


def _world(apps):
    Board, Department, User = (apps.get_model("duty", n) for n in ("Board", "Department", "User"))
    Period, Commute = apps.get_model("duty", "Period"), apps.get_model("duty", "Commute")
    it = Board.objects.get(code="it")
    Department.objects.create(code="MEMS", name="매칭엔진실", shifts="dawn,normal", board=it)
    m = {n: User.objects.create(username=f"T{i}", name=n) for i, n in enumerate(["가", "나", "다", "라"])}

    def period(name, status, **kw):
        return Period.objects.create(board=it, name=name, start_date=date(2026, 11, 13), end_date=date(2026, 11, 20),
                                     status=status, **kw)

    pub, gen, closed = period("배포", "published", publish_undo=[]), period("생성", "generated"), period("마감", "closed")
    for p in (pub, gen, closed):
        Commute.objects.create(period=p, date=date(2026, 11, 13), member=m["가"], shift="dawn")  # 지난 금요일
        Commute.objects.create(period=p, date=TODAY, member=m["가"], shift="dawn")
        Commute.objects.create(period=p, date=TODAY, member=m["나"], shift="dawn", reason="휴가")
        Commute.objects.create(period=p, date=TODAY, member=m["다"], shift="normal")
    pub.publish_undo = [
        ["c", gen.pk, "2026-11-13", m["라"].pk, "dawn", ""],  # 지난 날
        ["c", gen.pk, "2026-11-17", m["라"].pk, "dawn"],  # 2단계 전 다섯 칸 행
        ["c", gen.pk, "2026-11-18", m["라"].pk, "dawn", "출장"],
        ["c", gen.pk, "2026-11-18", m["다"].pk, "normal", ""],
        ["a", gen.pk, "2026-11-18", m["다"].pk, "slot0"],
    ]
    pub.save()
    return it, m, pub, gen, closed


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_fills_it_lunch_from_dawn_workers(old_apps):
    it, m, pub, gen, closed = _world(old_apps)
    apps = _migrate(AFTER)
    BoardShift, Department = apps.get_model("duty", "BoardShift"), apps.get_model("duty", "Department")
    lunch = BoardShift.objects.get(board_id=it.pk, key="lunch")
    assert (lunch.name, lunch.start, lunch.end) == ("점심당번", None, None)
    assert Department.objects.filter(code="MEMS").values_list("lunch_start", "lunch_end").get() == (time(11, 30), time(12, 30))
    rows = apps.get_model("duty", "DutyAssignment").objects.filter(cell="lunch")
    # 오늘(포함) 이후, 배포됨·생성됨 회차, 새벽, 사유 없음만
    assert sorted(rows.values_list("period_id", "date", "member_id")) == sorted(
        [(pub.pk, TODAY, m["가"].pk), (gen.pk, TODAY, m["가"].pk)])
    assert not apps.get_model("duty", "ChangeLog").objects.exists()  # 기록·알림 없음
    undo = apps.get_model("duty", "Period").objects.get(pk=pub.pk).publish_undo
    assert undo[5:] == [["a", gen.pk, "2026-11-17", m["라"].pk, "lunch"]]  # 기존 행 뒤에 하나만


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_no_reverse_once_lunch_is_used(old_apps):
    _world(old_apps)
    _migrate(AFTER)
    with pytest.raises(RuntimeError, match="백업"):
        _migrate(BEFORE)


@pytest.mark.parametrize("where", ["boardshift", "department"])
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_no_reverse_when_other_board_uses_lunch(old_apps, where):
    """되돌리기는 IT 근무표의 점심당번 정의·IT 부서 시각만 지운다. 다른 근무표가 점심당번을 쓰면 멈추고 그대로 둔다."""
    apps = _migrate(AFTER)
    Board, BoardShift, Department = (apps.get_model("duty", n) for n in ("Board", "BoardShift", "Department"))
    group = apps.get_model("auth", "Group").objects.create(name="운영팀 관리자")
    ops = Board.objects.create(code="ops", name="운영팀", input_mode="direct", admin_group=group)
    if where == "boardshift":
        BoardShift.objects.create(board=ops, key="lunch", name="점심")
    else:
        Department.objects.create(code="OPS", name="운영실", shifts="dawn", board=ops,
                                  lunch_start=time(12), lunch_end=time(13))
    with pytest.raises(RuntimeError, match="백업"):
        _migrate(BEFORE)
    apps = _migrate(AFTER)
    BoardShift, Department = apps.get_model("duty", "BoardShift"), apps.get_model("duty", "Department")
    if where == "boardshift":
        assert BoardShift.objects.filter(board__code="ops", key="lunch").exists()
    else:
        assert Department.objects.filter(code="OPS", lunch_start=time(12)).exists()
