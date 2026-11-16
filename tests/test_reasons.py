"""사유(휴가·출장·교육, 설계 2·4.6·4.7·6.2·6.4·7·8). 사유가 붙은 배정은 근무로 치지 않는다. 이름은 모두 가상."""
from datetime import date, datetime, timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from duty.csv_io import CsvInvalid, join_reason, split_reason
from duty.errors import DutyError
from duty.models import (REASONS, ChangeLog, Commute, DutyAssignment, Period, RosterPref, TelegramAlarmProfile,
                         validate_member_name)
from duty.alarms.plan import RuleSpec, plan
from duty.services import alarm_settings, calendar, change_notice, changes, collect, memos, publish, stats
from duty.services.generate import run_generation
from duty.services.roster import Day, find_day
from duty.shifts import KEYS
from tests.it_defs import IT_DEFS

S = Period.Status


# ── 값·이름 규칙·순수 함수 ──

def test_reasons_constant():
    assert REASONS == ("휴가", "출장", "교육")


@pytest.mark.parametrize("raw, expected", [
    ("가상일(휴가)", ("가상일", "휴가")),
    ("가상일(출장)", ("가상일", "출장")),
    ("가상일 (교육)", ("가상일", "교육")),
    ("가상일", ("가상일", "")),
    ("가상일(휴가) ", ("가상일(휴가) ", "")),  # 끝이 정확히 (사유)일 때만(split_names 가 이미 양끝 공백을 뗀다)
    ("가상일(병가)", ("가상일(병가)", "")),
    ("가상일(휴가)x", ("가상일(휴가)x", "")),
    ("(휴가)", ("(휴가)", "")),  # 이름이 비면 사유로 떼지 않는다
])
def test_split_reason(raw, expected):
    assert split_reason(raw) == expected


def test_join_reason():
    assert join_reason("가상일", "휴가") == "가상일(휴가)"
    assert join_reason("가상일", "") == "가상일"
    assert split_reason(join_reason("가상일", "출장")) == ("가상일", "출장")


@pytest.mark.parametrize("name", ["가상일(휴가)", "가상일(출장)", "가상일 (교육)"])
def test_member_name_cannot_end_with_reason(name):
    with pytest.raises(ValidationError, match="휴가"):
        validate_member_name(name)


def test_member_name_other_parentheses_ok():
    validate_member_name("가상일(A)")


def test_reason_db_constraints(make_member, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 16), end_date=date(2026, 11, 20))
    m = make_member("가")
    c = Commute.objects.create(period=p, date=date(2026, 11, 16), member=m, shift="dawn")
    assert c.reason == ""
    Commute.objects.filter(pk=c.pk).update(reason="휴가")
    with pytest.raises(IntegrityError), transaction.atomic():
        Commute.objects.filter(pk=c.pk).update(reason="병가")
    log = ChangeLog.objects.create(period=p, date=c.date, cell="dawn", before=m, after=m, reason_after="출장")
    assert log.reason_before == ""
    with pytest.raises(IntegrityError), transaction.atomic():
        ChangeLog.objects.filter(pk=log.pk).update(reason_before="병가")


# ── 출근표 입력 표·CSV ──

D = date(2026, 11, 9)  # 월
HEAD = "date,새벽,정상,석식교대,야간\n"


@pytest.fixture
def collecting(depts, make_member, fixed_today, it_board):
    fixed_today(date(2026, 11, 1))
    p = Period.objects.create(board=it_board, name="p", start_date=D, end_date=date(2026, 11, 13), status=S.COLLECTING)
    mgr = make_member("담당", user=True)
    depts["MEMS"].input_group.user_set.add(mgr)
    for n in ["가", "나", "다"]:
        make_member(n)
    return p, depts["MEMS"], mgr


