"""회차·부서의 근무표를 NOT NULL 로(설계 10절 1단계 3번). 0011 과 이 마이그레이션 사이에 근무표 없이 생긴 회차는 IT 로 채운다.
근무표 없는 부서는 0015 가 입력 그룹·담당자와 함께 옮겼어야 하므로, 남아 있으면 멈춘다."""
import django.db.models.deletion
from django.db import migrations, models


def fill_it(apps, schema_editor):
    Board = apps.get_model("duty", "Board")
    Department = apps.get_model("duty", "Department")
    Period = apps.get_model("duty", "Period")
    if left := sorted(Department.objects.filter(board=None).values_list("code", flat=True)):
        raise RuntimeError(f"근무표 없는 부서가 남아 있어 멈춥니다: {', '.join(left)}. "
                           "0015 가 옮겼어야 합니다(입력 그룹·담당자 복사). 업그레이드 전 백업으로 롤백한 뒤 업그레이드를 다시 하세요.")
    if not Period.objects.filter(board=None).exists():
        return
    it = Board.objects.get(code="it")  # 0011 이 만든 IT 근무표
    Period.objects.filter(board=None).update(board=it)


class Migration(migrations.Migration):

    dependencies = [
        ("duty", "0015_remove_department_managers"),
    ]

    operations = [
        migrations.RunPython(fill_it, migrations.RunPython.noop),  # 되돌릴 때 채운 값은 그대로 둔다
        migrations.AlterField(
            model_name="department",
            name="board",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="departments",
                                    to="duty.board", verbose_name="근무표"),
        ),
        migrations.AlterField(
            model_name="period",
            name="board",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="periods",
                                    to="duty.board", verbose_name="근무표"),
        ),
    ]
