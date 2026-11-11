"""지금 보내야 할 알림 계산. ORM 없음. 모든 시각은 Asia/Seoul naive."""
import hashlib
from dataclasses import dataclass
from datetime import date, datetime

from ..services.roster import Day
from ..shifts import CELLS, cell_start, cells_of
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
    return Day(d, 0, {}, {c: [] for c in CELLS}, {})


def _hash(prefix: str, text: str) -> str:
    return f"{prefix}:{hashlib.sha256(text.encode()).hexdigest()[:16]}"


def plan(rules, days, info, deliveries, now, destinations=None, dept_names=None, extra_dates=None,
         today=None) -> list[Due]:
    """destinations: (rule_id, channel) → 목적지 목록. deliveries: (rule_id, date, cell, channel, destination)
    → 그 목적지에 마지막으로 성공한 내용 hash(없으면 None)."""
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
            cells = cells_of(list(r.shifts))
            starts = {c: datetime.combine(day.date, cell_start(c)) for c in cells}
            if r.kind == "personal":
                if r.member_name:
                    out += _personal(r, day, cells, starts, deliveries, now, destinations, today)
            elif r.kind == "report":
                out += _report(r, day, cells, starts, info, deliveries, now, dept_names, day.date in synthetic,
                               destinations)
    return out


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


def _personal(r, day, cells, starts, deliveries, now, destinations, today):
    out = []
    for c in cells:
        start = starts[c]
        if not send_at(r.timing, r.offset, r.at_minute, day.date, start) <= now < start:
            continue
        inside = r.member_name in day.members.get(c, [])
        if inside:
            title, text = m.PERSONAL_TITLE, m.personal_text(r.member_name, day.date, c, today)
            # 오늘/내일 표기는 hash에서 뺀다(자정이 지났다고 다시 보내지 않게)
            h = _hash("in", m.personal_text(r.member_name, day.date, c, day.date))
        else:
            title = m.CANCEL_TITLE
            text = m.cancel_text(r.member_name, day.date, c, _successor(day, c, r.member_name))
            h = _hash("out", text)
        for ch, dest in _targets(r, destinations):
            last = deliveries.get((r.id, day.date, c, ch, dest))
            # 취소는 이 목적지에 무언가 성공적으로 알린 적이 있을 때만
            if last == h or (not inside and not (last or "").startswith(("in:", "out:"))):
                continue
            out.append(Due(r.id, day.date, c, ch, title, m.clip(text), h, f"/day/{day.date.isoformat()}/",
                           start, m.clip_bytes(text.replace("\n", " ")), dest))
    return out


def _report(r, day, cells, starts, info, deliveries, now, dept_names, synthetic, destinations):
    first, last_start = min(starts.values()), max(starts.values())
    if not send_at(r.timing, r.offset, r.at_minute, day.date, first) <= now < last_start:
        return []

    def keep(name):
        dept, typ = info.get(name, ("", ""))
        return (not r.depts or dept in r.depts) and (not r.types or typ in r.types)

    lines, uniq = [], set()
    for c in cells:
        names = [n for n in day.members.get(c, []) if keep(n)]
        uniq.update(names)
        lines.append(m.report_line(c, names))
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
