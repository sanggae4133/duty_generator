"""[근무표 설정](근무표 통합 설계 6.2): 근무표 관리자가 그 근무표의 사람·관리자·입력 담당자·근무 정의와 부서·회차 단계를 고친다.
모든 함수는 그 근무표 관리자만 부르고(첫 줄 _require_admin), 받은 부서·사람이 그 근무표 것인지 다시 본다(아니면 PermissionDenied,
뷰는 404). 쓰기마다 로그 한 줄과 Django LogEntry 한 줄을 남긴다(아이디·부서 코드·근무표 code 만, 실명·비밀번호 없음)."""
import logging
import re
from datetime import date

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q

from .. import accounts, perms
from ..errors import DutyError
from ..models import Board, BoardShift, Commute, Department, DutyAssignment, Period, User
from ..shifts import DEVELOPER, SHIFT_KEYS, STAFF, is_slot_cell, josa, shift_defs
from . import boards, prefs

log = logging.getLogger(__name__)

S = Period.Status
BEFORE_PUBLISH = [S.DRAFT, S.COLLECTING, S.CLOSED, S.GENERATED]
INVALID = "저장하지 않았습니다. 빨간 글씨로 표시한 칸을 고쳐 주세요."
STALE = "화면을 연 뒤 근무 정의나 부서가 바뀌었습니다. 저장하지 않았습니다. 근무표 설정 화면을 다시 열어 주세요."
NO_ADMIN_LEFT = "재직 중인 관리자가 아무도 남지 않습니다. 회차·배포·설정을 할 사람이 없으니 다른 사람을 먼저 넣으세요."


def _require_admin(by, board) -> None:
    if not perms.is_board_admin(by, board):
        raise PermissionDenied("이 근무표 관리자가 아닙니다.")


def _audit(by, board, obj, target: str, action: str) -> None:
    """로그 한 줄 + LogEntry 한 줄(관리 화면에서 그 사람·부서·근무표 편집 페이지의 [기록]에 보인다).
    Django 의 log_actions 는 object_repr 에 str(obj)(= 사람 실명)를 넣으므로 쓰지 않고 아이디·코드를 직접 넣는다."""
    log.info("board %s: %s %s by %s", board.code, action, target, by.username)
    LogEntry.objects.create(user=by, content_type=ContentType.objects.get_for_model(obj), object_id=str(obj.pk),
                            object_repr=target, action_flag=CHANGE, change_message=f"근무표 {board.code}: {action}")


def admin_candidates(board):
    """관리자 넣기 후보: 재직 중이고 그 근무표 부서 사람이거나 부서 없는 계정, 이미 관리자인 사람은 빼고, 이름 순.
    다른 근무표 사람은 넣지 않는다(필요하면 슈퍼유저가 관리 화면에서)."""
    return (User.objects.filter(is_active=True).filter(Q(department__board=board) | Q(department__isnull=True))
            .exclude(groups=board.admin_group_id).select_related("department").order_by("name"))


def assignee_candidates(board, dept):
    """입력 담당자 넣기 후보: 그 근무표 부서의 재직자, 이미 담당자인 사람은 빼고, 이름 순."""
    qs = User.objects.roster().filter(department__board=board).select_related("department")
    if dept.input_group_id:
        qs = qs.exclude(groups=dept.input_group_id)
    return qs.order_by("name")


def _dept(board, dept) -> Department:
    """트랜잭션 안에서 부서를 다시 읽고 그 근무표 부서인지 본다(IDOR)."""
    dept = Department.objects.select_related("input_group").get(pk=dept.pk)
    if dept.board_id != board.pk:
        raise PermissionDenied("이 근무표의 부서가 아닙니다.")
    return dept


@transaction.atomic
def add_admin(by, board, user) -> None:
    _require_admin(by, board)
    if not admin_candidates(board).filter(pk=user.pk).exists():
        raise PermissionDenied("관리자로 넣을 수 없는 사람입니다.")
    board.admin_group.user_set.add(user)
    _audit(by, board, user, user.username, "관리자 넣기")