def test_table_reads_and_writes_reason(collecting):
    p, dept, user = collecting
    assert collect.apply_table(user, p, dept, {D: {"dawn": ["가(휴가)"], "normal": ["나", "다(출장)"]}}) == 3
    assert dict(Commute.objects.values_list("member__name", "reason")) == {"가": "휴가", "나": "", "다": "출장"}
    assert collect.load_table(p, dept)[D] == {"dawn": ["가(휴가)"], "normal": ["나", "다(출장)"]}


def test_csv_reason_roundtrip(collecting):
    p, dept, user = collecting
    collect.apply_csv(user, p, dept, (HEAD + '2026-11-09,가(교육),"나, 다",,\n').encode())
    assert Commute.objects.get(member__name="가").reason == "교육"
    out = collect.export_csv(p, dept).decode("utf-8-sig")
    assert "2026-11-09,월,가(교육),\"나, 다\"" in out
    assert collect.apply_csv(user, p, dept, out.encode()) == 3  # 내려받은 그대로 다시 올려도 된다
    assert Commute.objects.get(member__name="가").reason == "교육"


def test_unknown_reason_is_not_a_member(collecting):
    p, dept, user = collecting
    with pytest.raises(CsvInvalid) as e:
        collect.apply_table(user, p, dept, {D: {"dawn": ["가(병가)"]}})
    assert "재직 멤버가 아닙니다: 가(병가)" in e.value.errors[0].reason


def test_reason_does_not_hide_double_shift(collecting):
    p, dept, user = collecting
    with pytest.raises(CsvInvalid) as e:
        collect.apply_table(user, p, dept, {D: {"dawn": ["가(휴가)"], "night": ["가"]}})
    assert "가: 새벽·야간에 중복" in e.value.errors[0].reason


def test_changing_only_reason_is_a_change(collecting, fixed_today):
    p, dept, user = collecting
    collect.apply_table(user, p, dept, {D: {"dawn": ["가"]}})
    fixed_today(date(2026, 11, 10))  # 일반 담당자에게 지난 날짜
    with pytest.raises(CsvInvalid) as e:
        collect.apply_table(user, p, dept, {D: {"dawn": ["가(휴가)"]}})
    assert "지난 날짜" in e.value.errors[0].reason


# ── 사유 바꾸기(근무 변경 창)·기록·변경 표시·변경 알림 ──

T = date(2026, 11, 10)  # 화
NOW = timezone.make_aware(datetime(2026, 11, 10, 9, 0))


@pytest.fixture
def pub(make_member, fixed_today, it_board):
    fixed_today(T)
    p = Period.objects.create(board=it_board, name="p", start_date=T, end_date=T, status=S.PUBLISHED,
                              overwrite_from=T, published_at=NOW - timedelta(days=1))
    m = {n: make_member(n, user=True) for n in ["가", "나", "다"]}
    Commute.objects.create(period=p, date=T, member=m["가"], shift="normal")
    Commute.objects.create(period=p, date=T, member=m["나"], shift="dawn")
    DutyAssignment.objects.create(period=p, date=T, cell="slot0", member=m["가"])
    return p, m


def test_set_reason_records_without_changing_people(pub, it_board):
    p, m = pub
    warnings = changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    assert Commute.objects.get(member=m["가"]).reason == "휴가"
    log = ChangeLog.objects.get()
    assert (log.cell, log.before, log.after, log.reason_before, log.reason_after, log.by) == (
        "normal", m["가"], m["가"], "", "휴가", m["다"])
    # 당번 칸은 자동으로 빼지 않고 경고만(점심당번이 생기면 같은 경고가 "점심당번 칸"으로 나온다)
    assert warnings == ["가은(는) 그날 장중관제 08:30~09:30 칸에 남아 있습니다. 그 칸을 눌러 다른 사람으로 바꾸거나 빼세요."]
    assert changes.set_reason(m["다"], it_board, T, m["나"], "출장") == []
    changes.set_reason(m["다"], it_board, T, m["가"], "")
    assert Commute.objects.get(member=m["가"]).reason == ""
    assert ChangeLog.objects.last().reason_before == "휴가"


