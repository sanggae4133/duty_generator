"""근무표 단계 설정(근무표 통합 설계 10.2, 1단계). 앱 코드를 import 하지 않고 값을 그대로 적는다.

- 단계 칸을 더한다: 작성 중·마감 단계 사용(기본 켬), 다섯 단계 화면 이름(기본 = 지금 IT 이름) + 이름 빈 글자 금지 제약.
- 직접 입력(input_mode=direct) 근무표: 작성 중·마감을 끄고 취합 중 = '입력 중', 생성됨 = '확정'(지금 화면 이름 그대로).
  부서별 취합(collect) 근무표는 기본값 그대로. 입력 그룹은 만들지 않는다(그룹 없음 = 관리자만 입력, 지금과 같다).
"""
from django.db import migrations, models


def forward(apps, schema_editor):
    apps.get_model("duty", "Board").objects.filter(input_mode="direct").update(
        use_draft=False, use_close=False, step_collecting="입력 중", step_generated="확정")


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('duty', '0022_lunch_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='board',
            name='use_draft',
            field=models.BooleanField(default=True, verbose_name='작성 중 단계 사용'),
        ),
        migrations.AddField(
            model_name='board',
            name='use_close',
            field=models.BooleanField(default=True, verbose_name='마감 단계 사용'),
        ),
        migrations.AddField(
            model_name='board',
            name='step_draft',
            field=models.CharField(default='작성 중', max_length=16, verbose_name='작성 중 이름'),
        ),
        migrations.AddField(
            model_name='board',
            name='step_collecting',
            field=models.CharField(default='취합 중', max_length=16, verbose_name='취합 중 이름'),
        ),
        migrations.AddField(
            model_name='board',
            name='step_closed',
            field=models.CharField(default='마감', max_length=16, verbose_name='마감 이름'),
        ),
        migrations.AddField(
            model_name='board',
            name='step_generated',
            field=models.CharField(default='생성됨', max_length=16, verbose_name='생성됨 이름'),
        ),
        migrations.AddField(
            model_name='board',
            name='step_published',
            field=models.CharField(default='배포됨', max_length=16, verbose_name='배포됨 이름'),
        ),
        migrations.AddConstraint(
            model_name='board',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('step_draft', ''), _negated=True), models.Q(('step_collecting', ''), _negated=True), models.Q(('step_closed', ''), _negated=True), models.Q(('step_generated', ''), _negated=True), models.Q(('step_published', ''), _negated=True)), name='board_step_names_set'),
        ),
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
