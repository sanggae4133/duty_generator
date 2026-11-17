"""근무표 단계 설정과 단계 규칙(근무표 통합 설계 5.1·5.2): 쿼리 없는 Board 메서드와, 서비스가 입력 방식 대신 그 규칙을 따르는지. 이름은 모두 가상."""
from datetime import date, time

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from duty.errors import DutyError
from duty.models import Board, BoardShift, Commute, Department, DutyAssignment, Period, PeriodEvent, User
from duty.services import boards, collect, periods, publish
from duty.services.generate import run_generation
from duty.shifts import day_spans, josa
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
    ((False, True), X, C, "'마감'인 회차만 장중관제 생성할 수 있습니다"),
    ((True, False), C, X, "'취합 중'인 회차만 장중관제 생성할 수 있습니다"),
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
    ((False, True), G, D, "'취합 중·마감'(으)로만 옮길 수 있습니다."),  # 끈 단계로: 켠 단계 이름만
    ((True, True), D, G, "옮길 수 없는 상태입니다."),                            # MOVABLE 밖
    ((True, True), P, G, "배포된 회차는 배포 취소로만 되돌릴 수 있습니다."),     # 배포됨이 먼저(main 은 '옮길 수 없는')
])
def test_move_checks_in_order(it_board, flags, status, to, msg):
    p = Period.objects.create(board=board_with(*flags), name="p", start_date=MON, end_date=FRI, status=status)
    with pytest.raises(DutyError) as e:
        periods.move(p, to)
    assert str(e.value) == msg


def test_slots_skip_only_days_without_any_rows(it_board):
    """관제는 출근 행이 하나도 없는 날만 뺀다. 한 부서만 빈 날(목·금)은 다른 부서 사람으로 채운다(경고는 부서별)."""
    b = board_with(False, False)
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    a, z = person("STA"), person("STB")
    for x in p.dates():
        Commute.objects.create(period=p, date=x, member=a, shift="dawn")
    for x in p.dates()[:3]:
        Commute.objects.create(period=p, date=x, member=z, shift="dawn")
    out = run_generation(p, seed=1)
    assert out.warnings[0] == "출근표가 비어 있는 날이 있습니다: 단계STB 2일(11/19~11/20). 그날 그 부서는 근무자가 없습니다."
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


def test_messages_use_step_names(it_board):
    """오류 글은 그 근무표의 단계 이름을 쓴다(근무표 통합 2단계)."""
    b = board_with(True, True, step_draft="준비", step_generated="만듦")
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    with pytest.raises(DutyError, match="'만듦'인 회차만 배포할 수 있습니다"):
        publish.publish(p, MON)
    with pytest.raises(DutyError, match="기간은 '준비' 단계에서만 고칠 수 있습니다"):
        periods.save_draft(p)


def test_day_spans():
    """긴 날짜 목록은 이어진 평일끼리 묶는다(금 → 월도 이어진 것으로)."""
    days = [date(2026, 11, d) for d in (16, 17, 18, 19, 20, 23, 25)]
    assert day_spans(days) == "11/16~11/23, 11/25" and day_spans([MON]) == "11/16" and day_spans([]) == ""


# ── 화면: 버튼 글자·생성 방식 문장·갈래가 단계 설정에서 나온다 ──

def test_buttons_from_step_names():
    assert Board(code="x", name="x").step_buttons(True) == {
        "open": "취합 열기", "close": "취합 마감", "generate": "장중관제 생성", "regenerate": "재생성", "undo": ""}
    assert Board(code="x", name="x", **OPS_STEPS).step_buttons(False) == {
        "open": "입력 열기", "close": "입력 마감", "generate": "확정", "regenerate": "", "undo": "확정 취소"}
    assert Board(code="x", name="x", step_collecting="접수 중", step_closed="종료").step_buttons(False)["close"] == "접수 종료"


def test_buttons_use_whole_name_when_it_cannot_be_cut():
    """취합 중 이름이 ' 중'으로 끝나지 않으면 열기·마감은 이름 전체 꼴, 생성은 끝의 '됨'만 뗀다(설계 5.4)."""
    b = Board(code="x", name="x", step_collecting="작성", step_generated="완료됨")
    assert {k: b.step_buttons(False)[k] for k in ("open", "close", "generate")} == {
        "open": "'작성'(으)로", "close": "'마감'(으)로", "generate": "완료"}


def test_josa():
    assert [josa("확정", "은/는"), josa("배포", "은/는"), josa("개발자", "을/를"), josa("직원", "을/를")] == ["은", "는", "를", "을"]
    assert [josa("입력 중", "으로/로"), josa("배포", "으로/로"), josa("마감 날", "으로/로"), josa("A", "으로/로")] == [
        "으로", "로", "로", "(으)로"]


