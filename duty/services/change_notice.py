"""내 근무가 바뀌면 알림. 작업자가 매분 아직 안 보낸 ChangeLog 를 보고 당사자(From·To, 바꾼 본인 제외)에게 보낸다."""
import logging
from datetime import timedelta

from django.utils import timezone

from ..alarms import messages as m
from ..alarms import senders
from ..models import ChangeLog, PushAlarmSubscription, TelegramAlarmProfile
from . import alarm_settings
from .alarm_runner import telegram_text

log = logging.getLogger(__name__)
FRESH = timedelta(days=1)  # 작업자가 오래 꺼져 있었으면 밀린 기록은 보내지 않는다


def tick(now) -> int:
    conf = alarm_settings.current()
    today = timezone.localdate(now)
    sent = 0
    for row in ChangeLog.objects.filter(notified=False).select_related("by", "before", "after").order_by("id"):
        if row.at >= now - FRESH and row.date >= today:
            for u in {row.before, row.after} - {None, row.by}:
                if u.is_active and u.notify_changes:
                    sent += _send(conf, u, row)
        ChangeLog.objects.filter(pk=row.pk).update(notified=True)
    if sent:
        log.info("change notices: sent=%d", sent)
    return sent


def _send(conf, user, row) -> int:
    # ponytail: 실패는 다시 보내지 않는다(같은 기록의 다른 사람에게 중복이 가지 않게). 근무표·정기 알림이 계속 보여 준다
    title, text = m.change_notice(row.date, row.cell, row.before and row.before.name, row.after and row.after.name,
                                  (row.by.name or row.by.username) if row.by else "-")
    url, cfg, n = f"/day/{row.date.isoformat()}/", conf.sender_config(), 0
    if conf.telegram_on:
        tg = TelegramAlarmProfile.objects.filter(user=user, verified_at__isnull=False).exclude(chat_id="").first()
        if tg:
            try:
                senders.telegram_send(cfg, tg.chat_id, telegram_text(text, url))
                n += 1
            except senders.SendError as e:
                log.warning("change notice telegram failed: %s", type(e).__name__)
    if conf.push_on:
        for sub in PushAlarmSubscription.objects.filter(user=user):
            try:
                senders.push_send(cfg, sub, title, text.split("\n", 1)[1], url, 86400)
                n += 1
            except senders.Gone:
                sub.delete()
            except senders.SendError as e:
                log.warning("change notice push failed: %s", type(e).__name__)
    return n
