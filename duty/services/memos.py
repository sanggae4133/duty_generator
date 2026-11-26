"""메모(날·주·달)와 근무 없음(설계 4.8·6.5). 편집은 그 근무표 관리 그룹만."""
from datetime import date, timedelta

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from .. import perms
from ..errors import DutyError
from ..models import ChangeLog, Commute, DutyAssignment, Memo, Period

DAY, WEEK, MONTH = Memo.Scope.DAY, Memo.Scope.WEEK, Memo.Scope.MONTH
MAX_TEXT = Memo._meta.get_field("text").max_length


def normalize(scope: str, d: date) -> date:
    """주 메모는 그 주 월요일, 달 메모는 그 달 1일에 붙는다."""
    if scope == WEEK:
        return d - timedelta(days=d.weekday())
    if scope == MONTH:
        return d.replace(day=1)
    if scope == DAY:
        return d
    raise DutyError("알 수 없는 메모 범위입니다.")


def _require_admin(user, board) -> None:
    if not perms.is_board_admin(user, board):
        raise PermissionDenied("메모는 근무표 관리자만 고칠 수 있습니다.")


def _rows(board, d: date):
    """그날 그 근무표의 모든 배정(모든 회차: 배포 회차 = 그날의 주인, 배포 전 회차의 입력·생성 행)."""
    return (Commute.objects.filter(period__board=board, date=d).select_related("period", "member").order_by("id"),
            DutyAssignment.objects.filter(period__board=board, date=d).select_related("period", "member").order_by("id"))


def affected(board, d: date) -> int:
    """근무 없음으로 저장하면 근무가 지워지는 사람 수(확인창 '○명의 근무가 지워집니다')."""
    commutes, duties = _rows(board, d)
    return len({*commutes.values_list("member_id", flat=True), *duties.values_list("member_id", flat=True)})


def _clear_day(user, board, d: date) -> int:
    """그날 배정을 모두 지운다. 배포 회차(그날의 주인)의 행은 지운 것마다 ChangeLog(빼기)를 남겨
    근무표 이력·변경 알림이 평소처럼 돈다. 배포 전 회차 행은 기록 없이 지운다(근무 없음 날은 늘 비어 있다)."""
    n = affected(board, d)
    commutes, duties = _rows(board, d)
    for rows, field in ((commutes, "shift"), (duties, "cell")):
        for r in rows:
            if r.period.status == Period.Status.PUBLISHED:
                ChangeLog.objects.create(by=user, period=r.period, date=d, cell=getattr(r, field), before=r.member,
                                         reason_before=getattr(r, "reason", ""))
    commutes.delete()
    duties.delete()
    return n


@transaction.atomic
def save(user, board, scope: str, d: date, text: str, no_work: bool = False, confirm: int | None = None,
         notify: bool = True) -> int:
    """메모를 저장하고 지운 근무의 사람 수를 돌려준다. 글이 비고 근무 없음도 아니면 지운다.
    notify=False 면 바뀌어도 메모 알림을 보내지 않는다(오타 고침 등).
    근무 없음으로 저장할 때 그날 배정이 있으면 confirm 이 확인창에서 본 인원수와 같아야 한다(그사이 바뀌었거나 없으면 DutyError)."""
    _require_admin(user, board)
    d = normalize(scope, d)
    text = (text or "").strip()
    if no_work and scope != DAY:
        raise DutyError("근무 없음은 날 메모에만 달 수 있습니다.")
    if no_work and d.weekday() >= 5:
        raise DutyError("근무 없음은 평일에만 달 수 있습니다.")
    if len(text) > MAX_TEXT:
        raise DutyError(f"메모는 {MAX_TEXT}자까지 쓸 수 있습니다.")
    if not text and not no_work:
        delete(user, board, scope, d)
        return 0
    cleared = 0
    old = Memo.objects.filter(board=board, scope=scope, date=d).first()
    if no_work and not (old and old.no_work):  # 근무 없음을 켤 때만 비운다(그 뒤 넣은 사람은 글을 고쳐도 남는다)
        n = affected(board, d)
        if n and confirm != n:
            raise DutyError(f"{n}명의 근무가 지워집니다. 확인하고 다시 저장해 주세요.")
        cleared = _clear_day(user, board, d)
    fields = {"text": text, "no_work": no_work}
    if old is None or old.text != text or old.no_work != no_work:  # 새로 달거나 바꿨을 때만 메모 알림(memo_notice)
        # 알림 끔이어도 아직 안 나간 알림은 살린다(저장 직후 오타 고침이 먼저 알림을 지우지 않게)
        fields.update(notice_pending=notify or bool(old and old.notice_pending), edited_by=user, edited_at=timezone.now())
    Memo.objects.update_or_create(board=board, scope=scope, date=d, defaults=fields)
    return cleared


@transaction.atomic
def delete(user, board, scope: str, d: date) -> None:
    """메모를 지운다. 근무 없음 날이었으면 빈 날이 되고, 근무 변경 '넣기'로 다시 채운다."""
    _require_admin(user, board)
    Memo.objects.filter(board=board, scope=scope, date=normalize(scope, d)).delete()


def no_work_days(board, start: date, end: date) -> set[date]:
    return set(Memo.objects.filter(board=board, scope=DAY, no_work=True, date__gte=start, date__lte=end)
               .values_list("date", flat=True))


def for_range(board, start: date, end: date) -> dict[str, dict[date, Memo]]:
    """start~end 화면에 걸리는 메모: {"day": {날짜: 메모}, "week": {월요일: 메모}, "month": {1일: 메모}}."""
    lo = min(normalize(WEEK, start), normalize(MONTH, start))
    out = {DAY: {}, WEEK: {}, MONTH: {}}
    for m in Memo.objects.filter(board=board, date__gte=lo, date__lte=end):
        if m.scope != DAY or m.date >= start:
            out[m.scope][m.date] = m
    return out
