"""점심당번(설계 2·4.1·4.4·6.3·6.4·7·8). 혼자인 당번 칸: 가장 이른 근무조를 따라가고 인원 제한 없음, 정의에는 시각이
없고 알림·캘린더 시각은 사람 부서의 점심 시각. 이름은 모두 가상."""
from datetime import date, datetime, time, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from duty.admin import DepartmentForm
from duty.alarms import messages as m
from duty.alarms.plan import RuleSpec, plan
from duty.alarms.schedule import same_day_notice
from duty.errors import DutyError
from duty.models import (AlarmRule, Board, BoardShift, ChangeLog, Commute, Department, DutyAssignment, Holiday, Period,
                         TelegramAlarmProfile)
from duty.services import alarm_runner, alarm_settings, alarms, calendar, change_notice, changes, prefs, stats
from duty.services.generate import run_generation
from duty.services.roster import Day
from duty.shifts import DUTY_KEYS, KEYS, LUNCH, SHIFT, SLOT, SLOT_KEYS, SOLO, cells_of, display_order, kind
from tests.it_defs import IT_DEFS, IT_DEFS2, OPS_STEPS
from tests.test_alarm_texts_it import REPORT_BODY

S = Period.Status
T = date(2026, 11, 10)  # 화
NOW = timezone.make_aware(datetime(2026, 11, 10, 9, 0))
MON, TUE = date(2026, 11, 16), date(2026, 11, 17)
NOON = (time(11, 30), time(12, 30))


def _bad(fn):
    with pytest.raises(IntegrityError), transaction.atomic():
        fn()


# ── 키·성격·모델·관리 화면 ──

def test_keys_kind_and_order():
    assert KEYS[-1] == LUNCH == "lunch" and DUTY_KEYS == (*SLOT_KEYS, LUNCH)  # 순회 순서의 끝(기존 칸 hash 불변)
    assert [kind(k) for k in ("dawn", "night", "slot0", "slot9", "lunch")] == [SHIFT, SHIFT, SLOT, SLOT, SOLO]
    assert [x.key for x in display_order(IT_DEFS2)][:6] == ["dawn", "normal", "dinner", "night", "lunch", "slot0"]
    assert cells_of(IT_DEFS2, []) == KEYS and cells_of(IT_DEFS2, ["lunch", "dawn"]) == ["dawn", "lunch"]


def test_lunch_definition_has_no_times(it_board):
    ops = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
    BoardShift.objects.create(board=ops, key="dawn", name="이른조", start=time(7), end=time(16))
    BoardShift.objects.create(board=ops, key="lunch", name="점심당번")
    _bad(lambda: BoardShift.objects.create(board=ops, key="normal", name="가운데조"))  # 근무조는 시각 필수
    _bad(lambda: BoardShift.objects.filter(board=ops, key="lunch").update(start=time(11), end=time(12)))


def test_lunch_rows_have_no_head_limit(lunch, make_member, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=T, end_date=T)
    a, b = make_member("가"), make_member("나")
    DutyAssignment.objects.create(period=p, date=T, cell="lunch", member=a)
    DutyAssignment.objects.create(period=p, date=T, cell="lunch", member=b)  # 인원 제한 없음
    _bad(lambda: DutyAssignment.objects.create(period=p, date=T, cell="lunch", member=a))  # 같은 사람 두 번은 안 됨
    _bad(lambda: DutyAssignment.objects.create(period=p, date=T, cell="dawn", member=a))  # 근무조 키는 당번 칸이 아니다
    ChangeLog.objects.create(period=p, date=T, cell="lunch", before=a, after=b)


def test_department_lunch_times(depts):
    ui = Department.objects.filter(pk=depts["UI"].pk)
    _bad(lambda: ui.update(lunch_start=time(11, 30)))
    _bad(lambda: ui.update(lunch_start=time(12, 30), lunch_end=time(11, 30)))
    ui.update(lunch_start=time(11, 30), lunch_end=time(12, 30))


