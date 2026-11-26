"""휴장일 표(Holiday) 채우기와 읽기(설계 5절)."""
from datetime import date

from django.db import transaction
from django.db.models import Max, Min

from .. import market_days, perms
from ..models import ChangeLog, Commute, DutyAssignment, Holiday, Period


def sync(today: date) -> int:
    """(가장 오래된 회차 시작 해, 올해 중 이른 해) ~ (내년, 가장 늦은 회차 종료 해 중 늦은 해)의 자동 휴장일 중 표에 없는 날짜만 auto 로 넣는다.
    있는 행(사람이 추가·끈 행 포함)은 건드리지 않고, 라이브러리에서 사라진 날짜도 지우지 않는다. 몇 번 불러도 결과가 같다. 넣은 수를 돌려준다."""
    span = Period.objects.aggregate(lo=Min("start_date"), hi=Max("end_date"))
    lo = min(today.year, span["lo"].year) if span["lo"] else today.year
    hi = max(today.year + 1, span["hi"].year) if span["hi"] else today.year + 1
    have = set(Holiday.objects.filter(date__year__gte=lo, date__year__lte=hi).values_list("date", flat=True))
    new = [Holiday(date=d, name=name, source=Holiday.Source.AUTO)
           for y in range(lo, hi + 1) for d, name in sorted(market_days.holidays_for(y).items()) if d not in have]
    Holiday.objects.bulk_create(new, ignore_conflicts=True)  # 작업자와 화면 쓰기가 동시에 불러도 겹치는 날짜는 무시
    for h in new:  # 새로 생긴 휴장일(라이브러리에 늦게 들어온 임시공휴일 등): 그날 배포된 근무를 비운다
        clear_day(h.date)
    return len(new)


@transaction.atomic
def clear_day(d: date) -> int:
    """휴장일이 새로 켜진 날(오늘 이후)의 배포된 근무를 근무 없음처럼 비우고 지운 사람 수를 돌려준다.
    지운 것마다 ChangeLog(바꾼 사람 없음 = 자동)를 남겨 변경 알림이 당사자에게 간다. 필요한 사람은 근무 변경으로 다시 넣는다.
    지난 날(기록)·배포 전 회차의 입력(만드는 도구가 건너뛴다)은 그대로. 휴장일을 다시 꺼도 되살리지 않는다."""
    if d < perms.today():
        return 0
    people = set()
    for model, field in ((Commute, "shift"), (DutyAssignment, "cell")):
        rows = model.objects.filter(date=d, period__status=Period.Status.PUBLISHED)
        ChangeLog.objects.bulk_create(
            ChangeLog(by=None, period_id=r.period_id, date=d, cell=getattr(r, field), before_id=r.member_id,
                      reason_before=getattr(r, "reason", "")) for r in rows.order_by("id"))
        people |= set(rows.values_list("member_id", flat=True))
        rows.delete()
    return len(people)


def closed(start: date, end: date) -> dict[date, str]:
    """start~end 의 켜진 휴장일 {날짜: 이름}."""
    return dict(Holiday.objects.filter(active=True, date__gte=start, date__lte=end).values_list("date", "name"))
