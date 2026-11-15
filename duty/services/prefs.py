from ..models import Department, RosterPref
from ..shifts import DEVELOPER, SLOT_GROUP, SLOT_GROUP_NAME, STAFF, shift_defs, slot_defs
from . import boards

_KEYS = ("f", "dept", "type", "shift", "hist")


def choices(defs) -> dict[str, str]:
    """스케줄 선택지 {키: 이름}. 근무조(시작 시각 순) → 장중관제 묶음(관제 칸이 있을 때). 화면 순서 = 키 순서."""
    out = {x.key: x.name for x in shift_defs(defs)}
    if slot_defs(defs):
        out[SLOT_GROUP] = SLOT_GROUP_NAME
    return out


def clean(board, depts, types, shifts) -> tuple[list[str], list[str], list[str]]:
    """유효한 값만 남긴다(부서·스케줄은 그 근무표 것만). 전부 선택했거나 남은 게 없으면 [](= 전체)."""
    def pick(vals, valid):
        got = [c for c in dict.fromkeys(vals) if c in valid]
        return [] if set(got) == valid else got

    return (
        pick(depts, set(Department.objects.filter(board=board).values_list("code", flat=True))),
        pick(types, {STAFF, DEVELOPER}),
        pick(shifts, set(choices(boards.active_defs(board)))),  # 꺼진 정의는 새로 고를 수 없다
    )


def resolve(user, get, board, with_view: bool = True) -> dict:
    """요청에 필터 값이 있으면 그 값을 쓰고 저장, 없으면 저장값을 불러온다. 빈 목록 = 전체."""
    pref = RosterPref.objects.filter(user=user).first()
    if not any(k in get for k in _KEYS) and not (with_view and "view" in get):
        if pref is None:
            return {"depts": [], "types": [], "shifts": [], "view": "week", "history": True}
        return dict(zip(("depts", "types", "shifts"), clean(board, pref.depts, pref.types, pref.shifts)),
                    view=pref.view, history=pref.history)
    d, t, s = clean(board, get.getlist("dept"), get.getlist("type"), get.getlist("shift"))
    view = get["view"] if with_view and get.get("view") in ("week", "month") else (pref.view if pref else "week")
    # 체크박스는 hidden hist=0 뒤에 오므로 마지막 값을 본다. hist 가 없는 주소(날짜 이동 등)는 저장값 유지
    history = get.getlist("hist")[-1] == "1" if "hist" in get else (pref.history if pref else True)
    new = {"depts": d, "types": t, "shifts": s, "view": view, "history": history}
    if pref is None or any(getattr(pref, k) != v for k, v in new.items()):
        RosterPref.objects.update_or_create(user=user, defaults=new)  # 첫 저장 동시 요청도 안전
    return new