@pytest.mark.parametrize("who, reason, msg", [
    ("가", "병가", "알 수 없는 사유"),
    ("가", "", "변경할 내용이 없습니다"),
    ("다", "휴가", "그날 근무조에 없습니다"),
])
def test_set_reason_rejects(pub, it_board, who, reason, msg):
    _, m = pub
    with pytest.raises(DutyError, match=msg):
        changes.set_reason(m["나"], it_board, T, m[who], reason)
    assert not ChangeLog.objects.exists()


def test_set_reason_needs_edit_permission(pub, it_board, fixed_today):
    _, m = pub
    fixed_today(T + timedelta(days=1))
    with pytest.raises(PermissionDenied):
        changes.set_reason(m["나"], it_board, T, m["가"], "휴가")  # 지난 날짜는 관리자만


def test_reason_only_log_is_not_a_change_on_screen(pub, it_board):
    _, m = pub
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    day = find_day(it_board, T)
    assert day.cells["normal"].labels == ["가"] and not day.cells["normal"].changed
    assert day.reasons == {("normal", "가"): "휴가"}
    changes.change_cell(m["다"], it_board, T, "normal", m["가"], m["다"])  # 뒤 기록의 A>B 는 그대로
    day = find_day(it_board, T)
    assert day.cells["normal"].labels == ["가>다"] and day.reasons == {}


def test_moves_keep_reason_with_person_and_log_it(pub, it_board):
    _, m = pub
    changes.set_reason(m["다"], it_board, T, m["가"], "교육")
    changes.swap(m["다"], it_board, T, "normal", m["가"], "dawn", m["나"])
    assert Commute.objects.get(member=m["가"]).reason == "교육" and Commute.objects.get(member=m["가"]).shift == "dawn"
    changes.change_cell(m["다"], it_board, T, "dawn", m["가"], None)  # 빼면 빠진 사람의 사유를 기록에 남긴다
    assert ChangeLog.objects.last().reason_before == "교육"


def test_change_notice_skips_reason_only_logs(pub, it_board, monkeypatch):
    _, m = pub
    conf = alarm_settings.current()
    conf.telegram_bot_token = "1234567890:" + "FAKE" + "x" * 31
    alarm_settings.save(conf)  # 토큰을 바꾸면 연결이 풀리므로 연결보다 먼저
    TelegramAlarmProfile.objects.create(user=m["가"], chat_id="11", verified_at=NOW)
    TelegramAlarmProfile.objects.create(user=m["나"], chat_id="22", verified_at=NOW)
    sent = []
    monkeypatch.setattr("duty.alarms.senders.telegram_send", lambda cfg, chat, text: sent.append((chat, text)) or {})
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    changes.exchange(m["다"], it_board, T, "normal", m["가"], m["나"])  # 맞교환 두 기록의 짝짓기도 그대로
    change_notice.tick(NOW)
    assert sorted(chat for chat, _ in sent) == ["11", "22"] and all("맞교환" in t for _, t in sent)
    assert not ChangeLog.objects.filter(notified=False).exists()


def test_clearing_no_work_day_logs_reason(pub, it_board, admin_user):
    _, m = pub
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    memos.save(admin_user, it_board, "day", T, "워크숍", no_work=True, confirm=2)  # 가·나 두 명
    assert ChangeLog.objects.get(cell="normal", after=None).reason_before == "휴가"


def test_history_page_shows_reason(pub, it_board, admin_client_ok):
    _, m = pub
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    body = admin_client_ok.get("/changes/").content.decode()
    assert "가 → 가(휴가)" in body


