import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
env = os.environ.get

DEBUG = env("DUTY_DEBUG", "0") == "1"
SECRET_KEY = env("DUTY_SECRET_KEY") or ("dev-insecure-key" if DEBUG else "")
if not SECRET_KEY:
    raise RuntimeError("DUTY_SECRET_KEY 환경변수가 필요합니다.")

ALLOWED_HOSTS = [h for h in env("DUTY_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in env("DUTY_CSRF_ORIGINS", "").split(",") if o]
API_TOKEN = env("DUTY_API_TOKEN", "")
ADMIN_PATH = env("DUTY_ADMIN_PATH", "admin").strip("/")
TELEGRAM_BOT_TOKEN = env("DUTY_TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME = env("DUTY_TELEGRAM_BOT_USERNAME", "").lstrip("@")
TELEGRAM_UPDATES_LOCK_PATH = env("DUTY_TELEGRAM_LOCK", str(BASE_DIR / ".telegram-updates.lock"))
VAPID_PUBLIC_KEY = env("DUTY_VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = env("DUTY_VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = env("DUTY_VAPID_SUBJECT", "mailto:admin@localhost")
SITE_URL = env("DUTY_SITE_URL", "")  # 텔레그램 알림의 절대 링크용(비면 생략)
ALARMS_LOCK_PATH = env("DUTY_ALARMS_LOCK", str(BASE_DIR / ".alarms.lock"))
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
        "NAME": env("DUTY_DB_PATH", str(BASE_DIR / "db.sqlite3")),
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
# duty.* INFO 로그(예: "alarms tick:")를 stderr로 → systemd journal. 기본 설정은 WARNING 이상만 찍는다.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"duty": {"handlers": ["console"], "level": "INFO"}},
}
