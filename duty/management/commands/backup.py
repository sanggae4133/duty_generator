from django.core.management.base import BaseCommand
from django.utils import timezone

from duty.services import backup


class Command(BaseCommand):
    help = "지금 DB 를 data/backups/db-YYYYMMDD-HHMMSS.sqlite3 로 백업한다(서비스가 도는 중에도 된다)."

    def handle(self, *args, **opts):
        self.stdout.write(f"백업: {backup.backup_now(timezone.now())}")
