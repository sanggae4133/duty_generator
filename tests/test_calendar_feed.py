import hashlib
import logging
from datetime import date, datetime, timedelta
from datetime import timezone as dt_tz

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, RequestFactory

from config.site_url import validate_site_url
from duty.errors import DutyError
from duty.logging import RedactCalendarFeed
from duty.models import CalendarFeed, ChangeLog, Commute, ControlDuty, Period, User
from duty.services import calendar

S = Period.Status
TODAY = date(2026, 11, 11)
D = date(2026, 11, 12)
SITE = "https://duty.example"
PUB_AT = datetime(2026, 11, 1, 3, 0, tzinfo=dt_tz.utc)


@pytest.fixture
def env(settings, fixed_today):
    settings.SITE_URL = SITE
    fixed_today(TODAY)
    return settings


@pytest.fixture
def me(env, make_member):
    return make_member("가상일", user=True)


def period(d=D, status=S.PUBLISHED, at=PUB_AT, end=None):
    return Period.objects.create(name="p", start_date=d, end_date=end or d, status=status, published_at=at)


def commute(p, member, shift="dawn", d=None):
    return Commute.objects.create(period=p, date=d or p.start_date, member=member, shift=shift)


def issue(user):
    url = calendar.issue(user)
    token = url.rsplit("/", 1)[1].removesuffix(".ics")
    return url, token


def path(token):
    return f"/calendar/{token}.ics"


def feed(client, token, method="get", **extra):
    return getattr(client, method)(path(token), **extra)


def vevents(resp):
    text = resp.content.decode().replace("\r\n ", "")
    blocks = text.split("BEGIN:VEVENT\r\n")[1:]
    return [dict(line.split(":", 1) for line in b.split("END:VEVENT")[0].strip().split("\r\n")) for b in blocks]


# --- 발급 서비스 ---

def test_issue_returns_site_url_and_stores_hash_only(client, me):
    url, token = issue(me)
    assert url == f"{SITE}/calendar/{token}.ics"
    assert len(token) == 43
    row = CalendarFeed.objects.get(user=me)
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(CalendarFeed.objects.values().get())
    assert feed(client, token).status_code == 200


def test_issue_trailing_slash_site(env, me):
    env.SITE_URL = SITE + "/"
    url, _ = issue(me)
    assert url.startswith(f"{SITE}/calendar/")


def test_reissue_invalidates_old_and_updates_issued_at(client, me):
    _, old = issue(me)
    CalendarFeed.objects.update(issued_at=PUB_AT)
    _, new = issue(me)
    assert CalendarFeed.objects.count() == 1
    assert CalendarFeed.objects.get().issued_at > PUB_AT
    assert feed(client, old).status_code == 404
    assert feed(client, new).status_code == 200


def test_revoke(client, me):
    _, token = issue(me)
    calendar.revoke(me)
    calendar.revoke(me)  # 없어도 오류 없음
    assert not CalendarFeed.objects.exists()
    assert feed(client, token).status_code == 404


def test_issue_requires_department(env, db):
    user = User.objects.create_user("nomember", password="unused-Pw-123", name="관리2")
    with pytest.raises(DutyError, match="근무표 대상 계정만 쓸 수 있습니다"):
        calendar.issue(user)
    assert not CalendarFeed.objects.exists()


def test_issue_requires_site_url(env, me):
    env.SITE_URL = ""
    with pytest.raises(DutyError, match="DUTY_SITE_URL"):
        calendar.issue(me)
    assert not CalendarFeed.objects.exists()


# --- 피드 접근 ---

@pytest.mark.parametrize("token", ["a" * 42, "a" * 44, "a" * 21 + "." + "a" * 21, "가" + "a" * 42])
def test_malformed_token_404(client, me, token):
    issue(me)
    assert feed(client, token).status_code == 404


