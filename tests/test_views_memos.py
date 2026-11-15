"""메모 화면: 날 메모·근무 없음(칸 덮기), 주 메모(주간 표 위·월간 그 주 행 아래), 달 메모(표 아래), 관리 그룹만 [메모] 팝업.
이름은 모두 가상."""
from datetime import date

import pytest

from duty.models import ChangeLog, Commute, Memo, Period

D = date(2026, 11, 18)  # 수요일
MON = date(2026, 11, 16)


@pytest.fixture
def world(make_member, fixed_today, it_board):
    fixed_today(MON)
    p = Period.objects.create(board=it_board, name="p", start_date=MON, end_date=date(2026, 11, 20),
                              status=Period.Status.PUBLISHED, overwrite_from=MON)
    m = make_member("가", user=True)
    for x in (D, date(2026, 11, 19)):
        Commute.objects.create(period=p, date=x, member=m, shift="normal")
    return p, m


def memo(it_board, scope, d, text, no_work=False):
    return Memo.objects.create(board=it_board, scope=scope, date=d, text=text, no_work=no_work)


# ── 보이기 ──

@pytest.mark.parametrize("url", [f"/?view=week&date={D}", f"/?view=month&date={D}", f"/day/{D}/"])
def test_day_memo_line_above_assignments(client, world, it_board, url):
    memo(it_board, "day", D, "전산 점검")
    client.force_login(world[1])
    body = client.get(url).content.decode()
    assert '<p class="memo">전산 점검</p>' in body and ">가<" in body


@pytest.mark.parametrize("url", [f"/?view=week&date={D}", f"/?view=month&date={D}"])
def test_no_work_covers_cell(client, world, it_board, url):
    memo(it_board, "day", D, "임시 휴무", no_work=True)
    Commute.objects.filter(date=D).delete()
    ChangeLog.objects.create(by=world[1], period=world[0], date=D, cell="normal", before=world[1])  # 지운 기록
    client.force_login(world[1])
    body = client.get(url).content.decode()
    assert '<p class="nowork">임시 휴무</p>' in body
    assert "<s>가</s>" not in body  # 지운 사람 취소선도 덮는다
    assert f'/cell/{D}/' not in body and f'/cell/2026-11-19/' in body  # 근무 없음 날만 칸 링크가 없다


def test_no_work_without_text_and_without_roster(client, world, it_board):
    memo(it_board, "day", date(2026, 11, 23), "", no_work=True)  # 배포 회차 밖(근무표 없음) 날에도 보인다
    client.force_login(world[1])
    body = client.get("/?view=week&date=2026-11-23").content.decode()
    assert '<p class="nowork">근무 없음</p>' in body and "근무표 없음" in body  # 23일은 덮고, 24~27일은 근무표 없음


def test_day_page_no_work_hides_change_buttons(client, world, it_board):
    memo(it_board, "day", D, "임시 휴무", no_work=True)
    client.force_login(world[1])
    body = client.get(f"/day/{D}/").content.decode()
    assert '<p class="nowork">임시 휴무</p>' in body and 'class="dcell"' not in body and "배포된 근무표에 없는" not in body


def test_week_memo_above_table_in_week_view(client, world, it_board):
    memo(it_board, "week", MON, "토요일 근무: 가")
    client.force_login(world[1])
    body = client.get(f"/?view=week&date={D}").content.decode()
    assert "토요일 근무: 가" in body and body.index("토요일 근무: 가") < body.index('id="roster"')


def test_week_memo_row_under_its_week_in_month_view(client, world, it_board):
    memo(it_board, "week", MON, "셋째 주 메모")
    client.force_login(world[1])
    body = client.get(f"/?view=month&date={D}").content.decode()
    i = body.index("셋째 주 메모")
    assert body.rindex(">20<", 0, i) > body.rindex(">16<", 0, i)  # 그 주(16~20일) 행 뒤
    assert body.index(">23<") > i and 'class="wmemo"' in body  # 다음 주 행 앞
    assert body.count('class="wmemo"') == 1  # 메모 없는 주는 줄을 만들지 않는다(관리자가 아니면)


