"""보안 점검 2단계. 번호는 점검 보고서의 항목 번호."""
import io
import logging
import os
import socket
import sqlite3
import threading

import pytest
from django.utils import timezone

from duty.csv_io import CsvInvalid, MAX_ERRORS, parse_commute_csv
from duty.guard import RequestGuard
from duty.models import CalendarFeed, PushAlarmSubscription, TelegramAlarmProfile

PW = "Old-pw-" + "12345"


# ---- #1·#2 요청 가드 ----

def _env(method="POST", path="/x/", body=b"", **extra):
    return {"REQUEST_METHOD": method, "PATH_INFO": path, "CONTENT_LENGTH": str(len(body)) if body else "",
            "wsgi.input": io.BytesIO(body), **extra}


def _call(app, env):
    out = {}
    body = b"".join(app(env, lambda status, headers: out.setdefault("status", status)))
    return out["status"], body


def _echo(seen):
    def app(environ, start_response):
        seen.append(environ["wsgi.input"].read())
        start_response("200 OK", [])
        return [b"ok"]
    return app


def test_guard_passes_body_through():
    seen = []
    status, _ = _call(RequestGuard(_echo(seen)), _env(body=b"a=1&b=2"))
    assert status.startswith("200") and seen == [b"a=1&b=2"]


def test_guard_rejects_large_body():
    seen = []
    shut = []
    sock = type("S", (), {"shutdown": lambda self, how: shut.append(how)})()
    g = RequestGuard(_echo(seen), max_body=10)
    status, body = _call(g, _env(body=b"x" * 11, **{"gunicorn.socket": sock}))
    assert status.startswith("413") and seen == [] and "크기" in body.decode()
    assert shut == [socket.SHUT_RD]  # 남은 본문을 읽느라 스레드를 잡지 않게 읽기를 닫는다


def test_guard_slow_body_times_out():
    """#1: 본문을 다 보내지 않으면 마감에 소켓 읽기를 닫고 408(Django 를 부르지 않는다)."""
    closed = threading.Event()

    class SlowInput:
        def read(self, n=-1):
            closed.wait(5)  # 마감에 소켓이 닫힐 때까지 막혀 있다가 빈 값
            return b""

    class Sock:
        def shutdown(self, how):
            closed.set()

    seen = []
    env = {**_env(body=b"x"), "CONTENT_LENGTH": "100", "wsgi.input": SlowInput(), "gunicorn.socket": Sock()}
    status, _ = _call(RequestGuard(_echo(seen), deadline=0.2), env)
    assert status.startswith("408") and seen == [] and closed.is_set()


def test_guard_limits_concurrent_logins():
    """#2: 비밀번호 확인 POST 는 동시에 limit 개까지만, 넘치면 바로 429."""
    entered, release = threading.Event(), threading.Event()

    def slow(environ, start_response):
        entered.set()
        release.wait(5)
        start_response("200 OK", [])
        return [b""]

    g = RequestGuard(slow, login_paths={"/login/"}, login_limit=1)
    t = threading.Thread(target=_call, args=(g, _env(path="/login/", body=b"a=1")))
    t.start()
    assert entered.wait(5)
    try:
        assert _call(g, _env(path="/login/", body=b"a=1"))[0].startswith("429")
        assert _call(g, _env(method="GET", path="/login/"))[0].startswith("200")  # 화면 열기는 막지 않는다
        assert _call(g, _env(path="/other/", body=b"a=1"))[0].startswith("200")
    finally:
        release.set()
        t.join()
    assert _call(g, _env(path="/login/", body=b"a=1"))[0].startswith("200")  # 끝나면 다시 된다


def test_wsgi_application_is_guarded():
    from config.wsgi import application
    assert isinstance(application, RequestGuard)
    from django.urls import reverse
    assert {reverse("login"), reverse("password_change"), reverse("admin:login")} <= application.login_paths


# ---- #4 로그 파일 크기 상한 ----

def test_log_file_capped(tmp_path):
    from duty.logging import CappedFileHandler
    h = CappedFileHandler(tmp_path / "a.log", max_bytes=2000)
    log = logging.getLogger("test.capped")
    log.addHandler(h)
    log.propagate = False
    try:
        for _ in range(500):
            log.warning("x" * 100)
    finally:
        log.removeHandler(h)
        h.close()
    text = (tmp_path / "a.log").read_text(encoding="utf-8")
    assert len(text) < 2500 and text.count("로그가 너무 많아") == 1


