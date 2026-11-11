"""알림 설정(AlarmSettings, 한 행) 읽기·저장. 토큰·개인키는 로그·메시지에 넣지 않는다."""
import logging

from django.db import transaction

from ..models import AlarmSettings, PushAlarmSubscription, TelegramAlarmProfile

log = logging.getLogger(__name__)


def current() -> AlarmSettings:
    return AlarmSettings.objects.get_or_create(pk=1)[0]


def _new_push_keys() -> tuple[str, str]:
    """(공개키, 개인키) base64url. pywebpush 가 vapid_private_key 로 받는 형식."""
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from py_vapid import Vapid01, b64urlencode
    v = Vapid01()
    v.generate_keys()
    return (b64urlencode(v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)),
            b64urlencode(v.private_key.private_numbers().private_value.to_bytes(32, "big")))


def ensure_push_keys() -> AlarmSettings:
    """푸시 키가 비어 있으면 만들어 저장한다. 실패하면 키 없이 돌려준다(push_on False)."""
    s = current()
    if s.push_on:
        return s
    try:
        pub, priv = _new_push_keys()
    except Exception:
        log.exception("push key generation failed")
        return s
    with transaction.atomic():  # IMMEDIATE: 다시 읽어 그사이 다른 요청이 만든 키가 있으면 그것을 쓴다
        s = AlarmSettings.objects.get(pk=1)
        if not s.push_on:
            s.vapid_public_key, s.vapid_private_key = pub, priv
            s.save(update_fields=["vapid_public_key", "vapid_private_key", "updated_at"])
    return s


def save(obj: AlarmSettings, regenerate_push_keys: bool = False) -> int:
    """관리 화면 저장. 봇(토큰·사용자명)이 바뀌면 모든 사용자의 텔레그램 확인·연결 대기 코드를 비운다
    (새 봇에서 [시작]을 다시 눌러야 함). 푸시 키를 다시 만들면 모든 기기 구독을 지운다.
    돌려주는 값: 텔레그램 확인을 초기화한 사용자 수."""
    with transaction.atomic():
        old = AlarmSettings.objects.filter(pk=1).first() or AlarmSettings()
        if regenerate_push_keys:
            obj.vapid_public_key, obj.vapid_private_key = _new_push_keys()
            PushAlarmSubscription.objects.all().delete()
        obj.save()
        if (old.telegram_bot_token, old.telegram_bot_username) == (obj.telegram_bot_token, obj.telegram_bot_username):
            return 0
        reset = TelegramAlarmProfile.objects.exclude(verified_at=None, link_code=None)
        return reset.update(verified_at=None, link_code=None, link_expires_at=None)
