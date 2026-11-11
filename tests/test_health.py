"""manage.py health: 상태가 바뀔 때만 관리자 텔레그램."""
import importlib
import os
import subprocess
import time
import urllib.error
from collections import namedtuple

import pytest
from django.core.management import CommandError, call_command

from duty.alarms import senders
from duty.models import AlarmSettings

health = importlib.import_module("duty.management.commands.health")
Usage = namedtuple("Usage", "total used free")


@pytest.fixture
def box(db, settings, tmp_path, monkeypatch):
    """정상인 서버: 웹 응답, 알림 서비스 enabled+active, 최근 백업, 디스크 50%."""
    settings.DB_PATH = str(tmp_path / "db.sqlite3")
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "db-20261111.sqlite3").write_text("x")
    monkeypatch.setattr(health, "BACKUP_DIR", backups)
    st = {"web": True, "enabled": True, "active": True, "disk": Usage(100, 50, 50), "sent": [], "send_raise": None,
          "urls": [], "commands": []}

    def urlopen(url, timeout=None):
        st["urls"].append((url, timeout))
        if not st["web"]:
            raise urllib.error.URLError("refused")
        return open(os.devnull, "rb")

    def run(cmd, **kw):
        st["commands"].append(cmd)
        ok = st["enabled"] if "is-enabled" in cmd else st["active"]
        return subprocess.CompletedProcess(cmd, 0 if ok else 3)

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
    monkeypatch.setattr(health.subprocess, "run", run)
    monkeypatch.setattr(health.shutil, "disk_usage", disk_usage)
    monkeypatch.setattr(senders, "telegram_send", send)
    AlarmSettings.objects.create(pk=1, telegram_bot_token="TOK", ops_chat_id=777)
    st["state"] = tmp_path / ".health.state"
    st["backups"] = backups
    return st


def run(capsys):
    call_command("health")
    return capsys.readouterr().out


def test_first_ok_records_only(box, capsys):
    assert "health: 정상(점검 시작)" in run(capsys)
    assert box["sent"] == [] and box["state"].read_text() == ""
    assert box["urls"] == [("http://127.0.0.1:8090/login/", 10)]
    assert run(capsys) == ""  # 그대로면 아무것도 안 남긴다


def test_change_sends_once_then_recovery(box, capsys):
    run(capsys)
    box["web"] = False
    box["active"] = False
    out = run(capsys)
    assert "health: 웹 응답 없음; 알림 서비스 멈춤;" in out
    [(tok, chat, text)] = box["sent"]
    assert tok == "TOK" and chat == "777" and text.startswith("[당번표 ") and "웹 응답 없음; 알림 서비스 멈춤;" in text
    run(capsys)
    assert len(box["sent"]) == 1
    box["web"] = box["active"] = True
    assert "health: 정상" in run(capsys)
    assert box["sent"][-1][2].endswith("정상으로 돌아왔습니다.") and box["state"].read_text() == ""


def test_first_run_with_problem_sends(box, capsys):
    box["disk"] = Usage(100, 95, 5)
    run(capsys)
    assert "디스크 95% 사용;" in box["sent"][0][2]


def test_alarms_disabled_not_checked(box, capsys):
    box["enabled"] = box["active"] = False
    run(capsys)
    assert box["sent"] == [] and box["commands"] == [["systemctl", "is-enabled", "-q", "duty-alarms"]]


def test_old_backup(box, capsys):
    old = time.time() - 27 * 3600
    for f in box["backups"].iterdir():
        os.utime(f, (old, old))
    run(capsys)
    assert "26시간 안에 만든 백업 없음;" in box["sent"][0][2]


def test_disk_check_failed(box, capsys):
    box["disk"] = OSError("x")
    run(capsys)
    assert "디스크 확인 실패;" in box["sent"][0][2]


def test_send_failure_keeps_state(box, capsys):
    run(capsys)
    box["web"] = False
    box["send_raise"] = senders.Temporary(502)
    with pytest.raises(CommandError):
        run(capsys)
    assert box["state"].read_text() == ""  # 다음 번에 다시 보낸다
    box["send_raise"] = None
    run(capsys)
    assert len(box["sent"]) == 1 and box["state"].read_text() != ""


def test_no_ops_chat_only_logs(box, capsys):
    AlarmSettings.objects.update(ops_chat_id=None)
    run(capsys)
    box["web"] = False
    assert "웹 응답 없음" in run(capsys)
    assert box["sent"] == [] and "웹 응답 없음" in box["state"].read_text()
