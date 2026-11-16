"""직접 입력 근무표를 한 번에 만든다(manage.py add_board). 관리 화면 절차(OPERATIONS '근무표 추가하기' 1~4단계)를
한 트랜잭션으로: 근무표·근무 정의·부서 하나·사람(사용할 수 없는 비밀번호)·근무표 관리자. 검사는 관리 화면과 같은 모델 검사를 쓴다."""
import re
from datetime import time

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction

from ..errors import DutyError
from ..models import Board, BoardShift, Department, InputMode, User
from ..shifts import LUNCH, SHIFT_KEYS, STAFF

Span = tuple[time, time]


def parse_span(text: str) -> Span:
    """'07:30-16:30' → (07:30, 16:30). 당일 근무만(시작 < 끝)."""
    m = re.fullmatch(r"(\d{2}):(\d{2})-(\d{2}):(\d{2})", text.strip())
    try:
        start, end = time(int(m[1]), int(m[2])), time(int(m[3]), int(m[4]))
    except (TypeError, ValueError):  # 모양이 틀리면 m 이 None, 25:00 같은 시각은 ValueError
        raise DutyError(f"시각은 HH:MM-HH:MM 으로 적습니다(예: 07:30-16:30): {text}") from None
    if start >= end:
        raise DutyError(f"시작이 끝보다 일러야 합니다(당일 근무만): {text}")
    return start, end


def read_people(text: str) -> list[tuple[int, str]]:
    """명단 파일: 한 줄에 이름 하나. 빈 줄·#로 시작하는 줄은 건너뛰고 앞뒤 공백을 지운다. (줄 번호, 이름)."""
    return [(i, s) for i, line in enumerate(text.splitlines(), 1) if (s := line.strip()) and not s.startswith("#")]


def _msg(e: ValidationError) -> str:
    return " ".join(e.messages)


@transaction.atomic
def create_direct_board(code: str, name: str, shifts: list[Span], lunch: Span | None,
                        people: list[tuple[int, str]], admin_username: str | None = None) -> Board:
    if not 1 <= len(shifts) <= len(SHIFT_KEYS):
        raise DutyError(f"근무조는 1~{len(SHIFT_KEYS)}개입니다.")
    if len({s for s, _ in shifts}) != len(shifts):
        raise DutyError("근무조끼리 시작 시각이 달라야 합니다(가장 이른 조를 하나로 정할 수 있게).")
    if not people:
        raise DutyError("명단 파일에 이름이 없습니다.")
    if Board.objects.filter(code=code).exists():
        raise DutyError(f"이미 있는 근무표 코드입니다: {code}")
    if Board.objects.filter(name=name).exists() or Group.objects.filter(name=f"{name} 근무표 관리").exists():
        raise DutyError(f"같은 이름의 근무표나 관리 그룹이 이미 있습니다: {name}")
    if len(code) > Department._meta.get_field("code").max_length:  # 부서 코드로도 쓴다
        raise DutyError("코드는 8자 이내로 적습니다(부서 코드로도 씁니다).")
    admin = None
    if admin_username:
        admin = User.objects.filter(username=admin_username).first()
        if admin is None:
            raise DutyError(f"근무표 관리자로 넣을 아이디가 없습니다: {admin_username}")

    board = Board(code=code, name=name, input_mode=InputMode.DIRECT)
    try:
        board.full_clean(exclude=["admin_group"])
        board.save()
        keys = SHIFT_KEYS[:len(shifts)]
        for key, (start, end) in zip(keys, shifts):
            s = BoardShift(board=board, key=key, name=start.strftime("%H:%M"), start=start, end=end, default_alarm=True)
            s.full_clean()
            s.save()
        BoardShift.objects.create(board=board, key=LUNCH, name="점심당번")
        dept = Department(code=code, name=name, shifts=",".join(keys), board=board,
                          lunch_start=lunch and lunch[0], lunch_end=lunch and lunch[1])
        dept.full_clean()
        dept.save()
    except ValidationError as e:
        raise DutyError(_msg(e)) from None

    width = max(2, len(str(len(people))))
    errors = []
    for n, (line, person) in enumerate(people, 1):
        username = f"{code}{n:0{width}d}"
        if User.objects.filter(username__iexact=username).exists():  # 관리 화면 UserAddForm 과 같다
            errors.append(f"{line}번째 줄: 아이디 {username} 가 이미 있습니다(대소문자 구분 없음).")
            continue
        user = User(username=username, name=person, department=dept, type=STAFF)
        user.set_unusable_password()  # 비밀번호는 관리 화면 액션 '계정 발급 / 비밀번호 초기화'로
        try:
            user.full_clean()  # 이름 규칙(validate_member_name)·길이·겹침(앞줄 포함: 앞줄은 이미 저장됐다)
        except ValidationError as e:
            errors.append(f"{line}번째 줄: {_msg(e)}")  # 이름(실명)은 오류에도 남기지 않는다
            continue
        user.save()
    if errors:
        raise DutyError("명단에 문제가 있어 아무것도 만들지 않았습니다.\n" + "\n".join(errors))  # 트랜잭션이 되돌린다
    if admin:
        admin.groups.add(board.admin_group)
    return board
