"""텔레그램·웹 푸시 발송기. 실패는 4종 예외로 분류한다.

토큰·endpoint·본문은 예외 메시지에 넣지 않는다(로그 유출 방지).
봇 토큰·VAPID 값은 Config 로 받는다(DB 설정은 services.alarm_settings 가 읽어 넘긴다 — 이 모듈은 ORM 없음).
"""
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import urllib.error
import urllib.request

from pywebpush import WebPushException, webpush


class SendError(Exception):
    def __init__(self, status: int | None = None):
        super().__init__(f"status={status}")
        self.status = status


class Gone(SendError):
    """구독 만료(404/410) → 호출자가 구독 삭제"""


class Permanent(SendError):
    """재시도 무의미"""


class Temporary(SendError):
    """일시 장애 → 백오프 재시도"""


class RetryLater(SendError):
    def __init__(self, seconds: int | None = None, status: int | None = None):
        super().__init__(status)
        self.seconds = seconds


@dataclass(frozen=True)
class Config:
    telegram_token: str = field(default="", repr=False)
    vapid_private_key: str = field(default="", repr=False)
    vapid_subject: str = ""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _retry_after(value) -> int | None:
    """Retry-After: 정수 초 또는 HTTP-date. 음수·과거·이상값은 None."""
    if value is None:
        return None
    try:
        n = int(value)
        return n if n >= 0 else None
    except (TypeError, ValueError):
        pass
    try:
        when = parsedate_to_datetime(str(value))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        secs = math.ceil((when - _utcnow()).total_seconds())
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    return secs if secs > 0 else None


def _telegram_call(cfg: Config, method: str, payload: dict):
    if not cfg.telegram_token:
        raise Permanent()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{cfg.telegram_token}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())["result"]
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            body = json.loads(e.read())
        except Exception:
            body = {}
        if code == 429:
            params = body.get("parameters") if isinstance(body, dict) else None
            ra = params.get("retry_after") if isinstance(params, dict) else None
            raise RetryLater(ra if isinstance(ra, int) and ra >= 0 else None, code) from None
        if 400 <= code < 500:
            raise Permanent(code) from None  # 409 = webhook 설정됨 등 봇 설정 오류
        raise Temporary(code) from None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):  # URLError·timeout·깨진 응답
        raise Temporary() from None


def telegram_send(cfg: Config, chat_id: str, text: str) -> dict:
    result = _telegram_call(cfg, "sendMessage", {"chat_id": chat_id, "text": text})
    if not isinstance(result, dict):
        raise Temporary()
    return result


def telegram_get_updates(cfg: Config, offset: int | None = None, limit: int = 100) -> list[dict]:
    payload = {"limit": limit, "allowed_updates": ["message"]}
    if offset is not None:
        payload = {"offset": offset, **payload}
    result = _telegram_call(cfg, "getUpdates", payload)
    if not isinstance(result, list):
        raise Temporary()
    return result


def telegram_check(cfg: Config, chat_id: str) -> str:
    try:
        return telegram_send(cfg, chat_id, "[테스트] 당번 알림 연결 확인")["chat"]["type"]
    except (KeyError, TypeError):
        raise Temporary() from None


def push_send(cfg: Config, sub, title: str, body: str, url: str, ttl: int) -> None:
    from ..errors import DutyError
    from ..services.alarms import check_endpoint  # 순환 import 회피
    try:
        check_endpoint(sub.endpoint)  # 방어: 저장 후 규칙이 강화돼도 허용 목록 밖으로는 보내지 않고 구독을 지운다
    except DutyError:
        raise Gone() from None  # 호출자가 구독을 지운다
    try:
        webpush(
            subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
            data=json.dumps({"title": title, "body": body, "url": url}, ensure_ascii=False),
            vapid_private_key=cfg.vapid_private_key,
            vapid_claims={"sub": cfg.vapid_subject},
            timeout=10,
            ttl=ttl,
        )
    except WebPushException as e:
        resp = e.response
        code = getattr(resp, "status_code", None)
        if code in (404, 410):
            raise Gone(code) from None
        if code in (429, 503):
            raise RetryLater(_retry_after(resp.headers.get("Retry-After")), code) from None
        # 401/403은 VAPID 키·설정 오류일 가능성 → 운영자가 고치면 되므로 재시도
        if code is not None and 400 <= code < 500 and code not in (401, 403):
            raise Permanent(code) from None
        raise Temporary(code) from None
    except (OSError, ValueError, TypeError):  # 깨진 VAPID 키 등 / requests 예외 포함(ConnectionError·Timeout)
        raise Temporary() from None
