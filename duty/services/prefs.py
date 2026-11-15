from ..models import Department, RosterPref
from ..shifts import DEVELOPER, SLOT_GROUP, SLOT_GROUP_NAME, STAFF, lunch_defs, shift_defs, slot_defs
from . import boards

_KEYS = ("f", "dept", "type", "shift", "hist")


def choices(defs) -> dict[str, str]:
    """스케줄 선택지 {키: 이름}. 근무조(시작 시각 순) → 장중관제 묶음(관제 칸이 있을 때) → 점심당번(있을 때).
    화면 순서 = 키 순서."""
    out = {x.key: x.name for x in shift_defs(defs)}
    if slot_defs(defs):
        out[SLOT_GROUP] = SLOT_GROUP_NAME
    out.update({x.key: x.name for x in lunch_defs(defs)})
    return out


def clean(board, depts, types, shifts) -> tuple[list[str], list[str], list[str]]:
    """유효한 값만 남긴다(부서·스케줄은 그 근무표 것만). 전부 선택했거나 남은 게 없으면 [](= 전체)."""
    active = boards.active_defs(board)

    def pick(vals, valid):
        got = [c for c in dict.fromkeys(vals) if c in valid]
        return [] if set(got) == valid else got

    return (
        pick(depts, set(Department.objects.filter(board=board).values_list("code", flat=True))),
        # 유형 필터는 켜진 관제 정의가 있는 근무표에만(관제 후보를 고르는 구분이라). 없으면 저장값도 무시
        pick(types, {STAFF, DEVELOPER}) if slot_defs(active) else [],
        pick(shifts, set(choices(active))),  # 꺼진 정의는 새로 고를 수 없다
    )


def resolve(user, get, board, with_view: bool = True, mine: bool = True) -> dict:
    """요청에 필터 값이 있으면 그 값을 쓰고 저장, 없으면 저장값을 불러온다. 빈 목록 = 전체.
    mine=False(보이는 근무표가 내 근무표가 아님, 설계 7): 부서·유형·스케줄은 늘 전체이고 저장된 필터를 덮어쓰지 않는다.
    보기(주간·월간)와 변경 내역 표시는 근무표와 상관없이 따르고 저장한다."""
    pref = RosterPref.objects.filter(user=user).first()
    if not any(k in get for k in (_KEYS if mine else ("hist",))) and not (with_view and "view" in get):
        if pref is None:
            return {"depts": [], "types": [], "shifts": [], "view": "week", "history": True}
        d, t, s = clean(board, pref.depts, pref.types, pref.shifts) if mine else ([], [], [])
        return {"depts": d, "types": t, "shifts": s, "view": pref.view, "history": pref.history}
    d, t, s = clean(board, get.getlist("dept"), get.getlist("type"), get.getlist("shift")) if mine else ([], [], [])
    view = get["view"] if with_view and get.get("view") in ("week", "month") else (pref.view if pref else "week")
    # 체크박스는 hidden hist=0 뒤에 오므로 마지막 값을 본다. hist 가 없는 주소(날짜 이동 등)는 저장값 유지
    history = get.getlist("hist")[-1] == "1" if "hist" in get else (pref.history if pref else True)
    new = {"view": view, "history": history, **({"depts": d, "types": t, "shifts": s} if mine else {})}
    if pref is None or any(getattr(pref, k) != v for k, v in new.items()):
        RosterPref.objects.update_or_create(user=user, defaults=new)  # 첫 저장 동시 요청도 안전
    return {"depts": d, "types": t, "shifts": s, **new}


def remember_board(user, board, home) -> None:
    """근무표 화면에서 ?board= 로 고른 근무표를 기억한다(설계 7). 내 근무표(home)를 고르면 비운다(None).
    기억이 이미 같으면 쓰지 않는다(없던 사용자가 내 근무표를 골라도 행을 만들지 않는다)."""
    keep = None if home is not None and board.pk == home.pk else board
    pref = RosterPref.objects.filter(user=user).first()
    if (pref.board_id if pref else None) != (keep.pk if keep else None):
        RosterPref.objects.update_or_create(user=user, defaults={"board": keep})
