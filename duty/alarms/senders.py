"""텔레그램·웹 푸시 발송기. 실패는 4종 예외로 분류한다.

토큰·endpoint·본문은 예외 메시지에 넣지 않는다(로그 유출 방지).
"""
import json
import urllib.error
import urllib.request

from django.conf import settings
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


def telegram_enabled() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN)


def push_enabled() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def telegram_send(chat_id: str, text: str) -> dict:
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": text}).encode(),
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
            ra = (body.get("parameters") or {}).get("retry_after")
            raise RetryLater(ra if isinstance(ra, int) else None, code) from None
        if code in (400, 401, 403, 404):
            raise Permanent(code) from None
        raise Temporary(code) from None
    except (OSError, ValueError, KeyError):  # URLError·timeout·깨진 응답
        raise Temporary() from None


def telegram_check(chat_id: str) -> str:
    return telegram_send(chat_id, "[테스트] 당번 알림 연결 확인")["chat"]["type"]


def push_send(sub, title: str, body: str, url: str, ttl: int) -> None:
    try:
        webpush(
            subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
            data=json.dumps({"title": title, "body": body, "url": url}, ensure_ascii=False),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            timeout=10,
            ttl=ttl,
        )
    except WebPushException as e:
        resp = e.response
        code = getattr(resp, "status_code", None)
        if code in (404, 410):
            raise Gone(code) from None
        if code in (429, 503):
            try:
                secs = int(resp.headers.get("Retry-After"))
            except (TypeError, ValueError):
                secs = None
            raise RetryLater(secs, code) from None
        # 401/403은 VAPID 키·설정 오류일 가능성 → 운영자가 고치면 되므로 재시도
        if code is not None and 400 <= code < 500 and code not in (401, 403):
            raise Permanent(code) from None
        raise Temporary(code) from None
    except OSError:  # requests 예외 포함(ConnectionError·Timeout)
        raise Temporary() from None
