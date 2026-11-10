import urllib.error
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
        maker = self._load(opts["maker_xlsx"], MAKER_ID)
        deploy = self._load(opts["deploy_xlsx"], DEPLOY_ID)
        r = run_import(maker, deploy, opts["dry_run"])
        for e in r.errors:
            self.stderr.write(e)
        self.stdout.write(f"멤버 {r.members}, 날짜 {r.dates}, 출근조 {r.commutes}, 관제 {r.duties}, 변경 {r.changes}")
        if r.errors:
            raise CommandError(f"오류 {len(r.errors)}건 — 반영하지 않았습니다.")
        self.stdout.write("dry-run: 반영하지 않았습니다." if opts["dry_run"] else "가져오기 완료")

    def _load(self, path, sheet_id) -> bytes:
        try:
            data = Path(path).read_bytes() if path else download_xlsx(sheet_id)
        except OSError as e:  # URLError, HTTPError, 시간 초과, 파일 없음
            reason = e.reason if isinstance(e, urllib.error.URLError) else e
            raise CommandError(f"{path or sheet_id}: 읽지 못했습니다 ({reason})")
        if not data.startswith(b"PK"):
            raise CommandError(f"{path or sheet_id}: xlsx가 아닙니다 (시트가 공개 상태인지 확인하세요)")
        return data
