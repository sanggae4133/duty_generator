import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.utils.log import DEFAULT_LOGGING

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

ALLOWED_HOSTS = [h for h in env("DUTY_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in env("DUTY_CSRF_ORIGINS", "").split(",") if o]
ADMIN_PATH = env("DUTY_ADMIN_PATH", "admin").strip("/")
TELEGRAM_BOT_TOKEN = env("DUTY_TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME = env("DUTY_TELEGRAM_BOT_USERNAME", "").lstrip("@")
DB_PATH = env("DUTY_DB_PATH", str(BASE_DIR / "db.sqlite3"))
LOCK_DIR = Path(DB_PATH).parent  # SQLite WAL 때문에 서비스 사용자가 반드시 쓸 수 있는 폴더
TELEGRAM_UPDATES_LOCK_PATH = env("DUTY_TELEGRAM_LOCK", str(LOCK_DIR / ".telegram-updates.lock"))
VAPID_PUBLIC_KEY = env("DUTY_VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = env("DUTY_VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = env("DUTY_VAPID_SUBJECT", "mailto:admin@localhost")
SITE_URL = validate_site_url(env("DUTY_SITE_URL", ""), DEBUG)  # 알림 링크·캘린더 구독 주소용(비면 생략)
ALARMS_LOCK_PATH = env("DUTY_ALARMS_LOCK", str(LOCK_DIR / ".alarms.lock"))
if not ADMIN_PATH:
    raise ImproperlyConfigured("DUTY_ADMIN_PATH 가 비어 있을 수 없습니다.")

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
        "OPTIONS": {"init_command": "PRAGMA journal_mode=WAL;", "transaction_mode": "IMMEDIATE"},
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
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "duty.User"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
SESSION_COOKIE_AGE = 14 * 24 * 3600
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000  # 출근표 표 저장: 260일 × 4칸

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = ["username"]  # Funnel 뒤에서는 모든 요청 IP가 127.0.0.1 이라 IP 잠금은 전원 차단이 된다
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "duty/locked.html"
SILENCED_SYSTEM_CHECKS = ["axes.W006"]  # 잠금은 의도적으로 username 만 기준(IP 는 Funnel 뒤에서 전원 동일)
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"  # 임시 비밀번호가 쿠키에 실리지 않게
# duty.* INFO 로그(예: "alarms tick:")를 stderr로 → systemd 가 /var/log/duty_generator/*.log 에 붙인다. 기본 설정은 WARNING 이상만 찍는다.
# 캘린더 피드 경로(/calendar/<토큰>.ics)는 비밀이라 django.request·django.server 로그에서 지운다.
# django.server 는 로거를 다시 설정하면 기존 핸들러가 빠지므로 Django 기본 핸들러를 그대로 다시 단다.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"redact_calendar": {"()": "duty.logging.RedactCalendarFeed"}},
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s", "datefmt": "%Y-%m-%d %H:%M:%S"},
        "django.server": DEFAULT_LOGGING["formatters"]["django.server"],
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        "django.server": DEFAULT_LOGGING["handlers"]["django.server"],
    },
    # 핸들러는 루트에만 단다: duty INFO 와 django.request·axes 경고가 모두 시각과 함께 한 번씩 찍힌다(caplog 도 루트에서 받음)
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "duty": {"level": "INFO"},
        "django": {"handlers": [], "level": "WARNING"},  # Django 기본 console(DEBUG 전용)·mail_admins 대신 루트 하나로
        "django.request": {"filters": ["redact_calendar"]},
        "django.server": {**DEFAULT_LOGGING["loggers"]["django.server"], "filters": ["redact_calendar"]},
    },
}
