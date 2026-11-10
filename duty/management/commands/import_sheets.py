from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from duty.importer import DEPLOY_ID, MAKER_ID, download_xlsx, run_import


class Command(BaseCommand):
    help = "구글 시트(제작기 tb_member, 배포용 view_all_combine/근무표)를 1회 가져온다."

    def add_arguments(self, parser):
        parser.add_argument("--maker-xlsx", help="제작기 xlsx 경로 (없으면 공개 URL에서 받음)")
        parser.add_argument("--deploy-xlsx", help="배포용 xlsx 경로 (없으면 공개 URL에서 받음)")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        maker = Path(opts["maker_xlsx"]).read_bytes() if opts["maker_xlsx"] else download_xlsx(MAKER_ID)
        deploy = Path(opts["deploy_xlsx"]).read_bytes() if opts["deploy_xlsx"] else download_xlsx(DEPLOY_ID)
        r = run_import(maker, deploy, opts["dry_run"])
        for e in r.errors:
            self.stderr.write(e)
        self.stdout.write(f"멤버 {r.members}, 날짜 {r.dates}, 출근조 {r.commutes}, 관제 {r.duties}, 변경 {r.changes}")
        if r.errors:
            raise CommandError(f"오류 {len(r.errors)}건 — 반영하지 않았습니다.")
        self.stdout.write("dry-run: 반영하지 않았습니다." if opts["dry_run"] else "가져오기 완료")
