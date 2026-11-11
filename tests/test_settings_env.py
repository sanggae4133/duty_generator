"""루트 .env 읽기(config/settings.py)와 deploy/.env.example 정합성."""
import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

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
    monkeypatch.setattr(os, "environ", {"DUTY_ENV_FILE": str(f)})
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
    names = set(re.findall(r'env\("(DUTY_[A-Z_]+)"', (ROOT / "config/settings.py").read_text(encoding="utf-8")))
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    listed = set(re.findall(r"^#? ?(DUTY_[A-Z_]+)=", example, re.M))
    assert names and names <= listed, names - listed


def test_deploy_files_use_root_env():
    assert not (ROOT / "deploy/env.example").exists()
    for p in (ROOT / "deploy").iterdir():
        assert "/etc/duty_generator" not in p.read_text(encoding="utf-8"), p.name
    assert ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8").split()