def test_admin_department_form_lunch(depts):
    ui = depts["UI"]
    data = {"code": ui.code, "name": ui.name, "board": ui.board_id, "order": ui.order, "shifts": ["normal"],
            "managers": []}
    form = DepartmentForm({**data, "lunch_start": "11:30", "lunch_end": ""}, instance=ui)
    assert not form.is_valid() and "점심 시각은 둘 다 비우거나" in str(form.errors)
    form = DepartmentForm({**data, "lunch_start": "11:30", "lunch_end": "12:30"}, instance=ui)
    assert form.is_valid(), form.errors
    assert form.save().lunch_end == time(12, 30)


# ── 생성: 가장 이른 근무조의 근무로 친 출근 전원 ──

@pytest.fixture
def gen(lunch, make_member, it_board):
    """관제를 만들 수 있는 이틀짜리 마감 회차(새벽 출근은 각 테스트가 넣는다)."""
    p = Period.objects.create(board=it_board, name="p", start_date=MON, end_date=TUE, status=S.CLOSED)
    normal = [make_member(f"N{i}", dept="MEMS") for i in range(5)]
    normal += [make_member(f"직원{x}", dept=x, type="직원") for x in ("MD", "UI")]
    dinner = [make_member(f"D{i}", dept="TMCH") for i in range(5)]
    for d in (MON, TUE):
        Commute.objects.bulk_create([Commute(period=p, date=d, member=x, shift="normal") for x in normal]
                                    + [Commute(period=p, date=d, member=x, shift="dinner") for x in dinner])
    return p


def _dawn(p, d, make_member, *names, reason=""):
    for n in names:
        Commute.objects.create(period=p, date=d, member=make_member(n), shift="dawn", reason=reason)


def test_generation_fills_lunch_with_earliest_shift(gen, make_member):
    _dawn(gen, MON, make_member, "가", "나")
    _dawn(gen, MON, make_member, "다", reason="휴가")  # 근무로 치지 않는다
    out = run_generation(gen, seed=3)
    lunch = DutyAssignment.objects.filter(period=gen, cell="lunch")
    assert sorted(lunch.values_list("date", "member__name")) == [(MON, "가"), (MON, "나")]
    assert DutyAssignment.objects.filter(period=gen, cell__startswith="slot").count() == 20
    assert out.warnings == ["점심당번을 채우지 못한 날(새벽 출근 없음): 11/17"]  # 아무도 없으면 비우고 경고


def test_lunch_does_not_change_slot_result(gen, make_member, lunch):
    _dawn(gen, MON, make_member, "가")
    run_generation(gen, seed=7)
    with_lunch = sorted(DutyAssignment.objects.filter(period=gen, cell__startswith="slot")
                        .values_list("date", "cell", "member__name"))
    BoardShift.objects.filter(pk=lunch.pk).delete()  # 저장한 정의는 instance.delete() 가 막는다(3단계), 시험 준비는 쿼리셋으로
    out = run_generation(gen, seed=7)
    assert sorted(DutyAssignment.objects.filter(period=gen).values_list("date", "cell", "member__name")) == with_lunch
    assert out.warnings == []  # 점심당번 정의가 없으면 채우지도 경고하지도 않는다


def test_generation_skips_closed_days(gen, make_member):
    Holiday.objects.create(date=TUE, name="임시 휴장")  # 새 회차는 skip_holidays 가 참
    _dawn(gen, MON, make_member, "가")
    out = run_generation(gen, seed=3)
    assert list(DutyAssignment.objects.filter(period=gen, cell="lunch").values_list("date", flat=True)) == [MON]
    assert out.warnings == []  # 건너뛰는 날은 빈 날로 경고하지 않는다


def test_generate_page_shows_lunch_warning(gen, admin_client_ok):
    r = admin_client_ok.post(f"/periods/{gen.pk}/action/generate/", follow=True)
    assert "점심당번을 채우지 못한 날(새벽 출근 없음): 11/16, 11/17" in r.content.decode()


def test_counts_leave_lunch_out(gen, make_member, it_board):
    run_generation(gen, seed=3)
    DutyAssignment.objects.create(period=gen, date=MON, cell="lunch", member=make_member("가"))
    counts, _, _ = stats.period_duty_counts(gen)
    assert sum(n for _, n in counts) == 20 and "가" not in dict(counts)
    Period.objects.filter(pk=gen.pk).update(status=S.PUBLISHED, overwrite_from=MON)
    rows, _, _ = stats.member_stats(it_board, None, None)
    assert sum(r.duty for r in rows) == 20


