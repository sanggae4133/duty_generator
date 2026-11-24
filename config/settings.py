import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.utils.log import DEFAULT_LOGGING

from duty.logging import LOG_DATEFMT, LOG_FORMAT

from .site_url import validate_site_url

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path) -> None:
    """KEY=VALUE 줄을 환경변수로. 빈 줄·# 주석은 건너뛰고 값 앞뒤 공백을 지운다(따옴표 처리 없음).
    이미 있는 환경변수가 이긴다. 파일이 없으면 아무것도 안 한다."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip())


# 설정값은 저장소 루트의 .env(.env.example 참고). DUTY_ENV_FILE="" 이면 읽지 않는다(테스트).
_env_file = os.environ.get("DUTY_ENV_FILE", str(BASE_DIR / ".env"))
if _env_file:
    load_env_file(_env_file)
env = os.environ.get

DEBUG = env("DUTY_DEBUG", "0") == "1"
SECRET_KEY = env("DUTY_SECRET_KEY") or ("dev-insecure-key" if DEBUG else "")
if not SECRET_KEY:
    raise RuntimeError("DUTY_SECRET_KEY 가 필요합니다(.env).")

ALLOWED_HOSTS = [h for h in (env("DUTY_ALLOWED_HOSTS") or "127.0.0.1,localhost").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in env("DUTY_CSRF_ORIGINS", "").split(",") if o]
ADMIN_PATH = (env("DUTY_ADMIN_PATH") or "admin").strip("/")
SITE_URL = validate_site_url(env("DUTY_SITE_URL", ""), DEBUG)  # 알림 링크·캘린더 구독 주소용(비면 생략)
HELP_VIDEO_DIR = BASE_DIR / "duty" / "help_videos"  # 권한별 사용법 영상(member/manager/admin.mp4, tools/help_videos 로 녹화)
REPO_URL = env("DUTY_REPO_URL", "https://github.com/sanggae4133/duty_generator").strip()  # 화면 아래 링크(일부러 비우면 숨김)
if REPO_URL and (not REPO_URL.startswith("https://") or any(c.isspace() or c in "\"'<>" for c in REPO_URL)):
    raise ImproperlyConfigured("DUTY_REPO_URL 은 https:// 로 시작하는 주소여야 합니다.")
if not ADMIN_PATH or (not DEBUG and ADMIN_PATH == "admin"):  # 운영은 짐작하기 어려운 주소를 꼭 정한다
    raise ImproperlyConfigured("DUTY_ADMIN_PATH 를 정하세요(운영은 admin 이 아닌 짐작하기 어려운 값).")

# 실행 중 생기는 파일은 전부 DATA_DIR 한 곳(DB·백업·로그·잠금). 상대 경로는 저장소 루트 기준.
# 서비스 사용자(duty)가 쓸 수 있어야 한다(SQLite WAL 도 이 폴더에 파일을 만든다).
DATA_DIR = BASE_DIR / (env("DUTY_DATA_DIR") or "data")
DB_PATH = DATA_DIR / "db.sqlite3"
BACKUP_DIR = DATA_DIR / "backups"
LOG_DIR = DATA_DIR / "logs"
ALARMS_LOCK_PATH = DATA_DIR / ".alarms.lock"  # run_worker 를 하나만 돌게
TELEGRAM_UPDATES_LOCK_PATH = DATA_DIR / ".telegram-updates.lock"  # [연결 확인]의 getUpdates 를 한 번에 하나만
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _int_setting(name: str, default: int, lo: int, hi: int) -> int:
    raw = env(name) or str(default)
    try:
        value = int(raw)
    except ValueError:
        value = None
    if value is None or not lo <= value <= hi:
        raise ImproperlyConfigured(f"{name} 는 {lo}~{hi} 사이 정수여야 합니다.")
    return value


BACKUP_HOUR = _int_setting("DUTY_BACKUP_HOUR", 3, 0, 23)  # 매일 이 시(0~23)에 run_worker 가 DB 백업
BACKUP_KEEP_DAYS = _int_setting("DUTY_BACKUP_KEEP_DAYS", 30, 1, 3650)
LOG_KEEP_DAYS = _int_setting("DUTY_LOG_KEEP_DAYS", 14, 1, 3650)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",
    "duty",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "duty.middleware.ForcePasswordChangeMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "duty.context.nav",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DB_PATH,
        # timeout: 쓰기 잠금을 기다리는 초(기본 5초를 넘기면 바로 500 "database is locked")
        "OPTIONS": {"init_command": "PRAGMA journal_mode=WAL;", "transaction_mode": "IMMEDIATE", "timeout": 20},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
if not DEBUG:
    # 운영: 정적 파일 이름에 해시를 붙여(whitenoise 가 그 파일에 1년 이상 immutable 캐시) 브라우저가 한 번 받으면 다시 묻지 않고,
    # 미리 압축(.gz)해 둔다. Funnel 은 새 연결·전송이 느려서(2026-11-19 측정 TLS 약 5초, 초당 20~40KB) 요청 수와 크기를 줄인다.
    # 업그레이드 때 collectstatic 이 해시 목록(staticfiles.json)을 만든다 — 빠뜨리면 화면이 500 이다(업그레이드 절차에 있다)
    STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "duty.User"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
SESSION_COOKIE_AGE = 90 * 24 * 3600  # 로그인할 때부터 90일. 요청마다 늘리지 않는다(SESSION_SAVE_EVERY_REQUEST 기본 False: 화면을 열 때 DB 쓰기 없음)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
# HTTPS 는 Funnel 이 맡지만, 브라우저가 http 로 시도하지 않게 HSTS 를 보낸다(nginx 가 X-Forwarded-Proto: https 로 덮어쓰고
# (deploy/duty-nginx.conf) gunicorn 이 127.0.0.1 의 그 헤더를 믿어 is_secure() 가 참일 때만 붙는다). SSL_REDIRECT 는 켜지 않는다(상태 점검이 http 로 부름)
SECURE_HSTS_SECONDS = 0 if DEBUG else 30 * 24 * 3600
# 클라이언트가 보낸 SCRIPT_NAME 헤더(gunicorn 은 127.0.0.1 에서 온 것을 믿는다)로 경로 앞부분을 바꾸지 못하게
FORCE_SCRIPT_NAME = ""
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000  # 출근표 표 저장: 260일 × 4칸

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
# 아이디 + 접속 IP 로 잠근다: 남이 아이디만 알아도 그 계정을 잠그던 것을 막는다(틀린 곳만 잠김).
# IP 는 Funnel·nginx 가 넘겨 준 실제 접속 IP(duty/client_ip.py). IP 하나만으로는 잠그지 않는다(사무실처럼 한 IP 를 여럿이 쓰면 전원 차단)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_CLIENT_IP_CALLABLE = "duty.client_ip.client_ip"
AXES_RESET_ON_SUCCESS = True
# 잠긴 동안의 시도로 잠금을 다시 15분 늘리거나 기록을 쌓지 않는다(피해자가 스스로 잠금을 늘리지 않게, DB 행 비대 방지)
AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT = False
AXES_LOCKOUT_TEMPLATE = "duty/locked.html"
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"  # 임시 비밀번호가 쿠키에 실리지 않게
# duty.* INFO 로그(예: "alarms tick:")를 stderr(→ journald)로. 웹·run_worker 는 시작할 때 data/logs/<web|worker>.log 도 붙인다
# (duty.logging.log_to_file). 기본 설정은 WARNING 이상만 찍는다.
# 캘린더 피드 경로(/calendar/<토큰>.ics)는 비밀이라 django.request·django.server 로그에서 지운다.
# django.server 는 로거를 다시 설정하면 기존 핸들러가 빠지므로 Django 기본 핸들러를 그대로 다시 단다.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"redact_calendar": {"()": "duty.logging.RedactCalendarFeed"}},
    "formatters": {
        "plain": {"format": LOG_FORMAT, "datefmt": LOG_DATEFMT},
        "django.server": DEFAULT_LOGGING["formatters"]["django.server"],
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        "django.server": DEFAULT_LOGGING["handlers"]["django.server"],
        "null": {"class": "logging.NullHandler"},
    },
    # 핸들러는 루트에만 단다: duty INFO 와 django.request·axes 경고가 모두 시각과 함께 한 번씩 찍힌다(caplog 도 루트에서 받음)
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "duty": {"level": "INFO"},
        "django": {"handlers": [], "level": "WARNING"},  # Django 기본 console(DEBUG 전용)·mail_admins 대신 루트 하나로
        "django.request": {"filters": ["redact_calendar"]},
        # 허용 안 된 Host 요청은 요청마다 트레이스백(Host 값 4번)을 남겨 디스크를 채울 수 있다 → 남기지 않는다(응답은 그대로 400)
        "django.security.DisallowedHost": {"handlers": ["null"], "propagate": False},
        "django.server": {**DEFAULT_LOGGING["loggers"]["django.server"], "filters": ["redact_calendar"]},
    },
}
