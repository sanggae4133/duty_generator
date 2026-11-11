import os

import django.core.validators
from django.db import migrations, models

OLD_ENV = ("DUTY_TELEGRAM_BOT_TOKEN", "DUTY_TELEGRAM_BOT_USERNAME", "DUTY_VAPID_PUBLIC_KEY", "DUTY_VAPID_PRIVATE_KEY",
           "DUTY_VAPID_SUBJECT", "DUTY_OPS_CHAT_ID")


def seed_from_env(apps, schema_editor):
    """예전에 환경변수(.env)로 주던 알림 설정이 있으면 그 값으로 행을 만든다(시험 서버 이전용, 1회)."""
    env = {k: os.environ.get(k, "").strip() for k in OLD_ENV}
    if not any(env.values()):
        return
    chat = env["DUTY_OPS_CHAT_ID"]
    apps.get_model("duty", "AlarmSettings").objects.update_or_create(pk=1, defaults=dict(
        telegram_bot_token=env["DUTY_TELEGRAM_BOT_TOKEN"],
        telegram_bot_username=env["DUTY_TELEGRAM_BOT_USERNAME"].lstrip("@"),
        vapid_public_key=env["DUTY_VAPID_PUBLIC_KEY"],
        vapid_private_key=env["DUTY_VAPID_PRIVATE_KEY"],
        vapid_subject=env["DUTY_VAPID_SUBJECT"] or "mailto:admin@localhost",
        ops_chat_id=int(chat) if chat.isascii() and chat.isdigit() and 1 <= int(chat) <= 2**63 - 1 else None,
    ))


class Migration(migrations.Migration):

    dependencies = [
        ('duty', '0001_v2'),
    ]

    operations = [
        migrations.CreateModel(
            name='AlarmSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('telegram_bot_token', models.CharField(blank=True, max_length=200, validators=[django.core.validators.RegexValidator('^\\d+:[A-Za-z0-9_-]+$', '봇 토큰 형식이 아닙니다(숫자:영문·숫자).')], verbose_name='텔레그램 봇 토큰')),
                ('telegram_bot_username', models.CharField(blank=True, help_text='@ 없이(붙여도 저장할 때 뗀다).', max_length=33, validators=[django.core.validators.RegexValidator('^@?[A-Za-z0-9_]{5,32}$', '봇 사용자명은 영문·숫자·_ 5~32자입니다.')], verbose_name='텔레그램 봇 사용자명')),
                ('ops_chat_id', models.PositiveBigIntegerField(blank=True, help_text='관리자 개인 텔레그램 chat_id(숫자). 비우면 장애 알림은 health.log 에만 남는다.', null=True, validators=[django.core.validators.MinValueValidator(1)], verbose_name='장애 알림 받을 chat_id')),
                ('vapid_public_key', models.CharField(blank=True, max_length=200, verbose_name='웹 푸시 공개키')),
                ('vapid_private_key', models.CharField(blank=True, max_length=200, verbose_name='웹 푸시 개인키')),
                ('vapid_subject', models.CharField(default='mailto:admin@localhost', help_text='mailto:주소 형식. 푸시 서비스가 문제 시 연락하는 주소.', max_length=200, verbose_name='웹 푸시 연락처')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='고친 시각')),
            ],
            options={
                'verbose_name': '알림 설정',
                'verbose_name_plural': '알림 설정',
                'constraints': [models.CheckConstraint(condition=models.Q(('pk', 1)), name='alarmsettings_single_row')],
            },
        ),
        migrations.RunPython(seed_from_env, migrations.RunPython.noop),
    ]
