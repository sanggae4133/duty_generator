"""근무표(Board)와 근무 정의 읽기, 그날의 주인(설계 6.1). 1단계는 IT 근무표 하나."""
from datetime import date

from django.db.models import Exists, F, OuterRef, Subquery
from django.db.models.functions import Coalesce

from ..models import Board, BoardShift, Period, PeriodEvent
from ..shifts import Def, ordered, weekdays


def it_board() -> Board:
    return Board.objects.get(code="it")


def defs(board: Board) -> list[Def]:
    """그 근무표의 근무 정의 전부(꺼진 것 포함: 표시·라벨·지난 행·기록의 이름을 찾는다). KEYS 순."""
    return ordered([
        Def(s.key, s.name, s.start, s.end, tuple(s.eligible_shifts), tuple(s.eligible_types), s.default_alarm, s.active)
        for s in BoardShift.objects.filter(board=board)
    ])


def active_defs(board: Board) -> list[Def]:
    """켜진 정의만(설계 4.3 '끄면 새 입력에서만 빠진다'): 입력 표·CSV 열, 부서 출근조·스케줄·알림 규칙 선택지, 생성."""
    return [x for x in defs(board) if x.active]


def board_of(user) -> Board | None:
    dept = getattr(user, "department", None)  # 익명·부서 없는 계정은 근무표가 없다
    return dept.board if dept else None


def _ranked(board):
    """그 근무표의 배포 회차를 최근 배포 순으로. 배포 순번 = 배포 PeriodEvent 의 id(시계와 무관).
    배포 이벤트가 없는 옛 회차는 이벤트가 있는 회차보다 오래된 것으로 보고, 그들끼리는 published_at(없으면 가장 오래됨), pk 순."""
    ev = PeriodEvent.objects.filter(period=OuterRef("pk"), to_status=Period.Status.PUBLISHED)
    return (
        Period.objects.filter(board=board, status=Period.Status.PUBLISHED)
        .annotate(owns_from=Coalesce("overwrite_from", "start_date"),  # 마이그레이션 전 옛 배포 회차는 비어 있을 수 있다
                  has_publish=Exists(ev),
                  publish_seq=Subquery(ev.order_by("-id").values("id")[:1]))
        .order_by("-has_publish", "-publish_seq", F("published_at").desc(nulls_last=True), "-pk")
    )


def owner(board, d: date) -> Period | None:
    """(근무표, 날짜)의 주인: overwrite_from ≤ d ≤ end_date 인 배포 회차 중 가장 최근에 배포한 것. 배정 행과 무관."""
    return _ranked(board).filter(owns_from__lte=d, end_date__gte=d).first()


def owners(board, start: date | None, end: date | None) -> dict[date, Period]:
    """start~end(None = 끝 없음)의 평일마다 주인. 주인이 없는 날은 빠지고, 배정 없는 날도 들어간다."""
    qs = _ranked(board)
    if start:
        qs = qs.filter(end_date__gte=start)
    if end:
        qs = qs.filter(owns_from__lte=end)
    ranked = list(qs)
    if not ranked:
        return {}
    lo = start or min(p.owns_from for p in ranked)
    hi = end or max(p.end_date for p in ranked)
    out = {}
    for x in weekdays(lo, hi):
        p = next((p for p in ranked if p.owns_from <= x <= p.end_date), None)  # ranked 는 최근 배포 순
        if p is not None:
            out[x] = p
    return out
