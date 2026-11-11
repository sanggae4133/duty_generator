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


def dests(rules):
    return {(r.id, ch): ["d"] for r in rules for ch in r.channels}


def run(rules, days, now, deliveries=None, **kw):
    kw.setdefault("destinations", dests(rules))
    return plan(rules, days, INFO, deliveries or {}, now, **kw)


def K(cell="dawn", ch="telegram", dest="d"):
    return (1, D, cell, ch, dest)


def first_hash(rules, days, now=None, deliveries=None):
    return run(rules, days, now or SUN18, deliveries)[0].content_hash


SUN18 = datetime(2026, 11, 15, 18)


def test_personal_window():
    d = [day(dawn=["가"])]
    due = run([rule()], d, SUN18)
    assert len(due) == 1 and due[0].content_hash.startswith("in:") and due[0].destination == "d"
    assert "가님, 내일 새벽 당번" in due[0].text and due[0].text.startswith("[당번 알림] 11/16(월) 새벽 06:30~15:30")
    assert due[0].expires_at == datetime(2026, 11, 16, 6, 30)
    assert run([rule()], d, datetime(2026, 11, 15, 17, 59)) == []
    assert run([rule()], d, datetime(2026, 11, 16, 6, 30)) == []


def test_resend_cancel_and_back():
    k = K()
    h_in = first_hash([rule()], [day(dawn=["가"])])
    assert run([rule()], [day(dawn=["가"])], SUN18, {k: h_in}) == []
    due = run([rule()], [day(dawn=["나"], replaced={("dawn", "나"): "가"})], SUN18, {k: h_in})
    assert len(due) == 1 and due[0].content_hash.startswith("out:") and "후임: 나" in due[0].text and due[0].title == "당번 변경"
    assert run([rule()], [day(dawn=["나"])], SUN18) == []
    h_out = run([rule()], [day()], SUN18, {k: h_in})[0].content_hash
    due = run([rule()], [day(dawn=["가"])], SUN18, {k: h_out})
    assert len(due) == 1 and due[0].content_hash == h_in


def test_today_and_midnight_rollover():
    r = [rule(offset=2)]
    d = [day(dawn=["가"])]
    sat = run(r, d, datetime(2026, 11, 14, 18))[0]
    assert "가님, 11/16(월) 새벽 당번" in sat.text
    # 자정이 지나 '내일'이 되어도 같은 내용으로 보고 다시 보내지 않음
    sun = run(r, d, datetime(2026, 11, 15, 0, 1), {K(): sat.content_hash})
    assert sun == []
    # 문구의 오늘/내일은 today 인자 기준
    t = run(r, d, datetime(2026, 11, 14, 18), today=date(2026, 11, 15))[0].text
    assert "내일 새벽 당번" in t


def test_destinations():
    d = [day(dawn=["가"])]
    assert run([rule()], d, SUN18, destinations={}) == []
    due = run([rule(channels=("telegram", "push"))], d, SUN18,
              destinations={(1, "telegram"): ["c1"], (1, "push"): ["sub:1", "sub:2"]})
    assert sorted((x.channel, x.destination) for x in due) == [("push", "sub:1"), ("push", "sub:2"), ("telegram", "c1")]
    h = due[0].content_hash
    # 성공 기록은 목적지별: sub:1만 받았으면 sub:2와 c1만 다시
    due = run([rule(channels=("telegram", "push"))], d, SUN18, {K(ch="push", dest="sub:1"): h},
              destinations={(1, "telegram"): ["c1"], (1, "push"): ["sub:1", "sub:2"]})
    assert sorted(x.destination for x in due) == ["c1", "sub:2"]


def test_no_cancel_without_successful_first():
    # 첫 알림이 성공하지 못한(last_sent None) 목적지에는 취소를 보내지 않음
    assert run([rule()], [day()], SUN18, {K(): None}) == []
    assert run([rule()], [], SUN18, {K(): None}, extra_dates={D}) == []


def test_cancel_for_missing_date():
    h_in = first_hash([rule()], [day(dawn=["가"])])
    due = run([rule()], [], SUN18, {K(): h_in}, extra_dates={D})
    assert len(due) == 1 and due[0].content_hash.startswith("out:") and "후임" not in due[0].text


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
    k = K("report")
    names = {"MEMS": "매칭엔진실"}
    assert run([r], d, SUN18, {k: due[0].content_hash}, dept_names=names) == []
    d2 = [day(dawn=["가"], normal=["가"])]
    ch = run([r], d2, SUN18, {k: due[0].content_hash}, dept_names=names)
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
    due = run([r], [], SUN18, {K("report"): "old"}, extra_dates={D})
    assert len(due) == 1 and due[0].text.startswith("[출근표 변경]")


def test_length_limits():
    r = rep(shifts=("slots",))
    info = {f"사람{i}가나다라마바사": ("MEMS", "개발자") for i in range(400)}
    names = list(info)
    d = [day(slot0=names, slot1=names)]
    due = plan([r], d, info, {}, SUN18, dests([r]))[0]
    assert len(due.text) == 4000 and due.text.endswith("(이하 생략, 웹에서 확인)")
    assert len(due.push_text.encode()) <= 1000
    p = plan([rule(shifts=("dawn",))], [day(dawn=["가"])], INFO, {}, SUN18, dests([rule()]))[0]
    assert len(p.push_text.encode()) <= 1000 and "\n" not in p.push_text


