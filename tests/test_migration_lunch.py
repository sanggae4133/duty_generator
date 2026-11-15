"""0022: IT 점심당번 정의·부서 점심 시각, 오늘 이후 배포됨·생성됨 회차의 새벽 근무자로 점심당번 채우기(설계 10절 2단계).
되돌리기는 없다(점심당번이 쓰인 DB 는 멈춘다). 이름은 모두 가상."""
from datetime import date, time

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

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


@pytest.fixture
def at_0020():
    apps = _migrate([("duty", "0020_reasons")])
    yield apps
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_0021_keeps_rows_and_adds_constraints(at_0020):
    """0020 → 0021: 기존 근무 정의·관제 배정·기록·발송 기록·부서는 그대로, 새 제약(점심당번 시각 없음·부서 점심 시각 짝)이 걸린다."""
    from django.db import IntegrityError, transaction
    a = at_0020
    group = a.get_model("auth", "Group").objects.create(name="운영팀 관리자")
    ops = a.get_model("duty", "Board").objects.create(code="ops", name="운영팀", input_mode="direct", admin_group=group)
    a.get_model("duty", "BoardShift").objects.create(board=ops, key="dawn", name="오전", start=time(7, 30), end=time(16, 30))
    a.get_model("duty", "Department").objects.create(code="OPS", name="운영실", shifts="dawn", board=ops)
    member = a.get_model("duty", "User").objects.create(username="T9", name="가상구")
    period = a.get_model("duty", "Period").objects.create(board=ops, name="가상 회차", start_date=TODAY, end_date=TODAY)
    a.get_model("duty", "DutyAssignment").objects.create(period=period, date=TODAY, member=member, cell="slot0")
    a.get_model("duty", "ChangeLog").objects.create(period=period, date=TODAY, cell="dawn", after=member)
    rule = a.get_model("duty", "AlarmRule").objects.create(user=member, kind="report", timing="days", offset=1,
                                                           at_minute=18 * 60, telegram=True, board=ops)
    a.get_model("duty", "AlarmDelivery").objects.create(rule=rule, date=TODAY, cell="report", channel="telegram",
                                                        destination="1", status="sent", content_hash="h")

    apps = _migrate(BEFORE)
    BoardShift, Department = apps.get_model("duty", "BoardShift"), apps.get_model("duty", "Department")
    DutyAssignment = apps.get_model("duty", "DutyAssignment")
    assert BoardShift.objects.filter(board__code="ops").values_list("key", "start").get() == ("dawn", time(7, 30))
    assert Department.objects.filter(code="OPS").values_list("shifts", "lunch_start", "lunch_end").get() == ("dawn", None, None)
    assert DutyAssignment.objects.filter(period__board__code="ops").values_list("cell", flat=True).get() == "slot0"
    assert apps.get_model("duty", "ChangeLog").objects.filter(period__board__code="ops", cell="dawn").count() == 1
    assert apps.get_model("duty", "AlarmDelivery").objects.filter(rule__board__code="ops", cell="report").count() == 1
    ops = apps.get_model("duty", "Board").objects.get(code="ops")
    for bad in (lambda: BoardShift.objects.create(board=ops, key="lunch", name="점심", start=time(11, 30), end=time(12, 30)),
                lambda: BoardShift.objects.create(board=ops, key="normal", name="주간"),  # 근무조는 시각 필수 그대로
                lambda: Department.objects.create(code="OPS2", name="운영2실", shifts="dawn", board=ops, lunch_start=time(12)),
                lambda: Department.objects.create(code="OPS3", name="운영3실", shifts="dawn", board=ops,
                                                  lunch_start=time(13), lunch_end=time(12)),
                lambda: DutyAssignment.objects.create(period_id=period.pk, date=TODAY, member_id=member.pk, cell="dawn")):
        with pytest.raises(IntegrityError), transaction.atomic():
            bad()
    BoardShift.objects.create(board=ops, key="lunch", name="점심")  # 점심당번은 시각 없이
    Department.objects.filter(code="OPS").update(lunch_start=time(12), lunch_end=time(13))
    DutyAssignment.objects.create(period_id=period.pk, date=TODAY, member_id=member.pk, cell="lunch")


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_unpublish_after_fill_restores_commutes_and_lunch(old_apps, fixed_today):
    """겹쳐 배포한 상태(나중 배포가 앞 회차의 날짜를 덮어씀)에서 0022 를 돌린 뒤 나중 회차를 배포 취소하면
    앞 회차의 근무조와 점심당번이 함께 되살아난다(다섯 칸 옛 c 행·여섯 칸 c 행 모두)."""
    a = old_apps
    Board, Period, Commute = (a.get_model("duty", n) for n in ("Board", "Period", "Commute"))
    PeriodEvent, DutyAssignment = a.get_model("duty", "PeriodEvent"), a.get_model("duty", "DutyAssignment")
    it = Board.objects.get(code="it")
    m = {n: a.get_model("duty", "User").objects.create(username=f"T{i}", name=n) for i, n in enumerate(["가", "나"])}
    first = Period.objects.create(board=it, name="앞", start_date=date(2026, 11, 13), end_date=date(2026, 11, 30),
                                  status="published", overwrite_from=date(2026, 11, 13), publish_undo=[],
                                  published_at=timezone.now())
    PeriodEvent.objects.create(period=first, from_status="generated", to_status="published")
    Commute.objects.create(period=first, date=TODAY, member=m["가"], shift="dawn")  # 덮어쓰기 전 날은 남는다
    later = Period.objects.create(board=it, name="뒤", start_date=date(2026, 11, 17), end_date=date(2026, 11, 30),
                                  status="published", overwrite_from=date(2026, 11, 17), published_at=timezone.now(), publish_undo=[
                                      ["c", first.pk, "2026-11-17", m["가"].pk, "dawn"],  # 2단계 전 다섯 칸 행
                                      ["c", first.pk, "2026-11-18", m["가"].pk, "dawn", ""],
                                      ["c", first.pk, "2026-11-18", m["나"].pk, "normal", ""],
                                      ["a", first.pk, "2026-11-18", m["나"].pk, "slot0"],
                                  ])
    PeriodEvent.objects.create(period=later, from_status="generated", to_status="published")
    Commute.objects.create(period=later, date=date(2026, 11, 17), member=m["나"], shift="dawn")
    _migrate(AFTER)
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    from duty import models
    from duty.services import publish
    fixed_today(TODAY)
    publish.unpublish(models.Period.objects.get(pk=later.pk))
    assert sorted(models.Commute.objects.filter(period_id=first.pk).values_list("date", "member_id", "shift", "reason")) == [
        (TODAY, m["가"].pk, "dawn", ""), (date(2026, 11, 17), m["가"].pk, "dawn", ""),
        (date(2026, 11, 18), m["가"].pk, "dawn", ""), (date(2026, 11, 18), m["나"].pk, "normal", "")]
    assert sorted(models.DutyAssignment.objects.filter(period_id=first.pk).values_list("date", "member_id", "cell")) == [
        (TODAY, m["가"].pk, "lunch"), (date(2026, 11, 17), m["가"].pk, "lunch"),
        (date(2026, 11, 18), m["가"].pk, "lunch"), (date(2026, 11, 18), m["나"].pk, "slot0")]
    assert models.DutyAssignment.objects.filter(period_id=later.pk).values_list("date", "member_id", "cell").get() == (
        date(2026, 11, 17), m["나"].pk, "lunch")
    assert models.Period.objects.get(pk=later.pk).status == "generated"
