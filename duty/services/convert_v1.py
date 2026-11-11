"""예전(duty 마이그레이션 0001~0009) SQLite 백업을 새 스키마(0001_v2) 빈 DB로 옮긴다. 1회용.

값은 원본 그대로 raw INSERT 한다(시각·JSON·null·해시 문자열 보존). auto_now(_add) 칸도 ORM 을 거치지 않으므로
원본 값이 그대로 들어간다(따로 update() 로 되돌릴 필요 없음).
출력은 건수만: 이름·비밀번호 해시·토큰 해시·푸시 endpoint·chat_id 는 출력하지 않는다.
"""
import sqlite3
from collections import Counter
from pathlib import Path

from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from duty.models import User

V1_MIGRATIONS = {
    "0001_initial", "0002_remove_controlduty_duty_one_slot_per_member", "0003_alter_member_name",
    "0004_roster_pref", "0005_db_constraints", "0006_alarms", "0007_default_alarm_rules",
    "0008_telegram_link_code", "0009_calendarfeed",
}
V2_MIGRATIONS = {"0001_v2"}

# (표, {새 칼럼: 예전 칼럼}, 예전 auth_user.id → 새 User id 로 바꿀 칼럼, 비울 칼럼). FK 순서
COPY = [
    ("duty_department", {}, (), ()),
    ("duty_department_managers", {"user_id": "member_id"}, (), ()),  # 멤버 id = User id
    ("duty_period", {}, (), ()),
    ("duty_commute", {}, (), ()),
    ("duty_controlduty", {}, (), ()),
    ("duty_changelog", {}, ("by_id",), ()),
    ("duty_rosterpref", {}, ("user_id",), ()),
    ("duty_calendarfeed", {}, ("user_id",), ()),
    ("duty_telegramalarmprofile", {}, ("user_id",), ("link_code", "link_expires_at")),  # 연결 대기 코드는 버림
    ("duty_pushalarmsubscription", {}, ("user_id",), ()),
    ("duty_alarmrule", {}, ("user_id",), ()),
    ("duty_alarmdelivery", {}, (), ()),
]
MEMBER_COLS = ["id", "code", "name", "part", "type", "is_active", "must_change_password", "department_id", "user_id"]
ACCOUNT_COLS = ["id", "password", "last_login", "is_superuser", "username", "first_name", "last_name", "email",
                "is_staff", "is_active", "date_joined"]
USER_COLS = [*ACCOUNT_COLS, "name", "department_id", "part", "type", "must_change_password"]
DISCARD = {"세션": ["django_session"],
           "axes 기록": ["axes_accessattempt", "axes_accessfailurelog", "axes_accesslog", "axes_accessattemptexpiration"],
           "관리 화면 기록": ["django_admin_log"]}
NO_ROWS = ["auth_group", "auth_user_groups", "auth_user_user_permissions"]


class ConvertError(Exception):
    pass


def _rows(db, sql):
    """db = 원본 sqlite3 연결 또는 대상 Django connection. dict 목록."""
    cur = db.cursor()
    try:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        cur.close()


def _count(db, table):
    return _rows(db, f'SELECT count(*) AS n FROM "{table}"')[0]["n"]


def _columns(db, table):
    return {r["name"] for r in _rows(db, f'PRAGMA table_info("{table}")')}


