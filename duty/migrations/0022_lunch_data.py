"""IT 근무표에 점심당번을 넣는다(설계 10절 2단계). 앱 코드를 import 하지 않고 값을 그대로 적는다.

- IT 점심당번 정의(시각 없음), IT 부서 점심 11:30–12:30.
- 오늘(마이그레이션이 도는 날, Asia/Seoul)부터 배포됨·생성됨 회차의 새벽 근무자(사유 없음)를 점심당번으로 채운다.
  ChangeLog·알림은 남기지 않는다. 배포됨 회차의 publish_undo 새벽 c 행(오늘 이후)에도 lunch a 행을 더한다
  (배포 취소로 되살아난 날에도 점심당번이 있게).
- 되돌리기는 만들지 않는다: 운영에 점심당번 행·기록·발송 기록이 쌓이므로 되돌리기는 업그레이드 전 백업 복원으로만 한다.
  점심당번 행·기록이 하나도 없는 DB(새 설치·테스트)에서만 IT 정의와 IT 부서 시각을 지우고 내려간다
  (다른 근무표가 점심당번 정의·부서 점심 시각을 쓰면 지우지 않고 멈춘다).
"""
from datetime import time

from django.db import migrations
from django.db.models import Q
from django.utils import timezone

IT_LUNCH = (time(11, 30), time(12, 30))


def fill(apps, schema_editor):
    Board, BoardShift, Department = (apps.get_model("duty", n) for n in ("Board", "BoardShift", "Department"))
    Period, Commute, DutyAssignment = (apps.get_model("duty", n) for n in ("Period", "Commute", "DutyAssignment"))
    board = Board.objects.filter(code="it").first()
    if board is None:  # 0011 이 IT 근무표를 만든다. 지워진 DB 면 할 일이 없다
        return
    BoardShift.objects.get_or_create(board=board, key="lunch", defaults={"name": "점심당번"})
    Department.objects.filter(board=board).update(lunch_start=IT_LUNCH[0], lunch_end=IT_LUNCH[1])
    today = timezone.localdate()
    periods = Period.objects.filter(board=board, status__in=["published", "generated"])
    dawn = Commute.objects.filter(period__in=periods, date__gte=today, shift="dawn", reason="")
    DutyAssignment.objects.bulk_create(
        [DutyAssignment(period_id=c.period_id, date=c.date, member_id=c.member_id, cell="lunch") for c in dawn],
        ignore_conflicts=True)
    for p in periods.filter(status="published").exclude(publish_undo=None):
        add = [["a", r[1], r[2], r[3], "lunch"] for r in p.publish_undo
               if r[0] == "c" and r[4] == "dawn" and (r[5:] or [""])[0] == "" and r[2] >= today.isoformat()]
        if add:
            p.publish_undo = p.publish_undo + add
            p.save(update_fields=["publish_undo"])


def reverse_if_unused(apps, schema_editor):
    """되돌리기 없음. 점심당번이 한 번도 쓰이지 않은(배정·기록·발송 기록·필터 저장값 없음) DB 만 이 마이그레이션이 넣은 것(IT 정의·IT 부서 시각)을 지우고
    내려간다(0021 의 제약이 통과하게). 다른 근무표의 점심당번 정의·부서 시각은 지우지 않고 멈춘다."""
    Board, BoardShift, Department, Period = (apps.get_model("duty", n)
                                             for n in ("Board", "BoardShift", "Department", "Period"))
    it = Board.objects.filter(code="it").values_list("pk", flat=True).first()
    used = any(apps.get_model("duty", n).objects.filter(cell="lunch").exists()
               for n in ("DutyAssignment", "ChangeLog", "AlarmDelivery"))
    used = used or any(r[0] == "a" and r[4] == "lunch"
                       for undo in Period.objects.exclude(publish_undo=None).values_list("publish_undo", flat=True)
                       for r in undo)
    used = used or any("lunch" in (shifts or [])  # 알림 규칙·캘린더·근무표 필터에 저장된 점심당번
                       for n in ("AlarmRule", "CalendarFeed", "RosterPref")
                       for shifts in apps.get_model("duty", n).objects.values_list("shifts", flat=True))
    others = Q() if it is None else ~Q(board_id=it)
    used = used or BoardShift.objects.filter(others, key="lunch").exists()
    used = used or Department.objects.filter(others, lunch_start__isnull=False).exists()
    if used:
        raise RuntimeError("점심당번 배정·기록이나 점심당번을 고른 알림·캘린더·근무표 필터가 있어 되돌릴 수 없습니다. 업그레이드 전 백업으로 복원하세요"
                           '(docs/OPERATIONS.md "업그레이드·롤백").')
    BoardShift.objects.filter(board_id=it, key="lunch").delete()
    Department.objects.filter(board_id=it).update(lunch_start=None, lunch_end=None)


class Migration(migrations.Migration):

    dependencies = [
        ('duty', '0021_lunch'),
    ]

    operations = [
        migrations.RunPython(fill, reverse_if_unused),
    ]
