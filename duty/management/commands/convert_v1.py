from django.core.management.base import BaseCommand, CommandError

from duty.services import convert_v1


class Command(BaseCommand):
    help = "예전(duty 0001~0009) DB 백업 파일을 지금 DB(migrate 만 한 빈 새 DB)로 옮긴다. 1회용."

    def add_arguments(self, parser):
        parser.add_argument("source", help="예전 DB 백업 파일(sqlite3 .backup 으로 만든 단일 파일)")

    def handle(self, *args, source, **opts):
        try:
            convert_v1.convert(source, self.stdout.write)
        except convert_v1.ConvertError as e:
            raise CommandError(f"변환하지 않았습니다(아무것도 쓰지 않음): {e}") from None
        self.stdout.write("변환을 마쳤습니다.")
