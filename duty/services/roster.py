"""배포된 근무표 읽기 모델. 화면·통계·알림·캘린더가 공통으로 쓴다."""

from collections import defaultdict
from datetime import date

from django.db.models import F

from ..models import ChangeLog, Commute, DutyAssignment, User
from ..shifts import (
    DAY_LABELS, SHIFT, SLOT_GROUP, SLOT_GROUP_NAME, Cell, Day, Log, cell_end, cell_label, cell_start, chain, display_order,
    is_slot_cell, join_reason, kind, ordered,
)
from . import boards

def published_days(board, start: date | None = None, end: date | None = None) -> list[Day]:
    """그 근무표에서 주인(boards.owners)이 있는 평일마다 Day 하나. 주인 회차의 행·기록만 쓴다(행이 없으면 빈 칸).
    칸 순서 = 정의의 KEYS 순(알림 내용 hash 가 이 순서에 걸려 있다)."""
    owner_id = {d: p.pk for d, p in boards.owners(board, start, end).items()}
    if not owner_id:
        return []
    keys = [x.key for x in ordered(boards.defs(board))]
    rng = {"period_id__in": set(owner_id.values()), "date__gte": min(owner_id), "date__lte": max(owner_id)}

    names: dict[tuple[date, str], list[str]] = defaultdict(list)
    reasons: dict[date, dict[tuple[str, str], str]] = defaultdict(dict)
    rows = Commute.objects.filter(**rng).order_by("date", "member__username")
    for d, pid, cell, name, why in rows.values_list("date", "period_id", "shift", "member__name", "reason"):
        if owner_id.get(d) == pid:
            names[(d, cell)].append(name)
            if why:
                reasons[d][(cell, name)] = why
    rows = DutyAssignment.objects.filter(**rng).order_by("date", "member__username")
    for d, pid, cell, name in rows.values_list("date", "period_id", "cell", "member__name"):
        if owner_id.get(d) == pid:
            names[(d, cell)].append(name)

    logs: dict[tuple[date, str], list[Log]] = defaultdict(list)
    # 배포 취소 이전 기록(log_floor 이하)은 다시 배포해도 쓰지 않는다(그사이 출근표·생성이 바뀌었을 수 있다)
    rows = (ChangeLog.objects.filter(**rng, id__gt=F("period__log_floor"))
            .order_by("at", "id").values_list("date", "period_id", "cell", "before__name", "after__name"))
    for d, pid, cell, before, after in rows:
        # 덮어쓰인 회차의 이력은 숨긴다. 사유만 바뀐 기록(before == after)은 변경 표시(A>B·취소선)에서 뺀다
        if owner_id.get(d) == pid and before != after:
            logs[(d, cell)].append((before, after))

    days = []
    for d in sorted(owner_id):
        cells, members, replaced = {}, {}, {}
        for cell in keys:
            current = names.get((d, cell), [])
            cell_logs = logs.get((d, cell), [])
            labels, removed, rep = chain(current, cell_logs)
            cells[cell] = Cell(labels, removed, bool(cell_logs))
            members[cell] = current
            replaced.update({(cell, name): prev for name, prev in rep.items()})
        days.append(Day(d, owner_id[d], cells, members, replaced, reasons[d]))
    return days


def find_day(board, d: date) -> Day | None:
    days = published_days(board, d, d)
    return days[0] if days else None


def member_schedule(board, member: User, start: date, shown=lambda cell: True,
                    end: date | None = None) -> list[tuple[date, list[tuple[str, str]]]]:
    """내 근무: 날마다 ["정상 08:00~17:00", "점심당번 11:30~12:30", "장중관제 08:30~09:30"]. 사유는 이름 뒤 "정상(휴가) 08:00~17:00".
    점심당번 시각은 부서 점심 시각(없으면 이름만). 글마다 (스케줄 키, 글) — 관제 칸은 'slots'(화면이 브라우저에서 거른다)."""
    defs = boards.defs(board)
    dept = member.department
    lunch = f" {dept.lunch_start:%H:%M}~{dept.lunch_end:%H:%M}" if dept and dept.lunch_start else ""

    def label(day, c):
        if is_slot_cell(c):
            return f"{SLOT_GROUP_NAME} {cell_label(defs, c)}"
        span = f" {cell_start(defs, c):%H:%M}~{cell_end(defs, c):%H:%M}" if kind(c) == SHIFT else lunch
        return join_reason(cell_label(defs, c), day.reason(c, member.name)) + span

    out = []
    for day in published_days(board, start, end):
        labels = [((SLOT_GROUP if is_slot_cell(c) else c), label(day, c))
                  for c, names in day.members.items() if shown(c) and member.name in names]
        if labels:
            out.append((day.date, labels))
    return out


def _span(a, b) -> str:
    return f"{a:%H:%M}~{b:%H:%M}" if a and b else ""


def export_rows(board, start: date, end: date | None, keep=lambda name: True, shown=lambda cell: True) -> list[tuple]:
    """엑셀 다운로드 줄: 배포된 날(published_days)의 지금 배정 한 사람마다
    (날짜, 요일, 근무표, 칸, 시간, 이름, 부서, 사유). 칸 순서는 화면(display_order), 사유 있는 사람도 넣는다.
    keep(이름)·shown(칸 키)은 근무표 화면의 부서·유형·스케줄 필터와 같은 함수다."""
    defs = boards.defs(board)
    days = published_days(board, start, end)
    names = {n for day in days for ns in day.members.values() for n in ns}
    people = {u.name: u.department for u in User.objects.filter(name__in=names).select_related("department")}
    out = []
    for day in days:
        for x in display_order(defs):
            if not shown(x.key):
                continue
            for n in filter(keep, day.members[x.key]):
                dept = people.get(n)
                if kind(x.key) == SHIFT or is_slot_cell(x.key):
                    span = _span(x.start, x.end)
                else:  # 점심당번: 그 사람 부서의 점심 시각(없으면 빈 칸)
                    span = _span(dept.lunch_start, dept.lunch_end) if dept else ""
                out.append((day.date, DAY_LABELS[day.date.weekday()], board.name,
                            SLOT_GROUP_NAME if is_slot_cell(x.key) else x.name, span, n,
                            dept.name if dept else "", day.reason(x.key, n)))
    return out