# ---- #9 비밀번호 초기화 때 다른 연결도 끊는다 ----

def test_reissue_revokes_channels(make_member):
    from duty.accounts import issue_account
    u = make_member("가")
    issue_account(u)  # 첫 발급
    CalendarFeed.objects.create(user=u, token_hash="h" * 64, issued_at=timezone.now())
    TelegramAlarmProfile.objects.create(user=u, chat_id="9", verified_at=timezone.now())
    PushAlarmSubscription.objects.create(user=u, endpoint="https://push.example/1", p256dh="p", auth="a")
    issue_account(u)  # 초기화
    assert not CalendarFeed.objects.filter(user=u).exists()
    assert TelegramAlarmProfile.objects.get(user=u).chat_id == ""
    assert not PushAlarmSubscription.objects.filter(user=u).exists()


# ---- #10 '지금 비밀번호' 확인도 잠금에 센다 ----

def test_old_password_failures_count_for_lockout(client, make_member):
    from axes.models import AccessAttempt
    u = make_member("가", user=True)
    u.set_password(PW)
    u.save()
    client.force_login(u)
    for _ in range(2):
        client.post("/password/", {"old_password": "wrong", "new_password1": "a", "new_password2": "b"})
    assert AccessAttempt.objects.get(username=u.username).failures_since_start == 2


def test_password_change_still_works(client, make_member):
    u = make_member("가", user=True)
    u.set_password(PW)
    u.save()
    client.force_login(u)
    new = "New-pw-" + "67890xyz"
    r = client.post("/password/", {"old_password": PW, "new_password1": new, "new_password2": new})
    assert r.status_code == 302
    u.refresh_from_db()
    assert u.check_password(new)


# ---- #18 로그인한 화면은 브라우저에 남기지 않는다 ----

def test_authenticated_pages_no_store(client, make_member):
    client.force_login(make_member("가", user=True))
    for path in ("/me/", "/password/"):
        assert "no-store" in client.get(path)["Cache-Control"], path


# ---- #15 백업 사본에서 세션을 지우고 600 ----

def test_backup_drops_sessions_and_is_private(tmp_path):
    from duty.services.backup import copy_db
    src = tmp_path / "src.sqlite3"
    c = sqlite3.connect(src)
    c.execute("CREATE TABLE django_session (session_key TEXT, session_data TEXT)")
    c.execute("INSERT INTO django_session VALUES ('k', 'secret-session-data')")
    c.commit()
    c.close()
    dest = tmp_path / "b" / "db.sqlite3"
    copy_db(src, dest)
    assert sqlite3.connect(dest).execute("SELECT count(*) FROM django_session").fetchone() == (0,)
    assert b"secret-session-data" not in dest.read_bytes()
    assert os.stat(dest).st_mode & 0o777 == 0o600


def test_backup_failure_leaves_no_tmp(tmp_path):
    from duty.services.backup import copy_db
    with pytest.raises(sqlite3.Error):
        copy_db(tmp_path / "없음.sqlite3", tmp_path / "b" / "d.sqlite3")
    assert list((tmp_path / "b").iterdir()) == []


def test_backup_without_session_table(tmp_path):
    from duty.services.backup import copy_db
    src = tmp_path / "src.sqlite3"
    sqlite3.connect(src).execute("CREATE TABLE t (x)").connection.commit()
    copy_db(src, tmp_path / "d.sqlite3")
    assert (tmp_path / "d.sqlite3").exists()


# ---- #13 오류 개수 상한 ----

def test_csv_error_cap():
    raw = ("date,정상\n" + "x,가\n" * 5000).encode()
    with pytest.raises(CsvInvalid) as e:
        parse_commute_csv(raw, ["normal"])
    assert len(e.value.errors) == MAX_ERRORS + 1
    assert "너무 많아" in e.value.errors[-1].reason


# ---- #11 chat_id 직접 입력은 없앤다(/start 코드 연결만) ----

def test_chat_id_direct_entry_removed(client, make_member):
    from duty.models import AlarmSettings
    AlarmSettings.objects.update_or_create(pk=1, defaults={"telegram_bot_token": "TOK"})  # 사용자명 없음
    u = make_member("가", user=True)
    client.force_login(u)
    client.post("/alarms/telegram/", {"chat_id": "123"})
    assert not TelegramAlarmProfile.objects.filter(user=u, chat_id="123").exists()
    assert "chat_id 직접 입력" not in client.get("/alarms/").content.decode()