def test_swap_records_reasons_in_both_logs(pub, it_board):
    """맞교환은 행의 근무조만 바꾸므로 사유는 사람을 따라간다. 두 기록 모두 그 사람들의 사유를 남긴다."""
    _, m = pub
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    changes.swap(m["다"], it_board, T, "normal", m["가"], "dawn", m["나"])
    assert dict(Commute.objects.values_list("member__name", "shift")) == {"가": "dawn", "나": "normal"}
    assert dict(Commute.objects.values_list("member__name", "reason")) == {"가": "휴가", "나": ""}
    a_log, b_log = ChangeLog.objects.order_by("id")[1:]
    assert (a_log.cell, a_log.before, a_log.after, a_log.reason_before, a_log.reason_after) == (
        "normal", m["가"], m["나"], "휴가", "")
    assert (b_log.cell, b_log.before, b_log.after, b_log.reason_before, b_log.reason_after) == (
        "dawn", m["나"], m["가"], "", "휴가")


# ── 화면: 사유는 취소선·옅은 회색(변경 내역 표시를 따른다), 근무 변경 창의 사유 선택, 입력 표 안내 ──

EXC = '<span class="lb exc"><s>가(휴가)</s></span>'


def test_roster_and_day_strike_reason_with_history(pub, it_board, client):
    _, m = pub
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    client.force_login(m["나"])
    for url in ["/?date=2026-11-10", "/?view=month&date=2026-11-10", "/day/2026-11-10/"]:
        body = client.get(url).content.decode()
        assert body.count(EXC) == 2, url  # 사유는 그날 그 사람 전체: 관제 칸의 가에도 그어진다
        assert 'class="rsn"' not in body, url


def test_reason_hidden_without_history(pub, it_board, client):
    """변경 내역을 끄면 빠진 사람처럼 사유 있는 사람도 숨긴다. 근무 변경 창에는 그대로 있어 고칠 수 있다."""
    _, m = pub
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    client.force_login(m["나"])
    RosterPref.objects.update_or_create(user=m["나"], defaults={"history": False})
    for url in ["/?date=2026-11-10", "/?view=month&date=2026-11-10", "/day/2026-11-10/"]:
        body = client.get(url).content.decode()
        assert 'lb exc' not in body and 'class="lb">가<' not in body, url
        assert 'class="lb">나<' in body, url
    assert "가 (휴가)" in client.get("/cell/2026-11-10/normal/").content.decode()


def test_cell_form_offers_reason_for_shift_cells_only(pub, client):
    _, m = pub
    client.force_login(m["나"])
    body = client.get("/cell/2026-11-10/normal/").content.decode()
    assert 'name="reason"' in body and "<option>휴가</option>" in body and "<option>교육</option>" in body
    assert 'name="reason"' not in client.get("/cell/2026-11-10/slot0/").content.decode()


def test_cell_post_sets_reason(pub, client):
    _, m = pub
    client.force_login(m["나"])
    r = client.post("/cell/2026-11-10/normal/", {"set_reason": "1", "member": m["가"].pk, "reason": "출장",
                                                 "next": "/day/2026-11-10/"}, follow=True)
    assert Commute.objects.get(member=m["가"]).reason == "출장"
    body = r.content.decode()
    assert "사유를 저장했습니다." in body and "장중관제 08:30~09:30 칸에 남아 있습니다" in body
    assert "가 (출장)" in client.get("/cell/2026-11-10/normal/").content.decode()  # From 목록에 지금 사유
    r = client.post("/cell/2026-11-10/normal/", {"set_reason": "1", "member": m["가"].pk, "reason": "출장"},
                    follow=True)
    assert "변경할 내용이 없습니다." in r.content.decode()
    r = client.post("/cell/2026-11-10/normal/", {"set_reason": "1", "member": "x", "reason": "휴가"}, follow=True)
    assert "사유를 붙일 사람을 골라 주세요." in r.content.decode()


def test_collect_table_explains_reason(collecting, client):
    p, dept, user = collecting
    client.force_login(user)
    assert "(휴가)처럼" in client.get(f"/collect/{p.pk}/{dept.code}/").content.decode()


def test_me_page_shows_reason(pub, it_board, client):
    _, m = pub
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    client.force_login(m["가"])
    assert "정상(휴가)" in client.get("/me/").content.decode()


