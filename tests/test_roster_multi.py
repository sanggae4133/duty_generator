"""여러 근무표 한 화면(근무표 통합 설계 9절, 5단계): 기억 목록·겹친 주간·월간·하루 화면·팝업·근무표 고르기.
이름은 모두 가상. two 픽스처: IT(가상다 새벽)·운영팀(가상나 새벽)이 D 에 배포, 로그인은 IT 의 가상가, 오늘 = D 앞 금요일."""
import re
from datetime import timedelta
from urllib.parse import quote

import pytest
from django.contrib.messages import get_messages
from django.utils.encoding import iri_to_uri
from django.utils.html import escape

from duty.models import Holiday, Memo, RosterPref
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
