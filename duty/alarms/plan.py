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


def _empty(d: date) -> Day:
    return Day(d, 0, {}, {c: [] for c in CELLS}, {})


def plan(rules, days, info, deliveries, now, dept_names=None, extra_dates=None) -> list[Due]:
    by_date = {d.date: d for d in days}
    for d in extra_dates or ():
        by_date.setdefault(d, _empty(d))
    dept_names = dept_names or {}
    out: list[Due] = []
    for day in sorted(by_date.values(), key=lambda x: x.date):
        for r in rules:
            cells = cells_of(list(r.shifts))
            starts = {c: datetime.combine(day.date, cell_start(c)) for c in cells}
            if r.kind == "personal":
                if r.member_name:
                    out += _personal(r, day, cells, starts, deliveries, now)
            else:
                out += _report(r, day, cells, starts, info, deliveries, now, dept_names)
    return out


def _personal(r, day, cells, starts, deliveries, now):
    out = []
    for c in cells:
        start = starts[c]
        if not send_at(r.timing, r.offset, r.at_minute, day.date, start) <= now < start:
            continue
        inside = r.member_name in day.members.get(c, [])
        for ch in r.channels:
            last = deliveries.get((r.id, day.date, c, ch))
            if inside and last != "in":
                title, text, h = m.PERSONAL_TITLE, m.personal_text(r.member_name, day.date, c, now.date()), "in"
            elif not inside and last == "in":
                succ = next((new for (cc, new), old in day.replaced.items() if cc == c and old == r.member_name), None)
                title, text, h = m.CANCEL_TITLE, m.cancel_text(r.member_name, day.date, c, succ), "out"
            else:
                continue
            out.append(Due(r.id, day.date, c, ch, title, m.clip(text), h, f"/day/{day.date.isoformat()}/",
                           start, m.clip_bytes(text.replace("\n", " "))))
    return out


def _report(r, day, cells, starts, info, deliveries, now, dept_names):
    first, last_start = min(starts.values()), max(starts.values())
    if not send_at(r.timing, r.offset, r.at_minute, day.date, first) <= now < last_start:
        return []

    def keep(name):
        dept, typ = info.get(name, ("", ""))
        return (not r.depts or dept in r.depts) and (not r.types or typ in r.types)

    lines, count = [], 0
    for c in cells:
        names = [n for n in day.members.get(c, []) if keep(n)]
        count += len(names)
        lines.append(m.report_line(c, names))
    h = hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]
    cond = "·".join([dept_names.get(x, x) for x in r.depts] + list(r.types))
    out = []
    for ch in r.channels:
        prev = deliveries.get((r.id, day.date, "report", ch))
        if prev == h:
            continue
        head = m.report_header(day.date, cond, prev is not None)
        summary = f"{head} · {count}명"
        out.append(Due(r.id, day.date, "report", ch, m.REPORT_TITLE, m.clip("\n".join([head, *lines])), h,
                       f"/day/{day.date.isoformat()}/", last_start, m.clip_bytes(summary)))
    return out
