from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.db.models import Q

from .. import perms
from ..errors import DutyError
from ..models import ChangeLog, Commute, ControlDuty, Member, Period
from ..shifts import COMMUTE_SHIFTS, CONTROL_SLOTS, DEVELOPER, cell_label, is_slot_cell, slot_index


@dataclass
class ChangeResult:
    warnings: list[str]


def _owner(d: date) -> Period:
    p = (
        Period.objects.filter(status=Period.Status.PUBLISHED)
        .filter(Q(commute__date=d) | Q(controlduty__date=d))
        .distinct()
        .first()
    )
    if p is None:
        raise DutyError("배포된 근무표에 없는 날짜입니다.")
    return p


def _eligibility_warnings(period: Period, d: date, slot: int, m: Member) -> list[str]:
    label, allowed = CONTROL_SLOTS[slot]
    out = []
    if m.type != DEVELOPER:
        out.append(f"{m.name}은(는) 개발자가 아닙니다.")
    shift = Commute.objects.filter(period=period, date=d, member=m).values_list("shift", flat=True).first()
    if shift not in allowed:
        out.append(f"{m.name}의 그날 출근조({COMMUTE_SHIFTS.get(shift, '없음')})는 {label} 관제 자격이 아닙니다.")
    return out


def _check_active(m: Member | None) -> None:
    if m is not None and not m.is_active:
        raise DutyError(f"{m.name}은(는) 재직 중이 아닙니다.")


@transaction.atomic
def change_cell(user, d: date, cell: str, before: Member | None, after: Member | None) -> ChangeResult:
    perms.assert_can_edit_date(user, d)
    period = _owner(d)
    if (before is None and after is None) or before == after:
        raise DutyError("변경할 내용이 없습니다.")
    _check_active(after)
    warnings: list[str] = []
    if is_slot_cell(cell):
        slot = slot_index(cell)
        if before is None or after is None:
            raise DutyError("관제 칸은 교체만 할 수 있습니다.")
        row = ControlDuty.objects.filter(period=period, date=d, slot=slot).first()
        if row is None or row.member_id != before.pk:
            raise DutyError(f"{before.name}은(는) 이 칸에 없습니다.")
        if ControlDuty.objects.filter(period=period, date=d, member=after).exists():
            raise DutyError(f"{after.name}은(는) 그날 이미 다른 관제 칸에 있습니다. 맞교환을 사용하세요.")
        row.member = after
        row.save()
        warnings = _eligibility_warnings(period, d, slot, after)
    else:
        if cell not in COMMUTE_SHIFTS:
            raise DutyError("알 수 없는 칸입니다.")
        row = None
        if before is not None:
            row = Commute.objects.filter(period=period, date=d, member=before, shift=cell).first()
            if row is None:
                raise DutyError(f"{before.name}은(는) 이 칸에 없습니다.")
        if after is not None and Commute.objects.filter(period=period, date=d, member=after).exists():
            raise DutyError(f"{after.name}은(는) 그날 이미 다른 출근조에 있습니다. 맞교환을 사용하세요.")
        if row is not None:
            row.delete()
            duty = ControlDuty.objects.filter(period=period, date=d, member=before).first()
            if duty is not None:
                warnings.append(f"{before.name}은(는) {CONTROL_SLOTS[duty.slot][0]} 관제 칸에 남아 있습니다.")
        if after is not None:
            Commute.objects.create(period=period, date=d, member=after, shift=cell)
    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell, before=before, after=after)
    return ChangeResult(warnings)


@transaction.atomic
def swap(user, d: date, cell_a: str, a: Member, cell_b: str, b: Member) -> ChangeResult:
    perms.assert_can_edit_date(user, d)
    period = _owner(d)
    if a == b or cell_a == cell_b:
        raise DutyError("서로 다른 두 칸의 서로 다른 사람을 골라 주세요.")
    if is_slot_cell(cell_a) != is_slot_cell(cell_b):
        raise DutyError("출근조끼리 또는 관제 칸끼리만 맞교환할 수 있습니다.")
    warnings: list[str] = []
    if is_slot_cell(cell_a):
        sa, sb = slot_index(cell_a), slot_index(cell_b)
        ra = ControlDuty.objects.filter(period=period, date=d, slot=sa, member=a).first()
        rb = ControlDuty.objects.filter(period=period, date=d, slot=sb, member=b).first()
        if ra is None or rb is None:
            raise DutyError("선택한 사람이 해당 칸에 없습니다.")
        ra.delete()
        rb.delete()
        ControlDuty.objects.create(period=period, date=d, slot=sa, member=b)
        ControlDuty.objects.create(period=period, date=d, slot=sb, member=a)
        warnings = _eligibility_warnings(period, d, sa, b) + _eligibility_warnings(period, d, sb, a)
    else:
        ra = Commute.objects.filter(period=period, date=d, member=a, shift=cell_a).first()
        rb = Commute.objects.filter(period=period, date=d, member=b, shift=cell_b).first()
        if ra is None or rb is None:
            raise DutyError("선택한 사람이 해당 칸에 없습니다.")
        ra.shift, rb.shift = cell_b, cell_a
        ra.save()
        rb.save()
    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell_a, before=a, after=b)
    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell_b, before=b, after=a)
    return ChangeResult(warnings)