# ── 근무 변경: 넣기·빼기·교체, 묶음이 달라 관제와 안 섞임, 같이 넘기기 ──

@pytest.fixture
def pub(lunch, make_member, fixed_today, it_board):
    fixed_today(T)
    p = Period.objects.create(board=it_board, name="p", start_date=T, end_date=T, status=S.PUBLISHED,
                              overwrite_from=T, published_at=NOW - timedelta(days=1))
    m = {n: make_member(n, user=True) for n in ["가", "나", "다", "라"]}
    for n, shift in (("가", "dawn"), ("나", "normal"), ("다", "dinner")):
        Commute.objects.create(period=p, date=T, member=m[n], shift=shift)
    DutyAssignment.objects.create(period=p, date=T, cell="slot0", member=m["나"])
    DutyAssignment.objects.create(period=p, date=T, cell="lunch", member=m["가"])
    return p, m


def _lunch_names(p):
    return sorted(DutyAssignment.objects.filter(period=p, cell="lunch").values_list("member__name", flat=True))


def test_lunch_add_remove_replace(pub, it_board):
    p, m = pub
    changes.change_cell(m["라"], it_board, T, "lunch", None, m["라"])  # 넣기만
    assert _lunch_names(p) == ["가", "라"]
    changes.change_cell(m["라"], it_board, T, "lunch", m["가"], m["다"])  # 교체
    changes.change_cell(m["라"], it_board, T, "lunch", m["라"], None)  # 빼기만
    assert _lunch_names(p) == ["다"]
    assert list(ChangeLog.objects.values_list("cell", "before__name", "after__name")) == [
        ("lunch", None, "라"), ("lunch", "가", "다"), ("lunch", "라", None)]
    with pytest.raises(DutyError, match="가은\\(는\\) 이 칸에 없습니다"):
        changes.change_cell(m["라"], it_board, T, "lunch", m["가"], m["나"])
    with pytest.raises(DutyError, match="다은\\(는\\) 이미 이 칸에 있습니다"):
        changes.exchange(m["라"], it_board, T, "lunch", None, m["다"])


def test_lunch_and_slots_do_not_mix(pub, it_board):
    p, m = pub
    assert changes.exchange(m["라"], it_board, T, "lunch", m["가"], m["나"]) == []  # 나의 관제 칸과 맞바꾸지 않는다
    assert _lunch_names(p) == ["나"] and DutyAssignment.objects.get(cell="slot0").member == m["나"]
    # 관제 칸 To 가 점심당번이어도 "다른 관제 칸" 경고·맞교환 개수 검사에 들지 않는다
    warnings = changes.exchange(m["라"], it_board, T, "slot0", m["나"], m["다"])
    assert not any("다른 관제 칸" in w for w in warnings)
    assert DutyAssignment.objects.get(cell="slot0").member == m["다"] and _lunch_names(p) == ["나"]
    with pytest.raises(DutyError, match="출근조끼리 또는 관제 칸끼리만"):
        changes.swap(m["라"], it_board, T, "lunch", m["나"], "normal", m["다"])


def test_lunch_needs_definition(pub, it_board, lunch):
    _, m = pub
    BoardShift.objects.filter(pk=lunch.pk).delete()  # 저장한 정의는 instance.delete() 가 막는다(3단계), 시험 준비는 쿼리셋으로
    with pytest.raises(DutyError, match="알 수 없는 칸"):
        changes.change_cell(m["라"], it_board, T, "lunch", m["가"], m["라"])


def test_carry_lunch_on_replace(pub, it_board):
    p, m = pub
    changes.change_cell(m["라"], it_board, T, "dawn", m["가"], m["라"])
    assert _lunch_names(p) == ["라"]
    assert list(ChangeLog.objects.values_list("cell", "before__name", "after__name")) == [
        ("dawn", "가", "라"), ("lunch", "가", "라")]  # 근무조 기록 뒤에
    changes.change_cell(m["다"], it_board, T, "dawn", m["라"], m["가"], carry_lunch=False)
    assert _lunch_names(p) == ["라"] and ChangeLog.objects.count() == 3
    changes.change_cell(m["다"], it_board, T, "dawn", m["가"], None)  # 빼기만은 넘길 사람이 없다
    assert _lunch_names(p) == ["라"]


