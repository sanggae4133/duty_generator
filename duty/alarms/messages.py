"""알림 문구. ORM 없음."""
from datetime import date

from ..shifts import DAY_LABELS, cell_end, cell_label, cell_start, is_slot_cell

CUT = "…(이하 생략, 웹에서 확인)"
PERSONAL_TITLE, CANCEL_TITLE, REPORT_TITLE = "당번 알림", "당번 변경", "출근표"


def day_label(d: date) -> str:
    return f"{d.month}/{d.day}({DAY_LABELS[d.weekday()]})"


def relative_day(d: date, today: date) -> str:
    return {0: "오늘", 1: "내일"}.get((d - today).days, day_label(d))


def cell_span(cell: str) -> str:
    """'새벽 06:30~15:30' 또는 '10:30~11:30'."""
    if is_slot_cell(cell):
        return cell_label(cell)
    return f"{cell_label(cell)} {cell_start(cell):%H:%M}~{cell_end(cell):%H:%M}"


def _kind(cell: str) -> str:
    return "장중관제" if is_slot_cell(cell) else f"{cell_label(cell)} 당번"


def personal_text(name: str, d: date, cell: str, today: date) -> str:
    return f"[{PERSONAL_TITLE}] {day_label(d)} {cell_span(cell)}\n{name}님, {relative_day(d, today)} {_kind(cell)}입니다."


def cancel_text(name: str, d: date, cell: str, successor: str | None = None) -> str:
    tail = f" (후임: {successor})" if successor else ""
    return f"[{CANCEL_TITLE}] {day_label(d)} {cell_span(cell)}\n{name}님의 근무가 취소되었습니다.{tail}"


def report_header(d: date, cond: str, changed: bool) -> str:
    title = f"{REPORT_TITLE} 변경" if changed else REPORT_TITLE
    return f"[{title}] {day_label(d)}" + (f" — {cond}" if cond else "")


def report_line(cell: str, names: list[str]) -> str:
    label = cell_label(cell) if is_slot_cell(cell) else f"{cell_label(cell)}({cell_start(cell):%H:%M}~)"
    return f"{label} {', '.join(names) if names else '-'}"


def clip(text: str, limit: int = 4000) -> str:
    return text if len(text) <= limit else text[: limit - len(CUT)] + CUT


def clip_bytes(text: str, limit: int = 1000) -> str:
    return text if len(text.encode()) <= limit else text.encode()[: limit - 3].decode(errors="ignore") + "..."
