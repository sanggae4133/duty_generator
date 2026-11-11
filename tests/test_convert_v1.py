"""convert_v1: 예전(0001~0009) DB 백업 → 새 스키마(0001_v2) 빈 DB. 데이터는 전부 가상."""
import functools
import json
import sqlite3
from io import StringIO
from pathlib import Path

import pytest
from django.contrib.auth.hashers import make_password
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import Client
from django.urls import reverse

from duty.models import ChangeLog, Department, User
from duty.services import convert_v1

FIXTURE = Path(__file__).parent / "fixtures" / "v1_empty.sql"
PW = "Known-Pw-123"
TOKEN_HASH = "a" * 64
ENDPOINT = "https://push.example.invalid/ep-secret"
CHAT_ID = "987654321"
NAMES = ["가상일", "가상이", "가상삼", "가상사", "가상오", "가상육"]
# 예전 auth_user.id → 새 User id. 연결 계정은 멤버 id, 연결 없는 계정은 max(멤버 id)=8 다음부터 auth_user.id 순
USER_MAP = {1: 9, 2: 1, 3: 2, 4: 3, 5: 5, 6: 10}
COPIED = ["duty_department", "duty_department_managers", "duty_period", "duty_commute", "duty_controlduty",
          "duty_changelog", "duty_rosterpref", "duty_calendarfeed", "duty_telegramalarmprofile",
          "duty_pushalarmsubscription", "duty_alarmrule", "duty_alarmdelivery"]


@functools.cache
def pw_hash():
    return make_password(PW)


