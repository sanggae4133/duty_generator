"""메모 알림(근무표마다 관리자가 [근무표 설정]에서 켠다, Board.notify_memos): 관리자가 메모를 새로 달거나 고치면
(memos.save 가 notice_pending 을 켠다) 작업자가 매분 보고 그 근무표 사람 모두에게 한 번 보낸다. 쓴 사람은 받지 않는다.
지운 메모는 알리지 않는다. 글은 자르지 않는다(메모는 500자까지)."""
import logging
from datetime import timedelta

from ..alarms import messages as m
from ..models import Memo, User
from . import alarm_settings
from .change_notice import _send

log = logging.getLogger(__name__)
FRESH = timedelta(days=1)  # 작업자가 오래 꺼져 있었으면 밀린 메모는 보내지 않는다


def tick(now) -> int:
    rows = list(Memo.objects.filter(notice_pending=True).select_related("board", "edited_by").order_by("id"))
    if not rows:
        return 0
    Memo.objects.filter(pk__in=[r.pk for r in rows]).update(notice_pending=False)  # 먼저 표시: 최대 한 번
    conf, sent = alarm_settings.current(), 0
    for r in rows:
        if not r.board.notify_memos or r.edited_at is None or r.edited_at < now - FRESH:
            continue
        by = (r.edited_by.name or r.edited_by.username) if r.edited_by else "-"
        title, text = m.memo_notice(r.board.name, r.scope, r.date, r.text, r.no_work, by)
        url = f"/day/{r.date.isoformat()}/" if r.scope == Memo.Scope.DAY else \
            f"/?view={'month' if r.scope == Memo.Scope.MONTH else 'week'}&date={r.date.isoformat()}"
        to = User.objects.filter(is_active=True, department__board=r.board).exclude(pk=r.edited_by_id)
        for u in to:  # 받는 사람의 내 근무표 = 메모의 근무표라 링크에 ?board= 가 필요 없다
            sent += _send(conf, u, title, text, url)
    if sent:
        log.info("memo notices: sent=%d", sent)
    return sent
