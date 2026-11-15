"""지금 보내야 할 알림 계산. ORM 없음. 모든 시각은 Asia/Seoul naive. 근무표 하나의 정의(defs)·근무표(days)·규칙만 받는다."""
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from ..csv_io import join_reason
from ..services.roster import Day
from ..shifts import KEYS, LUNCH, cell_start, cells_of
from . import messages as m
from .schedule import send_at


@dataclass(frozen=True)
class RuleSpec:
    id: int
    member_name: str | None
    kind: str  # "personal" | "report"
    timing: str
    offset: int
    at_minute: int
    channels: tuple[str, ...]
    shifts: tuple[str, ...]
    depts: tuple[str, ...]
    types: tuple[str, ...]
    lunch: tuple[time, time] | None = None  # 개인 규칙 주인 부서의 점심 시각(점심당번 시작·문구). 없으면 None


@dataclass(frozen=True)
class Due:
    rule_id: int
    date: date
    cell: str  # 칸 키 또는 "report"
    channel: str
    title: str
    text: str
    content_hash: str
    url: str
    expires_at: datetime
    push_text: str
    destination: str = ""


def _empty(d: date) -> Day:
    return Day(d, 0, {}, {c: [] for c in KEYS}, {})


def _hash(prefix: str, text: str) -> str:
    return f"{prefix}:{hashlib.sha256(text.encode()).hexdigest()[:16]}"


def plan(defs, rules, days, info, deliveries, now, destinations=None, dept_names=None, extra_dates=None,
         today=None, closed=frozenset()) -> list[Due]:
    """defs: 이 근무표의 정의. destinations: (rule_id, channel) → 목적지 목록. closed: 휴장일 날짜 집합(영업일 계산).
    deliveries: (rule_id, date, cell, channel, destination) → 그 목적지에 마지막으로 성공한 내용 hash(없으면 None)."""
    today = today or now.date()
    destinations = destinations or {}
    by_date = {d.date: d for d in days}
    synthetic = {d for d in (extra_dates or ()) if d not in by_date}
    for d in synthetic:
        by_date[d] = _empty(d)
    dept_names = dept_names or {}
    out: list[Due] = []
    for day in sorted(by_date.values(), key=lambda x: x.date):
        for r in rules:
            cells = cells_of(defs, list(r.shifts))  # 이 근무표에 없는 키는 조용히 무시
            if not cells:
                continue
            # 점심당번은 정의에 시각이 없어 여기서 빠진다(보고서 발송 창·만료는 시각 있는 칸으로만)
            starts = {c: datetime.combine(day.date, cell_start(defs, c)) for c in cells if c != LUNCH}
            if r.kind == "personal":
                if r.member_name:
                    if LUNCH in cells and (lunch := _lunch_start(r, day.date)):
                        starts[LUNCH] = lunch
                    out += _personal(defs, r, day, [c for c in cells if c in starts], starts, deliveries, now,
                                     destinations, today, closed)
            elif r.kind == "report" and starts:  # 점심당번만 고른 보고서는 저장 때 막는다(services.alarms.save_rule)
                out += _report(defs, r, day, cells, starts, info, deliveries, now, dept_names, day.date in synthetic,
                               destinations, closed)
    return out


def _lunch_start(r, d: date) -> datetime | None:
    """개인 알림의 점심당번 시작 = 그 사람 부서 점심 시각. 시각이 없으면 시각 기준 규칙에서 빼고(None),
    날짜 기준 규칙은 그날 끝(다음 날 00:00)까지 보낸다(만료도 그때)."""
    if r.lunch:
        return datetime.combine(d, r.lunch[0])
    return None if r.timing == "before_start" else datetime.combine(d + timedelta(days=1), time())


def _successor(day, cell, name):
    """replaced 간선을 모두 따라가 도달 가능한 사람 중 지금 칸에 있는 후임(최근 간선 우선)."""
    edges = [(old, new) for (c, new), old in day.replaced.items() if c == cell]
    seen, todo = {name}, [name]
    while todo:
        cur = todo.pop()
        for old, new in edges:
            if old == cur and new not in seen:
                seen.add(new)
                todo.append(new)
    now_in = day.members.get(cell, [])
    for _, new in reversed(edges):
        if new != name and new in seen and new in now_in:
            return new
    return None


def _targets(r, destinations):
    return [(ch, dest) for ch in r.channels for dest in destinations.get((r.id, ch), ())]


def _personal(defs, r, day, cells, starts, deliveries, now, destinations, today, closed):
    out = []
    for c in cells:
        if day.excused(r.member_name):  # 사유가 있으면 근무로 치지 않는다. 이미 보낸 알림의 취소도 보내지 않는다
            continue
        start = starts[c]
        if not send_at(r.timing, r.offset, r.at_minute, day.date, start, closed) <= now < start:
            continue
        inside = r.member_name in day.members.get(c, [])
        if inside:
            title, text = m.PERSONAL_TITLE, m.personal_text(defs, r.member_name, day.date, c, today, r.lunch)
            # 오늘/내일 표기는 hash에서 뺀다(자정이 지났다고 다시 보내지 않게)
            h = _hash("in", m.personal_text(defs, r.member_name, day.date, c, day.date, r.lunch))
        else:
            title = m.CANCEL_TITLE
            text = m.cancel_text(defs, r.member_name, day.date, c, _successor(day, c, r.member_name), r.lunch)
            h = _hash("out", text)
        for ch, dest in _targets(r, destinations):
            last = deliveries.get((r.id, day.date, c, ch, dest))
            # 취소는 이 목적지에 무언가 성공적으로 알린 적이 있을 때만
            if last == h or (not inside and not (last or "").startswith(("in:", "out:"))):
                continue
            out.append(Due(r.id, day.date, c, ch, title, m.clip(text), h, f"/day/{day.date.isoformat()}/",
                           start, m.clip_bytes(text.replace("\n", " ")), dest))
    return out


def _report(defs, r, day, cells, starts, info, deliveries, now, dept_names, synthetic, destinations, closed):
    first, last_start = min(starts.values()), max(starts.values())
    if not send_at(r.timing, r.offset, r.at_minute, day.date, first, closed) <= now < last_start:
        return []

    def keep(name):
        dept, typ = info.get(name, ("", ""))
        return (not r.depts or dept in r.depts) and (not r.types or typ in r.types)

    lines, uniq = [], set()
    for c in cells:
        names = [n for n in day.members.get(c, []) if keep(n)]
        uniq.update(n for n in names if not day.excused(n))  # 요약 인원은 근무로 치는 사람만
        lines.append(m.report_line(defs, c, [join_reason(n, day.reason(c, n)) for n in names]))  # 가(휴가)
    cond = "·".join([dept_names.get(x, x) for x in r.depts] + list(r.types))
    # 변경 표지만 빼고 보이는 내용 전체(머리·조건·근무표)
    h = _hash("report", "\n".join([m.report_header(day.date, cond, False), *lines]))
    out = []
    for ch, dest in _targets(r, destinations):
        prev = deliveries.get((r.id, day.date, "report", ch, dest))
        if prev == h or (prev is None and synthetic):
            continue
        head = m.report_header(day.date, cond, prev is not None)
        summary = f"{head} · {len(uniq)}명"
        out.append(Due(r.id, day.date, "report", ch, m.REPORT_TITLE, m.clip("\n".join([head, *lines])), h,
                       f"/day/{day.date.isoformat()}/", last_start, m.clip_bytes(summary), dest))
    return out