# ── 근무로 치지 않음: 개인 알림·보고서·캘린더·관제 생성 후보·통계 ──

SUN18 = datetime(2026, 11, 15, 18)
MON = date(2026, 11, 16)


def _day(reasons=None, **cells):
    members = {c: [] for c in KEYS}
    members.update(cells)
    return Day(MON, 1, {}, members, {}, reasons or {})


def _rule(**kw):
    base = dict(id=1, member_name="가", kind="personal", timing="days", offset=1, at_minute=18 * 60,
                channels=("telegram",), shifts=("dawn",), depts=(), types=())
    return RuleSpec(**{**base, **kw})


def _plan(rules, days, deliveries=None):
    dests = {(r.id, ch): ["d"] for r in rules for ch in r.channels}
    return plan(IT_DEFS, rules, days, {"가": ("MEMS", "개발자"), "나": ("MEMS", "개발자")}, deliveries or {}, SUN18,
                destinations=dests)


def test_personal_alarm_skips_reason_and_sends_no_cancel():
    r = _rule()
    h_in = _plan([r], [_day(dawn=["가"])])[0].content_hash
    away = _day({("dawn", "가"): "휴가"}, dawn=["가"])
    assert _plan([r], [away]) == []
    assert _plan([r], [away], {(1, MON, "dawn", "telegram", "d"): h_in}) == []  # 이미 보낸 알림은 되돌리지 않는다


def test_personal_alarm_skips_all_cells_of_reason_day():
    r = _rule(shifts=())  # 전부
    assert {d.cell for d in _plan([r], [_day(dawn=["가"], slot0=["가"])])} == {"dawn", "slot0"}
    assert _plan([r], [_day({("dawn", "가"): "휴가"}, dawn=["가"], slot0=["가"])]) == []


def test_report_reason_is_per_person_day():
    r = _rule(kind="report", member_name=None, shifts=())
    due = _plan([r], [_day({("dawn", "가"): "휴가"}, dawn=["가", "나"], slot0=["가"])])[0]
    assert "08:30~09:30 가(휴가)" in due.text.split("\n")
    assert due.push_text.endswith("· 1명")


def test_report_shows_name_with_reason():
    r = _rule(kind="report", member_name=None, shifts=("dawn", "normal"))
    plain = _plan([r], [_day(dawn=["가", "나"])])[0]
    due = _plan([r], [_day({("dawn", "가"): "출장"}, dawn=["가", "나"])])[0]
    assert due.text.split("\n")[1] == "새벽(06:30~) 가(출장), 나"
    assert plain.text.split("\n")[1] == "새벽(06:30~) 가, 나"  # 사유가 없으면 지금 문구 그대로
    assert due.content_hash != plain.content_hash
    assert due.push_text.endswith("· 1명")  # 근무로 치는 사람만 센다


def test_calendar_skips_reason_day(pub, it_board, settings):
    _, m = pub
    settings.SITE_URL = "https://duty.example"
    assert [e.summary for e in calendar._events(m["가"])] == ["정상 출근 08:00~17:00", "장중관제 08:30~09:30"]
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    assert calendar._events(m["가"]) == []  # 사유가 있는 날은 당번 칸 일정도 뺀다(그날 근무로 치지 않는다)


def test_generation_skips_reason_commutes(make_member, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=MON, end_date=MON, status=S.CLOSED)
    away = make_member("휴가자", dept="MEMS")
    Commute.objects.create(period=p, date=MON, member=away, shift="normal", reason="휴가")
    for i in range(5):
        Commute.objects.create(period=p, date=MON, member=make_member(f"N{i}", dept="MEMS"), shift="normal")
        Commute.objects.create(period=p, date=MON, member=make_member(f"D{i}", dept="TMCH"), shift="dinner")
    for dept in ("MD", "UI"):
        Commute.objects.create(period=p, date=MON, member=make_member(f"직원{dept}", dept=dept, type="직원"), shift="normal")
    run_generation(p, seed=3)
    assert DutyAssignment.objects.filter(period=p).count() == 10
    assert not DutyAssignment.objects.filter(member=away).exists()


