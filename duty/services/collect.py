from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count

from .. import perms
from ..csv_io import CommuteTable, CsvError, CsvInvalid, add_error, export_commute_csv, parse_commute_csv
from ..errors import DutyError
from ..models import Commute, Department, Period, User
from ..shifts import by_key, shift_defs
from . import boards


def _require_input(user, period: Period, dept: Department) -> None:
    if not perms.can_input_department(user, dept):
        raise PermissionDenied("이 부서의 출근표를 입력할 권한이 없습니다.")
    if period.status != Period.Status.COLLECTING:
        raise DutyError("취합 중인 회차가 아닙니다.")


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
    table: CommuteTable = {}
    rows = (
        Commute.objects.filter(period=period, member__department=dept)
        .select_related("member")
        .order_by("date", "member__username")
    )
    for c in rows:
        table.setdefault(c.date, {}).setdefault(c.shift, []).append(c.member.name)
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
    kept = {d: {n for k, v in day.items() if k in kept_keys for n in v} for d, day in loaded.items()}
    members = set(User.objects.roster().filter(department=dept).values_list("name", flat=True))
    for d in sorted(table):
        col = d.isoformat()
        if d not in valid_dates:
            add_error(errors, CsvError(0, col, "회차 기간의 평일이 아닙니다."))
            continue
        if _norm(table[d]) == _norm(existing.get(d, {})):
            continue  # 변경 없는 날짜는 재검증하지 않는다 (퇴사자 이름이 남아 있어도 다른 수정을 막지 않음)
        seen: dict[str, str] = {}
        for key, names in table[d].items():
            if names and key not in shift_keys:
                add_error(errors, CsvError(0, col, f"{dept.name}에는 {labels[key].name} 출근조가 없습니다."))
                continue
            for name in names:
                if name not in members:
                    add_error(errors, CsvError(0, col, f"{dept.name}의 재직 멤버가 아닙니다: {name}"))
                elif name in kept.get(d, ()):
                    add_error(errors, CsvError(0, col, f"{name}: 이미 사용하지 않는 근무조에 배정돼 있습니다"))
                elif name in seen:
                    add_error(errors, CsvError(0, col, f"{name}: {labels[seen[name]].name}·{labels[key].name}에 중복"))
                else:
                    seen[name] = key
    if not perms.is_admin(user):
        today = perms.today()
        for d in sorted(x for x in set(table) | set(existing) if x < today):
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
    Commute.objects.filter(period=period, member__department=dept).exclude(shift__in=_kept_keys(dept)).delete()
    rows = [
        Commute(period=period, date=d, member=by_name[n], shift=key)
        for d, day in table.items()
        for key, names in day.items()
        for n in names
    ]
    Commute.objects.bulk_create(rows)
    return len(rows)


def apply_csv(user, period: Period, dept: Department, raw: bytes) -> int:
    _require_input(user, period, dept)
    return apply_table(user, period, dept, parse_commute_csv(raw, shift_names(dept)))


def export_csv(period: Period, dept: Department) -> bytes:
    return export_commute_csv(period.dates(), shift_names(dept), load_table(period, dept))


def progress(period: Period) -> dict[str, tuple[int, int]]:
    total = len(period.dates())
    filled = dict(
        Commute.objects.filter(period=period)
        .values("member__department")
        .annotate(n=Count("date", distinct=True))
        .values_list("member__department", "n")
    )
    return {d.code: (filled.get(d.code, 0), total) for d in Department.objects.order_by("code")}
