from ..models import Department, RosterPref
from ..shifts import DEVELOPER, SLOT_GROUP, SLOT_GROUP_NAME, STAFF, lunch_defs, shift_defs, slot_defs
from . import boards

_FILTER_KEYS = ("f", "dept", "type", "shift")


def choices(defs) -> dict[str, str]:
    """스케줄 선택지 {키: 이름}. 근무조(시작 시각 순) → 장중관제 묶음(관제 칸이 있을 때) → 점심당번(있을 때).
    화면 순서 = 키 순서."""
    out = {x.key: x.name for x in shift_defs(defs)}
    if slot_defs(defs):
        out[SLOT_GROUP] = SLOT_GROUP_NAME
    out.update({x.key: x.name for x in lunch_defs(defs)})
    return out


def has_types(defs) -> bool:
    """유형(직원·개발자) 필터는 켜진 관제 정의가 있는 근무표에만(관제 후보를 고르는 구분이라). 꺼진 정의는 무시한다."""
    return bool(slot_defs([x for x in defs if x.active]))


def clean(board, depts, types, shifts) -> tuple[list[str], list[str], list[str]]:
    """유효한 값만 남긴다(부서·스케줄은 그 근무표 것만). 전부 선택했거나 남은 게 없으면 [](= 전체)."""
    active = boards.active_defs(board)

    def pick(vals, valid):
        got = [c for c in dict.fromkeys(vals) if c in valid]
        return [] if set(got) == valid else got

    return (
        pick(depts, set(Department.objects.filter(board=board).values_list("code", flat=True))),
        pick(types, {STAFF, DEVELOPER}) if has_types(active) else [],  # 없으면 저장값도 무시
        pick(shifts, set(choices(active))),  # 꺼진 정의는 새로 고를 수 없다
    )


def resolve(user, get, board, with_view: bool = True, mine: bool = True) -> dict:
    """요청에 값이 있으면 그 값을 쓰고 저장, 없으면 저장값을 불러온다. 빈 목록 = 전체. 세 묶음은 따로 본다:
    필터(f·dept·type·shift 중 하나라도 있을 때), 변경 내역(hist), 보기(view). 없는 묶음은 저장값을 그대로 둔다
    (근무표 화면의 이동 링크는 보기·날짜만 싣고 필터는 브라우저가 바꾸며 /prefs/ 로 저장한다).
    mine=False(보이는 근무표가 내 근무표가 아님, 설계 7): 부서·유형·스케줄은 늘 전체이고 저장된 필터를 덮어쓰지 않는다."""
    pref = RosterPref.objects.filter(user=user).first()
    has_f = mine and any(k in get for k in _FILTER_KEYS)
    has_h, has_v = "hist" in get, with_view and "view" in get
    if pref is None:
        saved = {"depts": [], "types": [], "shifts": [], "view": "week", "history": True}
    else:
        d, t, s = clean(board, pref.depts, pref.types, pref.shifts) if mine else ([], [], [])
        saved = {"depts": d, "types": t, "shifts": s, "view": pref.view, "history": pref.history}
    if not (has_f or has_h or has_v):
        return saved
    new = {}
    if has_f:
        new["depts"], new["types"], new["shifts"] = clean(board, get.getlist("dept"), get.getlist("type"), get.getlist("shift"))
    if has_v:
        new["view"] = get["view"] if get.get("view") in ("week", "month") else saved["view"]
    if has_h:  # 체크박스는 hidden hist=0 뒤에 오므로 마지막 값을 본다
        new["history"] = get.getlist("hist")[-1] == "1"
    if pref is None or any(getattr(pref, k) != v for k, v in new.items()):
        RosterPref.objects.update_or_create(user=user, defaults=new)  # 첫 저장 동시 요청도 안전
    return {**saved, **new}


def remember_boards(user, chosen, home) -> None:
    """근무표 화면에서 고른 목록을 기억한다(설계 5.5). chosen 은 boards.in_order 순서. [내 근무표] 하나면 비운다([]).
    기억이 이미 같으면 쓰지 않는다(없던 사용자가 내 근무표만 봐도 행을 만들지 않는다)."""
    keep = [] if home is not None and [b.pk for b in chosen] == [home.pk] else [b.code for b in chosen]
    pref = RosterPref.objects.filter(user=user).first()
    if (pref.boards if pref else []) != keep:
        RosterPref.objects.update_or_create(user=user, defaults={"boards": keep})
