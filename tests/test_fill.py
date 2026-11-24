"""입력 표의 [2주 전 기준으로 채우기]·[지난주와 같게](설계 6.2). 이름은 모두 가상."""
import re
from datetime import date, time

import pytest
from django.contrib.auth.models import Group

from duty.errors import DutyError
from duty.models import Board, BoardShift, Commute, Department, Holiday, Period, User
from duty.services import collect
from duty.shifts import two_week_rotation
from tests.it_defs import OPS_STEPS

S = Period.Status
KEYS = ["dawn", "normal", "dinner"]  # 이른·가운데·늦은


def d(m, day):
    return date(2026, m, day)


# ── 순수 함수: 대표 근무조와 맞바꾸기 ──

def test_rotation_swaps_early_and_late():
    base = {d(11, 2): {"가": "dawn", "나": "dinner", "다": "normal"}, d(11, 3): {"가": "dawn", "나": "dinner"}}
    assert two_week_rotation(base, ["가", "나", "다", "라"], KEYS) == {
        "가": "dinner", "나": "dawn", "다": "normal", "라": "normal"}  # 2주 전 근무가 없던 라는 가운데


def test_rotation_uses_most_frequent_then_first_seen():
    base = {d(11, 2): {"가": "normal", "나": "dinner"}, d(11, 3): {"가": "dawn", "나": "dawn"},
            d(11, 4): {"가": "dawn"}}
    out = two_week_rotation(base, ["가", "나"], KEYS)
    assert out["가"] == "dinner"  # dawn 2번 > normal 1번
    assert out["나"] == "dawn"  # dinner·dawn 1번씩 → 먼저 나온 dinner


# ── 서비스 ──

@pytest.fixture
def ops(it_board, fixed_today):
    """가짜 직접 입력 근무표 '운영팀'(근무조 셋, 부서 하나)과 사람들.
    11/2~11/13 배포됨, 11/16~12/4 입력 중(11/18 휴장일). 가상마는 퇴사, 가상라는 새로 왔다."""
    fixed_today(d(11, 1))
    board = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
    for key, name, h in (("dawn", "이른", 7), ("normal", "가운데", 9), ("dinner", "늦은", 11)):
        BoardShift.objects.create(board=board, key=key, name=name, start=time(h, 30), end=time(h + 9, 30))
    dept = Department.objects.create(code="OPS", name="운영", shifts="dawn,normal,dinner", board=board)
    people = {n: User.objects.create_user(f"OPS{i}", password=None, name=n, department=dept, part="", type="직원")
              for i, n in enumerate(["가상가", "가상나", "가상다", "가상라", "가상마", "가상바"])}
    people["가상마"].is_active = False
    people["가상마"].save()
    old = Period.objects.create(board=board, name="지난", start_date=d(11, 2), end_date=d(11, 13),
                                status=S.PUBLISHED, overwrite_from=d(11, 2))

    def put(day, name, shift, reason=""):
        Commute.objects.create(period=old, date=day, member=people[name], shift=shift, reason=reason)

    for day in (2, 3, 4, 5, 6):  # 2주 전 주
        put(d(11, day), "가상가", "dawn")
        put(d(11, day), "가상나", "dinner")
        put(d(11, day), "가상다", "normal" if day < 5 else "dawn")  # normal 3번 > dawn 2번
        put(d(11, day), "가상마", "dawn")  # 퇴사자: 넣지 않는다
        put(d(11, day), "가상바", "dawn", "휴가")  # 근무로 친 날이 없다 → 가운데
    put(d(11, 9), "가상가", "dinner", "휴가")  # 지난주
    put(d(11, 9), "가상나", "dawn")
    put(d(11, 9), "가상다", "normal")
    put(d(11, 11), "가상나", "dawn")  # 11/18(휴장일)로 옮겨질 줄
    now = Period.objects.create(board=board, name="이번", start_date=d(11, 16), end_date=d(12, 4), status=S.COLLECTING)
    Holiday.objects.create(date=d(11, 18), name="가상휴일")
    return now, dept


