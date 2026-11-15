from datetime import date

from django.db import transaction

from .. import perms
from ..errors import DutyError
from ..models import ChangeLog, Commute, DutyAssignment, Period, User
from ..shifts import Def, by_key, cell_label, is_slot_cell
from . import boards


def _owner(board, d: date) -> Period:
    p = boards.owner(board, d)  # 그날의 주인(설계 6.1): 기간·배포 순번으로 정한다. 행이 없는 날도 주인이 있다
    if p is None:
        raise DutyError("배포된 근무표에 없는 날짜입니다.")
    return p


def _slot_duties(period: Period, d: date, member: User):
    """그날 그 사람의 장중관제 배정(같은 묶음만. 다른 당번 칸과 섞지 않는다)."""
    return DutyAssignment.objects.filter(period=period, date=d, member=member, cell__startswith="slot")


def _eligibility_warnings(defs: list[Def], period: Period, d: date, cell: str, m: User) -> list[str]:
    df, names = by_key(defs)[cell], {x.key: x.name for x in defs}
    out = []
    if df.eligible_types and m.type not in df.eligible_types:
        out.append(f"{m.name}은(는) {'·'.join(df.eligible_types)}가 아닙니다.")
    shift = Commute.objects.filter(period=period, date=d, member=m).values_list("shift", flat=True).first()
    if shift not in df.eligible_shifts:
        out.append(f"{m.name}의 그날 출근조({names.get(shift, '없음')})는 {df.name} 관제 자격이 아닙니다.")
    return out


def _duty_warnings(defs: list[Def], period: Period, d: date, members) -> list[str]:
    """출근조가 바뀐 사람이 관제 칸을 갖고 있으면 자격을 다시 확인한다(경고만)."""
    out = []
    for m in members:
        if m is None:
            continue
        for duty in _slot_duties(period, d, m):
            out += _eligibility_warnings(defs, period, d, duty.cell, m)
    return out


def _check_cell(defs: list[Def], *cells: str) -> None:
    keys = {x.key for x in defs}
    if any(c not in keys for c in cells):
        raise DutyError("알 수 없는 칸입니다.")


def _check_active(m: User | None) -> None:
    if m is not None and not m.is_active:
        raise DutyError(f"{m.name}은(는) 재직 중이 아닙니다.")


def _check_candidate(board, m: User | None) -> None:
    """새로 들이는 사람은 그 근무표 부서의 재직자만(빼기만은 검사하지 않는다: 부서를 옮긴 사람의 옛 행 정리)."""
    _check_active(m)
    if m is not None and (m.department_id is None or m.department.board_id != board.pk):
        raise DutyError(f"{m.name}은(는) 근무표 대상이 아닙니다.")


@transaction.atomic
def change_cell(user, board, d: date, cell: str, before: User | None, after: User | None) -> list[str]:
    perms.assert_can_edit(user, board, d)
    period = _owner(board, d)
    defs = boards.defs(board)
    _check_cell(defs, cell)
    if (before is None and after is None) or before == after:
        raise DutyError("변경할 내용이 없습니다.")
    _check_candidate(board, after)
    warnings: list[str] = []
    if is_slot_cell(cell):
        if before is None or after is None:
            raise DutyError("관제 칸은 교체만 할 수 있습니다.")
        row = DutyAssignment.objects.filter(period=period, date=d, cell=cell).first()
        if row is None or row.member_id != before.pk:
            raise DutyError(f"{before.name}은(는) 이 칸에 없습니다.")
        row.member = after
        row.save()
        warnings = _eligibility_warnings(defs, period, d, cell, after)
        others = _slot_duties(period, d, after).exclude(cell=cell).order_by("cell")  # slot0~slot9: 글자 순 = 칸 순
        if others:
            labels = ", ".join(cell_label(defs, o.cell) for o in others)
            warnings.append(f"{after.name}은(는) 그날 다른 관제 칸({labels})도 맡고 있습니다.")
    else:
        row = None
        if before is not None:
            row = Commute.objects.filter(period=period, date=d, member=before, shift=cell).first()
            if row is None:
                raise DutyError(f"{before.name}은(는) 이 칸에 없습니다.")
        if after is not None and Commute.objects.filter(period=period, date=d, member=after).exists():
            raise DutyError(f"{after.name}은(는) 그날 이미 다른 출근조에 있습니다. 맞교환을 사용하세요.")
        if row is not None:
            row.delete()
        if after is not None:
            Commute.objects.create(period=period, date=d, member=after, shift=cell)
        warnings = _duty_warnings(defs, period, d, [before, after])
    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell, before=before, after=after)
    return warnings