def fetch(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def dump(cur, table):
    """표 전체를 저장된 값 그대로(드라이버 변환 없이) dict 목록으로."""
    cols = [r[1] for r in fetch(cur, f'PRAGMA table_info("{table}")')]
    quoted = ", ".join(f'"{c}"' for c in cols)
    return [dict(zip(cols, json.loads(r[0])))
            for r in fetch(cur, f'SELECT json_array({quoted}) FROM "{table}" ORDER BY rowid')]


def target_rows():
    with connection.cursor() as cur:
        tables = [r[0] for r in fetch(cur, "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'duty%'")]
        return {t: fetch(cur, f'SELECT count(*) FROM "{t}"')[0][0] for t in tables}


@pytest.fixture
def old(tmp_path):
    path = tmp_path / "old-v1.sqlite3"
    con = sqlite3.connect(path)
    con.executescript(FIXTURE.read_text())
    yield path, con
    con.close()


def seed(con):
    h = pw_hash()
    con.executescript("""
        INSERT INTO duty_department VALUES('MEMS','가상실A','dawn,normal,dinner,night');
        INSERT INTO duty_department VALUES('UI','가상실B','normal,dinner,night');
    """)
    # id, password, last_login, is_superuser, username, last_name, email, is_staff, is_active, date_joined, first_name
    con.executemany("INSERT INTO auth_user VALUES(?,?,?,?,?,?,?,?,?,?,?)", [
        (1, h, "2026-11-05 01:02:03.456789", 1, "admin", "", "admin@example.invalid", 1, 1, "2026-10-01 00:00:00", ""),
        (2, h, None, 0, "MEMS001", "성", "", 1, 1, "2026-10-02 00:00:00", "이름"),
        (3, h, None, 0, "MEMS002", "", "", 0, 0, "2026-10-03 00:00:00", ""),
        (4, h, "2026-11-01 00:00:00", 0, "old-login", "", "", 0, 1, "2026-10-04 00:00:00", ""),
        (5, h, None, 0, "MEMS004", "", "", 0, 0, "2026-10-05 00:00:00", ""),
        (6, h, None, 0, "viewer", "", "", 0, 0, "2026-10-06 00:00:00", ""),
    ])
    # id, code, name, part, type, is_active, must_change_password, department_id, user_id
    con.executemany("INSERT INTO duty_member VALUES(?,?,?,?,?,?,?,?,?)", [
        (1, "MEMS001", "가상일", "파트1", "개발자", 1, 0, "MEMS", 2),  # 멤버·계정 둘 다 활성, 스태프
        (2, "MEMS002", "가상이", "", "직원", 1, 1, "MEMS", 3),  # 계정만 비활성
        (3, "MEMS003", "가상삼", "", "개발자", 0, 0, "MEMS", 4),  # 멤버만 비활성, 아이디 ≠ 코드
        (5, "MEMS004", "가상사", "", "개발자", 0, 0, "MEMS", 5),  # 둘 다 비활성
        (7, "UI001", "가상오", "", "개발자", 1, 0, "UI", None),  # 계정 없음
        (8, "UI002", "가상육", "", "직원", 0, 0, "UI", None),  # 계정 없는 퇴사 멤버
    ])
    con.executescript(f"""
        INSERT INTO duty_department_managers VALUES(4,'MEMS',1);
        INSERT INTO duty_department_managers VALUES(6,'UI',7);
        INSERT INTO duty_period VALUES(3,'가상 회차','2026-11-02','2026-11-13','published',42,
            '2026-11-01 01:00:00','2026-11-01 02:00:00.5',NULL);
        INSERT INTO duty_commute VALUES(10,'2026-11-02','dawn',1,3);
        INSERT INTO duty_commute VALUES(11,'2026-11-02','normal',7,3);
        INSERT INTO duty_commute VALUES(12,'2026-11-03','night',3,3);
        INSERT INTO duty_controlduty VALUES(20,'2026-11-02',0,1,3);
        INSERT INTO duty_changelog VALUES(30,'2026-11-02 00:10:00.123456','2026-11-02','slot0',1,1,7,3);
        INSERT INTO duty_changelog VALUES(31,'2026-11-02 00:11:00','2026-11-02','normal',NULL,7,NULL,3);
        INSERT INTO duty_changelog VALUES(32,'2026-11-02 00:12:00','2026-11-02','dawn',2,NULL,3,3);
        INSERT INTO duty_rosterpref VALUES(40,'["MEMS"]','[]','["dawn"]','month',2);
        INSERT INTO duty_calendarfeed VALUES(50,'{TOKEN_HASH}','2026-11-03 00:00:00',2);
        INSERT INTO duty_telegramalarmprofile VALUES(60,'{CHAT_ID}','2026-11-03 00:00:00',NULL,2,'LINKCODE1',
            '2026-11-12 00:00:00');
        INSERT INTO duty_telegramalarmprofile VALUES(61,'',NULL,NULL,1,NULL,NULL);
        INSERT INTO duty_pushalarmsubscription VALUES(70,'{ENDPOINT}','p256-secret','auth-secret','내 폰',
            '2026-11-04 00:00:00',2);
        INSERT INTO duty_alarmrule VALUES(80,1,'personal','days',1,540,1,1,'[]','[]','[]',2);
        INSERT INTO duty_alarmrule VALUES(81,0,'report','days',0,480,1,0,'[]','["MEMS"]','["개발자"]',1);
        INSERT INTO duty_alarmdelivery VALUES(90,'2026-11-02','dawn','push','sub:70','sent',1,NULL,
            '{"b" * 64}','{"b" * 64}','2026-11-02 00:00:00',80);
        INSERT INTO duty_alarmdelivery VALUES(91,'2026-11-02','report','telegram','{CHAT_ID}','failed',2,
            '2026-11-02 00:05:00','{"c" * 64}',NULL,'2026-11-02 00:01:00',81);
        INSERT INTO django_session VALUES('sess1','data','2026-12-01 00:00:00');
        INSERT INTO axes_accessattempt VALUES(1,'ua','127.0.0.1','admin','','/login/','2026-11-01 00:00:00','','',1);
        INSERT INTO django_admin_log VALUES(1,'1','가상일',1,'',NULL,1,'2026-11-01 00:00:00');
    """)
    con.commit()


def run(path):
    out, err = StringIO(), StringIO()
    call_command("convert_v1", str(path), stdout=out, stderr=err)
    return out.getvalue() + err.getvalue()


def test_fixture_has_schema_but_no_business_rows(old):
    _, con = old
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert "duty_member" in tables and "auth_user" in tables
    for t in set(tables) - {"django_migrations", "django_content_type", "auth_permission", "sqlite_sequence"}:
        assert con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] == 0, t
    names = {r[0] for r in con.execute("SELECT name FROM django_migrations WHERE app='duty'")}
    assert names == convert_v1.V1_MIGRATIONS


