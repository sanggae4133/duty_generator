"""루트 .env 읽기(config/settings.py)와 deploy/.env.example 정합성."""
import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

import config.settings as cs

ROOT = Path(cs.BASE_DIR)


def test_load_env_file(monkeypatch, tmp_path):
    env = {"DUTY_KEEP": "from-env"}
    monkeypatch.setattr(os, "environ", env)
    f = tmp_path / ".env"
    f.write_text("# 주석\n\n  DUTY_A = one two  \nDUTY_KEEP=from-file\nDUTY_EMPTY=\n  # 들여쓴 주석\nnot-a-pair\nDUTY_B=x=y\n",
                 encoding="utf-8")
    cs.load_env_file(f)
    assert env == {"DUTY_KEEP": "from-env", "DUTY_A": "one two", "DUTY_EMPTY": "", "DUTY_B": "x=y"}


def test_load_env_file_missing_is_ok(monkeypatch, tmp_path):
    env = {}
    monkeypatch.setattr(os, "environ", env)
    cs.load_env_file(tmp_path / "없음.env")
    assert env == {}


def test_settings_read_env_file(monkeypatch, tmp_path):
    f = tmp_path / ".env"
    f.write_text("DUTY_ADMIN_PATH=from-file\nDUTY_DEBUG=1\n", encoding="utf-8")
    monkeypatch.setattr(os, "environ", {"DUTY_ENV_FILE": str(f), "DUTY_DATA_DIR": os.environ["DUTY_DATA_DIR"]})
    try:
        importlib.reload(cs)
        assert cs.ADMIN_PATH == "from-file"
    finally:
        monkeypatch.undo()
        importlib.reload(cs)


def test_test_settings_never_read_env_file(tmp_path):
    """테스트 설정은 개발자의 .env(또는 DUTY_ENV_FILE)를 읽지 않는다."""
    f = tmp_path / ".env"
    f.write_text("DUTY_ADMIN_PATH=leaked\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "DUTY_ADMIN_PATH"}
    r = subprocess.run([sys.executable, "-c", "import config.test_settings as t; print(t.ADMIN_PATH)"],
                       capture_output=True, text=True, cwd=ROOT, env={**env, "DUTY_ENV_FILE": str(f)})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "admin"


def test_env_example_lists_every_setting():
    names = set(re.findall(r'"(DUTY_[A-Z_]+)"', (ROOT / "config/settings.py").read_text(encoding="utf-8")))
    names.discard("DUTY_ENV_FILE")  # 테스트 전용
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    listed = set(re.findall(r"^#? ?(DUTY_[A-Z_]+)=", example, re.M))
    assert names and names <= listed, names - listed


def reload_with(monkeypatch, **env):
    base = {"DUTY_ENV_FILE": "", "DUTY_DEBUG": "1", "DUTY_DATA_DIR": os.environ["DUTY_DATA_DIR"]}  # 테스트용 임시 폴더
    monkeypatch.setattr(os, "environ", {k: v for k, v in {**base, **env}.items() if v is not None})
    importlib.reload(cs)
    return cs


@pytest.fixture
def restore_settings(monkeypatch):
    yield
    monkeypatch.undo()
    importlib.reload(cs)


def test_data_dir_default(monkeypatch, restore_settings):
    monkeypatch.setattr(cs.Path, "mkdir", lambda *a, **k: None)  # 저장소 data/ 를 만들지 않게
    s = reload_with(monkeypatch, DUTY_DATA_DIR=None)
    d = ROOT / "data"
    assert s.DATA_DIR == d and s.DATABASES["default"]["NAME"] == d / "db.sqlite3"
    assert (s.BACKUP_DIR, s.LOG_DIR) == (d / "backups", d / "logs")
    assert (s.ALARMS_LOCK_PATH, s.TELEGRAM_UPDATES_LOCK_PATH) == (d / ".alarms.lock", d / ".telegram-updates.lock")
    assert (s.BACKUP_HOUR, s.BACKUP_KEEP_DAYS, s.LOG_KEEP_DAYS) == (3, 30, 14)


def test_data_dir_override(monkeypatch, tmp_path, restore_settings):
    s = reload_with(monkeypatch, DUTY_DATA_DIR=str(tmp_path / "d"))
    assert s.DATA_DIR == tmp_path / "d" and s.DB_PATH == tmp_path / "d/db.sqlite3"
    assert s.DATA_DIR.is_dir()  # 없으면 만든다
    monkeypatch.setattr(cs.Path, "mkdir", lambda *a, **k: None)
    assert reload_with(monkeypatch, DUTY_DATA_DIR="").DATA_DIR == ROOT / "data"  # 빈 값 = 기본


def test_data_dir_relative_is_project_root(monkeypatch, restore_settings):
    monkeypatch.chdir("/")
    monkeypatch.setattr(cs.Path, "mkdir", lambda *a, **k: None)
    s = reload_with(monkeypatch, DUTY_DATA_DIR="data")
    assert s.DATA_DIR == ROOT / "data"


def test_number_settings(monkeypatch, restore_settings):
    s = reload_with(monkeypatch, DUTY_BACKUP_HOUR="23", DUTY_BACKUP_KEEP_DAYS="7", DUTY_LOG_KEEP_DAYS="")
    assert (s.BACKUP_HOUR, s.BACKUP_KEEP_DAYS, s.LOG_KEEP_DAYS) == (23, 7, 14)
    for k, v in [("DUTY_BACKUP_HOUR", "24"), ("DUTY_BACKUP_KEEP_DAYS", "0"), ("DUTY_LOG_KEEP_DAYS", "x")]:
        with pytest.raises(ImproperlyConfigured, match=k):
            reload_with(monkeypatch, **{k: v})


def test_deploy_is_two_units():
    assert sorted(p.name for p in (ROOT / "deploy").iterdir()) == ["duty-web.service", "duty-worker.service"]
    texts = [p.read_text(encoding="utf-8") for p in (ROOT / "deploy").iterdir()]
    texts.append((ROOT / ".env.example").read_text(encoding="utf-8"))
    for t in texts:
        for old in ("/etc/duty_generator", "/var/lib/duty_generator", "/var/log/duty_generator",
                    "/var/backups/duty_generator", "EnvironmentFile"):
            assert old not in t
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    assert ".env" in ignored and "data/" in ignored


def test_no_install_needed():
    """설치(pip install -e .) 없이 저장소 루트에서 돈다: 패키지 정의가 없다."""
    t = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[project]" not in t and "[build-system]" not in t and "[tool.pytest.ini_options]" in t
    assert (ROOT / "requirements.in").exists() and (ROOT / "requirements-dev.txt").exists()
