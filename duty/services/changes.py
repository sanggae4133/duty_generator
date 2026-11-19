from datetime import date

from django.db import transaction

from .. import perms
from ..errors import DutyError
from ..models import ChangeLog, Commute, DutyAssignment, Period, User
from ..shifts import LUNCH, REASONS, SHIFT, SLOT_GROUP_NAME, Def, by_key, cell_label, is_slot_cell, kind
from . import boards, memos


def _owner(board, d: date) -> Period:
    p = boards.owner(board, d)  # 그날의 주인(설계 6.1): 기간·배포 순번으로 정한다. 행이 없는 날도 주인이 있다
    if p is None:
        raise DutyError("배포된 근무표에 없는 날짜입니다.")
    if memos.no_work_days(board, d, d):  # 근무 없음 날은 늘 비어 있다(설계 6.4). 휴장일은 막지 않는다
        raise DutyError("근무 없는 날입니다.")
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


def _carry_lunch(user, period: Period, d: date, before: User, after: User) -> None:
    """점심당번도 같이 넘기기(설계 6.4): 떠나는 사람이 그날 점심당번이고 들어오는 사람은 아니면 넘긴다.
    기록은 근무조 기록 **뒤에** 남긴다(맞교환 기록 둘 사이에 끼면 변경 알림의 짝짓기가 깨진다)."""
    rows = DutyAssignment.objects.filter(period=period, date=d, cell=LUNCH)
    row = rows.filter(member=before).first()
    if row is None or rows.filter(member=after).exists():
        return
    row.member = after
    row.save()
    ChangeLog.objects.create(by=user, period=period, date=d, cell=LUNCH, before=before, after=after)


@transaction.atomic
def change_cell(user, board, d: date, cell: str, before: User | None, after: User | None,
                carry_lunch: bool = True) -> list[str]:
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
    elif cell == LUNCH:  # 혼자인 당번 칸: 넣기·빼기·교체, 인원 제한 없음
        rows = DutyAssignment.objects.filter(period=period, date=d, cell=cell)
        row = rows.filter(member=before).first() if before is not None else None
        if before is not None and row is None:
            raise DutyError(f"{before.name}은(는) 이 칸에 없습니다.")
        if after is not None and rows.filter(member=after).exists():
            raise DutyError(f"{after.name}은(는) 이미 이 칸에 있습니다.")
        if row is not None:
            row.delete()
        if after is not None:
            DutyAssignment.objects.create(period=period, date=d, cell=cell, member=after)
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
    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell, before=before, after=after,
                             reason_before=getattr(row, "reason", ""))  # 빠진 사람의 사유는 기록에 남긴다(관제 행에는 없다)
    if carry_lunch and kind(cell) == SHIFT and before is not None and after is not None:
        _carry_lunch(user, period, d, before, after)
    return warnings


@transaction.atomic
def set_reason(user, board, d: date, member: User, reason: str) -> list[str]:
    """근무조 배정에 사유(휴가·출장·교육, 빈 값 = 없음)를 붙이거나 뗀다. 사람은 그대로라 기록은 before == after 이고
    변경 알림은 나가지 않는다(설계 6.4). 당번 칸은 자동으로 빼지 않고 경고만 한다. 이미 보낸 개인 알림은 되돌리지 않는다."""
    perms.assert_can_edit(user, board, d)
    period = _owner(board, d)
    if reason not in ("", *REASONS):
        raise DutyError("알 수 없는 사유입니다.")
    row = Commute.objects.filter(period=period, date=d, member=member).first()
    if row is None:
        raise DutyError(f"{member.name}은(는) 그날 근무조에 없습니다.")
    if row.reason == reason:
        raise DutyError("변경할 내용이 없습니다.")
    ChangeLog.objects.create(by=user, period=period, date=d, cell=row.shift, before=member, after=member,
                             reason_before=row.reason, reason_after=reason)
    row.reason = reason
    row.save(update_fields=["reason"])
    duties = DutyAssignment.objects.filter(period=period, date=d, member=member).order_by("cell") if reason else []
    if not duties:
        return []
    defs = boards.defs(board)
    labels = ", ".join(f"{SLOT_GROUP_NAME} {cell_label(defs, x.cell)}" if is_slot_cell(x.cell) else cell_label(defs, x.cell)
                       for x in duties)
    solo = ", ".join(dict.fromkeys(cell_label(defs, x.cell) for x in duties if not is_slot_cell(x.cell)))
    if not any(is_slot_cell(x.cell) for x in duties):  # 점심당번 칸은 비워도 된다
        todo = "다른 사람으로 바꾸거나 빼세요."
    else:  # 관제 칸은 교체만(change_cell)
        todo = f"다른 사람으로 바꾸세요({solo} 칸은 빼도 됩니다)." if solo else "다른 사람으로 바꾸세요."
    return [f"{member.name}은(는) 그날 {labels} 칸에 남아 있습니다. 그 칸을 눌러 {todo}"]


