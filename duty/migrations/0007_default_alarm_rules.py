from django.conf import settings
from django.db import migrations

# services/alarms.DEFAULT_RULES 와 같은 값(마이그레이션은 시점 고정이라 복사)
DEFAULT_RULES = [
    dict(kind="personal", timing="days", offset=1, at_minute=18 * 60, telegram=True, push=False, shifts=["dawn", "dinner", "night"]),
    dict(kind="personal", timing="before_start", offset=120, at_minute=0, telegram=True, push=False, shifts=["dawn", "dinner", "night"]),
]


def add_defaults(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    AlarmRule = apps.get_model("duty", "AlarmRule")
    for u in User.objects.exclude(alarm_rules__isnull=False):
        AlarmRule.objects.bulk_create([AlarmRule(user=u, **r) for r in DEFAULT_RULES])


class Migration(migrations.Migration):
    dependencies = [("duty", "0006_alarms")]
    operations = [migrations.RunPython(add_defaults, migrations.RunPython.noop)]
