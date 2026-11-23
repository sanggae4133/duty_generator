"""엑셀 다운로드(근무표·내 근무)와 [내 근무] 기간. 이름은 모두 가상.
two 픽스처: IT(가상다 새벽)·운영팀(가상나 오전)이 D(월)에 배포, 로그인은 IT 의 가상가, 오늘 = D 앞 금요일."""
from datetime import date, time, timedelta
from io import BytesIO
from urllib.parse import quote

import pytest
from django.contrib.messages import get_messages
from openpyxl import load_workbook

from duty import xlsx
from duty.models import Commute, DutyAssignment, Period
from tests.test_alarm_boards import D, ops  # noqa: F401 (ops 는 픽스처)
from tests.test_board_pick import member, published, two  # noqa: F401 (two 는 픽스처)

HEAD = ["날짜", "요일", "근무표", "칸", "시간", "이름", "부서", "사유"]
WEEK = f"start={D}&end={D + timedelta(days=4)}"


def rows(resp):
    assert resp.status_code == 200, resp.status_code
    ws = load_workbook(BytesIO(resp.content)).active
    out = [[c.value for c in r] for r in ws.iter_rows()]
    assert out[0] == HEAD
    return [[v.date() if hasattr(v, "date") else v for v in r] for r in out[1:]]


def test_build_is_pure_and_formatted():
    data = xlsx.build([(D, "월", "IT 당번표", "새벽", "06:30~15:30", "가상다", "매칭엔진실", "")])
    ws = load_workbook(BytesIO(data)).active
    assert [c.value for c in ws[1]] == HEAD and all(c.font.bold for c in ws[1])
    assert ws.freeze_panes == "A2" and ws.auto_filter.ref == "A1:H2"
    assert ws["A2"].value.date() == D and ws["A2"].number_format == "yyyy-mm-dd"
    assert ws.column_dimensions["A"].width >= 11
    assert xlsx.build([])  # 빈 표도 머리줄만 있는 파일


def test_build_never_writes_formulas():
    """관리자가 넣은 이름이 '=' 로 시작해도 받는 사람의 엑셀에서 수식으로 돌지 않게(수식 주입) 글자로만 쓴다."""
    data = xlsx.build([(D, "월", "=HYPERLINK(\"http://x\",\"a\")", "=1+1", "", "=가상", "", "")])
    ws = load_workbook(BytesIO(data)).active
    assert [ws.cell(2, c).data_type for c in (3, 4, 6)] == ["s", "s", "s"]
    assert ws["D2"].value == "=1+1"


def test_login_required(client, db):
    for url in ("/export.xlsx", "/me/export.xlsx"):
        r = client.get(url)
        assert r.status_code == 302 and r.url.startswith("/login/")


