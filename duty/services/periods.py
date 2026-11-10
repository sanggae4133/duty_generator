from collections import defaultdict
from datetime import date

from django.db import transaction

from ..errors import DutyError
from ..models import Commute, ControlDuty, Department, Period

S = Period.Status


def save_draft(period: Period) -> Period:
    if period.pk and Period.objects.get(pk=period.pk).status != S.DRAFT:
        raise DutyError("기간은 작성 중(draft) 상태에서만 수정할 수 있습니다.")
    if period.start_date > period.end_date:
        raise DutyError("시작일이 종료일보다 늦습니다.")
    if not period.dates():
        raise DutyError("기간에 평일이 없습니다.")
    clash = (
        Period.objects.exclude(pk=period.pk)
        .exclude(status=S.PUBLISHED)
        .filter(start_date__lte=period.end_date, end_date__gte=period.start_date)
        .first()
    )
    if clash:
        raise DutyError(f"배포 전 회차와 기간이 겹칩니다: {clash.name}")
    period.save()
    return period


@transaction.atomic
def open_collecting(period: Period) -> None:
    if period.status not in {S.DRAFT, S.CLOSED, S.GENERATED}:
        raise DutyError("이 상태에서는 취합을 열 수 없습니다.")
    ControlDuty.objects.filter(period=period).delete()
    period.status, period.seed, period.generated_at = S.COLLECTING, None, None
    period.save()


def close_collecting(period: Period) -> None:
    if period.status != S.COLLECTING:
        raise DutyError("취합 중인 회차만 마감할 수 있습니다.")
    period.status = S.CLOSED
    period.save()


def missing_dates(period: Period) -> dict[str, list[date]]:
    have: dict[str, set[date]] = defaultdict(set)
    for code, d in Commute.objects.filter(period=period).values_list("member__department", "date"):
        have[code].add(d)
    out = {}
    for dept in Department.objects.order_by("code"):
        missing = [d for d in period.dates() if d not in have[dept.code]]
        if missing:
            out[dept.code] = missing
    return out
