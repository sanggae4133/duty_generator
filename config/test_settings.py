import atexit
import os
import shutil
import tempfile

os.environ["DUTY_ENV_FILE"] = ""  # 개발자의 .env 를 읽지 않는다
# 저장소 data/(개발 DB·백업)를 만들지도 쓰지도 않게 임시 폴더로. 프로세스가 끝나면 지운다
_data_dir = tempfile.mkdtemp(prefix="duty-test-")
atexit.register(shutil.rmtree, _data_dir, ignore_errors=True)
os.environ["DUTY_DATA_DIR"] = _data_dir
os.environ.setdefault("DUTY_DEBUG", "1")
os.environ.setdefault("DUTY_SECRET_KEY", "test-secret")

from .settings import *  # noqa: E402,F401,F403

WHITENOISE_USE_FINDERS = True  # staticfiles/ 디렉터리 없이 테스트
WHITENOISE_AUTOREFRESH = True

# 테스트에서는 빠른 해시를 쓴다(운영의 PBKDF2 100만 회는 계정을 만들거나 로그인할 때마다 0.5초씩 걸려 전체 테스트 시간의 대부분이었다).
# 운영 설정(config/settings.py)은 그대로다
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
