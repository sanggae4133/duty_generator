import os

os.environ.setdefault("DUTY_DEBUG", "1")
os.environ.setdefault("DUTY_SECRET_KEY", "test-secret")
os.environ.setdefault("DUTY_API_TOKEN", "test-token")

from .settings import *  # noqa: E402,F401,F403

WHITENOISE_USE_FINDERS = True  # staticfiles/ 디렉터리 없이 테스트
WHITENOISE_AUTOREFRESH = True