def test_no_login_and_must_change_password_ok(client, me):
    _, token = issue(me)
    assert feed(client, token).status_code == 200
    me.must_change_password = True
    me.save()
    client.force_login(me)
    r = feed(client, token)
    assert r.status_code == 200 and b"BEGIN:VCALENDAR" in r.content


def test_only_own_assignments(client, me, make_member):
    other = make_member("타인", user=True)
    p = period()
    commute(p, me, "normal")
    commute(p, other, "dinner")
    ControlDuty.objects.create(period=p, date=D, slot=1, member=me)
    ControlDuty.objects.create(period=p, date=D, slot=2, member=other)
    _, token = issue(me)
    evs = vevents(feed(client, token))
    assert [e["SUMMARY"] for e in evs] == ["정상 출근 08:00~17:00", "장중관제 09:30~10:30"]
    assert {e["UID"] for e in evs} == {f"20261112-normal-{me.pk}@duty-generator", f"20261112-slot1-{me.pk}@duty-generator"}


def test_dinner_summary(client, me):
    commute(period(), me, "dinner")
    _, token = issue(me)
    assert vevents(feed(client, token))[0]["SUMMARY"] == "석식교대 출근 09:00~18:00"


def test_times_in_utc(client, me):
    p = period()
    commute(p, me, "dawn")
    ControlDuty.objects.create(period=p, date=D, slot=1, member=me)
    _, token = issue(me)
    dawn, slot = vevents(feed(client, token))
    assert (dawn["DTSTART"], dawn["DTEND"]) == ("20261111T213000Z", "20261112T063000Z")
    assert (slot["DTSTART"], slot["DTEND"]) == ("20261112T003000Z", "20261112T013000Z")


def test_published_only_and_90_day_window(client, me):
    commute(period(status=S.GENERATED), me)
    edge = TODAY - timedelta(days=90)
    commute(period(edge), me)
    commute(period(edge - timedelta(days=1)), me)
    _, token = issue(me)
    evs = vevents(feed(client, token))
    assert [e["UID"].split("-")[0] for e in evs] == [edge.strftime("%Y%m%d")]


def test_window_moves_with_today_changes_etag(client, me, fixed_today):
    edge = TODAY - timedelta(days=90)
    commute(period(edge), me)
    _, token = issue(me)
    r1 = feed(client, token)
    assert len(vevents(r1)) == 1
    fixed_today(TODAY + timedelta(days=1))
    r2 = feed(client, token)
    assert vevents(r2) == [] and r2["ETag"] != r1["ETag"]


def test_dtstamp_is_latest_publish_or_change(client, me, make_member):
    p = period()
    commute(p, me, "normal")
    _, token = issue(me)
    r1 = feed(client, token)
    assert vevents(r1)[0]["DTSTAMP"] == "20261101T030000Z"
    other = make_member("교체자")
    ChangeLog.objects.create(period=p, date=D, cell="dinner", before=None, after=other)
    ChangeLog.objects.update(at=datetime(2026, 11, 5, 1, 2, 3, tzinfo=dt_tz.utc))
    r2 = feed(client, token)
    assert vevents(r2)[0]["DTSTAMP"] == "20261105T010203Z"
    assert r2["ETag"] != r1["ETag"]
    r3 = feed(client, token, HTTP_IF_NONE_MATCH=r1["ETag"])
    assert r3.status_code == 200


def test_period_without_published_at_excluded(client, me, caplog):
    p = period(at=None)
    commute(p, me)
    commute(period(D + timedelta(days=1)), me)
    _, token = issue(me)
    with caplog.at_level(logging.WARNING, logger="duty"):
        evs = vevents(feed(client, token))
    assert [e["UID"][:8] for e in evs] == ["20261113"]
    warn = [r.getMessage() for r in caplog.records if r.name.startswith("duty")]
    assert warn and str(p.pk) in warn[0] and "가상일" not in warn[0]


