import random
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from .. import perms
from ..errors import DutyError
from ..generator import GenerationOutput, generate_control_duty
from ..models import Commute, DutyAssignment, Period, User
from ..shifts import slot_defs
from . import boards, holidays
from .periods import missing_dates, record

S = Period.Status


@transaction.atomic  # 검사·입력 읽기·저장을 한 트랜잭션에(IMMEDIATE: 그동안 다른 쓰기는 기다린다)
def run_generation(period: Period, seed: int | None = None, by=None) -> GenerationOutput:
    period.refresh_from_db()
    if period.status not in {S.CLOSED, S.GENERATED}:
        raise DutyError("마감된 회차만 생성할 수 있습니다.")
    holidays.sync(perms.today())  # 작업자가 꺼져 있어도 휴장일 표가 비어 있지 않게
    missing = missing_dates(period)
    if missing:
        detail = ", ".join(f"{code} {len(ds)}일" for code, ds in missing.items())
        raise DutyError(f"출근표가 비어 있는 날짜가 있습니다: {detail}")
    if seed is None:
        seed = random.SystemRandom().randrange(2**31)

    skip = boards.skip_dates(period)  # 근무 없음 날·휴장일(skip_holidays)은 당번을 만들지 않는다. 남은 출근 행은 그대로 둔다
    dates = [d for d in period.dates() if d not in skip]
    slots = slot_defs(boards.active_defs(period.board))  # 인덱스 i ↔ 칸 키 slots[i].key. 꺼진 관제는 생성하지 않는다
    if slots:
        commutes: dict = defaultdict(lambda: defaultdict(set))
        rows = Commute.objects.filter(period=period, reason="").exclude(date__in=skip)  # 사유가 있으면 후보가 아니다
        for d, shift, code in rows.values_list("date", "shift", "member__username"):
            commutes[d][shift].add(code)
        members_by_type: dict = defaultdict(set)  # 그 근무표 부서 재직자. 칸별 유형 거르기는 generator 가 한다
        for typ, code in User.objects.roster().filter(department__board=period.board).values_list("type", "username"):
            members_by_type[typ].add(code)
        out = generate_control_duty(
            dates, commutes, dict(members_by_type), seed,
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
    old = period.status
    period.status, period.seed, period.generated_at = S.GENERATED, seed, timezone.now()
    period.save()
    record(period, old, by, "재생성" if old == S.GENERATED else "")
    return out
