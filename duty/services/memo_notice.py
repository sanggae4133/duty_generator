"""메모 알림(근무표마다 관리자가 [근무표 설정]에서 켠다, Board.notify_memos): 관리자가 메모를 새로 달거나 고치면
(memos.save 가 notice_pending 을 켠다) 작업자가 매분 보고 그 근무표 사람 모두에게 한 번 보낸다. 쓴 사람은 받지 않는다.
지운 메모와 이미 지난 날짜의 메모(주·달은 끝 날 기준)는 알리지 않는다. 글은 자르지 않는다(메모는 500자까지)."""
import logging
import calendar
from datetime import date, timedelta

from django.utils import timezone

from ..alarms import messages as m
from ..models import Memo, User
from . import alarm_settings
from .change_notice import _send

log = logging.getLogger(__name__)
FRESH = timedelta(days=1)  # 작업자가 오래 꺼져 있었으면 밀린 메모는 보내지 않는다


def recipients(board, writer):
    """메모 알림을 받는 사람: 그 근무표 재직자 모두, 쓴 사람은 빼고. 메모 창의 'N명에게 갑니다'도 이것을 센다."""
    return User.objects.filter(is_active=True, department__board=board).exclude(pk=writer.pk if writer else None)


def _last_day(r) -> date:
    if r.scope == Memo.Scope.WEEK:
        return r.date + timedelta(days=6)
    if r.scope == Memo.Scope.MONTH:
        return r.date.replace(day=calendar.monthrange(r.date.year, r.date.month)[1])
    return r.date


def tick(now) -> int:
    rows = list(Memo.objects.filter(notice_pending=True).select_related("board", "edited_by").order_by("id"))
    if not rows:
        return 0
    Memo.objects.filter(pk__in=[r.pk for r in rows]).update(notice_pending=False)  # 먼저 표시: 최대 한 번
    conf, sent, today = alarm_settings.current(), 0, timezone.localdate(now)
    for r in rows:
        if not r.board.notify_memos or r.edited_at is None or r.edited_at < now - FRESH or _last_day(r) < today:
            continue
        by = (r.edited_by.name or r.edited_by.username) if r.edited_by else "-"
        title, text = m.memo_notice(r.board.name, r.scope, r.date, r.text, r.no_work, by)
        url = f"/day/{r.date.isoformat()}/" if r.scope == Memo.Scope.DAY else \
            f"/?view={'month' if r.scope == Memo.Scope.MONTH else 'week'}&date={r.date.isoformat()}"
        for u in recipients(r.board, r.edited_by):  # 받는 사람의 내 근무표 = 메모의 근무표라 링크에 ?board= 가 필요 없다
            sent += _send(conf, u, title, text, url)
    if sent:
        log.info("memo notices: sent=%d", sent)
    return sent
