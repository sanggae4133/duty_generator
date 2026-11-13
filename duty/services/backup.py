"""DB 백업·복원(data/backups/). 백업은 SQLite 백업 API 로 뜬다(WAL 까지 담긴 일관된 단일 파일, 서비스가 도는 중에도 안전).

- 매일: run_worker 가 BACKUP_HOUR 시 이후 처음 돌 때 db-YYYYMMDD.sqlite3, 그 뒤 BACKUP_KEEP_DAYS 일보다 오래된 db-* 정리
- 손으로: manage.py backup → db-YYYYMMDD-HHMMSS.sqlite3 (같은 보관 규칙)
- 복원: manage.py restore <파일> → 지금 DB 를 before-restore-*.sqlite3 로 남기고 교체(이 파일들은 지우지 않는다)
"""
import fcntl
import logging
import os
import time
import re
import sqlite3
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.utils import timezone

from ..errors import DutyError

log = logging.getLogger(__name__)
DATED = re.compile(r"db-(\d{8})(?:-\d{6})?\.sqlite3")


def copy_db(src: Path, dest: Path) -> None:
    """src(읽기 전용으로 연다)를 dest 로. 임시 파일에 다 쓴 뒤 이름을 바꿔 반쯤 쓴 파일이 남지 않게."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    # 고유 이름에 처음부터 600(실명·해시가 들어간다). 실패하면 어느 단계든 지운다
    fd, name = tempfile.mkstemp(dir=dest.parent, prefix=dest.name + ".", suffix=".tmp")
    tmp = Path(name)
    try:
        os.close(fd)
        _backup_to(src, tmp)
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _backup_to(src: Path, tmp: Path) -> None:
    s = sqlite3.connect(f"{Path(src).resolve().as_uri()}?mode=ro", uri=True)
    try:
        d = sqlite3.connect(tmp)
        try:
            s.backup(d)
            # 세션 키가 있으면 백업을 얻은 사람이 비밀번호 없이 로그인된다 → 지운다(흔적도 남지 않게 secure_delete)
            if d.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='django_session'").fetchone():
                d.execute("PRAGMA secure_delete=ON")
                d.execute("DELETE FROM django_session")
                d.commit()
            d.execute("PRAGMA journal_mode=DELETE")  # 백업은 단일 파일로(읽기 전용으로 열어도 -wal·-shm 이 안 생기게)
        finally:
            d.close()
    finally:
        s.close()


def prune(today: date) -> None:
    cutoff = today - timedelta(days=settings.BACKUP_KEEP_DAYS)
    for p in settings.BACKUP_DIR.glob("db-*.sqlite3"):
        m = DATED.fullmatch(p.name)
        if m and datetime.strptime(m[1], "%Y%m%d").date() < cutoff:
            p.unlink()


def backup_now(now) -> Path:
    dest = settings.BACKUP_DIR / f"db-{timezone.localtime(now):%Y%m%d-%H%M%S}.sqlite3"
    copy_db(settings.DB_PATH, dest)
    return dest


RECENT = 26 * 3600  # 상태 점검의 "최근 백업" 기준과 같다


def has_recent() -> bool:
    """RECENT 안에 만든 db-* 백업이 있는가(파일 수정 시각 기준)."""
    cutoff = time.time() - RECENT
    try:
        return any(p.stat().st_mtime >= cutoff for p in Path(settings.BACKUP_DIR).glob("db-*.sqlite3"))
    except OSError:
        return False


def daily(now) -> Path | None:
    """오늘 백업이 없고 BACKUP_HOUR 시가 지났으면 만든다(늦게 켜져도 그날 안에 따라잡음).
    최근(26시간 안) 백업이 하나도 없으면(새 설치·오래 꺼져 있었음) 시각과 상관없이 바로 만든다."""
    local = timezone.localtime(now)
    dest = settings.BACKUP_DIR / f"db-{local:%Y%m%d}.sqlite3"
    if dest.exists() or (local.hour < settings.BACKUP_HOUR and has_recent()):
        return None
    copy_db(settings.DB_PATH, dest)
    prune(local.date())
    log.info("backup: %s", dest.name)
    return dest


def _code_migrations() -> set[tuple[str, str]]:
    """지금 코드로 migrate 한 DB 의 django_migrations 에 남는 (앱, 이름) 전부."""
    out = set()
    for key, m in MigrationLoader(None, ignore_no_migrations=True).graph.nodes.items():
        out |= set(m.replaces) if m.replaces else {key}
    return out


def check(src: Path) -> None:
    """복원해도 되는 백업인가: 손상 없음, 마이그레이션이 지금 코드와 같음."""
    if not src.is_file():
        raise DutyError(f"백업 파일이 없습니다: {src}")
    if src.resolve() == Path(settings.DB_PATH).resolve():
        raise DutyError("지금 DB 파일 자체는 복원할 수 없습니다. data/backups/ 의 백업 파일을 주세요.")
    try:
        con = sqlite3.connect(f"{src.resolve().as_uri()}?mode=ro", uri=True)
        try:
            ok = con.execute("PRAGMA quick_check").fetchall() == [("ok",)]
            applied = set(con.execute("SELECT app, name FROM django_migrations").fetchall()) if ok else set()
        finally:
            con.close()
    except sqlite3.DatabaseError:
        ok = False
    if not ok:
        raise DutyError("백업 파일 검사(quick_check) 실패: 손상됐거나 SQLite 파일이 아닙니다.")
    if applied != _code_migrations():
        raise DutyError("백업의 마이그레이션이 지금 코드와 다릅니다. 그 백업을 만든 버전의 코드로 바꾼 뒤 복원하세요"
                        "(docs/OPERATIONS.md \"업그레이드·롤백\").")


def restore(src: Path, now) -> Path | None:
    """검사 → 지금 DB 를 before-restore-*.sqlite3 로 → -wal/-shm 삭제 → 교체. 서비스는 멈춘 상태여야 한다.
    돌려주는 값: 복원 직전 DB 백업 경로(지금 DB 가 없었으면 None)."""
    src = Path(src)
    with open(settings.ALARMS_LOCK_PATH, "a") as lock:  # 끝날 때까지 잡고 있어 그동안 작업자가 뜨지 못한다
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DutyError("작업자가 돌고 있습니다. sudo systemctl stop duty-web duty-worker 후 다시 하세요.") from None
        check(src)
        connection.close()
        db = Path(settings.DB_PATH)
        before = None
        if db.exists():
            before = settings.BACKUP_DIR / f"before-restore-{timezone.localtime(now):%Y%m%d-%H%M%S}.sqlite3"
            copy_db(db, before)
        for suffix in ("-wal", "-shm"):  # 남은 WAL 이 새 파일에 덮어써지지 않게
            Path(f"{db}{suffix}").unlink(missing_ok=True)
        copy_db(src, db)
        return before
