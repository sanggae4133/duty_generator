from collections import defaultdict
from datetime import date

from django.db import transaction

from ..errors import DutyError
from ..models import Commute, ControlDuty, Department, Period, PeriodEvent

S = Period.Status


def record(period: Period, old: str, by=None, note: str = "") -> None:
    """상태가 old 에서 period.status 로 바뀐 것을 남긴다(저장은 호출한 쪽)."""
    PeriodEvent.objects.create(period=period, from_status=old, to_status=period.status, by=by, note=note)


@transaction.atomic
def save_draft(period: Period, by=None) -> Period:
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
    new = period.pk is None
    period.save()
    if new:
        record(period, "", by)
    else:  # 되돌아온 회차는 출근표가 있을 수 있다: 줄어든 기간 밖은 지운다
        for model in (Commute, ControlDuty):
            model.objects.filter(period=period).exclude(date__in=period.dates()).delete()
    return period


MOVABLE = (S.DRAFT, S.COLLECTING, S.CLOSED)  # 생성됨·배포됨은 생성·배포 버튼으로만 간다


@transaction.atomic
def move(period: Period, to: str, by=None) -> None:
    """배포 전 상태끼리 자유롭게 옮긴다. 생성됨에서 나가면 생성 결과(장중관제)를 지운다. 출근표는 남는다."""
    if to not in MOVABLE:
        raise DutyError("옮길 수 없는 상태입니다.")
    if period.status == S.PUBLISHED:
        raise DutyError("배포된 회차는 배포 취소로만 되돌릴 수 있습니다.")
    if period.status == to:
        raise DutyError("이미 그 상태입니다.")
    old = period.status
    ControlDuty.objects.filter(period=period).delete()
    period.status, period.seed, period.generated_at = to, None, None
    period.save()
    record(period, old, by)


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