@transaction.atomic
def remove_admin(by, board, user) -> None:
    """나 자신이나 퇴사한 관리자만 뺀다. 재직 중인 다른 관리자 빼기는 슈퍼유저(관리 화면): 빼고 나서 그 계정을 다루는 우회를 막는다."""
    _require_admin(by, board)
    user = User.objects.get(pk=user.pk)  # 재직 여부는 DB 에서
    if not board.admin_group.user_set.filter(pk=user.pk).exists():
        raise PermissionDenied("이 근무표 관리자가 아닙니다.")
    if user.pk != by.pk and user.is_active:
        raise PermissionDenied("재직 중인 다른 관리자는 슈퍼유저가 관리 화면에서 뺍니다.")
    if board in boards.left_without_admin([user]):
        raise DutyError(NO_ADMIN_LEFT)
    board.admin_group.user_set.remove(user)
    _audit(by, board, user, user.username, "관리자 빼기")


@transaction.atomic
def add_assignee(by, board, dept, user) -> None:
    """부서 입력 그룹에 넣는다. 첫 담당자면 그룹을 만든다(이름이 겹치면 DutyError)."""
    _require_admin(by, board)
    dept = _dept(board, dept)
    if not assignee_candidates(board, dept).filter(pk=user.pk).exists():
        raise PermissionDenied("입력 담당자로 넣을 수 없는 사람입니다.")
    dept.ensure_input_group().user_set.add(user)
    _audit(by, board, user, user.username, f"{dept.code} 입력 담당자 넣기")


@transaction.atomic
def remove_assignee(by, board, dept, user) -> None:
    """부서 입력 그룹에서 뺀다(퇴사자도). 담당자가 하나도 없으면 그 부서는 근무표 관리자만 입력한다."""
    _require_admin(by, board)
    dept = _dept(board, dept)
    if not (dept.input_group_id and dept.input_group.user_set.filter(pk=user.pk).exists()):
        raise PermissionDenied("이 부서의 입력 담당자가 아닙니다.")
    dept.input_group.user_set.remove(user)
    _audit(by, board, user, user.username, f"{dept.code} 입력 담당자 빼기")


class Stale(DutyError):
    """화면을 연 뒤 근무 정의·부서가 바뀌어 저장하지 않았다: 화면은 보낸 값 대신 새로 읽은 설정을 보인다."""


class NeedsConfirm(DutyError):
    """저장하지 않고 한 번 더 묻는다: 화면이 글을 보이고 [그래도 저장]이 rows 를 confirm 으로 다시 보낸다
    (메모의 근무 없음 확인과 같은 방식: 그사이 rows 가 바뀌면 다시 묻는다)."""

    def __init__(self, message: str, rows: int):
        super().__init__(message)
        self.rows = rows


def set_memo_notice(by, board, on: bool) -> None:
    """메모 알림 켜기·끄기(근무표 관리자). 켜면 메모를 새로 달거나 고칠 때 그 근무표 사람 모두에게 간다."""
    _require_admin(by, board)
    type(board).objects.filter(pk=board.pk).update(notify_memos=on)
    _audit(by, board, board, board.code, "메모 알림 " + ("켬" if on else "끔"))


def stranded(board) -> str:
    """끈 단계에 남은 회차 안내(설계 5.1·6.2). 없으면 빈 글자. 단계 저장 결과(설정 화면·관리 화면)에 쓴다."""
    on = board.steps()
    lines = [f"'{board.step_name(s)}' 단계에 회차 {n}개가 남아 있습니다." for s in (S.DRAFT, S.CLOSED)
             if s not in on and (n := Period.objects.filter(board=board, status=s).count())]
    return " ".join(lines) + " 회차 화면에서 다른 단계로 옮기세요." if lines else ""


