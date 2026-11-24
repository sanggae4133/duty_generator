"""근무표(Board)와 근무 정의 읽기, 그날의 주인(설계 6.1)."""
from datetime import date
from urllib.parse import urlencode

from django.db.models import Exists, F, OuterRef, Subquery
from django.db.models.functions import Coalesce

from .. import perms
from ..models import Board, BoardShift, Period, PeriodEvent, User
from ..shifts import Def, ordered, shift_defs, weekdays
from . import holidays, memos


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


def dept_keys(dept, defs: list[Def]) -> list[str]:
    """부서 출근조 가운데 defs 에 있는 근무조 키, 지금 시작 시각 순(저장한 부서 출근조 순서는 정의 시각을 바꾸면 낡는다)."""
    mine = set(dept.shift_keys())
    return [x.key for x in shift_defs(defs) if x.key in mine]


def left_without_admin(users) -> list[Board]:
    """users 를 관리 그룹에서 빼거나 퇴사시키면 재직 중인 관리자가 하나도 남지 않는 근무표(근무표 통합 설계 6.2·7.4).
    users 가운데 재직 관리자가 있는 근무표만 본다(이미 재직 관리자가 없는 근무표에서 퇴사자를 빼는 일은 막지 않는다)."""
    ids = [u.pk for u in users]
    return [b for b in Board.objects.filter(admin_group__user__in=ids, admin_group__user__is_active=True).distinct()
            if not User.objects.filter(groups=b.admin_group_id, is_active=True).exclude(pk__in=ids).exists()]


def board_of(user) -> Board | None:
    dept = getattr(user, "department", None)  # 익명·부서 없는 계정은 근무표가 없다
    return dept.board if dept else None


def home(user) -> Board | None:
    """내 근무표(설계 7): 내 부서의 근무표 → 내가 관리하는 첫 근무표 → 첫 근무표.
    ?board= 없는 /day/·/cell/·/memo/·/me/ 가 보는 근무표이고, 링크에 ?board= 를 붙일지 정하는 기준이다."""
    return board_of(user) or perms.admin_boards(user).order_by("id").first() or Board.objects.order_by("id").first()


def link_query(mine: Board | None, board: Board) -> str:
    """board 가 내 근무표(mine)가 아닐 때만 "?board=<code>". 내 근무표를 이미 아는 호출이 다시 조회하지 않게 나눴다."""
    return "" if mine is not None and mine.pk == board.pk else f"?board={board.code}"


def board_query(user, board: Board) -> str:
    """보이는 근무표가 내 근무표가 아닐 때만 "?board=<code>"(날짜 이동·필터 폼·htmx·변경 POST·알림 링크 공통).
    내 근무표면 "" 라 IT 사람의 링크·알림 주소는 1단계 그대로다."""
    return link_query(home(user), board)


def edit_boards(user) -> set[int]:
    """내가 바꿀 수 있는 근무표 id(근무표 통합 설계 9.4): 관리하는 근무표 ∪ 내 부서의 근무표. 둘 이상이면 팝업에 근무표 이름."""
    mine = board_of(user)
    return set(perms.admin_boards(user).values_list("pk", flat=True)) | ({mine.pk} if mine else set())


def in_order(chosen, home: Board | None) -> list[Board]:
    """고른 근무표 순서(근무표 통합 설계 9.1): 내 근무표 먼저, 나머지 id 순. 화면·기억·주소가 모두 이 순서.
    alarms/forms.py RuleForm 의 board queryset(Case/When)도 같은 순서다 — 바꾸면 함께 바꾼다."""
    return sorted(chosen, key=lambda b: (home is None or b.pk != home.pk, b.pk))


def selection_query(chosen: list[Board], home: Board | None) -> str:
    """고른 근무표 주소(설계 9.1). 하나면 link_query 그대로("" 또는 "?board=ops") — 근무표 하나인 화면의 링크는 글자 그대로다.
    둘 이상이면 "?board=it&board=ops"(chosen 은 in_order 순서)."""
    if len(chosen) == 1:
        return link_query(home, chosen[0])
    return "?" + urlencode([("board", b.code) for b in chosen])


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


def skip_reasons(period: Period) -> dict[date, str]:
    """만드는 도구(입력 표·CSV·생성·빈 날 검사)가 건너뛰는 날 {날짜: 까닭}(설계 5·6.5).
    근무 없음 날은 늘(까닭 = 메모 글), 휴장일은 period.skip_holidays 일 때만(2단계 전 회차는 거짓)."""
    out = holidays.closed(period.start_date, period.end_date) if period.skip_holidays else {}
    for x, memo in memos.for_range(period.board, period.start_date, period.end_date)[memos.DAY].items():
        if memo.no_work:
            out[x] = memo.text or "근무 없음"
    return out


def skip_dates(period: Period) -> set[date]:
    return set(skip_reasons(period))