def test_stats_count_only_real_work(make_member, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=MON, end_date=MON + timedelta(days=1),
                              status=S.PUBLISHED, overwrite_from=MON)
    a, b = make_member("가"), make_member("나")
    Commute.objects.create(period=p, date=MON, member=a, shift="dawn", reason="교육")
    Commute.objects.create(period=p, date=MON + timedelta(days=1), member=a, shift="night")
    Commute.objects.create(period=p, date=MON, member=b, shift="normal", reason="휴가")
    rows, _, _ = stats.member_stats(it_board, None, None)
    assert {(r.name, r.dawn, r.night) for r in rows} == {("가", 0, 1), ("나", 0, 0)}
    assert stats.period_duty_counts(p)[0] == []  # 관제 자격 출근이 사유뿐이면 모집단에서 빠진다(생성 후보와 같다)


def test_stats_skip_duties_on_reason_day(make_member, it_board):
    """사유가 생기기 전에 남은 당번 배정은 그날 근무로 치지 않는다."""
    p = Period.objects.create(board=it_board, name="p", start_date=MON, end_date=MON + timedelta(days=1),
                              status=S.PUBLISHED, overwrite_from=MON)
    a = make_member("가")
    Commute.objects.create(period=p, date=MON, member=a, shift="normal", reason="휴가")
    Commute.objects.create(period=p, date=MON + timedelta(days=1), member=a, shift="normal")
    for d in (MON, MON + timedelta(days=1)):
        DutyAssignment.objects.create(period=p, date=d, cell="slot0", member=a)
    rows, _, _ = stats.member_stats(it_board, None, None)
    assert [(r.name, r.duty) for r in rows] == [("가", 1)]
    assert stats.period_duty_counts(p)[0] == [("가", 1)]


# ── 배포·배포 취소: publish_undo 의 c 행 여섯째 칸 ──

def test_publish_undo_keeps_reason(make_member, it_board):
    a = Period.objects.create(board=it_board, name="A", start_date=MON, end_date=MON + timedelta(days=1),
                              status=S.PUBLISHED, overwrite_from=MON, published_at=NOW)
    b = Period.objects.create(board=it_board, name="B", start_date=MON, end_date=MON + timedelta(days=1), status=S.GENERATED)
    ga, na = make_member("가"), make_member("나")
    Commute.objects.create(period=a, date=MON, member=ga, shift="dawn", reason="휴가")
    Commute.objects.create(period=a, date=MON + timedelta(days=1), member=na, shift="normal")
    DutyAssignment.objects.create(period=a, date=MON, cell="slot0", member=na)
    publish.publish(b, MON)
    b.refresh_from_db()
    assert sorted(b.publish_undo) == sorted([
        ["c", a.pk, "2026-11-16", ga.pk, "dawn", "휴가"], ["c", a.pk, "2026-11-17", na.pk, "normal", ""],
        ["a", a.pk, "2026-11-16", na.pk, "slot0"]])
    publish.unpublish(b)
    assert Commute.objects.get(period=a, member=ga).reason == "휴가"


def test_unpublish_reads_old_rows_without_reason(make_member, it_board):
    a = Period.objects.create(board=it_board, name="A", start_date=MON, end_date=MON, status=S.GENERATED)
    b = Period.objects.create(board=it_board, name="B", start_date=MON, end_date=MON, status=S.GENERATED)
    publish.publish(b, MON)
    ga = make_member("가")
    Period.objects.filter(pk=b.pk).update(publish_undo=[["c", a.pk, "2026-11-16", ga.pk, "dawn"]])  # 2단계 전 배포
    publish.unpublish(Period.objects.get(pk=b.pk))
    assert Commute.objects.get(period=a, member=ga).reason == ""
