"""Memo 모델 제약(설계 4.8). 서비스를 거치지 않은 쓰기도 DB 가 막는다."""
from datetime import date

import pytest
from django.db import IntegrityError, transaction

from duty.models import Memo

D = date(2026, 11, 18)  # 수요일


# ── 모델 제약 ──

def _bad(**kw):
    with pytest.raises(IntegrityError), transaction.atomic():
        Memo.objects.create(**kw)


def test_constraints(it_board):
    _bad(board=it_board, scope="year", date=D, text="x")
    _bad(board=it_board, scope="week", date=D, text="x")  # 수요일
    _bad(board=it_board, scope="month", date=D, text="x")  # 18일
    _bad(board=it_board, scope="week", date=date(2026, 11, 16), text="x", no_work=True)  # 근무 없음은 날 메모만
    _bad(board=it_board, scope="day", date=D, text="")  # 빈 메모
    Memo.objects.create(board=it_board, scope="week", date=date(2026, 11, 16), text="x")
    Memo.objects.create(board=it_board, scope="month", date=date(2026, 11, 1), text="x")
    Memo.objects.create(board=it_board, scope="day", date=D, text="", no_work=True)
    _bad(board=it_board, scope="day", date=D, text="또")  # (근무표, 범위, 날짜)에 하나