def test_roster_export_both_boards(client, two):
    _, ga, _ = two
    client.force_login(ga)
    r = client.get(f"/export.xlsx?{WEEK}&board=ops&board=it")
    assert r["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert r["Cache-Control"] == "no-store"
    name = f"당번표_{D}_{D + timedelta(days=4)}.xlsx"
    assert f"filename*=UTF-8''{quote(name)}" in r["Content-Disposition"]
    assert rows(r) == [  # 날짜마다 내 근무표 먼저(화면 순서)
        [D, "월", "IT 당번표", "새벽", "06:30~15:30", "가상다", "매칭엔진실", None],
        [D, "월", "운영팀", "오전", "07:30~16:30", "가상나", "운영팀", None],
    ]


def test_roster_export_default_is_home_only(client, two):
    _, ga, _ = two
    client.force_login(ga)
    assert [r[5] for r in rows(client.get(f"/export.xlsx?{WEEK}"))] == ["가상다"]
    assert client.get(f"/export.xlsx?{WEEK}&board=nope").status_code == 404


def test_roster_export_filters_only_my_board(client, two):
    _, ga, _ = two
    client.force_login(ga)
    both = f"/export.xlsx?{WEEK}&board=it&board=ops"
    assert [r[5] for r in rows(client.get(both + "&dept=TMCH"))] == ["가상나"]  # 부서 필터는 IT 구역만
    assert [r[5] for r in rows(client.get(both + "&shift=normal"))] == ["가상나"]  # 스케줄도
    assert [r[5] for r in rows(client.get(both + "&dept=OPS"))] == ["가상다", "가상나"]  # 남의 부서 값은 버린다
    # 내 근무표가 없으면 필터를 쓰지 않는다(화면과 같다)
    assert [r[5] for r in rows(client.get(f"/export.xlsx?{WEEK}&board=ops&shift=normal"))] == ["가상나"]


def test_roster_export_only_published_and_reason_lunch_slot(client, two, it_board, depts, lunch):
    board, ga, na = two
    client.force_login(ga)
    nxt = D + timedelta(days=1)
    p = Period.objects.create(board=board, name="미배포", start_date=nxt, end_date=nxt, status="collecting")
    Commute.objects.create(period=p, date=nxt, member=na, shift="dawn")  # 배포 전: 화면에도 없다
    ip = Period.objects.get(board=it_board)
    da = Commute.objects.get(period=ip).member
    Commute.objects.filter(period=ip).update(reason="휴가")
    dept = depts["MEMS"]
    dept.lunch_start, dept.lunch_end = time(11, 30), time(12, 30)
    dept.save()
    DutyAssignment.objects.create(period=ip, date=D, cell="slot0", member=da)
    DutyAssignment.objects.create(period=ip, date=D, cell="lunch", member=da)
    got = rows(client.get(f"/export.xlsx?{WEEK}&board=it&board=ops"))
    assert [r[2:] for r in got] == [
        ["IT 당번표", "새벽", "06:30~15:30", "가상다", "매칭엔진실", "휴가"],
        ["IT 당번표", "점심당번", "11:30~12:30", "가상다", "매칭엔진실", "휴가"],
        ["IT 당번표", "장중관제", "08:30~09:30", "가상다", "매칭엔진실", "휴가"],
        ["운영팀", "오전", "07:30~16:30", "가상나", "운영팀", None],
    ]


@pytest.mark.parametrize("q, msg", [
    ("start=2026-01-01&end=2027-01-02", "기간은 1년까지"),
    (f"start={D}&end={D - timedelta(days=1)}", "시작일이 종료일보다 늦습니다"),
    ("start=&end=", "시작일과 종료일을 넣어 주세요"),
    ("start=x&end=2026-01-01", "시작일과 종료일을 넣어 주세요"),
])
def test_roster_export_bad_range(client, two, q, msg):
    _, ga, _ = two
    client.force_login(ga)
    r = client.get(f"/export.xlsx?{q}&next=/%3Fview%3Dmonth")
    assert r.status_code == 302 and r.url == "/?view=month"
    assert msg in [str(m) for m in get_messages(r.wsgi_request)][0]
    assert client.get("/export.xlsx?start=2026-01-01&end=2026-12-31").status_code == 200  # 1년(365일)은 된다


def test_roster_screen_has_export_box_prefilled(client, two):
    _, ga, _ = two
    client.force_login(ga)
    body = client.get(f"/?view=week&date={D}&board=it&board=ops&dept=MEMS").content.decode()
    box = body.split('<details class="export"')[1].split("</details>")[0]
    assert 'action="/export.xlsx"' in box
    assert f'name="start" value="{D}"' in box and f'name="end" value="{D + timedelta(days=4)}"' in box
    assert 'name="board" value="it" checked' in box and 'name="board" value="ops" checked' in box
    assert 'name="dept" value="MEMS" checked' in box and 'name="dept" value="TMCH"' in box
    assert 'name="dept" value="TMCH" checked' not in box
    month = client.get(f"/?view=month&date={D}").content.decode().split('<details class="export"')[1]
    assert 'name="start" value="2026-11-01"' in month and 'name="end" value="2026-11-30"' in month


# ── 내 근무 기간·다운로드 ──

@pytest.fixture
def mine(two, it_board):
    """가상가에게 지난 날(D-7)·D·D+7 근무. 오늘 = D-3."""
    _, ga, _ = two
    p = Period.objects.get(board=it_board)
    p.start_date = p.overwrite_from = D - timedelta(days=7)
    p.end_date = D + timedelta(days=7)
    p.save()
    for x, shift in ((D - timedelta(days=7), "normal"), (D, "dawn"), (D + timedelta(days=7), "dinner")):
        Commute.objects.create(period=p, date=x, member=ga, shift=shift)
    return ga


def test_me_default_unchanged_and_range(client, mine):
    client.force_login(mine)
    body = client.get("/me/").content.decode()
    assert "11/9 (월)" not in body and "11/16 (월)" in body and "11/23 (월)" in body  # 기본 = 오늘부터 끝까지
    assert 'name="start" value="2026-11-13"' in body and 'name="end" value=""' in body
    body = client.get("/me/?start=2026-11-09&end=2026-11-16").content.decode()
    assert "11/9 (월)" in body and "11/16 (월)" in body and "11/23 (월)" not in body  # 지난 날도 본다
    body = client.get("/me/?start=2026-11-20&end=2026-11-10").content.decode()
    assert "시작일이 종료일보다 늦습니다" in body
    assert 'formaction="/me/export.xlsx"' in body  # 지금 칸 값 그대로 내려받는다


def test_me_export(client, mine):
    client.force_login(mine)
    r = client.get("/me/export.xlsx?start=2026-11-09&end=2026-11-16&shift=normal&shift=dawn")
    assert f"filename*=UTF-8''{quote('내근무_2026-11-09_2026-11-16.xlsx')}" in r["Content-Disposition"]
    assert r["Cache-Control"] == "no-store"
    assert rows(r) == [
        [date(2026, 11, 9), "월", "IT 당번표", "정상", "08:00~17:00", "가상가", "매칭엔진실", None],
        [D, "월", "IT 당번표", "새벽", "06:30~15:30", "가상가", "매칭엔진실", None],
    ]  # 남의 근무(가상다)는 없다
    r = client.get("/me/export.xlsx")  # 기본 = 오늘부터 끝까지, 파일 이름 끝 = 마지막 근무 날
    assert [x[0] for x in rows(r)] == [D, D + timedelta(days=7)]
    assert quote("내근무_2026-11-13_2026-11-23.xlsx") in r["Content-Disposition"]
    r = client.get("/me/export.xlsx?start=2026-11-20&end=2026-11-10")
    assert r.status_code == 302 and r.url.startswith("/me/?")


def test_footer_credit(client, two, settings):
    _, ga, _ = two
    client.force_login(ga)
    settings.REPO_URL = "https://github.com/example/duty"
    body = client.get("/me/").content.decode()
    assert 'Developed by SJ · <a href="https://github.com/example/duty" target="_blank" rel="noopener">GitHub</a>' in body
    settings.REPO_URL = ""
    assert "Developed by SJ" not in client.get("/me/").content.decode()
