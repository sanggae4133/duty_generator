"""근무 없음 날: 근무 변경 막기(설계 6.4), 배포 취소가 그날 행을 되살리지 않기(설계 6.1). 이름은 모두 가상."""
from datetime import date

import pytest

from duty.errors import DutyError
from duty.models import Commute, DutyAssignment, Period
from duty.services import changes, memos
from duty.services.publish import publish, unpublish, unpublish_info

S = Period.Status
D = date(2026, 11, 18)  # 수요일


@pytest.fixture
def world(make_member, admin_user, fixed_today, it_board):
    fixed_today(date(2026, 11, 16))
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 16), end_date=date(2026, 11, 20),
                              status=S.PUBLISHED, overwrite_from=date(2026, 11, 16))
    m = {n: make_member(n, user=True) for n in ["가", "나", "다"]}
    Commute.objects.create(period=p, date=D, member=m["가"], shift="dawn")
    Commute.objects.create(period=p, date=D, member=m["나"], shift="normal")
    DutyAssignment.objects.create(period=p, date=D, cell="slot0", member=m["가"])
    Commute.objects.create(period=p, date=date(2026, 11, 19), member=m["다"], shift="normal")
    return p, m


# ── 근무 없음 날 근무 변경 막기 ──

def test_changes_blocked_on_no_work_day(world, admin_user, it_board):
    _, m = world
    memos.save(admin_user, it_board, "day", D, "휴무", no_work=True, confirm=True)
    with pytest.raises(DutyError, match="근무 없는 날입니다"):
        changes.change_cell(admin_user, it_board, D, "normal", None, m["다"])
    with pytest.raises(DutyError, match="근무 없는 날입니다"):
        changes.exchange(admin_user, it_board, D, "normal", m["가"], m["다"])
    with pytest.raises(DutyError, match="근무 없는 날입니다"):
        changes.swap(admin_user, it_board, D, "dawn", m["가"], "normal", m["나"])
    memos.delete(admin_user, it_board, "day", D)
    changes.change_cell(admin_user, it_board, D, "normal", None, m["다"])  # 메모를 지우면 넣기로 다시 채운다
    assert Commute.objects.filter(date=D, member=m["다"]).exists()


def test_plain_day_memo_does_not_block(world, admin_user, it_board):
    _, m = world
    memos.save(admin_user, it_board, "day", D, "행사")
    changes.change_cell(admin_user, it_board, D, "night", None, m["다"])


# ── 배포 취소는 근무 없음 날 행을 되살리지 않는다 ──

def test_unpublish_skips_no_work_days(make_member, admin_user, it_board, fixed_today):
    fixed_today(date(2026, 11, 2))
    ga, na = make_member("가"), make_member("나")
    a = Period.objects.create(board=it_board, name="A", start_date=date(2026, 11, 16), end_date=date(2026, 11, 20),
                              status=S.GENERATED)
    b = Period.objects.create(board=it_board, name="B", start_date=date(2026, 11, 16), end_date=date(2026, 11, 20),
                              status=S.GENERATED)
    for day in (17, 18):
        Commute.objects.create(period=a, date=date(2026, 11, day), member=ga, shift="normal")
        Commute.objects.create(period=b, date=date(2026, 11, day), member=na, shift="normal")
    publish(a, date(2026, 11, 16))
    publish(b, date(2026, 11, 16))  # A 의 17·18일 행이 publish_undo 로
    memos.save(admin_user, it_board, "day", D, "휴무", no_work=True, confirm=True)
    assert unpublish_info(b).restored_rows == 1
    unpublish(b)
    assert list(Commute.objects.filter(period=a).values_list("date", flat=True)) == [date(2026, 11, 17)]
