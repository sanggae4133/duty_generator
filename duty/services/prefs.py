from ..models import Department, RosterPref
from ..shifts import DEVELOPER, SLOT_GROUP, SLOT_GROUP_NAME, STAFF, lunch_defs, shift_defs, slot_defs
from . import boards

_FILTER_KEYS = ("f", "dept", "type", "shift")
DIM_KEYS = ("dept", "type", "shift")
_DIM_PARAMS = {"dept": "ddim", "type": "tdim", "shift": "sdim"}  # roster.js 가 fd=1 과 함께 보낸다


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


def _valid(board) -> tuple[set, set, set]:
    """그 근무표에서 고를 수 있는 부서·유형·스케줄 값."""
    active = boards.active_defs(board)
    return (set(Department.objects.filter(board=board).values_list("code", flat=True)),
            {STAFF, DEVELOPER} if has_types(active) else set(),  # 없으면 저장값도 무시
            set(choices(active)))  # 꺼진 정의는 새로 고를 수 없다


def clean(board, depts, types, shifts) -> tuple[list[str], list[str], list[str]]:
    """유효한 값만 남긴다(부서·스케줄은 그 근무표 것만). 전부 선택했거나 남은 게 없으면 [](= 전체)."""
    def pick(vals, valid):
        got = [c for c in dict.fromkeys(vals) if c in valid]
        return [] if set(got) == valid else got

    vd, vt, vs = _valid(board)
    return pick(depts, vd), pick(types, vt), pick(shifts, vs)


def clean_dims(board, dims: dict, mine: bool = True) -> dict:
    """흐리게 값: 유효한 것만(내 근무표가 아니면 부서·유형·스케줄은 없음). 흐리게는 '모두'여도 줄이지 않는다."""
    valid = _valid(board) if mine else (set(), set(), set())
    return {**{k: [c for c in dict.fromkeys(dims.get(k) or []) if c in v] for k, v in zip(DIM_KEYS, valid)},
            "hist": bool(dims.get("hist"))}


def resolve(user, get, board, with_view: bool = True, mine: bool = True) -> dict:
    """요청에 값이 있으면 그 값을 쓰고 저장, 없으면 저장값을 불러온다. 빈 목록 = 전체. 세 묶음은 따로 본다:
    필터(f·dept·type·shift 중 하나라도 있을 때), 변경 내역(hist), 보기(view). 없는 묶음은 저장값을 그대로 둔다
    (근무표 화면의 이동 링크는 보기·날짜만 싣고 필터는 브라우저가 바꾸며 /prefs/ 로 저장한다).
    mine=False(보이는 근무표가 내 근무표가 아님, 설계 7): 부서·유형·스케줄은 늘 전체이고 저장된 필터를 덮어쓰지 않는다."""
    pref = RosterPref.objects.filter(user=user).first()
    has_f = mine and any(k in get for k in _FILTER_KEYS)
    has_h, has_v = "hist" in get, with_view and "view" in get
    if pref is None:
        saved = {"depts": [], "types": [], "shifts": [], "view": "week", "history": True,
                 "dims": clean_dims(board, {}, mine)}
    else:
        d, t, s = clean(board, pref.depts, pref.types, pref.shifts) if mine else ([], [], [])
        saved = {"depts": d, "types": t, "shifts": s, "view": pref.view, "history": pref.history,
                 "dims": clean_dims(board, pref.dims, mine)}
    has_d = "fd" in get  # 흐리게는 근무표 화면(roster.js)만 보낸다: 하루 화면 필터 폼은 저장된 흐리게를 두고 간다
    if not (has_f or has_h or has_v or has_d):
        return saved
    new = {}
    if has_d:
        hist = get.get("hdim") == "1"
        if mine:
            new["dims"] = clean_dims(board, {**{k: get.getlist(p) for k, p in _DIM_PARAMS.items()}, "hist": hist})
        else:  # 남의 근무표만 볼 때: 내 근무표의 흐리게 값은 그대로 두고 변경 내역만
            new["dims"] = {**(pref.dims if pref else {}), "hist": hist}
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