def test_two_weeks_ago_fills_that_week_only(ops):
    p, dept = ops
    table = {d(11, 23): {"dawn": ["가상가"]}}  # 다른 주는 그대로
    out = collect.fill_week(p, dept, table, d(11, 19), collect.FILL_2W)
    week = {"dawn": ["가상나"], "normal": ["가상다", "가상라", "가상바"], "dinner": ["가상가"]}
    assert out == {d(11, 16): week, d(11, 17): week, d(11, 19): week, d(11, 20): week, d(11, 23): {"dawn": ["가상가"]}}
    assert Commute.objects.filter(period=p).count() == 0  # 저장하지 않는다


def test_two_weeks_ago_inside_period_reads_screen_table(ops):
    p, dept = ops
    table = {d(11, 16): {"dawn": ["가상다"], "dinner": ["가상가(교육)"]},
             d(11, 17): {"dawn": ["가상다"], "dinner": ["가상가"]}}  # 아직 저장하지 않은 화면의 표
    out = collect.fill_week(p, dept, table, d(11, 30), collect.FILL_2W)
    assert out[d(11, 30)] == {"dawn": ["가상가"], "normal": ["가상나", "가상라", "가상바"], "dinner": ["가상다"]}
    assert out[d(11, 16)] == table[d(11, 16)]


def test_same_as_last_week_copies_weekday_without_reason(ops):
    p, dept = ops
    out = collect.fill_week(p, dept, {d(11, 17): {"dawn": ["가상라"]}}, d(11, 16), collect.FILL_1W)
    assert out == {d(11, 16): {"dawn": ["가상나"], "normal": ["가상다"], "dinner": ["가상가"]}}  # 11/17 은 지난주가 비어 비움, 11/18 은 휴장일


def test_fill_errors(ops):
    p, dept = ops
    with pytest.raises(DutyError, match="알 수 없는 채우기"):
        collect.fill_week(p, dept, {}, d(11, 16), "3w")
    with pytest.raises(DutyError, match="회차 기간 밖"):
        collect.fill_week(p, dept, {}, d(12, 7), collect.FILL_1W)
    dept.shifts = "dawn,dinner"
    dept.save()
    with pytest.raises(DutyError, match="근무조가 3개일 때만"):
        collect.fill_week(p, dept, {}, d(11, 16), collect.FILL_2W)
    p.status = S.GENERATED  # 채우기는 입력을 받는 동안만(모든 근무표, 근무표 통합 2단계)
    p.save()
    with pytest.raises(DutyError, match="입력 중인 회차가 아닙니다"):
        collect.fill_week(p, dept, {}, d(11, 16), collect.FILL_1W)


def test_fill_works_on_it_board(it_board):
    """IT(마감을 쓰는 근무표)도 취합 중이면 채운다(근무표 통합 2단계)."""
    it = Period.objects.create(board=it_board, name="it", start_date=d(11, 16), end_date=d(11, 20), status=S.COLLECTING)
    mems = Department.objects.create(code="MEMS", name="매칭엔진실", shifts="dawn,normal,dinner", board=it_board)
    assert collect.fill_week(it, mems, {}, d(11, 16), collect.FILL_1W) == {}


# ── 화면 ──

@pytest.fixture
def ops_admin(client, ops, admin_user):
    ops[1].board.admin_group.user_set.add(admin_user)
    client.force_login(admin_user)
    return client


def test_buttons_per_week_and_enter_saves(ops_admin, ops):
    p, _ = ops
    body = ops_admin.get(f"/collect/{p.pk}/OPS/").content.decode()
    assert body.count('name="fill" value="2w:') == 3 and body.count('name="fill" value="1w:') == 3
    assert "<strong>11/16 주</strong>" in body and 'value="2w:2026-11-30"' in body
    assert body.index('class="enter-save"') < body.index('name="fill"')  # 칸에서 Enter = 저장


def test_two_weeks_button_needs_three_shifts(ops_admin, ops):
    p, dept = ops
    dept.shifts = "dawn,dinner"
    dept.save()
    body = ops_admin.get(f"/collect/{p.pk}/OPS/").content.decode()
    assert 'value="2w:' not in body and 'value="1w:2026-11-16"' in body


