"""작업자: 웹과 따로 도는 프로세스 하나(deploy/duty-worker.service). 1분마다 한 바퀴.

- 알림 발송: 매분(alarm_runner.tick)
- DB 백업: 하루 한 번, BACKUP_HOUR 시 이후(backup.daily)
- 상태 점검: 5분마다(health.check)
한 작업이 실패해도 로그만 남기고 다른 작업과 다음 바퀴는 계속 돈다.
"""
import fcntl
import logging
import time
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from duty.logging import log_to_file
from duty.services import alarm_runner, backup, health

log = logging.getLogger("duty.worker")
HEALTH_EVERY = 5  # 분


def run_round(now, everything=False) -> None:
    jobs = [("alarms", alarm_runner.tick), ("backup", backup.daily)]
    if everything or timezone.localtime(now).minute % HEALTH_EVERY == 0:
        jobs.append(("health", health.check))
    for name, job in jobs:
        try:
            job(now)
        except Exception:
            log.exception("worker job failed: %s", name)


class Command(BaseCommand):
    help = "작업자(알림 발송·매일 백업·상태 점검). 1분마다 돈다."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="모든 작업을 한 번만 실행")
        parser.add_argument("--dry-run", action="store_true",
                            help="지금 보낼 알림 건수만 출력(발송·기록 없음, 작업자가 도는 중에도 된다)")

    def handle(self, *args, once=False, dry_run=False, **opts):
        if dry_run:
            n = Counter(due.channel for due, *_ in alarm_runner.collect(timezone.now()))
            self.stdout.write(f"telegram={n['telegram']} push={n['push']}")
            return
        with open(settings.ALARMS_LOCK_PATH, "a") as lock:  # 작업자는 하나만(같은 알림 두 번 발송 방지)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | (fcntl.LOCK_NB if once else 0))
            except BlockingIOError:
                raise CommandError("다른 run_worker가 실행 중입니다.", returncode=1) from None
            log_to_file("worker")
            if once:
                run_round(timezone.now(), everything=True)
                return
            log.info("worker started")
            while True:
                run_round(timezone.now())
                now = timezone.now()
                time.sleep(60 - now.second - now.microsecond / 1e6)
