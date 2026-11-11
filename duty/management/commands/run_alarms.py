import fcntl
import logging
import time
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from duty.services import alarm_runner

log = logging.getLogger("duty.alarms")


class Command(BaseCommand):
    help = "개인 알림 발송 루프(1분마다)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="한 번만 실행")
        parser.add_argument("--dry-run", action="store_true", help="발송·기록 없이 채널별 건수만 출력")

    def handle(self, *args, once=False, dry_run=False, **opts):
        with open(settings.ALARMS_LOCK_PATH, "a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | (fcntl.LOCK_NB if once or dry_run else 0))
            except BlockingIOError:
                raise CommandError("다른 run_alarms가 실행 중입니다.", returncode=1) from None
            if dry_run:
                n = Counter(due.channel for due, *_ in alarm_runner.collect(timezone.now()))
                self.stdout.write(f"telegram={n['telegram']} push={n['push']}")
                return
            if once:
                alarm_runner.tick(timezone.now())
                return
            while True:
                try:
                    alarm_runner.tick(timezone.now())
                except Exception:
                    log.exception("alarms tick failed")
                now = timezone.now()
                time.sleep(60 - now.second - now.microsecond / 1e6)
