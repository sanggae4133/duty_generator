"""부서 출근표 CSV. 형식은 기존 취합 문서와 같다: date, (day), 새벽, 정상, 석식교대, 야간 / 이름 쉼표 구분."""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date

from .shifts import COMMUTE_SHIFTS, DAY_LABELS

CommuteTable = dict[date, dict[str, list[str]]]


@dataclass(frozen=True)
class CsvError:
    row: int  # 0 = 특정 행이 아님
    column: str
    reason: str


class CsvInvalid(Exception):
    def __init__(self, errors: list[CsvError]):
        super().__init__(f"CSV 오류 {len(errors)}건")
        self.errors = errors


def decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp949"):  # cp949: 한국어 Windows 엑셀 기본 저장 형식
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    raise CsvInvalid([CsvError(0, "", "UTF-8이나 CP949 CSV 파일이 아닙니다.")])


_NAME_SPLIT = re.compile(r"[,\n]")


def split_names(cell: str) -> list[str]:
    return [n.strip() for n in _NAME_SPLIT.split(cell or "") if n.strip()]


def header_key(h: str) -> str:
    return re.split(r"[\n(]", h, maxsplit=1)[0].strip()


_DATE_PATTERNS = [
    re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$"),
    re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$"),
    re.compile(r"^(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?$"),
]


def parse_date(s: str) -> date | None:
    s = (s or "").strip()
    for p in _DATE_PATTERNS:
        m = p.match(s)
        if m:
            try:
                return date(*map(int, m.groups()))
            except ValueError:
                return None
    return None


def parse_commute_csv(raw: bytes, shift_keys: list[str]) -> CommuteTable:
    try:
        rows = list(csv.reader(io.StringIO(decode(raw))))
    except csv.Error as e:
        raise CsvInvalid([CsvError(0, "", f"CSV 형식 오류: {e}")]) from e
    if not rows:
        raise CsvInvalid([CsvError(1, "", "빈 파일입니다.")])
    header = [header_key(h) for h in rows[0]]
    errors: list[CsvError] = []
    if "date" not in header:
        errors.append(CsvError(1, "date", "date 열이 없습니다."))
    cols: dict[str, int] = {}
    for key in shift_keys:
        label = COMMUTE_SHIFTS[key]
        if label in header:
            cols[key] = header.index(label)
        else:
            errors.append(CsvError(1, label, f"{label} 열이 없습니다."))
    if errors:
        raise CsvInvalid(errors)

    date_col = header.index("date")
    table: CommuteTable = {}
    for n, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue
        value = row[date_col] if date_col < len(row) else ""
        d = parse_date(value)
        if d is None:
            errors.append(CsvError(n, "date", f"날짜 형식이 아닙니다: {value!r}"))
            continue
        if d in table:
            errors.append(CsvError(n, "date", f"중복된 날짜입니다: {d}"))
            continue
        table[d] = {key: split_names(row[i] if i < len(row) else "") for key, i in cols.items()}
    if errors:
        raise CsvInvalid(errors)
    return table


def export_commute_csv(dates: list[date], shift_keys: list[str], table: CommuteTable) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "day", *[COMMUTE_SHIFTS[k] for k in shift_keys]])
    for d in dates:
        day = table.get(d, {})
        w.writerow([d.isoformat(), DAY_LABELS[d.weekday()], *[", ".join(day.get(k, [])) for k in shift_keys]])
    return buf.getvalue().encode("utf-8-sig")
