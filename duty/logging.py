"""로깅 필터. 캘린더 피드 경로에는 비밀 토큰이 들어 있어 로그에 남기지 않는다."""

import logging

FEED_PREFIX = "/calendar/"


class RedactCalendarFeed(logging.Filter):
    """django.request·django.server 레코드 중 피드 경로를 'calendar feed <상태코드>' 로 바꾼다."""

    def filter(self, record):
        path = getattr(getattr(record, "request", None), "path", None)
        hit = isinstance(path, str) and path.startswith(FEED_PREFIX)
        if not hit:
            try:
                hit = FEED_PREFIX in record.getMessage()
            except Exception:  # 형식이 깨진 레코드는 그대로 둔다
                hit = False
        if hit:
            status = getattr(record, "status_code", None)
            if status is None and isinstance(record.args, tuple) and len(record.args) > 1:
                status = record.args[1]
            record.msg, record.args = "calendar feed %s", (status,)
            if hasattr(record, "request"):
                del record.request
        return True
