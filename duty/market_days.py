"""휴장일 자동 계산(순수 모듈, ORM 없음). 결과는 services/holidays.sync 가 Holiday 표에 넣는다."""
from datetime import date

import holidays

YEAR_END = "연말 휴장"


def holidays_for(year: int) -> dict[date, str]:
    """그해 한국 공휴일(라이브러리 holidays, 대체공휴일·선거일·임시공휴일 포함) + 12/31 '연말 휴장'. 주말도 들어 있다."""
    out = dict(holidays.country_holidays("KR", years=year, language="ko"))
    out.setdefault(date(year, 12, 31), YEAR_END)
    return out
