"""기억한 근무표 RosterPref.board(FK 하나) → boards(code 목록)(근무표 통합 설계 5.5·10.2, 5단계).

- 앞으로: board 가 있는 행만 boards = [그 code]. NULL(= 내 근무표)은 기본값 [] 그대로.
- 거꾸로: 0018~0022 처럼 잃을 데이터가 있을 때만 거부한다. 근무표를 둘 이상 기억한 행이 있으면 board 하나로 나타낼 수 없어
  멈춘다(되돌리기는 업그레이드 전 백업 복원). 하나짜리는 board 로 옮긴다.
"""
from django.db import migrations, models


def forward(apps, schema_editor):
    RosterPref = apps.get_model("duty", "RosterPref")
    for p in RosterPref.objects.exclude(board=None).select_related("board"):
        p.boards = [p.board.code]
        p.save(update_fields=["boards"])


def backward(apps, schema_editor):
    RosterPref, Board = apps.get_model("duty", "RosterPref"), apps.get_model("duty", "Board")
    prefs = list(RosterPref.objects.all())
    many = sum(len(p.boards) > 1 for p in prefs)
    if many:
        raise RuntimeError(f"근무표를 둘 이상 기억한 사용자가 {many}명 있어 되돌릴 수 없습니다. 업그레이드 전 백업으로 복원하세요"
                           '(docs/OPERATIONS.md "업그레이드·롤백").')
    by_code = dict(Board.objects.values_list("code", "pk"))
    for p in prefs:
        if p.boards:
            p.board_id = by_code.get(p.boards[0])
            p.save(update_fields=["board"])


class Migration(migrations.Migration):

    dependencies = [
        ('duty', '0024_delete_groupkeeper'),
    ]

    operations = [
        migrations.AddField(
            model_name='rosterpref',
            name='boards',
            field=models.JSONField(default=list),
        ),
        migrations.RunPython(forward, backward),
        migrations.RemoveField(
            model_name='rosterpref',
            name='board',
        ),
    ]
