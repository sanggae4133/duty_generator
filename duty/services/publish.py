from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.utils import timezone

from ..errors import DutyError
from ..models import ChangeLog, Commute, ControlDuty, Period

S = Period.Status


@dataclass(frozen=True)
class PublishPreview:
    overwrite_from: date
    overwrite_to: date
    periods: list[str]
    discarded_changes: int


def _validate(period: Period, overwrite_from: date) -> None:
    if period.status != S.GENERATED:
        raise DutyError("생성이 끝난 회차만 배포할 수 있습니다.")
    if not period.start_date <= overwrite_from <= period.end_date:
        raise DutyError("덮어쓰기 시작일은 회차 기간 안이어야 합니다.")


def _others(period: Period):
    return Period.objects.filter(status=S.PUBLISHED).exclude(pk=period.pk)


def preview_publish(period: Period, overwrite_from: date) -> PublishPreview:
    _validate(period, overwrite_from)
    rng = {"date__gte": overwrite_from, "date__lte": period.end_date}
    names = set(Commute.objects.filter(period__in=_others(period), **rng).values_list("period__name", flat=True))
    names |= set(ControlDuty.objects.filter(period__in=_others(period), **rng).values_list("period__name", flat=True))
    # 이미 덮어써져 행이 없는 날짜의 옛 이력은 세지 않는다
    live = set(Commute.objects.filter(period__in=_others(period), **rng).values_list("period_id", "date"))
    live |= set(ControlDuty.objects.filter(period__in=_others(period), **rng).values_list("period_id", "date"))
    discarded = sum(
        1 for key in ChangeLog.objects.filter(period__in=_others(period), **rng).values_list("period_id", "date")
        if key in live
    )
    return PublishPreview(overwrite_from, period.end_date, sorted(names), discarded)


@transaction.atomic
def publish(period: Period, overwrite_from: date) -> None:
    _validate(period, overwrite_from)
    for model in (Commute, ControlDuty):
        model.objects.filter(period__in=_others(period), date__gte=overwrite_from, date__lte=period.end_date).delete()
        model.objects.filter(period=period, date__lt=overwrite_from).delete()
    period.status, period.overwrite_from, period.published_at = S.PUBLISHED, overwrite_from, timezone.now()
    period.save()