def test_convert_copies_everything(old, db):
    path, con = old
    seed(con)
    output = run(path)

    with connection.cursor() as cur:
        users = {u["id"]: u for u in dump(cur, "duty_user")}
        assert sorted(users) == [1, 2, 3, 5, 7, 8, 9, 10]
        h = pw_hash()
        expect = {  # id: (username, name, dept, type, is_active, is_staff, is_superuser, must_change)
            1: ("MEMS001", "가상일", "MEMS", "개발자", 1, 1, 0, 0),
            2: ("MEMS002", "가상이", "MEMS", "직원", 0, 0, 0, 1),
            3: ("MEMS003", "가상삼", "MEMS", "개발자", 0, 0, 0, 0),
            5: ("MEMS004", "가상사", "MEMS", "개발자", 0, 0, 0, 0),
            7: ("UI001", "가상오", "UI", "개발자", 1, 0, 0, 0),
            8: ("UI002", "가상육", "UI", "직원", 0, 0, 0, 0),
            9: ("admin", "admin", None, "", 1, 1, 1, 0),
            10: ("viewer", "viewer", None, "", 0, 0, 0, 0),
        }
        for uid, (username, name, dept, type_, active, staff, su, mcp) in expect.items():
            u = users[uid]
            assert (u["username"], u["name"], u["department_id"], u["type"], u["is_active"], u["is_staff"],
                    u["is_superuser"], u["must_change_password"]) == (username, name, dept, type_, active, staff, su, mcp)
        old_accounts = {a["id"]: a for a in dump(con.cursor(), "auth_user")}
        for old_id, new_id in USER_MAP.items():
            a, u = old_accounts[old_id], users[new_id]
            for k in ("password", "last_login", "date_joined", "first_name", "last_name", "email"):
                assert u[k] == a[k], (new_id, k)
        assert users[1]["part"] == "파트1"
        for uid in (7, 8):  # 계정 없던 멤버: 사용할 수 없는 비밀번호
            assert users[uid]["password"].startswith("!") and users[uid]["password"] != h
            assert users[uid]["last_login"] is None

        # 나머지 표: PK·FK·시각·JSON·null·해시가 원본과 같다(계정 FK만 대응표로 바뀜, 텔레그램 연결 대기 칸은 비움)
        for t in COPIED:
            expected = dump(con.cursor(), t)
            for row in expected:
                if t == "duty_department_managers":
                    row["user_id"] = row.pop("member_id")
                for k in ("user_id", "by_id"):
                    if t != "duty_department_managers" and row.get(k) is not None:
                        row[k] = USER_MAP[row[k]]
                if t == "duty_telegramalarmprofile":
                    row["link_code"] = row["link_expires_at"] = None
            got = dump(cur, t)
            assert got == expected, t
            assert len(got) > 0, t

        # 이후 새 행 id가 기존 최댓값보다 크다(AUTOINCREMENT 시퀀스가 따라옴)
        seq = dict(fetch(cur, "SELECT name, seq FROM sqlite_sequence"))
        for t in ["duty_user", *COPIED]:
            if t == "duty_department":
                continue  # code PK
            assert seq[t] >= fetch(cur, f'SELECT max(id) FROM "{t}"')[0][0], t
        assert target_rows()["duty_user_groups"] == 0

    assert dump_one("duty_alarmdelivery", 90)["destination"] == "sub:70"
    assert User.objects.get(pk=1).push_subscriptions.get().pk == 70
    assert User.objects.get(pk=1).calendar_feed.token_hash == TOKEN_HASH  # UID의 member_pk = User id = 멤버 id
    assert User.objects.get(pk=9).alarm_rules.get().pk == 81
    assert set(Department.objects.get(code="MEMS").managers.values_list("pk", flat=True)) == {1}
    assert User.objects.create_user("new-one", name="새사람", password=PW).pk > 10
    assert ChangeLog.objects.create(period_id=3, date="2026-11-04", cell="dawn", after_id=7).pk > 32

    # 출력: 건수만, 이름·비밀값 없음
    assert "duty_commute: 예전 3 → 새 3" in output
    assert "세션 1" in output and "axes 기록 1" in output and "관리 화면 기록 1" in output
    assert "코드로 바꾼 계정 1" in output
    for secret in [*NAMES, pw_hash(), TOKEN_HASH, ENDPOINT, CHAT_ID, "LINKCODE1", "p256-secret", "auth-secret"]:
        assert secret not in output


def dump_one(table, pk):
    with connection.cursor() as cur:
        return next(r for r in dump(cur, table) if r["id"] == pk)


def test_discarded_tables_are_not_copied(old, db):
    path, con = old
    seed(con)
    run(path)
    with connection.cursor() as cur:
        for t in ("django_session", "axes_accessattempt", "django_admin_log"):
            assert fetch(cur, f'SELECT count(*) FROM "{t}"')[0][0] == 0, t


def test_passwords_survive_login(old, db):
    path, con = old
    seed(con)
    run(path)
    ok = lambda u: Client().post(reverse("login"), {"username": u, "password": PW}).status_code == 302  # noqa: E731
    assert ok("MEMS001")  # 연결 계정: 해시 그대로
    assert ok("admin")  # 연결 없던 어드민 계정
    assert not ok("old-login")  # 아이디는 멤버 코드로 바뀜
    assert not ok("MEMS003")  # 멤버 퇴사 → 비활성
    assert not ok("MEMS002")  # 계정 비활성
    assert not ok("UI001")  # 계정 없던 멤버


def add_old(sql):
    return lambda con: (con.executescript(sql), con.commit())


def corrupt_page(con):
    root = con.execute("SELECT rootpage FROM sqlite_master WHERE name='duty_member'").fetchone()[0]
    size = con.execute("PRAGMA page_size").fetchone()[0]
    path = con.execute("PRAGMA database_list").fetchone()[2]
    con.close()
    with open(path, "r+b") as f:
        f.seek((root - 1) * size)
        f.write(b"\xff" * 64)