@pytest.mark.parametrize("case", ["inactive", "no_department"])
def test_inactive_or_no_department_gives_empty_calendar(client, me, case):
    commute(period(), me)
    _, token = issue(me)
    r1 = feed(client, token)
    assert len(vevents(r1)) == 1
    if case == "inactive":
        me.is_active = False
    else:
        me.department, me.type = None, ""
    me.save()
    r2 = feed(client, token)
    assert r2.status_code == 200 and b"BEGIN:VCALENDAR" in r2.content
    assert vevents(r2) == [] and r2["ETag"] != r1["ETag"]


def test_member_rename_keeps_uid(client, me):
    commute(period(), me)
    _, token = issue(me)
    uid = vevents(feed(client, token))[0]["UID"]
    me.name = "새이름"
    me.save()
    assert [e["UID"] for e in vevents(feed(client, token))] == [uid]


def test_url_and_description_with_site_url(client, me, env):
    commute(period(), me)
    _, token = issue(me)
    ev = vevents(feed(client, token))[0]
    assert ev["URL"] == f"{SITE}/me/" and ev["DESCRIPTION"] == f"근무표: {SITE}/me/"
    env.SITE_URL = ""
    ev = vevents(feed(client, token))[0]
    assert "URL" not in ev and "DESCRIPTION" not in ev


# --- 헤더·조건부 요청 ---

def check_headers(r, etag):
    assert r["Cache-Control"] == "private, no-cache"
    assert r["Referrer-Policy"] == "no-referrer"
    assert r["ETag"] == etag


def test_headers_etag_304_head_post(client, me):
    commute(period(), me)
    _, token = issue(me)
    r = feed(client, token)
    assert r["Content-Type"] == "text/calendar; charset=utf-8"
    etag = f'"{hashlib.sha256(r.content).hexdigest()}"'
    check_headers(r, etag)
    assert "Last-Modified" not in r
    r304 = feed(client, token, HTTP_IF_NONE_MATCH=etag)
    assert r304.status_code == 304
    check_headers(r304, etag)
    head = feed(client, token, "head")
    assert head.status_code == 200 and head.content == b""
    assert head["Content-Length"] == r["Content-Length"] == str(len(r.content))
    check_headers(head, etag)
    assert feed(client, token, "post").status_code == 405
    assert feed(Client(enforce_csrf_checks=True), token, "post").status_code == 405
    h304 = feed(client, token, "head", HTTP_IF_NONE_MATCH=etag)
    assert h304.status_code == 304
    check_headers(h304, etag)


def test_error_responses_have_security_headers(client, me):
    _, token = issue(me)
    for r in [feed(client, "x" * 43), feed(client, "A" * 43), feed(client, token, "post"), feed(client, "A" * 43, "post")]:
        assert r.status_code in (404, 405)
        assert r["Cache-Control"] == "private, no-cache" and r["Referrer-Policy"] == "no-referrer"


# --- 로그 ---

def test_feed_logs_have_no_token_or_path(client, me, caplog):
    _, token = issue(me)
    calendar.revoke(me)
    bad = "a" * 42
    with caplog.at_level(logging.INFO):
        assert feed(client, bad).status_code == 404
        assert feed(client, token).status_code == 404
        assert feed(client, token, "post").status_code == 405
    recs = [r for r in caplog.records if r.name == "django.request"]
    assert len(recs) == 3
    for r in recs:
        text = r.getMessage() + repr(r.args)
        assert token not in text and bad not in text and "/calendar/" not in text
        assert getattr(r, "request", None) is None
    assert {r.getMessage() for r in recs} == {"calendar feed 404", "calendar feed 405"}
    assert token not in caplog.text and "/calendar/" not in caplog.text


TOKEN = "T" * 43


def leaks(record):
    req = getattr(record, "request", None)
    text = record.getMessage() + repr(record.args) + repr(getattr(req, "path", "")) + repr(getattr(req, "META", ""))
    return TOKEN in text or "/calendar/" in text


