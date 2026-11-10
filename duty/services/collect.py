from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count

from .. import perms
from ..csv_io import CommuteTable, CsvError, CsvInvalid, export_commute_csv, parse_commute_csv
from ..errors import DutyError
from ..models import Commute, Department, Member, Period
from ..shifts import COMMUTE_SHIFTS


def _require_input(user, period: Period, dept: Department) -> None:
    if not perms.can_input_department(user, dept):
        raise PermissionDenied("이 부서의 출근표를 입력할 권한이 없습니다.")
    if period.status != Period.Status.COLLECTING:
        raise DutyError("취합 중인 회차가 아닙니다.")


def load_table(period: Period, dept: Department) -> CommuteTable:
    table: CommuteTable = {}
    rows = (
        Commute.objects.filter(period=period, member__department=dept)
        .select_related("member")
        .order_by("date", "member__code")
    )
    for c in rows:
        table.setdefault(c.date, {}).setdefault(c.shift, []).append(c.member.name)
    return table


def _norm(day: dict[str, list[str]]) -> dict[str, list[str]]:
    return {k: sorted(v) for k, v in day.items() if v}


def validate_table(user, period: Period, dept: Department, table: CommuteTable) -> list[CsvError]:
    errors: list[CsvError] = []
    valid_dates = set(period.dates())
    shift_keys = dept.shift_keys()
    existing = load_table(period, dept)
    members = set(Member.objects.filter(department=dept, is_active=True).values_list("name", flat=True))
    for d in sorted(table):
        col = d.isoformat()
        if d not in valid_dates:
            errors.append(CsvError(0, col, "회차 기간의 평일이 아닙니다."))
            continue
        if _norm(table[d]) == _norm(existing.get(d, {})):
            continue  # 변경 없는 날짜는 재검증하지 않는다 (퇴사자 이름이 남아 있어도 다른 수정을 막지 않음)
        seen: dict[str, str] = {}
        for key, names in table[d].items():
            if names and key not in shift_keys:
                errors.append(CsvError(0, col, f"{dept.name}에는 {COMMUTE_SHIFTS[key]} 출근조가 없습니다."))
                continue
            for name in names:
                if name not in members:
                    errors.append(CsvError(0, col, f"{dept.name}의 재직 멤버가 아닙니다: {name}"))
                elif name in seen:
                    errors.append(CsvError(0, col, f"{name}: {COMMUTE_SHIFTS[seen[name]]}·{COMMUTE_SHIFTS[key]}에 중복"))
                else:
                    seen[name] = key
    if not perms.is_admin(user):
        today = perms.today()
        for d in sorted(x for x in set(table) | set(existing) if x < today):
            if _norm(table.get(d, {})) != _norm(existing.get(d, {})):
                errors.append(CsvError(0, d.isoformat(), "지난 날짜는 어드민만 수정할 수 있습니다."))
    return errors


@transaction.atomic
def apply_table(user, period: Period, dept: Department, table: CommuteTable) -> int:
    _require_input(user, period, dept)
    errors = validate_table(user, period, dept, table)
    if errors:
        raise CsvInvalid(errors)
    by_name = {m.name: m for m in Member.objects.filter(department=dept)}
    Commute.objects.filter(period=period, member__department=dept).delete()
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
    return apply_table(user, period, dept, parse_commute_csv(raw, dept.shift_keys()))


def export_csv(period: Period, dept: Department) -> bytes:
    return export_commute_csv(period.dates(), dept.shift_keys(), load_table(period, dept))


def progress(period: Period) -> dict[str, tuple[int, int]]:
    total = len(period.dates())
    filled = dict(
        Commute.objects.filter(period=period)
        .values("member__department")
        .annotate(n=Count("date", distinct=True))
        .values_list("member__department", "n")
    )
    return {d.code: (filled.get(d.code, 0), total) for d in Department.objects.order_by("code")}
