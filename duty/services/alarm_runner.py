"""알림 발송 1회(tick). 계획(plan)은 순수 계층, 여기서는 조회·발송·기록만 한다."""
import logging
import math
from collections import defaultdict
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .. import perms
from ..alarms import messages as m
from ..alarms import senders
from ..alarms.plan import RuleSpec, plan
from ..alarms.schedule import send_at
from ..models import (AlarmDelivery, AlarmDeliveryStatus, AlarmRule, Department,
                      PushAlarmSubscription, TelegramAlarmProfile, User)
from .alarms import RULE_FIELDS
from .roster import published_days

log = logging.getLogger(__name__)
HORIZON = timedelta(days=45)
KEEP = timedelta(days=7)
LIMIT = 4000  # 텔레그램 본문 최대 길이


def _link(url: str) -> str | None:
    """SITE_URL 절대 링크. 비었거나 너무 길어 본문(최소 생략 표시만큼) 자리가 없으면 None."""
    link = settings.SITE_URL.rstrip("/") + url if settings.SITE_URL else None
    return link if link and len(link) + 1 + len(m.CUT) <= LIMIT else None


def telegram_text(text: str, url: str) -> str:
    """SITE_URL이 있으면 마지막 줄에 절대 링크. 링크 자리를 먼저 빼고 본문을 잘라 전체 4000자 이내."""
    link = _link(url)
    if link is None:
        return m.clip(text, LIMIT)
    return m.clip(text, LIMIT - len(link) - 1) + "\n" + link


def _destinations(rules):
    user_ids = {r.user_id for r in rules}
    tg, push = {}, defaultdict(list)
    if senders.telegram_enabled():
        tg = dict(TelegramAlarmProfile.objects.filter(user_id__in=user_ids, verified_at__isnull=False)
                  .exclude(chat_id="").values_list("user_id", "chat_id"))
    if senders.push_enabled():
        for uid, sid in PushAlarmSubscription.objects.filter(user_id__in=user_ids).values_list("user_id", "id"):
            push[uid].append(f"sub:{sid}")
    out = {}
    for r in rules:
        if r.telegram and r.user_id in tg:
            out[(r.id, "telegram")] = [tg[r.user_id]]
        if r.push and push[r.user_id]:
            out[(r.id, "push")] = push[r.user_id]
    return out


SNAP = ("user_id", "enabled", "telegram", "push", *RULE_FIELDS)  # 계획에 쓴 규칙 값. 발송 직전·기록 때 다시 비교


def _snap(rule) -> tuple:
    return tuple(getattr(rule, f) for f in SNAP)


def _current(rule_id, snap) -> bool:
    """규칙이 아직 있고 계획 때와 같은가(끔·조건/채널 변경·삭제면 False)."""
    rule = AlarmRule.objects.filter(id=rule_id).first()
    return rule is not None and _snap(rule) == snap


def _valid(rule, today) -> bool:
    """시각 계산이 되는 규칙인가. 잘못된 규칙 하나가 tick 전체를 멈추지 않게 미리 걸러 낸다."""
    try:
        send_at(rule.timing, rule.offset, rule.at_minute, today, datetime.combine(today, time()))
    except ValueError:
        log.warning("alarm rule invalid rule=%s", rule.id)
        return False
    return True


def collect(now):
    """보낼 (Due, 기존 기록, 규칙 스냅숏) 목록. 같은 내용의 backoff 중인 것은 뺀다."""
    if timezone.is_naive(now):
        raise ValueError("now는 aware datetime이어야 합니다.")
    today = perms.today()
    rules = [r for r in AlarmRule.objects.filter(enabled=True, user__is_active=True).select_related("user")
             if _valid(r, today)]
    snaps = {r.id: _snap(r) for r in rules}
    # 개인 알림 대상은 근무표 대상 계정(부서 있음)만. 부서 없는 어드민은 보고서형만 받는다
    specs = [RuleSpec(r.id, r.user.name if r.user.department_id else None, r.kind, r.timing, r.offset, r.at_minute,
                      tuple(ch for ch in ("telegram", "push") if getattr(r, ch)),
                      tuple(r.shifts), tuple(r.depts), tuple(r.types)) for r in rules]
    rows = {(d.rule_id, d.date, d.cell, d.channel, d.destination): d
            for d in AlarmDelivery.objects.filter(date__gte=today)}
    info = {n: (dept, typ) for n, dept, typ in User.objects.values_list("name", "department__code", "type")}
    dues = plan(specs, published_days(today, today + HORIZON), info,
                {k: d.last_sent_hash for k, d in rows.items()}, timezone.localtime(now).replace(tzinfo=None),
                destinations=_destinations(rules), dept_names=dict(Department.objects.values_list("code", "name")),
                extra_dates={k[1] for k in rows}, today=today)
    out = []
    for due in dues:
        row = rows.get((due.rule_id, due.date, due.cell, due.channel, due.destination))
        if (row and row.status == AlarmDeliveryStatus.FAILED and row.content_hash == due.content_hash
                and row.next_attempt_at and row.next_attempt_at > now):
            continue
        out.append((due, row, snaps[due.rule_id]))
    return out


