from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_save


def _default_alarms(sender, instance, created, raw=False, **kw):
    if created and not raw:
        from .services import alarms
        alarms.create_defaults(instance)


class DutyConfig(AppConfig):
    name = "duty"
    verbose_name = "당번표"

    def ready(self):
        post_save.connect(_default_alarms, sender=settings.AUTH_USER_MODEL, dispatch_uid="duty_default_alarms")
