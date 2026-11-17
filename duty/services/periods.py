from collections import defaultdict
from datetime import date

from django.db import transaction

from .. import perms
from ..errors import DutyError
from ..models import MOVABLE, ChangeLog, Commute, Department, DutyAssignment, Period, PeriodEvent
from . import boards, holidays

S = Period.Status


def record(period: Period, old: str, by=None, note: str = "") -> None:
    """상태가 old 에서 period.status 로 바뀐 것을 남긴다(저장은 호출한 쪽)."""
    PeriodEvent.objects.create(period=period, from_status=old, to_status=period.status, by=by, note=note)


def _names(board, statuses) -> str:
    """켠 단계 중 statuses 에 든 것의 이름(단계 순). 끈 단계 이름은 오류 글에 나오지 않는다(설계 6.1)."""
    return "·".join(board.step_name(s) for s in board.steps() if s in statuses)


@transaction.atomic
def save_draft(period: Period, by=None) -> Period:
    board = period.board
    row = Period.objects.select_for_update().get(pk=period.pk) if period.pk else None  # 상태는 DB 에서(낡은 객체 대비)
    if row and row.status not in board.editable():  # 작성 중, 작성 중을 안 쓰면 취합 중에서도(설계 5.2)
        raise DutyError(f"기간은 '{_names(board, board.editable())}' 단계에서만 고칠 수 있습니다.")
    if period.start_date > period.end_date:
        raise DutyError("시작일이 종료일보다 늦습니다.")
    if not period.dates():
        raise DutyError("기간에 평일이 없습니다.")
    clash = (
        Period.objects.exclude(pk=period.pk)
        .exclude(status=S.PUBLISHED)
        .filter(board_id=period.board_id, start_date__lte=period.end_date, end_date__gte=period.start_date)
        .first()
    )
    if clash:
        raise DutyError(f"배포 전 회차와 기간이 겹칩니다: {clash.name}")
    new = period.pk is None
    if new:
        period.status = board.first_step()  # 작성 중을 안 쓰면 만들자마자 취합 중(입력 중)
        period.save()
    else:  # 고칠 수 있는 칸만 쓴다: 낡은 객체가 상태·seed·생성 시각을 되돌리지 못하게
        period.status, period.seed, period.generated_at = row.status, row.seed, row.generated_at
        period.save(update_fields=["name", "start_date", "end_date"])
    if new:
        record(period, "", by)
    else:  # 되돌아온 회차는 출근표가 있을 수 있다: 줄어든 기간 밖은 지운다
        for model in (Commute, DutyAssignment):
            model.objects.filter(period=period).exclude(date__in=period.dates()).delete()
    holidays.sync(perms.today())  # 저장한 뒤: 이 회차의 해가 범위에 들어야 입력 표가 휴장일을 안다
    return period


@transaction.atomic
def move(period: Period, to: str, by=None) -> None:
    """배포 전 상태끼리 자유롭게 옮긴다. 생성됨에서 나가면 생성 결과(장중관제)를 지운다. 출근표는 남는다."""
    period.refresh_from_db()
    if period.status == S.PUBLISHED:
        raise DutyError("배포된 회차는 배포 취소로만 되돌릴 수 있습니다.")
    if period.status == to:
        raise DutyError("이미 그 상태입니다.")
    if to not in period.board.move_targets(period.status):  # 켠 배포 전 단계로만(설계 5.2)
        raise DutyError("옮길 수 없는 상태입니다." if to not in MOVABLE
                        else f"'{_names(period.board, MOVABLE)}'(으)로만 옮길 수 있습니다.")
    old = period.status
    DutyAssignment.objects.filter(period=period).delete()
    period.status, period.seed, period.generated_at = to, None, None
    period.save()
    record(period, old, by)


@transaction.atomic
def delete(period: Period) -> None:
    """시험·실수로 만든 회차를 지운다. 배포된 회차, 근무 변경 기록이 남은 회차(배포된 적 있음)는 안 된다."""
    period.refresh_from_db()
    if period.status == S.PUBLISHED:
        raise DutyError("배포된 회차는 지울 수 없습니다. 먼저 배포 취소하세요.")
    if ChangeLog.objects.filter(period=period).exists():
        raise DutyError("근무 변경 기록이 남은 회차(배포된 적 있음)는 지울 수 없습니다.")
    PeriodEvent.objects.filter(period=period).delete()
    period.delete()  # 출근표·장중관제는 함께 지워진다(CASCADE)


def empty_days(period: Period) -> list[date]:
    """그 근무표 부서 중 하나라도 출근표가 없는 평일(건너뛰는 날 제외), 날짜 순. 빈 평일 경고."""
    return sorted({d for ds in missing_dates(period).values() for d in ds})


def missing_dates(period: Period) -> dict[str, list[date]]:
    """그 근무표 부서마다 출근표가 하나도 없는 평일. 건너뛰는 날(근무 없음·휴장일)은 빼고 본다."""
    have: dict[str, set[date]] = defaultdict(set)
    for code, d in Commute.objects.filter(period=period).values_list("member__department", "date"):
        have[code].add(d)
    skip = boards.skip_dates(period)
    out = {}
    for dept in Department.objects.filter(board_id=period.board_id).order_by("code"):
        missing = [d for d in period.dates() if d not in have[dept.code] and d not in skip]
        if missing:
            out[dept.code] = missing
    return out
