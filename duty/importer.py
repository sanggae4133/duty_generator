"""기존 구글 시트 1회 가져오기.

제작기 tb_member → Department/Member
배포용 view_all_combine → 생성 당시 원본, 배포용 근무표 → 'A>B' 변경을 ChangeLog 로 기록하고 최종 상태 반영.
"""

import re
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO

import openpyxl
from django.db import transaction
from django.utils import timezone

from .models import ChangeLog, Commute, ControlDuty, Department, Member, Period
from .shifts import CELL_BY_LABEL, CELLS, DEVELOPER, STAFF, cell_label, is_slot_cell, slot_index

MAKER_ID = "1y-T4gWwGb9p8g4Lkla0so1yY7Ox_QnV0N1unRChfYOI"
DEPLOY_ID = "1RZjmnktNRFNg3KycrNI3No6Sczu8ATnWd1IWAYWxn5w"
IMPORT_PERIOD_NAME = "시트 이관"
DEPARTMENTS = [
    ("MEMS", "매칭엔진실", "dawn,normal,dinner,night"),
    ("TMCH", "매매지원실", "dawn,normal,dinner,night"),
    ("MD", "정보분배", "dawn,normal,dinner,night"),
    ("UI", "UI", "normal,dinner,night"),
]

_ARROW = re.compile(r"\s*-?\s*>\s*")  # duty_notifier cell_parser 와 같은 규칙
_SEP = re.compile(r"[,\n]")

Log = tuple[str | None, str | None]


def download_xlsx(sheet_id: str) -> bytes:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def parse_chains(cell) -> list[list[str]]:
    joined = _ARROW.sub(">", str(cell or ""))
    out = []
    for token in _SEP.split(joined):
        parts = [p.strip() for p in token.split(">") if p.strip().strip("-")]
        if parts:
            out.append(parts)
    return out


def diff_cell(original: list[str], final_cell) -> tuple[list[str], list[Log]]:
    chains = parse_chains(final_cell)
    heads = [c[0] for c in chains]
    removed = [o for o in original if o not in heads]
    added = [h for h in heads if h not in original]
    if len(removed) == len(added) == 1:  # 한 명을 덮어쓴 칸은 교체로 본다
        logs: list[Log] = [(removed[0], added[0])]
    else:  # 여러 명이 바뀌면 누가 누구를 대신했는지 모르므로 제거/추가로 남긴다
        logs = [(o, None) for o in removed] + [(None, h) for h in added]
    for c in chains:
        logs.extend(zip(c, c[1:]))
    return [c[-1] for c in chains], logs


def _as_date(v):
    if isinstance(v, datetime):
        return v.date()
    return v if isinstance(v, date) else None


def read_grid(ws, header_row: int) -> tuple[dict[date, dict[str, str]], list[str]]:
    rows = list(ws.iter_rows(min_row=header_row, values_only=True))
    if not rows:
        raise ValueError(f"{ws.title}: 비어 있습니다")
    cols = {i: CELL_BY_LABEL[str(h).strip()] for i, h in enumerate(rows[0]) if h is not None and str(h).strip() in CELL_BY_LABEL}
    missing = [cell_label(c) for c in CELLS if c not in cols.values()]
    if missing:  # 열이 빠지면 빈 칸으로 읽혀 전원 제거로 잘못 이관된다
        raise ValueError(f"{ws.title}: 열이 없습니다 — {', '.join(missing)}")
    grid: dict[date, dict[str, str]] = {}
    errors: list[str] = []
    for n, r in enumerate(rows[1:], start=header_row + 1):
        d = _as_date(r[0]) if r else None
        if not d and r and r[0] is not None and str(r[0]).strip():
            errors.append(f"{ws.title} {n}행: 날짜가 아닙니다: {r[0]!r}")
        if d:
            if d in grid:
                raise ValueError(f"{ws.title}: 날짜 중복 {d}")
            grid[d] = {cell: "" if i >= len(r) or r[i] is None else str(r[i]) for i, cell in cols.items()}
    return grid, errors


def read_members(ws) -> tuple[list[dict], list[str]]:
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError(f"{ws.title}: 비어 있습니다")
    idx = {str(h).strip(): i for i, h in enumerate(rows[0]) if h is not None}
    missing = [c for c in ("id", "department", "name", "part", "type", "is_active") if c not in idx]
    if missing:
        raise ValueError(f"{ws.title}: 열이 없습니다 — {', '.join(missing)}")
    out: list[dict] = []
    errors: list[str] = []
    for n, r in enumerate(rows[1:], start=2):
        if not any(c is not None and str(c).strip() for c in r):
            continue
        blank = [c for c in ("id", "department", "name", "type") if r[idx[c]] is None or not str(r[idx[c]]).strip()]
        if blank:
            errors.append(f"{ws.title} {n}행: 비어 있는 값 — {', '.join(blank)}")
            continue
        if str(r[idx["type"]]).strip() not in (DEVELOPER, STAFF):
            errors.append(f"{ws.title} {n}행: 알 수 없는 구분 {str(r[idx['type']]).strip()!r}")
            continue
        active = r[idx["is_active"]]
        out.append({
            "code": str(r[idx["id"]]).strip(),
            "department": str(r[idx["department"]]).strip(),
            "name": str(r[idx["name"]]).strip(),
            "part": str(r[idx["part"]] or "").strip(),
            "type": str(r[idx["type"]]).strip(),
            "is_active": active is True or str(active).upper() == "TRUE",
        })
    return out, errors