def test_carry_lunch_skips_when_incoming_has_it(pub, it_board):
    p, m = pub
    DutyAssignment.objects.create(period=p, date=T, cell="lunch", member=m["라"])
    changes.change_cell(m["다"], it_board, T, "dawn", m["가"], m["라"])
    assert _lunch_names(p) == ["가", "라"] and ChangeLog.objects.count() == 1


def test_carry_lunch_on_swap_keeps_notice_pairing(pub, it_board, monkeypatch):
    p, m = pub
    conf = alarm_settings.current()
    conf.telegram_bot_token = "1234567890:" + "FAKE" + "x" * 31
    alarm_settings.save(conf)
    TelegramAlarmProfile.objects.create(user=m["가"], chat_id="11", verified_at=NOW)
    TelegramAlarmProfile.objects.create(user=m["나"], chat_id="22", verified_at=NOW)
    sent = []
    monkeypatch.setattr("duty.alarms.senders.telegram_send", lambda cfg, chat, text: sent.append((chat, text)) or {})
    changes.exchange(m["다"], it_board, T, "dawn", m["가"], m["나"])  # 나는 정상 → 맞교환
    assert list(ChangeLog.objects.values_list("cell", "before__name", "after__name")) == [
        ("dawn", "가", "나"), ("normal", "나", "가"), ("lunch", "가", "나")]
    assert _lunch_names(p) == ["나"]
    change_notice.tick(NOW)
    texts = sorted(t.split("\n")[0] + "|" + chat for chat, t in sent)
    assert texts == ["[근무 변경] 11/10(화) 맞교환|11", "[근무 변경] 11/10(화) 맞교환|22",
                     "[근무 변경] 11/10(화) 점심당번|11", "[근무 변경] 11/10(화) 점심당번|22"]


def test_carry_lunch_on_swap_from_other_side(pub, it_board):
    p, m = pub
    changes.exchange(m["다"], it_board, T, "normal", m["나"], m["가"])  # To(가)가 새벽·점심당번 → 맞교환
    assert list(ChangeLog.objects.values_list("cell", "before__name", "after__name")) == [
        ("normal", "나", "가"), ("dawn", "가", "나"), ("lunch", "가", "나")]
    assert _lunch_names(p) == ["나"]  # 새벽을 떠난 가에게 남지 않는다


def test_set_reason_warns_lunch(pub, it_board):
    _, m = pub
    assert changes.set_reason(m["다"], it_board, T, m["가"], "휴가") == [
        "가은(는) 그날 점심당번 칸에 남아 있습니다. 그 칸을 눌러 다른 사람으로 바꾸거나 빼세요."]  # 자동으로 빼지 않는다


def test_set_reason_warns_slot_and_lunch_together(pub, it_board):
    p, m = pub
    DutyAssignment.objects.create(period=p, date=T, cell="lunch", member=m["나"])  # 나는 관제 칸에도 있다
    assert changes.set_reason(m["라"], it_board, T, m["나"], "휴가") == [
        "나은(는) 그날 점심당번, 장중관제 08:30~09:30 칸에 남아 있습니다. "
        "그 칸을 눌러 다른 사람으로 바꾸세요(점심당번 칸은 빼도 됩니다)."]  # 관제 칸은 비울 수 없다


# ── 화면: 근무조 → 점심당번 → 관제, 시각 없이 "점심당번", 근무 변경 창 ──

def test_roster_and_day_order(pub, client):
    _, m = pub
    client.force_login(m["나"])
    for url in ["/?date=2026-11-10", "/?view=month&date=2026-11-10"]:
        body = client.get(url).content.decode()
        assert body.index('<span class="shn">야간</span>') < body.index('<span class="shn">점심당번</span>') < body.index('<b class="sh">관제</b>')
        assert 'href="/day/2026-11-10/#lunch"' in body  # 칸을 눌러 바꾼다
    body = client.get("/day/2026-11-10/").content.decode()
    assert body.index("<strong>야간</strong>") < body.index("<strong>점심당번</strong>") < body.index("<strong>08:30~09:30</strong>")
    assert "11:30~12:30</strong>" not in body.split("<strong>점심당번</strong>")[1][:50]  # 시각 없이
    grp = body.split('<h4 class="grp">')
    assert [g.split("<")[0] for g in grp[1:]] == ["출근조", "당번", "장중관제"]  # 점심당번은 출근조 아래가 아니다


