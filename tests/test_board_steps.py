"""근무표 단계 설정과 단계 규칙(근무표 통합 설계 5.1·5.2): 쿼리 없는 Board 메서드와, 서비스가 입력 방식 대신 그 규칙을 따르는지. 이름은 모두 가상."""
from datetime import date, time

import pytest
from django.db import IntegrityError, transaction

from duty.errors import DutyError
from duty.models import Board, BoardShift, Commute, Department, DutyAssignment, Period, User
from duty.services import boards, collect, periods, publish
from duty.services.generate import run_generation
from tests.it_defs import OPS_STEPS

S = Period.Status
D, C, X, G, P = S.DRAFT, S.COLLECTING, S.CLOSED, S.GENERATED, S.PUBLISHED

# (use_draft, use_close) → 켠 단계, 첫 단계, 생성 받는 상태, 기간 수정 상태, {상태: 옮기기 대상}
RULES = [
    ((True, True), [D, C, X, G, P], D, X, {D},
     {D: [C, X], C: [D, X], X: [D, C], G: [D, C, X], P: []}),          # IT
    ((False, False), [C, G, P], C, C, {D, C},
     {D: [C], C: [], X: [C], G: [C], P: []}),                          # 시장운영실(끈 단계에 남은 회차는 취합 중으로만)
    ((False, True), [C, X, G, P], C, X, {D, C},
     {D: [C, X], C: [X], X: [C], G: [C, X], P: []}),                   # 작성 중만 끔
    ((True, False), [D, C, G, P], D, C, {D},
     {D: [C], C: [D], X: [D, C], G: [D, C], P: []}),                   # 마감만 끔
]


@pytest.mark.parametrize("flags,steps,first,gen_from,editable,targets", RULES)
def test_step_rules(flags, steps, first, gen_from, editable, targets):
    b = Board(code="x", name="x", use_draft=flags[0], use_close=flags[1])
    assert b.steps() == steps and b.first_step() == first and b.generate_from() == gen_from
    assert b.editable() == editable
    assert {s: b.move_targets(s) for s in S.values} == targets


def test_default_names_are_status_labels():
    b = Board(code="x", name="x")
    assert [b.step_name(s) for s in S.values] == [label for _, label in S.choices]


def test_ops_names_keep_turned_off_steps():
    b = Board(code="x", name="x", **OPS_STEPS)
    assert [b.step_name(s) for s in S.values] == ["작성 중", "입력 중", "마감", "확정", "배포됨"]


def test_legacy_rule_is_close_off():
    assert boards.legacy_admin_entry(Board(use_close=False)) and not boards.legacy_admin_entry(Board())


@pytest.mark.parametrize("field", ["step_draft", "step_collecting", "step_closed", "step_generated", "step_published"])
def test_step_names_cannot_be_empty(db, field):
    with pytest.raises(IntegrityError), transaction.atomic():
        Board.objects.create(code="x", name="x", **{field: ""})


# ── 서비스가 단계 설정을 따른다(입력 방식이 아니라) ──

MON, FRI = date(2026, 11, 16), date(2026, 11, 20)


def board_with(use_draft, use_close, slot=True, **names):
    """입력 방식은 기본값(부서별 취합) 그대로 두고 단계만 고른 근무표. 근무조 하나 + 관제 하나(직원, slot=False 면 없음), 부서 둘."""
    b = Board.objects.create(code="stp", name="단계팀", use_draft=use_draft, use_close=use_close, **names)
    BoardShift.objects.create(board=b, key="dawn", name="이른", start=time(7), end=time(16))
    if slot:
        BoardShift.objects.create(board=b, key="slot0", name="점검", start=time(10), end=time(11),
                                  eligible_shifts=["dawn"], eligible_types=["직원"])
    for code in ("STA", "STB"):
        Department.objects.create(code=code, name=f"단계{code}", shifts="dawn", board=b)
    return b


def person(code):
    return User.objects.create_user(f"{code}{User.objects.count():03d}", password=None, name=f"가상{code}{User.objects.count()}",
                                    department=Department.objects.get(code=code), type="직원")


@pytest.mark.parametrize("flags,first", [((True, True), D), ((False, False), C), ((False, True), C), ((True, False), D)])
def test_new_period_starts_at_first_step(it_board, flags, first):
    p = periods.save_draft(Period(board=board_with(*flags), name="p", start_date=MON, end_date=FRI))
    assert p.status == first


