from datetime import date, datetime

from duty.alarms.plan import RuleSpec, plan
from duty.services.roster import Day
from duty.shifts import CELLS

D = date(2026, 11, 16)  # 월
INFO = {"가": ("MEMS", "개발자"), "나": ("MEMS", "직원"), "다": ("OTH", "개발자")}


def day(d=D, replaced=None, **cells):
    members = {c: [] for c in CELLS}
    members.update({k: list(v) for k, v in cells.items()})
    return Day(d, 1, {}, members, replaced or {})


def rule(**kw):
    base = dict(id=1, member_name="가", kind="personal", timing="days", offset=1, at_minute=18 * 60,
                channels=("telegram",), shifts=("dawn",), depts=(), types=())
    base.update(kw)
    return RuleSpec(**base)


def run(rules, days, now, deliveries=None, **kw):
    return plan(rules, days, INFO, deliveries or {}, now, **kw)


SUN18 = datetime(2026, 11, 15, 18)


def test_personal_window():
    d = [day(dawn=["가"])]
    due = run([rule()], d, SUN18)
    assert len(due) == 1 and due[0].content_hash == "in"
    assert "가님, 내일 새벽 당번" in due[0].text and due[0].text.startswith("[당번 알림] 11/16(월) 새벽 06:30~15:30")
    assert due[0].expires_at == datetime(2026, 11, 16, 6, 30)
    assert run([rule()], d, datetime(2026, 11, 15, 17, 59)) == []
    assert run([rule()], d, datetime(2026, 11, 16, 6, 30)) == []


def test_resend_cancel_and_back():
    k = (1, D, "dawn", "telegram")
    assert run([rule()], [day(dawn=["가"])], SUN18, {k: "in"}) == []
    due = run([rule()], [day(dawn=["나"], replaced={("dawn", "나"): "가"})], SUN18, {k: "in"})
    assert len(due) == 1 and due[0].content_hash == "out" and "후임: 나" in due[0].text and due[0].title == "당번 변경"
    assert run([rule()], [day(dawn=["나"])], SUN18) == []
    assert len(run([rule()], [day(dawn=["가"])], SUN18, {k: "out"})) == 1


def test_cancel_for_missing_date():
    k = (1, D, "dawn", "telegram")
    due = run([rule()], [], SUN18, {k: "in"}, extra_dates={D})
    assert len(due) == 1 and due[0].content_hash == "out"


def test_channels_and_filters():
    d = [day(dawn=["가"], normal=["가"])]
    assert len(run([rule(channels=("telegram", "push"))], d, SUN18)) == 2
    assert run([rule(shifts=("normal",), offset=0, at_minute=0)], [day(normal=["가"])], datetime(2026, 11, 16, 0, 1))[0].cell == "normal"
    assert run([rule(shifts=("night",))], d, SUN18) == []
    assert run([rule(member_name=None)], d, SUN18) == []


def test_slot_before_start():
    r = rule(shifts=("slots",), timing="before_start", offset=60)
    d = [day(slot2=["가"])]
    due = run([r], d, datetime(2026, 11, 16, 9, 30))
    assert len(due) == 1 and due[0].expires_at == datetime(2026, 11, 16, 10, 30)
    assert "10:30~11:30" in due[0].text and "장중당번" in due[0].text
    assert run([r], d, datetime(2026, 11, 16, 9, 29)) == []


def rep(**kw):
    return rule(**{"kind": "report", "member_name": None, **kw})


def test_report_filter_and_change():
    r = rep(depts=("MEMS",), types=("개발자",), shifts=("dawn", "normal"))
    d = [day(dawn=["가", "나", "다"], normal=["다"])]
    due = run([r], d, SUN18, dept_names={"MEMS": "매칭엔진실"})
    assert len(due) == 1
    t = due[0].text.split("\n")
    assert t[0] == "[출근표] 11/16(월) — 매칭엔진실·개발자"
    assert t[1] == "새벽(06:30~) 가" and t[2] == "정상(08:00~) -"
    k = (1, D, "report", "telegram")
    assert run([r], d, SUN18, {k: due[0].content_hash}) == []
    d2 = [day(dawn=["가"], normal=["가"])]
    ch = run([r], d2, SUN18, {k: due[0].content_hash})
    assert len(ch) == 1 and ch[0].text.startswith("[출근표 변경]") and ch[0].cell == "report"


def test_report_window_and_expiry():
    r = rep(shifts=("night",))
    d = [day(night=["가"])]
    assert run([r], d, datetime(2026, 11, 15, 18))[0].expires_at == datetime(2026, 11, 16, 13, 30)
    assert run([r], d, datetime(2026, 11, 16, 13, 30)) == []
    # 창은 가장 늦은 시작까지: dawn 시작 후에도 night 전이면 발송
    r2 = rep(shifts=("dawn", "night"))
    due = run([r2], [day(dawn=["가"], night=["나"])], datetime(2026, 11, 16, 7))
    assert len(due) == 1 and due[0].expires_at == datetime(2026, 11, 16, 13, 30)


def test_report_missing_date_change():
    r = rep(shifts=("dawn",))
    k = (1, D, "report", "telegram")
    due = run([r], [], SUN18, {k: "old"}, extra_dates={D})
    assert len(due) == 1 and due[0].text.startswith("[출근표 변경]")


def test_length_limits():
    r = rep(shifts=("slots",))
    info = {f"사람{i}가나다라마바사": ("MEMS", "개발자") for i in range(400)}
    names = list(info)
    d = [day(slot0=names, slot1=names)]
    due = plan([r], d, info, {}, SUN18)[0]
    assert len(due.text) == 4000 and due.text.endswith("(이하 생략, 웹에서 확인)")
    assert len(due.push_text.encode()) <= 1000
    p = plan([rule(shifts=("dawn",))], [day(dawn=["가"])], INFO, {}, SUN18)[0]
    assert len(p.push_text.encode()) <= 1000 and "\n" not in p.push_text