def test_schedule_filter_and_me(pub, client):
    assert list(prefs.choices(IT_DEFS2).items())[-2:] == [("slots", "장중관제"), ("lunch", "점심당번")]
    assert "lunch" not in prefs.choices(IT_DEFS)
    _, m = pub
    client.force_login(m["가"])
    body = client.get("/?date=2026-11-10&f=1&shift=lunch").content.decode()
    assert 'class="sec k-lunch" data-k="lunch"' in body and 'value="lunch" checked' in body and 'value="dawn" checked' not in body
    me = client.get("/me/").content.decode()
    assert 'value="lunch"' in me and '새벽 06:30~15:30</span><span class="w" data-k="lunch">점심당번</span>' in me  # 부서 점심 시각이 없으면 이름만
    Department.objects.filter(pk=m["가"].department_id).update(lunch_start=time(11, 30), lunch_end=time(12, 30))
    assert '<span class="w" data-k="lunch">점심당번 11:30~12:30</span>' in client.get("/me/").content.decode()


def test_cell_form_for_lunch_and_carry(pub, client, lunch):
    _, m = pub
    client.force_login(m["나"])
    body = client.get("/cell/2026-11-10/lunch/").content.decode()
    assert "From 대신 To 가 점심당번이 됩니다." in body
    assert "(없음 — 새로 넣기만)" in body and "(없음 — 빼기만)" in body
    assert 'name="reason"' not in body and "carry_lunch" not in body
    assert 'name="carry_lunch" value="1" checked' in client.get("/cell/2026-11-10/dawn/").content.decode()
    assert "carry_lunch" not in client.get("/cell/2026-11-10/slot0/").content.decode()
    BoardShift.objects.filter(pk=lunch.pk).delete()  # 저장한 정의는 instance.delete() 가 막는다(3단계), 시험 준비는 쿼리셋으로
    assert "carry_lunch" not in client.get("/cell/2026-11-10/dawn/").content.decode()  # 정의가 없으면 숨김


def test_cell_post_carry_lunch(pub, client):
    p, m = pub
    client.force_login(m["다"])
    client.post("/cell/2026-11-10/dawn/", {"before": m["가"].pk, "after": m["라"].pk})  # 체크 해제
    assert _lunch_names(p) == ["가"]
    client.post("/cell/2026-11-10/dawn/", {"before": m["라"].pk, "after": m["나"].pk, "carry_lunch": "1"})
    assert _lunch_names(p) == ["가"]  # 떠나는 라는 점심당번이 아니다
    client.post("/cell/2026-11-10/lunch/", {"before": m["가"].pk, "after": m["라"].pk})
    assert _lunch_names(p) == ["라"]


# ── 알림: 문구 틀 셋, 개인 = 부서 점심 시각, 보고서 줄은 기존 줄 뒤(2단계 문구 고정) ──

SUN18 = datetime(2026, 11, 15, 18)
INFO = {"가": ("MEMS", "개발자"), "나": ("MEMS", "직원"), "다": ("OTH", "개발자")}


def _day(reasons=None, replaced=None, **cells):
    members = {c: [] for c in KEYS}
    members.update({k: list(v) for k, v in cells.items()})
    return Day(MON, 1, {}, members, replaced or {}, reasons or {})


def _rule(**kw):
    base = dict(id=1, member_name="가", kind="personal", timing="days", offset=1, at_minute=18 * 60,
                channels=("telegram",), shifts=("lunch",), depts=(), types=())
    return RuleSpec(**{**base, **kw})


def _plan(rules, days, deliveries=None, now=SUN18, **kw):
    dests = {(r.id, ch): ["d"] for r in rules for ch in r.channels}
    return plan(IT_DEFS2, rules, days, INFO, deliveries or {}, now, destinations=dests, **kw)


