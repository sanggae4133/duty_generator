"""로깅: 형식·파일 핸들러·캘린더 피드 경로 지우기(피드 경로에는 비밀 토큰이 들어 있어 로그에 남기지 않는다)."""

import logging
import logging.handlers
import re
from urllib.parse import unquote

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"
LOG_MAX_BYTES = 50 * 1024 * 1024  # 하루 파일 하나의 상한. 넘으면 자정까지 버린다(디스크가 차지 않게)


class CappedFileHandler(logging.handlers.TimedRotatingFileHandler):
    """자정마다 새 파일 + 하루 파일이 max_bytes 를 넘으면 그날은 안내 한 줄만 남기고 버린다."""

    def __init__(self, path, max_bytes=LOG_MAX_BYTES, **kw):
        super().__init__(path, when="midnight", encoding="utf-8", **kw)
        self.max_bytes, self.capped = max_bytes, False

    def emit(self, record):
        full = self.stream is not None and self.stream.tell() >= self.max_bytes and not self.shouldRollover(record)
        if not full:
            self.capped = False
        elif self.capped:
            return
        else:
            self.capped = True
            record = logging.makeLogRecord({"name": __name__, "levelno": logging.ERROR, "levelname": "ERROR",
                                            "msg": "로그가 너무 많아 오늘은 더 남기지 않습니다(자정에 다시 남김)"})
        super().emit(record)


def log_to_file(name: str) -> None:
    """루트 로거에 data/logs/<name>.log 를 붙인다(자정마다 새 파일, LOG_KEEP_DAYS 일 보관). 프로세스마다 한 번.
    한 파일은 한 프로세스만 쓴다(웹은 gunicorn --workers 1, 작업자는 run_worker 하나) — 회전이 꼬이지 않게."""
    from django.conf import settings
    root = logging.getLogger()
    path = settings.LOG_DIR / f"{name}.log"
    if any(getattr(h, "baseFilename", None) == str(path) for h in root.handlers):
        return
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
    h = CappedFileHandler(path, backupCount=settings.LOG_KEEP_DAYS)
    h.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATEFMT))
    root.addHandler(h)

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
