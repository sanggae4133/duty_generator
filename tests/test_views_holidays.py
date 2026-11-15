"""휴장일 이름 표시: 날짜 칸 맨 위(주간·월간), 하루 화면(설계 5절·7절). 이름은 모두 가상."""
from datetime import date

import pytest

from duty.models import Commute, Holiday, Period

D = date(2026, 11, 18)  # 수요일


@pytest.fixture
def viewer(client, make_member, fixed_today, it_board):
    fixed_today(D)
    p = Period.objects.create(board=it_board, name="p", start_date=D, end_date=D, status=Period.Status.PUBLISHED,
                              skip_holidays=False)  # 옛 회차: 휴장일 배정도 그대로 보이고 이름만 붙는다
    m = make_member("가", user=True)
    Commute.objects.create(period=p, date=D, member=m, shift="normal")
    Holiday.objects.create(date=D, name="임시 휴장")
    client.force_login(m)
    return client


@pytest.mark.parametrize("url", [f"/?view=week&date={D}", f"/?view=month&date={D}", f"/day/{D}/"])
def test_holiday_name_shown_with_assignments(viewer, url):
    body = viewer.get(url).content.decode()
    assert '<p class="hol">임시 휴장</p>' in body
    assert ">가<" in body  # 배정은 숨기지 않는다


def test_holiday_name_shown_on_day_without_roster(viewer):
    Holiday.objects.create(date=date(2026, 11, 19), name="대체 휴장")
    body = viewer.get(f"/?view=week&date={D}").content.decode()
    assert '<p class="hol">대체 휴장</p>' in body and "근무표 없음" in body


def test_turned_off_holiday_not_shown(viewer):
    Holiday.objects.filter(date=D).update(active=False)
    for url in (f"/?view=week&date={D}", f"/day/{D}/"):
        assert 'class="hol"' not in viewer.get(url).content.decode()


def test_month_view_hides_holiday_of_other_month(viewer):
    Holiday.objects.create(date=date(2026, 11, 30), name="지난달 휴장")  # 12월 달력 첫 줄에 걸린 11월 월요일
    assert "지난달 휴장" not in viewer.get("/?view=month&date=2026-12-02").content.decode()
    assert "지난달 휴장" in viewer.get(f"/?view=month&date={D}").content.decode()


def test_screens_do_not_sync_on_get(viewer):
    viewer.get(f"/?view=month&date={D}")
    viewer.get(f"/day/{D}/")
    assert Holiday.objects.count() == 1  # 화면을 여는 것으로는 휴장일을 채우지 않는다
