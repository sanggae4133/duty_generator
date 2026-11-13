"""운영: run_worker(알림·백업·상태 점검), backup/restore 명령, 파일 로그."""
import fcntl
import logging
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
from collections import namedtuple
from datetime import datetime, timedelta

import pytest
from django.core.management import CommandError, call_command
from django.db.migrations.loader import MigrationLoader
from django.utils import timezone

from duty.alarms import senders
from duty.errors import DutyError
from duty.models import AlarmSettings
from duty.services import alarm_runner, backup, change_notice, health

Usage = namedtuple("Usage", "total used free")


def at(y, mo, d, h=0, mi=0):
    return timezone.make_aware(datetime(y, mo, d, h, mi))


def make_db(path, rows=("a",)):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t(v)")
    con.executemany("INSERT INTO t VALUES(?)", [(r,) for r in rows])
    con.commit()
    con.close()


def rows(path):
    con = sqlite3.connect(path)
    try:
        return [r[0] for r in con.execute("SELECT v FROM t")]
    finally:
        con.close()


@pytest.fixture
def data(settings, tmp_path):
    settings.DATA_DIR = tmp_path
    settings.DB_PATH = tmp_path / "db.sqlite3"
    settings.BACKUP_DIR = tmp_path / "backups"
    settings.LOG_DIR = tmp_path / "logs"
    settings.ALARMS_LOCK_PATH = tmp_path / ".alarms.lock"
    settings.BACKUP_HOUR = 3
    settings.BACKUP_KEEP_DAYS = 30
    make_db(settings.DB_PATH)
    return settings


# ---- 백업 ----

def test_daily_backup_after_hour_once(data):
    data.BACKUP_DIR.mkdir()
    (data.BACKUP_DIR / "db-20261110.sqlite3").write_text("x")  # 방금 만든(26시간 안) 백업이 있으면 시각을 기다린다
    assert backup.daily(at(2026, 11, 11, 2, 59)) is None
    p = backup.daily(at(2026, 11, 11, 3, 0))
    assert p == data.BACKUP_DIR / "db-20261111.sqlite3" and rows(p) == ["a"]
    assert backup.daily(at(2026, 11, 11, 3, 1)) is None  # 하루 한 번
    assert not list(data.BACKUP_DIR.glob("*.tmp"))


def test_daily_backup_right_away_without_recent_backup(data):
    """새로 설치했거나 오래 꺼져 있었으면 시각과 상관없이 바로 만든다(상태 점검이 '백업 없음'으로 시작하지 않게)."""
    data.BACKUP_DIR.mkdir()
    old = data.BACKUP_DIR / "db-20261101.sqlite3"
    old.write_text("x")
    t = time.time() - 27 * 3600
    os.utime(old, (t, t))
    assert backup.daily(at(2026, 11, 11, 1, 0)).name == "db-20261111.sqlite3"
    assert backup.daily(at(2026, 11, 11, 2, 0)) is None


def test_daily_backup_catches_up_late_start(data):
    assert backup.daily(at(2026, 11, 11, 15, 0)).name == "db-20261111.sqlite3"


