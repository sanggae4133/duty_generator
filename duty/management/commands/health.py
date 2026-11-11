"""상태 점검(duty-health.timer 가 5분마다): 웹 응답·알림 서비스·최근 백업·디스크.
상태가 바뀔 때만(문제 생김 / 정상 복귀) 알림 설정의 ops_chat_id 로 텔레그램을 보낸다. 비어 있으면 기록만.
"""
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from duty.alarms import senders
from duty.services import alarm_settings

WEB_URL = "http://127.0.0.1:8090/login/"
BACKUP_DIR = Path("/var/backups/duty_generator")
BACKUP_MAX_AGE = 26 * 3600
DISK_LIMIT = 90


def _web_ok() -> bool:
    try:
        with urllib.request.urlopen(WEB_URL, timeout=10):
            return True
    except (OSError, ValueError):  # URLError·HTTPError(4xx/5xx)·timeout
        return False


def _systemctl(*args) -> bool:
    try:
        return subprocess.run(["systemctl", *args], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _recent_backup() -> bool:
    cutoff = time.time() - BACKUP_MAX_AGE
    try:
        return any(p.stat().st_mtime >= cutoff for p in BACKUP_DIR.glob("db-*.sqlite3"))
    except OSError:
        return False


def _disk_percent(path) -> int | None:
    """df 의 사용률과 같은 계산(used / (used + free), 올림). 실패하면 None."""
    try:
        u = shutil.disk_usage(path)
    except OSError:
        return None
    return -(-u.used * 100 // (u.used + u.free)) if u.used + u.free else None


def problems() -> str:
    out = []
    if not _web_ok():
        out.append("웹 응답 없음")
    if _systemctl("is-enabled", "-q", "duty-alarms") and not _systemctl("is-active", "-q", "duty-alarms"):
        out.append("알림 서비스 멈춤")
    if not _recent_backup():
        out.append("26시간 안에 만든 백업 없음")
    use = _disk_percent(Path(settings.DB_PATH).parent)
    if use is None:
        out.append("디스크 확인 실패")
    elif use >= DISK_LIMIT:
        out.append(f"디스크 {use}% 사용")
    return "".join(f" {p};" for p in out)


class Command(BaseCommand):
    help = "상태 점검. 상태가 바뀔 때만 관리자 텔레그램으로 알린다."

    def handle(self, *args, **opts):
        state = Path(settings.DB_PATH).parent / ".health.state"
        now = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")
        found = problems()
        if not state.exists() and not found:  # 첫 실행이 정상이면 기록만(알림 없음)
            self.stdout.write(f"{now} health: 정상(점검 시작)")
            state.write_text("", encoding="utf-8")
            return
        if state.exists() and state.read_text(encoding="utf-8") == found:
            return
        self.stdout.write(f"{now} health:{found or ' 정상'}")
        conf = alarm_settings.current()
        if conf.ops_chat_id and conf.telegram_on:
            text = f"[당번표 {socket.gethostname()}]{found or ' 정상으로 돌아왔습니다.'}"
            try:
                senders.telegram_send(conf.sender_config(), str(conf.ops_chat_id), text)
            except senders.SendError as e:  # 상태를 저장하지 않고 다음 번에 다시 보낸다
                raise CommandError(f"장애 알림 발송 실패({type(e).__name__}:{e.status})") from None
        state.write_text(found, encoding="utf-8")
