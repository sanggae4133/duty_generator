"""만드는 도구의 휴장일·근무 없음 건너뛰기(설계 5·6.3·6.5). 이름은 모두 가상."""
from datetime import date

import pytest

from duty.csv_io import CsvInvalid
from duty.models import Board, Commute, DutyAssignment, Holiday, Memo, Period, User
from duty.services import boards, collect, periods
from duty.services.generate import run_generation

S = Period.Status
HOL = date(2026, 11, 11)     # 수: 시험용 휴장일(사람이 추가)
NOWORK = date(2026, 11, 12)  # 목: 근무 없음 날
CSV_HEAD = "date,새벽,정상,석식교대,야간\n"


def d(day):
    return date(2026, 11, day)


@pytest.fixture
def period(it_board, fixed_today):
    fixed_today(d(1))
    Holiday.objects.create(date=HOL, name="시험 휴장")
    Memo.objects.create(board=it_board, scope="day", date=NOWORK, text="워크숍", no_work=True)
    return Period.objects.create(board=it_board, name="p", start_date=d(9), end_date=d(13), status=S.COLLECTING)


# ── skip_dates ──

def test_skip_dates_are_no_work_days_and_holidays(period):
    assert boards.skip_dates(period) == {HOL, NOWORK}
    assert boards.skip_reasons(period) == {HOL: "시험 휴장", NOWORK: "워크숍"}


def test_old_period_keeps_holidays_but_never_no_work_days(period):
    period.skip_holidays = False  # 2단계 전에 만든 회차: 휴장일 규칙 미적용
    period.save()
    assert boards.skip_dates(period) == {NOWORK}


def test_inactive_holiday_and_other_board_memo_do_not_count(period, it_board):
    Holiday.objects.filter(date=HOL).update(active=False)
    other = Board.objects.create(code="ops", name="시장운영실", input_mode="direct")
    Memo.objects.create(board=other, scope="day", date=d(13), text="딴 근무표", no_work=True)
    Memo.objects.create(board=it_board, scope="day", date=d(10), text="그냥 메모")
    assert boards.skip_dates(period) == {NOWORK}


def test_empty_no_work_memo_reason(period):
    Memo.objects.filter(date=NOWORK).update(text="")
    assert boards.skip_reasons(period)[NOWORK] == "근무 없음"


# ── 빈 날 검사·입력 현황 ──

def _fill(period, members, days):
    for day in days:
        for m in members:
            Commute.objects.create(period=period, date=day, member=m, shift="normal")


def test_missing_dates_and_progress_skip_closed_days(period, make_member):
    ms = [make_member(n, dept=c) for n, c in [("가", "MEMS"), ("나", "TMCH"), ("다", "MD"), ("라", "UI")]]
    _fill(period, ms, [d(9), d(10), d(13)])
    assert periods.missing_dates(period) == {}
    assert collect.progress(period)["MEMS"] == (3, 3)
    Commute.objects.filter(date=d(13), member=ms[3]).delete()
    assert periods.missing_dates(period) == {"UI": [d(13)]}
    assert collect.progress(period)["UI"] == (2, 3)


def test_missing_dates_old_period_counts_holiday(period, make_member):
    period.skip_holidays = False
    period.save()
    ms = [make_member(n, dept=c) for n, c in [("가", "MEMS"), ("나", "TMCH"), ("다", "MD"), ("라", "UI")]]
    _fill(period, ms, [d(9), d(10), d(13)])
    assert periods.missing_dates(period) == {c: [HOL] for c in ["MD", "MEMS", "TMCH", "UI"]}
    assert collect.progress(period)["MEMS"] == (3, 4)


# ── 출근표 입력(서비스·CSV) ──

@pytest.fixture
def mems(period, depts, make_member):
    mgr = make_member("담당", user=True)
    depts["MEMS"].input_group.user_set.add(mgr)
    for n in ["가", "나"]:
        make_member(n)
    return period, depts["MEMS"], mgr


def test_csv_with_names_on_closed_day_is_rejected(mems):
    p, dept, user = mems
    raw = CSV_HEAD + f"{d(10)},가,,,\n{HOL},나,,,\n{NOWORK},,가,,\n"
    with pytest.raises(CsvInvalid) as e:
        collect.apply_csv(user, p, dept, raw.encode())
    got = {(x.column, x.reason) for x in e.value.errors}
    assert got == {(HOL.isoformat(), "시험 휴장: 근무를 넣지 않는 날입니다."),
                   (NOWORK.isoformat(), "워크숍: 근무를 넣지 않는 날입니다.")}
    assert not Commute.objects.exists()