def convert(source: str, write) -> None:
    src = Path(source).resolve()
    dst = Path(str(connection.settings_dict["NAME"])).resolve()
    if not src.is_file():
        raise ConvertError("원본 파일이 없습니다.")
    if src == dst or (dst.exists() and src.samefile(dst)):
        raise ConvertError("원본이 현재 DB와 같은 파일입니다. 예전 DB 백업 파일을 지정하세요.")
    wal = Path(f"{src}-wal")
    if wal.exists() and wal.stat().st_size > 0:  # immutable 은 -wal 을 무시하므로 최근 변경이 조용히 빠진다
        raise ConvertError("원본 옆에 -wal 파일이 있습니다. sqlite3 .backup 으로 만든 단일 파일을 지정하세요.")
    # immutable: 정적 백업 파일. WAL 모드 백업도 -shm 을 만들지 않으므로 읽기 전용 폴더에서도 열린다
    old = sqlite3.connect(src.as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        with transaction.atomic():
            try:
                _check_source(old)
            except sqlite3.DatabaseError:
                raise ConvertError("원본을 읽을 수 없습니다(손상되었거나 SQLite DB가 아님).") from None
            _check_target()
            users, user_map, notes = _build_users(old)
            _write(old, users, user_map, notes, write)
    except (DatabaseError, sqlite3.DatabaseError) as e:  # 사전 검사 뒤 오류: 롤백된 뒤라 대상은 그대로
        raise ConvertError(f"옮기는 중 DB 오류({type(e).__name__})로 멈췄습니다. 전체를 되돌렸습니다.") from None
    finally:
        old.close()


def _check_source(old):
    if [r["quick_check"] for r in _rows(old, "PRAGMA quick_check")] != ["ok"]:
        raise ConvertError("원본 quick_check 실패: 손상된 파일입니다.")
    need = {"django_migrations": {"app", "name"}, "duty_member": set(MEMBER_COLS), "auth_user": set(ACCOUNT_COLS),
            **{t: set() for ts in DISCARD.values() for t in ts}, **{t: set() for t in NO_ROWS}}
    for table, renames, *_ in COPY:  # 대상 표의 칼럼 전부가 원본에 있어야 한다
        need[table] = {renames.get(c, c) for c in _columns(connection, table)}
    missing = sorted(t for t, cols in need.items() if not (have := _columns(old, t)) or not cols <= have)
    if missing:
        raise ConvertError(f"원본에 필요한 표·칼럼이 없습니다: {', '.join(missing)}")
    if {r["name"] for r in _rows(old, "SELECT name FROM django_migrations WHERE app='duty'")} != V1_MIGRATIONS:
        raise ConvertError("원본이 예전 버전(duty 마이그레이션 0001~0009) DB가 아닙니다.")
    if _rows(old, "PRAGMA foreign_key_check"):
        raise ConvertError("원본 foreign_key_check 실패: 끊긴 연결이 있습니다.")
    if any(_count(old, t) for t in NO_ROWS):
        raise ConvertError("원본에 그룹·직접 권한 행이 있습니다(auth_group 등). 정리한 뒤 다시 실행하세요.")


def _check_target():
    if {r["name"] for r in _rows(connection, "SELECT name FROM django_migrations WHERE app='duty'")} != V2_MIGRATIONS:
        raise ConvertError("현재 DB가 새 스키마(duty 마이그레이션 0001_v2 하나)가 아닙니다. 빈 DB에 migrate 하세요.")
    tables = _rows(connection, "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'duty_%'")
    if any(_count(connection, t["name"]) for t in tables):
        raise ConvertError("현재 DB가 비어 있지 않습니다. migrate 만 한 빈 DB에서 실행하세요.")


def _build_users(old):
    """만들 User 행, 예전 auth_user.id → 새 id 대응표, 출력용 건수(코드로 바뀐 아이디, 재직 AND로 바뀐 상태)."""
    members = _rows(old, "SELECT * FROM duty_member ORDER BY id")
    accounts = {a["id"]: a for a in _rows(old, "SELECT * FROM auth_user ORDER BY id")}
    now = connection.ops.adapt_datetimefield_value(timezone.now())
    users, user_map, notes = [], {}, Counter()
    for m in members:
        u = {"id": m["id"], "username": m["code"], "name": m["name"], "department_id": m["department_id"],
             "part": m["part"], "type": m["type"], "must_change_password": m["must_change_password"]}
        if (a := accounts.get(m["user_id"])) is not None:
            u |= {k: a[k] for k in ("password", "is_staff", "is_superuser", "last_login", "date_joined",
                                    "first_name", "last_name", "email")}
            u["is_active"] = int(bool(m["is_active"] and a["is_active"]))
            user_map[a["id"]] = m["id"]
            notes["renamed"] += a["username"] != m["code"]
            notes["active_off"] += bool(m["is_active"] and not a["is_active"])
            if a["is_active"] and not m["is_active"]:  # 예전엔 퇴사 스태프도 로그인됐다
                notes["login_off"] += 1
                notes["login_off_staff"] += bool(a["is_staff"] or a["is_superuser"])
        else:
            u |= {"password": make_password(None), "is_staff": 0, "is_superuser": 0, "last_login": None,
                  "date_joined": now, "first_name": "", "last_name": "", "email": "", "is_active": m["is_active"]}
        users.append(u)
    next_id = max((m["id"] for m in members), default=0)
    for a in accounts.values():  # auth_user.id 순
        if a["id"] in user_map:
            continue
        next_id += 1
        user_map[a["id"]] = next_id
        users.append({**a, "id": next_id, "name": a["username"], "department_id": None, "part": "", "type": "",
                      "must_change_password": 0})

    fields = [User._meta.get_field(f) for f in ("username", "name")]
    bad = []
    for u in users:
        try:
            for field in fields:  # 길이·blank·validator 전부(SQLite 는 길이를 강제하지 않음)
                field.clean(u[field.name], None)
        except ValidationError:
            bad.append(u["id"])
    if bad:
        raise ConvertError(f"아이디·이름 규칙(형식·길이)을 어기는 사용자 {len(bad)}명(새 id: {', '.join(map(str, bad))})")
    for f, label in (("username", "아이디 중복"), ("name", "이름 중복")):
        if dup := sum(n - 1 for n in Counter(u[f] for u in users).values() if n > 1):
            raise ConvertError(f"{label} {dup}건: 멤버 코드·이름과 연결 없는 계정 아이디가 겹칩니다.")
    return users, user_map, notes


def _insert(table, cols, rows):
    names = ", ".join(f'"{c}"' for c in cols)
    marks = ", ".join(["%s"] * len(cols))
    with connection.cursor() as cur:
        cur.executemany(f'INSERT INTO "{table}" ({names}) VALUES ({marks})', [[r[c] for c in cols] for r in rows])


def _copy(old, table, renames, remap, blank, user_map):
    rows = _rows(old, f'SELECT * FROM "{table}" ORDER BY rowid')
    for r in rows:
        for new, was in renames.items():
            r[new] = r.pop(was)
        for c in remap:
            if r[c] is not None:
                r[c] = user_map[r[c]]
        for c in blank:
            r[c] = None
    _insert(table, sorted(_columns(connection, table)), rows)
    return len(rows)


def _write(old, users, user_map, notes, write):
    _insert("duty_user", USER_COLS, users)
    n_members = _count(old, "duty_member")
    write(f"duty_user: 멤버 {n_members} + 연결 없는 계정 {len(users) - n_members} → 새 {_count(connection, 'duty_user')}")
    write(f"아이디가 멤버 코드와 달라 코드로 바꾼 계정 {notes['renamed']}")
    write(f"재직이었지만 계정 비활성이라 재직 끔 {notes['active_off']}")
    write(f"퇴사였지만 계정 활성이라 로그인 차단 {notes['login_off']} (그중 스태프 {notes['login_off_staff']})")
    if not any(u["is_superuser"] and u["is_active"] for u in users):
        write("경고: 활성 슈퍼유저가 없습니다. 관리 화면에 들어가려면 `manage.py createsuperuser`로 새로 만들거나, "
              "`manage.py shell`에서 기존 계정의 is_active를 켠 뒤 `manage.py changepassword <아이디>`로 비밀번호를 정하세요.")
    for table, renames, remap, blank in COPY:
        n = _copy(old, table, renames, remap, blank, user_map)
        write(f"{table}: 예전 {n} → 새 {_count(connection, table)}")
    connection.check_constraints()  # FK 는 커밋 때에야 검사되므로 여기서 미리 확인
    dropped = ", ".join(f"{label} {sum(_count(old, t) for t in ts)}" for label, ts in DISCARD.items())
    write(f"버림(옮기지 않음): {dropped}")
