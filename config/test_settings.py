import os

os.environ["DUTY_ENV_FILE"] = ""  # 개발자의 .env 를 읽지 않는다
os.environ.setdefault("DUTY_DEBUG", "1")
os.environ.setdefault("DUTY_SECRET_KEY", "test-secret")

from .settings import *  # noqa: E402,F401,F403

WHITENOISE_USE_FINDERS = True  # staticfiles/ 디렉터리 없이 테스트
WHITENOISE_AUTOREFRESH = True