@transaction.atomic
def save_steps(by, board, form) -> str:
    """회차 단계 칸 저장(form = forms.StepsForm, instance 는 그 근무표를 새로 읽은 것). 끈 단계에 회차가 남으면 그 안내를 돌려준다."""
    _require_admin(by, board)
    if form.instance.pk != board.pk:
        raise PermissionDenied("이 근무표의 단계가 아닙니다.")
    if not form.is_valid():
        raise DutyError(INVALID)
    # 단계 칸만 쓴다: Board.save 를 거치면 폼의 낡은 이름으로 관리 그룹 이름을 되돌릴 수 있다(그사이 바뀐 다른 칸을 덮지 않게)
    Board.objects.filter(pk=board.pk).update(**{f: form.cleaned_data[f] for f in form.Meta.fields})
    _audit(by, board, board, board.code, "회차 단계 저장")
    return stranded(form.instance)


def _names(keys, labels) -> str:
    """'이른'·'늦은'을 처럼 이름을 잇고 끝 이름에 맞는 '을/를'."""
    names = [labels[k] for k in keys]
    return "·".join(f"'{n}'" for n in names) + josa(names[-1], "을/를")


@transaction.atomic
def save_shifts(by, board, formset, dept_forms, confirm: int | None = None) -> list[str]:
    """근무 정의(formset = forms.BoardShiftFormSet, instance=board)와 부서 출근조·점심 시각(dept_forms = 그 근무표 부서마다
    forms.DeptShiftsForm)을 한 트랜잭션으로 저장한다(설계 6.2). 돌려주는 것 = 저장한 뒤 보일 경고 글들.
    - 표 전체 검사의 '부서마다 켜진 입력 근무조 하나 이상'은 이번에 저장할 부서 출근조로 본다(같은 저장에서 근무조를 끄고 옮길 수 있게).
    - 부서에서 근무조를 빼는데(같은 저장에서 끄면서 빼도) 배포 전 회차에 그 부서·근무조 출근표가 있으면 저장하지 않고
      NeedsConfirm(confirm = 본 행 수).
    - 생성됨 회차에 배정이 남은 장중관제 정의를 끄면 저장하고 경고."""
    _require_admin(by, board)
    if formset.instance.pk != board.pk or any(f.instance.board_id != board.pk for f in dept_forms):
        raise PermissionDenied("이 근무표의 근무 정의·부서가 아닙니다.")
    # 표 전체 검사는 보낸 행만 본다: 행을 빼고 보냈거나 화면을 연 뒤 정의·부서가 생겼으면 그 행이 검사에서 빠지므로 저장하지 않는다.
    # 부서 폼은 요청 때 DB 에서 만드니, 화면이 그린 부서인지는 늘 보내는 숨은 칸(d-<코드>-shown)으로 본다
    if ({f.instance.pk for f in formset.initial_forms} != set(board.shifts.values_list("pk", flat=True))
            or {f.instance.pk for f in dept_forms} != set(board.departments.values_list("pk", flat=True))
            or any(f.add_prefix("shown") not in f.data for f in dept_forms)):
        raise Stale(STALE)
    # 부서 출근조는 트랜잭션 안에서 다시 읽는다(화면이 그린 뒤 바뀌었을 수 있다, 설계 6.2). 화면에는 그린 때 켜진 근무조만
    # 체크박스로 나오므로, 나오지 않은 키(꺼진 근무조, 그린 뒤 다른 관리자가 켠 근무조)는 그대로 둔다: 다시 켜면 그 부서 입력 표 칸이 돌아온다
    saved = {code: set(keys.split(",")) - {""} for code, keys in board.departments.values_list("code", "shifts")}
    hidden = {f.instance.pk: saved[f.instance.pk] - f.shown() for f in dept_forms}
    depts_ok = all([f.is_valid() for f in dept_forms])  # 모든 부서의 오류를 한 번에 보이게(목록으로 다 돌린다)
    picked = {f.instance.pk: set(f.cleaned_data["shifts"]) | hidden[f.instance.pk] for f in dept_forms} if depts_ok else {}
    # 부서 칸이 틀리면 부서 검사는 건너뛴다({}): 저장된 출근조로 보면 관리 화면용 안내가 나온다
    formset.planned_depts = {f.instance.name: picked[f.instance.pk] for f in dept_forms} if depts_ok else {}
    if not (formset.is_valid() and depts_ok):
        raise DutyError(INVALID)
    rows = [f.cleaned_data for f in formset.forms if f.cleaned_data.get("key")]
    labels = {r["key"]: r["name"] for r in rows}
    lost, total = [], 0
    # 끄면서 빼도 묻는다: 꺼진 동안은 행이 남지만(collect._kept_keys) 다시 켜면 다음 표 저장이 지운다.
    # 그린 때 이미 꺼져 있던 키는 체크박스가 없어 picked 에 남으므로(hidden) 여기 걸리지 않는다
    for f in dept_forms:
        gone = [k for k in SHIFT_KEYS if k in saved[f.instance.pk] - picked[f.instance.pk]]
        qs = Commute.objects.filter(period__board=board, period__status__in=BEFORE_PUBLISH, member__department=f.instance,
                                    shift__in=gone)
        if gone and (n := qs.count()):
            names = ", ".join(sorted(set(qs.values_list("period__name", flat=True))))
            lost.append(f"{f.instance.name} 부서에서 {_names(gone, labels)} 빼면 배포 전 회차({names})의 "
                        f"그 근무조 출근표 {n}행이 다음 표 저장 때 지워집니다.")
            total += n
    if total and confirm != total:
        raise NeedsConfirm(" ".join(lost) + " 그래도 저장하려면 [그래도 저장]을 누르세요.", total)
    was_on = dict(BoardShift.objects.filter(board=board).values_list("key", "active"))
    turned_off = [r for r in rows if is_slot_cell(r["key"]) and was_on.get(r["key"]) and not r["active"]]
    formset.save()
    order = [x.key for x in shift_defs(boards.defs(board))]  # 부서 출근조는 시작 시각 순 쉼표 글자(입력 표 칸 순서)
    for f in dept_forms:
        dept = f.save(commit=False)
        dept.shifts = ",".join(k for k in order if k in picked[f.instance.pk])
        dept.save(update_fields=["shifts", "lunch_start", "lunch_end"])  # 이 세 칸만(그사이 생긴 입력 그룹 연결 등을 덮지 않게)
    generated = board.step_name(S.GENERATED)
    warnings = [f"{generated} 회차({name})에 '{r['name']}' 배정 {n}개가 남아 있습니다. "
                "다시 생성하거나 다른 상태로 옮기면 지워지고, 그대로 배포하면 근무표에 나옵니다."
                for r in turned_off
                for name, n in DutyAssignment.objects.filter(period__board=board, period__status=S.GENERATED, cell=r["key"])
                .values_list("period__name").annotate(n=Count("id")).order_by("period__name")]
    _audit(by, board, board, board.code, "근무 정의·부서 저장")
    return warnings


