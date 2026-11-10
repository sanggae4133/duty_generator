import pytest
from datetime import date
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from duty.models import AlarmRule, AlarmSent, PushAlarmSubscription, TelegramAlarmProfile, Department
from duty.services import alarms

BASE = dict(kind="personal", timing="days", offset=1, at_minute=1080, telegram=True, push=False, shifts=["dawn"])


@pytest.fixture
def user(db):
    u = User.objects.create_user("alarm-u", password="x")
    AlarmRule.objects.filter(user=u).delete()
    return u


def _bad(fn):
    with pytest.raises(IntegrityError), transaction.atomic():
        fn()


def _rule(user, **kw):
    return AlarmRule.objects.create(user=user, **{**BASE, **kw})


@pytest.mark.parametrize("kw", [
    dict(kind="x"), dict(timing="x"),
    dict(timing="before_start", offset=0, at_minute=0), dict(timing="before_start", offset=10081, at_minute=0),
    dict(timing="days", offset=-1), dict(timing="days", offset=31),
    dict(timing="bizdays", offset=0), dict(timing="bizdays", offset=31),
    dict(at_minute=-1), dict(at_minute=1440),
    dict(timing="before_start", offset=10, at_minute=60),
    dict(telegram=False, push=False),
    dict(depts=["MEMS"]), dict(types=["직원"]),
])
def test_rule_constraints(user, kw):
    _bad(lambda: _rule(user, **kw))


def test_rule_unique_even_if_channel_differs(user):
    _rule(user)
    _bad(lambda: _rule(user, telegram=False, push=True))


def test_report_allows_filters(user):
    _rule(user, kind="report", depts=["MEMS"], types=["직원"])


def test_sent_constraints(user):
    r = _rule(user)
    mk = lambda **kw: AlarmSent.objects.create(**{**dict(rule=r, date=date(2026, 11, 9), cell="dawn", channel="telegram",
                                                         content_hash="h", sent_at=timezone.now()), **kw})
    mk()
    _bad(mk)
    _bad(lambda: mk(channel="sms", cell="normal"))
    _bad(lambda: mk(cell="lunch"))
    mk(cell="report")


def test_push_endpoint_unique(user):
    PushAlarmSubscription.objects.create(user=user, endpoint="e", p256dh="p", auth="a")
    _bad(lambda: PushAlarmSubscription.objects.create(user=user, endpoint="e", p256dh="p", auth="a"))


def test_cascade(user):
    TelegramAlarmProfile.objects.create(user=user, chat_id="1")
    PushAlarmSubscription.objects.create(user=user, endpoint="e", p256dh="p", auth="a")
    r = _rule(user)
    AlarmSent.objects.create(rule=r, date=date(2026, 11, 9), cell="dawn", channel="push", content_hash="h", sent_at=timezone.now())
    r.delete()
    assert AlarmSent.objects.count() == 0
    r = _rule(user)
    AlarmSent.objects.create(rule=r, date=date(2026, 11, 9), cell="dawn", channel="push", content_hash="h", sent_at=timezone.now())
    user.delete()
    assert not (TelegramAlarmProfile.objects.exists() or PushAlarmSubscription.objects.exists()
                or AlarmRule.objects.exists() or AlarmSent.objects.exists())


def test_normalize(depts):
    assert alarms.normalize("report", ["night", "dawn", "x"], ["UI", "MEMS", "ZZ"], ["개발자", "직원"]) == (["dawn", "night"], ["MEMS", "UI"], [])
    assert alarms.normalize("report", ["dawn", "normal", "dinner", "night", "slots"], list(depts), []) == ([], [], [])
    assert alarms.normalize("personal", ["dawn"], ["MEMS"], ["직원"]) == (["dawn"], [], [])


def test_new_user_gets_default_rules(db):
    u = User.objects.create_user("fresh", password="x")
    rules = list(AlarmRule.objects.filter(user=u))
    assert [(r.timing, r.offset, r.at_minute) for r in rules] == [("days", 1, 1080), ("before_start", 120, 0)]
    assert all(r.telegram and not r.push and r.shifts == ["dawn", "dinner", "night"] for r in rules)
    alarms.create_defaults(u)
    assert AlarmRule.objects.filter(user=u).count() == 2


def test_data_migration_only_for_users_without_rules(user):
    import importlib
    from django.apps import apps
    from django.db import connection
    mod = importlib.import_module("duty.migrations.0007_default_alarm_rules")
    mod.add_defaults(apps, connection.schema_editor())  # user: 규칙 없음 → 2개
    other = User.objects.create_user("has-rules", password="x")  # 신호로 이미 2개
    mod.add_defaults(apps, None)
    assert AlarmRule.objects.filter(user=user).count() == 2
    assert AlarmRule.objects.filter(user=other).count() == 2