@pytest.mark.parametrize("status", [404, 500])
def test_filter_django_request_record(status):
    req = RequestFactory().get(path(TOKEN))
    rec = logging.LogRecord("django.request", logging.WARNING, __file__, 1, "Not Found: %s", (req.path,), None)
    rec.request, rec.status_code = req, status
    assert RedactCalendarFeed().filter(rec) is True
    assert rec.getMessage() == f"calendar feed {status}"
    assert not leaks(rec)


@pytest.mark.parametrize("status", ["200", "404", "500"])
def test_filter_django_server_record(status):
    rec = logging.LogRecord("django.server", logging.INFO, __file__, 1, '"%s" %s %s',
                            (f"GET {path(TOKEN)} HTTP/1.1", status, "123"), None)
    rec.request, rec.status_code = object(), int(status)
    assert RedactCalendarFeed().filter(rec) is True
    assert rec.getMessage() == f"calendar feed {status}"
    assert not leaks(rec)


def test_filter_django_server_bad_request_record():
    # runserver send_error: log_message("code %d, message %s", 400, "Bad request syntax ('GET /calendar/...')")
    rec = logging.LogRecord("django.server", logging.WARNING, __file__, 1, "code %d, message %s",
                            (400, f"Bad request syntax ('GET {path(TOKEN)} HTTP/1.1 x')"), None)
    rec.request = object()
    RedactCalendarFeed().filter(rec)
    assert rec.getMessage() == "calendar feed ?" and rec.args == ()
    assert not leaks(rec)


def test_filter_leaves_other_records():
    req = RequestFactory().get("/me/")
    rec = logging.LogRecord("django.request", logging.WARNING, __file__, 1, "Not Found: %s", ("/me/",), None)
    rec.request, rec.status_code = req, 404
    RedactCalendarFeed().filter(rec)
    assert rec.getMessage() == "Not Found: /me/" and rec.request is req


def test_filter_registered():
    for name in ("django.request", "django.server"):
        assert any(isinstance(f, RedactCalendarFeed) for f in logging.getLogger(name).filters)
    assert logging.getLogger("django.server").handlers  # runserver 접근 로그는 계속 찍힌다


# --- 설정 검증 ---

@pytest.mark.parametrize("url", [
    "https://duty.example/\r\nX: y", "https://duty.example\n", "ftp://duty.example",
    "https://duty.example/?a=1", "https://duty.example/?", "https://duty.example/#x", "https:///path",
    "http://duty.example", "https://user:pw@duty.example", "https://user@duty.example", "https://duty.example:abc",
    "https://duty.example:99999", "https://duty.example/sub", "https://duty.example/sub/",
])
def test_site_url_invalid(url):
    with pytest.raises(ImproperlyConfigured):
        validate_site_url(url, debug=False)


@pytest.mark.parametrize("url", ["", "https://duty.example", "https://duty.example/", "https://duty.example:8443"])
def test_site_url_valid(url):
    validate_site_url(url, debug=False)


def test_site_url_http_in_debug():
    validate_site_url("http://127.0.0.1:8000", debug=True)
    with pytest.raises(ImproperlyConfigured):
        validate_site_url("ftp://duty.example", debug=True)


# --- Fix round 2 ---

def test_changelog_on_date_without_rows_keeps_feed_200(client, me):
    p = period(end=D + timedelta(days=1))
    commute(p, me)  # D+1 에는 행 없음
    ChangeLog.objects.create(period=p, date=D + timedelta(days=1), cell="dawn", before=me, after=None)
    ChangeLog.objects.update(at=datetime(2026, 11, 5, tzinfo=dt_tz.utc))
    _, token = issue(me)
    r = feed(client, token)
    assert r.status_code == 200
    assert vevents(r)[0]["DTSTAMP"] == "20261101T030000Z"


def server_record(line, status="200"):
    rec = logging.LogRecord("django.server", logging.INFO, __file__, 1, '"%s" %s %s', (line, status, "10"), None)
    rec.request, rec.status_code = object(), int(status)
    return rec


