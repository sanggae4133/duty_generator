import random
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from ..errors import DutyError
from ..generator import GenerationOutput, generate_control_duty
from ..models import Commute, ControlDuty, Period, User
from ..shifts import DEVELOPER
from .periods import missing_dates, record

S = Period.Status


def run_generation(period: Period, seed: int | None = None, by=None) -> GenerationOutput:
    if period.status not in {S.CLOSED, S.GENERATED}:
        raise DutyError("마감된 회차만 생성할 수 있습니다.")
    missing = missing_dates(period)
    if missing:
        detail = ", ".join(f"{code} {len(ds)}일" for code, ds in missing.items())
        raise DutyError(f"출근표가 비어 있는 날짜가 있습니다: {detail}")
    if seed is None:
        seed = random.SystemRandom().randrange(2**31)

    commutes: dict = defaultdict(lambda: defaultdict(set))
    for d, shift, code in Commute.objects.filter(period=period).values_list("date", "shift", "member__username"):
        commutes[d][shift].add(code)
    developers = set(User.objects.roster().filter(type=DEVELOPER).values_list("username", flat=True))
    out = generate_control_duty(period.dates(), commutes, developers, seed)  # GenerationError 전파

    by_code = {m.username: m for m in User.objects.filter(username__in=out.counts)}
    with transaction.atomic():
        ControlDuty.objects.filter(period=period).delete()
        ControlDuty.objects.bulk_create(
            ControlDuty(period=period, date=d, slot=i, member=by_code[code])
            for d, picked in out.assignments.items()
            for i, code in enumerate(picked)
        )
        old = period.status
        period.status, period.seed, period.generated_at = S.GENERATED, seed, timezone.now()
        period.save()
        record(period, old, by, "재생성" if old == S.GENERATED else "")
    return out