def test_successor_chain_and_updates():
    k = K()
    r = [rule()]
    h_in = first_hash(r, [day(dawn=["가"])])
    # A>B>C: 현재 C
    d = day(dawn=["다"], replaced={("dawn", "나"): "가", ("dawn", "다"): "나"})
    due = run(r, [d], SUN18, {k: h_in})
    assert "후임: 다" in due[0].text and due[0].content_hash.startswith("out:")
    h_c = due[0].content_hash
    # A>B 후 B 제거: 후임 없음
    d = day(dawn=[], replaced={("dawn", "나"): "가"})
    due = run(r, [d], SUN18, {k: h_in})
    assert "후임" not in due[0].text and due[0].content_hash.startswith("out:")
    # 보낸 뒤 후임이 바뀌면 다시 보냄, 같으면 안 보냄
    h_b = run(r, [day(dawn=["나"], replaced={("dawn", "나"): "가"})], SUN18, {k: h_in})[0].content_hash
    d = day(dawn=["다"], replaced={("dawn", "나"): "가", ("dawn", "다"): "나"})
    assert run(r, [d], SUN18, {k: h_b})[0].content_hash == h_c != h_b
    assert run(r, [d], SUN18, {k: h_c}) == []
    # 재진입
    assert run(r, [day(dawn=["가"])], SUN18, {k: h_c})[0].content_hash == h_in


def test_report_unique_count():
    r = rep(shifts=("slots",))
    due = run([r], [day(slot0=["가"], slot1=["가"], slot2=["나"])], SUN18)[0]
    assert due.push_text.endswith("2명")


def test_synthetic_day_no_first_report():
    r = rep(shifts=("dawn",))
    assert run([r], [], SUN18, extra_dates={D}) == []


def test_unknown_kind_ignored():
    assert run([rule(kind="weird")], [day(dawn=["가"])], SUN18) == []


def test_personal_multi_slot_and_unknown_info():
    r = rule(shifts=("slots",), timing="before_start", offset=60)
    due = run([r], [day(slot2=["가"], slot3=["가"])], datetime(2026, 11, 16, 9, 30))
    assert [x.cell for x in due] == ["slot2"]  # slot3(11:30)은 아직 창 전
    r = rule(shifts=("slots",), timing="days", offset=1)
    due = run([r], [day(slot2=["가"], slot3=["가"])], SUN18)
    assert sorted(x.cell for x in due) == ["slot2", "slot3"]
    rp = rep(shifts=("dawn",), depts=("MEMS",))
    assert "미상" not in run([rp], [day(dawn=["미상", "가"])], SUN18)[0].text
    assert "미상" in run([rep(shifts=("dawn",))], [day(dawn=["미상", "가"])], SUN18)[0].text


def test_successor_reverts_and_dash_name():
    k = K()
    h_in = first_hash([rule()], [day(dawn=["가"])])
    # A>B>A>C: replaced = {B:A, A:B, C:A}
    d = day(dawn=["다"], replaced={("dawn", "나"): "가", ("dawn", "가"): "나", ("dawn", "다"): "가"})
    assert "후임: 다" in run([rule()], [d], SUN18, {k: h_in})[0].text
    # A>B, B 제거, A 다시 추가, A>C
    d = day(dawn=["다"], replaced={("dawn", "나"): "가", ("dawn", "다"): "가"})
    assert "후임: 다" in run([rule()], [d], SUN18, {k: h_in})[0].text
    # 이름이 "-"인 후임은 후임 없음과 구분
    h_none = run([rule()], [day()], SUN18, {k: h_in})[0].content_hash
    d = day(dawn=["-"], replaced={("dawn", "-"): "가"})
    due = run([rule()], [d], SUN18, {k: h_none})
    assert due[0].content_hash != h_none and "후임: -" in due[0].text


def test_cancel_needs_personal_hash_prefix():
    # in:/out: 형식이 아닌 성공 기록(예: 잘못된 값)에는 취소를 보내지 않음
    assert run([rule()], [day()], SUN18, {K(): "garbage"}) == []
    assert run([rule()], [day()], SUN18, {K(): ""}) == []


def test_report_hash_prefixed():
    assert run([rep(shifts=("dawn",))], [day(dawn=["가"])], SUN18)[0].content_hash.startswith("report:")


def test_report_hash_covers_condition_text():
    r = rep(depts=("MEMS",), shifts=("dawn",))
    d = [day(dawn=["가"])]
    h = run([r], d, SUN18, dept_names={"MEMS": "매칭엔진실"})[0].content_hash
    ch = run([r], d, SUN18, {K("report"): h}, dept_names={"MEMS": "새이름실"})
    assert len(ch) == 1 and ch[0].text.startswith("[출근표 변경]") and ch[0].content_hash.startswith("report:")
