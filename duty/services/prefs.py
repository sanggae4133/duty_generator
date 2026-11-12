from ..models import Department, RosterPref
from ..shifts import COMMUTE_SHIFTS, DEVELOPER, STAFF

SHIFT_CHOICES = {**COMMUTE_SHIFTS, "slots": "장중관제"}  # 화면 순서 = 키 순서
SHIFT_KEYS = list(SHIFT_CHOICES)
_KEYS = ("f", "dept", "type", "shift")


def clean(depts, types, shifts) -> tuple[list[str], list[str], list[str]]:
    """유효한 값만 남긴다. 전부 선택했거나 남은 게 없으면 [](= 전체)."""
    def pick(vals, valid):
        got = [c for c in dict.fromkeys(vals) if c in valid]
        return [] if set(got) == valid else got

    return (
        pick(depts, set(Department.objects.values_list("code", flat=True))),
        pick(types, {STAFF, DEVELOPER}),
        pick(shifts, set(SHIFT_KEYS)),
    )


def resolve(user, get, with_view: bool = True) -> dict:
    """요청에 필터 값이 있으면 그 값을 쓰고 저장, 없으면 저장값을 불러온다. 빈 목록 = 전체."""
    pref = RosterPref.objects.filter(user=user).first()
    if not any(k in get for k in _KEYS) and not (with_view and "view" in get):
        if pref is None:
            return {"depts": [], "types": [], "shifts": [], "view": "week"}
        return dict(zip(("depts", "types", "shifts"), clean(pref.depts, pref.types, pref.shifts)), view=pref.view)
    d, t, s = clean(get.getlist("dept"), get.getlist("type"), get.getlist("shift"))
    view = get["view"] if with_view and get.get("view") in ("week", "month") else (pref.view if pref else "week")
    new = {"depts": d, "types": t, "shifts": s, "view": view}
    if pref is None or any(getattr(pref, k) != v for k, v in new.items()):
        RosterPref.objects.update_or_create(user=user, defaults=new)  # 첫 저장 동시 요청도 안전
    return new
