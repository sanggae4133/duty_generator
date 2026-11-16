from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count

from .. import perms
from ..csv_io import (CommuteTable, CsvError, CsvInvalid, add_error, export_commute_csv, join_reason, parse_commute_csv,
                      split_reason)
from ..errors import DutyError
from ..models import Commute, Department, Period, User, step_label
from ..shifts import by_key, shift_defs
from . import boards


def _same_board(period: Period, dept: Department) -> None:
    if period.board_id != dept.board_id:
        raise DutyError("이 회차의 근무표에 속한 부서가 아닙니다.")


def _require_input(user, period: Period, dept: Department) -> None:
    if not perms.can_input_department(user, dept):
        raise PermissionDenied("이 부서의 출근표를 입력할 권한이 없습니다.")
    _same_board(period, dept)
    if period.status != Period.Status.COLLECTING:
        raise DutyError(f"{step_label(period.board, Period.Status.COLLECTING)}인 회차가 아닙니다.")  # 취합 중 / 입력 중


def input_keys(dept: Department) -> list[str]:
    """입력 표·CSV 의 근무조 키: 부서 출근조 가운데 켜진 근무조 정의가 있는 것. 순서 = 부서 출근조 순서."""
    on = {x.key for x in shift_defs(boards.active_defs(dept.board))}
    return [k for k in dept.shift_keys() if k in on]


def _kept_keys(dept: Department) -> set[str]:
    """저장해도 지우지 않는 근무조: 꺼진 근무조 정의(설계 6.2). 부서 출근조에서 뺀 근무조는 예전처럼 지운다."""
    return {x.key for x in boards.defs(dept.board) if not x.active}


def shift_names(dept: Department) -> dict[str, str]:
    """{입력 키: 근무 정의 이름}. 키·순서는 input_keys 와 같다(입력 표 머리글·CSV 열 이름)."""
    labels = by_key(boards.active_defs(dept.board))
    return {k: labels[k].name for k in input_keys(dept)}


def load_table(period: Period, dept: Department) -> CommuteTable:
    _same_board(period, dept)
    table: CommuteTable = {}
    rows = (
        Commute.objects.filter(period=period, member__department=dept)
        .select_related("member")
        .order_by("date", "member__username")
    )
    for c in rows:
        table.setdefault(c.date, {}).setdefault(c.shift, []).append(join_reason(c.member.name, c.reason))  # 이름(휴가)
    return table


def _norm(day: dict[str, list[str]]) -> dict[str, list[str]]:
    return {k: sorted(v) for k, v in day.items() if v}


def validate_table(user, period: Period, dept: Department, table: CommuteTable) -> list[CsvError]:
    errors: list[CsvError] = []
    valid_dates = set(period.dates())
    shift_keys = input_keys(dept)
    labels = by_key(boards.defs(dept.board))
    kept_keys = _kept_keys(dept)
    loaded = load_table(period, dept)
    existing = {d: {k: v for k, v in day.items() if k not in kept_keys} for d, day in loaded.items()}
    kept = {d: {split_reason(n)[0] for k, v in day.items() if k in kept_keys for n in v} for d, day in loaded.items()}
    members = set(User.objects.roster().filter(department=dept).values_list("name", flat=True))
    skip = boards.skip_reasons(period)
    for d in sorted(table):
        col = d.isoformat()
        if d not in valid_dates:
            add_error(errors, CsvError(0, col, "회차 기간의 평일이 아닙니다."))
            continue
        if d in skip:  # 건너뛰는 날은 비워 둔다. 이미 있는 행은 저장해도 남는다(apply_table)
            if any(table[d].values()):
                add_error(errors, CsvError(0, col, f"{skip[d]}: 근무를 넣지 않는 날입니다."))
            continue
        if _norm(table[d]) == _norm(existing.get(d, {})):
            continue  # 변경 없는 날짜는 재검증하지 않는다 (퇴사자 이름이 남아 있어도 다른 수정을 막지 않음)
        seen: dict[str, str] = {}
        for key, names in table[d].items():
            if names and key not in shift_keys:
                add_error(errors, CsvError(0, col, f"{dept.name}에는 {labels[key].name} 출근조가 없습니다."))
                continue
            for name in (split_reason(n)[0] for n in names):  # 사유는 떼고 사람만 본다
                if name not in members:
                    add_error(errors, CsvError(0, col, f"{dept.name}의 재직 멤버가 아닙니다: {name}"))
                elif name in kept.get(d, ()):
                    add_error(errors, CsvError(0, col, f"{name}: 이미 사용하지 않는 근무조에 배정돼 있습니다"))
                elif name in seen:
                    add_error(errors, CsvError(0, col, f"{name}: {labels[seen[name]].name}·{labels[key].name}에 중복"))
                else:
                    seen[name] = key
    if not perms.is_board_admin(user, period.board):
        today = perms.today()
        for d in sorted(x for x in set(table) | set(existing) if x < today and x not in skip):
            if _norm(table.get(d, {})) != _norm(existing.get(d, {})):
                add_error(errors, CsvError(0, d.isoformat(), "지난 날짜는 어드민만 수정할 수 있습니다."))
    return errors


@transaction.atomic
def apply_table(user, period: Period, dept: Department, table: CommuteTable) -> int:
    period.refresh_from_db()  # 그사이 마감됐으면 막는다
    _require_input(user, period, dept)
    errors = validate_table(user, period, dept, table)
    if errors:
        raise CsvInvalid(errors)
    by_name = {m.name: m for m in User.objects.filter(department=dept)}
    (Commute.objects.filter(period=period, member__department=dept)
     .exclude(shift__in=_kept_keys(dept)).exclude(date__in=boards.skip_dates(period)).delete())
    rows = [
        Commute(period=period, date=d, member=by_name[name], shift=key, reason=why)
        for d, day in table.items()
        for key, names in day.items()
        for name, why in map(split_reason, names)
    ]
    Commute.objects.bulk_create(rows)
    return len(rows)


def apply_csv(user, period: Period, dept: Department, raw: bytes) -> int:
    _require_input(user, period, dept)
    return apply_table(user, period, dept, parse_commute_csv(raw, shift_names(dept)))


def export_csv(period: Period, dept: Department) -> bytes:
    _same_board(period, dept)
    skip = boards.skip_dates(period)  # 건너뛰는 날은 빈 줄로(내려받은 그대로 다시 올려도 오류가 없게)
    table = {d: day for d, day in load_table(period, dept).items() if d not in skip}
    return export_commute_csv(period.dates(), shift_names(dept), table)


def progress(period: Period) -> dict[str, tuple[int, int]]:
    """부서마다 (출근표가 있는 날 수, 입력할 날 수). 건너뛰는 날은 양쪽에서 뺀다."""
    skip = boards.skip_dates(period)
    total = len([d for d in period.dates() if d not in skip])
    filled = dict(
        Commute.objects.filter(period=period).exclude(date__in=skip)
        .values("member__department")
        .annotate(n=Count("date", distinct=True))
        .values_list("member__department", "n")
    )
    depts = Department.objects.filter(board_id=period.board_id).order_by("code")
    return {d.code: (filled.get(d.code, 0), total) for d in depts}
