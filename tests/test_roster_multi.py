"""여러 근무표 한 화면(근무표 통합 설계 9절, 5단계): 기억 목록·겹친 주간·월간·하루 화면·팝업·근무표 고르기.
이름은 모두 가상. two 픽스처: IT(가상다 새벽)·운영팀(가상나 새벽)이 D 에 배포, 로그인은 IT 의 가상가, 오늘 = D 앞 금요일."""
import re
from datetime import timedelta
from urllib.parse import quote

import pytest
from django.contrib.messages import get_messages
from django.utils.encoding import iri_to_uri
from django.utils.html import escape

from duty.models import Holiday, Memo, RosterPref, User
from duty.services import boards, prefs
from tests.test_alarm_boards import D, ops  # noqa: F401 (ops 는 픽스처)
from tests.test_board_pick import WEEK, member, two  # noqa: F401 (two 는 픽스처)

BOTH = WEEK + "&board=it&board=ops"


def test_in_order_and_selection_query(two, it_board):
    board, _, _ = two
    assert boards.in_order([board, it_board], it_board) == [it_board, board]  # 내 근무표 먼저
    assert boards.in_order([it_board, board], board) == [board, it_board]  # 운영팀 사람에게는 운영팀이 먼저
    assert boards.selection_query([it_board], it_board) == ""
    assert boards.selection_query([board], it_board) == "?board=ops"  # 하나면 지금 주소 그대로
    assert boards.selection_query([it_board, board], it_board) == "?board=it&board=ops"


def test_remember_boards_list_and_clear(two, it_board):
    board, ga, _ = two
    prefs.remember_boards(ga, [it_board], it_board)
    assert not RosterPref.objects.filter(user=ga).exists()  # 내 근무표만이면 행을 만들지 않는다
    prefs.remember_boards(ga, [it_board, board], it_board)
    assert RosterPref.objects.get(user=ga).boards == ["it", "ops"]
    prefs.remember_boards(ga, [board], it_board)
    assert RosterPref.objects.get(user=ga).boards == ["ops"]
    prefs.remember_boards(ga, [it_board], it_board)
    assert RosterPref.objects.get(user=ga).boards == []


# ── 겹친 근무표 화면(설계 9.2·9.3) ──

def _names(body):
    """구역 이름표 글(순서대로)."""
    return [x.strip() for x in re.findall(r'<p class="bname">([^<]+)', body)]


def test_list_memory_shows_both(client, two):
    _, ga, _ = two
    client.force_login(ga)
    client.post("/prefs/", {"pick": "1", "board": ["ops", "it", "ops"]})  # 순서·중복과 상관없이
    assert RosterPref.objects.get(user=ga).boards == ["it", "ops"]  # 내 근무표 먼저 저장
    body = client.get(WEEK).content.decode()  # ?board= 가 없으면 기억한 목록
    assert "가상다" in body and "가상나" in body
    assert client.get(WEEK + "&board=it&board=nope").status_code == 404
    RosterPref.objects.filter(user=ga).update(boards=["ops", "gone"])  # 기억의 없는 code 는 버린다
    body = client.get(WEEK).content.decode()
    assert "가상나" in body and "가상다" not in body


def test_sections_in_order_with_labels(client, two):
    _, ga, _ = two
    client.force_login(ga)
    body = client.get(WEEK + "&board=ops&board=it").content.decode()
    assert _names(body) == ["IT 당번표", "운영팀"] * 7  # 날짜마다 내 근무표 먼저(주간 5일 + 주말 메모 칸 2일)
    assert body.count("<small>보기만</small>") == 7  # 바꿀 수 없는 운영팀 구역만
    assert '<span class="bnames">IT 당번표 + 운영팀</span>' in body  # 제목 옆 고른 이름들
    assert "보기 전용</small>" not in body  # 바꿀 수 있는 근무표(IT)가 있다
    assert '<a class="to-mine" role="button" href="/?board=it" data-remember="pick=1">내 근무표만 보기</a>' in body
    month = client.get(BOTH.replace("view=week", "view=month")).content.decode()
    assert len(_names(month)) == 2 * 35  # 2026년 11월 달력 5주(11/1 일 ~ 12/5 토, 앞뒤 달 날짜도 구역을 그린다) × 2


