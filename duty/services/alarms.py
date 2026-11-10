import fcntl
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .. import perms
from ..alarms import senders
from ..errors import DutyError
from ..models import AlarmRule, Department, TelegramAlarmProfile
from ..shifts import DEVELOPER, STAFF
from .prefs import SHIFT_KEYS

DEFAULT_RULES = [
    dict(kind="personal", timing="days", offset=1, at_minute=18 * 60, telegram=True, push=False, shifts=["dawn", "dinner", "night"]),
    dict(kind="personal", timing="before_start", offset=120, at_minute=0, telegram=True, push=False, shifts=["dawn", "dinner", "night"]),
]


def normalize(kind, shifts, depts, types):
    """알려진 값만 남기고 정해진 순서로 정렬. 전부 선택 = [](전체). 개인 규칙은 부서·유형 필터 없음."""
    def pick(vals, order):
        bad = [v for v in vals if v not in order]
        if bad:
            raise DutyError(f"알 수 없는 값: {', '.join(map(str, bad))}")
        got = [v for v in order if v in set(vals)]
        return [] if len(got) == len(order) else got

    s = pick(shifts, SHIFT_KEYS)
    d = pick(depts, sorted(Department.objects.values_list("code", flat=True)))
    t = pick(types, [STAFF, DEVELOPER])
    return (s, [], []) if kind == "personal" else (s, d, t)


def create_defaults(user) -> None:
    if AlarmRule.objects.filter(user=user).exists():
        return
    AlarmRule.objects.bulk_create([AlarmRule(user=user, **r) for r in DEFAULT_RULES])


# ---- 규칙 ----

RULE_FIELDS = ("kind", "timing", "offset", "at_minute", "shifts", "depts", "types")  # 바뀌면 오늘 이후 발송 기록 삭제


def save_rule(user, data: dict, rule: AlarmRule | None = None) -> AlarmRule:
    shifts, depts, types = normalize(data["kind"], data["shifts"], data["depts"], data["types"])
    new = {**data, "shifts": shifts, "depts": depts, "types": types}
    rule = rule or AlarmRule(user=user)
    changed = rule.pk is not None and any(getattr(rule, f) != new[f] for f in RULE_FIELDS)
    try:
        with transaction.atomic():
            for k, v in new.items():
                setattr(rule, k, v)
            rule.save()
            if changed:
                rule.deliveries.filter(date__gte=perms.today()).delete()
    except IntegrityError:
        raise DutyError("같은 규칙이 이미 있습니다.") from None
    return rule


def delete_rule(rule: AlarmRule) -> None:
    rule.delete()


def toggle_rule(rule: AlarmRule) -> None:
    rule.enabled = not rule.enabled
    rule.save(update_fields=["enabled"])


# ---- 텔레그램 ----

COOLDOWN = timedelta(seconds=30)
LINK_TTL = timedelta(minutes=10)


def _profile(user) -> TelegramAlarmProfile:
    return TelegramAlarmProfile.objects.get_or_create(user=user)[0]


def set_telegram(user, chat_id: str, verified: bool) -> None:
    _profile(user)
    TelegramAlarmProfile.objects.filter(user=user).update(
        chat_id=chat_id, verified_at=timezone.now() if verified else None)


def clear_telegram(user) -> None:
    TelegramAlarmProfile.objects.filter(user=user).update(chat_id="", verified_at=None)


def take_cooldown(user) -> bool:
    """외부 호출 전에 last_test_at 갱신. 30초 안에 또 부르면 False."""
    _profile(user)
    now = timezone.now()
    return bool(TelegramAlarmProfile.objects.filter(user=user)
                .filter(Q(last_test_at__isnull=True) | Q(last_test_at__lte=now - COOLDOWN))
                .update(last_test_at=now))


def new_link_code(user) -> str:
    """새 코드가 기존 코드를 덮어쓴다(이전 코드 무효)."""
    _profile(user)
    code = secrets.token_urlsafe(16)
    TelegramAlarmProfile.objects.filter(user=user).update(link_code=code, link_expires_at=timezone.now() + LINK_TTL)
    return code


def _link_from_updates(now) -> list[str]:
    """getUpdates 묶음마다 유효한 /start <코드>를 각 소유자에게 연결하고 offset으로 확인 처리. 연결된 chat_id 목록."""
    linked, offset = [], None
    for _ in range(50):  # ponytail: 묶음 100건 × 50, 전용 봇이라 넉넉함
        updates = senders.telegram_get_updates(offset=offset, limit=100)
        if not updates:
            break
        for u in updates:
            msg = u.get("message") if isinstance(u, dict) else None
            chat = msg.get("chat") if isinstance(msg, dict) else None
            text = msg.get("text") if isinstance(msg, dict) else None
            if not (isinstance(chat, dict) and chat.get("type") == "private" and isinstance(text, str)):
                continue
            cid = chat.get("id")
            parts = text.split()
            if not (isinstance(cid, int) and 1 <= cid <= 2**63 - 1 and len(parts) == 2 and parts[0] == "/start"):
                continue
            if TelegramAlarmProfile.objects.filter(link_code=parts[1], link_expires_at__gt=now).update(
                    chat_id=str(cid), verified_at=now, link_code=None, link_expires_at=None):
                linked.append(str(cid))
        last = max((u["update_id"] for u in updates if isinstance(u, dict) and isinstance(u.get("update_id"), int)),
                   default=None)
        if last is None:
            break
        offset = last + 1
    return linked


def check_link(user) -> str:
    """[연결 확인]. 성공 메시지를 돌려주고, 실패는 DutyError."""
    if not (settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_BOT_USERNAME):
        raise DutyError("텔레그램 봇이 설정되지 않았습니다.")
    now = timezone.now()
    TelegramAlarmProfile.objects.filter(link_expires_at__lte=now).update(link_code=None, link_expires_at=None)
    p = _profile(user)
    if p.link_code is None:
        if p.verified_at and p.chat_id:
            return "텔레그램이 연결되었습니다."
        raise DutyError("연결 코드가 만료되었습니다. 다시 [텔레그램 연결]을 눌러 주세요.")
    with open(settings.TELEGRAM_UPDATES_LOCK_PATH, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DutyError("다른 연결 확인이 진행 중입니다. 잠시 후 다시 시도하세요.") from None
        if not take_cooldown(user):
            raise DutyError("잠시 후 다시 시도하세요.")
        try:
            linked = _link_from_updates(now)
        except senders.Permanent:
            raise DutyError("텔레그램 봇 설정 오류입니다. 관리자에게 알려 주세요.") from None
        except senders.SendError:
            raise DutyError("텔레그램 서버에 연결하지 못했습니다. 잠시 후 다시 시도하세요.") from None
    for cid in linked:  # DB 반영 후 발송. 실패해도 연결은 유지
        try:
            senders.telegram_send(cid, "[연결 완료] 당번 알림이 이 채팅으로 옵니다.")
        except senders.SendError:
            pass
    p.refresh_from_db()
    if p.link_code is None and p.verified_at and p.chat_id:
        return "텔레그램이 연결되었습니다."
    raise DutyError("아직 확인되지 않았습니다. 텔레그램에서 [시작]을 눌렀는지 확인하고 다시 눌러 주세요.")