# ── 사람(근무표 통합 4단계, 설계 5.7·6.2) ──

USERNAME_RE = re.compile(r"[a-z][a-z0-9_]{1,29}")
BAD_USERNAME = "아이디는 영문 소문자로 시작하고 영문 소문자·숫자·_ 로만 씁니다(예: ops07)."
SAME_NAME = "이름: 같은 이름이 이미 있습니다(퇴사한 사람·다른 근무표 포함). 동명이인은 이름 뒤에 부서나 숫자를 붙여 구별합니다."


def locked_ids() -> set[int]:
    """사람 함수(set_person·set_active·issue)의 대상이 아닌 계정: 슈퍼유저와 관리자 계정(어느 근무표든 관리 그룹 멤버).
    관리자 계정의 발급·초기화·퇴사·이름 고치기는 슈퍼유저가 관리 화면에서 한다(관리자끼리 계정을 가로채지 못하게).
    나 자신은 관리자라 늘 든다. 화면도 이 목록으로 줄을 잠근다."""
    return set(User.objects.filter(Q(is_superuser=True) | Q(groups__admin_board__isnull=False)).values_list("pk", flat=True))


def _person(by, board, user) -> User:
    """트랜잭션 안에서 다시 읽고 대상인지 본다: 그 근무표 부서 사람이고, 나 자신·슈퍼유저·관리자 계정이 아님(없는 사람도, 아니면 PermissionDenied, 뷰는 404)."""
    user = User.objects.select_related("department").filter(pk=user.pk).first()
    if (user is None or user.department_id is None or user.department.board_id != board.pk or user.pk == by.pk
            or user.pk in locked_ids()):
        raise PermissionDenied("이 근무표 설정에서 다룰 수 없는 사람입니다.")
    return user