def test_backup_reads_wal_contents(data):
    con = sqlite3.connect(data.DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("INSERT INTO t VALUES('in-wal')")
    con.commit()  # 체크포인트 전, 열린 채로
    try:
        assert rows(backup.backup_now(at(2026, 11, 11, 10))) == ["a", "in-wal"]
    finally:
        con.close()


def test_backup_is_single_file_not_wal(data):
    data.DB_PATH.unlink()
    migrated(data.DB_PATH)
    con = sqlite3.connect(data.DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    con.close()
    p = backup.backup_now(at(2026, 11, 11, 10))
    c = sqlite3.connect(f"{p.as_uri()}?mode=ro", uri=True)
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    c.close()
    backup.restore(p, at(2026, 11, 11, 11))
    assert sorted(x.name for x in data.BACKUP_DIR.iterdir()) == [
        "before-restore-20261111-110000.sqlite3", "db-20261111-100000.sqlite3"]  # 읽기만 해도 -wal·-shm 이 생기지 않는다


def test_prune_keeps_recent_and_other_files(data):
    data.BACKUP_KEEP_DAYS = 2
    data.BACKUP_DIR.mkdir()
    for name in ["db-20261107.sqlite3", "db-20261108-101500.sqlite3", "db-20261109.sqlite3", "db-20261110.sqlite3",
                 "before-restore-20260101-000000.sqlite3", "memo.txt"]:
        (data.BACKUP_DIR / name).write_text("x")
    backup.daily(at(2026, 11, 11, 4))
    assert sorted(p.name for p in data.BACKUP_DIR.iterdir()) == [
        "before-restore-20260101-000000.sqlite3", "db-20261109.sqlite3", "db-20261110.sqlite3",
        "db-20261111.sqlite3", "memo.txt"]


def test_backup_command(data, capsys, monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(2026, 11, 11, 15, 30))
    call_command("backup")
    p = data.BACKUP_DIR / "db-20261111-153000.sqlite3"
    assert p.exists() and str(p) in capsys.readouterr().out


# ---- 복원 ----

def migrated(path, rows_=("restored",), extra=()):
    """이 코드의 마이그레이션이 다 적용된 것처럼 보이는 백업 파일."""
    make_db(path, rows_)
    loader = MigrationLoader(None, ignore_no_migrations=True)
    applied = set()
    for key, m in loader.graph.nodes.items():
        applied |= set(m.replaces) if m.replaces else {key}
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE django_migrations(id INTEGER PRIMARY KEY, app, name, applied)")
    con.executemany("INSERT INTO django_migrations(app, name, applied) VALUES(?, ?, '')", sorted(applied | set(extra)))
    con.commit()
    con.close()
    return path


def test_restore(data, tmp_path, monkeypatch, capsys):
    src = migrated(tmp_path / "old.sqlite3")
    (tmp_path / "db.sqlite3-wal").write_text("stale")
    (tmp_path / "db.sqlite3-shm").write_text("stale")
    monkeypatch.setattr(timezone, "now", lambda: at(2026, 11, 11, 9))
    call_command("restore", str(src))
    assert rows(data.DB_PATH) == ["restored"]
    assert not (tmp_path / "db.sqlite3-wal").exists() and not (tmp_path / "db.sqlite3-shm").exists()
    before = data.BACKUP_DIR / "before-restore-20261111-090000.sqlite3"
    assert rows(before) == ["a"]
    out = capsys.readouterr().out
    assert "migrate" in out and before.name in out


def test_restore_refuses_corrupt(data, tmp_path):
    bad = tmp_path / "bad.sqlite3"
    bad.write_bytes(b"SQLite format 3\x00" + b"\x00" * 200)
    with pytest.raises(CommandError, match="검사"):
        call_command("restore", str(bad))
    assert rows(data.DB_PATH) == ["a"]


def test_restore_refuses_other_migrations(data, tmp_path):
    src = migrated(tmp_path / "old.sqlite3", extra=[("duty", "9999_future")])
    with pytest.raises(CommandError, match="마이그레이션"):
        call_command("restore", str(src))
    assert rows(data.DB_PATH) == ["a"] and not data.BACKUP_DIR.exists()


def test_real_migrated_db_passes_check_and_restore(data, tmp_path, settings):
    """합성한 목록이 아니라 실제 migrate 한 DB 가 복원 검사를 통과한다(검사의 기대 목록 계산이 틀리면 여기서 걸린다)."""
    real = tmp_path / "real.sqlite3"
    code = ("import sys, django; from pathlib import Path; django.setup(); "
            "from django.core.management import call_command; call_command('migrate', verbosity=0); "
            "from django.conf import settings; from duty.services.backup import copy_db; "
            "copy_db(settings.DB_PATH, Path(sys.argv[1]))")
    subprocess.run([sys.executable, "-c", code, str(real)], capture_output=True, text=True, check=True,
                   cwd=settings.BASE_DIR, env={**os.environ, "DJANGO_SETTINGS_MODULE": "config.test_settings"})
    backup.check(real)
    backup.restore(real, NOW)
    con = sqlite3.connect(data.DB_PATH)
    try:
        assert con.execute("SELECT count(*) FROM django_migrations WHERE app='duty'").fetchone()[0] >= 2
    finally:
        con.close()
    con = sqlite3.connect(real)
    con.execute("DELETE FROM django_migrations WHERE app='duty' AND name='0002_alarmsettings'")
    con.commit()
    con.close()
    with pytest.raises(DutyError, match="마이그레이션"):
        backup.check(real)


def test_restore_refused_while_worker_runs(data, tmp_path):
    src = migrated(tmp_path / "old.sqlite3")
    with open(data.ALARMS_LOCK_PATH, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        with pytest.raises(CommandError, match="작업자가 돌고 있습니다"):
            call_command("restore", str(src))
    assert rows(data.DB_PATH) == ["a"] and not data.BACKUP_DIR.exists()


def test_restore_holds_worker_lock(data, tmp_path, monkeypatch):
    """복원하는 동안 작업자가 뜨지 못한다."""
    src = migrated(tmp_path / "old.sqlite3")
    real = backup.copy_db
    seen = []

    def spy(a, b):
        with open(data.ALARMS_LOCK_PATH, "a") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                seen.append("free")
            except BlockingIOError:
                seen.append("held")
        real(a, b)
    monkeypatch.setattr(backup, "copy_db", spy)
    backup.restore(src, NOW)
    assert seen == ["held", "held"]


def test_restore_refuses_missing_or_same(data, tmp_path):
    with pytest.raises(CommandError, match="없습니다"):
        call_command("restore", str(tmp_path / "none.sqlite3"))
    with pytest.raises(CommandError, match="지금 DB"):
        call_command("restore", str(data.DB_PATH))


# ---- 상태 점검 ----

@pytest.fixture
def box(db, data, monkeypatch):
    """정상인 서버: 웹 응답, 최근 백업, 디스크 50%."""
    data.BACKUP_DIR.mkdir()
    (data.BACKUP_DIR / "db-20261111.sqlite3").write_text("x")
    st = {"web": True, "disk": Usage(100, 50, 50), "sent": [], "send_raise": None, "urls": [], "down": set()}

    def urlopen(url, timeout=None):
        st["urls"].append((url, timeout))
        if not st["web"] or url in st["down"]:
            raise urllib.error.URLError("refused")
        return open(os.devnull, "rb")

    def disk_usage(path):
        if isinstance(st["disk"], Exception):
            raise st["disk"]
        return st["disk"]

    def send(cfg, chat_id, text):
        if st["send_raise"]:
            raise st["send_raise"]
        st["sent"].append((cfg.telegram_token, chat_id, text))
        return {}

    monkeypatch.setattr(health.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(health.shutil, "disk_usage", disk_usage)
    monkeypatch.setattr(senders, "telegram_send", send)
    AlarmSettings.objects.create(pk=1, telegram_bot_token="TOK", ops_chat_id=777)
    st["state"] = data.DATA_DIR / ".health.state"
    return st


NOW = at(2026, 11, 11, 12)


def test_health_first_ok_records_only(box, caplog):
    with caplog.at_level(logging.INFO):
        health.check(NOW)
    assert "health: 정상(점검 시작)" in caplog.text
    assert box["sent"] == [] and box["state"].read_text() == ""
    assert box["urls"] == [("http://127.0.0.1:8008/login/", 10)]
    caplog.clear()
    with caplog.at_level(logging.INFO):
        health.check(NOW)
    assert "health" not in caplog.text  # 그대로면 아무것도 안 남긴다


def test_health_tells_nginx_from_web(box):
    """nginx(8008)만 죽으면 'nginx 응답 없음', 웹(8090)까지 죽으면 '웹 응답 없음'으로 바뀌어 다시 알린다
    (nginx 를 꺼 둔 동안에도 웹 장애를 놓치지 않게)."""
    health.check(NOW)
    box["down"] = {"http://127.0.0.1:8008/login/"}
    health.check(NOW)
    assert "nginx 응답 없음(웹은 정상)" in box["sent"][-1][2]
    assert ("http://127.0.0.1:8090/login/", 10) in box["urls"]
    box["down"].add("http://127.0.0.1:8090/login/")
    health.check(NOW)
    assert len(box["sent"]) == 2 and "웹 응답 없음" in box["sent"][-1][2] and "nginx" not in box["sent"][-1][2]


def test_health_change_sends_once_then_recovery(box, caplog):
    health.check(NOW)
    box["web"] = False
    box["disk"] = Usage(100, 95, 5)
    with caplog.at_level(logging.WARNING):
        health.check(NOW)
    assert "health: 웹 응답 없음; 디스크 95% 사용;" in caplog.text
    [(tok, chat, text)] = box["sent"]
    assert tok == "TOK" and chat == "777" and text.startswith("[NXT 당번표 ") and "웹 응답 없음; 디스크 95% 사용;" in text
    health.check(NOW)
    assert len(box["sent"]) == 1
    box["web"], box["disk"] = True, Usage(100, 50, 50)
    health.check(NOW)
    assert box["sent"][-1][2].endswith("정상으로 돌아왔습니다.") and box["state"].read_text() == ""


def test_health_old_backup(box):
    old = time.time() - 27 * 3600
    for f in box["state"].parent.joinpath("backups").iterdir():
        os.utime(f, (old, old))
    health.check(NOW)
    assert "26시간 안에 만든 백업 없음;" in box["sent"][0][2]


def test_health_no_backup_dir(box, data):
    for f in data.BACKUP_DIR.iterdir():
        f.unlink()
    data.BACKUP_DIR.rmdir()
    health.check(NOW)
    assert "26시간 안에 만든 백업 없음;" in box["sent"][0][2]


def test_health_disk_check_failed(box):
    box["disk"] = OSError("x")
    health.check(NOW)
    assert "디스크 확인 실패;" in box["sent"][0][2]


def test_health_send_failure_retries_next_time(box):
    health.check(NOW)
    box["web"] = False
    box["send_raise"] = senders.Temporary(502)
    with pytest.raises(senders.Temporary):
        health.check(NOW)
    assert box["state"].read_text() == ""  # 다음 번에 다시 보낸다
    box["send_raise"] = None
    health.check(NOW)
    assert len(box["sent"]) == 1 and box["state"].read_text() != ""


def test_health_no_ops_chat_only_logs(box):
    AlarmSettings.objects.update(ops_chat_id=None)
    health.check(NOW)
    box["web"] = False
    health.check(NOW)
    assert box["sent"] == [] and "웹 응답 없음" in box["state"].read_text()


# ---- 작업자 ----

@pytest.fixture
def jobs(monkeypatch, db, data):
    calls = []

    def job(name, fail=False):
        def run(now):
            calls.append((name, now))
            if fail:
                raise RuntimeError(name)
        return run

    monkeypatch.setattr(alarm_runner, "tick", job("alarms", fail=True))
    monkeypatch.setattr(backup, "daily", job("backup"))
    monkeypatch.setattr(health, "check", job("health"))
    monkeypatch.setattr(change_notice, "tick", job("changes"))
    return calls


def test_round_isolates_failures(jobs, caplog):
    from duty.management.commands import run_worker
    run_worker.run_round(NOW)
    # 백업·점검이 먼저: 알림 발송이 네트워크 타임아웃으로 오래 걸려도 백업·점검이 밀리지 않게
    # 내 근무 변경 알림은 정기 알림보다 먼저(정기 발송이 느려도 '바로' 가게)
    assert [n for n, _ in jobs] == ["backup", "health", "changes", "alarms"] and all(t == NOW for _, t in jobs)
    assert "worker job failed: alarms" in caplog.text


def test_health_every_five_minutes(jobs):
    from duty.management.commands import run_worker
    for m in range(10):
        run_worker.run_round(NOW + timedelta(minutes=m))
    assert [t.minute for n, t in jobs if n == "health"] == [0, 5]
    assert len([n for n, _ in jobs if n == "alarms"]) == 10


def test_once_runs_all_jobs_and_logs_to_file(jobs, data, monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: NOW + timedelta(minutes=1))
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        call_command("run_worker", "--once")
    finally:
        for h in root.handlers[:]:
            if h not in before:
                root.removeHandler(h)
                h.close()
    assert [n for n, _ in jobs] == ["backup", "health", "changes", "alarms"]  # --once 는 시각과 상관없이 전부
    assert "worker job failed: alarms" in (data.LOG_DIR / "worker.log").read_text(encoding="utf-8")


def test_once_refused_while_worker_runs(jobs, data):
    with open(data.ALARMS_LOCK_PATH, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        with pytest.raises(CommandError, match="다른 run_worker가 실행 중입니다.") as e:
            call_command("run_worker", "--once")
        assert e.value.returncode == 1
    assert jobs == []


def test_dry_run_works_while_worker_runs(jobs, data, capsys):
    with open(data.ALARMS_LOCK_PATH, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        call_command("run_worker", "--dry-run")
    assert "telegram=0 push=0" in capsys.readouterr().out and jobs == []
    assert not AlarmSettings.objects.exists()  # 읽기만 한다(설정 행도 만들지 않음)


class Stop(Exception):
    pass


def test_loop_skips_health_on_first_round(jobs, data, monkeypatch):
    """막 켜졌을 때(재부팅·업그레이드) 아직 뜨는 중인 웹을 '응답 없음'으로 보지 않게 첫 바퀴는 점검을 건너뛴다."""
    from duty.management.commands import run_worker
    monkeypatch.setattr(timezone, "now", lambda: NOW)  # 5의 배수 분
    sleeps = []

    def sleep(sec):
        sleeps.append(sec)
        if len(sleeps) == 2:
            raise Stop
    monkeypatch.setattr(run_worker.time, "sleep", sleep)
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        with pytest.raises(Stop):
            call_command("run_worker")
    finally:
        for h in root.handlers[:]:
            if h not in before:
                root.removeHandler(h)
                h.close()
    assert [n for n, _ in jobs] == ["backup", "changes", "alarms", "backup", "health", "changes", "alarms"]


# ---- 파일 로그 ----

def test_tests_never_use_repo_data_dir(settings):
    assert settings.DATA_DIR != settings.BASE_DIR / "data"
    assert "duty-test-" in settings.DATA_DIR.name


def test_log_to_file_format_and_redaction(settings):
    code = ("import django, logging; django.setup(); from duty.logging import log_to_file; log_to_file('web'); "
            "log_to_file('web'); logging.getLogger('duty.x').info('hello'); "
            "from types import SimpleNamespace as N; logging.getLogger('django.request').warning("
            "'Not Found: %s', '/calendar/SECRETTOKEN.ics', extra={'request': N(path='/calendar/SECRETTOKEN.ics'), "
            "'status_code': 404}); [h.flush() for h in logging.getLogger().handlers]; "
            "from django.conf import settings as s; print((s.LOG_DIR / 'web.log').read_text(encoding='utf-8'), end='')")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=settings.BASE_DIR,
                       env={**os.environ, "DJANGO_SETTINGS_MODULE": "config.test_settings"})
    lines = r.stdout.splitlines()
    assert len(lines) == 2  # 핸들러는 한 번만 붙는다
    assert lines[0].endswith(" INFO duty.x hello") and lines[0][:4].isdigit()
    assert "SECRETTOKEN" not in lines[1] and "calendar feed" in lines[1]