def test_fill_post_draws_without_saving(ops_admin, ops):
    p, _ = ops
    r = ops_admin.post(f"/collect/{p.pk}/OPS/", {"fill": "2w:2026-11-16", "c_2026-11-23_dawn": "가상가"})
    body = r.content.decode()
    assert r.status_code == 200 and Commute.objects.filter(period=p).count() == 0
    assert 'name="c_2026-11-16_dawn" rows="2" class="filled" >가상나</textarea>' in body
    assert 'name="c_2026-11-23_dawn" rows="2" >가상가</textarea>' in body  # 다른 주는 화면 값 그대로, 색칠 없음
    assert "12칸을 채웠습니다(색칠한 칸). 아직 저장하지 않았습니다." in body  # 4일 × 3칸(11/18 휴장일)


def test_fill_buttons_on_every_board_only_while_open(client, admin_user, it_board, ops):
    """채우기 버튼은 근무표와 상관없이 입력을 받는 동안만(근무표 통합 2단계): IT 취합 중에도 보이고, 확정한 회차에는 없다."""
    p, _ = ops
    p.status = S.GENERATED
    p.save()
    ops[1].board.admin_group.user_set.add(admin_user)
    Department.objects.create(code="MEMS", name="매칭엔진실", shifts="dawn,normal,dinner", board=it_board)
    it = Period.objects.create(board=it_board, name="it", start_date=d(11, 16), end_date=d(11, 20), status=S.COLLECTING)
    client.force_login(admin_user)
    body = client.get(f"/collect/{it.pk}/MEMS/").content.decode()
    assert 'value="2w:2026-11-16"' in body and 'value="1w:2026-11-16"' in body
    assert 'name="fill"' not in client.get(f"/collect/{p.pk}/OPS/").content.decode()


def test_week_header_uses_monday_when_period_starts_midweek(ops_admin, ops):
    p, _ = ops
    p.start_date = d(11, 18)  # 수요일에 시작
    p.save()
    body = ops_admin.get(f"/collect/{p.pk}/OPS/").content.decode()
    assert "<strong>11/16 주</strong>" in body and 'value="2w:2026-11-16"' in body and 'value="1w:2026-11-16"' in body
    assert body.count('name="fill" value="1w:') == 3  # 11/16·11/23·11/30 주
    r = ops_admin.post(f"/collect/{p.pk}/OPS/", {"fill": "1w:2026-11-16"})
    assert 'name="c_2026-11-18_dawn"' in r.content.decode()  # 월·화는 회차 밖이라 줄이 없다


def test_fill_keeps_other_weeks_skipped_day_values(ops_admin, ops):
    """잠긴 날(휴장일·근무 없음) 칸은 보내지 않으므로, 채우기 뒤에도 DB 값을 그대로 보여 준다."""
    p, dept = ops
    Commute.objects.create(period=p, date=d(11, 25), member=User.objects.get(name="가상가"), shift="dawn")
    Holiday.objects.create(date=d(11, 25), name="가상휴일2")
    r = ops_admin.post(f"/collect/{p.pk}/OPS/", {"fill": "2w:2026-11-16"})
    assert 'name="c_2026-11-25_dawn" rows="2" disabled>가상가</textarea>' in r.content.decode()


def test_fill_skips_people_kept_on_inactive_shift(ops):
    """그날 꺼진 근무조(보존되는 키)에 행이 있는 사람은 켜진 근무조에 넣지 않는다(넣으면 저장 검증이 막는다)."""
    p, dept = ops
    BoardShift.objects.create(board=p.board, key="night", name="밤", start=time(13), end=time(22), active=False)
    ga = User.objects.get(name="가상가")
    Commute.objects.create(period=p, date=d(11, 23), member=ga, shift="night")
    table = {d(11, 16): {"dawn": ["가상가"], "normal": ["가상나"]}}
    out = collect.fill_week(p, dept, table, d(11, 23), collect.FILL_1W)
    assert out[d(11, 23)] == {"dawn": [], "normal": ["가상나"], "dinner": []}
    assert collect.validate_table(ga, p, dept, out) == []