def test_personal_lunch_with_department_time():
    [due] = _plan([_rule(lunch=NOON)], [_day(lunch=["가"])])
    assert (due.cell, due.title, due.text, due.content_hash, due.expires_at) == (
        "lunch", "당번 알림", "[당번 알림] 11/16(월) 점심당번 11:30~12:30\n가님, 내일 점심당번입니다.",
        "in:c19e395c7a14672c", datetime(2026, 11, 16, 11, 30))
    [due] = _plan([_rule(lunch=NOON, timing="before_start", offset=120, at_minute=0)], [_day(lunch=["가"])],
                  now=datetime(2026, 11, 16, 9, 30))
    assert due.text.startswith("[당번 알림] 11/16(월) 점심당번 11:30~12:30\n가님, 오늘 점심당번")


def test_personal_lunch_without_department_time():
    [due] = _plan([_rule()], [_day(lunch=["가"])])
    assert (due.text, due.content_hash, due.expires_at) == (
        "[당번 알림] 11/16(월) 점심당번\n가님, 내일 점심당번입니다.", "in:b9b22baa48acedca",
        datetime(2026, 11, 17))  # 날짜 기준: 그날 끝까지
    assert _plan([_rule(timing="before_start", offset=120, at_minute=0)], [_day(lunch=["가"])],
                 now=datetime(2026, 11, 16, 10)) == []  # 시각 기준 규칙에서는 빠진다


def test_personal_lunch_cancel_and_reason():
    sent = {(1, MON, "lunch", "telegram", "d"): "in:c19e395c7a14672c"}
    [due] = _plan([_rule(lunch=NOON)], [_day(lunch=["나"], replaced={("lunch", "나"): "가"})], sent)
    assert due.text == "[당번 변경] 11/16(월) 점심당번 11:30~12:30\n가님의 근무가 취소되었습니다. (후임: 나)"
    away = _day({("dawn", "가"): "휴가"}, dawn=["가"], lunch=["가"])  # 사유가 있는 날의 점심당번은 근무로 치지 않는다
    assert _plan([_rule(lunch=NOON)], [away]) == [] and _plan([_rule(lunch=NOON)], [away], sent) == []


def test_existing_cells_unchanged_with_lunch_defined():
    [due] = _plan([_rule(shifts=("dawn",), lunch=NOON)], [_day(dawn=["가"], lunch=["가"])])
    assert (due.text, due.content_hash) == ("[당번 알림] 11/16(월) 새벽 06:30~15:30\n가님, 내일 새벽 당번입니다.",
                                            "in:b67c7c6d5f7f719a")  # 1단계와 같은 hash


def test_report_appends_lunch_line_without_time():
    r = _rule(kind="report", member_name=None, shifts=(), depts=("MEMS",))
    d = _day(dawn=["가"], normal=["나"], slot0=["나"], night=["다"], lunch=["가", "다"])
    [due] = _plan([r], [d], dept_names={"MEMS": "매칭엔진실"})
    assert (due.text, due.content_hash, due.push_text, due.expires_at) == (
        "[출근표] 11/16(월) — 매칭엔진실\n" + REPORT_BODY + "\n점심당번 가", "report:37fb102d22a93e95",
        "[출근표] 11/16(월) — 매칭엔진실\n" + REPORT_BODY + "\n점심당번 가", datetime(2026, 11, 16, 17, 0))  # 발송 창·만료는 시각 있는 칸으로
    assert _plan([_rule(kind="report", member_name=None, shifts=("lunch",))], [d]) == []


def test_lunch_message_kinds_and_same_day_notice():
    assert m.change_notice(IT_DEFS2, T, "lunch", "가", "나", "관리자") == (
        "근무 변경", "[근무 변경] 11/10(화) 점심당번\n가 → 나\n바꾼 사람: 관리자")
    assert m.report_line(IT_DEFS2, "lunch", []) == "점심당번 -"
    assert same_day_notice(IT_DEFS2, "personal", "days", 0, 10 * 60, []) == \
        "새벽·정상·석식교대·장중관제 08:30~10:30은 발송 시각이 근무 시작 이후라 제외됩니다."
    assert same_day_notice(IT_DEFS2, "personal", "days", 0, 13 * 60, ["lunch"]) is None
    assert same_day_notice(IT_DEFS2, "report", "days", 0, 17 * 60, []) == "현재 선택으로는 보고서가 발송되지 않습니다."