@transaction.atomic
def exchange(user, board, d: date, cell: str, before: User | None, after: User | None) -> list[str]:
    """근무 변경 창의 저장. 둘 다 있으면 기본은 맞교환: To 가 그날 같은 묶음 다른 칸에 있으면 서로 바꾸고,
    없으면 From 대신 들어간다. 한쪽만 있으면 넣기·빼기(change_cell)."""
    perms.assert_can_edit(user, board, d)
    if before is None or after is None:
        return change_cell(user, board, d, cell, before, after)
    _check_cell(boards.defs(board), cell)
    period = _owner(board, d)
    if is_slot_cell(cell):
        rows = list(_slot_duties(period, d, after).exclude(cell=cell))
        if len(rows) > 1:
            raise DutyError(f"{after.name}은(는) 그날 장중관제가 여러 칸이라 맞바꿀 칸을 정할 수 없습니다. "
                            f"{after.name}의 칸을 눌러 거기서 바꿔 주세요.")
        if DutyAssignment.objects.filter(period=period, date=d, cell=cell, member=after).exists():
            raise DutyError(f"{after.name}은(는) 이미 이 칸에 있습니다.")
        other = rows[0].cell if rows else None
    else:
        other = Commute.objects.filter(period=period, date=d, member=after).values_list("shift", flat=True).first()
    if other == cell:
        raise DutyError(f"{after.name}은(는) 이미 이 칸에 있습니다.")
    if other:
        return swap(user, board, d, cell, before, other, after)
    return change_cell(user, board, d, cell, before, after)


@transaction.atomic
def swap(user, board, d: date, cell_a: str, a: User, cell_b: str, b: User) -> list[str]:
    perms.assert_can_edit(user, board, d)
    period = _owner(board, d)
    defs = boards.defs(board)
    _check_cell(defs, cell_a, cell_b)
    _check_candidate(board, a)  # 퇴사자·다른 근무표 사람을 다른 칸으로 옮기는 것도 새 배정이다
    _check_candidate(board, b)
    if a == b or cell_a == cell_b:
        raise DutyError("서로 다른 두 칸의 서로 다른 사람을 골라 주세요.")
    if is_slot_cell(cell_a) != is_slot_cell(cell_b):
        raise DutyError("출근조끼리 또는 관제 칸끼리만 맞교환할 수 있습니다.")
    warnings: list[str] = []
    if is_slot_cell(cell_a):
        ra = DutyAssignment.objects.filter(period=period, date=d, cell=cell_a, member=a).first()
        rb = DutyAssignment.objects.filter(period=period, date=d, cell=cell_b, member=b).first()
        if ra is None or rb is None:
            raise DutyError("선택한 사람이 해당 칸에 없습니다.")
        ra.delete()
        rb.delete()
        DutyAssignment.objects.create(period=period, date=d, cell=cell_a, member=b)
        DutyAssignment.objects.create(period=period, date=d, cell=cell_b, member=a)
        warnings = _eligibility_warnings(defs, period, d, cell_a, b) + _eligibility_warnings(defs, period, d, cell_b, a)
    else:
        ra = Commute.objects.filter(period=period, date=d, member=a, shift=cell_a).first()
        rb = Commute.objects.filter(period=period, date=d, member=b, shift=cell_b).first()
        if ra is None or rb is None:
            raise DutyError("선택한 사람이 해당 칸에 없습니다.")
        ra.shift, rb.shift = cell_b, cell_a
        ra.save()
        rb.save()
        warnings = _duty_warnings(defs, period, d, [a, b])
    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell_a, before=a, after=b)
    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell_b, before=b, after=a)
    return warnings
