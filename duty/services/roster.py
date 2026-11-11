"""배포된 근무표 읽기 모델. 화면·통계·알림·캘린더가 공통으로 쓴다."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from ..models import ChangeLog, Commute, ControlDuty, Period, User
from ..shifts import CELLS, cell_label, slot_cell

Log = tuple[str | None, str | None]


@dataclass
class Cell:
    labels: list[str]
    removed: list[str]
    changed: bool


@dataclass
class Day:
    date: date
    period_id: int
    cells: dict[str, Cell]
    members: dict[str, list[str]]
    replaced: dict[tuple[str, str], str]


def chain(current: list[str], logs: list[Log]) -> tuple[list[str], list[str], dict[str, str]]:
    """ChangeLog 순서대로 표시 라벨을 만든다. A→B 후 B→C 면 'A>B>C', 추가는 '+B', 제거는 removed 목록."""
    label: dict[str, str] = {}
    removed: list[str] = []
    replaced: dict[str, str] = {}
    for before, after in logs:
        prev = label.pop(before, before) if before else None
        if after:
            label[after] = f"{prev}>{after}" if prev else f"+{after}"
            replaced.pop(after, None)
            if before:
                replaced[after] = before
        elif prev:
            removed.append(prev)
    return [label.get(n, n) for n in current], removed, replaced


def published_days(start: date | None = None, end: date | None = None) -> list[Day]:
    def scoped(qs):
        qs = qs.filter(period__status=Period.Status.PUBLISHED)
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        return qs

    raw: dict[date, dict] = {}

    def slot(d, pid):
        return raw.setdefault(d, {"period": pid, "cells": defaultdict(list)})

    commutes = scoped(Commute.objects).order_by("date", "member__username")
    for d, pid, shift, name in commutes.values_list("date", "period_id", "shift", "member__name"):
        slot(d, pid)["cells"][shift].append(name)
    for d, pid, i, name in scoped(ControlDuty.objects).values_list("date", "period_id", "slot", "member__name"):
        slot(d, pid)["cells"][slot_cell(i)].append(name)

    logs: dict[tuple[date, str], list[Log]] = defaultdict(list)
    rows = scoped(ChangeLog.objects).order_by("at", "id").values_list("date", "period_id", "cell", "before__name", "after__name")
    for d, pid, cell, before, after in rows:
        if d in raw and raw[d]["period"] == pid:  # 덮어쓰인 회차의 이력은 숨긴다
            logs[(d, cell)].append((before, after))

    days = []
    for d in sorted(raw):
        cells, members, replaced = {}, {}, {}
        for cell in CELLS:
            current = raw[d]["cells"].get(cell, [])
            cell_logs = logs.get((d, cell), [])
            labels, removed, rep = chain(current, cell_logs)
            cells[cell] = Cell(labels, removed, bool(cell_logs))
            members[cell] = current
            replaced.update({(cell, name): prev for name, prev in rep.items()})
        days.append(Day(d, raw[d]["period"], cells, members, replaced))
    return days


def find_day(d: date) -> Day | None:
    days = published_days(d, d)
    return days[0] if days else None


def member_schedule(member: User, start: date) -> list[tuple[date, list[str]]]:
    out = []
    for day in published_days(start, None):
        labels = [cell_label(c) for c in CELLS if member.name in day.members[c]]
        if labels:
            out.append((day.date, labels))
    return out