@pytest.fixture
def stp(it_board, admin_user, client):
    """입력 방식은 부서별 취합 그대로, 작성 중·마감을 끄고 이름만 입력 중·확정으로 바꾼 근무표(관제 없음: 시장운영실 모양)."""
    b = board_with(False, False, slot=False, step_collecting="입력 중", step_generated="확정")
    b.admin_group.user_set.add(admin_user)
    client.force_login(admin_user)
    return b, client


def test_period_page_follows_steps(stp):
    b, client = stp
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    Commute.objects.create(period=p, date=MON, member=person("STA"), shift="dawn")
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert body.index(">입력 중<") < body.index(">확정<") < body.index(">배포됨<") and ">마감<" not in body
    assert f'href="/collect/{p.pk}/STA/">표 입력 · 단계STA</a>' in body and ">확정</button>" in body
    assert "확정할까요? 확정하면 배포할 수 있고, 표를 고치려면 [확정 취소]를 누릅니다." in body
    assert "⚠ 아직 입력하지 않은 평일: 11/16, 11/17, 11/18, 11/19, 11/20. 확정은 할 수 있지만" in body  # 단계STB 가 다 비었다
    assert "부서별 입력 현황" not in body and 'name="start_date"' in body and "생성 방식" not in body
    p.status = G
    p.save()
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert ">확정 취소</button>" in body and "다른 상태로 옮기기" not in body and "재생성" not in body
    assert "확정을 취소하고 입력 중으로 돌아갈까요? 출근표는 그대로 남습니다." in body


def test_period_page_with_draft_off_and_close_on(it_board, admin_user, client):
    b = board_with(False, True)
    b.admin_group.user_set.add(admin_user)
    client.force_login(admin_user)
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=D)  # 끈 단계에 남은 회차
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert "취합 열기" not in body and '<option value="collecting">' in body and '<option value="closed">' in body
    assert '<option value="draft">' not in body
    p.status = C
    p.save()
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert ">취합 마감</button>" in body and 'name="start_date"' in body and "부서별 입력 현황" in body
    p.status = X
    p.save()
    assert ">장중관제 생성</button>" in client.get(f"/periods/{p.pk}/").content.decode()


def test_renamed_steps_rename_buttons(it_board, admin_user, client):
    b = board_with(True, True, step_collecting="접수 중", step_closed="종료")
    b.admin_group.user_set.add(admin_user)
    client.force_login(admin_user)
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=D)
    assert ">접수 열기</button>" in client.get(f"/periods/{p.pk}/").content.decode()
    p.status = C
    p.save()
    assert ">접수 종료</button>" in client.get(f"/periods/{p.pk}/").content.decode()


def test_input_table_and_help_follow_legacy_rule(stp):
    b, client = stp
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    body = client.get(f"/collect/{p.pk}/STA/").content.decode()
    assert "지난주와 같게" in body and "CSV 올리기 (표 전체 교체)" in body and f'href="/periods/{p.pk}/"' in body
    assert "직접 입력 근무표 운영" in client.get("/help/").content.decode()


def test_legacy_board_with_slot_defs_looks_like_main(stp):
    """1단계: 마감을 안 쓰는 근무표는 관제 정의가 켜져 있어도 main 처럼 [확정]·[확정 취소], 생성 방식·재생성·배정 횟수 표 없음
    (임시 기준으로 고른다. 2단계에서 관제 정의라는 데이터 기준으로 바꾼다)."""
    b, client = stp
    BoardShift.objects.create(board=b, key="slot0", name="점검", start=time(10), end=time(11),
                              eligible_shifts=["dawn"], eligible_types=["직원"])
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert ">확정</button>" in body and "생성 방식" not in body
    p.status = G
    p.save()
    a = person("STA")
    Commute.objects.create(period=p, date=MON, member=a, shift="dawn")
    DutyAssignment.objects.create(period=p, date=MON, cell="slot0", member=a)
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert ">확정 취소</button>" in body and "재생성" not in body and "장중관제 배정 횟수" not in body


def test_step_names_are_escaped_in_confirm(stp):
    """확인창(인라인 JS) 안의 단계 이름 글은 escapejs 로 넣는다: 따옴표·역슬래시가 든 이름도 스크립트를 깨지 않는다."""
    b, client = stp
    Board.objects.filter(pk=b.pk).update(step_generated="확'정\\됨")
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert ("confirm('확\\u0027정\\u005C할까요? 확\\u0027정\\u005C하면 배포할 수 있고, "
            "표를 고치려면 [확\\u0027정\\u005C 취소]를 누릅니다.')") in body
    p.status = G
    p.save()
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert "confirm('확\\u0027정\\u005C을(를) 취소하고 입력 중으로 돌아갈까요? 출근표는 그대로 남습니다.')" in body
    p.status, p.publish_undo, p.published_at = P, [], timezone.now()
    p.save()
    PeriodEvent.objects.create(period=p, from_status=G, to_status=P)
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert "confirm('배포를 취소하고 이 회차를 확\\u0027정\\u005C됨으로 되돌릴까요?')" in body