def next_username(board) -> str:
    """사람 추가 아이디 칸에 미리 넣을 값: '<근무표 code><두 자리 번호>'(add_board 와 같은 꼴) 가운데 대소문자 구분 없이
    아직 없는 가장 작은 번호. code 는 Board.clean 이 영문 소문자로 지켜 늘 아이디 규칙에 맞는다."""
    taken = {u.lower() for u in User.objects.filter(username__istartswith=board.code).values_list("username", flat=True)}
    n = 1
    while f"{board.code}{n:02d}" in taken:
        n += 1
    return f"{board.code}{n:02d}"


def _type(board, type, current=STAFF) -> str:
    """구분: 켜진 장중관제 정의가 있는 근무표(관제 후보를 고르는 구분이라)에서만 고른다. 없으면 current(새 사람은 직원, 고치기는 그대로)."""
    if not prefs.has_types(boards.defs(board)):
        return current
    if type not in (STAFF, DEVELOPER):
        raise DutyError("구분(직원·개발자)을 고르세요.")
    return type


def _clean(user) -> None:
    """이름 규칙·이름 전체 고유·구분 제약(User.full_clean)을 이름·구분(과 구분 제약이 함께 보는 부서)만 본다:
    지금 규칙에 맞지 않는 다른 칸의 옛 값(아이디·전자우편 등)이 고치기를 막지 않게. 오류는 '칸 이름: 글' 한 줄."""
    if User.objects.filter(name=user.name).exclude(pk=user.pk).exists():
        raise DutyError(SAME_NAME)
    try:
        user.full_clean(exclude=[f.name for f in User._meta.fields if f.name not in ("name", "type", "department")])
    except ValidationError as e:
        raise DutyError(" ".join(("" if f == NON_FIELD_ERRORS else f"{User._meta.get_field(f).verbose_name}: ") + m
                                 for f, ms in e.message_dict.items() for m in ms)) from None


@transaction.atomic
def add_person(by, board, username, name, dept, type=None) -> User:
    """그 근무표 부서에 사람을 만든다. 비밀번호는 쓸 수 없는 값(관리 화면 UserAddForm 과 같다, 로그인은 [계정 발급] 뒤).
    아이디는 영문 소문자·숫자·_ 만(실명 아이디가 로그·LogEntry·로그인 잠금 기록에 남지 않게)."""
    _require_admin(by, board)
    dept = _dept(board, dept)
    if not USERNAME_RE.fullmatch(username):
        raise DutyError(BAD_USERNAME)
    if User.objects.filter(username__iexact=username).exists():  # 대소문자만 다른 아이디는 로그인·잠금에서 헷갈린다
        raise DutyError("같은 아이디가 이미 있습니다(대소문자 구분 없음).")
    user = User(username=username, name=name.strip(), department=dept, type=_type(board, type))
    user.set_unusable_password()
    _clean(user)
    user.save()
    _audit(by, board, user, username, "사람 추가")
    return user


