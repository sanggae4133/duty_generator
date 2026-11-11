import statistics
from dataclasses import dataclass
from datetime import date

from ..models import Commute, ControlDuty, Period, User
from ..shifts import CONTROL_SLOTS, DEVELOPER, TARGET_SPREAD, is_slot_cell
from .roster import published_days


@dataclass
class MemberStat:
    name: str
    duty: int = 0
    dawn: int = 0
    night: int = 0

    @property
    def total(self) -> int:
        return self.duty + self.dawn + self.night


@dataclass(frozen=True)
class Summary:
    mean: float
    stdev: float
    spread: int


def _summary(values: list[int]) -> Summary | None:
    if not values:
        return None
    stdev = statistics.stdev(values) if len(values) > 1 else 0.0
    return Summary(statistics.mean(values), stdev, max(values) - min(values))


def member_stats(start: date | None, end: date | None):
    days = published_days(start, end)
    stats = {n: MemberStat(n) for n in User.objects.roster().filter(type=DEVELOPER).values_list("name", flat=True)}
    # 퇴사·부서 해제된 개발자도 이 기간에 근무가 있으면 통계에 남긴다(역사는 그대로)
    developers = set(User.objects.filter(type=DEVELOPER).values_list("name", flat=True))
    for day in days:
        for names in day.members.values():
            for n in names:
                if n in developers:
                    stats.setdefault(n, MemberStat(n))
    for day in days:
        for cell, names in day.members.items():
            if is_slot_cell(cell):
                for n in names:
                    stats.setdefault(n, MemberStat(n)).duty += 1
    for day in days:
        for n in day.members["dawn"]:
            if n in stats:
                stats[n].dawn += 1
        for n in day.members["night"]:
            if n in stats:
                stats[n].night += 1
    rows = sorted(stats.values(), key=lambda s: (s.duty, s.name))
    return rows, _summary([s.duty for s in rows]), _summary([s.total for s in rows])


def period_duty_counts(period: Period) -> tuple[list[tuple[str, int]], int, bool]:
    # 생성기 풀과 같은 모집단: 회차 안에 자격 출근조가 있는 개발자. 0회 배정자도 포함한다.
    eligible = {s for _, allowed in CONTROL_SLOTS for s in allowed}
    pool = Commute.objects.filter(period=period, shift__in=eligible, member__type=DEVELOPER)
    n: dict[str, int] = dict.fromkeys(pool.values_list("member__name", flat=True), 0)
    for name in ControlDuty.objects.filter(period=period).values_list("member__name", flat=True):
        n[name] = n.get(name, 0) + 1
    counts = sorted(n.items(), key=lambda x: (x[1], x[0]))
    spread = counts[-1][1] - counts[0][1] if counts else 0
    return counts, spread, spread <= TARGET_SPREAD
