"""로깅 필터. 캘린더 피드 경로에는 비밀 토큰이 들어 있어 로그에 남기지 않는다."""

import logging
import re
from urllib.parse import unquote

FEED_PREFIX = "/calendar/"
# 요청 줄('GET /calendar/...', "Bad request syntax ('GET /calendar/...")에서 경로가 /calendar/로 시작할 때만
FEED_LINE = re.compile(r"\b[A-Z]+ (?:[a-z][a-z0-9+.-]*://[^/\s]*)?/calendar/")


class RedactCalendarFeed(logging.Filter):
    """django.request·django.server 레코드 중 피드 경로를 'calendar feed <상태코드>' 로 바꾼다."""

    def filter(self, record):
        path = getattr(getattr(record, "request", None), "path", None)
        hit = isinstance(path, str) and path.startswith(FEED_PREFIX)
        if not hit:
            try:
                hit = bool(FEED_LINE.search(unquote(record.getMessage())))
            except Exception:  # 형식이 깨진 레코드는 그대로 둔다
                hit = False
        if hit:
            status = getattr(record, "status_code", None)
            if status is None and isinstance(record.args, tuple) and len(record.args) > 1:
                status = record.args[1]  # django.server: (요청 줄, 상태, 크기)
            # 상태 자리에 요청 줄이 든 메시지가 올 수 있다(runserver "code %d, message %s"). 세 자리 숫자만 남긴다
            status = str(status) if re.fullmatch(r"\d{3}", str(status)) else "?"
            record.msg, record.args = f"calendar feed {status}", ()
            if hasattr(record, "request"):
                del record.request
        return True
