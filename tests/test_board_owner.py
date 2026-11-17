"""그날의 주인(설계 6.1)과 근무표 단위 조회·근무 변경: 근무표끼리 서로 영향이 없다. 이름은 모두 가상."""
from datetime import date, datetime, time
from datetime import timezone as dt_timezone

import pytest
from django.core.exceptions import PermissionDenied

from duty import shifts
from duty.errors import DutyError
from duty.models import Board, BoardShift, ChangeLog, Commute, Department, DutyAssignment, Period, PeriodEvent, User
from duty.services import boards, changes
from duty.services.roster import find_day, member_schedule, published_days
from tests.it_defs import OPS_STEPS

S = Period.Status


def d(m, day):
    return date(2026, m, day)


def at(m, day):
    return datetime(2026, m, day, tzinfo=dt_timezone.utc)


def published(board, name, start, end, frm=None, when=None, event=True):
    p = Period.objects.create(board=board, name=name, start_date=start, end_date=end, status=S.PUBLISHED,
                              overwrite_from=frm, published_at=when)
    if event:
        PeriodEvent.objects.create(period=p, from_status=S.GENERATED, to_status=S.PUBLISHED)
    return p


@pytest.fixture
def ops(it_board):
    """가짜 두 번째 근무표 '운영팀'(관리 그룹은 Board.save 가 만든다): 근무조 normal(주간) + 관제 slot0(점검A)."""
    board = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
    BoardShift.objects.create(board=board, key="normal", name="주간", start=time(9), end=time(18))
    BoardShift.objects.create(board=board, key="slot0", name="점검A", start=time(10), end=time(11),
                              eligible_shifts=["normal"], eligible_types=["개발자"])
    return board, Department.objects.create(code="OPS", name="운영", shifts="normal", board=board)


def ops_member(dept, name, type="직원"):
    return User.objects.create_user(f"OPS{User.objects.count():03d}", password="unused-Pw-123", name=name,
                                    department=dept, part="", type=type)


# ── 그날의 주인 ──

def test_owner_is_latest_publish_in_range(it_board):
    a = published(it_board, "A", d(11, 2), d(11, 27), frm=d(11, 2))
    b = published(it_board, "B", d(11, 16), d(12, 11), frm=d(11, 18))
    assert boards.owner(it_board, d(11, 17)) == a  # B 의 덮어쓰기 시작일 전
    assert boards.owner(it_board, d(11, 18)) == b
    assert boards.owner(it_board, d(12, 11)) == b
    assert boards.owner(it_board, d(12, 14)) is None
    assert boards.owner(it_board, d(10, 30)) is None


def test_owner_order_is_publish_event_not_clock(it_board):
    a = published(it_board, "A", d(11, 2), d(11, 27), when=at(11, 30))  # 시계는 늦지만 먼저 배포
    b = published(it_board, "B", d(11, 2), d(11, 27), when=at(11, 1))
    assert boards.owner(it_board, d(11, 10)) == b
    PeriodEvent.objects.create(period=a, from_status=S.GENERATED, to_status=S.PUBLISHED)  # A 를 다시 배포
    assert boards.owner(it_board, d(11, 10)) == a


def test_periods_without_publish_event_are_older(it_board):
    old1 = published(it_board, "옛1", d(11, 2), d(11, 27), when=at(11, 5), event=False)
    published(it_board, "옛2", d(11, 2), d(11, 27), when=at(11, 1), event=False)
    published(it_board, "옛3", d(11, 2), d(11, 27), when=None, event=False)  # published_at 없음 = 가장 오래됨
    assert boards.owner(it_board, d(11, 10)) == old1
    old4 = published(it_board, "옛4", d(11, 2), d(11, 27), when=at(11, 5), event=False)  # 같은 시각이면 pk 순
    assert boards.owner(it_board, d(11, 10)) == old4
    new = published(it_board, "새", d(11, 2), d(11, 27), when=at(10, 1))  # 이벤트 있는 회차가 더 최근
    assert boards.owner(it_board, d(11, 10)) == new