def test_month_memo_below_table(client, world, it_board):
    memo(it_board, "month", date(2026, 11, 1), "본부 점심: 가")
    client.force_login(world[1])
    for url in (f"/?view=month&date={D}", f"/?view=week&date={D}"):
        body = client.get(url).content.decode()
        assert body.index("본부 점심: 가") > body.index("</table>")
    assert "본부 점심: 가" not in client.get("/?view=month&date=2026-12-02").content.decode()  # 12월 달력엔 11월 메모 없음


def test_memo_text_is_escaped(client, world, it_board):
    memo(it_board, "day", D, "<b>x</b>")
    client.force_login(world[1])
    assert "&lt;b&gt;x&lt;/b&gt;" in client.get(f"/day/{D}/").content.decode()


# ── 관리 그룹만 [메모] ──

def test_memo_links_only_for_admin(client, world, admin_user):
    client.force_login(world[1])
    for url in (f"/?view=week&date={D}", f"/?view=month&date={D}", f"/day/{D}/"):
        assert "/memo/" not in client.get(url).content.decode()
    client.force_login(admin_user)
    week = client.get(f"/?view=week&date={D}").content.decode()
    assert f'hx-get="/memo/day/{D}/?next=' in week and f'/memo/week/{MON}/' in week and "/memo/month/2026-11-01/" in week
    month = client.get(f"/?view=month&date={D}").content.decode()
    assert month.count('class="wmemo"') == 5  # 11월 달력 5주 모두 [메모] 줄
    assert f"/memo/day/{D}/" in client.get(f"/day/{D}/").content.decode()


def test_popup_requires_admin(client, world):
    client.force_login(world[1])
    assert client.get(f"/memo/day/{D}/").status_code == 404
    assert client.post(f"/memo/day/{D}/", {"text": "x"}).status_code == 404
    assert not Memo.objects.exists()


def test_popup_form(admin_client_ok, world, it_board):
    memo(it_board, "week", MON, "기존 메모")
    body = admin_client_ok.get(f"/memo/week/{D}/").content.decode()  # 수요일로 열어도 그 주 월요일 메모
    assert "11/16 주 메모" in body and "기존 메모" in body and 'name="no_work"' not in body and "메모 지우기" in body
    body = admin_client_ok.get(f"/memo/day/{D}/").content.decode()
    assert 'name="no_work"' in body and 'data-affected="1"' in body and "메모 지우기" not in body
    assert admin_client_ok.get(f"/memo/year/{D}/").status_code == 404


def test_post_saves_and_redirects(admin_client_ok, world):
    r = admin_client_ok.post(f"/memo/month/{D}/", {"text": "본부 점심", "next": f"/?view=month&date={D}"})
    assert r.status_code == 302 and r.url == f"/?view=month&date={D}"
    assert Memo.objects.get().date == date(2026, 11, 1)


def test_post_no_work_needs_confirm(admin_client_ok, world):
    r = admin_client_ok.post(f"/memo/day/{D}/", {"text": "휴무", "no_work": "1"}, follow=True)
    assert "1명의 근무가 지워집니다" in r.content.decode() and not Memo.objects.exists()
    r = admin_client_ok.post(f"/memo/day/{D}/", {"text": "휴무", "no_work": "1", "confirm": "1"}, follow=True)
    assert "1명의 근무를 지웠습니다" in r.content.decode()
    assert Memo.objects.get().no_work and not Commute.objects.filter(date=D).exists()


def test_post_delete(admin_client_ok, world, it_board):
    memo(it_board, "day", D, "행사")
    admin_client_ok.post(f"/memo/day/{D}/", {"text": "행사", "delete": "1"})
    assert not Memo.objects.exists()
