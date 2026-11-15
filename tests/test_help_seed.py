"""사용법 영상 가짜 데이터(tools/help_videos/seed.py)가 근무표·그룹 구조에서 끝까지 도는지."""
from datetime import date
from pathlib import Path

import pytest

from duty import perms
from duty.models import ChangeLog, Department, DutyAssignment, Period, User

SEED = Path(__file__).resolve().parents[1] / "tools" / "help_videos" / "seed.py"


@pytest.mark.django_db
def test_seed_uses_it_board_and_groups(it_board, fixed_today, capsys):
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
    assert now.status == Period.Status.PUBLISHED
    assert DutyAssignment.objects.filter(period=now, cell__startswith="slot").exists()
    assert ChangeLog.objects.filter(period=now, cell="normal").count() == 1
