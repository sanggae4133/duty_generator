import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()

from duty.logging import log_to_file  # noqa: E402  (설정을 읽은 뒤)

log_to_file("web")
