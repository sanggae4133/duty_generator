from ..models import Department, RosterPref
from ..shifts import DEVELOPER, STAFF

SHIFT_KEYS = ["dawn", "normal", "dinner", "night", "slots"]
_KEYS = ("f", "dept", "type", "shift")


def resolve(user, get, with_view: bool = True) -> dict:
    """요청에 필터 값이 있으면 그 값을 쓰고 저장, 없으면 저장값을 불러온다. 빈 목록 = 전체."""
    pref = RosterPref.objects.filter(user=user).first() or RosterPref(user=user)
    if not any(k in get for k in _KEYS) and not (with_view and "view" in get):
        return {"depts": pref.depts, "types": pref.types, "shifts": pref.shifts, "view": pref.view}
    valid = {"dept": set(Department.objects.values_list("code", flat=True)), "type": {STAFF, DEVELOPER}, "shift": set(SHIFT_KEYS)}

    def pick(name):
        got = [c for c in dict.fromkeys(get.getlist(name)) if c in valid[name]]
        return [] if set(got) == valid[name] else got

    new = {"depts": pick("dept"), "types": pick("type"), "shifts": pick("shift"), "view": pref.view}
    if with_view and get.get("view") in ("week", "month"):
        new["view"] = get["view"]
    if any(getattr(pref, k) != v for k, v in new.items()) or pref.pk is None:
        for k, v in new.items():
            setattr(pref, k, v)
        pref.save()
    return new
