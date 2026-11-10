import fcntl
import ipaddress
import re
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .. import perms
from ..alarms import senders
from ..errors import DutyError
from ..models import AlarmRule, Department, PushAlarmSubscription, TelegramAlarmProfile
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
    changed = rule.pk is not None and _key(rule) != tuple(new[f] for f in RULE_FIELDS)
    try:
        with transaction.atomic():
            for k, v in new.items():
                setattr(rule, k, v)
            rule.save()
            if changed:
                rule.deliveries.filter(date__gte=perms.today()).delete()
    except IntegrityError:
        key = tuple(new[f] for f in RULE_FIELDS)
        if any(_key(r) == key for r in AlarmRule.objects.filter(user=user).exclude(pk=rule.pk)):
            raise DutyError("같은 규칙이 이미 있습니다.") from None
        raise
    return rule


def _key(rule: AlarmRule) -> tuple:
    """정규화한 비교 키. 저장값이 정규화 전 형태(순서·전부 선택)여도 같게 본다."""
    try:
        shifts, depts, types = normalize(rule.kind, rule.shifts, rule.depts, rule.types)
    except DutyError:  # 지금은 없는 부서 등 → 저장값 그대로
        shifts, depts, types = rule.shifts, rule.depts, rule.types
    return rule.kind, rule.timing, rule.offset, rule.at_minute, shifts, depts, types


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
    TelegramAlarmProfile.objects.filter(user=user).update(  # 대기 중인 연결 코드도 폐기
        chat_id=chat_id, verified_at=timezone.now() if verified else None, link_code=None, link_expires_at=None)


def clear_telegram(user) -> None:
    TelegramAlarmProfile.objects.filter(user=user).update(chat_id="", verified_at=None, link_code=None,
                                                          link_expires_at=None)


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


MAX_BATCHES = 100  # ponytail: 안전 상한(100건 × 100묶음). 전용 봇이라 넘을 일 없음, 넘으면 확인 처리 후 재시도 안내


def _link_from_updates(now, linked: list[str]) -> None:
    """getUpdates 묶음마다 유효한 /start <코드>를 각 소유자에게 연결하고 offset으로 확인 처리, 빈 결과까지.
    연결된 chat_id는 호출자의 linked에 바로 넣는다(뒤 묶음이 실패해도 완료 메시지를 보내도록)."""
    offset = None
    for _ in range(MAX_BATCHES):
        updates = senders.telegram_get_updates(offset=offset, limit=100)
        if not updates:
            return
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
            return
        offset = last + 1
    if not senders.telegram_get_updates(offset=offset, limit=1):  # 마지막 묶음 확인 처리. 남은 건 처리·확인 안 함
        return
    raise DutyError("처리할 메시지가 남았습니다. 잠시 후 다시 시도하세요.")


def check_link(user) -> str:
    """[연결 확인]. 성공 메시지를 돌려주고, 실패는 DutyError."""
    if not (settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_BOT_USERNAME):
        raise DutyError("텔레그램 봇이 설정되지 않았습니다.")
    now = timezone.now()
    expired = "연결 코드가 만료되었습니다. 다시 [텔레그램 연결]을 눌러 주세요."
    if TelegramAlarmProfile.objects.filter(user=user, link_code__isnull=False, link_expires_at__lte=now).update(
            link_code=None, link_expires_at=None):
        raise DutyError(expired)
    TelegramAlarmProfile.objects.filter(link_expires_at__lte=now).update(link_code=None, link_expires_at=None)
    p = _profile(user)
    if p.link_code is None:
        if p.verified_at and p.chat_id:  # 코드 없이 누름: 방금 남의 확인으로 연결됐거나 이전부터 연결됨
            return "텔레그램이 연결되었습니다." if now - p.verified_at < LINK_TTL else "이미 연결되어 있습니다(기존 연결 유지)."
        raise DutyError(expired)
    linked: list[str] = []
    try:
        with open(settings.TELEGRAM_UPDATES_LOCK_PATH, "a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DutyError("다른 연결 확인이 진행 중입니다. 잠시 후 다시 시도하세요.") from None
            if not take_cooldown(user):
                raise DutyError("잠시 후 다시 시도하세요.")
            try:
                _link_from_updates(now, linked)
            except senders.Permanent:
                raise DutyError("텔레그램 봇 설정 오류입니다. 관리자에게 알려 주세요.") from None
            except senders.SendError:
                raise DutyError("텔레그램 서버에 연결하지 못했습니다. 잠시 후 다시 시도하세요.") from None
    finally:
        for cid in linked:  # DB 반영 후 발송(오류가 나도 이미 연결된 사람에겐). 실패해도 연결은 유지
            try:
                senders.telegram_send(cid, "[연결 완료] 당번 알림이 이 채팅으로 옵니다.")
            except senders.SendError:
                pass
    p.refresh_from_db()
    if p.link_code is None and p.verified_at and p.chat_id:
        return "텔레그램이 연결되었습니다."
    raise DutyError("아직 확인되지 않았습니다. 텔레그램에서 [시작]을 눌렀는지 확인하고 다시 눌러 주세요.")


# ---- 웹 푸시 ----

PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "push.apple.com")  # WNS는 실제 Edge 검증 전까지 제외
UNSUPPORTED = "지원하지 않는 푸시 서비스입니다."
MAX_DEVICES = 20