def test_report_rule_needs_timed_cell(lunch, admin_user, it_board):
    base = dict(enabled=True, kind="report", timing="days", offset=1, at_minute=18 * 60, telegram=True, push=False,
                depts=[], types=[], board_id=it_board.pk)
    with pytest.raises(DutyError, match="점심당번만으로는"):
        alarms.save_rule(admin_user, {**base, "shifts": ["lunch"]})
    assert alarms.save_rule(admin_user, {**base, "shifts": ["lunch", "dawn"]}).shifts == ["dawn", "lunch"]


def test_report_rule_all_on_lunch_only_board_refused(admin_user, it_board):
    """켜진 정의가 점심당번뿐인 근무표에서 '전체'(빈 목록)도 점심당번만이라 막는다."""
    board = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
    BoardShift.objects.create(board=board, key="lunch", name="점심당번")
    base = dict(enabled=True, kind="report", timing="days", offset=1, at_minute=18 * 60, telegram=True, push=False,
                depts=[], types=[], board_id=board.pk)
    for shifts in ([], ["lunch"]):
        with pytest.raises(DutyError, match="점심당번만으로는"):
            alarms.save_rule(admin_user, {**base, "shifts": shifts})


def test_runner_uses_department_lunch_time(pub, it_board, fixed_today):
    p, m = pub
    fixed_today(T - timedelta(days=1))
    Department.objects.filter(code="MEMS").update(lunch_start=time(11, 40), lunch_end=time(12, 40))
    conf = alarm_settings.current()
    conf.telegram_bot_token = "1234567890:" + "FAKE" + "x" * 31
    alarm_settings.save(conf)
    TelegramAlarmProfile.objects.create(user=m["가"], chat_id="11", verified_at=NOW)
    AlarmRule.objects.create(user=m["가"], kind="personal", timing="days", offset=1, at_minute=18 * 60, telegram=True,
                             shifts=["lunch"])
    [(due, _, _)] = alarm_runner.collect(timezone.make_aware(datetime(2026, 11, 9, 18)))
    assert due.text == "[당번 알림] 11/10(화) 점심당번 11:40~12:40\n가님, 내일 점심당번입니다."


# ── 캘린더: 부서 점심 시각이 있으면 일정 하나 ──

def test_calendar_lunch_event(pub, it_board, settings):
    _, m = pub
    settings.SITE_URL = "https://duty.example"
    assert [e.summary for e in calendar._events(m["가"])] == ["새벽 출근 06:30~15:30"]  # 부서 시각이 없으면 없음
    Department.objects.filter(code="MEMS").update(lunch_start=time(11, 30), lunch_end=time(12, 30))
    m["가"].refresh_from_db()
    events = calendar._events(m["가"])
    assert [e.summary for e in events] == ["새벽 출근 06:30~15:30", "점심당번"]
    assert (events[1].start.hour, events[1].start.minute, events[1].end.hour) == (11, 30, 12)
    assert events[1].uid.startswith("20261110-lunch-")
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    assert calendar._events(m["가"]) == []  # 사유가 있는 날은 빠진다


def test_same_day_notice_personal_counts_lunch_by_department_time():
    """개인 규칙: 점심당번은 부서 점심 시각으로 따진다(시각이 없으면 그날 끝까지 가므로 빠지지 않는다)."""
    from datetime import time
    # 07:00 발송, 새벽(06:30)+점심당번(11:30): 새벽만 빠지고 점심당번은 간다
    assert same_day_notice(IT_DEFS2, "personal", "days", 0, 7 * 60, ["dawn", "lunch"], lunch=time(11, 30)) == \
        "새벽은 발송 시각이 근무 시작 이후라 제외됩니다."
    assert same_day_notice(IT_DEFS2, "personal", "days", 0, 7 * 60, ["dawn", "lunch"]) == \
        "새벽은 발송 시각이 근무 시작 이후라 제외됩니다."
    # 13:00 발송: 부서 점심 11:30 이면 둘 다 빠진다
    assert same_day_notice(IT_DEFS2, "personal", "days", 0, 13 * 60, ["dawn", "lunch"], lunch=time(11, 30)) == \
        "현재 선택으로는 발송되는 근무가 없습니다."
