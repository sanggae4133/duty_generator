# 휴장일 표와 회차의 휴장일 건너뛰기(설계 5절·10절 2단계). 표만 만들고 채우지 않는다(라이브러리 버전에 따라 결과가 달라지지 않게,
# 채우기는 services/holidays.sync). 2단계부터 되돌리기는 백업 복원으로만 한다.
# 맨 앞 이름 검사: 2단계 첫 마이그레이션이라 여기서 멈추면 2단계 변경이 하나도 들어가지 않는다(사유 칸은 0020).

from django.db import migrations, models

SUFFIXES = ("(휴가)", "(출장)", "(교육)")


def check_names(apps, schema_editor):
    """표·CSV 의 "이름(휴가)"와 헷갈리는 계정 이름이 있으면 멈춘다(설계 10절 2단계). 앱 코드를 import 하지 않는다."""
    User = apps.get_model("duty", "User")
    taken = sorted(n for n in User.objects.values_list("name", flat=True) if n.endswith(SUFFIXES))
    if taken:
        raise RuntimeError(
            f"이름이 (휴가)·(출장)·(교육)으로 끝나는 계정이 있어 멈춥니다: {', '.join(taken)}. 업그레이드 전 백업으로 롤백한 뒤"
            '(docs/OPERATIONS.md "업그레이드·롤백") 옛 버전 관리 화면에서 그 이름을 바꾸고 업그레이드를 다시 하세요.')


def refuse_reverse(apps, schema_editor):
    """되돌릴 때 휴장일(사람이 고친 값 포함)을 조용히 지우지 않는다. 표가 비어 있으면(새 DB·테스트) 그냥 지나간다."""
    if apps.get_model("duty", "Holiday").objects.exists():
        raise RuntimeError('휴장일이 있어 되돌리지 않습니다. 2단계부터 되돌리기는 업그레이드 전 백업 복원으로만 합니다'
                           '(docs/OPERATIONS.md "업그레이드·롤백").')


class Migration(migrations.Migration):

    dependencies = [
        ('duty', '0017_alarmrule_board_rules'),
    ]

    operations = [
        migrations.RunPython(check_names, migrations.RunPython.noop),
        # 기존 회차는 거짓(사용자 결정 "다음에 만드는 회차부터"), 그다음 모델 기본값을 참으로(이후 만드는 회차)
        migrations.AddField(
            model_name='period',
            name='skip_holidays',
            field=models.BooleanField(default=False, verbose_name='휴장일 건너뛰기'),
        ),
        migrations.AlterField(
            model_name='period',
            name='skip_holidays',
            field=models.BooleanField(default=True, verbose_name='휴장일 건너뛰기'),
        ),
        migrations.CreateModel(
            name='Holiday',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True, verbose_name='날짜')),
                ('name', models.CharField(max_length=64, verbose_name='이름')),
                ('source', models.CharField(choices=[('auto', '자동'), ('manual', '직접 추가')], default='manual', max_length=8, verbose_name='출처')),
                ('active', models.BooleanField(default=True, help_text='끄면 휴장일이 아닙니다(이미 있는 배정은 그대로).', verbose_name='휴장')),
            ],
            options={
                'verbose_name': '휴장일',
                'verbose_name_plural': '휴장일',
                'ordering': ['date'],
                'constraints': [models.CheckConstraint(condition=models.Q(('source__in', ['auto', 'manual'])), name='holiday_source_valid')],
            },
        ),
        migrations.RunPython(migrations.RunPython.noop, refuse_reverse),  # 되돌릴 때 가장 먼저 돈다
    ]
