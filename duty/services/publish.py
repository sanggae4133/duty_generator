from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from ..errors import DutyError
from ..models import ChangeLog, Commute, DutyAssignment, Period, PeriodEvent, User
from . import boards, memos
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
        raise DutyError(f"'{period.board.step_name(S.GENERATED)}'인 회차만 배포할 수 있습니다.")
    if not period.start_date <= overwrite_from <= period.end_date:
        raise DutyError("덮어쓰기 시작일은 회차 기간 안이어야 합니다.")


def _others(period: Period):
    # 근무표 필터가 빠지면 다른 근무표를 배포할 때 이 근무표의 같은 기간 행이 지워진다(설계 6.1)
    return Period.objects.filter(status=S.PUBLISHED, board_id=period.board_id).exclude(pk=period.pk)


def preview_publish(period: Period, overwrite_from: date) -> PublishPreview:
    _validate(period, overwrite_from)
    # 덮어쓸 대상 = 범위 안 날짜마다의 주인(설계 6.1). 이 회차는 배포 전이라 주인이 아니다
    own = boards.owners(period.board, overwrite_from, period.end_date)
    # 이미 덮어써져 그날의 주인이 아닌 회차의 옛 이력은 세지 않는다
    discarded = sum(
        1 for pid, d in ChangeLog.objects.filter(
            period__in=_others(period), date__gte=overwrite_from, date__lte=period.end_date,
        ).values_list("period_id", "date")
        if d in own and own[d].pk == pid
    )
    return PublishPreview(overwrite_from, period.end_date, sorted({p.name for p in own.values()}), discarded)


# 행 종류 → (모델, 넷째 칸부터의 필드). 옛 "k"(관제 숫자) 행은 마이그레이션 0013 이 "a" 로 바꿨다.
# c 행의 여섯째 칸(reason)은 2단계부터: 그 전에 배포한 회차의 다섯 칸짜리 c 행은 사유 없음으로 되살린다
_MODELS = {"c": (Commute, ("shift", "reason")), "a": (DutyAssignment, ("cell",))}


@transaction.atomic
def publish(period: Period, overwrite_from: date, by=None) -> None:
    period.refresh_from_db()  # 화면이 트랜잭션 밖에서 읽은 상태를 믿지 않는다(동시 배포)
    _validate(period, overwrite_from)
    undo = []
    for key, (model, fields) in _MODELS.items():
        doomed = (
            model.objects.filter(period__in=_others(period), date__gte=overwrite_from, date__lte=period.end_date)
            | model.objects.filter(period=period, date__lt=overwrite_from)
        )
        undo += [[key, p, d.isoformat(), m, *vals]
                 for p, d, m, *vals in doomed.values_list("period_id", "date", "member_id", *fields)]
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
    top = (PeriodEvent.objects.filter(to_status=S.PUBLISHED, period__status=S.PUBLISHED,
                                      period__board_id=period.board_id)  # 배포 취소 순서는 근무표마다
           .order_by("-id").select_related("period").first())
    if top and top.period_id != period.pk:
        return blocked(f"나중에 배포된 회차({top.period.name})부터 배포 취소해야 합니다.")
    return UnpublishInfo(None, len(_restorable(period)), ChangeLog.objects.filter(period=period, at__gte=period.published_at).count())


def _restorable(period: Period) -> list:
    """배포 취소로 되살릴 행: 그 근무표의 근무 없음 날짜 행은 빼고(근무 없음 날은 늘 비어 있다, 설계 6.1)."""
    closed = {x.isoformat() for x in memos.no_work_days(period.board, date.min, date.max)}
    return [r for r in period.publish_undo if r[2] not in closed]


@transaction.atomic
def unpublish(period: Period, by=None) -> None:
    """가장 최근 배포를 되돌린다: 배포가 지운 행을 되살리고 회차는 생성됨으로. 배포 뒤 수정은 회차 데이터에 남는다."""
    period = Period.objects.select_for_update().get(pk=period.pk)
    info = unpublish_info(period)
    if info.blocker:
        raise DutyError(info.blocker)
    undo = _restorable(period)
    if User.objects.filter(pk__in={r[3] for r in undo}).count() != len({r[3] for r in undo}):
        raise DutyError("되살릴 근무의 사용자가 삭제되어 배포를 취소할 수 없습니다.")
    for key, (model, fields) in _MODELS.items():
        model.objects.bulk_create(
            model(period_id=p, date=date.fromisoformat(d), member_id=m, **dict(zip(fields, vals)))
            for k, p, d, m, *vals in undo if k == key
        )
    period.status, period.overwrite_from, period.published_at, period.publish_undo = S.GENERATED, None, None, None
    period.log_floor = ChangeLog.objects.aggregate(m=Max("id"))["m"] or 0  # 지금까지의 기록은 다시 배포해도 쓰지 않는다
    period.save()
    record(period, S.PUBLISHED, by, "배포 취소")