def test_dates_editable_while_collecting_without_draft(it_board):
    p = Period.objects.create(board=board_with(False, True), name="p", start_date=MON, end_date=FRI, status=C)
    p.end_date = date(2026, 11, 18)
    periods.save_draft(p)
    assert Period.objects.get(pk=p.pk).end_date == date(2026, 11, 18)


@pytest.mark.parametrize("flags,ok,refused,msg", [
    ((False, True), X, C, "마감된 회차만 생성할 수 있습니다"),
    ((True, False), C, X, "입력 중인 회차만 확정할 수 있습니다"),  # 1단계: 마감을 안 쓰면 옛 직접 입력 문구
])
def test_generate_from_rule(it_board, flags, ok, refused, msg):
    b = board_with(*flags)
    bad = Period.objects.create(board=b, name="bad", start_date=MON, end_date=FRI, status=refused)
    with pytest.raises(DutyError, match=msg):
        run_generation(bad)
    good = Period.objects.create(board=b, name="good", start_date=date(2026, 11, 23), end_date=date(2026, 11, 23),
                                 status=ok)
    for code in ("STA", "STB"):
        Commute.objects.create(period=good, date=good.start_date, member=person(code), shift="dawn")
    run_generation(good, seed=1)
    assert Period.objects.get(pk=good.pk).status == G


@pytest.mark.parametrize("flags,status,to,msg", [  # 검사 순서: 배포됨 → 같은 상태 → move_targets(설계 6.1)
    ((False, True), G, D, "직접 입력 근무표는 입력 중으로만 옮길 수 있습니다."),  # 끈 단계로(1단계 글)
    ((True, True), D, G, "옮길 수 없는 상태입니다."),                            # MOVABLE 밖
    ((True, True), P, G, "배포된 회차는 배포 취소로만 되돌릴 수 있습니다."),     # 배포됨이 먼저(main 은 '옮길 수 없는')
])
def test_move_checks_in_order(it_board, flags, status, to, msg):
    p = Period.objects.create(board=board_with(*flags), name="p", start_date=MON, end_date=FRI, status=status)
    with pytest.raises(DutyError) as e:
        periods.move(p, to)
    assert str(e.value) == msg


def test_slots_skip_only_days_without_any_rows(it_board):
    """1단계: 관제는 출근 행이 하나도 없는 날만 뺀다. 한 부서만 빈 날(목·금)은 다른 부서 사람으로 채운다(경고는 그대로)."""
    b = board_with(False, False)
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    a, z = person("STA"), person("STB")
    for x in p.dates():
        Commute.objects.create(period=p, date=x, member=a, shift="dawn")
    for x in p.dates()[:3]:
        Commute.objects.create(period=p, date=x, member=z, shift="dawn")
    out = run_generation(p, seed=1)
    assert out.warnings[0] == "입력하지 않은 평일이 있습니다(그날은 근무자가 없습니다): 11/19, 11/20"
    assert sorted(DutyAssignment.objects.filter(period=p).values_list("date", flat=True)) == p.dates()


def test_names_come_from_board(it_board, admin_user):
    b = board_with(True, True, step_collecting="모으는 중")
    b.admin_group.user_set.add(admin_user)
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    assert p.status_label == "모으는 중"
    p.status = G
    p.save()
    with pytest.raises(DutyError, match="모으는 중인 회차가 아닙니다"):
        collect.apply_table(admin_user, p, Department.objects.get(code="STA"), {})


@pytest.mark.parametrize("flags,allowed", [((False, False), True), ((True, False), True), ((True, True), False)])
def test_fill_follows_legacy_rule(it_board, flags, allowed):
    """1단계: 채우기는 마감을 안 쓰는 근무표에서만(2단계에서 모든 근무표)."""
    b = board_with(*flags)
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    dept = Department.objects.get(code="STA")
    if allowed:
        assert collect.fill_week(p, dept, {}, MON, collect.FILL_1W) == {}
    else:
        with pytest.raises(DutyError, match="채우기는 직접 입력 근무표에서만 씁니다"):
            collect.fill_week(p, dept, {}, MON, collect.FILL_1W)


@pytest.mark.parametrize("flags,msg", [((False, False), "확정한 회차만"), ((True, True), "생성이 끝난 회차만")])
def test_publish_message_follows_legacy_rule(it_board, flags, msg):
    p = Period.objects.create(board=board_with(*flags), name="p", start_date=MON, end_date=FRI, status=C)
    with pytest.raises(DutyError, match=msg):
        publish.publish(p, MON)