@pytest.mark.parametrize("line", ["POST /alarms/calendar/issue/ HTTP/1.1", "GET /help/calendar/ HTTP/1.1"])
def test_filter_keeps_non_feed_calendar_paths(line):
    rec = server_record(line)
    RedactCalendarFeed().filter(rec)
    assert rec.getMessage() == f'"{line}" 200 10'


def test_filter_keeps_non_feed_request_path():
    req = RequestFactory().get("/alarms/calendar/issue/")
    rec = logging.LogRecord("django.request", logging.WARNING, __file__, 1, "Method Not Allowed: %s",
                            ("/alarms/calendar/issue/",), None)
    rec.request, rec.status_code = req, 405
    RedactCalendarFeed().filter(rec)
    assert rec.getMessage() == "Method Not Allowed: /alarms/calendar/issue/" and rec.request is req


def test_filter_redacts_percent_encoded_feed_path():
    rec = server_record(f"GET /%63alendar/{TOKEN}.ics HTTP/1.1")
    RedactCalendarFeed().filter(rec)
    assert rec.getMessage() == "calendar feed 200"
    assert not leaks(rec)


# ── 캘린더에 넣을 근무 고르기 ──

def _summaries(client, token):
    return sorted(e["SUMMARY"] for e in vevents(feed(client, token)))


def test_feed_filters_by_chosen_shifts(client, me):
    from duty.models import ControlDuty
    p = period()
    commute(p, me, "normal")
    ControlDuty.objects.create(period=p, date=D, slot=0, member=me)
    _, token = issue(me)
    assert len(_summaries(client, token)) == 2  # 기본 = 전부
    calendar.set_shifts(me, ["slots"])
    assert _summaries(client, token) == ["장중관제 08:30~09:30"]
    calendar.set_shifts(me, ["normal"])
    assert [s.split()[0] for s in _summaries(client, token)] == ["정상"]
    calendar.set_shifts(me, ["dawn", "normal", "dinner", "night", "slots"])  # 전부 고르면 빈 목록(=전부)으로
    assert me.calendar_feed.__class__.objects.get(user=me).shifts == []


def test_reissue_keeps_shift_choice(client, me):
    issue(me)
    calendar.set_shifts(me, ["night"])
    issue(me)
    assert me.calendar_feed.__class__.objects.get(user=me).shifts == ["night"]


def test_shift_choice_view(client, me):
    client.force_login(me)
    r = client.post("/alarms/calendar/shifts/", {"shift": ["slots"]})
    assert r.status_code == 302  # 구독 전이면 저장할 곳이 없다는 안내
    issue(me)
    body = client.get("/alarms/").content.decode()
    assert "일정에 넣을 근무" in body and body.count('name="shift"') == 5
    client.post("/alarms/calendar/shifts/", {"shift": ["slots", "night"]})
    assert me.calendar_feed.__class__.objects.get(user=me).shifts == ["night", "slots"]
    body = client.get("/alarms/").content.decode()
    import re
    assert len(re.findall(r'name="shift" value="(?:night|slots)" checked', body)) == 2
    assert client.post("/alarms/calendar/shifts/", {"shift": ["bogus"]}).status_code == 302
    assert me.calendar_feed.__class__.objects.get(user=me).shifts == ["night", "slots"]  # 모르는 값은 무시하지 않고 거절


def test_empty_choice_is_rejected(client, me):
    """전부 해제는 '전부'와 저장값이 같아(빈 목록) 헷갈리므로 거절한다."""
    issue(me)
    calendar.set_shifts(me, ["night"])
    client.force_login(me)
    client.post("/alarms/calendar/shifts/", {})
    assert me.calendar_feed.__class__.objects.get(user=me).shifts == ["night"]
    assert "하나 이상" in client.get("/alarms/").content.decode()