def _send(due, now, expires, user_id):
    """성공 True, 구독 없음/Gone은 None. 실패는 예외."""
    if due.channel == "telegram":
        senders.telegram_send(due.destination, telegram_text(due.text, due.url))
        return True
    # 지금도 규칙 주인의 구독일 때만(그사이 다른 사용자에게 넘어갔으면 건너뜀)
    sub = PushAlarmSubscription.objects.filter(id=int(due.destination.removeprefix("sub:")), user_id=user_id).first()
    if sub is None:
        return None
    try:
        senders.push_send(sub, due.title, due.push_text, due.url,
                          max(1, math.ceil((expires - now).total_seconds())))
    except senders.Gone:
        sub.delete()
        return None
    return True


def _next_attempt(err, attempts, now, expires):
    if isinstance(err, senders.Permanent):
        return expires
    if isinstance(err, senders.RetryLater) and err.seconds is not None and err.seconds >= 0:
        return now + timedelta(seconds=err.seconds)
    return now + timedelta(minutes=min(2 ** (attempts - 1), 30))


def tick(now) -> tuple[int, int, int]:
    pending = collect(now)
    sent = failed = 0
    if settings.SITE_URL and any(d.channel == "telegram" and _link(d.url) is None for d, *_ in pending):
        log.warning("alarms: SITE_URL too long, telegram link omitted")
    for due, row, snap in pending:
        key = dict(rule_id=due.rule_id, date=due.date, cell=due.cell, channel=due.channel, destination=due.destination)
        expires = timezone.make_aware(due.expires_at)
        # ponytail: 발송 직전·기록 때 규칙을 다시 본다. 남는 틈은 네트워크 호출 자체(≤10초), 막으려면 규칙별 claim 잠금
        if not _current(due.rule_id, snap):
            continue
        err = None
        try:
            ok = _send(due, now, expires, snap[0])
        except Exception as e:  # 예기치 않은 예외도 일시 실패로(로그엔 예외 타입만)
            ok, err = False, e
        if not ok and err is None:
            continue
        with transaction.atomic():  # IMMEDIATE: 웹 쓰기와 직렬화된 상태에서 재확인 후 기록
            if not _current(due.rule_id, snap):
                continue  # 그사이 바뀌거나 지워짐 → 옛 조건 기록을 남기지 않는다(삭제된 규칙 FK 오류도 피함)
            if err is None:
                AlarmDelivery.objects.update_or_create(**key, defaults=dict(
                    status=AlarmDeliveryStatus.SENT, attempts=0, next_attempt_at=None,
                    content_hash=due.content_hash, last_sent_hash=due.content_hash))
                sent += 1
                continue
            same = row is not None and row.status == AlarmDeliveryStatus.FAILED and row.content_hash == due.content_hash
            attempts = row.attempts + 1 if same else 1
            d, _ = AlarmDelivery.objects.update_or_create(**key, defaults=dict(
                status=AlarmDeliveryStatus.FAILED, attempts=attempts, content_hash=due.content_hash,
                next_attempt_at=_next_attempt(err, attempts, now, expires)))
        failed += 1
        log.warning("alarm send failed rule=%s channel=%s delivery=%s status=%s attempt=%s",
                    due.rule_id, due.channel, d.id, f"{type(err).__name__}:{getattr(err, 'status', None)}", attempts)
    AlarmDelivery.objects.filter(date__lt=perms.today() - KEEP).delete()
    log.info("alarms tick: due=%d sent=%d failed=%d", len(pending), sent, failed)
    return len(pending), sent, failed
