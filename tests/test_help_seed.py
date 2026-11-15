"""사용법 영상 가짜 데이터(tools/help_videos/seed.py)가 근무표·그룹 구조에서 끝까지 도는지."""
from datetime import date
from pathlib import Path

import pytest

from duty import perms
from duty.models import ChangeLog, Commute, Department, DutyAssignment, Holiday, Memo, Period, User

SEED = Path(__file__).resolve().parents[1] / "tools" / "help_videos" / "seed.py"


@pytest.mark.django_db
def test_seed_uses_it_board_and_groups(it_board, lunch, fixed_today, capsys):
    fixed_today(date(2026, 11, 11))  # 수요일
    exec(compile(SEED.read_text(encoding="utf-8"), str(SEED), "exec"), {"__name__": "seed"})
    assert capsys.readouterr().out.strip().endswith("seeded")

    assert list(Department.objects.order_by("order").values_list("code", flat=True)) == ["MEMS", "TMCH", "MD", "UI"]
    assert set(Department.objects.values_list("board", flat=True)) == {it_board.pk}
    assert set(Period.objects.values_list("board", flat=True)) == {it_board.pk}

    admin, manager, member = (User.objects.get(username=u) for u in ("admin", "manager", "member"))
    assert perms.is_board_admin(admin, it_board)
    assert not perms.is_admin(manager) and not perms.is_admin(member)
    assert list(perms.managed_departments(manager).values_list("code", flat=True)) == ["MEMS"]
    assert not perms.managed_departments(member).exists()

    now = Period.objects.get(name="이번 회차")
    nxt = Period.objects.get(name="다음 회차")
    assert now.status == Period.Status.PUBLISHED
    assert DutyAssignment.objects.filter(period=now, cell__startswith="slot").exists()
    assert ChangeLog.objects.filter(period=now, cell="normal").count() == 1

    # 2단계 화면 예시(member 영상): 휴장일·메모·사유·점심당번
    hol = Holiday.objects.get(source=Holiday.Source.MANUAL)
    assert hol.active and now.start_date <= hol.date <= now.end_date and hol.date.weekday() < 5
    assert not Commute.objects.filter(period=now, date=hol.date).exists()  # 건너뛰는 날은 비어 있다
    assert set(Memo.objects.values_list("scope", flat=True)) == {"day", "week", "month"}
    nowork = Memo.objects.get(no_work=True)
    assert nxt.start_date <= nowork.date <= nxt.end_date
    assert not Commute.objects.filter(period=nxt, date=nowork.date).exists()
    assert Commute.objects.filter(period=now).exclude(reason="").count() == 1
    assert DutyAssignment.objects.filter(period=now, cell="lunch").exists()
    assert Department.objects.exclude(lunch_start=None).count() == 4


@pytest.mark.django_db
def test_seed_refuses_non_empty_db(it_board):
    """계정이 하나라도 있는 DB(운영 DB 등)에서는 아무것도 쓰지 않고 멈춘다."""
    User.objects.create_user("someone", password=None, name="가상사람")
    with pytest.raises(SystemExit, match="빈 임시 DB"):
        exec(compile(SEED.read_text(encoding="utf-8"), str(SEED), "exec"), {"__name__": "seed"})
    assert User.objects.count() == 1 and not Department.objects.exists()
