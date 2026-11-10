from ..errors import DutyError
from ..models import AlarmRule, Department
from ..shifts import DEVELOPER, STAFF
from .prefs import SHIFT_KEYS

DEFAULT_RULES = [
    dict(kind="personal", timing="days", offset=1, at_minute=18 * 60, telegram=True, push=False, shifts=["dawn", "dinner", "night"]),
    dict(kind="personal", timing="before_start", offset=120, at_minute=0, telegram=True, push=False, shifts=["dawn", "dinner", "night"]),
]


def normalize(kind, shifts, depts, types):
    """알려진 값만 남기고 정해진 순서로 정렬. 전부 선택 = [](전체). 개인 규칙은 부서·유형 필터 없음."""
    def pick(vals, order):
        bad = [v for v in vals if v not in order]
        if bad:
            raise DutyError(f"알 수 없는 값: {', '.join(map(str, bad))}")
        got = [v for v in order if v in set(vals)]
        return [] if len(got) == len(order) else got

    s = pick(shifts, SHIFT_KEYS)
    d = pick(depts, sorted(Department.objects.values_list("code", flat=True)))
    t = pick(types, [STAFF, DEVELOPER])
    return (s, [], []) if kind == "personal" else (s, d, t)


def create_defaults(user) -> None:
    if AlarmRule.objects.filter(user=user).exists():
        return
    AlarmRule.objects.bulk_create([AlarmRule(user=user, **r) for r in DEFAULT_RULES])
