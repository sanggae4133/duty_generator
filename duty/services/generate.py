import random
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from .. import perms
from ..errors import DutyError
from ..generator import GenerationOutput, generate_control_duty
from ..models import Commute, Department, DutyAssignment, Period, User
from ..shifts import LUNCH, by_key, day_spans, shift_defs, slot_defs
from . import boards, holidays
from .periods import missing_dates, record, require_admin

S = Period.Status


@transaction.atomic  # 검사·입력 읽기·저장을 한 트랜잭션에(IMMEDIATE: 그동안 다른 쓰기는 기다린다)
def run_generation(period: Period, seed: int | None = None, by=None) -> GenerationOutput:
    require_admin(period, by)
    period.refresh_from_db()
    board = period.board
    active = boards.active_defs(board)
    slots = slot_defs(active)  # 인덱스 i ↔ 칸 키 slots[i].key. 꺼진 관제는 생성하지 않는다
    if period.status not in {board.generate_from(), S.GENERATED}:  # 마감을 쓰면 마감에서, 아니면 취합 중에서
        raise DutyError(f"'{board.step_name(board.generate_from())}'인 회차만 "
                        f"{board.step_buttons(bool(slots))['generate']}할 수 있습니다.")
    holidays.sync(perms.today())  # 작업자가 꺼져 있어도 휴장일 표가 비어 있지 않게
    warnings = []
    missing = missing_dates(period)  # 빈 평일은 모든 근무표에서 막지 않고 경고로만 알린다(설계 6.1)
    if missing:
        names = dict(Department.objects.filter(board=board).values_list("code", "name"))
        detail = ", ".join(f"{names[code]} {len(ds)}일({day_spans(ds)})" for code, ds in missing.items())
        warnings.append(f"출근표가 비어 있는 날이 있습니다: {detail}. 그날 그 부서는 근무자가 없습니다.")
    if seed is None:
        seed = random.SystemRandom().randrange(2**31)

    skip = boards.skip_dates(period)  # 근무 없음 날·휴장일(skip_holidays)은 당번을 만들지 않는다. 남은 출근 행은 그대로 둔다
    dates = [d for d in period.dates() if d not in skip]
    worked = set(Commute.objects.filter(period=period, member__department__board=period.board)  # 다른 근무표로 옮긴 사람 행은 빼고
                 .values_list("date", flat=True))
    slot_dates = [d for d in dates if d in worked]  # 출근 행이 하나도 없는 날은 후보가 없으니 관제를 만들지 않는다
    if slots:
        commutes: dict = defaultdict(lambda: defaultdict(set))
        rows = Commute.objects.filter(period=period, reason="").exclude(date__in=skip)  # 사유가 있으면 후보가 아니다
        for d, shift, code in rows.values_list("date", "shift", "member__username"):
            commutes[d][shift].add(code)
        members_by_type: dict = defaultdict(set)  # 그 근무표 부서 재직자. 칸별 유형 거르기는 generator 가 한다
        for typ, code in User.objects.roster().filter(department__board=period.board).values_list("type", "username"):
            members_by_type[typ].add(code)
        out = generate_control_duty(
            slot_dates, commutes, dict(members_by_type), seed,
            [(x.name, x.eligible_shifts, x.eligible_types) for x in slots],
        )  # GenerationError 전파
    else:  # 장중관제 정의가 없는 근무표는 생성기를 부르지 않는다
        out = GenerationOutput({}, {}, 0, True)

    by_code = {m.username: m for m in User.objects.filter(username__in=out.counts)}
    DutyAssignment.objects.filter(period=period).delete()
    DutyAssignment.objects.bulk_create(
        DutyAssignment(period=period, date=d, cell=slots[i].key, member=by_code[code])
        for d, picked in out.assignments.items()
        for i, code in enumerate(picked)
    )
    out.warnings[:0] = warnings
    if LUNCH in by_key(active) and shift_defs(active):
        out.warnings += _fill_lunch(period, dates, skip, shift_defs(active)[0])
    old = period.status
    period.status, period.seed, period.generated_at = S.GENERATED, seed, timezone.now()
    period.save()
    record(period, old, by, "재생성" if old == S.GENERATED else "")
    return out


def _days(days) -> str:
    return ", ".join(f"{d.month}/{d.day}" for d in days)


def _fill_lunch(period: Period, dates: list, skip: set, early) -> list[str]:
    """점심당번 = 날짜마다 가장 이른 근무조(early)에 근무로 친(사유 없는) 출근을 한 사람 전원(설계 6.3). 무작위 없음.
    아무도 없는 날은 비우고 경고 한 줄."""
    by_day: dict = defaultdict(list)
    rows = Commute.objects.filter(period=period, shift=early.key, reason="").exclude(date__in=skip)
    for d, member_id in rows.order_by("date", "member__username").values_list("date", "member_id"):
        by_day[d].append(member_id)
    DutyAssignment.objects.bulk_create(
        DutyAssignment(period=period, date=d, cell=LUNCH, member_id=m) for d in dates for m in by_day[d])
    empty = [d for d in dates if not by_day[d]]
    if not empty:
        return []
    return [f"점심당번을 채우지 못한 날({early.name} 출근 없음): {_days(empty)}"]
