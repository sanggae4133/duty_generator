"""캘린더 구독(ICS) 주소 발급과 피드 내용. 토큰 원문은 발급 응답에서만 돌려주고 어디에도 저장하지 않는다."""

import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from .. import ics, perms
from ..errors import DutyError
from ..models import CalendarFeed, ChangeLog, Period
from ..shifts import CELLS, COMMUTE_SHIFTS, cell_end, cell_label, cell_start, is_slot_cell
from . import roster

logger = logging.getLogger(__name__)

NAME = "NXT 당번(내 일정)"
WINDOW = timedelta(days=90)
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}")
NO_MEMBER = "근무표 대상 계정만 쓸 수 있습니다."
NO_SITE_URL = "서버 주소(DUTY_SITE_URL)가 설정되지 않아 구독 주소를 만들 수 없습니다. 관리자에게 문의하세요."


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue(user) -> str:
    """구독 주소를 새로 만든다(재발급이면 이전 주소는 바로 무효). 반환값 = 절대 URL."""
    if user.department_id is None:
        raise DutyError(NO_MEMBER)
    if not settings.SITE_URL:
        raise DutyError(NO_SITE_URL)
    for attempt in range(3):  # 해시 unique 충돌(사실상 없음)·동시 첫 발급 시 2회까지 다시
        token = secrets.token_urlsafe(32)
        try:
            with transaction.atomic():
                CalendarFeed.objects.update_or_create(
                    user=user, defaults={"token_hash": _hash(token), "issued_at": timezone.now()})
        except IntegrityError:
            if attempt == 2:
                raise
            continue
        return settings.SITE_URL.rstrip("/") + reverse("calendar_feed", args=[token])


def set_shifts(user, shifts) -> None:
    """캘린더에 넣을 근무를 고른다(알림 규칙의 스케줄과 같은 값). 구독 주소는 그대로."""
    from .alarms import normalize  # 순환 import 피함
    row = CalendarFeed.objects.filter(user=user).first()
    if row is None:
        raise DutyError("먼저 구독 주소를 발급하세요.")
    if not shifts:  # 저장값 [] 은 '전부'라, 전부 해제를 그대로 받으면 반대로 전부 들어간다
        raise DutyError("캘린더에 넣을 근무를 하나 이상 고르세요.")
    row.shifts = normalize("personal", shifts, [], [])[0]  # 모르는 값은 오류, 전부 = []
    row.save(update_fields=["shifts"])


def revoke(user) -> None:
    CalendarFeed.objects.filter(user=user).delete()


def feed(token: str) -> bytes | None:
    """토큰의 ICS 본문. 모르는 토큰이면 None(404). 퇴사(비활성)·부서 없음이면 빈 캘린더."""
    if not TOKEN_RE.fullmatch(token):
        return None
    row = CalendarFeed.objects.select_related("user").filter(token_hash=_hash(token)).first()
    if row is None:
        return None
    if not (row.user.is_active and row.user.department_id):
        return ics.calendar(NAME, [])
    return ics.calendar(NAME, _events(row.user, row.shifts))


def _events(member, shifts=()) -> list[ics.Event]:
    since = perms.today() - WINDOW
    days = roster.published_days(since, None)
    published = dict(Period.objects.filter(pk__in={d.period_id for d in days}).values_list("pk", "published_at"))
    for pid in sorted(pk for pk, at in published.items() if at is None):
        logger.warning("calendar feed: published_at 없는 배포 회차 %s 제외", pid)
    days = [d for d in days if published[d.period_id]]
    if not days:
        return []
    owner = {d.date: d.period_id for d in days}
    changes = ChangeLog.objects.filter(period_id__in=set(owner.values()), date__gte=since).values_list("period_id", "date", "at")
    dtstamp = max([published[pid] for pid in owner.values()] + [at for pid, d, at in changes if owner.get(d) == pid])  # 행 없는 날짜의 기록은 제외

    tz = timezone.get_default_timezone()
    url = settings.SITE_URL.rstrip("/") + reverse("me") if settings.SITE_URL else None
    events = []
    for day in days:
        for cell in CELLS:
            if member.name not in day.members[cell] or (shifts and ("slots" if is_slot_cell(cell) else cell) not in shifts):
                continue
            start, end = cell_start(cell), cell_end(cell)
            summary = f"장중관제 {cell_label(cell)}" if is_slot_cell(cell) else \
                f"{COMMUTE_SHIFTS[cell]} 출근 {start:%H:%M}~{end:%H:%M}"
            events.append(ics.Event(
                uid=f"{day.date:%Y%m%d}-{cell}-{member.pk}@duty-generator", dtstamp=dtstamp,
                start=datetime.combine(day.date, start, tz), end=datetime.combine(day.date, end, tz),
                summary=summary, url=url))
    return events