def test_two_weeks_ago_without_any_work_refuses(ops):
    """기준 주에 근무로 친 사람이 아무도 없으면 모두 가운데 조로 채우지 않고 알린다(4단계 점검)."""
    p, dept = ops
    with pytest.raises(DutyError, match="2주 전 그 주에 근무가 없어 채울 수 없습니다"):
        collect.fill_week(p, dept, {}, d(11, 30), collect.FILL_2W)


def test_table_cells_wrap_and_messages_are_plain(ops_admin, ops):
    p, _ = ops
    body = ops_admin.get(f"/collect/{p.pk}/OPS/").content.decode()
    assert '<textarea name="c_2026-11-16_dawn"' in body  # 이름이 많아도 줄바꿈으로 다 보인다
    assert 'name="c_2026-11-18_dawn" rows="2" disabled>' in body  # 11/18 휴장일 칸(까닭은 날짜 밑 글)
    assert "CSV 올리기(이 표 전체 교체)" in body and "부서 전체" not in body
    r = ops_admin.post(f"/collect/{p.pk}/OPS/", {"c_2026-11-16_dawn": "가상가"}, follow=True)
    assert "표를 저장했습니다." in r.content.decode() and "명분" not in r.content.decode()


def test_table_escapes_posted_values(ops_admin, ops):
    p, _ = ops
    bad = "</textarea><script>x</script>"
    for data in ({"fill": "2w:2026-11-16", "c_2026-11-23_dawn": bad},  # 채우기: 다른 주는 화면 값 그대로
                 {"c_2026-11-23_dawn": bad}):  # 저장 실패(모르는 이름): 고친 값 그대로 다시 그린다
        body = ops_admin.post(f"/collect/{p.pk}/OPS/", data).content.decode()
        assert "&lt;/textarea&gt;&lt;script&gt;x&lt;/script&gt;</textarea>" in body and "<script>x</script>" not in body
    assert Commute.objects.filter(period=p).count() == 0


@pytest.mark.parametrize("how", ["2w", "1w"])
def test_non_admin_fill_keeps_past_days_then_saves(client, ops, fixed_today, how):
    """관리자가 아닌 입력 담당은 지난 날을 못 고친다: 채우기도 오늘 전 줄은 보낸 값 그대로 두고, 바로 [표 저장]이 된다."""
    p, dept = ops
    ga = User.objects.get(name="가상가")
    Commute.objects.create(period=p, date=d(11, 16), member=ga, shift="normal")
    g = Group.objects.create(name="가상 입력")  # 지금은 마감을 쓰는 근무표(IT)만 입력 그룹이 생긴다: 여기선 손으로 붙인다
    Department.objects.filter(pk=dept.pk).update(input_group=g)
    g.user_set.add(ga)
    fixed_today(d(11, 17))  # 화요일: 11/16 은 지난 날(잠김)
    client.force_login(ga)
    body = client.post(f"/collect/{p.pk}/OPS/", {"fill": f"{how}:2026-11-16", "c_2026-11-16_normal": "가상가"}).content.decode()
    assert 'name="c_2026-11-16_normal" rows="2" readonly>가상가</textarea>' in body  # 그대로, 색칠 없음
    assert 'name="c_2026-11-16_dawn" rows="2" readonly></textarea>' in body
    if how == "2w":
        assert 'name="c_2026-11-17_dawn" rows="2" class="filled" >가상나</textarea>' in body
    post = {m[0]: m[1] for m in re.findall(r'<textarea name="(c_[^"]+)"[^>]*>([^<]*)</textarea>', body)}
    r = client.post(f"/collect/{p.pk}/OPS/", post, follow=True)
    assert "표를 저장했습니다." in r.content.decode()
    assert Commute.objects.get(period=p, date=d(11, 16)).member == ga


def test_week_all_before_keep_before_is_left_as_is(ops):
    """keep_before 로 그 주가 모두 지난 날이면 아무것도 바꾸지 않고 표를 그대로 돌려준다(2주 기준이 없다는 오류도 내지 않는다)."""
    p, dept = ops
    table = {d(11, 30): {"dawn": ["가상가"]}}
    for how in (collect.FILL_2W, collect.FILL_1W):
        out = collect.fill_week(p, dept, table, d(11, 30), how, keep_before=d(12, 7))
        assert out == table and out is not table  # 늘 새 표
