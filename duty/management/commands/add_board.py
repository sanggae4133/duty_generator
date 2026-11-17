import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from duty.errors import DutyError
from duty.services import board_setup


class Command(BaseCommand):
    help = ("근무표 관리자가 출근표를 넣는 근무표(예: 시장운영실, 단계 입력 중 → 확정 → 배포됨)를 한 번에 만든다: "
            "근무표·근무 정의·부서·사람 계정(비밀번호 없이)·근무표 관리자. 하나라도 문제가 있으면 아무것도 만들지 않는다.")
    stealth_options = ("stdin",)  # 테스트가 call_command(stdin=...)로 명단을 넘긴다

    def add_arguments(self, parser):
        parser.add_argument("code", help="근무표 코드(영문 소문자로 시작, 8자 이내). 부서 코드·아이디 앞부분으로도 쓴다")
        parser.add_argument("name", help="근무표 이름(부서 이름으로도 쓴다)")
        parser.add_argument("--shifts", required=True, help="근무조 시각, 쉼표로(최대 4개). 예: 07:30-16:30,09:00-18:00")
        parser.add_argument("--lunch", help="부서 점심 시각. 예: 11:30-12:30 (없으면 비워 둔다)")
        parser.add_argument("--people", required=True, help="명단 파일(UTF-8, 한 줄에 이름 하나, 빈 줄·# 줄은 건너뜀). - 는 표준 입력")
        parser.add_argument("--admin", help="근무표 관리 그룹에 넣을 기존 사용자 아이디")

    def handle(self, *args, **o):
        try:
            shifts = [board_setup.parse_span(s) for s in o["shifts"].split(",")]
            try:
                lunch = board_setup.parse_span(o["lunch"]) if o["lunch"] else None
            except DutyError as e:
                raise DutyError(f"점심 {e}") from None
            try:
                # '-' = 표준 입력: 운영자가 자기 홈의 명단을 '< ~/mops.txt' 로 넘겨 duty 사용자는 파일을 읽지 않는다
                if o["people"] == "-":
                    src = o.get("stdin") or sys.stdin
                    text = src.buffer.read().decode("utf-8") if hasattr(src, "buffer") else src.read()  # 로캘과 상관없이 UTF-8
                else:
                    text = Path(o["people"]).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                raise DutyError(f"명단 파일을 읽을 수 없습니다(UTF-8 텍스트인지 보세요): {e.__class__.__name__}") from None
            board = board_setup.create_board(o["code"], o["name"], shifts, lunch,
                                             board_setup.read_people(text), o["admin"])
        except DutyError as e:
            raise CommandError(str(e)) from None

        dept = board.departments.get()
        ids = list(dept.members.order_by("username").values_list("username", flat=True))
        shift_txt = ", ".join(f"{s.name}({s.start:%H:%M}~{s.end:%H:%M})"
                              for s in board.shifts.exclude(key="lunch").order_by("start"))
        lunch_txt = f"{dept.lunch_start:%H:%M}~{dept.lunch_end:%H:%M}" if dept.lunch_start else "비움"
        admin_txt = f"{o['admin']} 를 '{board.admin_group.name}' 그룹에 넣음" if o["admin"] else "없음(나중에 관리 화면에서)"
        self.stdout.write("\n".join([
            f"근무표를 만들었습니다: {board.name} (코드 {board.code}, 단계 {' → '.join(board.step_name(s) for s in board.steps())})",
            f"근무조: {shift_txt} · 점심당번",
            f"부서: {dept.name} (코드 {dept.code}), 점심 시각: {lunch_txt}",
            f"계정: {len(ids)}명, {ids[0]}~{ids[-1]} (비밀번호 없음)",
            f"근무표 관리자: {admin_txt}",
            "다음 할 일:",
            "  1. 관리 화면 → 사용자 → 이 사람들을 체크 → 액션 '계정 발급 / 비밀번호 초기화' → 임시 비밀번호를 사람마다 따로 전달",
            "  2. 아이디는 임시입니다. 바꾸려면 관리 화면 → 사용자에서 고칩니다(계정 발급 전에 하는 편이 낫습니다)",
            "  3. 근무표 관리자가 첫 회차를 만들고 배포합니다(OPERATIONS.md '근무표 추가하기' 5단계)",
            "  명단 파일은 실명이 들어 있으니 지웁니다.",
        ]))