def test_holiday_once_memos_named_and_nowork_line(client, two):
    board, ga, _ = two
    Holiday.objects.create(date=D + timedelta(days=1), name="가상 휴장")
    Memo.objects.create(board=board, scope="day", date=D, text="운영 날 메모")
    Memo.objects.create(board=board, scope="day", date=D + timedelta(days=2), text="운영 쉬는 날", no_work=True)
    Memo.objects.create(board=board, scope="week", date=D, text="운영 주 메모")
    Memo.objects.create(board=board, scope="month", date=D.replace(day=1), text="운영 달 메모")
    client.force_login(ga)
    body = client.get(BOTH).content.decode()
    assert body.count("가상 휴장") == 1  # 휴장일은 날짜 칸에 한 번(모든 근무표 공통)
    ops_label = body.index('<p class="bname">운영팀')
    assert ops_label < body.index("운영 날 메모")  # 날 메모는 그 구역 이름표 아래
    assert '<p class="nowork-line">운영 쉬는 날</p>' in body and 'class="nowork"' not in body  # 그 구역 안 한 줄
    # 근무표 이름은 흐린 <small> 밖에 본문색 굵게(시력이 약한 사용자)
    assert "<b>운영팀 · </b><small>주 메모</small>" in body and "<b>운영팀 · </b><small>11월 메모</small>" in body


def test_only_editable_sections_link_with_their_board(client, two):
    board, ga, _ = two
    client.force_login(ga)
    body = client.get(BOTH).content.decode()
    nq = quote(BOTH + f"#d-{D}")  # 돌아올 주소 = 지금 화면 그대로 + 그 날짜 칸
    assert f'hx-get="/cell/{D}/dawn/?next={nq}"' in body  # IT 구역(내 근무표라 ?board= 없음)
    assert f"/day/{D}/?board=ops#dawn" not in body  # 운영팀 구역은 보기만
    assert f'id="d-{D}"' in body
    ga.groups.add(board.admin_group)  # 운영팀 관리자가 되면 그 구역도
    body = client.get(BOTH).content.decode()
    assert f'href="/day/{D}/?board=ops#dawn"' in body and f'hx-get="/cell/{D}/dawn/?next={nq}&amp;board=ops"' in body
    assert "보기만" not in body
    assert f'href="/memo/day/{D}/?board=ops"' in body  # [메모]는 그 구역 이름표 끝
    assert f'href="/day/{D}/?board=it&amp;board=ops"' in body  # 날짜 링크는 고른 목록 그대로


def test_filters_apply_to_my_section_only(client, two):
    _, ga, _ = two
    client.force_login(ga)
    client.post("/prefs/", {"f": "1", "dept": "TMCH"})  # 내 근무표 필터: 가상다(MEMS)가 숨는다(브라우저가)
    body = client.get(f"/?date={D}&board=it&board=ops").content.decode()  # 저장한 필터 그대로
    assert 'value="TMCH" checked' in body and 'value="MEMS" checked' not in body
    assert re.search(r'data-d="MEMS" data-t="[^"]+"><span class="tk[^"]*">가상다<', body)  # 내 근무표 구역만 필터 표시
    assert re.search(r'<span class="lb"><span class="tk">가상나<', body)  # 운영팀 구역은 늘 전체(표시 없음)
    assert "부서·구분·근무는 내 근무표에만 적용됩니다" in body
    assert '<input type="hidden" name="board" value="it"><input type="hidden" name="board" value="ops">' in body  # 필터 폼이 고른 목록 그대로
    one = client.get(WEEK + "&board=it").content.decode().split('id="xl-panel"')[0]  # 엑셀 상자는 근무표를 더 고를 수 있어 늘 적는다
    assert "부서·구분·근무는 내 근무표에만" not in one  # 하나면 지금 그대로


def test_to_mine_label_rules(client, two):
    board, ga, _ = two
    client.force_login(ga)
    assert 'class="to-mine"' not in client.get(WEEK + "&board=it").content.decode()  # 정확히 [내 근무표]
    assert ">보기 전용 · 내 근무표로</a>" in client.get(WEEK + "&board=ops").content.decode()  # 지금 글자
    ga.groups.add(board.admin_group)  # 바꿀 수 있는 남의 근무표 하나: '보기 전용'이라 하지 않는다(계획 5번)
    body = client.get(WEEK + "&board=ops").content.decode()
    assert '<a class="to-mine" role="button" href="/?board=it" data-remember="pick=1">내 근무표로</a>' in body and "보기 전용" not in body