def test_owner_falls_back_to_start_date_and_ignores_unpublished(it_board):
    p = published(it_board, "p", d(11, 9), d(11, 13))  # overwrite_from 비어 있음 = 시작일부터
    Period.objects.create(board=it_board, name="g", start_date=d(11, 9), end_date=d(11, 13), status=S.GENERATED)
    assert boards.owner(it_board, d(11, 9)) == p


def test_owners_covers_weekdays_without_rows(it_board):
    a = published(it_board, "A", d(11, 2), d(11, 13), frm=d(11, 2))
    b = published(it_board, "B", d(11, 9), d(11, 20), frm=d(11, 11))
    assert boards.owners(it_board, d(11, 6), d(11, 23)) == {
        d(11, 6): a, d(11, 9): a, d(11, 10): a,
        d(11, 11): b, d(11, 12): b, d(11, 13): b,
        d(11, 16): b, d(11, 17): b, d(11, 18): b, d(11, 19): b, d(11, 20): b,
    }
    assert boards.owners(it_board, d(11, 19), None) == {d(11, 19): b, d(11, 20): b}  # None = 끝 없음
    assert boards.owners(it_board, d(12, 1), None) == {}


def test_owner_is_per_board(it_board, ops):
    board, _ = ops
    it = published(it_board, "IT", d(11, 9), d(11, 13))
    op = published(board, "운영", d(11, 9), d(11, 13))  # 나중에 배포했지만 다른 근무표
    assert boards.owner(it_board, d(11, 10)) == it
    assert boards.owner(board, d(11, 10)) == op
    assert set(boards.owners(it_board, d(11, 9), d(11, 13)).values()) == {it}


# ── 근무표 단위 조회 ──

def test_published_days_includes_owned_days_without_rows(it_board, make_member):
    p = published(it_board, "p", d(11, 9), d(11, 10))
    Commute.objects.create(period=p, date=d(11, 9), member=make_member("가"), shift="normal")
    days = published_days(it_board, d(11, 9), d(11, 10))
    assert [x.date for x in days] == [d(11, 9), d(11, 10)]
    assert days[1].period_id == p.pk and not any(days[1].members.values())
    assert list(days[0].cells) == [k for k in shifts.KEYS if k != shifts.LUNCH]  # 칸 순회 순서 = KEYS(알림 hash 불변)


def test_published_days_uses_only_owner_rows(it_board, make_member):
    a = published(it_board, "A", d(11, 9), d(11, 13))
    b = published(it_board, "B", d(11, 11), d(11, 13), frm=d(11, 11))
    ga, na = make_member("가"), make_member("나")
    Commute.objects.create(period=a, date=d(11, 11), member=ga, shift="normal")  # 덮어쓰인 회차의 행
    Commute.objects.create(period=b, date=d(11, 11), member=na, shift="normal")
    ChangeLog.objects.create(period=a, date=d(11, 11), cell="normal", before=None, after=ga)
    day = find_day(it_board, d(11, 11))
    assert day.period_id == b.pk and day.members["normal"] == ["나"] and not day.cells["normal"].changed


def test_published_days_per_board(it_board, ops, make_member):
    board, dept = ops
    it = published(it_board, "IT", d(11, 10), d(11, 10))
    op = published(board, "운영", d(11, 10), d(11, 10))
    Commute.objects.create(period=it, date=d(11, 10), member=make_member("가"), shift="normal")
    oa = ops_member(dept, "운영가")
    Commute.objects.create(period=op, date=d(11, 10), member=oa, shift="normal")
    [iday] = published_days(it_board, d(11, 10), d(11, 10))
    [oday] = published_days(board, d(11, 10), d(11, 10))
    assert iday.members["normal"] == ["가"] and oday.members["normal"] == ["운영가"]
    assert list(oday.cells) == ["normal", "slot0"]  # 그 근무표의 정의만
    assert member_schedule(board, oa, d(11, 10)) == [(d(11, 10), ["주간 09:00~18:00"])]


