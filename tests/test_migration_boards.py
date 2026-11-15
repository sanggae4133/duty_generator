"""1단계 마이그레이션(0010 스키마 + 0011 데이터)을 0009 상태의 가짜 데이터로 올리고 되돌린다."""
from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0009_roster_history")]
AFTER = [("duty", "0011_boards_data")]


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


def _seed(apps):
    Department = apps.get_model("duty", "Department")
    User = apps.get_model("duty", "User")
    Period = apps.get_model("duty", "Period")
    AlarmRule = apps.get_model("duty", "AlarmRule")
    mems = Department.objects.create(code="MEMS", name="가부서", shifts="dawn,normal,dinner,night")
    ui = Department.objects.create(code="UI", name="나부서", shifts="normal,dinner,night")
    extra = Department.objects.create(code="ZZ", name="다부서", shifts="normal")
    mgr = User.objects.create(username="MEMS001", name="담당가", department=mems, type="개발자")
    staff = User.objects.create(username="adm", name="관리가", is_staff=True)
    su = User.objects.create(username="root", name="최고가", is_staff=True, is_superuser=True)
    mems.managers.add(mgr)
    pub = Period.objects.create(name="배포", start_date=date(2026, 11, 2), end_date=date(2026, 11, 13), status="published")
    pub_s = Period.objects.create(name="배포S", start_date=date(2026, 11, 16), end_date=date(2026, 11, 27),
                                  status="published", overwrite_from=date(2026, 11, 18))
    draft = Period.objects.create(name="작성", start_date=date(2026, 11, 30), end_date=date(2026, 12, 11))
    rep = AlarmRule.objects.create(user=staff, kind="report", timing="days", offset=1, at_minute=600, telegram=True,
                                   depts=["MEMS"])
    per = AlarmRule.objects.create(user=mgr, kind="personal", timing="days", offset=1, at_minute=600, telegram=True)
    return dict(mems=mems.pk, ui=ui.pk, extra=extra.pk, mgr=mgr.pk, staff=staff.pk, su=su.pk,
                pub=pub.pk, pub_s=pub_s.pk, draft=draft.pk, rep=rep.pk, per=per.pk)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_forward_builds_it_board_and_groups(old_apps):
    ids = _seed(old_apps)
    apps = _migrate(AFTER)
    Board = apps.get_model("duty", "Board")
    Department = apps.get_model("duty", "Department")
    Period = apps.get_model("duty", "Period")
    AlarmRule = apps.get_model("duty", "AlarmRule")
    GroupKeeper = apps.get_model("duty", "GroupKeeper")
    Group = apps.get_model("auth", "Group")

    it = Board.objects.get(code="it")
    assert (it.name, it.input_mode, it.admin_group.name) == ("IT 당번표", "collect", "IT 근무표 관리")
    rows = {s.key: s for s in it.shifts.all()}
    assert len(rows) == 14
    assert (rows["dawn"].name, str(rows["dawn"].start), str(rows["dawn"].end)) == ("새벽", "06:30:00", "15:30:00")
    assert (rows["slot0"].name, rows["slot0"].eligible_shifts, rows["slot0"].eligible_types) == ("08:30~09:30", ["normal"], ["개발자"])
    assert rows["slot9"].eligible_shifts == ["dinner"] and rows["slot4"].eligible_shifts == ["normal", "dinner"]
    assert {k for k, s in rows.items() if s.default_alarm} == {"dawn", "dinner", "night"}

    depts = {d.code: d for d in Department.objects.all()}
    assert {d.board_id for d in depts.values()} == {it.id}
    assert (depts["MEMS"].order, depts["UI"].order, depts["ZZ"].order) == (0, 3, 99)
    assert depts["MEMS"].input_group.name == "가부서 출근표 입력"
    assert list(depts["MEMS"].input_group.user_set.values_list("pk", flat=True)) == [ids["mgr"]]
    assert not depts["UI"].input_group.user_set.exists()

    assert set(it.admin_group.user_set.values_list("pk", flat=True)) == {ids["staff"], ids["su"]}
    created = {it.admin_group_id, *(d.input_group_id for d in depts.values())}
    assert set(GroupKeeper.objects.values_list("group_id", flat=True)) == created
    assert set(GroupKeeper.objects.values_list("user_id", flat=True)) == {ids["su"]}
    assert Group.objects.count() == 4

    periods = {p.pk: p for p in Period.objects.all()}
    assert {p.board_id for p in periods.values()} == {it.id}
    assert periods[ids["pub"]].overwrite_from == date(2026, 11, 2)
    assert periods[ids["pub_s"]].overwrite_from == date(2026, 11, 18)
    assert periods[ids["draft"]].overwrite_from is None
    assert AlarmRule.objects.get(pk=ids["rep"]).board_id == it.id
    assert AlarmRule.objects.get(pk=ids["rep"]).depts == ["MEMS"]
    assert AlarmRule.objects.get(pk=ids["per"]).board_id is None


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_backward_restores_managers_and_removes_boards(old_apps):
    ids = _seed(old_apps)
    _migrate(AFTER)
    apps = _migrate(BEFORE)
    Department = apps.get_model("duty", "Department")
    Group = apps.get_model("auth", "Group")
    mems = Department.objects.get(pk=ids["mems"])
    assert list(mems.managers.values_list("pk", flat=True)) == [ids["mgr"]]
    assert not Department.objects.get(pk=ids["ui"]).managers.exists()
    assert not Group.objects.exists()


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_forward_stops_on_group_name_clash(old_apps):
    _seed(old_apps)
    clash = old_apps.get_model("auth", "Group").objects.create(name="가부서 출근표 입력")
    with pytest.raises(RuntimeError, match="가부서 출근표 입력"):
        _migrate(AFTER)
    clash.delete()  # 뒷정리(최신으로 올리기)가 같은 이유로 멈추지 않게