def test_queries_do_not_grow_with_days(client, two):
    """쿼리는 근무표마다 몇 번이고 날짜마다 묻지 않는다(계획 9번): 두 근무표 주간과 월간의 쿼리 수가 같다."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    _, ga, _ = two
    client.force_login(ga)
    month = BOTH.replace("view=week", "view=month")
    client.get(BOTH)  # 기억·보기 저장 같은 첫 쓰기를 먼저 치운다
    with CaptureQueriesContext(connection) as week_q:
        client.get(BOTH)
    client.get(month)
    with CaptureQueriesContext(connection) as month_q:
        client.get(month)
    assert len(month_q) == len(week_q)


# ── 하루 화면과 팝업(설계 9.4) ──

def test_day_two_boards(client, two):
    _, ga, _ = two
    client.force_login(ga)
    client.post("/prefs/", {"f": "1", "dept": "TMCH"})  # 내 근무표 필터는 내 구역에만
    body = client.get(f"/day/{D}/?board=ops&board=it").content.decode()
    it_at, ops_at = body.index('<h3 class="bname">IT 당번표'), body.index('<h3 class="bname">운영팀')
    assert it_at < ops_at  # 내 근무표 먼저
    it_part, ops_part = body[it_at:ops_at], body[ops_at:]
    assert 'id="ops-dawn"' in ops_part and "가상나" in ops_part and "보기만" in ops_part
    assert "바꾸기</summary>" not in ops_part  # 바꿀 수 없는 구역
    assert "가상다" not in it_part  # TMCH 필터
    assert f'href="/day/2026-11-13/?board=it&amp;board=ops&amp;f=1' in body  # 앞 날짜도 고른 목록 그대로
    assert '<input type="hidden" name="board" value="it"><input type="hidden" name="board" value="ops">' in body


def test_day_cell_next_has_selection_and_anchor(client, two):
    board, ga, na = two
    ga.groups.add(board.admin_group)
    client.force_login(ga)
    body = client.get(f"/day/{D}/?board=it&board=ops").content.decode()
    assert f'value="/day/{D}/?board=it&amp;board=ops#ops-dawn"' in body  # 저장 뒤 이 화면의 그 칸으로
    assert f'action="/cell/{D}/dawn/?board=ops"' in body  # POST 는 그 구역 근무표 하나


def test_popup_next_round_trip_and_safe(client, two):
    """회귀 방지(먼저 실패하는 테스트가 아님): 겹친 화면의 next 가 팝업 POST 뒤 그대로 돌아오고, 밖 주소는 버린다."""
    _, ga, _ = two
    nb = member("it03", "가상라", ga.department)
    da = User.objects.get(username="it02")
    client.force_login(ga)
    back = BOTH + f"&q1=가상다#d-{D}"
    form = client.get(f"/cell/{D}/dawn/?next={quote(back)}").content.decode()
    assert f'name="next" value="{escape(back)}"' in form
    r = client.post(f"/cell/{D}/dawn/", {"before": da.pk, "after": nb.pk, "next": back})
    assert r.status_code == 302 and r.url == iri_to_uri(back)  # 고른 근무표·검색·앵커가 그대로(Location 은 한글을 %인코딩)
    r = client.post(f"/cell/{D}/dawn/", {"before": nb.pk, "after": da.pk, "next": "https://evil.example/"})
    assert r.url == f"/day/{D}/"  # 밖 주소는 safe_next 가 버린다


def test_popup_is_one_board(client, two, it_board):
    board, ga, _ = two
    ga.groups.add(board.admin_group, it_board.admin_group)  # 두 근무표 관리자여도(권한 404 가 아니라 근무표 둘이라 404)
    client.force_login(ga)
    assert client.get(f"/cell/{D}/dawn/?board=it&board=ops").status_code == 404
    assert client.get(f"/memo/day/{D}/?board=it&board=ops").status_code == 404
    assert client.get(f"/memo/day/{D}/?board=ops").status_code == 200


def test_popup_board_name_when_two_editable(client, two):
    board, ga, na = two
    client.force_login(ga)
    assert "IT 당번표 · " not in client.get(f"/cell/{D}/dawn/").content.decode()  # 바꿀 수 있는 근무표가 하나
    ga.groups.add(board.admin_group)
    assert "운영팀 · 2026-11-16" in client.get(f"/cell/{D}/dawn/?board=ops").content.decode()
    assert "운영팀 · 11/16 주 메모" in client.get(f"/memo/week/{D}/?board=ops").content.decode()
    nb = member("op02", "가상마", na.department)
    r = client.post(f"/cell/{D}/dawn/?board=ops", {"before": na.pk, "after": nb.pk})
    assert "운영팀 · 변경했습니다." in [str(m) for m in get_messages(r.wsgi_request)]


# ── 근무표 고르기(설계 9.1, 계획 2·3번) ──

def _picker(body):
    return re.search(r'<form method="get" class="board-pick"[^>]*>.*?</form>', body, re.S)[0]


def test_picker_dropdown(client, two):
    _, ga, _ = two
    client.force_login(ga)
    body = client.get(WEEK + "&q1=가상다").content.decode()
    f = _picker(body)
    assert "근무표: IT 당번표</summary>" in f
    assert re.findall(r'name="board" value="(\w+)"( checked)?', f) == [("it", " checked"), ("ops", "")]
    assert f.index("IT 당번표 (내 근무표)") < f.index("운영팀")
    assert f.count("<button>보기</button>") == 2 and "하나도 고르지 않으면 내 근무표만 보입니다" in f
    assert 'name="pick" value="1"' in f and f'name="date" value="{D}"' in f and 'name="q1" value="가상다"' in f
    assert 'name="q2"' not in f  # 빈 검색 칸은 보내지 않는다
    for name in ("view", "dept", "type", "shift", "hist"):  # 저장값으로 남는다(계획 2번)
        assert f'name="{name}"' not in f, name
    assert 'aria-label="근무표"' not in body  # 옛 근무표 버튼 없음
    assert body.index('class="board-pick"') < body.index(">주간</a>")  # [주간]·[월간] 앞
    two_names = _picker(client.get(BOTH).content.decode())
    assert "근무표: IT 당번표 + 운영팀</summary>" in two_names


def test_pick_semantics_and_memory(client, two):
    _, ga, _ = two
    client.force_login(ga)
    client.post("/prefs/", {"pick": "1", "board": ["ops", "it"]})
    assert RosterPref.objects.get(user=ga).boards == ["it", "ops"]
    assert "가상나" in client.get(WEEK).content.decode()  # pick 도 board 도 없으면 기억한 목록
    body = client.get(f"/?pick=1&date={D}").content.decode()  # 하나도 안 고르고 [보기]: 기억과 상관없이 내 근무표만
    assert "가상다" in body and "가상나" not in body


def test_links_after_pick_have_no_pick_and_dropdown_closed(client, two):
    _, ga, _ = two
    client.force_login(ga)
    body = client.get(f"/?pick=1&board=it&board=ops&view=week&date={D}").content.decode()
    assert "?board=it&amp;board=ops&amp;view=week&amp;date=2026-11-09" in body  # ◀ 도 같은 꼴, view·date 를 지킨다
    links = body.replace('data-remember="pick=1"', "")  # [내 근무표만 보기]가 /prefs/ 로 보내는 값은 링크가 아니다
    assert "pick=" not in links and "pick%3D" not in links  # 다른 링크·팝업 next 에 pick 없음
    assert '<details class="dropdown" open' not in body  # 보낸 뒤 닫힌 채(계획 3번)


def test_picker_keeps_search_and_saved_filter(client, two):
    _, ga, _ = two
    client.force_login(ga)
    client.post("/prefs/", {"f": "1", "dept": "TMCH"})  # 내 근무표 필터: 가상다(MEMS) 숨김
    client.post("/prefs/", {"pick": "1", "board": ["it", "ops"], "date": str(D), "q1": "가상나"})  # 고르기 폼이 보내는 꼴
    body = client.get(f"/?pick=1&board=it&board=ops&date={D}&q1=가상나").content.decode()
    assert RosterPref.objects.get(user=ga).depts == ["TMCH"]  # 고르기 폼이 저장된 필터를 지우지 않는다(계획 2번)
    assert 'value="TMCH" checked' in body and '<span class="tk hl1">가상나</span>' in body  # 필터·검색 색칠이 남는다


def test_get_does_not_remember_boards_prefs_post_does(client, two):
    _, ga, _ = two
    client.force_login(ga)
    client.get(BOTH)
    client.get(f"/?pick=1&board=ops&date={D}")
    assert not RosterPref.objects.filter(user=ga).exists()  # GET 은 기억하지 않는다
    client.post("/prefs/", {"pick": "1", "board": ["ops", "it", "ops", "nope"]})  # 고르기 폼이 보낸다(없는 code 는 버림)
    assert RosterPref.objects.get(user=ga).boards == ["it", "ops"]
    client.post("/prefs/", {"board": "ops", "f": "1"})  # 하루 화면 필터 폼(pick 없음)은 목록을 건드리지 않는다
    assert RosterPref.objects.get(user=ga).boards == ["it", "ops"]
    client.post("/prefs/", {"pick": "1"})  # 하나도 안 고름 = 내 근무표만 = 기억 비움
    assert RosterPref.objects.get(user=ga).boards == []


def test_pick_form_and_to_mine_remember(client, two):
    _, ga, _ = two
    client.force_login(ga)
    body = client.get(WEEK + "&board=ops").content.decode()
    assert '<form method="get" class="board-pick" data-remember="">' in body
    assert '<a class="to-mine" role="button" href="/?board=it" data-remember="pick=1">' in body
    day = client.get(f"/day/{D}/?board=ops").content.decode()
    assert f'href="/?board=it&amp;date={D}" data-remember="pick=1">' in day
