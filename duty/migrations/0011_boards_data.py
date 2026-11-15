"""1단계 데이터 이전: 기존 데이터를 IT 근무표 하나로 묶고, 권한을 그룹으로 옮긴다.

앱 코드(shifts.py 등)를 import 하지 않는다: 앱 상수가 나중에 바뀌어도 이 마이그레이션의 결과는 같아야 한다.
"""
from datetime import time

from django.db import migrations

IT_CODE = "it"
IT_NAME = "IT 당번표"
IT_ADMIN_GROUP = "IT 근무표 관리"
DEPT_ORDER = ["MEMS", "TMCH", "MD", "UI"]  # 지금 근무표 부서 필터 순서(views/roster.py DEPT_ORDER). 없는 부서는 뒤로
_BOTH = ["normal", "dinner"]
_DEV = ["개발자"]
IT_SHIFTS = [  # 1단계 시점 shifts.py 상수 그대로(키, 이름, 시작, 끝, 자격 근무조, 자격 구분, 기본 알림)
    ("dawn", "새벽", time(6, 30), time(15, 30), [], [], True),
    ("normal", "정상", time(8, 0), time(17, 0), [], [], False),
    ("dinner", "석식교대", time(9, 0), time(18, 0), [], [], True),
    ("slot0", "08:30~09:30", time(8, 30), time(9, 30), ["normal"], _DEV, False),
    ("slot1", "09:30~10:30", time(9, 30), time(10, 30), _BOTH, _DEV, False),
    ("slot2", "10:30~11:30", time(10, 30), time(11, 30), _BOTH, _DEV, False),
    ("slot3", "11:30~12:30", time(11, 30), time(12, 30), _BOTH, _DEV, False),
    ("slot4", "12:30~13:30", time(12, 30), time(13, 30), _BOTH, _DEV, False),
    ("slot5", "13:30~14:30", time(13, 30), time(14, 30), _BOTH, _DEV, False),
    ("slot6", "14:30~15:30", time(14, 30), time(15, 30), _BOTH, _DEV, False),
    ("slot7", "15:30~16:30", time(15, 30), time(16, 30), _BOTH, _DEV, False),
    ("slot8", "16:30~17:00", time(16, 30), time(17, 0), _BOTH, _DEV, False),
    ("slot9", "17:00~18:00", time(17, 0), time(18, 0), ["dinner"], _DEV, False),
    ("night", "야간", time(13, 30), time(21, 30), [], [], True),
]


def _input_group_name(dept) -> str:
    return f"{dept.name} 출근표 입력"


def forward(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Board = apps.get_model("duty", "Board")
    BoardShift = apps.get_model("duty", "BoardShift")
    GroupKeeper = apps.get_model("duty", "GroupKeeper")
    Department = apps.get_model("duty", "Department")
    Period = apps.get_model("duty", "Period")
    User = apps.get_model("duty", "User")
    AlarmRule = apps.get_model("duty", "AlarmRule")

    depts = list(Department.objects.all())
    # 같은 이름의 그룹이 이미 있으면 뜻이 섞이므로 멈춘다(운영자가 그 그룹 이름을 바꾼 뒤 다시 올린다)
    taken = sorted(Group.objects.filter(name__in=[IT_ADMIN_GROUP, *map(_input_group_name, depts)])
                   .values_list("name", flat=True))
    if taken:
        raise RuntimeError(f"이미 있는 그룹 이름이라 멈춥니다: {', '.join(taken)}. 업그레이드 전 백업으로 롤백한 뒤(docs/OPERATIONS.md \"업그레이드·롤백\") 옛 버전 관리 화면에서 그 그룹 이름을 바꾸고 업그레이드를 다시 하세요.")

    admin_group = Group.objects.create(name=IT_ADMIN_GROUP)
    board = Board.objects.create(code=IT_CODE, name=IT_NAME, input_mode="collect", admin_group=admin_group)
    BoardShift.objects.bulk_create([
        BoardShift(board=board, key=k, name=n, start=s, end=e, eligible_shifts=es, eligible_types=et, default_alarm=da)
        for k, n, s, e, es, et, da in IT_SHIFTS])
    admin_group.user_set.set(User.objects.filter(is_staff=True))  # is_staff 값 자체는 그대로 둔다

    groups = [admin_group]
    for dept in depts:
        group = Group.objects.create(name=_input_group_name(dept))
        group.user_set.set(dept.managers.all())
        dept.board, dept.input_group = board, group
        dept.order = DEPT_ORDER.index(dept.code) if dept.code in DEPT_ORDER else 99
        dept.save(update_fields=["board", "input_group", "order"])
        groups.append(group)

    GroupKeeper.objects.bulk_create([GroupKeeper(group=g, user=u)
                                     for u in User.objects.filter(is_superuser=True) for g in groups])
    Period.objects.update(board=board)
    for p in Period.objects.filter(status="published", overwrite_from__isnull=True):
        p.overwrite_from = p.start_date
        p.save(update_fields=["overwrite_from"])
    AlarmRule.objects.filter(kind="report").update(board=board)  # depts 는 다시 정규화하지 않는다


def backward(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Board = apps.get_model("duty", "Board")
    BoardShift = apps.get_model("duty", "BoardShift")
    GroupKeeper = apps.get_model("duty", "GroupKeeper")
    Department = apps.get_model("duty", "Department")
    Period = apps.get_model("duty", "Period")
    AlarmRule = apps.get_model("duty", "AlarmRule")
    RosterPref = apps.get_model("duty", "RosterPref")

    created = list(Board.objects.values_list("admin_group_id", flat=True))
    for dept in Department.objects.exclude(input_group=None).select_related("input_group"):
        dept.managers.set(dept.input_group.user_set.all())
        created.append(dept.input_group_id)
    # 채운 overwrite_from 은 되돌리지 않는다(배포 회차의 start_date 와 같아 뜻이 같다)
    Department.objects.update(board=None, input_group=None, order=99)
    Period.objects.update(board=None)
    AlarmRule.objects.update(board=None)
    RosterPref.objects.update(board=None)
    GroupKeeper.objects.all().delete()
    BoardShift.objects.all().delete()
    # Board 는 역참조가 많아 delete() 의 연쇄 검사가 되돌리는 중의 옛 모델 상태와 어긋난다(참조는 위에서 다 비웠다)
    Board.objects.all()._raw_delete(schema_editor.connection.alias)
    Group.objects.filter(id__in=created).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("duty", "0010_boards"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
