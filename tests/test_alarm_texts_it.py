"""IT 정의로 만든 알림 문구·hash 가 1단계 전과 한 글자도 같다(hash 가 달라지면 최근 45일 알림이 다시 나간다)."""
from datetime import date, datetime

from duty.alarms import messages as m
from duty.alarms.plan import RuleSpec, plan
from duty.alarms.schedule import same_day_notice
from duty.shifts import Day
from duty.shifts import KEYS
from tests.it_defs import IT_DEFS

D = date(2026, 11, 16)  # 월
E = date(2026, 11, 10)  # 화
SUN18 = datetime(2026, 11, 15, 18)
INFO = {"가": ("MEMS", "개발자"), "나": ("MEMS", "직원"), "다": ("OTH", "개발자")}
DESTS = {(1, "telegram"): ["d"]}
REPORT_BODY = ("새벽(06:30~) 가\n정상(08:00~) 나\n석식교대(09:00~) -\n08:30~09:30 나\n09:30~10:30 -\n"
               "10:30~11:30 -\n11:30~12:30 -\n12:30~13:30 -\n13:30~14:30 -\n14:30~15:30 -\n15:30~16:30 -\n"
               "16:30~17:00 -\n17:00~18:00 -\n야간(13:30~) -")


def day(replaced=None, **cells):
    members = {c: [] for c in KEYS}
    members.update({k: list(v) for k, v in cells.items()})
    return Day(D, 1, {}, members, replaced or {})


def rule(**kw):
    base = dict(id=1, member_name="가", kind="personal", timing="days", offset=1, at_minute=18 * 60,
                channels=("telegram",), shifts=("dawn",), depts=(), types=())
    return RuleSpec(**{**base, **kw})


def run(r, d, deliveries=None, **kw):
    return plan(IT_DEFS, [r], [d], INFO, deliveries or {}, SUN18, destinations=DESTS, **kw)


def test_personal_shift():
    [due] = run(rule(), day(dawn=["가"]))
    assert (due.title, due.text, due.content_hash, due.url, due.expires_at) == (
        "당번 알림", "[당번 알림] 11/16(월) 새벽 06:30~15:30\n가님, 내일 새벽 당번입니다.", "in:b67c7c6d5f7f719a",
        "/day/2026-11-16/", datetime(2026, 11, 16, 6, 30))
    assert due.push_text == due.text  # 푸시도 텔레그램과 같은 글(줄바꿈 그대로)


def test_personal_slot():
    [due] = run(rule(shifts=("slots",)), day(slot0=["가"]))
    assert (due.cell, due.text, due.content_hash, due.expires_at) == (
        "slot0", "[당번 알림] 11/16(월) 08:30~09:30\n가님, 내일 장중관제입니다.", "in:c4693d2be729b43f",
        datetime(2026, 11, 16, 8, 30))


def test_cancel():
    sent = {(1, D, "dawn", "telegram", "d"): "in:b67c7c6d5f7f719a"}
    [due] = run(rule(), day(dawn=["나"], replaced={("dawn", "나"): "가"}), sent)
    assert (due.title, due.text, due.content_hash) == (
        "당번 변경", "[당번 변경] 11/16(월) 새벽 06:30~15:30\n가님의 근무가 취소되었습니다. (후임: 나)",
        "out:3b1b539a890431ae")


def test_report_full_text():
    r = rule(kind="report", member_name=None, shifts=(), depts=("MEMS",))
    d = day(dawn=["가"], normal=["나"], slot0=["나"], night=["다"])
    [due] = run(r, d, dept_names={"MEMS": "매칭엔진실"})
    assert (due.title, due.text, due.content_hash, due.push_text, due.url, due.expires_at) == (
        "출근표", "[출근표] 11/16(월) — 매칭엔진실\n" + REPORT_BODY, "report:1b8af80d11eb4183",
        "[출근표] 11/16(월) — 매칭엔진실\n" + REPORT_BODY, "/day/2026-11-16/", datetime(2026, 11, 16, 17, 0))  # 푸시도 전체
    [changed] = run(r, d, {(1, D, "report", "telegram", "d"): "old"}, dept_names={"MEMS": "매칭엔진실"})
    assert changed.text == "[출근표 변경] 11/16(월) — 매칭엔진실\n" + REPORT_BODY
    assert changed.content_hash == "report:1b8af80d11eb4183"
    assert dict(changed.cells) == {"dawn": "가", "normal": "나", "dinner": "-", "slot0": "나", **{
        f"slot{i}": "-" for i in range(1, 10)}, "night": "-"}


def test_report_change_diff_lines():
    """출근표 변경: 그 목적지에 마지막으로 보낸 칸과 달라진 칸만 '전 → 후'. 표지·바뀐 칸은 hash 에 넣지 않는다."""
    r = rule(kind="report", member_name=None, shifts=(), depts=("MEMS",))
    d = day(dawn=["가"], normal=["나"], slot0=["나"], night=["다"])
    key = (1, D, "report", "telegram", "d")
    [base] = run(r, d, dept_names={"MEMS": "매칭엔진실"})
    old = {**dict(base.cells), "normal": "-", "slot0": "가"}
    [ch] = run(r, d, {key: "old"}, dept_names={"MEMS": "매칭엔진실"}, sent_cells={key: old})
    assert ch.text == ("[출근표 변경] 11/16(월) — 매칭엔진실\n바뀐 칸\n▶ 정상(08:00~) - → 나\n▶ 08:30~09:30 가 → 나\n"
                       "지금 출근표\n" + REPORT_BODY)
    assert ch.push_text == ch.text and ch.content_hash == base.content_hash


def test_change_notices():
    """변경 알림: 칸 시각과 오늘·내일을 붙이고, 넣기는 'B 추가'(US-CHANGE-TEXT)."""
    assert m.change_notice(IT_DEFS, E, D, "slot0", "가", "나", "관리자") == (
        "근무 변경", "[근무 변경] 가 → 나\n11/10(화) 장중관제 08:30~09:30\n바꾼 사람: 관리자")
    assert m.change_notice(IT_DEFS, E, E, "normal", None, "나", "관리자") == (
        "근무 변경", "[근무 변경] 나 추가\n오늘 11/10(화) 정상 08:00~17:00\n바꾼 사람: 관리자")
    assert m.change_notice(IT_DEFS, E, date(2026, 11, 9), "night", "가", None, "관리자") == (
        "근무 변경", "[근무 변경] 가 빠짐\n내일 11/10(화) 야간 13:30~21:30\n바꾼 사람: 관리자")
    assert m.swap_notice(IT_DEFS, E, D, "normal", "가", "dinner", "나", "다") == (
        "근무 변경", "[근무 변경] 맞교환 가 ↔ 나\n▶ 가 정상 → 석식교대\n▶ 나 석식교대 → 정상\n11/10(화)\n바꾼 사람: 다")


def test_same_day_notices():
    assert same_day_notice(IT_DEFS, "personal", "days", 0, 10 * 60, []) == \
        "새벽·정상·석식교대·장중관제 08:30~10:30은 발송 시각이 근무 시작 이후라 제외됩니다."
    assert same_day_notice(IT_DEFS, "report", "days", 0, 17 * 60, []) == "현재 선택으로는 보고서가 발송되지 않습니다."
    assert same_day_notice(IT_DEFS, "personal", "days", 0, 20 * 60, ["slots", "night"]) == \
        "현재 선택으로는 발송되는 근무가 없습니다."