def test_empty_closed_day_row_is_fine(mems):
    p, dept, user = mems
    raw = CSV_HEAD + f"{d(10)},가,,,\n{HOL},,,,\n"
    assert collect.apply_csv(user, p, dept, raw.encode()) == 1


def test_old_period_accepts_names_on_holiday(mems):
    p, dept, user = mems
    p.skip_holidays = False
    p.save()
    assert collect.apply_csv(user, p, dept, (CSV_HEAD + f"{HOL},나,,,\n").encode()) == 1


def test_save_keeps_rows_already_on_closed_day(mems, fixed_today):
    """휴장일을 나중에 추가해도 이미 넣은 행은 지우지 않는다(설계 5). 지난 날짜여도 일반 담당자의 저장을 막지 않는다."""
    p, dept, user = mems
    na = User.objects.get(name="나")
    Commute.objects.create(period=p, date=HOL, member=na, shift="dawn")
    fixed_today(d(12))  # HOL 은 지난 날짜
    assert collect.apply_table(user, p, dept, {d(13): {"normal": ["가"]}}) == 1
    assert set(Commute.objects.values_list("date", flat=True)) == {HOL, d(13)}


def test_export_leaves_closed_day_empty(mems):
    p, dept, user = mems
    Commute.objects.create(period=p, date=HOL, member=User.objects.get(name="나"), shift="dawn")
    lines = collect.export_csv(p, dept).decode("utf-8-sig").splitlines()
    assert lines[3] == f"{HOL},수,,,,"
    collect.apply_csv(user, p, dept, collect.export_csv(p, dept))  # 내려받은 그대로 다시 올려도 된다


# ── 출근표 입력 표(화면) ──

def test_table_locks_closed_rows(client, mems):
    p, dept, user = mems
    client.force_login(user)
    body = client.get(f"/collect/{p.pk}/MEMS/").content.decode()
    assert f'name="c_{HOL}_dawn" value="" disabled' in body
    assert f'name="c_{NOWORK}_normal" value="" disabled' in body
    assert f'name="c_{d(10)}_dawn" value="" >' in body
    assert '<small class="hol" title="시험 휴장">시험 휴장</small>' in body
    assert '<small class="hol" title="워크숍">워크숍</small>' in body


def test_table_post_on_closed_day_is_rejected(client, mems):
    p, dept, user = mems
    client.force_login(user)
    r = client.post(f"/collect/{p.pk}/MEMS/", {f"c_{HOL}_dawn": "가", f"c_{d(10)}_dawn": "나"})
    assert r.status_code == 400 and "시험 휴장: 근무를 넣지 않는 날입니다." in r.content.decode()
    assert not Commute.objects.exists()


# ── 생성 ──

@pytest.fixture
def staffed(period, make_member):
    """test_generate 와 같은 인원(관제 10칸이 다 차는). days 에만 출근표를 넣는다."""
    normal = [make_member(f"N{i}", dept="MEMS") for i in range(7)] + [make_member("엠", dept="MD", type="직원"),
                                                                     make_member("유", dept="UI", type="직원")]
    dinner = [make_member(f"D{i}", dept="TMCH") for i in range(7)]

    def fill(days):
        for x in days:
            Commute.objects.bulk_create([Commute(period=period, date=x, member=m, shift="normal") for m in normal]
                                        + [Commute(period=period, date=x, member=m, shift="dinner") for m in dinner])
    period.status = S.CLOSED
    period.save()
    return period, fill


def test_generation_skips_closed_days(staffed):
    p, fill = staffed
    fill([d(9), d(10), d(13)])  # 건너뛰는 날은 출근표가 비어도 생성된다
    run_generation(p, seed=5)
    assert set(DutyAssignment.objects.values_list("date", flat=True)) == {d(9), d(10), d(13)}


def test_generation_ignores_rows_left_on_holiday(staffed):
    p, fill = staffed
    fill(p.dates())  # 휴장일을 나중에 추가해 행이 남아 있어도 관제는 만들지 않는다
    run_generation(p, seed=5)
    assert HOL not in set(DutyAssignment.objects.values_list("date", flat=True))
    assert Commute.objects.filter(date=HOL).exists()


def test_old_period_generates_on_holiday(staffed):
    p, fill = staffed
    p.skip_holidays = False
    p.save()
    fill([d(9), d(10), HOL, d(13)])
    run_generation(p, seed=5)
    assert set(DutyAssignment.objects.values_list("date", flat=True)) == {d(9), d(10), HOL, d(13)}
