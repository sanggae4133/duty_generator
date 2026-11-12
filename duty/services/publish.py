from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from ..errors import DutyError
from ..models import ChangeLog, Commute, ControlDuty, Period, PeriodEvent, User
from .periods import record

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


_MODELS = {"c": (Commute, "shift"), "k": (ControlDuty, "slot")}


@transaction.atomic
def publish(period: Period, overwrite_from: date, by=None) -> None:
    period.refresh_from_db()  # 화면이 트랜잭션 밖에서 읽은 상태를 믿지 않는다(동시 배포)
    _validate(period, overwrite_from)
    undo = []
    for key, (model, field) in _MODELS.items():
        doomed = (
            model.objects.filter(period__in=_others(period), date__gte=overwrite_from, date__lte=period.end_date)
            | model.objects.filter(period=period, date__lt=overwrite_from)
        )
        undo += [[key, p, d.isoformat(), m, v] for p, d, m, v in doomed.values_list("period_id", "date", "member_id", field)]
        doomed.delete()
    period.status, period.overwrite_from, period.published_at = S.PUBLISHED, overwrite_from, timezone.now()
    period.publish_undo = undo
    period.save()
    record(period, S.GENERATED, by, f"덮어쓰기 시작일 {overwrite_from.isoformat()}")


@dataclass(frozen=True)
class UnpublishInfo:
    blocker: str | None  # 있으면 취소할 수 없는 이유
    restored_rows: int
    later_changes: int  # 배포 뒤 이 회차에서 바뀐 근무(근무표에서는 빠지고 회차 데이터에는 남음)


def unpublish_info(period: Period) -> UnpublishInfo:
    def blocked(msg):
        return UnpublishInfo(msg, 0, 0)

    if period.status != S.PUBLISHED:
        return blocked("배포된 회차가 아닙니다.")
    if period.publish_undo is None:
        return blocked("이 기능 전에 배포된 회차라 되돌릴 정보가 없습니다.")
    # 배포 순서는 시계가 아니라 상태 기록 순번으로 정한다(같은 시각·시계 보정에도 맞게)
    top = (PeriodEvent.objects.filter(to_status=S.PUBLISHED, period__status=S.PUBLISHED)
           .order_by("-id").select_related("period").first())
    if top and top.period_id != period.pk:
        return blocked(f"나중에 배포된 회차({top.period.name})부터 배포 취소해야 합니다.")
    return UnpublishInfo(None, len(period.publish_undo), ChangeLog.objects.filter(period=period, at__gte=period.published_at).count())


@transaction.atomic
def unpublish(period: Period, by=None) -> None:
    """가장 최근 배포를 되돌린다: 배포가 지운 행을 되살리고 회차는 생성됨으로. 배포 뒤 수정은 회차 데이터에 남는다."""
    period = Period.objects.select_for_update().get(pk=period.pk)
    info = unpublish_info(period)
    if info.blocker:
        raise DutyError(info.blocker)
    undo = period.publish_undo
    if User.objects.filter(pk__in={r[3] for r in undo}).count() != len({r[3] for r in undo}):
        raise DutyError("되살릴 근무의 사용자가 삭제되어 배포를 취소할 수 없습니다.")
    for key, (model, field) in _MODELS.items():
        model.objects.bulk_create(
            model(period_id=p, date=date.fromisoformat(d), member_id=m, **{field: v})
            for k, p, d, m, v in undo if k == key
        )
    period.status, period.overwrite_from, period.published_at, period.publish_undo = S.GENERATED, None, None, None
    period.log_floor = ChangeLog.objects.aggregate(m=Max("id"))["m"] or 0  # 지금까지의 기록은 다시 배포해도 쓰지 않는다
    period.save()
    record(period, S.PUBLISHED, by, "배포 취소")