@pytest.mark.parametrize("break_source, message", [
    (add_old("DROP TABLE django_session;"), "필요한 표"),
    (add_old("ALTER TABLE duty_period DROP COLUMN overwrite_from;"), "필요한 표"),
    (add_old("ALTER TABLE duty_member DROP COLUMN must_change_password;"), "필요한 표"),
    (add_old("INSERT INTO duty_commute VALUES(99,'2026-11-04','dawn',999,3);"), "foreign_key_check"),
    (add_old("DELETE FROM django_migrations WHERE name='0009_calendarfeed';"), "0001~0009"),
    (add_old("INSERT INTO django_migrations(app,name,applied) VALUES('duty','0010_x','2026-11-11');"), "0001~0009"),
    (add_old("INSERT INTO auth_user VALUES(11,'x',NULL,0,'MEMS003','','',0,1,'2026-10-01','');"), "아이디 중복"),
    (add_old("INSERT INTO auth_user VALUES(11,'x',NULL,0,'가상일','','',0,1,'2026-10-01','');"), "이름 중복"),
    (add_old("INSERT INTO auth_user VALUES(11,'x',NULL,0,'bad name','','',0,1,'2026-10-01','');"), "규칙"),
    (add_old("UPDATE duty_member SET name='가상>칠' WHERE id=7;"), "규칙"),
    (add_old(f"UPDATE duty_member SET name='{'가' * 33}' WHERE id=7;"), "규칙"),
    (add_old("INSERT INTO auth_group VALUES(1,'g');"), "그룹"),
    (add_old("INSERT INTO auth_group VALUES(1,'g'); INSERT INTO auth_user_groups VALUES(1,1,1);"), "그룹"),
    (add_old("INSERT INTO auth_user_user_permissions VALUES(1,1,1);"), "그룹"),
    (corrupt_page, "손상"),
])
def test_precheck_failure_writes_nothing(old, db, break_source, message):
    path, con = old
    seed(con)
    break_source(con)
    with pytest.raises(CommandError, match=message) as e:
        run(path)
    for secret in NAMES:
        assert secret not in str(e.value)
    assert set(target_rows().values()) == {0}


def test_target_not_empty(old, db):
    path, con = old
    seed(con)
    Department.objects.create(code="X", name="가상실X", shifts="normal")
    with pytest.raises(CommandError, match="비어 있지 않"):
        run(path)
    assert User.objects.count() == 0 and Department.objects.count() == 1


def test_target_wrong_migrations(old, db):
    path, con = old
    seed(con)
    with connection.cursor() as cur:
        cur.execute("INSERT INTO django_migrations(app,name,applied) VALUES('duty','0002_x','2026-11-11')")
    with pytest.raises(CommandError, match="0001_v2"):
        run(path)
    assert set(target_rows().values()) == {0}


def test_same_path_refused(old, db, monkeypatch):
    path, con = old
    seed(con)
    monkeypatch.setitem(connection.settings_dict, "NAME", str(path))
    with pytest.raises(CommandError, match="같은 파일"):
        run(path)
    assert set(target_rows().values()) == {0}


def test_source_opened_read_only(old, db):
    path, con = old
    seed(con)
    before = path.read_bytes()
    run(path)
    assert path.read_bytes() == before


@pytest.fixture
def ro_dir(tmp_path):
    d = tmp_path / "ro"
    d.mkdir()
    yield d
    d.chmod(0o755)


def test_wal_backup_in_read_only_dir(old, ro_dir, db):
    path, con = old
    seed(con)
    con.execute("PRAGMA journal_mode=WAL")
    backup = ro_dir / "old-v1.sqlite3"
    dest = sqlite3.connect(backup)
    con.backup(dest)
    dest.close()
    assert backup.read_bytes()[18:20] == b"\x02\x02"  # 헤더가 WAL 모드
    ro_dir.chmod(0o555)
    output = run(backup)
    assert "duty_commute: 예전 3 → 새 3" in output
    assert sorted(p.name for p in ro_dir.iterdir()) == ["old-v1.sqlite3"]  # -wal·-shm 안 만듦


def test_failure_midway_rolls_back_everything(old, db, monkeypatch):
    path, con = old
    seed(con)
    real = convert_v1._copy

    def boom(old_db, table, *a):
        if table == "duty_alarmdelivery":  # 사용자·앞 표들은 이미 들어간 뒤
            raise RuntimeError("고의 실패")
        return real(old_db, table, *a)

    monkeypatch.setattr(convert_v1, "_copy", boom)
    with pytest.raises(RuntimeError):
        run(path)
    assert set(target_rows().values()) == {0}
