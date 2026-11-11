from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def validate_site_url(url: str, debug: bool) -> str:
    """DUTY_SITE_URL 검증(비면 통과). 피드 주소·알림 링크의 기준이 된다."""
    if not url:
        return url
    schemes = {"https", "http"} if debug else {"https"}
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url) or "?" in url or "#" in url:
        raise ImproperlyConfigured("DUTY_SITE_URL 에 공백·제어문자·query·fragment 를 쓸 수 없습니다.")
    parts = urlsplit(url)
    try:
        parts.port  # 숫자가 아니거나 범위 밖이면 ValueError
    except ValueError:
        raise ImproperlyConfigured("DUTY_SITE_URL 의 포트가 올바르지 않습니다.") from None
    if parts.username is not None or parts.password is not None:
        raise ImproperlyConfigured("DUTY_SITE_URL 에 사용자 정보(user@)를 넣을 수 없습니다.")
    if parts.scheme not in schemes or not parts.hostname:
        raise ImproperlyConfigured("DUTY_SITE_URL 은 https://호스트 형식이어야 합니다(DEBUG 에서는 http 허용).")
    if parts.path not in ("", "/"):
        raise ImproperlyConfigured("DUTY_SITE_URL 은 경로 없이 https://호스트[:포트] 만 쓸 수 있습니다.")
    return url
