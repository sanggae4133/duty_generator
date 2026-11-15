"""관제 배정 ControlDuty(slot 숫자) → DutyAssignment(cell "slot{n}"), 배포 취소 보관 행 k → a. 되돌리기 포함.

앱 코드(shifts.py 등)를 import 하지 않는다: 앱 상수가 나중에 바뀌어도 이 마이그레이션의 결과는 같아야 한다.
"""
from django.db import migrations


def _undo(apps, convert):
    Period = apps.get_model("duty", "Period")
    for p in Period.objects.exclude(publish_undo=None):
        new = [convert(r) for r in p.publish_undo]
        if new != p.publish_undo:
            p.publish_undo = new
            p.save(update_fields=["publish_undo"])


def forward(apps, schema_editor):
    ControlDuty = apps.get_model("duty", "ControlDuty")
    DutyAssignment = apps.get_model("duty", "DutyAssignment")
    DutyAssignment.objects.bulk_create(
        DutyAssignment(period_id=r.period_id, date=r.date, cell=f"slot{r.slot}", member_id=r.member_id)
        for r in ControlDuty.objects.all()
    )
    ControlDuty.objects.all().delete()  # 되돌리기가 같은 행을 다시 만들 때 겹치지 않게(표는 0014 가 지운다)
    _undo(apps, lambda r: ["a", r[1], r[2], r[3], f"slot{r[4]}"] if r[0] == "k" else r)


def backward(apps, schema_editor):
    ControlDuty = apps.get_model("duty", "ControlDuty")
    DutyAssignment = apps.get_model("duty", "DutyAssignment")
    rows = DutyAssignment.objects.filter(cell__startswith="slot")
    ControlDuty.objects.bulk_create(
        ControlDuty(period_id=r.period_id, date=r.date, slot=int(r.cell[4:]), member_id=r.member_id) for r in rows
    )
    rows.delete()
    _undo(apps, lambda r: ["k", r[1], r[2], r[3], int(r[4][4:])] if r[0] == "a" and r[4].startswith("slot") else r)


class Migration(migrations.Migration):

    dependencies = [
        ("duty", "0012_dutyassignment"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
