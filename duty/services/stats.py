import statistics
from dataclasses import dataclass
from datetime import date

from django.db.models import Q

from ..models import Board, Commute, DutyAssignment, Period, User
from ..shifts import TARGET_SPREAD, is_slot_cell, slot_defs
from . import boards
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


def member_stats(board: Board, start: date | None, end: date | None):
    days = published_days(board, start, end)
    # ponytail: 관제 칸들의 자격 유형 합집합(IT = 개발자). 칸마다 달라지면 칸별로 센다
    types = {t for x in slot_defs(boards.defs(board)) for t in x.eligible_types}  # 관제 정의가 없으면 비어 통계도 없다
    roster = User.objects.roster().filter(department__board=board, type__in=types)  # 그 근무표 부서 사람만
    stats = {n: MemberStat(n) for n in roster.values_list("name", flat=True)}
    # 퇴사·부서 해제된 사람도 이 기간에 근무가 있으면 통계에 남긴다(역사는 그대로)
    eligible = set(User.objects.filter(type__in=types).values_list("name", flat=True))
    for day in days:
        for names in day.members.values():
            for n in names:
                if n in eligible:
                    stats.setdefault(n, MemberStat(n))
    for day in days:
        for cell, names in day.members.items():
            if is_slot_cell(cell):
                for n in names:
                    stats.setdefault(n, MemberStat(n)).duty += 1
    for day in days:
        for n in day.members.get("dawn", ()):  # 근무표에 그 정의가 없으면 칸도 없다
            if n in stats:
                stats[n].dawn += 1
        for n in day.members.get("night", ()):
            if n in stats:
                stats[n].night += 1
    rows = sorted(stats.values(), key=lambda s: (s.duty, s.name))
    return rows, _summary([s.duty for s in rows]), _summary([s.total for s in rows])


def period_duty_counts(period: Period) -> tuple[list[tuple[str, int]], int, bool]:
    # 생성기 풀과 같은 모집단: 회차 안에 자격 근무조 출근이 있고 자격 유형인 사람. 0회 배정자도 포함한다.
    slots = slot_defs(boards.active_defs(period.board))  # 생성과 같은 칸(켜진 관제)
    q = Q(pk__in=[])  # 칸별 자격(generator 와 같다): 그 칸 자격 근무조 출근 ∧ 그 칸 자격 유형(빈 튜플 = 전원)
    for x in slots:
        q |= Q(shift__in=x.eligible_shifts, **({"member__type__in": x.eligible_types} if x.eligible_types else {}))
    # 사람은 생성기 members_by_type 와 같다: 그 근무표 부서의 재직자(배정받은 퇴사자는 아래 배정 수로 남는다)
    pool = Commute.objects.filter(q, period=period, member__department__board=period.board, member__is_active=True)
    n: dict[str, int] = dict.fromkeys(pool.values_list("member__name", flat=True), 0)
    for name in DutyAssignment.objects.filter(period=period).values_list("member__name", flat=True):
        n[name] = n.get(name, 0) + 1
    counts = sorted(n.items(), key=lambda x: (x[1], x[0]))
    spread = counts[-1][1] - counts[0][1] if counts else 0
    return counts, spread, spread <= TARGET_SPREAD
