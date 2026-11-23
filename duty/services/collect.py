from datetime import date, timedelta

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count

from .. import perms
from ..csv_io import (CommuteTable, CsvError, CsvInvalid, add_error, export_commute_csv, join_reason, parse_commute_csv,
                      split_reason)
from ..errors import DutyError
from ..models import Commute, Department, Period, User
from ..shifts import SHIFT_KEYS, by_key, shift_defs, two_week_rotation, weekdays
from . import boards, roster


def _same_board(period: Period, dept: Department) -> None:
    if period.board_id != dept.board_id:
        raise DutyError("이 회차의 근무표에 속한 부서가 아닙니다.")


def _require_input(user, period: Period, dept: Department) -> None:
    if not perms.can_input_department(user, dept):
        raise PermissionDenied("이 부서의 출근표를 입력할 권한이 없습니다.")
    _same_board(period, dept)
    _require_collecting(period)


def _require_collecting(period: Period) -> None:
    if period.status != Period.Status.COLLECTING:
        raise DutyError(f"{period.board.step_name(Period.Status.COLLECTING)}인 회차가 아닙니다.")  # 취합 중 / 입력 중


def input_keys(dept: Department) -> list[str]:
    """입력 표·CSV 의 근무조 키: 부서 출근조 가운데 켜진 근무조 정의가 있는 것, 지금 시작 시각 순."""
    return boards.dept_keys(dept, boards.active_defs(dept.board))


def _kept_keys(dept: Department) -> set[str]:
    """저장해도 지우지 않는 근무조: 꺼진 근무조 정의(설계 6.2). 부서 출근조에서 뺀 근무조는 예전처럼 지운다."""
    return {x.key for x in boards.defs(dept.board) if not x.active}


def _kept_names(loaded: CommuteTable, kept_keys: set[str]) -> dict[date, set[str]]:
    """{날짜: 꺼진 근무조(보존 키)에 행이 있는 사람}. 그날 켜진 근무조에 다시 넣을 수 없다."""
    return {d: {split_reason(n)[0] for k, v in day.items() if k in kept_keys for n in v} for d, day in loaded.items()}


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
    kept = _kept_names(loaded, kept_keys)
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


FILL_2W, FILL_1W = "2w", "1w"  # [2주 전 기준으로 채우기], [지난주와 같게]


def can_rotate(dept: Department) -> bool:
    """[2주 전 기준으로 채우기]는 입력 근무조가 정확히 3개일 때만(이른·가운데·늦은 조가 정해지게, 설계 6.2)."""
    return len(input_keys(dept)) == 3


def _base(period: Period, table: CommuteTable, dates: list[date]) -> dict[date, dict[str, tuple[str, str]]]:
    """채우기의 기준 {날짜: {이름: (근무조, 사유)}}(설계 6.2): 회차 기간 안의 날은 지금 화면의 표(table, 저장 전 고친 것 포함),
    밖의 날은 배포된 근무표(그날의 주인 회차)."""
    inside = [d for d in dates if period.start_date <= d <= period.end_date]
    out = {d: {name: (k, why) for k, names in table.get(d, {}).items() for name, why in map(split_reason, names)}
           for d in inside}
    outside = [d for d in dates if d not in inside]
    if outside:
        for day in roster.published_days(period.board, min(outside), max(outside)):
            if day.date in outside:
                out[day.date] = {n: (k, day.reason(k, n)) for k in SHIFT_KEYS for n in day.members.get(k, [])}
    return out


def fill_week(period: Period, dept: Department, table: CommuteTable, day: date, how: str,
              keep_before: date | None = None) -> CommuteTable:
    """[2주 전 기준으로 채우기](how=FILL_2W)·[지난주와 같게](FILL_1W)(설계 6.2): day 가 든 주(회차 기간 ∩ 월~금)의 줄만
    다시 채운 새 표를 돌려준다. 다른 주는 table 그대로. 저장하지 않는다(저장은 [표 저장]과 기존 검증).
    지금 재직하는 그 부서 사람만 넣고, 건너뛰는 날(휴장일·근무 없음)은 비운다.
    keep_before: 이 날 전 줄도 table 그대로(관리자가 아니면 지난 날을 못 고치므로 저장 검증에 막히지 않게)."""
    _same_board(period, dept)
    _require_collecting(period)  # 모든 근무표, 입력을 받는 동안만(설계 6.1)
    if how not in (FILL_2W, FILL_1W):
        raise DutyError("알 수 없는 채우기입니다.")
    if how == FILL_2W and not can_rotate(dept):
        raise DutyError("2주 전 기준으로 채우기는 근무조가 3개일 때만 씁니다.")
    monday = day - timedelta(days=day.weekday())
    week = [d for d in period.dates() if monday <= d <= monday + timedelta(days=4)]
    if not week:
        raise DutyError("회차 기간 밖의 주입니다.")
    if keep_before:
        week = [d for d in week if d >= keep_before]
        if not week:  # 그 주가 모두 지난 날: 고칠 줄이 없다
            return dict(table)
    keys = input_keys(dept)
    names = list(User.objects.roster().filter(department=dept).order_by("name").values_list("name", flat=True))
    if how == FILL_2W:
        base = _base(period, table, weekdays(monday - timedelta(days=14), monday - timedelta(days=10)))
        counted = {d: {n: k for n, (k, why) in rows.items() if not why} for d, rows in base.items()}  # 근무로 친 날만
        if not any(counted.values()):  # 기준이 없으면 모두 가운데 조가 된다: 잘못 채운 표를 저장하지 않게 막는다
            raise DutyError("2주 전 그 주에 근무가 없어 채울 수 없습니다(이전 근무표가 배포되지 않았거나 비어 있음). 이 주는 직접 넣으세요.")
        order = [x.key for x in shift_defs(boards.active_defs(dept.board)) if x.key in keys]  # 시작 시각 순
        picks = two_week_rotation(counted, names, order)
        plan = {d: picks for d in week}
    else:  # 지난주 같은 요일을 그대로(사유는 옮기지 않는다)
        base = _base(period, table, [d - timedelta(days=7) for d in week])
        plan = {d: {n: k for n, (k, _) in base.get(d - timedelta(days=7), {}).items()} for d in week}
    skip = boards.skip_dates(period)
    kept = _kept_names(load_table(period, dept), _kept_keys(dept))  # 그날 꺼진 근무조에 남은 사람은 넣지 않는다
    out = {d: v for d, v in table.items() if d not in week}
    for d in week:
        row = {k: [n for n in names if plan[d].get(n) == k and n not in kept.get(d, ())] for k in keys}
        if d not in skip and any(row.values()):
            out[d] = row
    return out
