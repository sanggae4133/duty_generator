"""근무표 단계 설정(근무표 통합 설계 10.2, 1단계). 앱 코드를 import 하지 않고 값을 그대로 적는다.

- 단계 칸을 더한다: 작성 중·마감 단계 사용(기본 켬), 다섯 단계 화면 이름(기본 = 지금 IT 이름) + 이름 빈 글자 금지 제약.
- 직접 입력(input_mode=direct) 근무표: 작성 중·마감을 끄고 취합 중 = '입력 중', 생성됨 = '확정'(지금 화면 이름 그대로).
  부서별 취합(collect) 근무표는 기본값 그대로. 입력 그룹은 만들지 않는다(그룹 없음 = 관리자만 입력, 지금과 같다).
- 입력 방식 칸(input_mode)과 그 제약을 지운다.
- 거꾸로(0018~0022 처럼 잃을 데이터가 있을 때만 거부): input_mode 를 되살려 근무표마다 채운다. 둘 다 켬 + IT 기본 이름이면
  collect, 둘 다 끔 + 직접 입력 기본 이름이면 direct. 그 밖(하나만 끔, 이름을 고침)은 input_mode 로 나타낼 수 없어
  그 근무표 코드를 알려 주며 멈춘다(되돌리기는 업그레이드 전 백업 복원으로).
"""
from django.db import migrations, models

FIELDS = ("use_draft", "use_close", "step_draft", "step_collecting", "step_closed", "step_generated", "step_published")
MODES = {
    (True, True, "작성 중", "취합 중", "마감", "생성됨", "배포됨"): "collect",
    (False, False, "작성 중", "입력 중", "마감", "확정", "배포됨"): "direct",
}


def forward(apps, schema_editor):
    apps.get_model("duty", "Board").objects.filter(input_mode="direct").update(
        use_draft=False, use_close=False, step_collecting="입력 중", step_generated="확정")


def backward(apps, schema_editor):
    """RemoveField 가 먼저 되돌려져 input_mode 칸(기본 collect)이 있는 상태에서 돈다."""
    Board = apps.get_model("duty", "Board")
    rows = list(Board.objects.order_by("id").values_list("pk", "code", *FIELDS))
    odd = [code for _, code, *steps in rows if tuple(steps) not in MODES]
    if odd:
        raise RuntimeError(f"단계를 고친 근무표가 있어 입력 방식으로 되돌릴 수 없습니다: {', '.join(odd)}. "
                           '업그레이드 전 백업으로 복원하세요(docs/OPERATIONS.md "업그레이드·롤백").')
    for pk, _, *steps in rows:
        Board.objects.filter(pk=pk).update(input_mode=MODES[tuple(steps)])


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
        migrations.RunPython(forward, backward),
        migrations.RemoveConstraint(
            model_name='board',
            name='board_input_mode_valid',
        ),
        migrations.RemoveField(
            model_name='board',
            name='input_mode',
        ),
    ]
