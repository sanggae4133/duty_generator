"""알림 문구. ORM 없음. 칸 이름·시각은 근무표 정의 목록(defs)에서 읽는다."""
from datetime import date

from ..shifts import DAY_LABELS, SLOT_GROUP_NAME, cell_end, cell_label, cell_start, is_slot_cell

CUT = "…(이하 생략, 웹에서 확인)"
PERSONAL_TITLE, CANCEL_TITLE, REPORT_TITLE = "당번 알림", "당번 변경", "출근표"


def day_label(d: date) -> str:
    return f"{d.month}/{d.day}({DAY_LABELS[d.weekday()]})"


def relative_day(d: date, today: date) -> str:
    return {0: "오늘", 1: "내일"}.get((d - today).days, day_label(d))


def cell_span(defs, cell: str) -> str:
    """'새벽 06:30~15:30' 또는 '10:30~11:30'."""
    if is_slot_cell(cell):
        return cell_label(defs, cell)
    return f"{cell_label(defs, cell)} {cell_start(defs, cell):%H:%M}~{cell_end(defs, cell):%H:%M}"


def _kind(defs, cell: str) -> str:
    return SLOT_GROUP_NAME if is_slot_cell(cell) else f"{cell_label(defs, cell)} 당번"


def _where(defs, cell: str) -> str:
    return f"{SLOT_GROUP_NAME} {cell_label(defs, cell)}" if is_slot_cell(cell) else cell_label(defs, cell)


def change_notice(defs, d: date, cell: str, before: str | None, after: str | None, by: str) -> tuple[str, str]:
    """내 근무가 바뀌었을 때(제목, 본문). 교체 A → B, 넣기 +B, 빼기 A 빠짐."""
    what = f"{before} → {after}" if before and after else (f"+{after}" if after else f"{before} 빠짐")
    return "근무 변경", f"[근무 변경] {day_label(d)} {_where(defs, cell)}\n{what}\n바꾼 사람: {by}"


def swap_notice(defs, d: date, cell_a: str, a: str, cell_b: str, b: str, by: str) -> tuple[str, str]:
    """맞교환 한 번(기록 2건)을 한 통으로: A 는 cell_a → cell_b, B 는 반대로."""
    return "근무 변경", (f"[근무 변경] {day_label(d)} 맞교환\n{a} {_where(defs, cell_a)} → {_where(defs, cell_b)}\n"
                       f"{b} {_where(defs, cell_b)} → {_where(defs, cell_a)}\n바꾼 사람: {by}")


def personal_text(defs, name: str, d: date, cell: str, today: date) -> str:
    return (f"[{PERSONAL_TITLE}] {day_label(d)} {cell_span(defs, cell)}\n"
            f"{name}님, {relative_day(d, today)} {_kind(defs, cell)}입니다.")


def cancel_text(defs, name: str, d: date, cell: str, successor: str | None = None) -> str:
    tail = f" (후임: {successor})" if successor else ""
    return f"[{CANCEL_TITLE}] {day_label(d)} {cell_span(defs, cell)}\n{name}님의 근무가 취소되었습니다.{tail}"


def report_header(d: date, cond: str, changed: bool) -> str:
    title = f"{REPORT_TITLE} 변경" if changed else REPORT_TITLE
    return f"[{title}] {day_label(d)}" + (f" — {cond}" if cond else "")


def report_line(defs, cell: str, names: list[str]) -> str:
    label = cell_label(defs, cell) if is_slot_cell(cell) else f"{cell_label(defs, cell)}({cell_start(defs, cell):%H:%M}~)"
    return f"{label} {', '.join(names) if names else '-'}"


def clip(text: str, limit: int = 4000) -> str:
    return text if len(text) <= limit else text[: limit - len(CUT)] + CUT


def clip_bytes(text: str, limit: int = 1000) -> str:
    return text if len(text.encode()) <= limit else text.encode()[: limit - 3].decode(errors="ignore") + "..."
