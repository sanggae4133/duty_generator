"""휴장일 표(Holiday) 채우기와 읽기(설계 5절)."""
from datetime import date

from django.db.models import Max, Min

from .. import market_days
from ..models import Holiday, Period


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
    return len(new)


def closed(start: date, end: date) -> dict[date, str]:
    """start~end 의 켜진 휴장일 {날짜: 이름}."""
    return dict(Holiday.objects.filter(active=True, date__gte=start, date__lte=end).values_list("date", "name"))