@transaction.atomic
def set_person(by, board, user, name, type=None) -> None:
    """이름·구분을 고친다(검사는 add_person 과 같다). 부서를 바꾸는 길은 없다(인사이동은 슈퍼유저)."""
    _require_admin(by, board)
    user = _person(by, board, user)
    user.name, user.type = name.strip(), _type(board, type, user.type)
    _clean(user)
    user.save(update_fields=["name", "type"])
    _audit(by, board, user, user.username, "이름·구분 고치기")


def future_cells(board, user) -> list[tuple[date, str, Period, str]]:
    """읽기만: 그 사람의 오늘 이후 칸 전부 — 배포 근무(그날의 주인 회차의 행)와 배포 전 회차의 출근표·당번 행.
    (날짜, 칸 이름, 회차, 단계 이름), 날짜 순. 그 근무표 회차만. 퇴사 확인과 퇴사 뒤 목록에 쓴다."""
    today = perms.today()
    names = {x.key: x.name for x in boards.defs(board)}
    owner = {d: p.pk for d, p in boards.owners(board, today, None).items()}
    out = []
    for model, col in ((Commute, "shift"), (DutyAssignment, "cell")):
        for row in model.objects.filter(period__board=board, member=user, date__gte=today).select_related("period__board"):
            p, key = row.period, getattr(row, col)
            if p.status in BEFORE_PUBLISH or owner.get(row.date) == p.pk:
                out.append((row.date, names.get(key, key), p, p.status_label))
    return sorted(out, key=lambda c: (c[0], c[2].pk))


@transaction.atomic
def set_active(by, board, user, active: bool, confirm: int | None = None) -> list:
    """퇴사(accounts.deactivate: 로그인·연결 모두 끊음)·다시 재직(accounts.reactivate: 옛 비밀번호·연결도 끊고 재직만 켬, 로그인하려면 [계정 발급]).
    오늘 이후 칸이 있으면 confirm(화면이 보여 준 칸 수)이 같을 때만 퇴사한다(아니면 NeedsConfirm, 막지는 않는다).
    퇴사면 남은 칸 목록을 돌려준다. 관리자 계정은 _person 이 막으므로 재직 관리자 검사는 여기 없다(boards.left_without_admin 한 곳)."""
    _require_admin(by, board)
    user = _person(by, board, user)
    if user.is_active == active:
        raise DutyError("이미 재직 중인 사람입니다." if active else "이미 퇴사 처리된 사람입니다.")
    if active:
        accounts.reactivate(user)
        _audit(by, board, user, user.username, "다시 재직")
        return []
    cells = future_cells(board, user)
    if cells and confirm != len(cells):
        raise NeedsConfirm(f"이 근무 {len(cells)}칸은 그대로 남습니다. 근무표·입력 표에서 다른 사람으로 바꾸세요.", len(cells))
    accounts.deactivate(user)
    _audit(by, board, user, user.username, "퇴사")
    return cells


@transaction.atomic
def issue(by, board, users) -> list[tuple[User, str]]:
    """계정 발급 / 비밀번호 초기화(연결은 남긴다: '비밀번호를 잊었어요' 길). 여러 사람을 한 트랜잭션으로 — 하나라도 대상이
    아니면 아무것도 하지 않는다. 임시 비밀번호를 돌려준다(화면이 응답 본문에만 그린다. 여기서도 로그·기록에 넣지 않는다)."""
    _require_admin(by, board)
    users = list({u.pk: u for u in users}.values())  # 같은 사람이 두 번 오면 두 번째 발급이 앞 비밀번호를 무효로 만든다
    people = [_person(by, board, u) for u in users]
    if not people:
        raise DutyError("계정을 발급할 사람을 고르세요.")
    if not all(u.is_active for u in people):
        raise DutyError("퇴사한 사람은 먼저 [다시 재직]을 누르세요.")
    out = []
    for u in people:
        action = "비밀번호 초기화" if u.has_usable_password() else "계정 발급"
        out.append((u, accounts.issue_account(u, revoke_links=False)))
        _audit(by, board, u, u.username, action)
    return out
