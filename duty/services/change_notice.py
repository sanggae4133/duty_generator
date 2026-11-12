"""내 근무가 바뀌면 알림. 작업자가 매분 아직 안 보낸 ChangeLog 를 보고 당사자(From·To, 바꾼 본인 제외)에게 보낸다."""
import logging
from datetime import timedelta

from .. import perms
from ..alarms import messages as m
from ..alarms import senders
from ..models import ChangeLog, Commute, ControlDuty, Period, PushAlarmSubscription, TelegramAlarmProfile
from . import alarm_settings
from .alarm_runner import telegram_text

log = logging.getLogger(__name__)
FRESH = timedelta(days=1)  # 작업자가 오래 꺼져 있었으면 밀린 기록은 보내지 않는다


def tick(now) -> int:
    rows = list(ChangeLog.objects.filter(notified=False).select_related("by", "before", "after", "period").order_by("id"))
    if not rows:
        return 0
    # 먼저 표시하고 보낸다: 보내는 도중 작업자가 죽어도 다시 보내지 않는다(최대 한 번). 실패는 로그만
    ChangeLog.objects.filter(pk__in=[r.pk for r in rows]).update(notified=True)
    conf, today, sent, i = alarm_settings.current(), perms.today(), 0, 0
    while i < len(rows):
        r = rows[i]
        pair = rows[i + 1] if i + 1 < len(rows) and _is_swap(r, rows[i + 1]) else None
        i += 2 if pair else 1
        if not _live(r, now, today):
            continue
        by = (r.by.name or r.by.username) if r.by else "-"
        if pair:
            title, text = m.swap_notice(r.date, r.cell, r.before.name, pair.cell, r.after.name, by)
        else:
            title, text = m.change_notice(r.date, r.cell, r.before and r.before.name, r.after and r.after.name, by)
        for u in {r.before, r.after} - {None, r.by}:
            if u.is_active and u.notify_changes:
                sent += _send(conf, u, title, text, f"/day/{r.date.isoformat()}/")
    if sent:
        log.info("change notices: sent=%d", sent)
    return sent


def _is_swap(a, b) -> bool:
    """swap() 이 연달아 남긴 두 기록(A 칸 A>B, B 칸 B>A)."""
    return (a.before_id and a.after_id and a.by_id == b.by_id and a.date == b.date and a.period_id == b.period_id
            and b.before_id == a.after_id and b.after_id == a.before_id and a.cell != b.cell)


def _live(r, now, today) -> bool:
    """지금 근무표에 살아 있는 기록만: 배포 중인 회차가 그날의 주인이고, 배포 취소 이전 기록이 아니다."""
    p = r.period
    return (r.at >= now - FRESH and r.date >= today and p.status == Period.Status.PUBLISHED and r.id > p.log_floor
            and (Commute.objects.filter(period=p, date=r.date).exists()
                 or ControlDuty.objects.filter(period=p, date=r.date).exists()))


def _send(conf, user, title, text, url) -> int:
    cfg, n = conf.sender_config(), 0
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
