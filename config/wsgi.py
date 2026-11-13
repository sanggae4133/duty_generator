import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()

from django.urls import reverse  # noqa: E402  (설정을 읽은 뒤)

from duty.guard import RequestGuard  # noqa: E402
from duty.logging import log_to_file  # noqa: E402

log_to_file("web")
# 본문 크기·수신 마감, 비밀번호 확인 POST 동시 개수 제한(duty/guard.py)
application = RequestGuard(application, login_paths={reverse("login"), reverse("admin:login"),
                                                      reverse("password_change")})
