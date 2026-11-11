import pytest
from datetime import date
from django.db import IntegrityError, transaction
from django.utils import timezone

from duty.models import AlarmDelivery, AlarmRule, PushAlarmSubscription, TelegramAlarmProfile, User
from duty.errors import DutyError
from duty.services import alarms

BASE = dict(kind="personal", timing="days", offset=1, at_minute=1080, telegram=True, push=False, shifts=["dawn"])


@pytest.fixture
def user(db):
    return User.objects.create_user("alarm-u", password="x", name="알림")


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


def _delivery(r, **kw):
    return AlarmDelivery.objects.create(**{**dict(rule=r, date=date(2026, 11, 9), cell="dawn", channel="telegram",
                                                  destination="1", status="sent", content_hash="h"), **kw})


def test_delivery_constraints(user):
    r = _rule(user)
    d = _delivery(r)
    assert d.attempts == 0 and d.next_attempt_at is None and d.updated_at
    _bad(lambda: _delivery(r))
    _delivery(r, destination="2")  # 목적지가 다르면 허용
    _bad(lambda: _delivery(r, channel="sms", cell="normal"))
    _bad(lambda: _delivery(r, cell="lunch"))
    _bad(lambda: _delivery(r, cell="normal", status="x"))
    _bad(lambda: _delivery(r, cell="normal", attempts=-1))
    _delivery(r, cell="report", status="failed", attempts=1, next_attempt_at=timezone.now())


def test_push_endpoint_unique(user):
    PushAlarmSubscription.objects.create(user=user, endpoint="e", p256dh="p", auth="a")
    _bad(lambda: PushAlarmSubscription.objects.create(user=user, endpoint="e", p256dh="p", auth="a"))


def test_cascade(user):
    TelegramAlarmProfile.objects.create(user=user, chat_id="1")
    PushAlarmSubscription.objects.create(user=user, endpoint="e", p256dh="p", auth="a")
    r = _rule(user)
    _delivery(r, channel="push")
    r.delete()
    assert AlarmDelivery.objects.count() == 0
    r = _rule(user)
    _delivery(r, channel="push")
    user.delete()
    assert not (TelegramAlarmProfile.objects.exists() or PushAlarmSubscription.objects.exists()
                or AlarmRule.objects.exists() or AlarmDelivery.objects.exists())


def test_normalize(depts):
    assert alarms.normalize("report", ["night", "dawn"], ["UI", "MEMS"], ["개발자", "직원"]) == (["dawn", "night"], ["MEMS", "UI"], [])
    assert alarms.normalize("report", ["dawn", "normal", "dinner", "night", "slots"], list(depts), []) == ([], [], [])
    assert alarms.normalize("personal", ["dawn"], ["MEMS"], ["직원"]) == (["dawn"], [], [])


def test_create_defaults(db):
    u = User.objects.create_user("fresh", password="x", name="새")
    assert not AlarmRule.objects.exists()  # 계정 생성만으로는 안 생긴다(최초 발급 때 issue_account 가 만든다)
    alarms.create_defaults(u)
    rules = list(AlarmRule.objects.filter(user=u))
    assert [(r.timing, r.offset, r.at_minute) for r in rules] == [("days", 1, 1080), ("before_start", 120, 0)]
    assert all(r.telegram and not r.push and r.shifts == ["dawn", "dinner", "night"] for r in rules)
    alarms.create_defaults(u)
    assert AlarmRule.objects.filter(user=u).count() == 2


@pytest.mark.parametrize("kw", [
    dict(timing="before_start", offset=1, at_minute=0), dict(timing="before_start", offset=10080, at_minute=0),
    dict(timing="days", offset=0), dict(timing="days", offset=30),
    dict(timing="bizdays", offset=1), dict(timing="bizdays", offset=30),
    dict(at_minute=0), dict(at_minute=1439),
])
def test_rule_allowed_boundaries(user, kw):
    _rule(user, **kw)


def test_normalize_rejects_unknown(depts):
    for args in [(["x"], [], []), ([], ["ZZ"], []), ([], [], ["외계인"])]:
        with pytest.raises(DutyError, match="알 수 없는 값"):
            alarms.normalize("report", *args)
    for args in [(["x"], [], []), (["dawn"], ["UNKNOWN"], []), (["dawn"], [], ["UNKNOWN"])]:
        with pytest.raises(DutyError, match="알 수 없는 값"):
            alarms.normalize("personal", *args)