@dataclass
class ImportReport:
    members: int = 0
    dates: int = 0
    commutes: int = 0
    duties: int = 0
    changes: int = 0
    errors: list[str] = field(default_factory=list)


def run_import(maker: bytes, deploy: bytes, dry_run: bool) -> ImportReport:
    report = ImportReport()
    if Period.objects.filter(name=IMPORT_PERIOD_NAME).exists():
        report.errors.append("이미 가져온 회차(시트 이관)가 있습니다.")
        return report
    try:
        mk = openpyxl.load_workbook(BytesIO(maker), data_only=True)
        dp = openpyxl.load_workbook(BytesIO(deploy), data_only=True)
    except Exception:  # BadZipFile, InvalidFileException 등
        report.errors.append("xlsx 파일을 읽을 수 없습니다.")
        return report
    try:
        members, errors = read_members(mk["tb_member"])
        original, e1 = read_grid(dp["view_all_combine"], 1)
        final, e2 = read_grid(dp["근무표"], 2)
    except KeyError as e:
        report.errors.append(f"시트가 없습니다: {e.args[0]}")
        return report
    except ValueError as e:
        report.errors.append(str(e))
        return report
    errors += e1 + e2
    dept_codes = {name: code for code, name, _ in DEPARTMENTS}
    names: set[str] = set()
    codes: set[str] = set()
    for m in members:
        if m["code"] in codes:
            errors.append(f"멤버 코드 중복: {m['code']}")
        codes.add(m["code"])
        if m["department"] not in dept_codes:
            errors.append(f"{m['name']}: 알 수 없는 부서 {m['department']}")
        if m["name"] in names:
            errors.append(f"멤버 이름 중복: {m['name']}")
        names.add(m["name"])

    errors += [f"{d}: view_all_combine에 없는 날짜" for d in sorted(set(final) - set(original))]
    plan: dict[date, dict[str, tuple[list[str], list[Log]]]] = {}
    for d in sorted(original):
        if d not in final:
            errors.append(f"{d}: 근무표에 없는 날짜")
            continue
        day = {}
        origs = {}
        for cell in CELLS:
            origs[cell] = [n for c in parse_chains(original[d].get(cell)) for n in c]
            fin, logs = diff_cell(origs[cell], final[d].get(cell))
            for n in sorted({*fin, *(x for pair in logs for x in pair if x)}):
                if n not in names:
                    errors.append(f"{d} {cell_label(cell)}: 멤버에 없는 이름 '{n}'")
            if is_slot_cell(cell) and len(fin) != 1:
                errors.append(f"{d} {cell_label(cell)}: 관제 칸은 1명이어야 합니다 ({', '.join(fin) or '비어 있음'})")
            day[cell] = (fin, logs)
        # 새로 들어간 출근조가 있으면, 원래 있던 다른 출근조에서는 이동한 것으로 보고 뺀다
        commute_cells = [c for c in CELLS if not is_slot_cell(c)]
        for c in commute_cells:
            for n in day[c][0]:
                if n in origs[c]:
                    continue
                for c2 in commute_cells:
                    if c2 != c and n in origs[c2] and n in day[c2][0]:
                        day[c2][0].remove(n)
                        day[c2][1].append((n, None))
        commute_seen: dict[str, str] = {}
        for c in commute_cells:
            for n in day[c][0]:
                if n in commute_seen:
                    errors.append(f"{d}: {n}이(가) {cell_label(commute_seen[n])}·{cell_label(c)}에 중복")
                commute_seen[n] = c
        plan[d] = day

    if not plan:
        errors.append("가져올 날짜가 없습니다")
    report.members, report.dates = len(members), len(plan)
    for day in plan.values():
        for cell, (fin, logs) in day.items():
            if is_slot_cell(cell):
                report.duties += len(fin)
            else:
                report.commutes += len(fin)
            report.changes += len(logs)
    report.errors = errors
    if errors or dry_run:
        return report
    _write(members, plan, dept_codes)
    return report


@transaction.atomic
def _write(members, plan, dept_codes) -> None:
    for code, name, shifts in DEPARTMENTS:
        Department.objects.update_or_create(code=code, defaults={"name": name, "shifts": shifts})
    by_name = {}
    for m in members:
        obj, _ = Member.objects.update_or_create(code=m["code"], defaults={
            "name": m["name"], "department_id": dept_codes[m["department"]],
            "part": m["part"], "type": m["type"], "is_active": m["is_active"],
        })
        by_name[obj.name] = obj
    dates = sorted(plan)
    period = Period.objects.create(
        name=IMPORT_PERIOD_NAME, start_date=dates[0], end_date=dates[-1],
        status=Period.Status.PUBLISHED, published_at=timezone.now(), overwrite_from=dates[0],
    )
    commutes, duties, logs = [], [], []
    for d, day in plan.items():
        for cell, (fin, pairs) in day.items():
            for n in fin:
                if is_slot_cell(cell):
                    duties.append(ControlDuty(period=period, date=d, slot=slot_index(cell), member=by_name[n]))
                else:
                    commutes.append(Commute(period=period, date=d, member=by_name[n], shift=cell))
            for before, after in pairs:
                logs.append(ChangeLog(
                    by=None, period=period, date=d, cell=cell,
                    before=by_name[before] if before else None, after=by_name[after] if after else None,
                ))
    Commute.objects.bulk_create(commutes)
    ControlDuty.objects.bulk_create(duties)
    ChangeLog.objects.bulk_create(logs)