@transaction.atomic
def exchange(user, board, d: date, cell: str, before: User | None, after: User | None,
             carry_lunch: bool = True, keep_other: bool = False) -> list[str]:
    """근무 변경 창의 저장. 둘 다 있으면 기본은 맞교환: To 가 그날 같은 묶음 다른 칸에 있으면 서로 바꾸고,
    없으면 From 대신 들어간다. 한쪽만 있으면 넣기·빼기(change_cell). 점심당번은 묶음이 혼자라 늘 교체.
    carry_lunch: 근무조 칸에서 From 이 점심당번이면 To 에게 넘긴다.
    keep_other: 관제 칸에서 To 의 다른 관제 칸은 그대로 두고 이 칸에도 넣는다(맞바꾸지 않음, From 휴가 등).
    근무조는 한 사람 하루 하나라 무시한다."""
    perms.assert_can_edit(user, board, d)
    if before is None or after is None or (keep_other and is_slot_cell(cell)):
        return change_cell(user, board, d, cell, before, after, carry_lunch)
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
    elif cell == LUNCH:
        other = None  # 같은 묶음에 다른 칸이 없다(관제와 맞교환하지 않는다)
    else:
        other = Commute.objects.filter(period=period, date=d, member=after).values_list("shift", flat=True).first()
    if other == cell:
        raise DutyError(f"{after.name}은(는) 이미 이 칸에 있습니다.")
    if other:
        return swap(user, board, d, cell, before, other, after, carry_lunch)
    return change_cell(user, board, d, cell, before, after, carry_lunch)


@transaction.atomic
def swap(user, board, d: date, cell_a: str, a: User, cell_b: str, b: User, carry_lunch: bool = True) -> list[str]:
    perms.assert_can_edit(user, board, d)
    period = _owner(board, d)
    defs = boards.defs(board)
    _check_cell(defs, cell_a, cell_b)
    _check_candidate(board, a)  # 퇴사자·다른 근무표 사람을 다른 칸으로 옮기는 것도 새 배정이다
    _check_candidate(board, b)
    if a == b or cell_a == cell_b:
        raise DutyError("서로 다른 두 칸의 서로 다른 사람을 골라 주세요.")
    if kind(cell_a) != kind(cell_b):  # 점심당번끼리는 위의 같은 칸 검사에 걸린다(혼자인 칸)
        raise DutyError("출근조끼리 또는 관제 칸끼리만 맞교환할 수 있습니다.")
    warnings: list[str] = []
    why_a = why_b = ""  # 사유는 사람을 따라간다(근무조 행만 있다). 두 기록 모두에 남긴다
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
        why_a, why_b = ra.reason, rb.reason
        ra.shift, rb.shift = cell_b, cell_a
        ra.save()
        rb.save()
        warnings = _duty_warnings(defs, period, d, [a, b])
    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell_a, before=a, after=b,
                             reason_before=why_a, reason_after=why_b)
    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell_b, before=b, after=a,
                             reason_before=why_b, reason_after=why_a)
    if carry_lunch and kind(cell_a) == SHIFT:  # 맞교환은 두 사람 다 떠나는 사람: 점심당번인 쪽이 상대에게 넘긴다
        holder, other = (a, b) if DutyAssignment.objects.filter(period=period, date=d, cell=LUNCH, member=a).exists() else (b, a)
        _carry_lunch(user, period, d, holder, other)
    return warnings
