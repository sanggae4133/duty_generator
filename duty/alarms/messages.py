"""알림 문구. ORM 없음. 칸 이름·시각은 근무표 정의 목록(defs)에서 읽는다."""
from datetime import date

from ..shifts import DAY_LABELS, SHIFT, SLOT, SLOT_GROUP_NAME, cell_end, cell_label, cell_start, is_slot_cell, kind

# 문구 틀은 키의 성격으로 셋: 근무조("새벽 06:30~15:30", "새벽 당번"), 묶음 당번 칸("08:30~09:30", "장중관제"),
# 혼자인 당번 칸(점심당번: 정의에 시각이 없다. 개인 알림은 그 사람 부서 점심 시각 lunch=(시작, 끝)이 있으면 붙인다)

CUT = "…(이하 생략, 웹에서 확인)"
PERSONAL_TITLE, CANCEL_TITLE, REPORT_TITLE = "당번 알림", "당번 변경", "출근표"


def day_label(d: date) -> str:
    return f"{d.month}/{d.day}({DAY_LABELS[d.weekday()]})"


def relative_day(d: date, today: date) -> str:
    return {0: "오늘", 1: "내일"}.get((d - today).days, day_label(d))


def cell_span(defs, cell: str, lunch=None) -> str:
    """'새벽 06:30~15:30', '10:30~11:30', '점심당번 11:30~12:30'(부서 점심 시각이 없으면 '점심당번')."""
    if kind(cell) == SLOT:
        return cell_label(defs, cell)
    if kind(cell) != SHIFT:
        return cell_label(defs, cell) + (f" {lunch[0]:%H:%M}~{lunch[1]:%H:%M}" if lunch else "")
    return f"{cell_label(defs, cell)} {cell_start(defs, cell):%H:%M}~{cell_end(defs, cell):%H:%M}"


def _kind(defs, cell: str) -> str:
    return {SHIFT: f"{cell_label(defs, cell)} 당번", SLOT: SLOT_GROUP_NAME}.get(kind(cell), cell_label(defs, cell))


def _where(defs, cell: str) -> str:
    return f"{SLOT_GROUP_NAME} {cell_label(defs, cell)}" if is_slot_cell(cell) else cell_label(defs, cell)


def _when(d: date, today: date) -> str:
    """'오늘 11/10(화)'·'내일 11/10(화)', 그 밖에는 '11/10(화)'."""
    rel = relative_day(d, today)
    return f"{rel} {day_label(d)}" if rel != day_label(d) else rel


def change_notice(defs, d: date, today: date, cell: str, before: str | None, after: str | None, by: str) -> tuple[str, str]:
    """내 근무가 바뀌었을 때(제목, 본문). 교체 A → B, 넣기 B 추가, 빼기 A 빠짐. 근무조는 시각까지('그래서 몇 시에')."""
    what = f"{before} → {after}" if before and after else (f"{after} 추가" if after else f"{before} 빠짐")
    where = _where(defs, cell) if is_slot_cell(cell) else cell_span(defs, cell)
    return "근무 변경", f"[근무 변경] {_when(d, today)} {where}\n{what}\n바꾼 사람: {by}"


def memo_notice(board: str, scope: str, d: date, text: str, no_work: bool, by: str) -> tuple[str, str]:
    """메모가 새로 달리거나 바뀌었을 때(제목, 본문). 날 = 11/10(화), 주 = 11/9(월) 주, 달 = 11월."""
    where = {"day": day_label(d), "week": f"{day_label(d)} 주", "month": f"{d.month}월"}[scope]
    body = ("근무 없음: " if no_work else "") + (text or "근무 없음")  # 메모는 500자까지라 자르지 않는다
    return "메모", f"[메모] {board} · {where}\n{body}\n쓴 사람: {by}"


def swap_notice(defs, d: date, today: date, cell_a: str, a: str, cell_b: str, b: str, by: str) -> tuple[str, str]:
    """맞교환 한 번(기록 2건)을 한 통으로: A 는 cell_a → cell_b, B 는 반대로."""
    return "근무 변경", (f"[근무 변경] {_when(d, today)} 맞교환\n{a} {_where(defs, cell_a)} → {_where(defs, cell_b)}\n"
                       f"{b} {_where(defs, cell_b)} → {_where(defs, cell_a)}\n바꾼 사람: {by}")


def personal_text(defs, name: str, d: date, cell: str, today: date, lunch=None) -> str:
    return (f"[{PERSONAL_TITLE}] {day_label(d)} {cell_span(defs, cell, lunch)}\n"
            f"{name}님, {relative_day(d, today)} {_kind(defs, cell)}입니다.")


def cancel_text(defs, name: str, d: date, cell: str, successor: str | None = None, lunch=None) -> str:
    tail = f" (후임: {successor})" if successor else ""
    return f"[{CANCEL_TITLE}] {day_label(d)} {cell_span(defs, cell, lunch)}\n{name}님의 근무가 취소되었습니다.{tail}"


def report_header(d: date, cond: str, changed: bool) -> str:
    title = f"{REPORT_TITLE} 변경" if changed else REPORT_TITLE
    return f"[{title}] {day_label(d)}" + (f" — {cond}" if cond else "")


def report_line(defs, cell: str, names: list[str]) -> str:
    # 점심당번 줄은 시각 없이 "점심당번 가, 나"(기존 줄 뒤: 순회 순서 KEYS 의 끝)
    label = f"{cell_label(defs, cell)}({cell_start(defs, cell):%H:%M}~)" if kind(cell) == SHIFT else cell_label(defs, cell)
    return f"{label} {', '.join(names) if names else '-'}"


LIMIT = 4000  # 텔레그램 본문 최대 길이


def clip(text: str, limit: int = LIMIT) -> str:
    return text if len(text) <= limit else text[: limit - len(CUT)] + CUT


PUSH_BYTES = 3000  # 웹 푸시 한 통의 본문 한도(암호화 포함 4KB 안: 제목·주소 자리를 남긴다)


def push_body(text: str) -> str:
    """푸시 본문 = 텔레그램과 같은 글(줄바꿈 그대로, 링크 줄 없음: 알림을 누르면 열린다)."""
    return clip_bytes(text, PUSH_BYTES)


def clip_bytes(text: str, limit: int = 1000) -> str:
    return text if len(text.encode()) <= limit else text.encode()[: limit - 3].decode(errors="ignore") + "..."
