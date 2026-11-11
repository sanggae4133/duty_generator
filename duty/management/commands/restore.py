from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from duty.errors import DutyError
from duty.services import backup


class Command(BaseCommand):
    help = ("백업 파일로 DB 를 바꾼다. 먼저 sudo systemctl stop duty-web duty-worker. "
            "지금 DB 는 data/backups/before-restore-*.sqlite3 로 남는다.")

    def add_arguments(self, parser):
        parser.add_argument("file", help="백업 파일(절대 경로 권장)")

    def handle(self, *args, file, **opts):
        try:
            before = backup.restore(file, timezone.now())
        except DutyError as e:
            raise CommandError(f"복원하지 않았습니다(아무것도 바꾸지 않음): {e}") from None
        self.stdout.write(f"복원했습니다: {file}")
        if before:
            self.stdout.write(f"복원 직전 DB: {before}")
        self.stdout.write("이제 migrate 를 실행하고 서비스를 시작하세요(README \"백업·복원\").")
