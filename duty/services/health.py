"""상태 점검(run_worker 가 5분마다): 웹 응답·최근 백업·디스크.
상태가 바뀔 때만(문제 생김 / 정상 복귀) 알림 설정의 ops_chat_id 로 텔레그램을 보낸다. 비어 있으면 로그만.
마지막 상태는 data/.health.state. 발송에 실패하면 상태를 저장하지 않아 다음 점검에서 다시 보낸다.
"""
import logging
import shutil
import socket
import urllib.request
from pathlib import Path

from django.conf import settings

from ..alarms import senders
from . import alarm_settings, backup

log = logging.getLogger(__name__)
WEB_URL = "http://127.0.0.1:8090/login/"  # deploy/duty-web.service 의 --bind 와 같아야 한다
DISK_LIMIT = 90


def _web_ok() -> bool:
    try:
        with urllib.request.urlopen(WEB_URL, timeout=10):
            return True
    except (OSError, ValueError):  # URLError·HTTPError(4xx/5xx)·timeout
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
    if not backup.has_recent():
        out.append("26시간 안에 만든 백업 없음")
    use = _disk_percent(settings.DATA_DIR)
    if use is None:
        out.append("디스크 확인 실패")
    elif use >= DISK_LIMIT:
        out.append(f"디스크 {use}% 사용")
    return "".join(f" {p};" for p in out)


def check(now) -> None:
    state = Path(settings.DATA_DIR) / ".health.state"
    found = problems()
    if not state.exists() and not found:  # 첫 점검이 정상이면 기록만(알림 없음)
        log.info("health: 정상(점검 시작)")
        state.write_text("", encoding="utf-8")
        return
    if state.exists() and state.read_text(encoding="utf-8") == found:
        return
    if found:
        log.warning("health:%s", found)
    else:
        log.info("health: 정상")
    conf = alarm_settings.current()
    if conf.ops_chat_id and conf.telegram_on:
        text = f"[당번표 {socket.gethostname()}]{found or ' 정상으로 돌아왔습니다.'}"
        senders.telegram_send(conf.sender_config(), str(conf.ops_chat_id), text)  # 실패는 예외 → 상태 저장 안 함
    state.write_text(found, encoding="utf-8")