def test_cell_to_options_only_board_members(client, it_board, ops, make_member, fixed_today):
    """근무 변경 창 To 후보 = 그 근무표 부서의 재직자(설계 6.4·7절). 부서 필터가 비어(= 전체) 있어도 남의 근무표 사람은 없다."""
    fixed_today(d(11, 10))
    board, dept = ops
    p = published(it_board, "IT", d(11, 10), d(11, 10))
    a = make_member("가", user=True)
    make_member("나")
    Commute.objects.create(period=p, date=d(11, 10), member=a, shift="normal")
    ops_member(dept, "운영가")
    client.force_login(a)
    body = client.get("/cell/2026-11-10/normal/").content.decode()
    assert 'name="after"' in body and "나 · " in body  # 같은 근무표 사람은 To 에 있다
    assert "운영가" not in body


# ── 근무표 단위 근무 변경 ──

@pytest.fixture
def two(it_board, ops, make_member, fixed_today):
    fixed_today(d(11, 10))
    board, dept = ops
    it = published(it_board, "IT", d(11, 10), d(11, 11))  # pk 가 작다(옛 _owner 는 근무표 구분 없이 pk 순으로 골랐다)
    op = published(board, "운영", d(11, 10), d(11, 11))
    ga = make_member("가", user=True)
    oa, ob = ops_member(dept, "운영가"), ops_member(dept, "운영나")
    Commute.objects.create(period=it, date=d(11, 10), member=ga, shift="normal")
    Commute.objects.create(period=op, date=d(11, 10), member=oa, shift="normal")
    return it, op, ga, oa, ob


def test_change_on_ops_board_uses_ops_owner(two, ops, it_board):
    it, op, ga, oa, ob = two
    board, _ = ops
    changes.change_cell(oa, board, d(11, 10), "normal", oa, ob)
    assert Commute.objects.get(member=ob).period == op
    assert ChangeLog.objects.get().period == op
    assert Commute.objects.get(member=ga).period == it  # IT 근무표는 그대로
    assert find_day(it_board, d(11, 10)).members["normal"] == ["가"]


def test_add_on_owned_day_without_rows(two, ops):
    _, op, _, oa, ob = two
    board, _ = ops
    changes.change_cell(oa, board, d(11, 11), "normal", None, ob)  # 행이 없어도 기간으로 주인이 있다
    assert Commute.objects.get(member=ob, date=d(11, 11)).period == op


def test_other_board_member_cannot_be_assigned(two, it_board):
    _, _, ga, oa, _ = two
    with pytest.raises(DutyError, match="운영가은\\(는\\) 근무표 대상이 아닙니다"):
        changes.change_cell(ga, it_board, d(11, 10), "normal", ga, oa)
    assert not ChangeLog.objects.exists()


def test_other_board_user_cannot_edit(two, it_board):
    _, _, ga, oa, _ = two
    with pytest.raises(PermissionDenied, match="이 근무표를 바꿀 권한이 없습니다"):
        changes.exchange(oa, it_board, d(11, 10), "normal", ga, None)
    assert Commute.objects.filter(member=ga).exists()


def test_cell_must_be_defined_on_board(two, ops):
    _, _, _, oa, ob = two
    board, _ = ops
    with pytest.raises(DutyError, match="알 수 없는 칸"):
        changes.change_cell(oa, board, d(11, 10), "dawn", None, ob)


def test_eligibility_warning_reads_board_defs(two, ops):
    _, op, _, oa, ob = two
    board, dept = ops
    dev = ops_member(dept, "운영개발", type="개발자")
    DutyAssignment.objects.create(period=op, date=d(11, 10), cell="slot0", member=oa)
    w = changes.change_cell(oa, board, d(11, 10), "slot0", oa, dev)
    assert w == ["운영개발의 그날 출근조(없음)는 점검A 관제 자격이 아닙니다."]
    w = changes.change_cell(oa, board, d(11, 10), "slot0", dev, ob)
    assert w == ["운영나은(는) 개발자가 아닙니다.", "운영나의 그날 출근조(없음)는 점검A 관제 자격이 아닙니다."]