class SubscriptionConflict(DutyError):
    """다른 사용자의 endpoint인데 키가 다름 → 409"""


def _b64url(v, lo, hi) -> bool:
    return isinstance(v, str) and lo <= len(v) <= hi and re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", v) is not None


def check_endpoint(endpoint) -> None:
    """SSRF 방지: https, userinfo·포트 없음, IP 리터럴 아님, 허용 목록 호스트."""
    # 공백·제어 문자는 urlsplit·requests가 벗겨내므로 미리 막는다(같은 endpoint 중복 등록 방지)
    if not isinstance(endpoint, str) or len(endpoint) > 500 or not re.fullmatch(r"[\x21-\x7e]+", endpoint):
        raise DutyError("잘못된 푸시 구독입니다.")
    try:
        u = urlsplit(endpoint)
        port = u.port
    except ValueError:
        raise DutyError("잘못된 푸시 구독입니다.") from None
    host = (u.hostname or "").lower()
    if u.scheme != "https" or "@" in u.netloc or port is not None or ":" in u.netloc or not host:
        raise DutyError(UNSUPPORTED)
    try:
        ipaddress.ip_address(host)
        raise DutyError(UNSUPPORTED)
    except ValueError:
        pass
    if not any(host == s or host.endswith("." + s) for s in PUSH_HOSTS):
        raise DutyError(UNSUPPORTED)


def ua_label(ua: str) -> str:
    def first(pairs):
        return next((name for key, name in pairs if key in ua), "")
    browser = first([("Edg", "Edge"), ("SamsungBrowser", "삼성 인터넷"), ("Firefox/", "Firefox"), ("FxiOS", "Firefox"),
                     ("CriOS", "Chrome"), ("Chrome/", "Chrome"), ("Safari/", "Safari")])
    os_ = first([("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "Windows"),
                 ("CrOS", "ChromeOS"), ("Mac OS X", "macOS"), ("Linux", "Linux")])
    if not browser and os_ in ("iPhone", "iPad") and "AppleWebKit" in ua and "Mobile" in ua:
        browser = "홈 화면 앱"
    return " / ".join(p for p in (browser, os_) if p)[:80] or "알 수 없는 기기"


def add_subscription(user, endpoint, p256dh, auth, user_agent: str, replaces=None) -> PushAlarmSubscription:
    """replaces: 이 브라우저가 전에 등록한 endpoint. 내 것이면 같은 트랜잭션에서 지운다(UA로 합치지 않음)."""
    check_endpoint(endpoint)
    if not (_b64url(p256dh, 80, 100) and _b64url(auth, 16, 32)):
        raise DutyError("잘못된 푸시 키입니다.")
    with transaction.atomic():
        old = PushAlarmSubscription.objects.filter(endpoint=endpoint).first()
        if old and old.user_id != user.id and (old.p256dh, old.auth) != (p256dh, auth):
            raise SubscriptionConflict("다른 사용자가 등록한 기기입니다.")
        mine = PushAlarmSubscription.objects.filter(user=user)
        if isinstance(replaces, str) and replaces != endpoint:
            mine.filter(endpoint=replaces).delete()
        if not (old and old.user_id == user.id) and mine.count() >= MAX_DEVICES:
            raise DutyError(f"등록 기기는 최대 {MAX_DEVICES}대입니다. 쓰지 않는 기기를 먼저 해제해 주세요.")
        return PushAlarmSubscription.objects.update_or_create(endpoint=endpoint, defaults=dict(
            user=user, p256dh=p256dh, auth=auth, label=ua_label(user_agent)))[0]


def remove_subscription(user, endpoint) -> None:
    PushAlarmSubscription.objects.filter(user=user, endpoint=endpoint).delete()


def delete_subscription(sub: PushAlarmSubscription) -> None:
    sub.delete()


def delete_all_subscriptions(user) -> None:
    PushAlarmSubscription.objects.filter(user=user).delete()


def test_push(user) -> tuple[int, int]:
    """내 모든 구독에 테스트 푸시. (성공, 실패). Gone은 삭제하고 실패로 센다."""
    ok = fail = 0
    for sub in PushAlarmSubscription.objects.filter(user=user):
        try:
            senders.push_send(sub, "[테스트] 당번 알림", "이 기기로 푸시 알림이 옵니다.", "/alarms/", 60)
            ok += 1
        except senders.Gone:
            sub.delete()
            fail += 1
        except senders.SendError:
            fail += 1
    return ok, fail
