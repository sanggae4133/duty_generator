# 근무표 일반화 1단계(구조 일반화) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** IT 칸 상수에 묶인 앱을 "근무표(Board) + 근무 정의(BoardShift) + 그룹 권한" 구조로 바꾼다. 사용자 화면·알림 문구·링크·칸 순서는 한 글자도 바뀌지 않는다.

**Architecture:** 근무표·근무 정의·그룹을 모델로 추가하고(기존 데이터는 IT 근무표로 이전), `shifts.py` 의 상수를 "정의 목록을 받는 순수 헬퍼"로 바꾼다. 모든 서비스가 근무표를 명시 인자로 받고, 그날의 주인은 회차 기간으로 정한다. 권한은 Django 그룹(근무표 관리 그룹·부서 입력 그룹)으로 판단한다.

**Tech Stack:** Python 3.12, Django 5.2, SQLite(WAL), pytest + pytest-django, htmx 템플릿.

**Spec:** `docs/superpowers/specs/2026-11-15-boards-design.md` (1단계 = 11절 "1단계", 마이그레이션 = 10절 "1단계")

## Global Constraints

- 사용자 화면 글자·알림 문구·알림 링크·칸 순서 불변. 예외: 슈퍼유저 전용 Django 관리 화면(설계 7절).
- 기존 테스트의 단언(assert) 기대 값은 바꾸지 않는다. 허용하는 기계적 변경은 설계 11절 (a)~(d)뿐.
- 각 작업이 끝난 시점에 `.venv/bin/pytest -W error -q` 전체가 통과한다(경고 0개).
- TDD: 실패하는 테스트를 먼저 쓰고 실패를 확인한 뒤 구현한다.
- DB를 바꾸는 규칙은 `duty/services/`. 뷰·명령에서 모델을 직접 고치지 않는다.
- ORM 없는 순수 모듈: `shifts`·`generator`·`csv_io`·`ics`·`alarms/`(senders 제외).
- "오늘"은 `from . import perms` 후 `perms.today()`.
- 정해진 값 칸은 `choices` + DB `CheckConstraint`. 기록을 남길 FK는 `PROTECT`.
- 마이그레이션 파일은 지우지 않는다. manage.py 명령은 `DJANGO_SETTINGS_MODULE=config.test_settings` 로 돌린다(실명 DB에 접속하지 않게).
- 실명 데이터 금지(테스트·fixture는 가상 이름). `data/`, DB 파일, `.superpowers/`, `.env` 는 열지 않는다.
- 화면에 보이는 문구는 한국어. 커밋 메시지는 `feat:`/`fix:`/`docs:`/`style:` + 한국어 요약.
- 1단계에 넣지 않는 것: 사유·메모·점심당번·휴장일·로그인 90일·근무표 고르기 버튼(2단계), 직접 입력 화면·그룹 화면(3단계).

## 작업 순서와 마이그레이션 번호

| Task | 내용 | 마이그레이션 |
|---|---|---|
| 1 | 근무표·근무 정의·그룹 모델(추가만), 테스트 픽스처, 기존 테스트에 IT 근무표 지정 | 0010_boards, 0011_boards_data |
| 2 | ControlDuty → DutyAssignment | 0012_dutyassignment, 0013_controlduty_to_assignment, 0014_delete_controlduty |
| 3 | shifts.py 정의 헬퍼, services/boards.py, 표시 계열 | 없음 |
| 4 | 그룹 권한(perms·managers 호환·메뉴) | managers M2M 삭제(다음 번호) |
| 5 | 그날의 주인·근무표 단위 조회·근무 변경, 영상 가짜 데이터 | 없음 |
| 6 | 근무표 단위 회차·배포·배포 취소·회차 뷰 권한·NOT NULL | boards_not_null(다음 번호) |
| 7 | 생성·취합·통계를 근무 정의로 | 없음 |
| 8 | 알림·캘린더·변경 알림을 근무 정의로 | AlarmRule 제약(다음 번호) |
| 9 | 관리 화면(근무표·그룹·사용자) | 없음 |
| 10 | 문서·남은 상수 확인·화면 확인·PR | 없음 |

각 작업의 정확한 마이그레이션 번호는 그 작업 본문에 적혀 있다(앞 작업 다음 번호). 작업 본문의 "검증" 메모는 계획을 쓸 때 저장소 사본에서 돌려 본 결과다. 실제 테스트 개수는 앞 작업 결과에 따라 조금 다를 수 있으니, 기대 결과의 핵심은 "실패 → 통과, 전체 경고 0"이다.

---

### Task 1: 근무표·근무 정의·그룹 모델과 마이그레이션(추가만)

> 검증: 아래 코드를 main 사본(`git archive main`)에 그대로 넣어 확인했다. 저장소는 고치지 않았다. 결과: `.venv/bin/pytest -W error -q` → **790 passed**(기존 775 + 새 15), 경고 0개. `makemigrations duty --check --dry-run` → "No changes detected in app 'duty'". Step 2(ImportError)와 Step 10(NodeNotFoundError, 3 failed)의 실패도 사본에서 재현했다. 기존 테스트 파일의 회차 생성 전부에 board 를 넣은 뒤, 임시 `pre_save` 검사로 "board 없는 Period 저장"이 테스트 코드에서는 0건임을 확인했다(남은 1건은 앱 코드 `views/manage.py` 회차 만들기 화면: `tests/test_views_manage.py::test_create_period`. Task 6 이 고친다).
>
> 이 작업의 범위: 스키마·데이터 추가만 한다. 앱 코드의 읽기·권한은 하나도 바꾸지 않으므로 화면·알림·링크는 그대로다(권한은 계속 `is_staff`·`managers`, 부서 필터는 계속 `DEPT_ORDER`). `board` 칸은 전부 null 허용이다.
> 뒤 작업으로 넘기는 것: `ControlDuty`→`DutyAssignment`(Task 2), `shifts.py` 헬퍼(by_key·ordered·shift_defs·slot_defs…)와 `SLOT_GROUP*`(Task 3), `DEPT_ORDER`→`Department.order`(Task 3), perms 그룹화·managers 호환 property·M2M 삭제·`DepartmentForm`(Task 4), `tools/help_videos/seed.py`(Task 5), board NOT NULL·회차 만들기 화면의 board(Task 6), 관리 화면 Board·그룹(Task 9), 문서(Task 10).

**Files:**
- Modify: `duty/shifts.py:3`(import), `duty/shifts.py:52`(`CELLS` 줄 → `SHIFT_KEYS`·`SLOT_KEYS`·`KEYS`·`CELLS = KEYS`·`Def`)
- Modify: `duty/models.py:2`(Group import), `duty/models.py:8`(shifts import), `duty/models.py:29-41`(`class Department`부터 `__str__` 뒤 빈 줄까지 → InputMode·Board·BoardShift·GroupKeeper + Department 새 칸·save), `duty/models.py:98`(Period.board), `duty/models.py:139`·`144`(Commute.shift choices·제약 → SHIFT_KEYS), `duty/models.py:176`(ChangeLog 제약 → KEYS), `duty/models.py:188`(RosterPref.board), `duty/models.py:294`(AlarmRule.board), `duty/models.py:323`·`336`(AlarmDelivery 주석·제약 → KEYS)
- Create: `duty/migrations/0010_boards.py`(스키마, makemigrations 생성 그대로), `duty/migrations/0011_boards_data.py`(데이터, reverse 포함)
- Create: `tests/it_defs.py`
- Modify: `tests/conftest.py:5`(import), `tests/conftest.py:15-17`(it_board 추가, depts), `tests/conftest.py:34-36`(admin_user)
- Modify(허용 변환 a, 단언 불변): `tests/test_calendar_feed.py`, `tests/test_change_notice.py`, `tests/test_changes.py`, `tests/test_collect.py`, `tests/test_db_constraints.py`, `tests/test_generate.py`, `tests/test_models.py`, `tests/test_period_lifecycle.py`, `tests/test_periods.py`, `tests/test_publish.py`, `tests/test_roster.py`, `tests/test_roster_prefs.py`, `tests/test_run_alarms.py`, `tests/test_stats.py`, `tests/test_views_collect.py`, `tests/test_views_manage.py`, `tests/test_views_roster.py`
- Test: `tests/test_boards_models.py`(새), `tests/test_migration_boards.py`(새)

**Interfaces:**
- Consumes: 없음(첫 작업)
- Produces:
  - `duty.shifts`: `SHIFT_KEYS: tuple[str, ...] = ("dawn","normal","dinner","night")`, `SLOT_KEYS: tuple[str, ...] = ("slot0",…,"slot9")`, `KEYS: list[str]`(dawn, normal, dinner, slot0..slot9, night — 지금 CELLS 와 같은 값·순서), `CELLS = KEYS`(옛 이름, 같은 객체), `@dataclass(frozen=True) class Def(key: str, name: str, start: time | None, end: time | None, eligible_shifts: tuple[str, ...] = (), eligible_types: tuple[str, ...] = (), default_alarm: bool = False, active: bool = True)`. `COMMUTE_SHIFTS`·`CONTROL_SLOTS`·`SHIFT_TIMES`·`cell_label` 등 옛 상수·함수는 그대로 남는다.
  - `duty.models`:
    - `InputMode(TextChoices)`: `COLLECT="collect"`("부서별 취합"), `DIRECT="direct"`("관리자 직접 입력"). `Board.InputMode` 는 별칭.
    - `Board(code: CharField(16, unique), name: CharField(32), input_mode: choices InputMode 기본 collect, admin_group: OneToOne(Group, PROTECT, related_name="admin_board", editable=False))`. Meta ordering `["id"]`, 제약 `board_input_mode_valid`. `save()`: `admin_group_id` 가 없으면 `Group(name=f"{name} 근무표 관리")`를 만든다(이름을 바꿔 다시 저장해도 그룹은 그대로).
    - `BoardShift(board: FK(Board, PROTECT, related_name="shifts"), key: CharField(8, choices=[(k, "근무조 1~4"/"관제 1~10") for k in KEYS]), name: CharField(32), start/end: TimeField(null), eligible_shifts: JSON list, eligible_types: JSON list, default_alarm: bool, active: bool=True)`. 제약 `boardshift_one_per_key`(board,key unique), `boardshift_one_per_name`(board,name unique: 이름이 CSV 열·화면 라벨이 되므로), `boardshift_key_valid`(key in KEYS), `boardshift_times_valid`(start·end 필수, start < end).
    - `GroupKeeper(group: FK(Group, CASCADE, related_name="keepers"), user: FK(User, CASCADE, related_name="kept_groups"))`. 제약 `groupkeeper_once`.
    - `Department.board: FK(Board, PROTECT, null, blank, related_name="departments")`, `Department.order: IntegerField(default=99)`(순서 칸을 비운 새 부서는 옛 `DEPT_ORDER` 밖 부서처럼 맨 뒤), `Department.input_group: OneToOne(Group, PROTECT, null, editable=False, related_name="input_department")`. `Department.save()`: board 가 collect 근무표이고 input_group 이 없으면 `Group(name=f"{name} 출근표 입력")`을 만든다. `managers` M2M 은 그대로 남는다.
    - `Period.board: FK(Board, PROTECT, null, blank, related_name="periods")`, `AlarmRule.board: FK(Board, PROTECT, null, blank, related_name="alarm_rules")`, `RosterPref.board: FK(Board, SET_NULL, null, blank, related_name="+")`.
    - 제약 상수 교체: `Commute.shift` choices `[(k, k) for k in SHIFT_KEYS]`·`commute_shift_valid`=SHIFT_KEYS, `changelog_cell_valid`=KEYS, `alarmdelivery_cell_valid`=`[*KEYS, "report"]`(값이 같아 제약 SQL 그대로). models.py 는 더 이상 `CELLS`·`COMMUTE_SHIFTS` 를 import 하지 않는다(`CONTROL_SLOTS` 는 ControlDuty 제약 때문에 남음, Task 2 가 정리).
  - 마이그레이션: `0010_boards`(의존: `auth.0012_alter_user_first_name_max_length`, `duty.0009_roster_history`), `0011_boards_data`(의존: `duty.0010_boards`). 다음 마이그레이션 번호는 `0012`(Task 2 의 `0012_dutyassignment`). 0011 이 만드는 것: IT 근무표 `code="it"`, `name="IT 당번표"`, 관리 그룹 `"IT 근무표 관리"`, 정의 14행, 부서별 `"{부서 이름} 출근표 입력"` 그룹(managers 복사), 부서 order(MEMS 0·TMCH 1·MD 2·UI 3·그 밖 99), is_staff → IT 관리 그룹, 슈퍼유저 → 모든 새 그룹의 GroupKeeper, 모든 회차 board=IT, 배포 회차의 빈 overwrite_from = start_date, 보고서 규칙 board=IT.
  - `tests/it_defs.py`: `IT_DEFS: list[Def]`(KEYS 순 14개, 지금 shifts.py 상수와 같은 값)
  - `tests/conftest.py`: fixture `it_board(db) -> Board`(code "it", 정의 14행 보장), `depts(it_board)`(board=it_board, order=DEPTS index: MEMS 0·TMCH 1·MD 2·UI 3), `admin_user(it_board)`(is_staff=True 유지 + `it_board.admin_group` 멤버)

- [ ] **Step 1: IT 정의와 모델 테스트를 먼저 쓴다**

`tests/it_defs.py`(새 파일):
```python
"""테스트 전용 IT 근무 정의. 1단계 전 duty/shifts.py 상수(COMMUTE_SHIFTS·CONTROL_SLOTS·SHIFT_TIMES)와 같은 값."""
from datetime import time

from duty.shifts import Def

_BOTH = ("normal", "dinner")
_DEV = ("개발자",)
_SLOTS = [  # (시작, 끝, 자격 근무조)
    ("08:30", "09:30", ("normal",)),
    ("09:30", "10:30", _BOTH),
    ("10:30", "11:30", _BOTH),
    ("11:30", "12:30", _BOTH),
    ("12:30", "13:30", _BOTH),
    ("13:30", "14:30", _BOTH),
    ("14:30", "15:30", _BOTH),
    ("15:30", "16:30", _BOTH),
    ("16:30", "17:00", _BOTH),
    ("17:00", "18:00", ("dinner",)),
]

IT_DEFS: list[Def] = [  # KEYS 순. active 는 기본값 True(IT 정의는 모두 켜짐, boards.defs 결과와 같다)
    Def("dawn", "새벽", time(6, 30), time(15, 30), default_alarm=True),
    Def("normal", "정상", time(8, 0), time(17, 0)),
    Def("dinner", "석식교대", time(9, 0), time(18, 0), default_alarm=True),
    *[Def(f"slot{i}", f"{a}~{b}", time.fromisoformat(a), time.fromisoformat(b), eligible_shifts=e, eligible_types=_DEV)
      for i, (a, b, e) in enumerate(_SLOTS)],
    Def("night", "야간", time(13, 30), time(21, 30), default_alarm=True),
]
```

`tests/test_boards_models.py`(새 파일):
```python
"""근무표·근무 정의·그룹 모델(1단계)."""
from datetime import time

import pytest
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction

from duty.models import Board, BoardShift, Department, GroupKeeper
from duty.shifts import KEYS
from tests.it_defs import IT_DEFS


def _bad(fn):
    with pytest.raises(IntegrityError), transaction.atomic():
        fn()


def test_it_defs_match_keys_order():
    assert [d.key for d in IT_DEFS] == KEYS


def test_it_board_fixture_has_14_defs_and_admin_group(it_board):
    assert it_board.code == "it" and it_board.input_mode == "collect"
    assert sorted(it_board.shifts.values_list("key", flat=True)) == sorted(KEYS)
    assert it_board.admin_group_id is not None


def test_board_save_creates_admin_group(db):
    b = Board.objects.create(code="ops", name="운영팀", input_mode=Board.InputMode.DIRECT)
    assert b.admin_group.name == "운영팀 근무표 관리"
    before = Group.objects.count()
    b.name = "운영팀2"
    b.save()  # 이미 있으면 새로 만들지 않는다
    assert Group.objects.count() == before and b.admin_group.name == "운영팀 근무표 관리"


def test_department_save_creates_input_group_for_collect_board(it_board):
    d = Department.objects.create(code="QA", name="품질", shifts="normal", board=it_board)
    assert d.input_group.name == "품질 출근표 입력"


def test_department_without_collect_board_has_no_input_group(db):
    ops = Board.objects.create(code="ops", name="운영팀", input_mode=Board.InputMode.DIRECT)
    assert Department.objects.create(code="OPS", name="운영", shifts="normal", board=ops).input_group is None
    assert Department.objects.create(code="NB", name="무소속", shifts="normal").input_group is None


def test_depts_fixture_on_it_board_with_input_groups(depts, it_board):
    assert {d.board_id for d in depts.values()} == {it_board.id}
    assert all(d.input_group_id for d in depts.values())


def test_admin_user_in_it_admin_group(admin_user, it_board):
    assert admin_user.groups.filter(pk=it_board.admin_group_id).exists()


def test_board_constraints(it_board):
    _bad(lambda: Board.objects.create(code="it", name="중복"))
    _bad(lambda: Board.objects.create(code="x", name="x", input_mode="bogus"))


def test_boardshift_constraints(it_board):
    _bad(lambda: BoardShift.objects.create(board=it_board, key="dawn", name="중복", start=time(6), end=time(7)))
    ops = Board.objects.create(code="ops", name="운영팀")
    _bad(lambda: BoardShift.objects.create(board=ops, key="lunch", name="점심", start=time(11), end=time(12)))
    _bad(lambda: BoardShift.objects.create(board=ops, key="dawn", name="이른", start=time(9), end=time(8)))
    _bad(lambda: BoardShift.objects.create(board=ops, key="dawn", name="이른"))
    BoardShift.objects.create(board=ops, key="dawn", name="이른", start=time(7, 30), end=time(16, 30))


def test_boardshift_name_unique_per_board(it_board):
    ops = Board.objects.create(code="ops", name="운영팀")
    BoardShift.objects.create(board=ops, key="dawn", name="새벽", start=time(7), end=time(16))  # 다른 근무표와는 겹쳐도 된다
    _bad(lambda: BoardShift.objects.create(board=ops, key="normal", name="새벽", start=time(9), end=time(18)))


def test_groupkeeper_unique(admin_user, it_board):
    GroupKeeper.objects.create(group=it_board.admin_group, user=admin_user)
    _bad(lambda: GroupKeeper.objects.create(group=it_board.admin_group, user=admin_user))


def test_boardshift_key_labels_are_neutral():
    labels = dict(BoardShift._meta.get_field("key").choices)
    assert labels["dawn"] == "근무조 1" and labels["night"] == "근무조 4"
    assert labels["slot0"] == "관제 1" and labels["slot9"] == "관제 10"


def test_depts_fixture_order_matches_old_filter_order(depts):
    assert [d.code for d in sorted(depts.values(), key=lambda d: d.order)] == ["MEMS", "TMCH", "MD", "UI"]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_boards_models.py -q`
Expected: 수집 단계 ERROR 1개. `ImportError: cannot import name 'Board' from 'duty.models'`(테스트 파일의 첫 duty import. conftest 는 아직 그대로라 정상으로 읽힌다).

- [ ] **Step 3: `duty/shifts.py`에 키 상수와 Def 를 더한다**

3번째 줄 `from datetime import date, time, timedelta` 를 아래로 바꾼다.
```python
from dataclasses import dataclass
from datetime import date, time, timedelta
```
52번째 줄 `CELLS: list[str] = ["dawn", "normal", "dinner", *[slot_cell(i) for i in range(len(CONTROL_SLOTS))], "night"]` 를 아래로 바꾼다(위치는 지금처럼 `slot_index` 정의 뒤, `cell_label` 앞).
```python
SHIFT_KEYS = ("dawn", "normal", "dinner", "night")  # 근무조 키(한 사람 하루 하나)
SLOT_KEYS = tuple(slot_cell(i) for i in range(10))  # 장중관제 칸 키(자동 생성, 칸당 1명)
# 근무표가 쓸 수 있는 키 전부. 순서 = 알림·캘린더 칸 순회 순서(바꾸면 알림 hash 가 달라져 다시 나간다)
KEYS: list[str] = ["dawn", "normal", "dinner", *SLOT_KEYS, "night"]
CELLS = KEYS  # 1단계 동안 남기는 옛 이름


@dataclass(frozen=True)
class Def:
    """근무 정의 하나(BoardShift 를 ORM 없이 다루는 값)."""
    key: str
    name: str
    start: time | None
    end: time | None
    eligible_shifts: tuple[str, ...] = ()
    eligible_types: tuple[str, ...] = ()
    default_alarm: bool = False
    active: bool = True  # 꺼진 정의: 새 입력·생성·선택지에서 빠지고(boards.active_defs) 이름 찾기에는 남는다(boards.defs)
```
(나머지 함수는 이 작업에서 그대로 둔다. `CELLS` 값·순서는 전과 같다.)

- [ ] **Step 4: `duty/models.py`에 모델을 더하고 제약 상수를 바꾼다**

앞에서부터 순서대로 고친다(줄 번호는 앞 편집으로 밀리므로 기준 문장으로 찾는다).

2번째 줄:
```python
from django.contrib.auth.models import AbstractUser, Group, UserManager as DjangoUserManager
```
8번째 줄(`CELLS`·`COMMUTE_SHIFTS` 는 빼고 새 이름을 넣는다, 지적 9):
```python
from .shifts import CONTROL_SLOTS, DEVELOPER, KEYS, SHIFT_KEYS, STAFF, is_slot_cell, slot_index, weekdays
```
29~41번째 줄(`class Department(models.Model):`부터 `__str__` 의 `return self.name` 뒤 빈 줄까지)을 아래로 바꾼다. 42번째 줄 `def shift_keys` 는 그대로 남고, 바꾼 블록 끝에 빈 줄 하나를 두고 이어진다.
```python
class InputMode(models.TextChoices):
    COLLECT = "collect", "부서별 취합"
    DIRECT = "direct", "관리자 직접 입력"


class Board(models.Model):
    """근무표 하나(IT 당번표, 시장운영실…). 회차·부서·근무 정의가 여기에 속한다."""
    InputMode = InputMode

    code = models.CharField("코드", max_length=16, unique=True, help_text="짧은 영문. IT = it")
    name = models.CharField("이름", max_length=32)
    input_mode = models.CharField("입력 방식", max_length=8, choices=InputMode.choices, default=InputMode.COLLECT)
    admin_group = models.OneToOneField(Group, on_delete=models.PROTECT, related_name="admin_board",
                                       verbose_name="관리 그룹", editable=False)

    class Meta:
        verbose_name = verbose_name_plural = "근무표"
        ordering = ["id"]
        constraints = [_one_of("input_mode", InputMode.values, "board_input_mode_valid")]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.admin_group_id is None:  # 어느 길로 만들어도 관리 그룹이 빠지지 않게
            self.admin_group = Group.objects.create(name=f"{self.name} 근무표 관리")
        super().save(*args, **kwargs)


def _key_label(key: str) -> str:
    # 관리 화면 표시는 중립적으로(시장운영실이 dawn 을 '새벽'으로 오해하지 않게). DB 값은 키 그대로
    return f"관제 {slot_index(key) + 1}" if is_slot_cell(key) else f"근무조 {SHIFT_KEYS.index(key) + 1}"


class BoardShift(models.Model):
    """근무 정의: 근무표가 쓰는 키 하나에 붙인 이름·시각·자격."""
    board = models.ForeignKey(Board, on_delete=models.PROTECT, related_name="shifts", verbose_name="근무표")
    key = models.CharField("키", max_length=8, choices=[(k, _key_label(k)) for k in KEYS])
    name = models.CharField("이름", max_length=32)
    start = models.TimeField("시작", null=True, blank=True)
    end = models.TimeField("끝", null=True, blank=True)
    eligible_shifts = models.JSONField("자격 근무조", default=list, blank=True)
    eligible_types = models.JSONField("자격 구분", default=list, blank=True)
    default_alarm = models.BooleanField("기본 알림 대상", default=False)
    active = models.BooleanField("사용", default=True)

    class Meta:
        verbose_name = verbose_name_plural = "근무 정의"
        constraints = [
            models.UniqueConstraint(fields=["board", "key"], name="boardshift_one_per_key"),
            # 이름은 CSV 열 이름·화면 라벨이 된다. 겹치면 CSV 열이 하나로 합쳐져 값이 사라지므로 DB 가 막는다
            models.UniqueConstraint(fields=["board", "name"], name="boardshift_one_per_name"),
            _one_of("key", KEYS, "boardshift_key_valid"),
            # 1단계 키(근무조·관제)는 시각이 필수이고 당일 근무만(2단계에 시각 없는 점심당번을 더한다)
            models.CheckConstraint(name="boardshift_times_valid",
                                   condition=Q(start__isnull=False, end__isnull=False, start__lt=models.F("end"))),
        ]

    def __str__(self):
        return f"{self.board} {self.name}"


class GroupKeeper(models.Model):
    """그룹 관리자: 그 그룹에 멤버를 넣고 빼기만 한다."""
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="keepers", verbose_name="그룹")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="kept_groups",
                             verbose_name="그룹 관리자")

    class Meta:
        verbose_name = verbose_name_plural = "그룹 관리자"
        constraints = [models.UniqueConstraint(fields=["group", "user"], name="groupkeeper_once")]


class Department(models.Model):
    code = models.CharField("코드", max_length=8, primary_key=True)
    name = models.CharField("이름", max_length=32, unique=True)
    shifts = models.CharField("가능한 출근조", max_length=64, help_text="쉼표 구분: dawn,normal,dinner,night")
    managers = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="managed_departments", verbose_name="입력 담당자")
    board = models.ForeignKey(Board, on_delete=models.PROTECT, null=True, blank=True, related_name="departments",
                              verbose_name="근무표")
    order = models.IntegerField("순서", default=99, help_text="근무표 부서 필터 순서(작은 값이 앞, 기본 99는 맨 뒤)")
    input_group = models.OneToOneField(Group, on_delete=models.PROTECT, null=True, blank=True, editable=False,
                                       related_name="input_department", verbose_name="입력 그룹")

    class Meta:
        verbose_name = verbose_name_plural = "부서"
        ordering = ["code"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # 부서별 취합 근무표의 부서는 입력 그룹이 있어야 한다(픽스처·관리 화면·서비스 어느 길로 만들어도)
        if self.input_group_id is None and self.board_id is not None and self.board.input_mode == InputMode.COLLECT:
            self.input_group = Group.objects.create(name=f"{self.name} 출근표 입력")
        super().save(*args, **kwargs)

```

Period: `overwrite_from = models.DateField(null=True, blank=True)` 바로 아래에 더한다.
```python
    board = models.ForeignKey(Board, on_delete=models.PROTECT, null=True, blank=True, related_name="periods",
                              verbose_name="근무표")
```

Commute(지적 9): 
```python
    shift = models.CharField(max_length=8, choices=list(COMMUTE_SHIFTS.items()))
```
→
```python
    shift = models.CharField(max_length=8, choices=[(k, k) for k in SHIFT_KEYS])
```
그리고 `_one_of("shift", COMMUTE_SHIFTS, "commute_shift_valid")` → `_one_of("shift", SHIFT_KEYS, "commute_shift_valid")`.
(choices 라벨은 화면 어디에도 쓰이지 않는다: `get_shift_display` 사용처 0, Commute 는 관리 화면에 등록돼 있지 않다.)

ChangeLog: `_one_of("cell", CELLS, "changelog_cell_valid")` → `_one_of("cell", KEYS, "changelog_cell_valid")`.

RosterPref: `history = models.BooleanField(default=True)  # 변경 내역…` 줄 바로 아래에 더한다.
```python
    board = models.ForeignKey(Board, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")  # 마지막으로 본 근무표
```

AlarmRule: `types = models.JSONField("유형", default=list)` 바로 아래, `class Meta` 앞에 더한다.
```python
    # 보고서 규칙의 근무표. 개인 규칙은 비운다(주인 부서의 근무표)
    board = models.ForeignKey(Board, on_delete=models.PROTECT, null=True, blank=True, related_name="alarm_rules",
                              verbose_name="근무표")
```

AlarmDelivery: 주석 `cell = models.CharField(max_length=8)  # CELLS 또는 "report"` → `# KEYS 또는 "report"`, 제약 `_one_of("cell", [*CELLS, "report"], "alarmdelivery_cell_valid")` → `_one_of("cell", [*KEYS, "report"], "alarmdelivery_cell_valid")`.

- [ ] **Step 5: 스키마 마이그레이션 `0010_boards`를 만든다**

Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --name boards`
Expected: `duty/migrations/0010_boards.py` 생성. 의존성 `('auth', '0012_alter_user_first_name_max_length'), ('duty', '0009_roster_history')`. 출력 연산 순서:
```
    + Add field input_group to department
    + Add field order to department
    ~ Alter field shift on commute
    + Create model Board
    + Add field board to alarmrule
    + Add field board to department
    + Add field board to period
    + Add field board to rosterpref
    + Create model BoardShift
    + Create model GroupKeeper
    + Create constraint board_input_mode_valid on model board
    + Create constraint boardshift_one_per_key on model boardshift
    + Create constraint boardshift_one_per_name on model boardshift
    + Create constraint boardshift_key_valid on model boardshift
    + Create constraint boardshift_times_valid on model boardshift
    + Create constraint groupkeeper_once on model groupkeeper
```
`Add field order` 는 모델을 따라 `default=99` 로 나온다. `commute_shift_valid`·`changelog_cell_valid`·`alarmdelivery_cell_valid` 은 값이 같아 연산이 나오지 않아야 한다(나오면 상수 값이 다른 것이니 멈추고 확인). 손으로 고치지 않고 생성된 그대로 커밋한다.

- [ ] **Step 6: conftest 픽스처를 바꾼다**

`tests/conftest.py` 5번째 줄 `from duty.models import Department, User` →
```python
from duty.models import Board, BoardShift, Department, User
from tests.it_defs import IT_DEFS
```
15~17번째 줄 `depts` 픽스처 → (지적 8: order = 지금 `DEPT_ORDER` 순서의 index. DEPTS 가 이미 MEMS·TMCH·MD·UI 순이라 enumerate index 와 같다)
```python
@pytest.fixture
def it_board(db):
    # 마이그레이션이 만든 IT 근무표가 있으면 그것을, flush 된 DB(transaction=True 테스트 뒤)면 새로 만든다
    board, _ = Board.objects.get_or_create(code="it", defaults={"name": "IT 당번표", "input_mode": Board.InputMode.COLLECT})
    for d in IT_DEFS:
        BoardShift.objects.get_or_create(board=board, key=d.key, defaults=dict(
            name=d.name, start=d.start, end=d.end, eligible_shifts=list(d.eligible_shifts),
            eligible_types=list(d.eligible_types), default_alarm=d.default_alarm))
    return board


@pytest.fixture
def depts(it_board):
    # order = 지금 근무표 부서 필터 순서(views/roster.py DEPT_ORDER: MEMS·TMCH·MD·UI = DEPTS 순서)
    return {c: Department.objects.create(code=c, name=n, shifts=s, board=it_board, order=i)
            for i, (c, n, s) in enumerate(DEPTS)}
```
34~36번째 줄 `admin_user` →
```python
@pytest.fixture
def admin_user(it_board):
    user = User.objects.create_user("admin", password="unused-Pw-123", name="관리자", is_staff=True)
    user.groups.add(it_board.admin_group)
    return user
```
(허용 변환 a. perms 가 아직 is_staff 를 보므로 `is_staff=True` 는 남긴다.)

- [ ] **Step 7: 모델 테스트 통과를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_boards_models.py -q`
Expected: `13 passed`. (0011 전이라 마이그레이션 데이터가 없어 it_board 가 새로 만들어진다. 0011 뒤에는 마이그레이션이 만든 IT 근무표를 get_or_create 로 쓴다. 두 경우 다 통과한다.)

- [ ] **Step 8: 기존 테스트의 회차 생성에 board 를 넣는다(허용 변환 a, 지적 3)**

규칙: `tests/` 에서 저장되는 `Period(...)`·`Period.objects.create(...)` 마다 첫 인자로 `board=it_board, ` 를 넣는다. 단언문은 하나도 바꾸지 않는다.
- 테스트 함수·픽스처: 인자에 `it_board` 를 더한다(`db` 만 받던 것은 `db` 를 `it_board` 로 바꾼다. it_board 가 db 를 끌어온다).
- 픽스처가 아닌 일반 헬퍼(`test_publish.make_period`, `test_period_lifecycle.make_period`, `test_stats.setup_period`, `test_roster.make_published`, `test_calendar_feed.period`, `test_views_manage._generated`): 호출부를 바꾸지 않도록 첫 줄에 `it_board = Board.objects.get(code="it")` 를 두고 `Board` 를 import 한다. 이 헬퍼들은 모두 make_member·me 를 쓰는 테스트에서만 불리므로 it_board 픽스처가 이미 행을 만들어 둔 상태다.
- 그대로 두는 것: `tests/test_models.py::test_period_dates_are_weekdays` 의 `Period(...)`(저장하지 않고 db 도 쓰지 않는다), `tests/test_migration_boards.py`(옛 상태 모델).

확인용 grep(결과가 위 두 곳만 나와야 한다):
```bash
grep -rn "Period(\|Period.objects.create" tests | grep -v "board="
```
Expected:
```
tests/test_models.py:14:    p = Period(name="p", start_date=date(2026, 11, 6), end_date=date(2026, 11, 10))
```
(Step 9 전이므로 test_migration_boards.py 는 아직 없다.)

정확한 변경(17개 파일, `git apply` 로 붙여도 되고 손으로 고쳐도 된다. 각 파일 맨 위 import 줄 기준):
```diff
diff --git a/tests/test_calendar_feed.py b/tests/test_calendar_feed.py
index ccacdde..67e011f 100644
--- a/tests/test_calendar_feed.py
+++ b/tests/test_calendar_feed.py
@@ -12,3 +12,3 @@ from duty.errors import DutyError
 from duty.logging import RedactCalendarFeed
-from duty.models import CalendarFeed, ChangeLog, Commute, ControlDuty, Period, User
+from duty.models import Board, CalendarFeed, ChangeLog, Commute, ControlDuty, Period, User
 from duty.services import calendar
@@ -35,3 +35,4 @@ def me(env, make_member):
 def period(d=D, status=S.PUBLISHED, at=PUB_AT, end=None):
-    return Period.objects.create(name="p", start_date=d, end_date=end or d, status=status, published_at=at)
+    it_board = Board.objects.get(code="it")  # make_member·me 픽스처가 it_board 를 이미 만든다
+    return Period.objects.create(board=it_board, name="p", start_date=d, end_date=end or d, status=status, published_at=at)
 
diff --git a/tests/test_change_notice.py b/tests/test_change_notice.py
index c58b90a..bb0c834 100644
--- a/tests/test_change_notice.py
+++ b/tests/test_change_notice.py
@@ -15,3 +15,3 @@ NOW = timezone.make_aware(datetime(2026, 11, 10, 9, 0))
 @pytest.fixture
-def world(make_member, fixed_today, monkeypatch):
+def world(make_member, fixed_today, monkeypatch, it_board):
     fixed_today(D)
@@ -21,3 +21,3 @@ def world(make_member, fixed_today, monkeypatch):
     alarm_settings.ensure_push_keys()  # 푸시도 켜진 상태
-    p = Period.objects.create(name="p", start_date=D, end_date=D + timedelta(days=3), status=Period.Status.PUBLISHED)
+    p = Period.objects.create(board=it_board, name="p", start_date=D, end_date=D + timedelta(days=3), status=Period.Status.PUBLISHED)
     a, b, c = make_member("가", user=True), make_member("나", user=True), make_member("다", user=True)
diff --git a/tests/test_changes.py b/tests/test_changes.py
index a07076c..55dc28f 100644
--- a/tests/test_changes.py
+++ b/tests/test_changes.py
@@ -15,5 +15,5 @@ D = date(2026, 11, 10)
 @pytest.fixture
-def world(make_member, fixed_today):
+def world(make_member, fixed_today, it_board):
     fixed_today(D)
-    p = Period.objects.create(name="p", start_date=D, end_date=D, status=S.PUBLISHED)
+    p = Period.objects.create(board=it_board, name="p", start_date=D, end_date=D, status=S.PUBLISHED)
     m = {n: make_member(n, user=True) for n in ["가", "나", "다", "라"]}
@@ -246,3 +246,3 @@ def test_exchange_with_multi_slot_holder_is_explained(world):
 
-def test_owner_with_many_published_periods(make_member):
+def test_owner_with_many_published_periods(make_member, it_board):
     """근무 변경 때 날짜의 배포 회차를 찾는 쿼리가 회차 수에 비례해 느려지지 않는다(JOIN 곱 + DISTINCT 대신 EXISTS)."""
@@ -254,3 +254,3 @@ def test_owner_with_many_published_periods(make_member):
         d0 = date(2026, 11, 2 + i * 7)
-        p = Period.objects.create(name=f"p{i}", start_date=d0, end_date=d0, status=S.PUBLISHED)
+        p = Period.objects.create(board=it_board, name=f"p{i}", start_date=d0, end_date=d0, status=S.PUBLISHED)
         Commute.objects.create(period=p, date=d0, member=m, shift="normal")
@@ -258,3 +258,3 @@ def test_owner_with_many_published_periods(make_member):
         ps.append((p, d0))
-    only_control = Period.objects.create(name="c", start_date=date(2026, 12, 1), end_date=date(2026, 12, 1),
+    only_control = Period.objects.create(board=it_board, name="c", start_date=date(2026, 12, 1), end_date=date(2026, 12, 1),
                                          status=S.PUBLISHED)
diff --git a/tests/test_collect.py b/tests/test_collect.py
index e14e870..073c2b0 100644
--- a/tests/test_collect.py
+++ b/tests/test_collect.py
@@ -15,5 +15,5 @@ CSV = 'date,새벽,정상,석식교대,야간\n2026-11-09,가,"나,다",,\n'
 @pytest.fixture
-def setup(depts, make_member, fixed_today):
+def setup(depts, make_member, fixed_today, it_board):
     fixed_today(date(2026, 11, 1))
-    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13), status=S.COLLECTING)
+    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13), status=S.COLLECTING)
     mgr = make_member("담당", user=True)
diff --git a/tests/test_db_constraints.py b/tests/test_db_constraints.py
index d1fea66..0373d6a 100644
--- a/tests/test_db_constraints.py
+++ b/tests/test_db_constraints.py
@@ -13,4 +13,4 @@ D = date(2026, 11, 9)
 @pytest.fixture
-def period(db):
-    return Period.objects.create(name="p", start_date=D, end_date=date(2026, 11, 13))
+def period(it_board):
+    return Period.objects.create(board=it_board, name="p", start_date=D, end_date=date(2026, 11, 13))
 
@@ -26,6 +26,6 @@ def test_member_type(depts):
 
-def test_period_status_and_dates(db):
-    _bad(lambda: Period.objects.create(name="p", start_date=D, end_date=D, status="bogus"))
-    _bad(lambda: Period.objects.create(name="p", start_date=D, end_date=date(2026, 11, 1)))
-    Period.objects.create(name="ok", start_date=D, end_date=D)  # 하루짜리 회차는 허용
+def test_period_status_and_dates(it_board):
+    _bad(lambda: Period.objects.create(board=it_board, name="p", start_date=D, end_date=D, status="bogus"))
+    _bad(lambda: Period.objects.create(board=it_board, name="p", start_date=D, end_date=date(2026, 11, 1)))
+    Period.objects.create(board=it_board, name="ok", start_date=D, end_date=D)  # 하루짜리 회차는 허용
 
diff --git a/tests/test_generate.py b/tests/test_generate.py
index b93ab82..4380d72 100644
--- a/tests/test_generate.py
+++ b/tests/test_generate.py
@@ -13,4 +13,4 @@ S = Period.Status
 @pytest.fixture
-def closed_period(make_member):
-    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13), status=S.CLOSED)
+def closed_period(make_member, it_board):
+    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13), status=S.CLOSED)
     normal = [make_member(f"N{i}", dept="MEMS") for i in range(7)]
diff --git a/tests/test_models.py b/tests/test_models.py
index 4dcde52..5c5dd75 100644
--- a/tests/test_models.py
+++ b/tests/test_models.py
@@ -17,4 +17,4 @@ def test_period_dates_are_weekdays():
 
-def test_period_default_status_is_draft(db):
-    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
+def test_period_default_status_is_draft(it_board):
+    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
     assert p.status == Period.Status.DRAFT
@@ -22,4 +22,4 @@ def test_period_default_status_is_draft(db):
 
-def test_one_commute_per_member_per_day(make_member):
-    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
+def test_one_commute_per_member_per_day(make_member, it_board):
+    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
     m = make_member("가")
@@ -30,4 +30,4 @@ def test_one_commute_per_member_per_day(make_member):
 
-def test_one_member_per_duty_slot(make_member):
-    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
+def test_one_member_per_duty_slot(make_member, it_board):
+    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
     a, b = make_member("가"), make_member("나")
@@ -38,4 +38,4 @@ def test_one_member_per_duty_slot(make_member):
 
-def test_member_may_hold_several_duty_slots_per_day(make_member):
-    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
+def test_member_may_hold_several_duty_slots_per_day(make_member, it_board):
+    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
     a = make_member("가")
diff --git a/tests/test_period_lifecycle.py b/tests/test_period_lifecycle.py
index 20a982b..0805376 100644
--- a/tests/test_period_lifecycle.py
+++ b/tests/test_period_lifecycle.py
@@ -5,3 +5,3 @@ import pytest
 from duty.errors import DutyError
-from duty.models import ChangeLog, Commute, ControlDuty, Period, PeriodEvent
+from duty.models import Board, ChangeLog, Commute, ControlDuty, Period, PeriodEvent
 from duty.services import periods
@@ -19,3 +19,4 @@ def d(m, day):
 def make_period(name, start, end, status, member):
-    p = Period.objects.create(name=name, start_date=start, end_date=end, status=status)
+    it_board = Board.objects.get(code="it")
+    p = Period.objects.create(board=it_board, name=name, start_date=start, end_date=end, status=status)
     for x in weekdays(start, end):
@@ -48,4 +49,4 @@ def test_move_from_generated_drops_control_duty_and_logs(make_member, admin_user
 
-def test_move_draft_to_closed_directly(db):
-    p = Period.objects.create(name="p", start_date=d(11, 9), end_date=d(11, 13))
+def test_move_draft_to_closed_directly(it_board):
+    p = Period.objects.create(board=it_board, name="p", start_date=d(11, 9), end_date=d(11, 13))
     periods.move(p, S.CLOSED)
@@ -55,4 +56,4 @@ def test_move_draft_to_closed_directly(db):
 @pytest.mark.parametrize("to", [S.GENERATED, S.PUBLISHED, "bogus"])
-def test_move_rejects_targets_with_own_action(db, to):
-    p = Period.objects.create(name="p", start_date=d(11, 9), end_date=d(11, 13), status=S.CLOSED)
+def test_move_rejects_targets_with_own_action(it_board, to):
+    p = Period.objects.create(board=it_board, name="p", start_date=d(11, 9), end_date=d(11, 13), status=S.CLOSED)
     with pytest.raises(DutyError):
@@ -61,4 +62,4 @@ def test_move_rejects_targets_with_own_action(db, to):
 
-def test_move_rejects_same_status_and_published(db):
-    p = Period.objects.create(name="p", start_date=d(11, 9), end_date=d(11, 13), status=S.CLOSED)
+def test_move_rejects_same_status_and_published(it_board):
+    p = Period.objects.create(board=it_board, name="p", start_date=d(11, 9), end_date=d(11, 13), status=S.CLOSED)
     with pytest.raises(DutyError):
@@ -80,4 +81,4 @@ def test_draft_shrink_drops_commutes_outside(make_member):
 
-def test_create_and_generate_and_publish_are_logged(make_member, admin_user):
-    p = periods.save_draft(Period(name="p", start_date=d(11, 9), end_date=d(11, 13)), by=admin_user)
+def test_create_and_generate_and_publish_are_logged(make_member, admin_user, it_board):
+    p = periods.save_draft(Period(board=it_board, name="p", start_date=d(11, 9), end_date=d(11, 13)), by=admin_user)
     assert list(PeriodEvent.objects.values_list("from_status", "to_status")) == [("", S.DRAFT)]
@@ -145,4 +146,4 @@ def test_unpublish_keeps_edits_and_counts_them(abc, admin_user):
 
-def test_unpublish_without_snapshot_refused(db):
-    p = Period.objects.create(name="old", start_date=d(11, 9), end_date=d(11, 13), status=S.PUBLISHED)
+def test_unpublish_without_snapshot_refused(it_board):
+    p = Period.objects.create(board=it_board, name="old", start_date=d(11, 9), end_date=d(11, 13), status=S.PUBLISHED)
     assert unpublish_info(p).blocker
@@ -176,6 +177,6 @@ def test_stale_period_objects_are_rechecked(abc, admin_user):
 
-def test_stale_collect_rejected(make_member, admin_user):
+def test_stale_collect_rejected(make_member, admin_user, it_board):
     from duty.services import collect
     m = make_member("가")
-    p = Period.objects.create(name="p", start_date=d(11, 9), end_date=d(11, 9), status=S.COLLECTING)
+    p = Period.objects.create(board=it_board, name="p", start_date=d(11, 9), end_date=d(11, 9), status=S.COLLECTING)
     stale = Period.objects.get(pk=p.pk)
@@ -211,5 +212,5 @@ def test_changes_before_unpublish_not_replayed(abc, admin_user):
 
-def test_period_with_events_cannot_be_deleted(db):
+def test_period_with_events_cannot_be_deleted(it_board):
     from django.db.models import ProtectedError
-    p = periods.save_draft(Period(name="p", start_date=d(11, 9), end_date=d(11, 13)))
+    p = periods.save_draft(Period(board=it_board, name="p", start_date=d(11, 9), end_date=d(11, 13)))
     with pytest.raises(ProtectedError):
diff --git a/tests/test_periods.py b/tests/test_periods.py
index 773aba0..e35626e 100644
--- a/tests/test_periods.py
+++ b/tests/test_periods.py
@@ -15,11 +15,11 @@ def d(m, day):
 
-def test_unpublished_periods_cannot_overlap(db):
-    periods.save_draft(Period(name="a", start_date=d(11, 9), end_date=d(11, 30)))
+def test_unpublished_periods_cannot_overlap(it_board):
+    periods.save_draft(Period(board=it_board, name="a", start_date=d(11, 9), end_date=d(11, 30)))
     with pytest.raises(DutyError):
-        periods.save_draft(Period(name="b", start_date=d(11, 20), end_date=d(12, 31)))
+        periods.save_draft(Period(board=it_board, name="b", start_date=d(11, 20), end_date=d(12, 31)))
 
 
-def test_overlap_with_published_is_allowed(db):
-    Period.objects.create(name="a", start_date=d(11, 2), end_date=d(11, 30), status=S.PUBLISHED)
-    p = periods.save_draft(Period(name="b", start_date=d(11, 16), end_date=d(12, 31)))
+def test_overlap_with_published_is_allowed(it_board):
+    Period.objects.create(board=it_board, name="a", start_date=d(11, 2), end_date=d(11, 30), status=S.PUBLISHED)
+    p = periods.save_draft(Period(board=it_board, name="b", start_date=d(11, 16), end_date=d(12, 31)))
     assert p.pk
@@ -27,14 +27,14 @@ def test_overlap_with_published_is_allowed(db):
 
-def test_start_after_end_rejected(db):
+def test_start_after_end_rejected(it_board):
     with pytest.raises(DutyError):
-        periods.save_draft(Period(name="a", start_date=d(11, 30), end_date=d(11, 9)))
+        periods.save_draft(Period(board=it_board, name="a", start_date=d(11, 30), end_date=d(11, 9)))
 
 
-def test_weekend_only_period_rejected(db):
+def test_weekend_only_period_rejected(it_board):
     with pytest.raises(DutyError):
-        periods.save_draft(Period(name="a", start_date=d(11, 14), end_date=d(11, 15)))
+        periods.save_draft(Period(board=it_board, name="a", start_date=d(11, 14), end_date=d(11, 15)))
 
 
-def test_dates_editable_only_in_draft(db):
-    p = Period.objects.create(name="a", start_date=d(11, 9), end_date=d(11, 30), status=S.COLLECTING)
+def test_dates_editable_only_in_draft(it_board):
+    p = Period.objects.create(board=it_board, name="a", start_date=d(11, 9), end_date=d(11, 30), status=S.COLLECTING)
     p.end_date = d(12, 4)
@@ -44,4 +44,4 @@ def test_dates_editable_only_in_draft(db):
 
-def test_open_close_and_reopen_deletes_duties(make_member):
-    p = Period.objects.create(name="a", start_date=d(11, 9), end_date=d(11, 13))
+def test_open_close_and_reopen_deletes_duties(make_member, it_board):
+    p = Period.objects.create(board=it_board, name="a", start_date=d(11, 9), end_date=d(11, 13))
     periods.move(p, S.COLLECTING)
@@ -58,4 +58,4 @@ def test_open_close_and_reopen_deletes_duties(make_member):
 
-def test_open_rejected_when_published(db):
-    p = Period.objects.create(name="a", start_date=d(11, 9), end_date=d(11, 13), status=S.PUBLISHED)
+def test_open_rejected_when_published(it_board):
+    p = Period.objects.create(board=it_board, name="a", start_date=d(11, 9), end_date=d(11, 13), status=S.PUBLISHED)
     with pytest.raises(DutyError):
@@ -64,4 +64,4 @@ def test_open_rejected_when_published(db):
 
-def test_missing_dates(make_member):
-    p = Period.objects.create(name="a", start_date=d(11, 9), end_date=d(11, 10))
+def test_missing_dates(make_member, it_board):
+    p = Period.objects.create(board=it_board, name="a", start_date=d(11, 9), end_date=d(11, 10))
     Commute.objects.create(period=p, date=d(11, 9), member=make_member("가", dept="MEMS"), shift="normal")
diff --git a/tests/test_publish.py b/tests/test_publish.py
index 4ecc146..aec0c5d 100644
--- a/tests/test_publish.py
+++ b/tests/test_publish.py
@@ -5,3 +5,3 @@ import pytest
 from duty.errors import DutyError
-from duty.models import ChangeLog, Commute, ControlDuty, Period
+from duty.models import Board, ChangeLog, Commute, ControlDuty, Period
 from duty.services.publish import preview_publish, publish
@@ -17,3 +17,4 @@ def d(m, day):
 def make_period(name, start, end, status, member):
-    p = Period.objects.create(name=name, start_date=start, end_date=end, status=status)
+    it_board = Board.objects.get(code="it")  # make_member·me 픽스처가 it_board 를 이미 만든다
+    p = Period.objects.create(board=it_board, name=name, start_date=start, end_date=end, status=status)
     for x in weekdays(start, end):
diff --git a/tests/test_roster.py b/tests/test_roster.py
index d98c19a..1ccc031 100644
--- a/tests/test_roster.py
+++ b/tests/test_roster.py
@@ -2,3 +2,3 @@ from datetime import date
 
-from duty.models import ChangeLog, Commute, ControlDuty, Period
+from duty.models import Board, ChangeLog, Commute, ControlDuty, Period
 from duty.services.roster import chain, member_schedule, published_days
@@ -20,3 +20,4 @@ def test_chain_add_and_remove():
 def make_published(make_member):
-    p = Period.objects.create(name="p", start_date=D, end_date=D, status=S.PUBLISHED)
+    it_board = Board.objects.get(code="it")  # make_member·me 픽스처가 it_board 를 이미 만든다
+    p = Period.objects.create(board=it_board, name="p", start_date=D, end_date=D, status=S.PUBLISHED)
     staff = make_member("직원1", type="직원")
diff --git a/tests/test_roster_prefs.py b/tests/test_roster_prefs.py
index 3f7b266..3a591f1 100644
--- a/tests/test_roster_prefs.py
+++ b/tests/test_roster_prefs.py
@@ -10,5 +10,5 @@ D = date(2026, 11, 10)
 @pytest.fixture
-def world(make_member, fixed_today):
+def world(make_member, fixed_today, it_board):
     fixed_today(D)
-    p = Period.objects.create(name="p", start_date=D, end_date=D, status=Period.Status.PUBLISHED)
+    p = Period.objects.create(board=it_board, name="p", start_date=D, end_date=D, status=Period.Status.PUBLISHED)
     a, b = make_member("가", user=True), make_member("나", user=True)
diff --git a/tests/test_run_alarms.py b/tests/test_run_alarms.py
index 938ed20..44bd359 100644
--- a/tests/test_run_alarms.py
+++ b/tests/test_run_alarms.py
@@ -85,5 +85,5 @@ def issued(make_member, name):
 @pytest.fixture
-def member(make_member, env):
+def member(make_member, env, it_board):
     m = issued(make_member, NAME)
-    p = Period.objects.create(name="p", start_date=D, end_date=D, status=Period.Status.PUBLISHED)
+    p = Period.objects.create(board=it_board, name="p", start_date=D, end_date=D, status=Period.Status.PUBLISHED)
     Commute.objects.create(period=p, date=D, member=m, shift="dawn")
diff --git a/tests/test_stats.py b/tests/test_stats.py
index 9d49988..8c39a78 100644
--- a/tests/test_stats.py
+++ b/tests/test_stats.py
@@ -2,3 +2,3 @@ from datetime import date
 
-from duty.models import Commute, ControlDuty, Period
+from duty.models import Board, Commute, ControlDuty, Period
 from duty.services.stats import member_stats, period_duty_counts
@@ -10,3 +10,4 @@ D1, D2 = date(2026, 11, 9), date(2026, 11, 10)
 def setup_period(make_member, status=S.PUBLISHED):
-    p = Period.objects.create(name="p", start_date=D1, end_date=D2, status=status)
+    it_board = Board.objects.get(code="it")  # make_member·me 픽스처가 it_board 를 이미 만든다
+    p = Period.objects.create(board=it_board, name="p", start_date=D1, end_date=D2, status=status)
     a, b = make_member("가"), make_member("나")
diff --git a/tests/test_views_collect.py b/tests/test_views_collect.py
index 65bece1..6c4b359 100644
--- a/tests/test_views_collect.py
+++ b/tests/test_views_collect.py
@@ -9,5 +9,5 @@ from duty.models import Commute, Period
 @pytest.fixture
-def ctx(depts, make_member, fixed_today):
+def ctx(depts, make_member, fixed_today, it_board):
     fixed_today(date(2026, 11, 1))
-    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 10), status=Period.Status.COLLECTING)
+    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 10), status=Period.Status.COLLECTING)
     mgr = make_member("담당", user=True)
diff --git a/tests/test_views_manage.py b/tests/test_views_manage.py
index a8e179c..1954848 100644
--- a/tests/test_views_manage.py
+++ b/tests/test_views_manage.py
@@ -4,3 +4,3 @@ import pytest
 
-from duty.models import ChangeLog, Commute, Period, User
+from duty.models import Board, ChangeLog, Commute, Period, User
 
@@ -25,6 +25,6 @@ def test_create_period(admin_client_ok):
 
-def test_full_flow(admin_client_ok, make_member, fixed_today):
+def test_full_flow(admin_client_ok, make_member, fixed_today, it_board):
     fixed_today(date(2026, 11, 1))
     c = admin_client_ok
-    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 10))
+    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 10))
     c.post(f"/periods/{p.pk}/action/open/")
@@ -44,4 +44,4 @@ def test_full_flow(admin_client_ok, make_member, fixed_today):
 
-def test_generation_failure_is_shown(admin_client_ok, make_member):
-    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 9), status=Period.Status.CLOSED)
+def test_generation_failure_is_shown(admin_client_ok, make_member, it_board):
+    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 9), status=Period.Status.CLOSED)
     for code in ["MEMS", "TMCH", "MD", "UI"]:
@@ -52,4 +52,4 @@ def test_generation_failure_is_shown(admin_client_ok, make_member):
 
-def test_stats_and_changes_pages(admin_client_ok, make_member):
-    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 9), status=Period.Status.PUBLISHED)
+def test_stats_and_changes_pages(admin_client_ok, make_member, it_board):
+    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 9), status=Period.Status.PUBLISHED)
     m = make_member("가")
@@ -67,4 +67,4 @@ def test_anonymous_redirected_to_login(client, url):
 
-def test_action_get_is_405(admin_client_ok):
-    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 9))
+def test_action_get_is_405(admin_client_ok, it_board):
+    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 9))
     assert admin_client_ok.get(f"/periods/{p.pk}/action/open/").status_code == 405
@@ -73,3 +73,4 @@ def test_action_get_is_405(admin_client_ok):
 def _generated(make_member, start=date(2026, 11, 9), end=date(2026, 11, 11)):
-    old = Period.objects.create(name="옛회차", start_date=date(2026, 11, 2), end_date=date(2026, 11, 10), status=Period.Status.PUBLISHED)
+    it_board = Board.objects.get(code="it")
+    old = Period.objects.create(board=it_board, name="옛회차", start_date=date(2026, 11, 2), end_date=date(2026, 11, 10), status=Period.Status.PUBLISHED)
     m = make_member("가")
@@ -77,3 +78,3 @@ def _generated(make_member, start=date(2026, 11, 9), end=date(2026, 11, 11)):
     ChangeLog.objects.create(period=old, date=date(2026, 11, 10), cell="dawn", before=None, after=m)
-    new = Period.objects.create(name="새회차", start_date=start, end_date=end, status=Period.Status.GENERATED)
+    new = Period.objects.create(board=it_board, name="새회차", start_date=start, end_date=end, status=Period.Status.GENERATED)
     return old, new
@@ -111,4 +112,4 @@ def test_publish_post_past_start_inside_period_ok(admin_client_ok, make_member,
 
-def test_change_log_filters(admin_client_ok, make_member):
-    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 10), status=Period.Status.PUBLISHED)
+def test_change_log_filters(admin_client_ok, make_member, it_board):
+    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 10), status=Period.Status.PUBLISHED)
     a, b = make_member("가", user=True), make_member("나")
@@ -147,4 +148,4 @@ def test_admin_nav_link_superuser_only(client, admin_user, make_member):
 
-def test_generate_has_detail_dialog(admin_client_ok):
-    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13),
+def test_generate_has_detail_dialog(admin_client_ok, it_board):
+    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13),
                               status=Period.Status.CLOSED)
@@ -155,6 +156,6 @@ def test_generate_has_detail_dialog(admin_client_ok):
 
-def test_lifecycle_move_and_unpublish_views(admin_client_ok, make_member):
+def test_lifecycle_move_and_unpublish_views(admin_client_ok, make_member, it_board):
     from duty.models import ControlDuty, PeriodEvent
     m = make_member("가")
-    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13), status=Period.Status.GENERATED)
+    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13), status=Period.Status.GENERATED)
     for x in p.dates():
@@ -180,3 +181,3 @@ def test_lifecycle_move_and_unpublish_views(admin_client_ok, make_member):
 
-def test_period_delete_view(admin_client_ok, make_member):
+def test_period_delete_view(admin_client_ok, make_member, it_board):
     from django.test import Client
@@ -184,3 +185,3 @@ def test_period_delete_view(admin_client_ok, make_member):
     member.force_login(make_member("가", user=True))
-    p = Period.objects.create(name="시험", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
+    p = Period.objects.create(board=it_board, name="시험", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
     assert "회차 삭제" in admin_client_ok.get(f"/periods/{p.pk}/").content.decode()
@@ -192,5 +193,5 @@ def test_period_delete_view(admin_client_ok, make_member):
 
-def test_period_detail_with_event_without_user(admin_client_ok):
+def test_period_detail_with_event_without_user(admin_client_ok, it_board):
     from duty.services import periods
-    p = periods.save_draft(Period(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13)))  # by 없음
+    p = periods.save_draft(Period(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13)))  # by 없음
     assert admin_client_ok.get(f"/periods/{p.pk}/").status_code == 200
diff --git a/tests/test_views_roster.py b/tests/test_views_roster.py
index 5b4b33b..2f3cf24 100644
--- a/tests/test_views_roster.py
+++ b/tests/test_views_roster.py
@@ -11,5 +11,5 @@ D = date(2026, 11, 10)
 @pytest.fixture
-def world(make_member, fixed_today):
+def world(make_member, fixed_today, it_board):
     fixed_today(D)
-    p = Period.objects.create(name="p", start_date=D, end_date=D, status=Period.Status.PUBLISHED)
+    p = Period.objects.create(board=it_board, name="p", start_date=D, end_date=D, status=Period.Status.PUBLISHED)
     a, b = make_member("가", user=True), make_member("나", user=True)
```

Run: `.venv/bin/pytest -W error -q`
Expected: `788 passed`(기존 775 + 새 13), 경고 0개.

- [ ] **Step 9: 마이그레이션 테스트를 먼저 쓴다**

`tests/test_migration_boards.py`(새 파일, 이름은 모두 가상):
```python
"""1단계 마이그레이션(0010 스키마 + 0011 데이터)을 0009 상태의 가짜 데이터로 올리고 되돌린다."""
from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0009_roster_history")]
AFTER = [("duty", "0011_boards_data")]


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()  # 앞선 migrate 로 바뀐 적용 기록을 다시 읽는다
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_apps():
    apps = _migrate(BEFORE)
    yield apps
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())  # 다른 테스트를 위해 최신 스키마로


def _seed(apps):
    Department = apps.get_model("duty", "Department")
    User = apps.get_model("duty", "User")
    Period = apps.get_model("duty", "Period")
    AlarmRule = apps.get_model("duty", "AlarmRule")
    mems = Department.objects.create(code="MEMS", name="가부서", shifts="dawn,normal,dinner,night")
    ui = Department.objects.create(code="UI", name="나부서", shifts="normal,dinner,night")
    extra = Department.objects.create(code="ZZ", name="다부서", shifts="normal")
    mgr = User.objects.create(username="MEMS001", name="담당가", department=mems, type="개발자")
    staff = User.objects.create(username="adm", name="관리가", is_staff=True)
    su = User.objects.create(username="root", name="최고가", is_staff=True, is_superuser=True)
    mems.managers.add(mgr)
    pub = Period.objects.create(name="배포", start_date=date(2026, 11, 2), end_date=date(2026, 11, 13), status="published")
    pub_s = Period.objects.create(name="배포S", start_date=date(2026, 11, 16), end_date=date(2026, 11, 27),
                                  status="published", overwrite_from=date(2026, 11, 18))
    draft = Period.objects.create(name="작성", start_date=date(2026, 11, 30), end_date=date(2026, 12, 11))
    rep = AlarmRule.objects.create(user=staff, kind="report", timing="days", offset=1, at_minute=600, telegram=True,
                                   depts=["MEMS"])
    per = AlarmRule.objects.create(user=mgr, kind="personal", timing="days", offset=1, at_minute=600, telegram=True)
    return dict(mems=mems.pk, ui=ui.pk, extra=extra.pk, mgr=mgr.pk, staff=staff.pk, su=su.pk,
                pub=pub.pk, pub_s=pub_s.pk, draft=draft.pk, rep=rep.pk, per=per.pk)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_forward_builds_it_board_and_groups(old_apps):
    ids = _seed(old_apps)
    apps = _migrate(AFTER)
    Board = apps.get_model("duty", "Board")
    Department = apps.get_model("duty", "Department")
    Period = apps.get_model("duty", "Period")
    AlarmRule = apps.get_model("duty", "AlarmRule")
    GroupKeeper = apps.get_model("duty", "GroupKeeper")
    Group = apps.get_model("auth", "Group")

    it = Board.objects.get(code="it")
    assert (it.name, it.input_mode, it.admin_group.name) == ("IT 당번표", "collect", "IT 근무표 관리")
    rows = {s.key: s for s in it.shifts.all()}
    assert len(rows) == 14
    assert (rows["dawn"].name, str(rows["dawn"].start), str(rows["dawn"].end)) == ("새벽", "06:30:00", "15:30:00")
    assert (rows["slot0"].name, rows["slot0"].eligible_shifts, rows["slot0"].eligible_types) == ("08:30~09:30", ["normal"], ["개발자"])
    assert rows["slot9"].eligible_shifts == ["dinner"] and rows["slot4"].eligible_shifts == ["normal", "dinner"]
    assert {k for k, s in rows.items() if s.default_alarm} == {"dawn", "dinner", "night"}

    depts = {d.code: d for d in Department.objects.all()}
    assert {d.board_id for d in depts.values()} == {it.id}
    assert (depts["MEMS"].order, depts["UI"].order, depts["ZZ"].order) == (0, 3, 99)
    assert depts["MEMS"].input_group.name == "가부서 출근표 입력"
    assert list(depts["MEMS"].input_group.user_set.values_list("pk", flat=True)) == [ids["mgr"]]
    assert not depts["UI"].input_group.user_set.exists()

    assert set(it.admin_group.user_set.values_list("pk", flat=True)) == {ids["staff"], ids["su"]}
    created = {it.admin_group_id, *(d.input_group_id for d in depts.values())}
    assert set(GroupKeeper.objects.values_list("group_id", flat=True)) == created
    assert set(GroupKeeper.objects.values_list("user_id", flat=True)) == {ids["su"]}
    assert Group.objects.count() == 4

    periods = {p.pk: p for p in Period.objects.all()}
    assert {p.board_id for p in periods.values()} == {it.id}
    assert periods[ids["pub"]].overwrite_from == date(2026, 11, 2)
    assert periods[ids["pub_s"]].overwrite_from == date(2026, 11, 18)
    assert periods[ids["draft"]].overwrite_from is None
    assert AlarmRule.objects.get(pk=ids["rep"]).board_id == it.id
    assert AlarmRule.objects.get(pk=ids["rep"]).depts == ["MEMS"]
    assert AlarmRule.objects.get(pk=ids["per"]).board_id is None


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_backward_restores_managers_and_removes_boards(old_apps):
    ids = _seed(old_apps)
    _migrate(AFTER)
    apps = _migrate(BEFORE)
    Department = apps.get_model("duty", "Department")
    Group = apps.get_model("auth", "Group")
    mems = Department.objects.get(pk=ids["mems"])
    assert list(mems.managers.values_list("pk", flat=True)) == [ids["mgr"]]
    assert not Department.objects.get(pk=ids["ui"]).managers.exists()
    assert not Group.objects.exists()


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_forward_stops_on_group_name_clash(old_apps):
    _seed(old_apps)
    clash = old_apps.get_model("auth", "Group").objects.create(name="가부서 출근표 입력")
    with pytest.raises(RuntimeError, match="가부서 출근표 입력"):
        _migrate(AFTER)
    clash.delete()  # 뒷정리(최신으로 올리기)가 같은 이유로 멈추지 않게
```

- [ ] **Step 10: 실패를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_migration_boards.py -q`
Expected: `3 failed`. 세 테스트 모두 `_migrate(AFTER)` 에서 `django.db.migrations.exceptions.NodeNotFoundError: Node ('duty', '0011_boards_data') not a valid node`. 세 번째 테스트는 이 오류가 `RuntimeError` 가 아니라 `pytest.raises` 를 빠져나가 실패한다.

- [ ] **Step 11: 데이터 마이그레이션 `0011_boards_data`를 쓴다**

`duty/migrations/0011_boards_data.py`(새 파일):
```python
"""1단계 데이터 이전: 기존 데이터를 IT 근무표 하나로 묶고, 권한을 그룹으로 옮긴다.

앱 코드(shifts.py 등)를 import 하지 않는다: 앱 상수가 나중에 바뀌어도 이 마이그레이션의 결과는 같아야 한다.
"""
from datetime import time

from django.db import migrations

IT_CODE = "it"
IT_NAME = "IT 당번표"
IT_ADMIN_GROUP = "IT 근무표 관리"
DEPT_ORDER = ["MEMS", "TMCH", "MD", "UI"]  # 지금 근무표 부서 필터 순서(views/roster.py DEPT_ORDER). 없는 부서는 뒤로
_BOTH = ["normal", "dinner"]
_DEV = ["개발자"]
IT_SHIFTS = [  # 1단계 시점 shifts.py 상수 그대로(키, 이름, 시작, 끝, 자격 근무조, 자격 구분, 기본 알림)
    ("dawn", "새벽", time(6, 30), time(15, 30), [], [], True),
    ("normal", "정상", time(8, 0), time(17, 0), [], [], False),
    ("dinner", "석식교대", time(9, 0), time(18, 0), [], [], True),
    ("slot0", "08:30~09:30", time(8, 30), time(9, 30), ["normal"], _DEV, False),
    ("slot1", "09:30~10:30", time(9, 30), time(10, 30), _BOTH, _DEV, False),
    ("slot2", "10:30~11:30", time(10, 30), time(11, 30), _BOTH, _DEV, False),
    ("slot3", "11:30~12:30", time(11, 30), time(12, 30), _BOTH, _DEV, False),
    ("slot4", "12:30~13:30", time(12, 30), time(13, 30), _BOTH, _DEV, False),
    ("slot5", "13:30~14:30", time(13, 30), time(14, 30), _BOTH, _DEV, False),
    ("slot6", "14:30~15:30", time(14, 30), time(15, 30), _BOTH, _DEV, False),
    ("slot7", "15:30~16:30", time(15, 30), time(16, 30), _BOTH, _DEV, False),
    ("slot8", "16:30~17:00", time(16, 30), time(17, 0), _BOTH, _DEV, False),
    ("slot9", "17:00~18:00", time(17, 0), time(18, 0), ["dinner"], _DEV, False),
    ("night", "야간", time(13, 30), time(21, 30), [], [], True),
]


def _input_group_name(dept) -> str:
    return f"{dept.name} 출근표 입력"


def forward(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Board = apps.get_model("duty", "Board")
    BoardShift = apps.get_model("duty", "BoardShift")
    GroupKeeper = apps.get_model("duty", "GroupKeeper")
    Department = apps.get_model("duty", "Department")
    Period = apps.get_model("duty", "Period")
    User = apps.get_model("duty", "User")
    AlarmRule = apps.get_model("duty", "AlarmRule")

    depts = list(Department.objects.all())
    # 같은 이름의 그룹이 이미 있으면 뜻이 섞이므로 멈춘다(운영자가 그 그룹 이름을 바꾼 뒤 다시 올린다)
    taken = sorted(Group.objects.filter(name__in=[IT_ADMIN_GROUP, *map(_input_group_name, depts)])
                   .values_list("name", flat=True))
    if taken:
        raise RuntimeError(f"이미 있는 그룹 이름이라 멈춥니다: {', '.join(taken)}. 업그레이드 전 백업으로 롤백한 뒤(docs/OPERATIONS.md \"업그레이드·롤백\") 옛 버전 관리 화면에서 그 그룹 이름을 바꾸고 업그레이드를 다시 하세요.")

    admin_group = Group.objects.create(name=IT_ADMIN_GROUP)
    board = Board.objects.create(code=IT_CODE, name=IT_NAME, input_mode="collect", admin_group=admin_group)
    BoardShift.objects.bulk_create([
        BoardShift(board=board, key=k, name=n, start=s, end=e, eligible_shifts=es, eligible_types=et, default_alarm=da)
        for k, n, s, e, es, et, da in IT_SHIFTS])
    admin_group.user_set.set(User.objects.filter(is_staff=True))  # is_staff 값 자체는 그대로 둔다

    groups = [admin_group]
    for dept in depts:
        group = Group.objects.create(name=_input_group_name(dept))
        group.user_set.set(dept.managers.all())
        dept.board, dept.input_group = board, group
        dept.order = DEPT_ORDER.index(dept.code) if dept.code in DEPT_ORDER else 99
        dept.save(update_fields=["board", "input_group", "order"])
        groups.append(group)

    GroupKeeper.objects.bulk_create([GroupKeeper(group=g, user=u)
                                     for u in User.objects.filter(is_superuser=True) for g in groups])
    Period.objects.update(board=board)
    for p in Period.objects.filter(status="published", overwrite_from__isnull=True):
        p.overwrite_from = p.start_date
        p.save(update_fields=["overwrite_from"])
    AlarmRule.objects.filter(kind="report").update(board=board)  # depts 는 다시 정규화하지 않는다


def backward(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Board = apps.get_model("duty", "Board")
    BoardShift = apps.get_model("duty", "BoardShift")
    GroupKeeper = apps.get_model("duty", "GroupKeeper")
    Department = apps.get_model("duty", "Department")
    Period = apps.get_model("duty", "Period")
    AlarmRule = apps.get_model("duty", "AlarmRule")
    RosterPref = apps.get_model("duty", "RosterPref")

    created = list(Board.objects.values_list("admin_group_id", flat=True))
    for dept in Department.objects.exclude(input_group=None).select_related("input_group"):
        dept.managers.set(dept.input_group.user_set.all())
        created.append(dept.input_group_id)
    # 채운 overwrite_from 은 되돌리지 않는다(배포 회차의 start_date 와 같아 뜻이 같다)
    Department.objects.update(board=None, input_group=None, order=99)
    Period.objects.update(board=None)
    AlarmRule.objects.update(board=None)
    RosterPref.objects.update(board=None)
    GroupKeeper.objects.all().delete()
    BoardShift.objects.all().delete()
    # Board 는 역참조가 많아 delete() 의 연쇄 검사가 되돌리는 중의 옛 모델 상태와 어긋난다(참조는 위에서 다 비웠다)
    Board.objects.all()._raw_delete(schema_editor.connection.alias)
    Group.objects.filter(id__in=created).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("duty", "0010_boards"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
```
`_raw_delete` 를 쓰는 이유: 0011 과 0010 을 한꺼번에 되돌릴 때 `Board.objects.all().delete()` 는 `ValueError: Cannot query "Board object (1)": Must be "Board" instance.` 로 멈춘다. Board 를 가리키는 참조는 바로 위에서 모두 비우므로 연쇄 검사 없이 지워도 안전하다.

- [ ] **Step 12: 마이그레이션 테스트 통과를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_migration_boards.py tests/test_boards_models.py -q`
Expected: `15 passed`

- [ ] **Step 13: 모델과 마이그레이션이 맞는지 확인한다**

Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --check --dry-run`
Expected: `No changes detected in app 'duty'`

- [ ] **Step 14: 전체 테스트를 돌린다**

Run: `.venv/bin/pytest -W error -q`
Expected: `791 passed`(788 + 마이그레이션 테스트 3), 경고 0개. `depts[...].managers.add(...)` 를 쓰는 기존 테스트(test_admin_department·test_admin_users·test_collect·test_perms·test_views_collect·test_help)는 M2M 이 아직 남아 있어 그대로 돈다.

- [ ] **Step 15: 커밋한다**

```bash
git add duty/shifts.py duty/models.py duty/migrations/0010_boards.py duty/migrations/0011_boards_data.py \
        tests/it_defs.py tests/conftest.py tests/test_boards_models.py tests/test_migration_boards.py \
        tests/test_calendar_feed.py tests/test_change_notice.py tests/test_changes.py tests/test_collect.py \
        tests/test_db_constraints.py tests/test_generate.py tests/test_models.py tests/test_period_lifecycle.py \
        tests/test_periods.py tests/test_publish.py tests/test_roster.py tests/test_roster_prefs.py \
        tests/test_run_alarms.py tests/test_stats.py tests/test_views_collect.py tests/test_views_manage.py \
        tests/test_views_roster.py
git commit -m "feat: 근무표·근무 정의·그룹 모델과 IT 근무표 데이터 이전 마이그레이션(추가만)"
```
(커밋 메시지 끝에 세션의 Co-Authored-By·Claude-Session 줄을 붙인다.)

**뒤 작업이 알아야 할 점**
- 다음 마이그레이션 번호는 `0012`다(Task 2: `0012_dutyassignment`, `0013_controlduty_to_assignment`, `0014_delete_controlduty`). managers M2M 을 지우는 마이그레이션(Task 4)은 0011 뒤에 와야 한다. 되돌릴 때 M2M 이 먼저 다시 생기고 그다음 0011 backward 가 managers 를 채운다.
- `Board.save` 가 자동으로 만드는 그룹 이름은 `"{name} 근무표 관리"`(지적 13: 관리 화면도 이 규칙만 쓴다, 따로 그룹을 만들지 않는다). flush 뒤 픽스처가 새로 만든 IT 근무표의 그룹 이름은 "IT 당번표 근무표 관리"라 마이그레이션의 "IT 근무표 관리"와 다를 수 있다. 그룹 이름에 기대는 테스트는 쓰지 않는다.
- `Department.save` 는 collect 근무표의 부서에만 입력 그룹을 만든다. board 없는 부서는 그룹이 없다: 관리 화면 `DepartmentForm`(fields 에 board 없음, Task 4 가 고침), `tools/help_videos/seed.py`(Task 5 가 고침).
- `Department.save` 의 `Group.objects.create(name=f"{name} 출근표 입력")` 는 같은 이름 그룹이 이미 있으면 `Group.name` unique 위반 `IntegrityError` 로 500 이 난다. 0011 은 이 충돌을 `RuntimeError` 로 먼저 막지만 관리 화면 길은 막지 않는다. **Task 4 는 `DepartmentForm.clean` 에 아래 검사와 테스트를 더한다**(3단계 근무표 추가 화면의 "근무표 관리" 그룹 이름 검사도 같은 규칙을 쓴다). 새 부서뿐 아니라 입력 그룹 없는 기존 부서를 collect 근무표로 옮길 때도 `save` 가 그룹을 만들므로 조건은 "입력 그룹 없음 + 고른 board 가 collect" 다. board·name 을 함께 보므로 `clean_name` 이 아니라 `clean` 에 둔다(`clean_name` 시점에는 board 가 아직 cleaned_data 에 없을 수 있다).
  ```python
  # DepartmentForm.clean 안, return c 바로 앞
  name = c.get("name")
  if (board and name and not self.instance.input_group_id and board.input_mode == InputMode.COLLECT
          and Group.objects.filter(name=f"{name} 출근표 입력").exists()):
      self.add_error("name", f"같은 이름의 그룹이 이미 있습니다: {name} 출근표 입력")
  ```
  (`from django.contrib.auth.models import Group`, `from ..models import InputMode` 를 admin.py import 에 더한다.)
  ```python
  # tests/test_admin_department.py 끝
  def test_new_department_name_clashing_input_group_is_rejected(depts):
      Group.objects.create(name="운영 출근표 입력")
      data = {"code": "OPS", "name": "운영", "board": depts["UI"].board_id, "order": 9,
              "shifts": ["normal"], "managers": []}
      form = DepartmentForm(data)
      assert not form.is_valid()
      assert "같은 이름의 그룹이 이미 있습니다: 운영 출근표 입력" in str(form.errors["name"])
  ```
  (테스트 import 에 `from django.contrib.auth.models import Group`. 이 테스트는 Task 4 Step 2 의 실패 목록에 하나 더해진다: 검사 전에는 `form.is_valid()` 가 True 라 AssertionError.)
- 앱 코드가 board 없는 회차를 만드는 곳이 남아 있다: `duty/views/manage.py` 회차 만들기(`period or Period()`)와 `tools/help_videos/seed.py`. 근무표 없는 부서는 Task 4 의 0015 가 managers M2M 을 지우기 전에 IT 로 옮긴다(입력 그룹·담당자 포함). Task 6 의 NOT NULL 마이그레이션은 회차 만들기 길을 먼저 고친 뒤 0011 과 그 사이에 생긴 board 없는 회차를 IT 로 채우고, 그때 근무표 없는 부서가 남아 있으면 멈춘다.
- 이제 기존 테스트의 모든 저장 회차는 `board=it_board` 다. 뒤 작업이 `board=` 로 거르는 쿼리를 넣어도 기존 테스트가 빈 결과로 깨지지 않는다. 새로 쓰는 테스트도 회차를 만들 때 반드시 board 를 준다.
- `depts` 의 order 는 MEMS 0·TMCH 1·MD 2·UI 3(지금 `DEPT_ORDER` 와 같은 순서). Task 3 이 `DEPT_ORDER` 를 `order_by("order", "code")` 로 바꿔도 부서 필터 순서가 그대로다.
- 옛 이름 `CELLS`(= KEYS)·`COMMUTE_SHIFTS`·`CONTROL_SLOTS`·`SHIFT_TIMES` 는 shifts.py 에 그대로 있다. models.py 는 이제 `CONTROL_SLOTS`(ControlDuty, Task 2 가 지움)만 옛 상수로 쓴다.


---

### Task 2: ControlDuty → DutyAssignment

관제 배정 표 `ControlDuty(slot: int)`를 새 표 `DutyAssignment(cell: str)`로 옮긴다. 순서는 세 가지다.
1. 모델과 스키마 마이그레이션 `0012_dutyassignment`를 만든다(지적 1).
2. 데이터 마이그레이션 `0013_controlduty_to_assignment`를 만든다. `publish_undo`의 `k` 행을 `a` 행으로 바꾸고, 되돌리기도 넣는다.
3. `0014_delete_controlduty`로 `ControlDuty`를 지운다.

그 표를 직접 읽고 쓰는 서비스 7개와 테스트(설계 11절 허용 변환 b)는 기계적으로 바꾼다. 동작, 화면, 알림 문구, 링크, 칸 순서는 그대로다. 문서는 고치지 않는다. 문서 수정은 Task 10에 모은다(지적 17).

> 검증: `git archive main` 사본에서 이 작업의 코드를 그대로 넣어 돌렸다. 사본에는 Task 1이 없어서 다음 두 가지만 다르게 했다.
> - `0012`의 의존을 `0009_roster_history`로 두었다.
> - 마이그레이션 테스트의 Board 준비 줄을 뺐다.
>
> 결과는 다음과 같다.
> - Step 3: 2 failed(NodeNotFoundError, 단언 실패).
> - Step 5: 1 passed, 1 failed.
> - Step 7: 32 failed.
> - Step 12·15: 777 passed(775 + 새 2), 경고 0개.
> - `makemigrations duty --check --dry-run`: "No changes detected in app 'duty'".
> - 자동 생성 결과는 0012의 인덱스 이름 `duty_dutyas_date_7fadc2_idx`와 0014의 `DeleteModel`이며, 아래에 적은 그대로다.
>
> Task 1 뒤에 이 작업을 하면 Step 15의 기대는 **793 passed**(791 + 2)다.

**Files:**
- Modify: `duty/models.py`
  - 8행 shifts import: Task 1 상태 `from .shifts import CONTROL_SLOTS, DEVELOPER, KEYS, SHIFT_KEYS, STAFF, is_slot_cell, slot_index, weekdays`에서 Step 2는 `SLOT_KEYS`를 더하고, Step 13은 `CONTROL_SLOTS`를 뺀다.
  - `Period.publish_undo` 바로 위 주석을 고친다(Step 13).
  - `class ControlDuty`를 지운다(Step 13).
  - `class ChangeLog` 바로 앞에 `class DutyAssignment`를 더한다(Step 2).
- Create: `duty/migrations/0012_dutyassignment.py`: 스키마. `makemigrations`가 생성한 그대로 둔다.
- Create: `duty/migrations/0013_controlduty_to_assignment.py`: 데이터 RunPython. reverse를 포함한다.
- Create: `duty/migrations/0014_delete_controlduty.py`: `makemigrations`가 생성한 그대로 둔다.
- Create: `tests/test_migration_duty_assignment.py`
- Modify(아래 줄 번호는 main 기준이다. Task 1은 서비스 파일을 건드리지 않으므로 그대로 맞다):
  - `duty/services/generate.py`: 9–10행 import, 35–37행 저장
  - `duty/services/publish.py`: 9행 import, 38·41행 `preview_publish`, 49행 `_MODELS`
  - `duty/services/roster.py`: 9–10행 import, 65–66행 `published_days`의 관제 반복문
  - `duty/services/changes.py`
    - 8행 import, 18행 `_owner`, 44–45행 `_duty_warnings`
    - `change_cell`의 79행·85–87행
    - `exchange`의 115·119·121행
    - `swap`의 145–146·151–152행
  - `duty/services/stats.py`: 5행 import, 67행 `period_duty_counts`
  - `duty/services/periods.py`: 7행 import, 38행 `save_draft`, 57행 `move`
  - `duty/services/change_notice.py`: 8행 import, 53행 `_live`
- Test(허용 변환 b만, 단언 불변): 다음 13개 파일
  - `tests/test_changes.py`, `tests/test_periods.py`, `tests/test_views_manage.py`, `tests/test_publish.py`, `tests/test_views_roster.py`
  - `tests/test_stats.py`, `tests/test_roster.py`, `tests/test_roster_prefs.py`, `tests/test_period_lifecycle.py`, `tests/test_generate.py`
  - `tests/test_db_constraints.py`, `tests/test_calendar_feed.py`, `tests/test_models.py`
- 바꾸지 않는 파일(grep으로 확인했다):
  - `duty/services/calendar.py`, `duty/services/alarm_runner.py`, `duty/alarms/*`, `duty/views/*.py`: `ControlDuty`를 직접 읽지 않는다. `roster.published_days`의 `Day.members`·`Day.cells`(칸 키 `slot0`~`slot9`)만 읽고 키 모양이 같다.
  - `duty/views/manage.py` 55행의 `f.slot`: generator 실패 결과(`GenerationFailure.slot`, 인덱스)이고 모델이 아니다.
  - `duty/generator.py`: 1행 docstring의 `InMarketControlDutyGenerator.gs`는 옛 Apps Script 파일 이름이라 남긴다.
  - `duty/admin.py`, `tools/`, 템플릿, `duty/management/`: `ControlDuty`가 없다.
  - `docs/*.md`: Task 10이 고친다. ARCHITECTURE.md의 데이터 그림과 publish_undo 행 모양을 고칠 차례이고, 0013이 `k`를 `a`로 바꾼다는 설명도 이때 넣는다.

**Interfaces:**
- Consumes:
  - Task 1의 `duty.shifts.SLOT_KEYS`(`("slot0", …, "slot9")`), `slot_cell(i) -> str`, `slot_index(cell) -> int`, `is_slot_cell(cell) -> bool`. 뒤의 세 함수는 main부터 있었다.
  - Task 1의 마지막 마이그레이션 `("duty", "0011_boards_data")`. 이것이 0012의 의존이 되며, makemigrations가 leaf로 자동으로 고른다.
  - Task 1의 `duty.models.Board(code, name, input_mode, admin_group)`와 `Period.board`. 마이그레이션 테스트의 준비 코드에서만 쓴다.
- Produces:
  - `duty.models.DutyAssignment`
    - 칸: `period`(FK Period CASCADE, `related_name="duty_assignments"`), `date`(DateField), `cell`(CharField max_length=8, `choices=[(k, k) for k in SLOT_KEYS]`), `member`(FK User PROTECT, 역참조 기본 이름 `dutyassignment`)
    - 제약:
      - `dutyassignment_once`: unique(period, date, cell, member)
      - `dutyassignment_one_per_slot`: unique(period, date, cell), condition `Q(cell__startswith="slot")`
      - `dutyassignment_cell_valid`: `cell ∈ SLOT_KEYS`
    - 인덱스: `date`
  - 마이그레이션
    - `duty.0012_dutyassignment`: CreateModel
    - `duty.0013_controlduty_to_assignment`: `ControlDuty(slot=n)`을 `DutyAssignment(cell="slot{n}")`로, `publish_undo`의 `["k", p, d, m, n]`을 `["a", p, d, m, "slot{n}"]`로 바꾼다. reverse는 그 반대다.
    - `duty.0014_delete_controlduty`: DeleteModel
    - **다음 번호는 0015다.**
  - `duty.services.publish._MODELS = {"c": (Commute, "shift"), "a": (DutyAssignment, "cell")}`. 배포가 남기는 undo 행은 `["c", period_id, "YYYY-MM-DD", member_id, shift]`와 `["a", period_id, "YYYY-MM-DD", member_id, "slotN"]`이다.
  - 공개 함수 시그니처는 바뀌지 않는다: `published_days`, `change_cell`, `exchange`, `swap`, `run_generation`, `period_duty_counts`, `save_draft`, `move`, `preview_publish`, `publish`, `unpublish`.
  - `duty.models.ControlDuty`는 없어진다. `duty/models.py`는 옛 상수(`CONTROL_SLOTS`·`CELLS`·`COMMUTE_SHIFTS`)를 하나도 import하지 않는다.
  - 1단계에서는 당번 행이 전부 `slot*`이다. 그래서 "당번 행 전체"를 보는 곳의 동작이 지금과 같다: `_owner`의 EXISTS, `preview_publish`의 `live`, `change_notice._live`, `stats.period_duty_counts`. 그날의 주인(6.1) 기준으로 바꾸는 일: `_owner`=Task 5, `preview_publish`=Task 6, `period_duty_counts`=Task 7, `change_notice._live`=Task 8.

명령은 저장소 루트에서 실행한다. `manage.py`는 늘 `DJANGO_SETTINGS_MODULE=config.test_settings`로 부른다. `DUTY_DEBUG=1`은 `.env`와 `data/`의 실명 DB에 접속하므로 쓰지 않는다(지적 19).

- [ ] **Step 1: 마이그레이션 테스트를 먼저 쓴다**

`tests/test_migration_duty_assignment.py`(새 파일, 이름은 모두 가상):
```python
"""ControlDuty → DutyAssignment 데이터 이전(설계 10절 1단계, 12절 마이그레이션 테스트). 가상의 이름만 쓴다."""
from datetime import date, datetime, timezone

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from duty.models import Commute, DutyAssignment, Period
from duty.services.publish import unpublish

BEFORE = [("duty", "0012_dutyassignment")]
AFTER = [("duty", "0013_controlduty_to_assignment")]
D = date(2026, 11, 9)


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()  # 앞선 migrate 로 바뀐 적용 기록을 다시 읽는다
    executor.migrate(target)
    return executor.loader.project_state(target).apps


def _leaf():
    return MigrationExecutor(connection).loader.graph.leaf_nodes()


@pytest.fixture
def old_apps():
    apps = _migrate(BEFORE)
    yield apps
    _migrate(_leaf())  # 다른 테스트를 위해 최신 스키마로


def _seed(apps):
    """p: 배포됨(관제 slot0=가, slot9=나, publish_undo 에 q 의 c·k 행), q: 생성됨(publish_undo 없음)."""
    Group = apps.get_model("auth", "Group")
    Board = apps.get_model("duty", "Board")
    Period_ = apps.get_model("duty", "Period")
    User = apps.get_model("duty", "User")
    ControlDuty = apps.get_model("duty", "ControlDuty")
    # 마이그레이션 0011 이 만든 IT 근무표가 있으면 그것을, flush 된 DB 면 새로(이력 모델엔 Board.save 가 없어 그룹을 직접)
    board = Board.objects.filter(code="it").first() or Board.objects.create(
        code="it", name="IT 당번표", input_mode="collect", admin_group=Group.objects.create(name="이전 시험 관리"))
    a = User.objects.create(username="T001", name="가상가")
    b = User.objects.create(username="T002", name="가상나")
    q = Period_.objects.create(name="q", start_date=D, end_date=D, status="generated", board=board)
    p = Period_.objects.create(name="p", start_date=D, end_date=D, status="published", board=board,
                               published_at=datetime(2026, 11, 6, tzinfo=timezone.utc), publish_undo=[
        ["c", q.pk, "2026-11-09", a.pk, "normal"], ["k", q.pk, "2026-11-09", b.pk, 3]])
    ControlDuty.objects.create(period=p, date=D, slot=0, member=a)
    ControlDuty.objects.create(period=p, date=D, slot=9, member=b)
    return p.pk, q.pk, a.pk, b.pk


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_controlduty_to_assignment_and_back(old_apps):
    p, q, a, b = _seed(old_apps)

    apps = _migrate(AFTER)
    DA = apps.get_model("duty", "DutyAssignment")
    P = apps.get_model("duty", "Period")
    assert sorted(DA.objects.values_list("period_id", "date", "cell", "member_id")) == [
        (p, D, "slot0", a), (p, D, "slot9", b)]
    assert not apps.get_model("duty", "ControlDuty").objects.exists()
    assert P.objects.get(pk=p).publish_undo == [
        ["c", q, "2026-11-09", a, "normal"], ["a", q, "2026-11-09", b, "slot3"]]
    assert P.objects.get(pk=q).publish_undo is None

    apps = _migrate(BEFORE)  # 되돌리기
    CD = apps.get_model("duty", "ControlDuty")
    assert sorted(CD.objects.values_list("period_id", "date", "slot", "member_id")) == [
        (p, D, 0, a), (p, D, 9, b)]
    assert not apps.get_model("duty", "DutyAssignment").objects.exists()
    assert apps.get_model("duty", "Period").objects.get(pk=p).publish_undo == [
        ["c", q, "2026-11-09", a, "normal"], ["k", q, "2026-11-09", b, 3]]


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_unpublish_after_conversion_restores_assignment(old_apps):
    """옛 k 행이 a 행으로 바뀐 회차를 배포 취소하면 관제 칸이 되살아난다(설계 12절 '변환 뒤 배포 취소')."""
    p, q, a, b = _seed(old_apps)
    _migrate(_leaf())
    unpublish(Period.objects.get(pk=p))
    assert Commute.objects.filter(period_id=q, date=D, member_id=a, shift="normal").exists()
    assert DutyAssignment.objects.filter(period_id=q, date=D, cell="slot3", member_id=b).exists()
```
`published_at`이 필요한 이유가 있다. `unpublish_info`가 `ChangeLog.objects.filter(at__gte=period.published_at)`를 세기 때문에, 이 값이 None이면 `ValueError: Cannot use None as a query value`가 난다.

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_migration_duty_assignment.py -q`
Expected: 수집 오류 1개(`ImportError: cannot import name 'DutyAssignment' from 'duty.models'`), `1 error`.

- [ ] **Step 3: `DutyAssignment` 모델과 스키마 마이그레이션 `0012_dutyassignment`를 만든다(지적 1)**

`duty/models.py` 8번째 줄(Task 1 상태)에서는 `SLOT_KEYS`만 더한다.
```python
from .shifts import CONTROL_SLOTS, DEVELOPER, KEYS, SHIFT_KEYS, SLOT_KEYS, STAFF, is_slot_cell, slot_index, weekdays
```
`class ChangeLog(models.Model):` 바로 앞에 아래 블록을 넣는다. 이 시점에는 `class ControlDuty` 뒤에 들어가며, `ControlDuty`는 Step 13에서 지운다. 블록 끝에는 빈 줄 둘을 둔다.
```python
class DutyAssignment(models.Model):
    """당번 배정 한 칸(1단계는 장중관제 slot0~slot9). 생성이 만들고 근무 변경이 바꾼다."""
    period = models.ForeignKey(Period, on_delete=models.CASCADE, related_name="duty_assignments")
    date = models.DateField()
    cell = models.CharField(max_length=8, choices=[(k, k) for k in SLOT_KEYS])
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["period", "date", "cell", "member"], name="dutyassignment_once"),
            # 관제 칸은 칸당 한 명(DB가 계속 보장)
            models.UniqueConstraint(fields=["period", "date", "cell"], condition=Q(cell__startswith="slot"),
                                    name="dutyassignment_one_per_slot"),
            _one_of("cell", SLOT_KEYS, "dutyassignment_cell_valid"),
        ]
        indexes = [models.Index(fields=["date"])]
```
(`Q`는 models.py 6행에서 이미 import하고 있다.)

Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --name dutyassignment`
Expected 출력:
```
Migrations for 'duty':
  duty/migrations/0012_dutyassignment.py
    + Create model DutyAssignment
```
생성된 파일은 아래와 같아야 하고, 첫 줄의 생성 시각만 다르다. 손으로 고치지 않는다. `dependencies`가 `0011_boards_data`가 아니면 Task 1이 덜 끝난 것이니 멈춘다.
```python
# Generated by Django 5.2.19 on 2026-11-15 08:30

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('duty', '0011_boards_data'),
    ]

    operations = [
        migrations.CreateModel(
            name='DutyAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('cell', models.CharField(choices=[('slot0', 'slot0'), ('slot1', 'slot1'), ('slot2', 'slot2'), ('slot3', 'slot3'), ('slot4', 'slot4'), ('slot5', 'slot5'), ('slot6', 'slot6'), ('slot7', 'slot7'), ('slot8', 'slot8'), ('slot9', 'slot9')], max_length=8)),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('period', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='duty_assignments', to='duty.period')),
            ],
            options={
                'indexes': [models.Index(fields=['date'], name='duty_dutyas_date_7fadc2_idx')],
                'constraints': [models.UniqueConstraint(fields=('period', 'date', 'cell', 'member'), name='dutyassignment_once'), models.UniqueConstraint(condition=models.Q(('cell__startswith', 'slot')), fields=('period', 'date', 'cell'), name='dutyassignment_one_per_slot'), models.CheckConstraint(condition=models.Q(('cell__in', ['slot0', 'slot1', 'slot2', 'slot3', 'slot4', 'slot5', 'slot6', 'slot7', 'slot8', 'slot9'])), name='dutyassignment_cell_valid')],
            },
        ),
    ]
```

Run: `.venv/bin/pytest -W error tests/test_migration_duty_assignment.py -q`
Expected: `2 failed`.
- `test_controlduty_to_assignment_and_back`: `_migrate(AFTER)`에서 `NodeNotFoundError: Node ('duty', '0013_controlduty_to_assignment') not a valid node`가 난다.
- `test_unpublish_after_conversion_restores_assignment`: leaf가 0012이고 `_MODELS`가 아직 `k`를 `ControlDuty`로 되살린다. 그래서 `DutyAssignment ... cell="slot3"` 단언이 `assert False`로 실패한다.

- [ ] **Step 4: 데이터 마이그레이션 `0013_controlduty_to_assignment`를 쓴다**

`duty/migrations/0013_controlduty_to_assignment.py`(새 파일):
```python
"""관제 배정 ControlDuty(slot 숫자) → DutyAssignment(cell "slot{n}"), 배포 취소 보관 행 k → a. 되돌리기 포함.

앱 코드(shifts.py 등)를 import 하지 않는다: 앱 상수가 나중에 바뀌어도 이 마이그레이션의 결과는 같아야 한다.
"""
from django.db import migrations


def _undo(apps, convert):
    Period = apps.get_model("duty", "Period")
    for p in Period.objects.exclude(publish_undo=None):
        new = [convert(r) for r in p.publish_undo]
        if new != p.publish_undo:
            p.publish_undo = new
            p.save(update_fields=["publish_undo"])


def forward(apps, schema_editor):
    ControlDuty = apps.get_model("duty", "ControlDuty")
    DutyAssignment = apps.get_model("duty", "DutyAssignment")
    DutyAssignment.objects.bulk_create(
        DutyAssignment(period_id=r.period_id, date=r.date, cell=f"slot{r.slot}", member_id=r.member_id)
        for r in ControlDuty.objects.all()
    )
    ControlDuty.objects.all().delete()  # 되돌리기가 같은 행을 다시 만들 때 겹치지 않게(표는 0014 가 지운다)
    _undo(apps, lambda r: ["a", r[1], r[2], r[3], f"slot{r[4]}"] if r[0] == "k" else r)


def backward(apps, schema_editor):
    ControlDuty = apps.get_model("duty", "ControlDuty")
    DutyAssignment = apps.get_model("duty", "DutyAssignment")
    rows = DutyAssignment.objects.filter(cell__startswith="slot")
    ControlDuty.objects.bulk_create(
        ControlDuty(period_id=r.period_id, date=r.date, slot=int(r.cell[4:]), member_id=r.member_id) for r in rows
    )
    rows.delete()
    _undo(apps, lambda r: ["k", r[1], r[2], r[3], int(r[4][4:])] if r[0] == "a" and r[4].startswith("slot") else r)


class Migration(migrations.Migration):

    dependencies = [
        ("duty", "0012_dutyassignment"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
```

- [ ] **Step 5: 첫째 테스트 통과를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_migration_duty_assignment.py -q`
Expected: `1 failed, 1 passed`.
- `test_controlduty_to_assignment_and_back`는 통과한다.
- `test_unpublish_after_conversion_restores_assignment`는 아직 실패한다. `publish._MODELS`가 `"k"`만 알아서 `a` 행을 무시하고, 그래서 `cell="slot3"` 단언이 깨진다. Step 9에서 통과한다.

- [ ] **Step 6: 기존 테스트를 변환 b로 바꾼다(기계적 치환, 단언 불변)**

1) 아래 스크립트로 13개 파일을 일괄 치환한다. `test_generator.py`·`test_baseline.py`에는 해당 문자열이 없다. Task 1(변환 a)이 바꾼 import 줄과 `board=` 인자는 그대로 남는다. 문자열 치환이라 줄 번호와 상관없다.
```bash
.venv/bin/python - <<'EOF'
import pathlib, re
for f in ["tests/test_changes.py", "tests/test_periods.py", "tests/test_views_manage.py", "tests/test_publish.py",
          "tests/test_views_roster.py", "tests/test_stats.py", "tests/test_roster.py", "tests/test_roster_prefs.py",
          "tests/test_period_lifecycle.py", "tests/test_generate.py", "tests/test_db_constraints.py",
          "tests/test_calendar_feed.py", "tests/test_models.py"]:
    p = pathlib.Path(f)
    s = p.read_text()
    s = s.replace("ControlDuty", "DutyAssignment")
    s = re.sub(r"\bslot=(\d+)", r'cell="slot\1"', s)
    s = s.replace('values_list("date", "member_id", "slot")', 'values_list("date", "member_id", "cell")')
    s = s.replace('values_list("slot", flat=True)', 'values_list("cell", flat=True)')
    p.write_text(s)

# test_swap_duty_when_member_holds_two_slots: 단언 {1, 2}/{0} 을 그대로 두려고 칸 키를 숫자로 되돌린다
p = pathlib.Path("tests/test_changes.py")
s = p.read_text()
old = 'slots = lambda n: set(DutyAssignment.objects.filter(period=p, date=D, member=m[n]).values_list("cell", flat=True))'
assert s.count(old) == 1
s = s.replace(old, 'slots = lambda n: {slot_index(c) for c in\n'
                   '                       DutyAssignment.objects.filter(period=p, date=D, member=m[n]).values_list("cell", flat=True)}')
s = s.replace("from duty.services.roster import find_day\n", "from duty.services.roster import find_day\nfrom duty.shifts import slot_index\n", 1)
p.write_text(s)
EOF
```
치환 예시는 다음과 같다.
- `ControlDuty.objects.create(period=p, date=D, slot=0, member=m["가"])`는 `DutyAssignment.objects.create(period=p, date=D, cell="slot0", member=m["가"])`가 된다.
- `ControlDuty.objects.get(period=p, date=D, slot=1).member == m["가"]`는 `DutyAssignment.objects.get(period=p, date=D, cell="slot1").member == m["가"]`가 된다.
- 함수 안의 지역 import도 같이 바뀐다.
  - `tests/test_views_manage.py::test_lifecycle_move_and_unpublish_views`: `from duty.models import DutyAssignment, PeriodEvent`
  - `tests/test_calendar_feed.py::test_feed_filters_by_chosen_shifts`: `from duty.models import DutyAssignment`
- `tests/test_period_lifecycle.py::rows`의 `values_list(..., "slot")`는 `"cell"`이 된다. 이 값은 앞뒤를 비교하는 데만 쓰고, 리터럴 기대 값이 없다.

치환 뒤에도 기존 단언이 그대로 맞는 곳:
- `tests/test_db_constraints.py::test_control_slot_range`: `slot=10`이 `cell="slot10"`이 된다. 이 값은 `dutyassignment_cell_valid`에 걸리므로 같은 `IntegrityError` 단언이 맞는다. `cell="slot9"`는 들어간다.
- `tests/test_models.py::test_one_member_per_duty_slot`: 같은 칸에 두 번째 사람을 넣으면 `dutyassignment_one_per_slot`에 걸려 `IntegrityError`가 난다.
- `tests/test_models.py::test_member_may_hold_several_duty_slots_per_day`: slot0과 slot1은 서로 다른 칸이라 통과한다.

2) 남은 것이 없는지 확인한다. `__pycache__`의 옛 `.pyc`가 걸리지 않게 `.py`만 본다. 새 마이그레이션 테스트는 일부러 `ControlDuty`를 쓰므로 뺀다.
Run: `grep -rn --include=*.py 'ControlDuty\|\bslot=\|"slot")\|"slot", flat' tests/ | grep -v tests/test_migration_duty_assignment.py; echo "exit=$?"`
Expected: 출력 없음, `exit=1`

- [ ] **Step 7: 실패를 확인한다(서비스가 아직 ControlDuty를 읽는다)**

Run: `.venv/bin/pytest -W error -q`
Expected: 약 32 failed, 나머지는 passed. 예를 들면 다음과 같다.
- `test_generate`: `DutyAssignment...count() == 50`이 0이 된다.
- `test_roster`·`test_views_roster`: 관제 칸이 빈다.
- `test_changes`: 관제 교체가 "이 칸에 없습니다"로 실패한다.
- `test_migration_duty_assignment.py::test_unpublish_after_conversion_restores_assignment`

- [ ] **Step 8: `duty/services/generate.py`**

9–10행. 지금:
```python
from ..models import Commute, ControlDuty, Period, User
from ..shifts import DEVELOPER
```
바꾼 뒤:
```python
from ..models import Commute, DutyAssignment, Period, User
from ..shifts import DEVELOPER, slot_cell
```
35–37행. 지금:
```python
    ControlDuty.objects.filter(period=period).delete()
    ControlDuty.objects.bulk_create(
        ControlDuty(period=period, date=d, slot=i, member=by_code[code])
```
바꾼 뒤:
```python
    DutyAssignment.objects.filter(period=period).delete()
    DutyAssignment.objects.bulk_create(
        DutyAssignment(period=period, date=d, cell=slot_cell(i), member=by_code[code])
```

- [ ] **Step 9: `duty/services/publish.py`**

9행. 지금 `from ..models import ChangeLog, Commute, ControlDuty, Period, PeriodEvent, User`
바꾼 뒤:
```python
from ..models import ChangeLog, Commute, DutyAssignment, Period, PeriodEvent, User
```
38행. 지금:
```python
    names |= set(ControlDuty.objects.filter(period__in=_others(period), **rng).values_list("period__name", flat=True))
```
바꾼 뒤:
```python
    names |= set(DutyAssignment.objects.filter(period__in=_others(period), **rng).values_list("period__name", flat=True))
```
41행. 지금:
```python
    live |= set(ControlDuty.objects.filter(period__in=_others(period), **rng).values_list("period_id", "date"))
```
바꾼 뒤:
```python
    live |= set(DutyAssignment.objects.filter(period__in=_others(period), **rng).values_list("period_id", "date"))
```
49행. 지금 `_MODELS = {"c": (Commute, "shift"), "k": (ControlDuty, "slot")}`
바꾼 뒤(지적 2: 주석의 번호는 0013이다):
```python
_MODELS = {"c": (Commute, "shift"), "a": (DutyAssignment, "cell")}  # 옛 "k"(관제 숫자) 행은 마이그레이션 0013 이 "a" 로 바꿨다
```
`publish`와 `unpublish` 본문은 `_MODELS`를 돌기만 하므로 그대로 둔다. `field`가 `"cell"`이 되므로 `["a", p, d, m, "slotN"]`을 남기고, 그 행으로 되살린다.

Run: `.venv/bin/pytest -W error tests/test_migration_duty_assignment.py -q`
Expected: `2 passed`

- [ ] **Step 10: `duty/services/roster.py`**

9–10행. 지금:
```python
from ..models import ChangeLog, Commute, ControlDuty, Period, User
from ..shifts import CELLS, cell_label, is_slot_cell, slot_cell
```
바꾼 뒤(`slot_cell`은 65–66행에서만 쓰였다):
```python
from ..models import ChangeLog, Commute, DutyAssignment, Period, User
from ..shifts import CELLS, cell_label, is_slot_cell
```
65–66행. 지금:
```python
    for d, pid, i, name in scoped(ControlDuty.objects).values_list("date", "period_id", "slot", "member__name"):
        slot(d, pid)["cells"][slot_cell(i)].append(name)
```
바꾼 뒤:
```python
    for d, pid, cell, name in scoped(DutyAssignment.objects).values_list("date", "period_id", "cell", "member__name"):
        slot(d, pid)["cells"][cell].append(name)
```

- [ ] **Step 11: `duty/services/changes.py`**

9행 shifts import는 그대로 둔다. `CONTROL_SLOTS`·`slot_index`를 계속 쓰기 때문이다.

8행. 지금 `from ..models import ChangeLog, Commute, ControlDuty, Period, User`
바꾼 뒤:
```python
from ..models import ChangeLog, Commute, DutyAssignment, Period, User
```
`_owner` 18행. 지금:
```python
                | Exists(ControlDuty.objects.filter(period=OuterRef("pk"), date=d)))
```
바꾼 뒤:
```python
                | Exists(DutyAssignment.objects.filter(period=OuterRef("pk"), date=d)))
```
`_duty_warnings` 44–45행. 지금:
```python
        for duty in ControlDuty.objects.filter(period=period, date=d, member=m):
            out += _eligibility_warnings(period, d, duty.slot, m)
```
바꾼 뒤:
```python
        for duty in DutyAssignment.objects.filter(period=period, date=d, member=m):
            out += _eligibility_warnings(period, d, slot_index(duty.cell), m)
```
`change_cell` 79행. 지금:
```python
        row = ControlDuty.objects.filter(period=period, date=d, slot=slot).first()
```
바꾼 뒤:
```python
        row = DutyAssignment.objects.filter(period=period, date=d, cell=cell).first()
```
`change_cell` 85–87행. 지금:
```python
        others = ControlDuty.objects.filter(period=period, date=d, member=after).exclude(slot=slot).order_by("slot")
        if others:
            labels = ", ".join(CONTROL_SLOTS[o.slot][0] for o in others)
```
바꾼 뒤:
```python
        # slot0~slot9 는 숫자가 한 자리라 글자 순서가 칸 순서다
        others = DutyAssignment.objects.filter(period=period, date=d, member=after).exclude(cell=cell).order_by("cell")
        if others:
            labels = ", ".join(CONTROL_SLOTS[slot_index(o.cell)][0] for o in others)
```
76행의 지역 변수 `slot = slot_index(cell)`은 84행 `_eligibility_warnings(period, d, slot, after)`가 계속 쓰므로 남긴다.

`exchange` 115행. 지금:
```python
        rows = list(ControlDuty.objects.filter(period=period, date=d, member=after).exclude(slot=slot_index(cell)))
```
바꾼 뒤:
```python
        rows = list(DutyAssignment.objects.filter(period=period, date=d, member=after).exclude(cell=cell))
```
`exchange` 119행. 지금:
```python
        if ControlDuty.objects.filter(period=period, date=d, slot=slot_index(cell), member=after).exists():
```
바꾼 뒤:
```python
        if DutyAssignment.objects.filter(period=period, date=d, cell=cell, member=after).exists():
```
`exchange` 121행. 지금:
```python
        other = f"slot{rows[0].slot}" if rows else None
```
바꾼 뒤:
```python
        other = rows[0].cell if rows else None
```
`swap` 145–146행. 지금:
```python
        ra = ControlDuty.objects.filter(period=period, date=d, slot=sa, member=a).first()
        rb = ControlDuty.objects.filter(period=period, date=d, slot=sb, member=b).first()
```
바꾼 뒤:
```python
        ra = DutyAssignment.objects.filter(period=period, date=d, cell=cell_a, member=a).first()
        rb = DutyAssignment.objects.filter(period=period, date=d, cell=cell_b, member=b).first()
```
`swap` 151–152행. 지금:
```python
        ControlDuty.objects.create(period=period, date=d, slot=sa, member=b)
        ControlDuty.objects.create(period=period, date=d, slot=sb, member=a)
```
바꾼 뒤:
```python
        DutyAssignment.objects.create(period=period, date=d, cell=cell_a, member=b)
        DutyAssignment.objects.create(period=period, date=d, cell=cell_b, member=a)
```
144행의 `sa, sb = slot_index(cell_a), slot_index(cell_b)`는 153행 `_eligibility_warnings`가 계속 쓰므로 남긴다.

- [ ] **Step 12: `duty/services/stats.py`, `periods.py`, `change_notice.py`, 그리고 통과 확인**

`stats.py`
- 5행: 지금 `from ..models import Commute, ControlDuty, Period, User`. 바꾼 뒤:
  ```python
  from ..models import Commute, DutyAssignment, Period, User
  ```
  6행의 `CONTROL_SLOTS`는 64행에서 쓰므로 그대로 둔다.
- 67행: 지금 `    for name in ControlDuty.objects.filter(period=period).values_list("member__name", flat=True):`. 바꾼 뒤:
  ```python
      for name in DutyAssignment.objects.filter(period=period).values_list("member__name", flat=True):
  ```

`periods.py`
- 7행: 지금 `from ..models import ChangeLog, Commute, ControlDuty, Department, Period, PeriodEvent`. 바꾼 뒤:
  ```python
  from ..models import ChangeLog, Commute, Department, DutyAssignment, Period, PeriodEvent
  ```
- 38행: 지금 `        for model in (Commute, ControlDuty):`. 바꾼 뒤:
  ```python
          for model in (Commute, DutyAssignment):
  ```
- 57행: 지금 `    ControlDuty.objects.filter(period=period).delete()`. 바꾼 뒤:
  ```python
      DutyAssignment.objects.filter(period=period).delete()
  ```

`change_notice.py`
- 8행: 지금 `from ..models import ChangeLog, Commute, ControlDuty, Period, PushAlarmSubscription, TelegramAlarmProfile`. 바꾼 뒤:
  ```python
  from ..models import ChangeLog, Commute, DutyAssignment, Period, PushAlarmSubscription, TelegramAlarmProfile
  ```
- 53행: 지금 `                 or ControlDuty.objects.filter(period=p, date=r.date).exists()))`. 바꾼 뒤:
  ```python
                   or DutyAssignment.objects.filter(period=p, date=r.date).exists()))
  ```
  그날의 주인(6.1) 기준으로 바꾸는 일: `_owner`=Task 5, `preview_publish`=Task 6, `period_duty_counts`=Task 7, `change_notice._live`=Task 8.

Run: `.venv/bin/pytest -W error -q`
Expected: 모두 passed(Task 1 뒤 기준 793 passed), 경고 0개. 이 시점에는 `ControlDuty` 모델과 표가 남아 있지만 쓰는 곳이 없다.

- [ ] **Step 13: `ControlDuty` 모델을 지우고 `0014_delete_controlduty`를 만든다**

1) `duty/models.py`에서 `class ControlDuty(models.Model):`부터 그 `indexes = [models.Index(fields=["date"])]` 줄 뒤 빈 줄 둘까지를 통째로 지운다. 그러면 `class Commute` 바로 뒤에 `class DutyAssignment`가 온다.

2) 8번째 줄에서 `CONTROL_SLOTS`를 뺀다. 지운 `duty_slot_range` 제약이 그 상수를 쓰던 마지막 곳이었다.
```python
from .shifts import DEVELOPER, KEYS, SHIFT_KEYS, SLOT_KEYS, STAFF, is_slot_cell, slot_index, weekdays
```
Run: `grep -n "CONTROL_SLOTS\|CELLS\|COMMUTE_SHIFTS" duty/models.py; echo "exit=$?"`
Expected: 출력 없음, `exit=1`

3) `Period.publish_undo` 바로 위의 주석 한 줄을 고친다. 지금:
```python
    # 배포가 지운 행 [[모델 c|k, 회차 id, 날짜, 멤버 id, 출근조|칸]]. 배포 취소 때 되살린다. null = 되돌릴 정보 없음
```
바꾼 뒤:
```python
    # 배포가 지운 행 목록: ["c", 회차 id, 날짜, 멤버 id, 출근조] | ["a", 회차 id, 날짜, 멤버 id, 당번 칸]. 배포 취소 때 되살린다. null = 되돌릴 정보 없음
```

4) Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --name delete_controlduty`
Expected 출력:
```
Migrations for 'duty':
  duty/migrations/0014_delete_controlduty.py
    - Delete model ControlDuty
```
생성된 파일은 아래와 같고, 생성 시각 줄만 다르다. 손으로 고치지 않는다.
```python
# Generated by Django 5.2.19 on 2026-11-15 08:32

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('duty', '0013_controlduty_to_assignment'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ControlDuty',
        ),
    ]
```

- [ ] **Step 14: 모델·마이그레이션·남은 이름을 확인한다**

Run:
```bash
DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --check --dry-run
grep -rn --include=*.py "ControlDuty" duty tests tools | grep -v "duty/migrations/" | grep -v "tests/test_migration_duty_assignment.py"
.venv/bin/pytest -W error tests/test_migration_duty_assignment.py tests/test_migration_boards.py tests/test_user_model.py -q
```
Expected:
- 첫 명령은 `No changes detected in app 'duty'`를 찍는다.
- grep은 `duty/generator.py:1:`(옛 Apps Script 파일 이름) 한 줄만 낸다.
- pytest는 모두 passed다.
  - `BEFORE`로 되돌릴 때 0014의 reverse가 `ControlDuty` 표를 다시 만들고, fixture 뒷정리가 끝까지 다시 올린다.
  - Task 1의 `test_migration_boards`는 0009까지 내려갔다가 올라오면서 0012~0014를 지난다. 이 두 표는 비어 있으니 그대로 통과한다.
  - `test_no_pending_migrations`도 통과한다.

- [ ] **Step 15: 전체 테스트**

Run: `.venv/bin/pytest -W error -q`
Expected: **793 passed**(Task 1 뒤 791 + 새 2), 경고 0개.

이 작업은 화면 코드(views·templates·static)를 바꾸지 않는다. 화면이 받는 값(`published_days`의 칸 키·이름)도 같아서, 기존 화면 테스트(`test_views_roster`·`test_roster_prefs`·`test_calendar_feed`)가 지금 단언 그대로 통과한다. 그래서 브라우저 확인은 화면을 바꾸는 작업에서 한다. 이 단계에서 `DUTY_DEBUG=1 runserver`로 실명 DB를 열지 않는다.

- [ ] **Step 16: 커밋**

```bash
git add duty/models.py duty/migrations/0012_dutyassignment.py duty/migrations/0013_controlduty_to_assignment.py \
  duty/migrations/0014_delete_controlduty.py \
  duty/services/generate.py duty/services/publish.py duty/services/roster.py duty/services/changes.py \
  duty/services/stats.py duty/services/periods.py duty/services/change_notice.py \
  tests/test_migration_duty_assignment.py \
  tests/test_changes.py tests/test_periods.py tests/test_views_manage.py tests/test_publish.py \
  tests/test_views_roster.py tests/test_stats.py tests/test_roster.py tests/test_roster_prefs.py \
  tests/test_period_lifecycle.py tests/test_generate.py tests/test_db_constraints.py \
  tests/test_calendar_feed.py tests/test_models.py
git commit -m "$(cat <<'EOF'
feat: 관제 배정을 DutyAssignment(cell=slotN)로 옮기고 ControlDuty 삭제(배포 취소 보관 행 k→a, 되돌리기 포함)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

**계획을 쓰며 정한 것(검토 때 볼 점):**
- **지적 1:** 모델과 스키마 마이그레이션(0012)을 이 작업의 첫 구현 단계(Step 3)로 넣었다. `makemigrations`가 생성한 그대로 커밋한다.
- **지적 2:** 파일 이름을 `0012_dutyassignment`, `0013_controlduty_to_assignment`, `0014_delete_controlduty`로 고정했다. 테스트의 BEFORE는 0012, AFTER는 0013이다. `publish.py` 주석은 0013을 가리킨다. 뒤 작업의 첫 마이그레이션 번호는 **0015**다.
- **지적 19:** 모든 `manage.py` 명령에 `DJANGO_SETTINGS_MODULE=config.test_settings`를 붙였다. 옛 Step 1의 `manage.py shell` 확인은 지우고, Step 2의 pytest 수집 오류로 대신했다. 옛 Step 17의 `DUTY_DEBUG=1 runserver` 화면 확인도 지웠다. 화면 코드가 바뀌지 않기 때문이다.
- **지적 17:** 문서(ARCHITECTURE.md 43·87행)는 고치지 않는다. Task 10에 넘긴다. models.py 코드 주석(`publish_undo`)만 고친다.
- **기대 값 불변:** `test_swap_duty_when_member_holds_two_slots`는 `slot_index`로 숫자를 다시 만들어, 단언 `{1, 2}`/`{0}`을 그대로 둔다.
- **정방향이 `ControlDuty` 행을 지운다:** 되돌리기가 같은 행을 다시 만들 때 unique 제약 `duty_one_member_per_slot`에 걸리지 않게 하려는 것이다. 표는 0014에서 어차피 지운다.
- **마이그레이션 테스트의 Board:** 0012 시점에는 `Period.board`가 null을 허용하지만, Task 6이 NOT NULL로 바꾼 뒤에도 0012 이력 모델로 돌므로 그대로 서도록 board를 준다. 이력 모델에는 `Board.save()`가 없어서 관리 그룹을 직접 만든다. IT 근무표가 이미 있으면(0011이 만든 것) 그것을 쓴다.
- **_migrate:** Task 1의 `test_migration_boards`와 같은 모양이다. `build_graph()`로 적용 기록을 다시 읽고, fixture 뒷정리로 leaf까지 올린다.


---

### Task 3: shifts.py 정의 기반 헬퍼·boards 서비스·표시 계열

`duty/shifts.py` 의 칸 헬퍼를 정의 목록(defs)을 받는 순수 함수로 바꾼다(기본값 없음, 설계 4.1). `duty/services/boards.py` 에 `it_board`·`defs`·`board_of` 를 만든다. 표시·라벨 계열은 근무표 정의를 읽게 한다. 대상은 근무표 화면, 스케줄 선택지, CSV 열 이름, 관리 화면 부서 출근조, 회차·이력 화면 칸 이름이다.

이 작업에서 정하는 것:
- `views/roster.py` 의 모든 뷰(roster·cell·day·me)는 `_board(user) = boards.board_of(user) or boards.it_board()` 하나로 근무표를 정한다(지적 12). 뒤 작업(Task 5 조회·변경)은 이미 있는 `board` 변수를 넘기기만 한다.
- `DEPT_ORDER` 상수를 지운다. 부서 필터는 `Department.objects.filter(board=board).order_by("order", "code")` 이다(지적 8, 설계 4.4·7절). Task 1 의 conftest `depts` 가 order 0..3(MEMS·TMCH·MD·UI)을 주므로 기존 테스트의 순서는 그대로다.
- 회차 생성 실패 칸 이름은 `slot_names = [x.name for x in slot_defs(defs)]` / `slot_names[f.slot]` 이다(지적 11). generator 의 칸 번호는 관제 정의 순서이므로 Task 7 generate 의 `slots[i].key` 와 맞는다.
- `collect.shift_names(dept)` 의 순서는 **부서 출근조 순서**(`dept.shift_keys()`)다(지적 10). Task 7 은 이 정의를 다시 만들지 않는다.

알림·캘린더·생성·통계·변경은 뒤 작업 범위다(Task 5·7·8). 거기서는 이 작업이 시그니처를 바꾼 헬퍼만 기계적으로 `LEGACY_DEFS` 로 부른다. `alarms/` 는 순수 모듈이라 `boards.defs()`(ORM)를 부를 수 없기 때문이다. `LEGACY_DEFS` 는 옛 상수로 만든 IT 정의다. 테스트가 `IT_DEFS` 와 같다고 고정하므로 알림 문구는 한 글자도 바뀌지 않는다. 옛 상수(`COMMUTE_SHIFTS`·`CONTROL_SLOTS`·`SHIFT_TIMES`)와 `LEGACY_DEFS` 는 뒤 작업이 모든 호출부를 옮긴 뒤 지운다.

사용자 화면 글자, 칸 순서, 알림 문구·링크는 바뀌지 않는다. 템플릿의 묶음 제목 "관제"(`_daycell.html`)와 "장중관제"(`day.html`, `_cell_form.html`)는 지금 글자 그대로 둔다. 이 값은 `SLOT_GROUP_SHORT`·`SLOT_GROUP_NAME` 과 같다. 묶음 제목을 정의 목록에서 고르는 일은 2단계(점심당번)에서 한다. 문서는 고치지 않는다(ARCHITECTURE 수정은 Task 10 에 모은다, 지적 17).

줄 번호는 `main`(567ca6d) 기준이다. Task 1·2 는 아래 파일 가운데 `duty/services/roster.py`(Task 2: shifts import 가 `from ..shifts import CELLS, cell_label, is_slot_cell`)와 테스트 파일의 회차·당번 준비 코드만 바꿨다. 그래서 교체는 줄 번호가 아니라 **인용한 원문**으로 찾는다.

**Files:**
- Modify: `duty/shifts.py`(전체 교체)
- Create: `duty/services/boards.py`
- Modify: `duty/services/prefs.py`(전체 교체)
- Modify: `duty/views/roster.py`(전체 교체. 바뀌는 곳: import 13~16, `DEPT_ORDER`·`_filters` 53~59, `_shown` 78~80, `_filter_ctx`·`_shift_choices` 83~97, `_cell_context` 105~119, `roster` 130~197, `cell` 200~221, `day` 231~255, `me` 259~268)
- Modify: `duty/views/alarms.py`(import 13~14, `condition_label` 36~40, `_index` 53~55·68)
- Modify: `duty/alarms/forms.py`(import 6, `shifts` 필드 21~22, `__init__` 27~29, `initial_from` 40)
- Modify: `duty/services/alarms.py`(import 18~19, `normalize` 36)
- Modify: `duty/csv_io.py`(import 9, `parse_commute_csv` 77~94, `export_commute_csv` 117~123)
- Modify: `duty/services/collect.py`(import 9, `input_keys`·`shift_names` 새로 만듦, `validate_table` 38~57, `apply_table` 의 삭제 조건, `apply_csv` 89, `export_csv` 93)
- Modify: `duty/views/collect.py`(import 13, `_render_table` 39·50, `table` POST 의 출근조 키)
- Modify: `duty/admin.py`(import 13~14, `DepartmentForm` 의 shifts 필드 20·`__init__` 29·`clean_shifts` 38, `DepartmentAdmin.shift_labels` 52)
- Modify: `duty/views/manage.py`(import 12~15, `_render_detail` 45~56, `change_log` 의 `logs = [` 앞과 `cell` 한 줄)
- Modify(기계적으로 `LEGACY_DEFS` 를 넘김): `duty/alarms/messages.py`, `duty/alarms/schedule.py`, `duty/alarms/plan.py`, `duty/services/calendar.py`, `duty/services/roster.py`
- Create: `tests/test_boards.py`
- Test(허용 변환 d와 새 테스트): `tests/test_shifts.py`
- Test(허용 변환 c와 새 테스트): `tests/test_csv_io.py`
- Test(허용 변환 c): `tests/test_security_stage2.py`
- Test(새 테스트): `tests/test_roster_prefs.py`, `tests/test_views_roster.py`, `tests/test_collect.py`, `tests/test_admin_department.py`, `tests/test_views_manage.py`

**Interfaces:**
- Consumes:
  - Task 1:
    - `duty.models.Board`(code, name, input_mode, admin_group, `Board.InputMode.DIRECT`)
    - `BoardShift`(필드 `key, name, start, end, eligible_shifts(JSON list), eligible_types(JSON list), default_alarm, active`)
    - `Department.board`·`Department.order`, `Period.board`
    - 마이그레이션 0011 이 만든 IT 근무표(code `"it"`)와 정의 14행
    - `duty.shifts.Def`·`KEYS`·`SHIFT_KEYS`·`SLOT_KEYS`·`CELLS`
    - `tests/it_defs.IT_DEFS`
    - conftest `it_board`·`depts`(board=it_board, order 0..3)·`admin_user`(부서 없음)
    - 기존 테스트 회차에 `board=it_board`(허용 변환 a)
  - Task 2: `DutyAssignment`(이 작업은 직접 쓰지 않는다), `services/roster.py` 의 shifts import 모양
- Produces:
  - `duty/shifts.py`(순수 모듈):
    - 상수: `KEYS: list[str]`, `CELLS = KEYS`, `SHIFT_KEYS`, `SLOT_KEYS`, `SLOT_GROUP = "slots"`, `SLOT_GROUP_NAME = "장중관제"`, `SLOT_GROUP_SHORT = "관제"`
    - 그대로 남는 것: `Def`, `DEVELOPER`, `STAFF`, `TARGET_SPREAD`, `MAX_SWAP_ITERATIONS`, `DAY_LABELS`, `weekdays`
    - `slot_cell(i) -> str`, `is_slot_cell(cell) -> bool`, `slot_index(cell) -> int`
    - `by_key(defs) -> dict[str, Def]`
    - `ordered(defs) -> list[Def]`(KEYS 순), `shift_defs(defs) -> list[Def]`(근무조, 시작 시각 순), `slot_defs(defs) -> list[Def]`(관제, 키 순), `display_order(defs) -> list[Def]`(근무조 → 관제)
    - `cell_label(defs, cell) -> str`, `cell_start(defs, cell) -> time`, `cell_end(defs, cell) -> time`
    - `cells_of(defs, keys: list[str]) -> list[str]`(빈 목록 = 전부, KEYS 순)
    - 이행용(뒤 작업이 지움): `COMMUTE_SHIFTS`, `CONTROL_SLOTS`, `SHIFT_TIMES`, `LEGACY_DEFS: list[Def]`(KEYS 순, `IT_DEFS` 와 같음)
  - `duty/services/boards.py`:
    - `it_board() -> Board`
    - `defs(board) -> list[Def]`(꺼진 정의 포함 전부, KEYS 순, JSON 칸은 tuple, `Def.active` 채움). 표시·라벨·`published_days`·알림 문구·캘린더 이름이 쓴다.
    - `active_defs(board) -> list[Def]`(켜진 것만). 새 입력 경로가 쓴다: 입력 표·CSV 열(`collect.shift_names`), 부서 출근조 선택지, 스케줄 선택지(`prefs.clean`·`_shift_choices`), 생성 `slot_defs`, 알림 규칙 선택지·`normalize`·기본 규칙. 1단계에는 꺼진 정의가 없어 결과가 `defs` 와 같다.
    - `board_of(user) -> Board | None`(부서 없으면 None)
  - `duty/services/prefs.py`:
    - `choices(defs) -> dict[str, str]`: 근무조(시작 시각 순) 뒤에, 관제 칸이 있으면 `"slots": "장중관제"`
    - `clean(board, depts, types, shifts) -> tuple[list[str], list[str], list[str]]`(부서는 그 근무표 것만)
    - `resolve(user, get, board, with_view: bool = True) -> dict`
    - 옛 `prefs.SHIFT_CHOICES`·`prefs.SHIFT_KEYS` 는 없앤다
  - `duty/views/roster.py`:
    - `_board(user) -> Board`
    - `_filters(request, board)`, `_filter_ctx(board, defs, depts, types, shifts, history=True)`, `_shift_choices(defs, shifts)`
    - `_cell_context(defs, day, cell, d, depts=None, types=None, members=())`
    - `DEPT_ORDER` 없음
  - `duty/csv_io.py`(names = {키: 열 이름}, 순서 = 열 순서):
    - `parse_commute_csv(raw: bytes, names: dict[str, str]) -> CommuteTable`
    - `export_commute_csv(dates, names: dict[str, str], table) -> bytes`
  - `duty/services/collect.py`: `input_keys(dept) -> list[str]`(부서 출근조 중 켜진 근무조 정의가 있는 키, `dept.shift_keys()` 순서. 입력 표 칸·POST·CSV 열·검증·저장이 모두 쓴다), `shift_names(dept) -> dict[str, str]`({입력 키: 정의 이름}, 같은 순서). `apply_table` 은 꺼진 근무조 정의의 행만 남기고 그 부서의 나머지 행을 지우고 다시 넣는다(부서 출근조에서 뺀 근무조의 행도 지운다).
  - `duty/views/alarms.py`: `condition_label(r, dept_names: dict, shift_names: dict) -> str`
  - `duty/alarms/forms.py`: 모듈 함수 `_shift_choices() -> dict[str, str]`(1단계 IT 고정, Task 8 이 근무표별로 바꾼다)

---

- [ ] **Step 1: tests/test_shifts.py 를 정의 기반으로 바꾸고(허용 변환 d) 새 헬퍼 테스트를 더한다**

  기존 6개 테스트의 기대 값은 그대로 둔다. 상수와 1인자 헬퍼 호출만 `IT_DEFS` 를 넘기는 호출로 바꾼다. `CELLS[...]` 는 `[d.key for d in ordered(IT_DEFS)]` 로 바꾼다. `cells_of([]) == CELLS` 의 기대 값 `CELLS`(KEYS 별칭)는 그대로 둔다. 함수 안의 import 는 파일 위로 올린다. 파일 전체를 아래로 바꾼다.

```python
from datetime import date, time

from duty.shifts import (
    CELLS, LEGACY_DEFS, Def, by_key, cell_end, cell_label, cell_start, cells_of, display_order, is_slot_cell,
    ordered, shift_defs, slot_defs, slot_index, weekdays,
)
from tests.it_defs import IT_DEFS


def test_cells_order_matches_combined_view():
    cells = [d.key for d in ordered(IT_DEFS)]
    assert cells[:3] == ["dawn", "normal", "dinner"]
    assert cells[3:13] == [f"slot{i}" for i in range(10)]
    assert cells[-1] == "night"


def test_cell_labels_roundtrip():
    assert cell_label(IT_DEFS, "slot0") == "08:30~09:30"
    assert cell_label(IT_DEFS, "slot9") == "17:00~18:00"
    assert cell_label(IT_DEFS, "night") == "야간"


def test_slot_helpers():
    assert is_slot_cell("slot3") and not is_slot_cell("dawn")
    assert slot_index("slot7") == 7


def test_weekdays_skip_weekend():
    # 2026-11-06 금, 11-09 월
    assert weekdays(date(2026, 11, 6), date(2026, 11, 10)) == [
        date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 10)
    ]


def test_cell_times():
    assert cell_start(IT_DEFS, "dawn") == time(6, 30) and cell_end(IT_DEFS, "dawn") == time(15, 30)
    assert cell_start(IT_DEFS, "dinner") == time(9, 0) and cell_start(IT_DEFS, "night") == time(13, 30)
    assert cell_start(IT_DEFS, "slot0") == time(8, 30) and cell_end(IT_DEFS, "slot8") == time(17, 0)


def test_cells_of():
    assert cells_of(IT_DEFS, []) == CELLS
    assert cells_of(IT_DEFS, ["night", "dawn"]) == ["dawn", "night"]
    assert cells_of(IT_DEFS, ["slots"]) == [f"slot{i}" for i in range(10)]


# ---- 정의 목록 헬퍼 ----

SLOTS = [f"slot{i}" for i in range(10)]


def test_display_helpers_with_it_defs():
    assert [d.key for d in shift_defs(IT_DEFS)] == ["dawn", "normal", "dinner", "night"]
    assert [d.key for d in slot_defs(IT_DEFS)] == SLOTS
    assert [d.key for d in display_order(IT_DEFS)] == ["dawn", "normal", "dinner", "night", *SLOTS]
    assert by_key(IT_DEFS)["dinner"].name == "석식교대"


def test_helpers_read_only_given_defs():
    # 근무조 3개, 키 순서와 시작 시각 순서가 다른 근무표(관제 없음)
    defs = [Def("dawn", "가운데", time(9), time(18)), Def("night", "늦은", time(11), time(20)),
            Def("dinner", "이른", time(7, 30), time(16, 30))]
    assert [d.name for d in shift_defs(defs)] == ["이른", "가운데", "늦은"]
    assert [d.key for d in display_order(defs)] == ["dinner", "dawn", "night"]
    assert [d.key for d in ordered(defs)] == ["dawn", "dinner", "night"]
    assert slot_defs(defs) == []
    assert cells_of(defs, []) == ["dawn", "dinner", "night"]
    assert cells_of(defs, ["slots"]) == []
    assert cell_label(defs, "dinner") == "이른" and cell_start(defs, "night") == time(11)


def test_legacy_defs_equal_it_defs():
    # 1단계 이행용 LEGACY_DEFS(알림·캘린더가 임시로 씀)가 IT 정의와 한 글자도 다르지 않다
    assert by_key(LEGACY_DEFS) == by_key(IT_DEFS)
    assert [d.key for d in LEGACY_DEFS] == [d.key for d in ordered(IT_DEFS)]
```

  실행: `.venv/bin/pytest -W error tests/test_shifts.py -q`
  기대: 수집 단계에서 `ImportError: cannot import name 'LEGACY_DEFS' from 'duty.shifts'` 로 ERROR 1개.

- [ ] **Step 2: duty/shifts.py 를 정의 기반 헬퍼로 바꾼다**

  Task 1 이 넣은 `SHIFT_KEYS`·`SLOT_KEYS`·`KEYS`·`CELLS`·`Def` 는 값과 주석이 아래와 같다(위치만 옮긴다). 파일 전체를 아래로 바꾼다.

```python
"""칸 키와 근무 정의(Def) 헬퍼. ORM 없음.

칸 키(KEYS)는 고정 목록이고 키 글자가 성격을 정한다: dawn·normal·dinner·night = 근무조, slot* = 장중관제.
이름·시각·자격은 근무표마다 DB(BoardShift)에 있고, 아래 헬퍼는 그 정의 목록(defs)을 인자로 받는다(기본값 없음).
"""

from dataclasses import dataclass
from datetime import date, time, timedelta

SHIFT_KEYS = ("dawn", "normal", "dinner", "night")  # 근무조 키(한 사람 하루 하나)
SLOT_KEYS = tuple(f"slot{i}" for i in range(10))  # 장중관제 칸 키(자동 생성, 칸당 1명)
# 근무표가 쓸 수 있는 키 전부. 순서 = 알림·캘린더 칸 순회 순서(바꾸면 알림 hash 가 달라져 다시 나간다)
KEYS: list[str] = ["dawn", "normal", "dinner", *SLOT_KEYS, "night"]
CELLS = KEYS  # 1단계 동안 남기는 옛 이름
SLOT_GROUP, SLOT_GROUP_NAME, SLOT_GROUP_SHORT = "slots", "장중관제", "관제"  # 장중관제 묶음 키·이름·짧은 이름

DEVELOPER = "개발자"
STAFF = "직원"
TARGET_SPREAD = 2
MAX_SWAP_ITERATIONS = 10000
DAY_LABELS = "월화수목금토일"


@dataclass(frozen=True)
class Def:
    """근무 정의 하나(BoardShift 를 ORM 없이 다루는 값)."""
    key: str
    name: str
    start: time | None
    end: time | None
    eligible_shifts: tuple[str, ...] = ()
    eligible_types: tuple[str, ...] = ()
    default_alarm: bool = False
    active: bool = True  # 꺼진 정의: 새 입력·생성·선택지에서 빠지고(boards.active_defs) 이름 찾기에는 남는다(boards.defs)


def slot_cell(i: int) -> str:
    return f"slot{i}"


def is_slot_cell(cell: str) -> bool:
    return cell.startswith("slot")


def slot_index(cell: str) -> int:
    return int(cell[4:])


def by_key(defs: list[Def]) -> dict[str, Def]:
    return {x.key: x for x in defs}


def ordered(defs: list[Def]) -> list[Def]:
    """KEYS 순(알림·캘린더·published_days 순회 순서)."""
    return sorted(defs, key=lambda x: KEYS.index(x.key))


def shift_defs(defs: list[Def]) -> list[Def]:
    """근무조만, 시작 시각 순."""
    return sorted((x for x in defs if x.key in SHIFT_KEYS), key=lambda x: x.start)


def slot_defs(defs: list[Def]) -> list[Def]:
    """장중관제 칸만, 키 순."""
    return ordered([x for x in defs if is_slot_cell(x.key)])


def display_order(defs: list[Def]) -> list[Def]:
    """화면 순서: 근무조(시작 시각 순) → 장중관제(키 순)."""
    return shift_defs(defs) + slot_defs(defs)


def cell_label(defs: list[Def], cell: str) -> str:
    return by_key(defs)[cell].name


def cell_start(defs: list[Def], cell: str) -> time:
    return by_key(defs)[cell].start


def cell_end(defs: list[Def], cell: str) -> time:
    return by_key(defs)[cell].end


def cells_of(defs: list[Def], keys: list[str]) -> list[str]:
    """스케줄 키(근무조 키, "slots") → 칸 키. 빈 목록 = 전부. KEYS 순."""
    cells = [x.key for x in ordered(defs)]
    if not keys:
        return cells
    return [c for c in cells if (is_slot_cell(c) and SLOT_GROUP in keys) or c in keys]


def weekdays(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


# ---- 1단계 이행용 옛 상수. 변경·생성·통계·알림·캘린더 작업(Task 5·7·8)이 근무표 정의를 받게 되면 지운다 ----

COMMUTE_SHIFTS: dict[str, str] = {  # 순서 = 화면 표시 순서
    "dawn": "새벽",
    "normal": "정상",
    "dinner": "석식교대",
    "night": "야간",
}

_BOTH = ("normal", "dinner")
CONTROL_SLOTS: list[tuple[str, tuple[str, ...]]] = [  # (라벨, 자격 출근조)
    ("08:30~09:30", ("normal",)),
    ("09:30~10:30", _BOTH),
    ("10:30~11:30", _BOTH),
    ("11:30~12:30", _BOTH),
    ("12:30~13:30", _BOTH),
    ("13:30~14:30", _BOTH),
    ("14:30~15:30", _BOTH),
    ("15:30~16:30", _BOTH),
    ("16:30~17:00", _BOTH),
    ("17:00~18:00", ("dinner",)),
]

SHIFT_TIMES: dict[str, tuple[str, str]] = {  # 9시=석식교대, 저녁=야간
    "dawn": ("06:30", "15:30"),
    "normal": ("08:00", "17:00"),
    "dinner": ("09:00", "18:00"),
    "night": ("13:30", "21:30"),
}


def _legacy_defs() -> list[Def]:
    t = time.fromisoformat
    out = [Def(k, n, t(SHIFT_TIMES[k][0]), t(SHIFT_TIMES[k][1]), default_alarm=k in ("dawn", "dinner", "night"))
           for k, n in COMMUTE_SHIFTS.items()]
    for i, (label, allowed) in enumerate(CONTROL_SLOTS):
        a, b = label.split("~")
        out.append(Def(slot_cell(i), label, t(a), t(b), eligible_shifts=allowed, eligible_types=(DEVELOPER,)))
    return ordered(out)


LEGACY_DEFS: list[Def] = _legacy_defs()  # IT 정의와 같다(tests/test_shifts.py 가 IT_DEFS 와 비교)
```

- [ ] **Step 3: 시그니처가 바뀐 헬퍼의 호출부에 `LEGACY_DEFS` 를 기계적으로 넘긴다(이 커밋 안에서 전부 초록이 되게)**

  `views/roster.py`·`views/manage.py` 는 Step 9·16 에서 근무표 정의로 다시 바꾼다. 여기서 넣는 것은 임시다. 이 7개 파일의 shifts import 는 모두 `from ..shifts import ...` 한 줄짜리다. 헬퍼 이름 뒤에 `(` 가 오는 곳은 모두 실제 호출이다(주석·문서 문자열에는 없다).

```bash
F="duty/alarms/messages.py duty/alarms/schedule.py duty/alarms/plan.py duty/services/calendar.py duty/services/roster.py duty/views/roster.py duty/views/manage.py"
sed -i -E 's/\b(cell_label|cell_start|cell_end|cells_of)\(/\1(LEGACY_DEFS, /g' $F
sed -i -E 's/^from \.\.shifts import (.*)$/from ..shifts import LEGACY_DEFS, \1/' $F
git diff --stat
```

  결과로 생기는 import 줄(확인용):
  - messages: `from ..shifts import LEGACY_DEFS, DAY_LABELS, cell_end, cell_label, cell_start, is_slot_cell`
  - schedule: `from ..shifts import LEGACY_DEFS, cell_end, cell_label, cell_start, cells_of, is_slot_cell`
  - plan: `from ..shifts import LEGACY_DEFS, CELLS, cell_start, cells_of`
  - calendar: `from ..shifts import LEGACY_DEFS, CELLS, COMMUTE_SHIFTS, cell_end, cell_label, cell_start, is_slot_cell`
  - services/roster: `from ..shifts import LEGACY_DEFS, CELLS, cell_label, is_slot_cell`(Task 2 상태. Task 2 전이면 끝에 `, slot_cell`)
  - views/roster: `from ..shifts import LEGACY_DEFS, CELLS, COMMUTE_SHIFTS, DAY_LABELS, DEVELOPER, STAFF, cell_label, is_slot_cell`
  - views/manage: `from ..shifts import LEGACY_DEFS, CONTROL_SLOTS, cell_label`

  호출부는 이렇게 바뀐다. 다른 글자는 바뀌지 않는다.
  - `cell_label(cell)` → `cell_label(LEGACY_DEFS, cell)`
  - `cells_of(shifts)` → `cells_of(LEGACY_DEFS, shifts)`
  - `cell_start(c).hour` → `cell_start(LEGACY_DEFS, c).hour`

  확인: `grep -rnP "\b(cell_label|cell_start|cell_end|cells_of)\((?!LEGACY_DEFS|defs)" duty --include=*.py | grep -v "^duty/shifts.py"`
  기대: 결과 없음(`(?!` 는 `-P` 에서만 된다. `-E` 와 같이 쓰지 않는다).

- [ ] **Step 4: 통과 확인과 커밋**

  실행: `.venv/bin/pytest -W error tests/test_shifts.py tests/test_alarm_plan.py tests/test_alarm_schedule.py tests/test_change_notice.py tests/test_calendar_feed.py -q`
  기대: 전부 통과. 알림 문구 테스트가 그대로 통과하므로 `LEGACY_DEFS` 로 만든 문구가 지금과 같다.

  실행: `.venv/bin/pytest -W error -q`
  기대: `796 passed`(Task 2 끝 793 + 새 3), 경고 0.

```bash
git add duty/shifts.py duty/alarms/messages.py duty/alarms/schedule.py duty/alarms/plan.py duty/services/calendar.py duty/services/roster.py duty/views/roster.py duty/views/manage.py tests/test_shifts.py
git commit -m "feat: shifts 헬퍼가 근무 정의 목록을 인자로 받게(알림·캘린더는 이행용 LEGACY_DEFS)"
```

- [ ] **Step 5: boards 서비스 실패 테스트를 쓴다**

  Create `tests/test_boards.py`:

```python
from duty.models import BoardShift
from duty.services import boards
from duty.shifts import KEYS, by_key
from tests.it_defs import IT_DEFS


def test_it_board_defs_match_it_definitions(it_board):
    assert boards.it_board() == it_board
    got = boards.defs(it_board)
    assert [d.key for d in got] == KEYS
    assert by_key(got) == by_key(IT_DEFS)


def test_defs_include_inactive_and_use_tuples(it_board):
    BoardShift.objects.filter(board=it_board, key="night").update(active=False)
    got = by_key(boards.defs(it_board))
    assert got["night"].name == "야간" and not got["night"].active  # 꺼도 지난 행·기록의 이름은 찾는다
    assert "night" not in [x.key for x in boards.active_defs(it_board)]  # 새 입력 선택지에서는 빠진다
    assert got["slot0"].eligible_shifts == ("normal",)
    assert got["slot0"].eligible_types == ("개발자",)


def test_board_of(make_member, admin_user, it_board):
    assert boards.board_of(make_member("가")) == it_board
    assert boards.board_of(admin_user) is None  # 부서 없는 계정
```

  실행: `.venv/bin/pytest -W error tests/test_boards.py -q`
  기대: 수집 단계에서 `ImportError: cannot import name 'boards' from 'duty.services'` 로 ERROR 1개.

- [ ] **Step 6: duty/services/boards.py 를 만든다**

```python
"""근무표(Board)와 근무 정의 읽기. 1단계는 IT 근무표 하나."""
from ..models import Board, BoardShift
from ..shifts import Def, ordered


def it_board() -> Board:
    return Board.objects.get(code="it")


def defs(board: Board) -> list[Def]:
    """그 근무표의 근무 정의 전부(꺼진 것 포함: 표시·라벨·지난 행·기록의 이름을 찾는다). KEYS 순."""
    return ordered([
        Def(s.key, s.name, s.start, s.end, tuple(s.eligible_shifts), tuple(s.eligible_types), s.default_alarm, s.active)
        for s in BoardShift.objects.filter(board=board)
    ])


def active_defs(board: Board) -> list[Def]:
    """켜진 정의만(설계 4.3 '끄면 새 입력에서만 빠진다'): 입력 표·CSV 열, 부서 출근조·스케줄·알림 규칙 선택지, 생성."""
    return [x for x in defs(board) if x.active]


def board_of(user) -> Board | None:
    dept = getattr(user, "department", None)  # 익명·부서 없는 계정은 근무표가 없다
    return dept.board if dept else None
```

  실행: `.venv/bin/pytest -W error tests/test_boards.py -q`
  기대: `3 passed`.

  실행: `.venv/bin/pytest -W error -q`
  기대: `799 passed`(796 + 새 3), 경고 0.

```bash
git add duty/services/boards.py tests/test_boards.py
git commit -m "feat: 근무표 정의 읽기 서비스(boards.it_board·defs·board_of)"
```

- [ ] **Step 7: 스케줄 선택지·근무표 화면 라벨·근무표별 부서 필터의 실패 테스트를 먼저 쓴다**

  `tests/test_roster_prefs.py`: 파일 위 `from duty.models import ...` 줄 바로 아래에 세 줄을 더한다.

```python
from duty.services import prefs
from duty.shifts import is_slot_cell
from tests.it_defs import IT_DEFS
```

  그리고 파일 끝에 테스트를 더한다.

```python
def test_schedule_choices_follow_definitions():
    assert prefs.choices(IT_DEFS) == {
        "dawn": "새벽", "normal": "정상", "dinner": "석식교대", "night": "야간", "slots": "장중관제",
    }
    assert list(prefs.choices(IT_DEFS)) == ["dawn", "normal", "dinner", "night", "slots"]  # 화면 순서
    no_slots = [d for d in IT_DEFS if not is_slot_cell(d.key)]
    assert list(prefs.choices(no_slots)) == ["dawn", "normal", "dinner", "night"]  # 관제 없는 근무표엔 묶음 없음
```

  `tests/test_views_roster.py`:
  - 2번째 줄 `from datetime import date` 를 `from datetime import date, time` 으로 바꾼다.
  - `from duty.models import ...` 줄(Task 2 뒤에는 `from duty.models import Commute, DutyAssignment, Period`) 바로 아래에 `from duty.models import Board, BoardShift, Department, User` 한 줄을 더한다.
  - 파일 끝에 아래를 더한다. 둘째 테스트는 지적 8·12를 고정한다. 부서 필터는 그 근무표 부서만 `order` 순으로 보인다. 다른 근무표 부서 사람에게는 그 근무표의 부서·정의가 보인다. 근무 변경 창 To 후보에도 다른 근무표 사람이 나오지 않는다(마지막 assert).

```python
def test_labels_and_cells_come_from_board_definitions(client, world, it_board):
    a, _ = world
    BoardShift.objects.filter(board=it_board, key="dinner").update(name="늦은조")
    BoardShift.objects.filter(board=it_board, key="slot0").update(name="08:31~09:30")
    client.force_login(a)
    week = client.get(f"/?view=week&date={D}").content.decode()
    assert "늦은조" in week and "08:31" in week
    day = client.get(f"/day/{D}/").content.decode()
    assert "<strong>늦은조</strong>" in day and "<strong>08:31~09:30</strong>" in day
    assert "석식교대" not in day
    assert "늦은조" in client.get("/me/").content.decode()  # 스케줄 선택지
    assert client.get(f"/cell/{D}/lunch/").status_code == 404  # 정의에 없는 칸


def _dept_codes(body: str) -> list[str]:
    return re.findall(r'name="dept" value="(\w+)"', body)


def test_views_use_own_board_departments_and_definitions(client, world, it_board):
    a, _ = world
    ops = Board.objects.create(code="ops", name="운영팀", input_mode=Board.InputMode.DIRECT)
    BoardShift.objects.create(board=ops, key="dawn", name="이른조", start=time(7), end=time(16))
    ops_dept = Department.objects.create(code="OPS", name="운영부서", shifts="dawn", board=ops)
    Department.objects.filter(code="UI").update(order=-1)
    client.force_login(a)
    assert _dept_codes(client.get("/").content.decode()) == ["UI", "MEMS", "TMCH", "MD"]  # 그 근무표 부서만, order 순
    assert _dept_codes(client.get(f"/day/{D}/").content.decode()) == ["UI", "MEMS", "TMCH", "MD"]
    Department.objects.create(code="AA", name="가", shifts="normal", board=it_board)  # 순서 칸을 비운 새 부서
    assert _dept_codes(client.get("/").content.decode())[-1] == "AA"  # 기본 99라 맨 뒤(옛 DEPT_ORDER 밖 부서와 같다)
    o = User.objects.create_user("OPS001", name="운영", department=ops_dept, part="", type="직원")
    client.force_login(o)
    week = client.get("/").content.decode()
    assert _dept_codes(week) == ["OPS"] and "이른조" in week and "석식교대" not in week
    me = client.get("/me/").content.decode()
    assert "이른조" in me and "석식교대" not in me
    assert client.get(f"/cell/{D}/dinner/").status_code == 404  # 운영팀 정의에 없는 칸
    client.force_login(a)
    assert "OPS001" not in client.get(f"/cell/{D}/normal/").content.decode()  # IT 칸 To 후보에 운영팀 사람 없음
```

  실행: `.venv/bin/pytest -W error tests/test_roster_prefs.py tests/test_views_roster.py -q -k "choices or board_definitions or own_board"`
  기대: `3 failed`.
  - `test_schedule_choices_follow_definitions`: `AttributeError: module 'duty.services.prefs' has no attribute 'choices'`
  - `test_labels_and_cells_come_from_board_definitions`: 첫 assert(`"늦은조" in week`)에서 실패한다. 칸 이름이 아직 `LEGACY_DEFS` 에서 오기 때문이다.
  - `test_views_use_own_board_departments_and_definitions`: `assert ['MEMS', 'TMCH', 'MD', 'UI', 'OPS'] == ['UI', 'MEMS', 'TMCH', 'MD']` 로 실패한다(지금은 `DEPT_ORDER` 정렬, 모든 부서).

- [ ] **Step 8: prefs 를 정의 기반으로 바꾸고, `SHIFT_CHOICES`·`prefs.SHIFT_KEYS` 를 쓰던 알림 쪽을 옮긴다**

  이 단계가 끝나도 `views/roster.py` 는 아직 옛 `prefs` API를 부른다. 그래서 테스트는 Step 9까지 끝낸 뒤 Step 10에서 돌린다.

  `duty/services/prefs.py` 전체:

```python
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
```

  `duty/services/alarms.py`. 알림 작업(Task 8) 전까지는 IT 근무표 하나를 쓴다. 순서(dawn·normal·dinner·night·slots)가 옛 `SHIFT_KEYS` 와 같아서 정규화 결과와 보고서 hash 는 그대로다.
  - 18~19줄 `from . import alarm_settings` / `from .prefs import SHIFT_KEYS` 두 줄을 아래 한 줄로 바꾼다.

```python
from . import alarm_settings, boards, prefs
```

  - `normalize` 의 `    s = pick(shifts, SHIFT_KEYS)` 를 아래로 바꾼다.

```python
    s = pick(shifts, list(prefs.choices(boards.active_defs(boards.it_board()))))  # 1단계: IT 하나. 알림 작업(Task 8)에서 규칙의 근무표로
```

  `duty/alarms/forms.py`:
  - 6줄 `from ..services.prefs import SHIFT_CHOICES` 를 `from ..services import boards, prefs` 로 바꾼다.
  - `class RuleForm(forms.Form):` 바로 위(빈 줄 두 개 사이)에 아래 함수를 더한다.

```python
def _shift_choices() -> dict[str, str]:
    return prefs.choices(boards.active_defs(boards.it_board()))  # 1단계: IT 하나. 알림 작업(Task 8)에서 규칙의 근무표로
```

  - 21~22줄 `shifts` 필드를 아래 한 줄로 바꾼다.

```python
    shifts = forms.MultipleChoiceField(label="스케줄", required=False, widget=forms.CheckboxSelectMultiple)
```

  - `__init__` 을 아래로 바꾼다.

```python
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["shifts"].choices = list(_shift_choices().items())
        self.fields["depts"].choices = list(Department.objects.values_list("code", "name"))
```

  - `initial_from` 의 `shifts=rule.shifts or list(SHIFT_CHOICES),` 를 `shifts=rule.shifts or list(_shift_choices()),` 로 바꾼다.

  `duty/views/alarms.py`:
  - 13~14줄 `from ..services import alarm_settings, alarms, calendar` / `from ..services.prefs import SHIFT_CHOICES` 두 줄을 아래 한 줄로 바꾼다.

```python
from ..services import alarm_settings, alarms, boards, calendar, prefs
```

  - `condition_label` 을 아래로 바꾼다.

```python
def condition_label(r, dept_names: dict, shift_names: dict) -> str:
    s = f"스케줄: {_names(r.shifts, shift_names)}"
    if r.kind == "personal":
        return s
    return f"부서: {_names(r.depts, dept_names)} / 유형: {_names(r.types, {})} / {s}"
```

  - `_index` 의 첫 세 줄(`dept_names = ...`, `rules = [`, `{"r": r, ... condition_label(r, dept_names),`)을 아래로 바꾼다.

```python
    dept_names = dict(Department.objects.values_list("code", "name"))
    shift_names = prefs.choices(boards.defs(boards.it_board()))  # 1단계: IT 하나. 알림 작업(Task 8)에서 규칙의 근무표로
    rules = [
        {"r": r, "timing": timing_label(r), "cond": condition_label(r, dept_names, shift_names),
```

  - 같은 함수의 `"shift_choices": list(SHIFT_CHOICES.items()),` 를 `"shift_choices": list(shift_names.items()),` 로 바꾼다.

- [ ] **Step 9: views/roster.py 를 근무표 정의로 그린다(`_board` 하나, `DEPT_ORDER` 삭제)**

  파일 전체를 아래로 바꾼다. 바뀌는 곳은 다음과 같다. 나머지(`_item`·`_items`·`_latest`·`_lines`·`_member`·`_filtered`·`_keeper`·`LOW/HIGH`·`_month_shift`·`_neighbor`)는 글자 그대로다.
  - import: `boards` 를 더하고, `LEGACY_DEFS`·`CELLS`·`COMMUTE_SHIFTS` 를 뺀다.
  - `DEPT_ORDER` 를 지우고 `_board` 를 둔다.
  - `_filters`·`_filter_ctx`·`_shift_choices`·`_cell_context` 가 board·defs 를 받는다.
  - `_active_members(board, depts, types)`: 근무 변경 창 To 후보를 그 근무표 부서의 재직자로 좁힌다(설계 6.4·7절, Task 5 `_check_candidate(board, m)` 와 같은 규칙). 부서 필터가 비어 있어도 다른 근무표 사람은 나오지 않는다.
  - 4개 뷰 첫머리에서 `board = _board(request.user)`·`defs = boards.defs(board)` 를 정한다.

  `published_days`·`find_day`·`member_schedule`·`changes.exchange` 호출은 지금 그대로다. 근무표 인자는 Task 5 가 이미 있는 `board` 변수로 넘긴다. `perms.is_admin(...)` 두 줄은 Task 4 가 바꾼다.

```python
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from .. import perms
from ..csv_io import split_names
from ..errors import DutyError
from ..models import Department, User
from ..services import boards, changes, prefs
from ..services.roster import find_day, member_schedule, published_days
from ..shifts import (
    DAY_LABELS, DEVELOPER, SLOT_GROUP, STAFF, by_key, cell_label, display_order, is_slot_cell, ordered, shift_defs,
    slot_defs,
)
from .common import date_param, safe_next


def _item(label: str, names: list[str], removed: bool = False) -> dict:
    """라벨(A, A>B>C, +B)을 이름 토큰으로 나눈다. 마지막 이름 앞은 취소선, hl은 검색어 번호(1..3)."""
    parts = [p.strip().lstrip("+") for p in label.split(">")]
    tokens = [
        {"name": n, "struck": removed or k < len(parts) - 1, "hl": next((i for i, q in enumerate(names, 1) if q == n), 0)}
        for k, n in enumerate(parts)
    ]
    return {"tokens": tokens, "changed": len(parts) > 1 or label.startswith("+") or removed}


def _items(labels: list[str], names: list[str], removed: bool = False) -> list[dict]:
    return [_item(lb, names, removed) for lb in labels]


def _latest(labels: list[str]) -> list[str]:
    """변경 내역을 숨길 때: 'A>B>C'·'+C' → 'C'(지금 근무하는 사람만)."""
    return [lb.split(">")[-1].strip().lstrip("+") for lb in labels]


def _lines(labels: list[str], names: list[str], removed: bool = False, per_line: int = 3) -> list[list[dict]]:
    items = _items(labels, names, removed)
    return [items[i:i + per_line] for i in range(0, len(items), per_line)]


def _member(username: str | None) -> User | None:
    if not username:
        return None
    m = User.objects.filter(username=username).first()
    if m is None:
        raise DutyError("없는 멤버입니다.")  # 조작된 코드가 '삭제'로 해석되지 않게
    return m


def _board(user):
    """이 사용자가 보는 근무표. 1단계: 내 부서의 근무표, 없으면 IT(근무표 고르기는 2단계). 모든 뷰가 이것 하나를 쓴다."""
    return boards.board_of(user) or boards.it_board()


def _filters(request, board) -> tuple[list[str], list[str]]:
    """?dept=MEMS&dept=UI, ?type=직원 → 유효한 값만. 빈 목록 = 전체."""
    d, t, _ = prefs.clean(board, request.GET.getlist("dept"), request.GET.getlist("type"), [])
    return d, t


def _filtered(qs, depts: list[str], types: list[str]):
    qs = qs.filter(department_id__in=depts) if depts else qs
    return qs.filter(type__in=types) if types else qs


def _keeper(depts: list[str], types: list[str]):
    """라벨의 현재(마지막) 사람이 부서·유형 필터를 모두 통과하면 True인 함수."""
    info = {n: (d, t) for n, d, t in User.objects.values_list("name", "department_id", "type")} if depts or types else {}

    def keep(label: str) -> bool:
        d, t = info.get(label.split(">")[-1].strip().lstrip("+"), (None, None))
        return (not depts or d in depts) and (not types or t in types)

    return keep


def _shown(shifts: list[str]):
    """칸 키가 스케줄 필터를 통과하는지. 빈 목록 = 전체, 관제 10칸은 'slots' 하나로."""
    return lambda k: not shifts or (SLOT_GROUP if is_slot_cell(k) else k) in shifts


def _filter_ctx(board, defs, depts, types, shifts, history: bool = True) -> dict:
    return {
        "history": history,
        "filter_on": bool(depts or types or shifts),
        "type_choices": [{"code": t, "name": t, "checked": not types or t in types} for t in (STAFF, DEVELOPER)],
        "dept_choices": [
            {"code": d.code, "name": d.name, "checked": not depts or d.code in depts}
            for d in Department.objects.filter(board=board).order_by("order", "code")  # 그 근무표 부서만
        ],
        "shift_choices": _shift_choices(defs, shifts),
    }


def _shift_choices(defs, shifts) -> list[dict]:
    on = [x for x in defs if x.active]  # 선택지는 켜진 정의만(prefs.clean 의 boards.active_defs 와 같은 범위)
    return [{"code": c, "name": n, "checked": not shifts or c in shifts} for c, n in prefs.choices(on).items()]


def _active_members(board, depts: list[str] | None = None, types: list[str] | None = None):
    """근무 변경 창 To 후보: 그 근무표 부서의 재직자(필터가 비어도 다른 근무표 사람은 빠진다)."""
    qs = User.objects.roster().filter(department__board=board).select_related("department").order_by("name")
    return list(_filtered(qs, depts or [], types or []))


def _cell_context(defs, day, cell: str, d, depts: list[str] | None = None, types: list[str] | None = None, members=()):
    current = day.members[cell] if day else []
    qs = User.objects.filter(name__in=current).order_by("name")
    # To 목록에 그날 같은 종류 근무를 붙인다(맞교환이 기본이라 무엇과 바뀌는지 보이게)
    kinds = [x.key for x in ordered(defs) if is_slot_cell(x.key) == is_slot_cell(cell)]
    where = {}
    for k in kinds:
        for n in (day.members[k] if day else []):
            where[n] = f"{where[n]}·{cell_label(defs, k)}" if n in where else cell_label(defs, k)  # 관제 여러 칸이면 모두
    return {
        "d": d, "cell": cell, "label": cell_label(defs, cell), "slot": is_slot_cell(cell),
        "current_members": list(_filtered(qs, depts or [], types or [])),
        "to_options": [{"username": m.username, "name": m.name, "dept": m.department.name,
                        "where": where.get(m.name, "근무 없음")} for m in members if m.name not in current],
    }


LOW, HIGH = date(2000, 1, 1), date(2099, 12, 31)


def _month_shift(d: date, step: int) -> date:
    m = d.month - 1 + step
    return date(d.year + m // 12, m % 12 + 1, 1)


@login_required
def roster(request):
    names = split_names(request.GET.get("q", ""))[:3]  # 구버전 ?q=a,b,c
    names = [request.GET.get(f"q{i}", "").strip() or (names[i - 1] if i <= len(names) else "") for i in (1, 2, 3)]
    today, admin = perms.today(), perms.is_admin(request.user)
    board = _board(request.user)
    defs = boards.defs(board)
    pref = prefs.resolve(request.user, request.GET, board)
    view, depts, types, shifts, history = pref["view"], pref["depts"], pref["types"], pref["shifts"], pref["history"]
    show = (lambda x: x) if history else _latest
    anchor = date_param(request, "date") or today
    if not LOW <= anchor <= HIGH:  # 극단 날짜의 overflow 방지
        anchor = today
    keep, shown = _keeper(depts, types), _shown(shifts)

    def link(v: str, d: date) -> str | None:
        if not LOW <= d <= HIGH:
            return None  # 범위 밖으로 가는 링크는 만들지 않는다
        params = {"view": v, "date": d.isoformat(), **{f"q{i}": n for i, n in enumerate(names, 1) if n}, "dept": depts, "type": types, "shift": shifts}
        return "?" + urlencode(params, doseq=True)

    if view == "week":
        monday = anchor - timedelta(days=anchor.weekday())
        weeks = [[monday + timedelta(days=i) for i in range(5)]]
        prev_d, next_d = monday - timedelta(days=7), monday + timedelta(days=7)
        title = f"{monday:%Y-%m-%d} ~ {monday + timedelta(days=4):%m-%d}"
    else:
        first = anchor.replace(day=1)
        cur = first - timedelta(days=first.weekday())
        weeks = []
        last = _month_shift(first, 1) - timedelta(days=1)
        while cur <= last:
            if cur + timedelta(days=4) >= first:  # 주말만 걸친 앞 주는 건너뜀
                weeks.append([cur + timedelta(days=i) for i in range(5)])
            cur += timedelta(days=7)
        prev_d, next_d = _month_shift(first, -1), _month_shift(first, 1)
        title = f"{first.year}년 {first.month}월"
    first_day, last_day = weeks[0][0], weeks[-1][-1]
    by_date = {d.date: d for d in published_days(first_day, last_day)}

    def day_cells(d: date) -> dict:
        found = by_date.get(d)
        return {
            x.key: {
                "key": x.key, "slot": is_slot_cell(x.key), "label": x.name,
                "lines": _lines(show([lb for lb in found.cells[x.key].labels if keep(lb)]), names) if found else [],
                "removed": _lines([lb for lb in found.cells[x.key].removed if keep(lb)], names, True) if found and history else [],
            }
            for x in display_order(defs) if shown(x.key)
        }

    def day_info(d: date) -> dict:
        cells = day_cells(d)
        other = view == "month" and d.month != anchor.month
        return {
            "date": d, "is_today": d == today, "other": other, "empty": d not in by_date,
            "edit": (admin or d >= today) and not other and d in by_date,  # 배포된 근무표가 있는 날만
            "commute": [cells[x.key] for x in shift_defs(defs) if x.key in cells],
            "duty": [{"time": cells[x.key]["label"][:5], **cells[x.key]} for x in slot_defs(defs) if x.key in cells],
        }

    days = [[day_info(d) for d in w] for w in weeks]
    ctx = {
        "view": view, "title": title, "names": names, "date": anchor, "today_link": (link(view, today) or f"?view={view}&date={today.isoformat()}") + "#today",
        "prev": link(view, prev_d), "next": link(view, next_d),
        "week_link": link("week", anchor), "month_link": link("month", anchor),
        "filter_qs": "".join("&" + urlencode({k: v}) for k, vs in (("dept", depts), ("type", types)) for v in vs),
    }
    ctx.update(_filter_ctx(board, defs, depts, types, shifts, history), weeks=days)
    return render(request, "duty/roster.html", ctx)


@login_required
def cell(request, d, cell):
    board = _board(request.user)
    defs = boards.defs(board)
    if cell not in by_key(defs):
        raise Http404
    fallback = reverse("day", args=[d])
    if request.method == "POST":
        try:
            # "+"·"-" = 없음(넣기만·빼기만). 기본은 둘 다 고른 맞교환
            before, after = request.POST.get("before"), request.POST.get("after")
            result = changes.exchange(request.user, d, cell, _member(None if before == "+" else before),
                                      _member(None if after == "-" else after))
        except DutyError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, "변경했습니다.")
            for w in result:
                messages.warning(request, w)
        return redirect(safe_next(request, fallback))
    depts, types = _filters(request, board)
    ctx = _cell_context(defs, find_day(d), cell, d, depts, types, _active_members(board, depts, types))
    ctx.update(next=safe_next(request, fallback))
    return render(request, "duty/_cell_form.html", ctx)


def _neighbor(d, step: int):
    d = d + timedelta(days=step)
    while d.weekday() >= 5:
        d += timedelta(days=step)
    return d


@login_required
def day(request, d):
    board = _board(request.user)
    defs = boards.defs(board)
    pref = prefs.resolve(request.user, request.GET, board, with_view=False)
    depts, types, shifts, history = pref["depts"], pref["types"], pref["shifts"], pref["history"]
    show = (lambda x: x) if history else _latest
    found = find_day(d)
    editable = perms.is_admin(request.user) or d >= perms.today()
    members = _active_members(board, depts, types)
    keep, shown = _keeper(depts, types), _shown(shifts)
    sections = []
    if found:
        for k in filter(shown, [x.key for x in display_order(defs)]):  # 출근조 먼저, 관제는 뒤에 묶어서
            ctx = _cell_context(defs, found, k, d, depts, types, members)
            ctx.update(
                next=request.path,
                items=_items(show([x for x in found.cells[k].labels if keep(x)]), []),
                removed_items=_items([x for x in found.cells[k].removed if keep(x)], [], True) if history else [],
            )
            sections.append(ctx)
    qs = "?" + urlencode({"f": 1, "dept": depts, "type": types, "shift": shifts}, doseq=True)
    return render(request, "duty/day.html", {
        "d": d, "weekday": DAY_LABELS[d.weekday()], "found": found, "sections": sections,
        "editable": editable, "prev": _neighbor(d, -1), "next_day": _neighbor(d, 1),
        "qs": qs, **_filter_ctx(board, defs, depts, types, shifts, history),
    })



@login_required
def me(request):
    member = request.user if request.user.department_id else None
    board = _board(request.user)
    _, _, shifts = prefs.clean(board, [], [], request.GET.getlist("shift"))
    items = member_schedule(member, perms.today(), _shown(shifts)) if member else []
    return render(request, "duty/me.html", {
        "member": member,
        "shift_choices": _shift_choices(boards.defs(board), shifts),
        "items": [{"date": d, "weekday": DAY_LABELS[d.weekday()], "labels": labels, "today": d == perms.today()} for d, labels in items],
    })
```

  IT 정의의 화면 순서는 지금 `CELLS`·`COMMUTE_SHIFTS` 순서와 같다. 근무조 dawn·normal·dinner·night(시작 06:30·08:00·09:00·13:30) 다음에 slot0~9가 온다(Step 1 `test_display_helpers_with_it_defs`). `day_cells` 의 dict 순서는 바뀌지만, 템플릿은 `commute`·`duty` 목록만 읽는다. 부서 필터 순서는 conftest `depts` 의 order(0..3)와 마이그레이션 0011 의 order(MEMS 0, TMCH 1, MD 2, UI 3)가 옛 `DEPT_ORDER` 와 같아서 바뀌지 않는다.

- [ ] **Step 10: 통과 확인과 커밋**

  실행: `grep -rn "SHIFT_CHOICES\|prefs\.SHIFT_KEYS\|from \.prefs import SHIFT_KEYS" duty`
  기대: 결과 없음(`duty/shifts.py` 의 `SHIFT_KEYS` 는 다른 상수라 이 검색에 걸리지 않는다).

  실행: `grep -n "LEGACY_DEFS\|CELLS\|COMMUTE_SHIFTS\|DEPT_ORDER" duty/views/roster.py`
  기대: 결과 없음.

  실행: `.venv/bin/pytest -W error tests/test_roster_prefs.py tests/test_views_roster.py tests/test_roster.py tests/test_views_alarms.py tests/test_alarm_models.py tests/test_views_calendar.py -q`
  기대: 전부 통과(Step 7의 세 테스트 포함).

  실행: `.venv/bin/pytest -W error -q`
  기대: `802 passed`, 경고 0.

```bash
git add duty/services/prefs.py duty/services/alarms.py duty/alarms/forms.py duty/views/alarms.py duty/views/roster.py tests/test_roster_prefs.py tests/test_views_roster.py
git commit -m "feat: 근무표 화면이 보는 근무표 하나(_board)의 정의·부서로 칸 이름·순서·필터를 그린다"
```

- [ ] **Step 11: CSV 열 이름 실패 테스트를 쓰고 기존 테스트를 허용 변환 c로 바꾼다**

  `tests/test_csv_io.py`:
  - 5~7줄(`from duty.csv_io import ...`, 빈 줄, `KEYS = [...]`)을 아래로 바꾼다. 기존 테스트 본문의 `KEYS` 사용과 단언은 그대로 둔다. dict 를 돌면 키가 같은 순서로 나오기 때문이다.

```python
from duty.csv_io import CsvInvalid, export_commute_csv, parse_commute_csv, parse_date, split_names
from duty.shifts import by_key
from tests.it_defs import IT_DEFS


def _names(keys: list[str]) -> dict[str, str]:
    """IT 정의의 {키: 이름}(CSV 열 이름)."""
    return {k: by_key(IT_DEFS)[k].name for k in keys}


KEYS = _names(["dawn", "normal", "dinner", "night"])
```

  - `test_ui_without_dawn_column_is_fine` 의 `parse_commute_csv(raw, ["normal", "dinner", "night"])` 를 `parse_commute_csv(raw, _names(["normal", "dinner", "night"]))` 로 바꾼다.
  - 끝에 새 테스트를 더한다.

```python
def test_columns_follow_given_names():
    names = {"dawn": "이른조", "night": "늦은조"}
    raw = export_commute_csv([date(2026, 11, 9)], names, {date(2026, 11, 9): {"dawn": ["가"]}})
    assert raw.decode("utf-8-sig").splitlines()[0] == "date,day,이른조,늦은조"
    assert parse_commute_csv(raw, names)[date(2026, 11, 9)] == {"dawn": ["가"], "night": []}
```

  (`names` 의 이름이 서로 다르다는 전제다. 한 근무표 안에서 이름이 겹치면 DB 가 막는다(Task 1 `boardshift_one_per_name`). 그래서 csv_io 는 이름 겹침을 따로 검사하지 않는다.)

  `tests/test_security_stage2.py`:
  - 14줄 `from duty.models import CalendarFeed, PushAlarmSubscription, TelegramAlarmProfile` 바로 아래에 두 줄을 더한다.

```python
from duty.shifts import by_key
from tests.it_defs import IT_DEFS
```

  - `test_csv_error_cap` 의 `parse_commute_csv(raw, ["normal"])` 를 `parse_commute_csv(raw, {"normal": by_key(IT_DEFS)["normal"].name})` 로 바꾼다. 단언은 그대로 둔다.

  `tests/test_collect.py`:
  - 8줄 `from duty.models import Period` 를 `from duty.models import BoardShift, Commute, Period` 로 바꾼다.
  - 끝에 새 테스트 둘을 더한다. 둘째는 꺼진 근무조 방침(설계 6.2)을 고정한다: 머리글·칸·CSV 열에서 빠지고, 그 근무조의 기존 배정은 저장 뒤에도 남는다.

```python
def test_csv_columns_follow_board_definitions(setup, it_board):
    p, dept, user = setup
    assert collect.shift_names(dept) == {"dawn": "새벽", "normal": "정상", "dinner": "석식교대", "night": "야간"}
    BoardShift.objects.filter(board=it_board, key="dinner").update(name="늦은조")
    assert collect.export_csv(p, dept).decode("utf-8-sig").splitlines()[0] == "date,day,새벽,정상,늦은조,야간"
    raw = 'date,새벽,정상,늦은조,야간\n2026-11-09,가,,나,\n'.encode()
    assert collect.apply_csv(user, p, dept, raw) == 2


def test_inactive_shift_left_out_of_input_but_kept_on_save(setup, it_board, client):
    p, dept, user = setup
    collect.apply_csv(user, p, dept, 'date,새벽,정상,석식교대,야간\n2026-11-09,가,나,,\n'.encode())
    BoardShift.objects.filter(board=it_board, key="dawn").update(active=False)
    assert collect.input_keys(dept) == ["normal", "dinner", "night"] == list(collect.shift_names(dept))
    assert collect.export_csv(p, dept).decode("utf-8-sig").splitlines()[0] == "date,day,정상,석식교대,야간"
    client.force_login(user)
    assert 'name="c_2026-11-09_dawn"' not in client.get(f"/collect/{p.pk}/MEMS/").content.decode()  # 입력 칸 없음
    collect.apply_csv(user, p, dept, 'date,정상,석식교대,야간\n2026-11-09,다,,\n'.encode())
    # 입력 키(정상·석식교대·야간)의 행만 바뀌고, 꺼진 새벽의 기존 배정은 지워지지 않는다
    assert dict(Commute.objects.filter(period=p).values_list("member__name", "shift")) == {"가": "dawn", "다": "normal"}
    # 꺼진 근무조에 남은 사람을 그날 켜진 근무조에 다시 넣으면 검증 오류(하루 한 출근 제약에 걸리기 전에)
    with pytest.raises(CsvInvalid) as e:
        collect.apply_csv(user, p, dept, 'date,정상,석식교대,야간\n2026-11-09,가,,\n'.encode())
    assert any("이미 사용하지 않는 근무조에 배정돼 있습니다" in err.reason for err in e.value.errors)
```

  실행: `.venv/bin/pytest -W error tests/test_csv_io.py tests/test_collect.py tests/test_security_stage2.py -q`
  기대: `3 failed, 37 passed`.
  - `test_columns_follow_given_names`: `AssertionError: assert 'date,day,새벽,야간' == 'date,day,이른조,늦은조'`
  - `test_csv_columns_follow_board_definitions`: `AttributeError: module 'duty.services.collect' has no attribute 'shift_names'`
  - `test_inactive_shift_left_out_of_input_but_kept_on_save`: `AttributeError: module 'duty.services.collect' has no attribute 'input_keys'`

- [ ] **Step 12: csv_io 와 collect 를 정의 이름으로 바꾼다**

  `duty/csv_io.py`:
  - 9줄 `from .shifts import COMMUTE_SHIFTS, DAY_LABELS` 를 `from .shifts import DAY_LABELS` 로 바꾼다.
  - 77줄 `def parse_commute_csv(raw: bytes, shift_keys: list[str]) -> CommuteTable:` 를 아래 두 줄로 바꾼다.

```python
def parse_commute_csv(raw: bytes, names: dict[str, str]) -> CommuteTable:
    """names = {출근조 키: 열 이름(근무 정의 이름)}. 열 제목은 줄바꿈·'(' 앞까지만 맞춘다."""
```

  - 89~90줄을 아래 한 줄로 바꾼다(91줄 `if label in header:` 부터는 그대로).
    - 지금: `    for key in shift_keys:` / `        label = COMMUTE_SHIFTS[key]`

```python
    for key, label in names.items():
```

  - `export_commute_csv` 전체(117~124줄)를 아래로 바꾼다.

```python
def export_commute_csv(dates: list[date], names: dict[str, str], table: CommuteTable) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "day", *names.values()])
    for d in dates:
        day = table.get(d, {})
        w.writerow([d.isoformat(), DAY_LABELS[d.weekday()], *[", ".join(day.get(k, [])) for k in names]])
    return buf.getvalue().encode("utf-8-sig")
```

  `duty/services/collect.py`:
  - 9줄 `from ..shifts import COMMUTE_SHIFTS` 를 아래 두 줄로 바꾼다.

```python
from ..shifts import by_key, shift_defs
from . import boards
```

  - `_require_input` 바로 아래(빈 줄 두 개 뒤, `def load_table` 앞)에 `input_keys`·`shift_names` 를 더한다. 입력 표 칸·POST 처리·CSV 열·`validate_table`·`apply_table` 은 모두 `input_keys` 하나로 키를 정한다.

```python
def input_keys(dept: Department) -> list[str]:
    """입력 표·CSV 의 근무조 키: 부서 출근조 가운데 켜진 근무조 정의가 있는 것. 순서 = 부서 출근조 순서."""
    on = {x.key for x in shift_defs(boards.active_defs(dept.board))}
    return [k for k in dept.shift_keys() if k in on]


def shift_names(dept: Department) -> dict[str, str]:
    """{입력 키: 근무 정의 이름}. 키·순서는 input_keys 와 같다(입력 표 머리글·CSV 열 이름)."""
    labels = by_key(boards.active_defs(dept.board))
    return {k: labels[k].name for k in input_keys(dept)}
```

  - `validate_table`:
    - `    shift_keys = dept.shift_keys()` 를 `    shift_keys = input_keys(dept)` 로 바꾸고, 다음 줄에 `    labels = by_key(boards.defs(dept.board))` 를 더한다.
    - `    existing = load_table(period, dept)` 를 아래 세 줄로 바꾼다. 비교·지난 날짜 판단은 입력 키 행만 본다(꺼진 근무조 행은 이 표에서 바뀌지 않는다).

```python
    loaded = load_table(period, dept)
    existing = {d: {k: v for k, v in day.items() if k in shift_keys} for d, day in loaded.items()}
    kept = {d: {n for k, v in day.items() if k not in shift_keys for n in v} for d, day in loaded.items()}
```

    - `                elif name in seen:` 바로 위에 두 줄을 넣는다(꺼진 근무조에 남은 사람을 그날 다시 넣으면 하루 한 출근 제약에 걸린다).

```python
                elif name in kept.get(d, ()):
                    add_error(errors, CsvError(0, col, f"{name}: 이미 사용하지 않는 근무조에 배정돼 있습니다"))
```

    - `f"{dept.name}에는 {COMMUTE_SHIFTS[key]} 출근조가 없습니다."` 를 `f"{dept.name}에는 {labels[key].name} 출근조가 없습니다."` 로 바꾼다.
    - `f"{name}: {COMMUTE_SHIFTS[seen[name]]}·{COMMUTE_SHIFTS[key]}에 중복"` 을 `f"{name}: {labels[seen[name]].name}·{labels[key].name}에 중복"` 으로 바꾼다.
  - `apply_table` 의 `    Commute.objects.filter(period=period, member__department=dept).delete()` 를 아래로 바꾼다(설계 6.2: 저장은 입력 키의 행만 바꾸고, 꺼진 근무조의 기존 배정은 지우지 않는다).

```python
    Commute.objects.filter(period=period, member__department=dept, shift__in=input_keys(dept)).delete()
```

  - `apply_csv` 의 `parse_commute_csv(raw, dept.shift_keys())` 를 `parse_commute_csv(raw, shift_names(dept))` 로 바꾼다.
  - `export_csv` 의 `export_commute_csv(period.dates(), dept.shift_keys(), load_table(period, dept))` 를 `export_commute_csv(period.dates(), shift_names(dept), load_table(period, dept))` 로 바꾼다.

  `duty/views/collect.py`:
  - 13줄 `from ..shifts import COMMUTE_SHIFTS, DAY_LABELS` 를 `from ..shifts import DAY_LABELS` 로 바꾼다.
  - `_render_table` 의 `    keys = dept.shift_keys()` 를 `    keys = collect.input_keys(dept)` 로, `"shift_labels": [COMMUTE_SHIFTS[k] for k in keys],` 를 `"shift_labels": list(collect.shift_names(dept).values()),` 로 바꾼다(머리글과 칸이 같은 키·순서).
  - `table` 뷰 POST 의 `for k in dept.shift_keys()}` 를 `for k in collect.input_keys(dept)}` 로 바꾼다.

  실행: `.venv/bin/pytest -W error tests/test_csv_io.py tests/test_collect.py tests/test_views_collect.py tests/test_security_stage2.py -q`
  기대: 전부 통과. 기존 CSV(`새벽\n(06:30~15:30)` 머리글 포함)도 그대로 읽힌다(`test_parse_basic`). 1단계에는 꺼진 정의가 없어 `input_keys(dept) == dept.shift_keys()` 이므로 기존 테스트의 저장·검증 결과는 같다.

  실행: `.venv/bin/pytest -W error -q`
  기대: `805 passed`(802 + 새 3), 경고 0.

```bash
git add duty/csv_io.py duty/services/collect.py duty/views/collect.py tests/test_csv_io.py tests/test_collect.py tests/test_security_stage2.py
git commit -m "feat: 출근표 CSV 열 이름과 입력 표 머리글을 근무 정의 이름으로"
```

- [ ] **Step 13: 관리 화면 부서 출근조 실패 테스트를 쓴다**

  `tests/test_admin_department.py` 의 `from duty.admin import DepartmentForm` 바로 아래에 `from duty.models import BoardShift` 를 더한다. 그리고 끝에 아래 테스트를 더한다.

```python
def test_shift_choices_and_labels_come_from_board_definitions(su_client, depts, it_board):
    BoardShift.objects.filter(board=it_board, key="dinner").update(name="늦은조")
    form = DepartmentForm(instance=depts["UI"])
    assert ("dinner", "늦은조") in form.fields["shifts"].choices
    html = su_client.get(reverse("admin:duty_department_changelist")).content.decode()
    assert "정상·늦은조·야간" in html
```

  실행: `.venv/bin/pytest -W error tests/test_admin_department.py -q -k board_definitions`
  기대: `1 failed`. 선택지가 아직 `('dinner', '석식교대')` 라 `AssertionError` 가 난다.

- [ ] **Step 14: admin.py 를 바꾼다(바뀌는 줄만. managers 관련 코드와 Meta 는 그대로, Task 4 가 바꾼다)**

  - 13~14줄 `from .services import alarm_settings` / `from .shifts import COMMUTE_SHIFTS` 를 아래로 바꾼다.

```python
from .services import alarm_settings, boards
from .shifts import shift_defs
```

  - `DepartmentForm.shifts` 필드 선언(20줄)에서 `choices=list(COMMUTE_SHIFTS.items()), ` 를 지운다.

```python
    shifts = forms.MultipleChoiceField(
        label="가능한 출근조", widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "출근조를 하나 이상 선택하세요."},
    )
```

  - `DepartmentForm.__init__` 의 `super().__init__(*args, **kwargs)` 바로 아래에 두 줄을 더한다. 그 아래 managers 후보 줄과 `initial["shifts"]` 줄은 그대로 둔다.

```python
        board = self.instance.board if self.instance.board_id else boards.it_board()  # 1단계: 새 부서는 IT
        self.fields["shifts"].choices = [(x.key, x.name) for x in shift_defs(boards.active_defs(board))]
```

  - `clean_shifts` 의 return 줄을 아래로 바꾼다.

```python
        return ",".join(k for k, _ in self.fields["shifts"].choices if k in picked)  # 화면 순서(시작 시각 순)로 저장
```

  - `DepartmentAdmin.shift_labels` 의 return 줄을 아래 두 줄로 바꾼다.

```python
        names = {x.key: x.name for x in boards.defs(obj.board)}
        return "·".join(names.get(k, k) for k in obj.shift_keys())
```

  실행: `.venv/bin/pytest -W error tests/test_admin_department.py -q`
  기대: `7 passed`. `test_form_saves_in_display_order` 의 `"dawn,night"` 도 그대로 나온다(IT 시작 시각 순이 옛 순서와 같다). `test_form_rejects_empty_or_unknown` 의 `["nomal"]` 도 선택지 밖이라 그대로 거절된다.

  실행: `.venv/bin/pytest -W error -q`
  기대: `806 passed`, 경고 0.

```bash
git add duty/admin.py tests/test_admin_department.py
git commit -m "feat: 관리 화면 부서 출근조 선택지를 근무 정의에서"
```

- [ ] **Step 15: 회차·이력 화면 칸 이름 실패 테스트를 쓴다**

  `tests/test_views_manage.py` 의 `from duty.models import Board, ChangeLog, Commute, Period, User`(Task 1 상태) 바로 아래에 `from duty.models import BoardShift` 를 더한다. 그리고 끝에 아래 테스트를 더한다.

```python
def test_change_log_label_from_board_definitions(admin_client_ok, make_member, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 9),
                              status=Period.Status.PUBLISHED)
    m = make_member("가")
    ChangeLog.objects.create(period=p, date=date(2026, 11, 9), cell="dawn", before=None, after=m)
    BoardShift.objects.filter(board=it_board, key="dawn").update(name="이른조")
    assert "이른조" in admin_client_ok.get("/changes/").content.decode()


def test_generation_failure_label_from_board_definitions(admin_client_ok, make_member, it_board):
    BoardShift.objects.filter(board=it_board, key="slot0").update(name="관제첫칸")
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 9),
                              status=Period.Status.CLOSED)
    for code in ["MEMS", "TMCH", "MD", "UI"]:
        Commute.objects.create(period=p, date=date(2026, 11, 9), member=make_member(f"직{code}", dept=code, type="직원"), shift="normal")
    r = admin_client_ok.post(f"/periods/{p.pk}/action/generate/")
    assert r.status_code == 200 and "관제첫칸" in r.content.decode()
```

  실행: `.venv/bin/pytest -W error tests/test_views_manage.py -q -k board_definitions`
  기대: `2 failed`. 칸 이름이 아직 `LEGACY_DEFS`·`CONTROL_SLOTS` 에서 오기 때문이다(개발자가 없어 관제 10칸이 모두 실패하고, 화면에는 `08:30~09:30` 이 나온다).

- [ ] **Step 16: views/manage.py 를 바꾼다**

  - import 를 바꾼다.
    - `from ..models import ChangeLog, Period` → `from ..models import Board, ChangeLog, Period`
    - `from ..services import collect, generate, periods, stats` → `from ..services import boards, collect, generate, periods, stats`
    - `from ..shifts import LEGACY_DEFS, CONTROL_SLOTS, cell_label`(Step 3 상태) → `from ..shifts import cell_label, slot_defs`
  - `_render_detail` 의 첫 줄 `    counts, spread, reached = stats.period_duty_counts(period)` 바로 아래에 한 줄을 더한다(지적 11).

```python
    slot_names = [x.name for x in slot_defs(boards.defs(period.board))]  # generator 의 칸 번호 = 관제 정의 순서
```

  - 같은 함수의 failures 줄을 아래로 바꾼다.

```python
        "failures": [{"date": f.date, "slot": slot_names[f.slot], "candidates": f.candidates} for f in failures],
```

  - `change_log` 에서 `    logs = [` 바로 위에 아래 줄을 더한다. `qs` 는 이미 `select_related(..., "period")` 이므로 `log.period.board_id` 에 쿼리가 더 들지 않는다.

```python
    defs = {b.pk: boards.defs(b) for b in Board.objects.all()}  # 근무표마다 한 번만 읽는다
```

  - 그리고 `"cell": cell_label(LEGACY_DEFS, log.cell),` 를 `"cell": cell_label(defs[log.period.board_id], log.cell),` 로 바꾼다.

  (`stats.period_duty_counts`·`publishing.unpublish_info` 호출 모양은 Task 2 상태 그대로다. board 없는 회차는 Task 6 이 없앤다. 그 전까지 board 없는 회차의 상세 화면은 실패 목록이 비어 있으면 그대로 그려진다.)

  실행: `.venv/bin/pytest -W error tests/test_views_manage.py -q`
  기대: 전부 통과.

  실행: `.venv/bin/pytest -W error -q`
  기대: `808 passed`, 경고 0.

```bash
git add duty/views/manage.py tests/test_views_manage.py
git commit -m "feat: 회차 생성 실패·변경 이력의 칸 이름을 근무 정의에서"
```

- [ ] **Step 17: 남은 사용처 점검과 브라우저 확인**

  실행: `grep -rnE "COMMUTE_SHIFTS|CONTROL_SLOTS|SHIFT_TIMES|\bCELLS\b|LEGACY_DEFS|DEPT_ORDER" duty --include=*.py | grep -v "^duty/shifts.py" | grep -v migrations`
  기대: 남는 곳은 뒤 작업 범위뿐이다.
  - `generator.py`(Task 7)
  - `services/changes.py`(Task 5)
  - `services/stats.py`(Task 7)
  - `services/calendar.py`·`services/roster.py`(Task 5·8)
  - `alarms/plan.py`·`alarms/schedule.py`·`alarms/messages.py`(Task 8)

  `models.py`·`views/`·`admin.py`·`csv_io.py`·`services/prefs.py`·`services/collect.py` 에는 남지 않는다(`DEPT_ORDER` 는 어디에도 없다). `tests/test_generator.py` 는 `CONTROL_SLOTS` 를 쓴다. 생성 작업(Task 7) 범위라 그대로 둔다. `DEVELOPER`·`STAFF` 는 `views/roster.py` 의 유형 필터와 `alarms/forms.py` 의 유형 선택지에 남는다. 이것은 근무 정의가 아니라 `User.type` 값이므로 바꾸지 않는다.

  브라우저 확인(CLAUDE.md). 실명 DB 를 열지 않도록 `config.test_settings` 로 띄운다. 이 설정은 프로세스마다 빈 임시 DATA_DIR 을 쓰므로, migrate·가짜 데이터·서버를 한 프로세스에서 돌린다. 스크립트는 저장소 밖 임시 폴더에 둔다.

```bash
W=$(mktemp -d)
cat > $W/serve.py <<'EOF'
"""브라우저 확인용: 임시 DATA_DIR(test_settings)에 가짜 데이터를 넣고 같은 프로세스에서 서버를 띄운다."""
import sys

import django

django.setup()
from django.core.management import call_command  # noqa: E402

call_command("migrate", verbosity=0)
exec(open("tools/help_videos/seed.py", encoding="utf-8").read())
try:
    from duty.models import Board, Department
except ImportError:
    pass  # main 사본(근무표 없음)
else:
    it = Board.objects.get(code="it")
    for i, code in enumerate(["MEMS", "TMCH", "MD", "UI"]):  # seed.py 가 근무표를 주는 일은 Task 5. 그 전까지 여기서 붙인다
        Department.objects.filter(code=code).update(board=it, order=i)
call_command("runserver", sys.argv[1], use_reloader=False)
EOF
mkdir $W/main && git archive main | tar -x -C $W/main
DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. .venv/bin/python $W/serve.py 127.0.0.1:8795 &   # 이 브랜치
(cd $W/main && DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. $OLDPWD/.venv/bin/python $W/serve.py 127.0.0.1:8796) &   # main
# 확인이 끝나면: kill %1 %2; rm -rf $W
```

  계정은 `member`·`manager`·`admin`(비밀번호 `Demo-pass-123`, seed.py 머리말)이다. 두 주소(8795 이 브랜치, 8796 main)를 PC 1400px와 모바일 390px에서 나란히 본다. 생성 결과는 실행마다 달라지므로 이름 배치가 아니라 글자·칸·순서를 비교한다.
  - 주간·월간 근무표: 칸 이름, "관제" 묶음, 칸 순서, 부서 필터(MEMS·TMCH·MD·UI 순), 스케줄 필터 선택지
  - 하루 화면: "출근조"/"장중관제" 제목, 바꾸기 창 To 목록의 "근무 없음"/칸 이름
  - 내 근무: 스케줄 선택지
  - 출근표 입력 표 머리글(manager), CSV 내려받기 머리글
  - 알림 규칙 화면: 스케줄 체크박스, 규칙 목록 "스케줄: …"
  - 관리 화면 부서 목록·수정 화면의 출근조(admin)
  - 회차 상세, 변경 이력(admin)

  기대: 글자 하나도 다르지 않다.

  실행: `.venv/bin/pytest -W error -q`
  기대: `808 passed`, 경고 0. 이 단계는 커밋할 파일이 없다.

---

검증 메모(Task 작성자):
- 위 Step 1~16 을 Task 1 까지 적용한 사본(`/tmp/t1v2` 를 복사한 `/tmp/t3v2`, 790 passed)에 그대로 적용해 돌렸다. 단계별 전체 결과는 793 → 796 → 799 → 801 → 802 → 804 passed, 경고 0 이었다. Task 2 의 새 테스트 2개를 더하면 위 기대 값(795·798·801·803·804·806)이 된다.
- 실패 확인(Step 1·5·7·11·13·15)도 같은 사본에서 구현 전 상태로 돌려 기대 메시지를 확인했다.
- Step 17 의 serve.py 도 그 사본에서 띄웠다. member 로그인 뒤 근무표의 부서 필터가 MEMS·TMCH·MD·UI 순으로 나왔다.
- Task 2 와 겹치는 곳: `services/roster.py` 는 shifts import 한 줄뿐이고 Step 3 sed 는 두 모양 모두에 맞는다. 테스트 파일의 `from duty.models import ...` 줄은 Task 2 가 바꾸므로, 이 작업은 그 줄을 고치지 않고 **새 줄을 더한다**.
- 지적 반영: 8(`DEPT_ORDER` 삭제, 부서 필터 order 순·근무표 부서만), 10(shift_names 정의·순서를 여기서 정함), 11(`slot_names[f.slot]`, import `cell_label, slot_defs`), 12(`_board` 하나), 17(문서 수정 없음). 지적 6·18 은 Task 8 이 이 작업의 `_shift_choices()`·`views/alarms.py` import(`alarm_settings, alarms, boards, calendar, prefs`)를 그대로 두고 근무표별로 바꾸면 된다.
- 알려진 한계(뒤 작업이 없앰): `boards.defs(None)` 은 빈 목록이다. board 없는 부서(seed.py, Task 5 가 고침)는 `shift_names` 에서 KeyError 가 난다. board 없는 회차(관리 화면 회차 만들기, Task 6 이 고침)는 이력 화면 `defs[None]` 에서 KeyError 가 난다. 둘 다 테스트에는 없는 경로다. 1단계 PR 은 Task 10 까지 한 번에 합치므로 운영에는 나가지 않는다.


---

### Task 4: 그룹 권한(perms·managers 호환·메뉴)

관리자 판정을 `is_staff` 에서 그룹으로 옮긴다. 근무표 관리 그룹은 `Board.admin_group`, 부서 입력 그룹은 `Department.input_group` 이다. `Department.managers` M2M 은 지우고 같은 이름의 호환 property 와 관리 화면 폼만 남긴다. 사용자 화면의 글자·순서·링크와 알림은 바뀌지 않는다(IT 관리 그룹 = 마이그레이션 0011 이 옮긴 옛 스태프). 바뀌는 것은 다음 둘이다.
- 슈퍼유저 관리 화면의 부서 화면: 근무표·순서 칸이 생기고, 입력 담당자 위젯을 폼이 직접 그린다.
- 권한의 뜻(설계 9절): 스태프·슈퍼유저라고 자동으로 통과하지 않는다. 부서 없는 계정이나 다른 근무표 사람은 그 근무표를 고치지 못한다.

순서(지적 5): managers M2M 삭제·property·마이그레이션·DepartmentForm 과 perms 교체를 **한 커밋**에 넣는다. M2M 이 없으면 옛 `perms.managed_departments`(`user.managed_departments`)와 `filter_horizontal=["managers"]` 가 곧바로 깨지기 때문이다. 그다음 메뉴·근무표 편집 판단을 두 번째 커밋으로 한다.

**Files:**
- Modify: `duty/models.py`
  - `Department.managers` M2M 한 줄을 지운다. Task 1~3 상태에서 104줄 `managers = models.ManyToManyField(...)`.
  - `def shift_keys` 아래에 `managers` property 를 더한다.
- Create: `duty/migrations/0015_remove_department_managers.py`. `makemigrations` 로 만든 뒤 operations 맨 앞에 근무표 없는 부서를 IT 로 옮기는 `RunPython` 을 손으로 더한다(M2M 이 남아 있을 때 담당자를 입력 그룹으로 복사). 의존은 `('duty', '0014_delete_controlduty')`(Task 2) 다.
- Modify: `duty/admin.py`
  - import 에 `FilteredSelectMultiple` 을 더한다(4줄 `from django.contrib.auth.admin ...` 바로 위). 같은 줄 바로 아래에 `from django.contrib.auth.models import Group` 을 더한다(Task 9 가 더하려던 줄을 이 작업이 먼저 넣는다. Task 9 는 이 줄을 다시 더하지 않는다).
  - `DepartmentForm`·`DepartmentAdmin` 을 바꾼다. Task 3 상태에서 17–64줄이다.
- Modify: `duty/perms.py`(전체 교체)
- Modify: `duty/context.py:18`(`if user.is_staff:`)
- Modify: `duty/views/roster.py`. 아래 줄 번호는 Task 3 상태다.
  - `roster()` 139줄 `today, admin = …`
  - 191줄 `"edit": …`
  - `day()` 248줄 `editable = …`
- Test:
  - `tests/test_perms.py`: 전체 교체. 기존 3개는 글자 그대로 둔다.
  - `tests/test_admin_department.py`: `_data` 에 허용 변환 (a) 를 하고 새 테스트를 더한다.
  - `tests/test_migration_department_managers.py`(새): 0015 가 근무표 없는 부서를 IT 로 옮기고 담당자를 입력 그룹에 복사하는지
  - `tests/test_views_manage.py`, `tests/test_help.py`, `tests/test_views_roster.py`: 끝에 테스트를 더한다.
- 코드는 바꾸지 않고 테스트로만 확인하는 곳:
  - `duty/views/common.py:11-18` 의 `admin_required` 는 `perms.is_admin` 을 부르므로 그대로 그룹 기준이 된다.
  - `duty/help.py:46-51` 의 `allowed` 도 `perms.is_admin`·`managed_departments` 만 쓴다.
  - `duty/services/changes.py:68,133` 의 `perms.assert_can_edit_date(user, d)` 는 그대로 둔다. 이 작업이 그 함수를 IT 근무표 기준 임시 함수로 바꾸고, Task 5 가 `assert_can_edit(user, board, d)` 로 바꾼 뒤 임시 함수를 지운다.
  - `duty/services/collect.py:60`, `duty/views/collect.py:40` 의 `perms.is_admin` 은 뜻이 이미 그룹 기준이 됐다. 이것을 `is_board_admin(user, period.board)` 로 좁히는 일은 Task 7 몫이다.
- 바꾸지 않음:
  - 관리 화면의 Board·BoardShift·Group·GroupKeeper 등록과 UserAdmin 의 그룹 칸은 Task 9 몫이다.
  - 문서는 Task 10 몫이다(지적 17).
  - `tools/help_videos/seed.py` 는 Task 5 몫이다(아래 "알려진 한계" 참고).

**Interfaces:**
- Consumes:
  - Task 1:
    - `Board`(`save()` 가 `"{name} 근무표 관리"` 그룹을 만든다), `Board.InputMode`
    - `Department.board`·`.order`·`.input_group`. collect 근무표 부서는 `save()` 가 `"{name} 출근표 입력"` 그룹을 만든다.
    - 마이그레이션 0011: managers 를 입력 그룹으로, is_staff 를 IT 관리 그룹으로 옮긴다. reverse 는 입력 그룹을 managers 로 되돌린다.
    - conftest 의 `it_board`, `depts`(board=it_board, order 0..3), `admin_user`(IT 관리 그룹 멤버, is_staff, 부서 없음), `make_member`, `fixed_today`
  - Task 2: 마지막 마이그레이션 `0014_delete_controlduty`
  - Task 3:
    - `boards.it_board()`, `boards.defs(board)`
    - `shifts.shift_defs`
    - `views/roster.py` 의 `_board(user)` 와, `roster()`·`day()` 첫머리에 이미 있는 `board` 변수(지적 12)
    - admin `DepartmentForm` 의 출근조 선택지(`shift_defs(boards.defs(...))`)
    - test_views_roster 의 `world` fixture 와 `from duty.models import Board, BoardShift, Department, User` 줄
- Produces(`duty/perms.py`):
  - `today() -> date`(그대로)
  - `admin_boards(user) -> QuerySet[Board]`: 관리 그룹 멤버인 근무표들이다. 익명이면 none. 스태프·슈퍼유저라고 자동으로 넣지 않는다.
  - `is_board_admin(user, board) -> bool`
  - `is_admin(user) -> bool`(= `admin_boards(user).exists()`, 메뉴·영상·`admin_required` 용)
  - `stats_boards(user) -> QuerySet[Board]`: `admin_boards(user)` 가운데 `slot*` 정의(`BoardShift.key` 가 `slot` 으로 시작)가 있는 근무표. distinct. 통계 메뉴(설계 7절)가 쓴다. **Task 6 의 `stats_view` 는 `admin_boards(...)` 대신 `perms.stats_boards(request.user).order_by("id").first()` 를 쓰고, `None` 이면 403 을 낸다**(근무표가 IT 하나인 1단계에서는 결과가 같다).
  - `managed_departments(user) -> QuerySet[Department]`: 입력 그룹 멤버인 부서 ∪ 내가 관리하는 근무표의 모든 부서. distinct, Meta 순서(code).
  - `can_input_department(user, dept) -> bool`
  - `assert_can_edit(user, board, d) -> None`. 실패 문구는 둘이다.
    - 그 근무표 관리 그룹도 아니고 그 근무표 부서 사람도 아니면 `PermissionDenied("이 근무표를 바꿀 권한이 없습니다.")`
    - 지난 날짜이고 관리 그룹이 아니면 기존 문구 그대로 `PermissionDenied("지난 날짜는 어드민만 수정할 수 있습니다.")`
  - `can_edit(user, board, d) -> bool`
  - **임시** `assert_can_edit_date(user, d) -> None` = `assert_can_edit(user, boards.it_board(), d)`. Task 5 가 지운다.
- Produces(모델): `Department.managers` property. 입력 그룹이 있으면 `input_group.user_set` 을 돌려준다(관련 매니저라 `.all()`·`.add()`·`.set()` 이 된다). 없으면 `User.objects.none()` 이다. 2단계 끝에 지운다.
- Produces(`duty/admin.py`):
  - `DepartmentForm`
    - Meta.fields 는 `["code", "name", "board", "order", "shifts"]` 이고, 선언 필드로 `managers`(`ModelMultipleChoiceField` + `FilteredSelectMultiple`)가 있다.
    - `board` 는 필수다.
    - 저장된 부서는 `board` 칸이 `disabled`(읽기 전용)다. 새 부서만 근무표를 고른다(설계 4.4: 1단계에서는 저장된 부서의 근무표를 바꿀 수 없다).
    - `clean()` 은 입력 그룹이 아직 없는 새 부서를 collect 근무표에 둘 때 `"{name} 출근표 입력"` 그룹이 이미 있는 경우(`name` 칸 오류 `"같은 이름의 그룹이 이미 있습니다: …"`, `Group.name` unique 위반 500 을 막는다. 3단계 근무표 추가 화면도 같은 규칙).
  - `DepartmentAdmin`
    - `get_queryset`: `prefetch_related("input_group__user_set")`
    - `save_related`: `input_group.user_set.set(managers)`
- 마이그레이션: `0015_remove_department_managers`. 다음 번호는 **0016** 이다.

---

- [ ] **Step 1: 권한·부서 관리 화면 테스트를 먼저 쓴다(실패 확인용)**

`tests/test_perms.py` 를 아래 내용으로 통째로 바꾼다. 기존 테스트 3개(`test_past_date_is_admin_only`·`test_can_input_department`·`test_managed_departments`)는 글자 하나 바꾸지 않는다. `test_past_date_is_admin_only` 는 임시 `assert_can_edit_date` 를 그대로 부르고, Task 5 가 허용 변환 (c) 로 `assert_can_edit(u, it_board, d)` 로 바꾼다. 나머지는 새 테스트다. 두 번째 근무표는 `Board.objects.create` 로 만들어 관리 그룹을 `Board.save` 에 맡긴다(지적 13: 그룹 이름 규칙은 한 곳).

```python
from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied

from duty import perms
from duty.models import Board, Department, User


def test_past_date_is_admin_only(fixed_today, make_member, admin_user):
    fixed_today(date(2026, 11, 10))
    m = make_member("가", user=True)
    perms.assert_can_edit_date(m, date(2026, 11, 10))  # 오늘은 누구나
    with pytest.raises(PermissionDenied):
        perms.assert_can_edit_date(m, date(2026, 11, 9))
    perms.assert_can_edit_date(admin_user, date(2026, 11, 9))


def test_can_input_department(depts, make_member, admin_user):
    m = make_member("가", user=True)
    depts["MEMS"].managers.add(m)
    assert perms.can_input_department(m, depts["MEMS"])
    assert not perms.can_input_department(m, depts["MD"])
    assert perms.can_input_department(admin_user, depts["MD"])


def test_managed_departments(depts, make_member, admin_user):
    m = make_member("가", user=True)
    depts["MD"].managers.add(m)
    assert list(perms.managed_departments(m)) == [depts["MD"]]
    assert perms.managed_departments(admin_user).count() == 4
    assert perms.managed_departments(AnonymousUser()).count() == 0


@pytest.fixture
def ops(it_board):
    """두 번째 근무표(가짜 '운영팀', 직접 입력)와 그 부서 하나. 관리 그룹은 Board.save 가 만든다."""
    board = Board.objects.create(code="ops", name="운영팀", input_mode="direct")
    return board, Department.objects.create(code="OPS", name="운영", shifts="normal", board=board)


def test_admin_is_group_member_not_staff_or_superuser(it_board, ops, make_member):
    staff = User.objects.create_user("st", name="스태프", is_staff=True)
    root = User.objects.create_superuser("root", password="unused-Pw-123", name="루트")
    m = make_member("가")
    for u in (staff, root, m, AnonymousUser()):
        assert not perms.is_admin(u) and not perms.admin_boards(u).exists()
    it_board.admin_group.user_set.add(m)
    assert list(perms.admin_boards(m)) == [it_board]
    assert perms.is_admin(m) and perms.is_board_admin(m, it_board) and not perms.is_board_admin(m, ops[0])


def test_managed_departments_is_input_groups_plus_admin_boards(it_board, ops, depts, make_member):
    m = make_member("가")
    depts["MD"].managers.add(m)          # 입력 그룹
    ops[0].admin_group.user_set.add(m)   # 운영팀 관리자 → 운영팀의 모든 부서
    assert list(perms.managed_departments(m)) == [depts["MD"], ops[1]]
    assert perms.can_input_department(m, ops[1]) and not perms.can_input_department(m, depts["UI"])
    it_board.admin_group.user_set.add(m)
    assert perms.managed_departments(m).count() == 5  # 입력 그룹과 관리 근무표가 겹쳐도 한 번씩


def test_can_edit_own_board_only(fixed_today, it_board, ops, make_member):
    fixed_today(date(2026, 11, 10))
    today, past = date(2026, 11, 10), date(2026, 11, 9)
    m = make_member("가")  # IT 부서
    o = User.objects.create_user("OPS001", name="운영가", department=ops[1], type="직원")
    nodept = User.objects.create_user("x", name="무소속")
    root = User.objects.create_superuser("root", password="unused-Pw-123", name="루트")
    assert perms.can_edit(m, it_board, today) and not perms.can_edit(m, it_board, past)
    assert not perms.can_edit(m, ops[0], today)  # 남의 근무표는 보기만
    assert perms.can_edit(o, ops[0], today) and not perms.can_edit(o, it_board, today)
    for u in (nodept, root, AnonymousUser()):
        assert not perms.can_edit(u, it_board, today)
    with pytest.raises(PermissionDenied, match="이 근무표를 바꿀 권한이 없습니다"):
        perms.assert_can_edit(m, ops[0], today)
    with pytest.raises(PermissionDenied, match="지난 날짜는 어드민만"):
        perms.assert_can_edit(m, it_board, past)


def test_board_admin_edits_past_of_that_board_only(fixed_today, it_board, ops):
    fixed_today(date(2026, 11, 10))
    a = User.objects.create_user("adm2", name="운영관리")
    ops[0].admin_group.user_set.add(a)
    assert perms.can_edit(a, ops[0], date(2026, 11, 9))  # 부서가 없어도 관리 그룹이면
    assert not perms.can_edit(a, it_board, date(2026, 11, 10))


def test_assert_can_edit_date_is_it_board(fixed_today, ops):
    """Task 5 가 changes 에 board 를 넘길 때까지의 임시 함수: IT 근무표 기준."""
    fixed_today(date(2026, 11, 10))
    o = User.objects.create_user("OPS001", name="운영가", department=ops[1], type="직원")
    with pytest.raises(PermissionDenied, match="이 근무표를 바꿀 권한이 없습니다"):
        perms.assert_can_edit_date(o, date(2026, 11, 10))
```

`tests/test_views_manage.py` 끝에 더한다. 파일 맨 위 import 에 `User` 가 이미 있다.

```python


@pytest.fixture
def staff_only(db):
    return User.objects.create_user("st", password="unused-Pw-123", name="스태프", is_staff=True)


@pytest.mark.parametrize("url", ["/periods/", "/stats/", "/changes/"])
def test_admin_pages_need_admin_group_not_staff(client, staff_only, it_board, url):
    client.force_login(staff_only)
    assert client.get(url).status_code == 403
    it_board.admin_group.user_set.add(staff_only)
    assert client.get(url).status_code == 200
```

`tests/test_help.py` 끝에 더한다. 파일 맨 위 import 에 `User` 가 이미 있다. 응답은 실패할 때(200, 파일 응답)에도 닫는다. 닫지 않으면 `-W error` 에서 ResourceWarning 이 다른 테스트의 ERROR 로 번진다.

```python


def test_video_roles_follow_groups_not_staff(client, videos, it_board, make_member):
    def status(name):
        r = client.get(f"/help/video/{name}.mp4")
        r.close()  # 실패할 때(200)도 파일을 닫는다
        return r.status_code

    staff = User.objects.create_user("st", password="unused-Pw-123", name="스태프", is_staff=True)
    client.force_login(staff)
    assert [status(n) for n in ("manager", "admin")] == [403, 403]
    m = make_member("가", user=True)
    it_board.admin_group.user_set.add(m)
    client.force_login(m)
    assert [status(n) for n in ("manager", "admin")] == [200, 200]
```

`tests/test_admin_department.py` 를 고친다.

(1) import 를 더한다. 맨 위 `import pytest` 바로 아래에 다음 한 줄을 넣는다.
```python
from django.contrib.auth.models import Group
from django.core.exceptions import FieldDoesNotExist
```
Task 3 이 넣은 `from duty.models import BoardShift` 바로 아래에 다음 한 줄을 넣는다.
```python
from duty.models import Board, Department
```

(2) 허용 변환 (a): `_data` 에 부서의 근무표·순서를 넣는다. 준비 코드만 바꾸고 단언은 그대로 둔다.
```python
def _data(dept, shifts):
    return {"code": dept.code, "name": dept.name, "shifts": shifts, "managers": []}
```
→
```python
def _data(dept, shifts):
    return {"code": dept.code, "name": dept.name, "board": dept.board_id, "order": dept.order,
            "shifts": shifts, "managers": []}
```

(3) 파일 끝에 더한다.
```python


def test_managers_is_input_group_not_a_field(depts, make_member):
    with pytest.raises(FieldDoesNotExist):
        Department._meta.get_field("managers")
    a = make_member("가")
    depts["UI"].managers.add(a)
    assert list(depts["UI"].input_group.user_set.all()) == [a]
    direct = Board.objects.create(code="ops", name="운영팀", input_mode="direct")
    assert list(Department.objects.create(code="OPS", name="운영", shifts="normal", board=direct).managers.all()) == []


def test_form_initial_managers_from_input_group(depts, make_member):
    a = make_member("가")
    depts["UI"].input_group.user_set.add(a)
    assert list(DepartmentForm(instance=depts["UI"]).initial["managers"]) == [a]


def test_save_sets_input_group_members(su_client, depts, make_member):
    a, b = make_member("가"), make_member("나")
    depts["UI"].input_group.user_set.add(a)
    r = su_client.post(reverse("admin:duty_department_change", args=["UI"]),
                       {**_data(depts["UI"], ["normal"]), "managers": [b.pk]})
    assert r.status_code == 302, r.content.decode()
    assert list(depts["UI"].input_group.user_set.all()) == [b]


def test_change_page_uses_filtered_select(su_client, depts):
    html = su_client.get(reverse("admin:duty_department_change", args=["UI"])).content.decode()
    assert 'name="managers"' in html and "selectfilter" in html
    assert 'name="board"' in html and 'name="order"' in html


def test_saved_department_board_is_read_only(depts):
    other = Board.objects.create(code="ops", name="운영팀", input_mode="direct")
    form = DepartmentForm({**_data(depts["UI"], ["normal"]), "board": other.pk}, instance=depts["UI"])
    assert form.fields["board"].disabled and not DepartmentForm().fields["board"].disabled  # 새 부서만 고른다
    assert form.is_valid(), form.errors
    assert form.save().board_id == depts["UI"].board_id  # 보낸 근무표는 무시된다(옮기기는 별도 기능)


def test_new_department_input_group_name_clash(it_board):
    """Department.save 가 만들 입력 그룹 이름이 이미 있으면 500 대신 칸 오류."""
    Group.objects.create(name="품질 출근표 입력")
    data = {"code": "QA", "name": "품질", "board": it_board.pk, "order": 9, "shifts": ["normal"], "managers": []}
    form = DepartmentForm(data)
    assert not form.is_valid()
    assert "같은 이름의 그룹이 이미 있습니다: 품질 출근표 입력" in str(form.errors.get("name", ""))
```

`tests/test_migration_department_managers.py` 를 새로 만든다(틀은 `tests/test_migration_boards.py` 와 같다, 이름은 모두 가상).

```python
"""0015: managers M2M 을 지우기 전에, 0011 뒤 근무표 없이 생긴 부서를 IT 로 옮기고 담당자를 입력 그룹에 복사한다."""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0014_delete_controlduty")]
AFTER = [("duty", "0015_remove_department_managers")]


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()  # 앞선 migrate 로 바뀐 적용 기록을 다시 읽는다
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_apps():
    apps = _migrate(BEFORE)
    yield apps
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())  # 다른 테스트를 위해 최신 스키마로


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_null_board_department_moves_to_it_with_managers(old_apps):
    Board = old_apps.get_model("duty", "Board")
    Group = old_apps.get_model("auth", "Group")
    it = Board.objects.filter(code="it").first() or Board.objects.create(
        code="it", name="IT 당번표", input_mode="collect", admin_group=Group.objects.create(name="IT 근무표 관리"))
    mgr = old_apps.get_model("duty", "User").objects.create(username="MGR001", name="담당가")
    dept = old_apps.get_model("duty", "Department").objects.create(code="ZZ", name="무소속부서", shifts="normal")
    dept.managers.add(mgr)

    apps = _migrate(AFTER)
    d = apps.get_model("duty", "Department").objects.get(code="ZZ")
    assert d.board_id == it.pk and d.input_group.name == "무소속부서 출근표 입력"
    assert list(d.input_group.user_set.values_list("username", flat=True)) == ["MGR001"]
    _migrate(BEFORE)  # 되돌리기: M2M 이 다시 생긴다(채운 board·입력 그룹은 그대로)
```

`tests/test_admin_users.py` 의 `test_department_manager_choices_are_roster`·`test_department_keeps_current_manager_outside_roster` 는 바꾸지 않는다. `depts["UI"].managers.add(gone)` 는 property(관련 매니저)로 그대로 돈다. test_collect·test_views_collect·test_help 의 `depts["MEMS"].managers.add(...)` 도 같다.

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_perms.py tests/test_views_manage.py tests/test_help.py tests/test_admin_department.py tests/test_migration_department_managers.py -q`

Expected: `16 failed`. ERROR 는 없어야 한다.
- test_migration_department_managers
  - `test_null_board_department_moves_to_it_with_managers`: `NodeNotFoundError: Node ('duty', '0015_remove_department_managers') not a valid node`
- test_perms
  - `test_admin_is_group_member_not_staff_or_superuser`: 스태프가 `is_admin` 이라 AssertionError 가 난다.
  - `test_managed_departments_is_input_groups_plus_admin_boards`: 운영 부서가 빠져 AssertionError 가 난다.
  - `test_can_edit_own_board_only`·`test_board_admin_edits_past_of_that_board_only`: `AttributeError: module 'duty.perms' has no attribute 'can_edit'`
  - `test_assert_can_edit_date_is_it_board`: `DID NOT RAISE PermissionDenied`
- test_views_manage
  - `test_admin_pages_need_admin_group_not_staff[...]` 3개: 스태프에게 200 이 나온다.
- test_help
  - `test_video_roles_follow_groups_not_staff`: 스태프에게 `[200, 200]` 이 나온다.
- test_admin_department
  - `test_managers_is_input_group_not_a_field`: `DID NOT RAISE FieldDoesNotExist`
  - `test_form_initial_managers_from_input_group`: 초기값이 M2M 기준(빈 목록)이다.
  - `test_save_sets_input_group_members`: M2M 에 저장돼 입력 그룹이 `[가]` 로 남는다.
  - `test_change_page_uses_filtered_select`: `name="board"` 칸이 없다.
  - `test_saved_department_board_is_read_only`: `KeyError: 'board'`(board 칸이 아직 없다).
  - `test_new_department_input_group_name_clash`: 이름 검사가 없어 폼이 유효하다(저장하지 않으므로 IntegrityError ERROR 는 나지 않는다).
- 기존 테스트는 모두 PASS 다.

- [ ] **Step 3: 모델에서 M2M 을 빼고 호환 property 를 둔다**

`duty/models.py` 의 `Department` 에서 이 줄을 지운다.

```python
    managers = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="managed_departments", verbose_name="입력 담당자")
```

`shift_keys` 메서드 바로 아래에 더한다. `User` 는 같은 모듈 아래쪽에 정의돼 있지만 실행할 때 찾으므로 괜찮다. `settings` import 는 다른 FK 가 쓰므로 그대로 둔다.

```python
    @property
    def managers(self):
        """1단계 호환(2단계 끝에 지운다): 출근표 입력 담당 = 입력 그룹 멤버. 그룹이 없으면(직접 입력 근무표) 빈 목록."""
        return self.input_group.user_set if self.input_group_id else User.objects.none()
```

마이그레이션은 Step 4 의 admin 수정 뒤에 만든다. 지금 admin 의 `DepartmentForm.Meta.fields` 에 `"managers"` 가 있어서, manage.py 가 시작할 때 `FieldError: Unknown field(s) (managers)` 로 멈추기 때문이다.

- [ ] **Step 4: `DepartmentForm`·`DepartmentAdmin` 을 바꾼다**

`duty/admin.py` 4줄 `from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin` 바로 위에 더한다.

```python
from django.contrib.admin.widgets import FilteredSelectMultiple
```

같은 줄(`from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin`) 바로 아래에 더한다.

```python
from django.contrib.auth.models import Group
```

`class DepartmentForm(forms.ModelForm):` 부터 `class UserAddForm(forms.ModelForm):` 바로 앞까지(Task 3 상태 17–65줄, `DepartmentAdmin` 끝의 빈 줄 둘 포함)를 아래로 바꾼다. 출근조 선택지 두 줄과 `clean_shifts`·`shift_labels` 는 Task 3 이 쓴 그대로다.

```python
class DepartmentForm(forms.ModelForm):
    # DB에는 지금처럼 "normal,dinner,night" 문자열로 저장하고, 입력만 체크박스로 받는다
    shifts = forms.MultipleChoiceField(
        label="가능한 출근조", widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "출근조를 하나 이상 선택하세요."},
    )
    # 1단계 호환: 입력 담당자 = 부서 입력 그룹 멤버. 모델 칸이 아니라 DepartmentAdmin.save_related 가 그룹에 넣는다
    managers = forms.ModelMultipleChoiceField(
        label="입력 담당자", queryset=User.objects.none(), required=False,
        widget=FilteredSelectMultiple("입력 담당자", is_stacked=False),
    )

    class Meta:
        model = Department
        fields = ["code", "name", "board", "order", "shifts"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["board"].required = True  # 부서는 근무표 하나에 속한다(DB NOT NULL 은 Task 6)
        if self.instance.board_id:  # 1단계: 저장된 부서의 근무표는 바꿀 수 없다(옮기기는 필요해지면 별도 기능, 설계 4.4)
            self.fields["board"].disabled = True
        board = self.instance.board if self.instance.board_id else boards.it_board()  # 1단계: 새 부서는 IT
        self.fields["shifts"].choices = [(x.key, x.name) for x in shift_defs(boards.active_defs(board))]
        # 후보는 roster()만. 지금 담당자는 퇴사·부서 해제됐어도 보여야 저장할 때 조용히 빠지지 않는다
        current = self.instance.managers.all()  # 새 부서·직접 입력 근무표 부서는 빈 목록
        self.fields["managers"].queryset = (User.objects.roster() | current).distinct()
        self.initial.setdefault("managers", list(current))
        if self.instance.pk:
            self.initial["shifts"] = self.instance.shift_keys()

    def clean_shifts(self):
        picked = set(self.cleaned_data["shifts"])
        return ",".join(k for k, _ in self.fields["shifts"].choices if k in picked)  # 화면 순서(시작 시각 순)로 저장

    def clean(self):
        c = super().clean()
        board, name = c.get("board"), c.get("name")
        # Department.save 가 만들 입력 그룹 이름이 이미 있으면 Group.name unique 위반(500) 대신 칸 오류로
        group = f"{name} 출근표 입력"
        if (board and name and board.input_mode == board.InputMode.COLLECT and not self.instance.input_group_id
                and Group.objects.filter(name=group).exists()):
            self.add_error("name", f"같은 이름의 그룹이 이미 있습니다: {group}")
        return c


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    form = DepartmentForm
    list_display = ["code", "name", "shift_labels", "member_count", "manager_names"]

    def get_queryset(self, request):
        return (super().get_queryset(request).annotate(_n=Count("members", distinct=True))
                .prefetch_related("input_group__user_set"))

    @admin.display(description="가능한 출근조")
    def shift_labels(self, obj):
        names = {x.key: x.name for x in boards.defs(obj.board)}
        return "·".join(names.get(k, k) for k in obj.shift_keys())

    @admin.display(description="인원", ordering="_n")
    def member_count(self, obj):
        return obj._n

    @admin.display(description="입력 담당자")
    def manager_names(self, obj):
        return ", ".join(m.name for m in obj.managers.all()) or "(없음)"

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if form.instance.input_group_id:  # 직접 입력 근무표의 부서는 입력 그룹이 없다
            form.instance.input_group.user_set.set(form.cleaned_data["managers"])


```

이 코드에서 정한 것은 다음과 같다.
- `managers` 는 선언 필드라서 `Meta.fields` 에 없어도 폼에 들어간다.
- `filter_horizontal` 은 지웠다. 모델 M2M 이 없으면 system check 오류(admin.E019)가 나기 때문이다. 같은 위젯은 `FilteredSelectMultiple` 이 그린다.
- 새 부서는 `save_model` 때 `Department.save` 가 입력 그룹을 만든다. 그다음 `save_related` 가 멤버를 넣는다.

마이그레이션을 만든다(지적 19: 실명 DB 를 열지 않게 `config.test_settings`).

```bash
DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --name remove_department_managers
DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations --check --dry-run
```

Expected:
- 첫 명령은 `duty/migrations/0015_remove_department_managers.py` 를 만든다. 내용은 `migrations.RemoveField(model_name='department', name='managers')` 하나이고, 의존성은 `('duty', '0014_delete_controlduty')` 다. 출력에는 `- Remove field managers from department` 가 나온다.
- 둘째 명령은 `No changes detected` 다.

만든 파일에 `RunPython` 을 손으로 더한다. 0011 뒤 근무표 없이 생긴 부서(관리 화면·seed)를 M2M 이 남아 있을 때 IT 로 옮겨야 담당자를 잃지 않는다. `from django.db import migrations` 아래에 함수를 두고, operations 맨 앞에 넣는다. `RemoveField` 는 생성된 그대로 둔다.

```python
def fill_departments(apps, schema_editor):
    """근무표 없는 부서 → IT(collect). 입력 그룹이 없으면 만들고 managers 를 복사한다(0011 과 같은 규칙)."""
    Board = apps.get_model("duty", "Board")
    Department = apps.get_model("duty", "Department")
    Group = apps.get_model("auth", "Group")
    GroupKeeper = apps.get_model("duty", "GroupKeeper")
    User = apps.get_model("duty", "User")
    left = list(Department.objects.filter(board=None))
    if not left:
        return
    it = Board.objects.get(code="it")  # 0011 이 만든 IT 근무표
    names = [f"{d.name} 출근표 입력" for d in left if d.input_group_id is None]
    if taken := sorted(Group.objects.filter(name__in=names).values_list("name", flat=True)):
        raise RuntimeError(f"이미 있는 그룹 이름이라 멈춥니다: {', '.join(taken)}. 업그레이드 전 백업으로 롤백한 뒤"
                           f"(docs/OPERATIONS.md \"업그레이드·롤백\") 옛 버전 관리 화면에서 그 그룹 이름을 바꾸고 업그레이드를 다시 하세요.")
    keepers = list(User.objects.filter(is_superuser=True))
    for d in left:
        d.board = it
        if d.input_group_id is None:
            d.input_group = Group.objects.create(name=f"{d.name} 출근표 입력")
            d.input_group.user_set.set(d.managers.all())
            GroupKeeper.objects.bulk_create([GroupKeeper(group=d.input_group, user=u) for u in keepers])
        d.save(update_fields=["board", "input_group"])
```

```python
    operations = [
        migrations.RunPython(fill_departments, migrations.RunPython.noop),  # 되돌릴 때 옮긴 값은 그대로 둔다
        migrations.RemoveField(
            model_name="department",
            name="managers",
        ),
    ]
```

- 되돌릴 때는 `RemoveField` reverse 가 빈 M2M 을 먼저 만들고(`RunPython` reverse 는 아무것도 하지 않는다), 이어서 0011 reverse 가 입력 그룹 멤버를 managers 로 채운다.

- [ ] **Step 5: `duty/perms.py` 를 통째로 바꾼다**

`duty/services/__init__.py` 는 비어 있고 `services/boards.py` 는 models 만 import 한다. 그래서 perms 가 맨 위에서 `boards` 를 import 해도 순환이 생기지 않는다.

```python
"""권한 규칙. 다른 모듈은 `from . import perms` 후 `perms.today()` 형태로 호출한다(테스트 monkeypatch 용).

관리자 판정은 그룹으로 한다(근무표 관리 그룹 = Board.admin_group, 부서 입력 그룹 = Department.input_group).
스태프·슈퍼유저 표시는 쓰지 않는다(슈퍼유저도 그룹에 들어가야 근무표를 다룬다).
"""

from datetime import date

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils import timezone

from .models import Board, Department
from .services import boards


def today() -> date:
    return timezone.localdate()


def admin_boards(user):
    """내가 관리 그룹 멤버인 근무표들."""
    if not user.is_authenticated:
        return Board.objects.none()
    return Board.objects.filter(admin_group__user=user)


def is_board_admin(user, board) -> bool:
    return admin_boards(user).filter(pk=board.pk).exists()


def is_admin(user) -> bool:
    """어느 근무표든 관리자(메뉴·영상용)."""
    return admin_boards(user).exists()


def stats_boards(user):
    """통계를 볼 수 있는 근무표: 내가 관리하고 장중관제(slot*) 정의가 있는 근무표(설계 7절)."""
    return admin_boards(user).filter(shifts__key__startswith="slot").distinct()


def managed_departments(user):
    """출근표를 입력할 수 있는 부서: 입력 그룹 멤버인 부서 ∪ 내가 관리하는 근무표의 모든 부서."""
    if not user.is_authenticated:
        return Department.objects.none()
    return Department.objects.filter(Q(input_group__user=user) | Q(board__admin_group__user=user)).distinct()


def can_input_department(user, dept: Department) -> bool:
    return managed_departments(user).filter(pk=dept.pk).exists()


def assert_can_edit(user, board, d: date) -> None:
    """근무표 board 의 날짜 d 를 바꿀 수 있는가: 그 근무표 관리 그룹, 또는 그 근무표 부서 사람(오늘 이후만)."""
    if is_board_admin(user, board):
        return
    if not (user.is_authenticated and user.department_id and user.department.board_id == board.pk):
        raise PermissionDenied("이 근무표를 바꿀 권한이 없습니다.")
    if d < today():
        raise PermissionDenied("지난 날짜는 어드민만 수정할 수 있습니다.")


def can_edit(user, board, d: date) -> bool:
    try:
        assert_can_edit(user, board, d)
    except PermissionDenied:
        return False
    return True


def assert_can_edit_date(user, d: date) -> None:
    """임시(Task 5 가 지운다): changes 가 아직 근무표를 받지 않아 IT 근무표로 검사한다."""
    assert_can_edit(user, boards.it_board(), d)
```

`Group` 과 사용자 사이의 조회 이름은 `user` 다(`User.groups` 의 related_query_name). 그래서 `admin_group__user=user` 와 `input_group__user=user` 로 거른다.

- [ ] **Step 6: 통과를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_perms.py tests/test_views_manage.py tests/test_help.py tests/test_admin_department.py tests/test_migration_department_managers.py tests/test_admin_users.py tests/test_changes.py tests/test_collect.py tests/test_views_collect.py -q`

Expected: 전부 PASS. 다음 기존 단언도 그대로 통과한다.
- `test_changelist_shows_labels_count_and_managers` 의 `">가<"`
- `test_form_saves_in_display_order` 의 `"dawn,night"`
- `test_department_keeps_current_manager_outside_roster`
- test_changes 전체: 변경하는 사람은 IT 부서 멤버이거나 `admin_user`(IT 관리 그룹)다.

Run: `.venv/bin/pytest -W error -q`

Expected: **824 passed**, 경고 0. Task 1~3 까지는 808 이고 여기에 새 테스트 16개(마이그레이션 테스트 1개 포함)가 더해진다.

- [ ] **Step 7: 커밋**

```bash
git add duty/models.py duty/migrations/0015_remove_department_managers.py duty/admin.py duty/perms.py tests/test_perms.py tests/test_views_manage.py tests/test_help.py tests/test_admin_department.py tests/test_migration_department_managers.py
git commit -m "feat: 관리자·입력 담당 판정을 그룹 기준으로(managers 칸 삭제·입력 그룹 호환, 스태프·슈퍼유저 자동 통과 없음)"
```

- [ ] **Step 8: 메뉴·근무표 편집 판단 테스트를 쓴다(실패 확인용)**

`tests/test_views_manage.py` 끝에 더한다. `staff_only` fixture 는 Step 1 에서 만들었다.

```python


def test_admin_menu_follows_group(client, it_board, make_member, staff_only):
    client.force_login(staff_only)
    assert 'href="/periods/"' not in client.get("/").content.decode()  # 스태프 표시만으로는 아님
    m = make_member("가", user=True)
    client.force_login(m)
    assert 'href="/periods/"' not in client.get("/").content.decode()
    it_board.admin_group.user_set.add(m)
    body = client.get("/").content.decode()
    assert all(f'href="{u}"' in body for u in ("/periods/", "/stats/", "/changes/", "/collect/"))


def test_stats_menu_only_for_boards_with_slots(client, it_board, make_member):
    """설계 7절: 통계는 slot* 정의가 있는 근무표의 관리 그룹만. 정의 없는 근무표 관리자는 회차·이력만."""
    m = make_member("가", user=True)
    Board.objects.create(code="ops", name="운영팀", input_mode="direct").admin_group.user_set.add(m)
    client.force_login(m)
    body = client.get("/").content.decode()
    assert 'href="/periods/"' in body and 'href="/changes/"' in body and 'href="/stats/"' not in body


def test_superuser_is_not_admin_automatically(client, it_board):
    root = User.objects.create_superuser("root", password="unused-Pw-123", name="루트")
    client.force_login(root)
    body = client.get("/").content.decode()
    assert '<a href="/admin/">관리</a>' in body and 'href="/periods/"' not in body
    assert client.get("/periods/").status_code == 403
```

`Board` 는 test_views_manage 맨 위 `from duty.models import Board, ChangeLog, Commute, Period, User`(Task 1 상태)에 이미 있다.

`tests/test_views_roster.py` 끝에 더한다. `Board`·`User` 는 Task 3 이 더한 `from duty.models import Board, BoardShift, Department, User` 줄에 이미 있다.

```python


@pytest.mark.parametrize("who,editable", [("it_admin", True), ("staff", False), ("ops_admin", False)])
def test_past_edit_follows_board_admin_group(client, world, fixed_today, it_board, who, editable):
    a, _ = world
    fixed_today(date(2026, 11, 12))
    if who == "it_admin":
        it_board.admin_group.user_set.add(a)
    elif who == "staff":
        a.is_staff = True
        a.save()
    else:  # 다른 근무표의 관리자라고 IT 근무표의 지난 날을 고칠 수는 없다
        Board.objects.create(code="ops", name="운영팀", input_mode="direct").admin_group.user_set.add(a)
    client.force_login(a)
    assert ("/cell/2026-11-10/" in client.get("/?date=2026-11-10").content.decode()) == editable
    assert ("바꾸기</summary>" in client.get("/day/2026-11-10/").content.decode()) == editable


def test_member_without_department_cannot_edit(client, world, admin_user):
    """부서 없는 계정은 근무표가 없어 보기만 한다(관리 그룹이면 고친다). 오늘 날짜도 같다."""
    nodept = User.objects.create_user("x", password="unused-Pw-123", name="무소속")
    client.force_login(nodept)
    assert "/cell/2026-11-10/" not in client.get("/?date=2026-11-10").content.decode()
    assert "바꾸기</summary>" not in client.get("/day/2026-11-10/").content.decode()
    client.force_login(admin_user)
    assert "바꾸기</summary>" in client.get("/day/2026-11-10/").content.decode()
```

- [ ] **Step 9: 실패를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_views_manage.py tests/test_views_roster.py -q`

Expected: `5 failed`.
- `test_admin_menu_follows_group`: context.py 가 아직 `user.is_staff` 라서 스태프에게 회차 메뉴가 보인다.
- `test_stats_menu_only_for_boards_with_slots`: 운영팀 관리자는 스태프가 아니라서 회차 메뉴가 안 보인다.
- `test_superuser_is_not_admin_automatically`: 슈퍼유저도 `is_staff` 라서 회차 메뉴가 보인다.
- `test_past_edit_follows_board_admin_group[ops_admin-False]`: roster.py 가 아직 `perms.is_admin` 이라서 다른 근무표 관리자도 IT 의 지난 칸 링크를 본다.
- `test_member_without_department_cannot_edit`: 아직 `d >= today` 라서 부서 없는 계정도 오늘 칸 링크를 본다.
- 나머지 parametrize 둘(it_admin, staff)은 PASS 다. 스태프의 경우는 Step 5 의 `is_admin` 교체로 이미 통과한다.

- [ ] **Step 10: 메뉴와 근무표 편집 판단을 바꾼다**

`duty/context.py` 18–19줄:

```python
    if user.is_staff:
        items += [("회차", "/periods/", ()), ("통계", "/stats/", ()), ("이력", "/changes/", ())]
```
→
```python
    if perms.is_admin(user):  # 어느 근무표든 관리 그룹 멤버(스태프 표시는 관리자 판정에 쓰지 않는다)
        items.append(("회차", "/periods/", ()))
        if perms.stats_boards(user).exists():  # 통계는 slot* 정의가 있는 근무표의 관리 그룹만(설계 7절)
            items.append(("통계", "/stats/", ()))
        items.append(("이력", "/changes/", ()))
```

메뉴 순서(회차·통계·이력)와 글자는 그대로다. IT 근무표에는 0011 이 넣은 `slot0`~`slot9` 정의가 있어 IT 관리자에게는 지금처럼 통계가 보인다.

`duty/views/roster.py` 는 세 군데를 고친다. 근무표는 Task 3 이 각 뷰 첫머리에 둔 `board = _board(request.user)` 변수를 그대로 쓴다(지적 12). 새로 `boards.it_board()` 를 부르지 않는다.

1. `roster()` 에서 다음 세 줄(Task 3 상태 139–141줄)을 바꾼다.
```python
    today, admin = perms.today(), perms.is_admin(request.user)
    board = _board(request.user)
    defs = boards.defs(board)
```
→
```python
    today = perms.today()
    board = _board(request.user)
    defs = boards.defs(board)
    # 칸 링크 권한: 날짜마다 묻지 않고 지난 날·오늘 이후 두 번만 묻는다
    edit_past, edit_now = (perms.can_edit(request.user, board, x) for x in (today - timedelta(days=1), today))
```

2. `day_info` 안의 다음 줄(Task 3 상태 191줄)을 바꾼다.
```python
            "edit": (admin or d >= today) and not other and d in by_date,  # 배포된 근무표가 있는 날만
```
→
```python
            "edit": (edit_past if d < today else edit_now) and not other and d in by_date,  # 배포된 근무표가 있는 날만
```

3. `day()` 의 다음 줄(Task 3 상태 248줄)을 바꾼다. `board` 는 같은 함수 첫 줄에 이미 있다.
```python
    editable = perms.is_admin(request.user) or d >= perms.today()
```
→
```python
    editable = perms.can_edit(request.user, board, d)
```

`timedelta` 는 roster.py 1줄 `from datetime import date, timedelta` 에 이미 있다.

- [ ] **Step 11: 통과를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_views_manage.py tests/test_views_roster.py tests/test_help.py -q`

Expected: 전부 PASS. 다음 기존 테스트도 포함된다.
- `test_admin_nav_link_superuser_only`: admin_user 는 스태프이지만 슈퍼유저가 아니어서 관리 링크가 없다.
- `test_past_cells_not_editable_for_member_in_week`
- `test_admin_pages_forbidden_for_member`

Run:
```bash
grep -rnE "\.is_staff\b|managed_departments\.all|filter_horizontal" duty --include=*.py | grep -v migrations
grep -rn "assert_can_edit_date" duty --include=*.py
```

Expected:
- 첫 grep 은 `duty/admin.py` 의 `admin.site.has_permission = lambda request: … request.user.is_staff and request.user.is_superuser` 한 줄만 낸다. 이 줄은 관리자 판정이 아니라 Django 관리 화면의 출입문이고, `test_admin_site_needs_staff_too` 가 고정한다.
- 둘째 grep 은 `duty/perms.py` 의 임시 함수 정의와 `duty/services/changes.py` 의 호출 두 줄(68·133)을 낸다. Task 5 가 지운다.

Run: `.venv/bin/pytest -W error -q`

Expected: **831 passed**(824 + 7), 경고 0.

- [ ] **Step 12: 브라우저로 확인한다(CLAUDE.md, PC 1400px·모바일 390px)**

Task 3 Step 17 처럼 `config.test_settings` 로 띄운다. 이 설정은 프로세스마다 빈 임시 DATA_DIR 을 쓰므로 migrate·가짜 데이터·서버를 한 프로세스에서 돌린다. 실명 DB 는 열지 않는다. 스크립트는 저장소 밖 임시 폴더에 둔다.

이 시점의 `tools/help_videos/seed.py` 는 그대로는 돌지 않는다. 고치는 일은 Task 5 몫이므로, serve.py 가 그 전까지 다음 두 가지를 대신 해 준다.
- seed.py 의 부서에는 근무표가 없다. 그래서 입력 그룹이 없고, `depts["MEMS"].managers.add` 가 AttributeError 를 낸다. serve.py 는 부서를 저장할 때 IT 근무표와 순서를 붙인다.
- seed.py 의 `admin` 은 슈퍼유저일 뿐 IT 관리 그룹이 아니다. 그래서 `changes.change_cell(admin, …)` 이 PermissionDenied 를 낸다. serve.py 는 슈퍼유저를 만들 때 IT 관리 그룹에 넣는다.

main 사본에는 `Board` 가 없으므로 serve.py 는 아무것도 하지 않고 seed.py 를 그대로 돌린다.

```bash
W=$(mktemp -d)
cat > $W/serve.py <<'EOF'
"""브라우저 확인용: 임시 DATA_DIR(test_settings)에 가짜 데이터를 넣고 같은 프로세스에서 서버를 띄운다."""
import sys

import django

django.setup()
from django.core.management import call_command  # noqa: E402

call_command("migrate", verbosity=0)
try:
    from duty.models import Board, Department, User
except ImportError:
    pass  # main 사본(근무표 없음): seed.py 그대로
else:
    # seed.py 를 근무표에 맞추는 일은 Task 5. 그 전까지 여기서 부서에 IT 근무표·순서를 주고, 관리자를 IT 관리 그룹에 넣는다
    it = Board.objects.get(code="it")
    _save, _su = Department.save, User.objects.create_superuser

    def save(self, *a, **k):
        if self.board_id is None:
            self.board, self.order = it, ["MEMS", "TMCH", "MD", "UI"].index(self.code)
        _save(self, *a, **k)

    def create_superuser(*a, **k):
        u = _su(*a, **k)
        it.admin_group.user_set.add(u)
        return u

    Department.save, User.objects.create_superuser = save, create_superuser
exec(open("tools/help_videos/seed.py", encoding="utf-8").read())
call_command("runserver", sys.argv[1], use_reloader=False)
EOF
mkdir $W/main && git archive main | tar -x -C $W/main
DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. .venv/bin/python $W/serve.py 127.0.0.1:8795 &   # 이 브랜치
(cd $W/main && DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. $OLDPWD/.venv/bin/python $W/serve.py 127.0.0.1:8796) &   # main
# 확인이 끝나면: kill %1 %2; rm -rf $W
```

계정은 `member`·`manager`·`admin` 이고 비밀번호는 `Demo-pass-123` 이다(seed.py 머리말). 두 주소(8795 이 브랜치, 8796 main)를 나란히 본다.
- 상단 메뉴가 같아야 한다.
  - member: 근무표·내 근무·알림·캘린더·도움말
  - manager: 위에 출근표 입력이 더해진다.
  - admin: 위에 출근표 입력·회차·통계·이력·관리가 더해진다.
- 주간·월간 근무표의 칸 링크와 하루 화면의 [바꾸기]가 같아야 한다. admin 은 지난 날짜에도 보이고, member 는 오늘 이후만 보인다.
- 출근표 입력 목록이 같아야 한다. manager 는 MEMS, admin 은 네 부서다.
- 도움말 영상 목록이 같아야 한다.
- 관리 화면의 부서 목록에서 입력 담당자가 "나담당"(MEMS)이고 나머지는 "(없음)"이어야 한다.
- 관리 화면의 부서 수정 화면은 이 브랜치에만 바뀐 곳이 있다.
  - 근무표·순서 칸이 더해진다.
  - 입력 담당자는 두 칸 선택 위젯이다(main 과 같은 모양).
  - 저장한 뒤 목록의 담당자가 바뀐 대로 보여야 한다.

기대: 관리 화면 부서 수정 화면의 근무표·순서 칸 말고는 글자 하나 다르지 않다. 이 단계는 커밋할 파일이 없다.

- [ ] **Step 13: 커밋**

```bash
git add duty/context.py duty/views/roster.py tests/test_views_manage.py tests/test_views_roster.py
git commit -m "feat: 관리 메뉴와 근무표 칸 편집 판단을 그룹·근무표 기준으로(perms.is_admin·can_edit)"
```

---

**이 작업에서 빼거나 정한 것**
- **통계 메뉴:** 설계 7절대로 `perms.stats_boards(user)`(관리 근무표 중 slot* 정의가 있는 것)가 있을 때만 보인다. 통계 화면도 같은 조건을 써야 하므로, Task 6 `stats_view` 는 `perms.stats_boards(request.user).order_by("id").first()` 를 고르고 `None` 이면 403 이다(Interfaces 참고). 그 전까지 지금 `stats_view` 는 `admin_required` 그대로다.
- **부서 근무표 변경 막기(설계 4.4):** 저장된 부서의 board 칸은 읽기 전용이다. "소속 사람·기록이 있으면 막기"는 Commute·ChangeLog 가 그때의 부서를 남기지 않아(퇴사해 부서가 풀린 사람의 기록은 이 부서와 이어지지 않는다) 정확히 검사할 수 없으므로, 1단계는 아예 바꾸지 못하게 한다. 부서를 다른 근무표로 옮기기는 필요해지면 별도 기능(기록 처리 포함)으로 만든다.
- **새 부서의 출근조 선택지(알려진 한계):** 설계 4.4 는 "그 근무표의 근무조 정의"에서 읽는다. 이 작업은 새 부서일 때 늘 `boards.it_board()` 정의를 보인다(폼을 다시 그리지 않으면 고른 board 를 알 수 없다). 1단계는 근무표가 IT 하나라 같다. Board 를 여러 개 실제로 만드는 3단계에서 고친다.
- **Task 10 에 넘길 것:** 위 알려진 한계(새 부서의 출근조 선택지)를 PR 본문 "결정이 필요한 것"과 ARCHITECTURE "남은 일"에 한 줄씩 적는다.
- **뜻이 바뀌는 곳(설계 9절·216행, 의도한 변경):**
  - 부서 없는 일반 계정은 오늘 이후 칸도 고치지 못한다. 뷰와 서비스(임시 `assert_can_edit_date`) 둘 다다.
  - 스태프는 지난 날짜를 고치지 못한다. 0011 이 옛 스태프를 IT 관리 그룹에 넣었으므로 운영 화면은 같다.
  - 슈퍼유저는 그룹에 들어가야 근무표를 다룬다.
- **알려진 한계(Task 5 가 없앤다):** `tools/help_videos/seed.py` 는 이 작업 뒤 Task 5 전까지 `depts["MEMS"].managers.add` 에서 AttributeError 로 멈춘다. 부서에 근무표가 없어 입력 그룹이 없기 때문이다. 그 줄을 넘겨도 `changes.change_cell(admin, …)` 에서 PermissionDenied 로 멈춘다. 슈퍼유저가 IT 관리 그룹이 아니기 때문이다. Task 5 의 seed.py 교체에서 부서에 `board=it, order=i` 를 주고 `boards.it_board().admin_group.user_set.add(admin)` 을 넣어야 한다. 이 경로는 테스트가 없다. 1단계 PR 은 Task 10 까지 한 번에 합치므로 운영에는 나가지 않는다.
- **지적 반영:**
  - 4: 그룹 권한을 Task 5~7 앞에 두고, 임시 `assert_can_edit_date` 를 남겼다.
  - 5: M2M 삭제·property·DepartmentForm 을 perms 교체와 같은 커밋에 넣었다.
  - 7: DepartmentForm 에 board 칸을 넣었다(필수).
  - 12: roster 는 이미 있는 `board` 를 쓴다.
  - 13: 테스트의 두 번째 근무표는 `Board.save` 가 그룹을 만든다.
  - 17: 문서는 고치지 않았다.
  - 19: manage.py 명령은 `config.test_settings` 로 돌린다.

<!-- 검증 메모(Task 작성자):
- Task 1·3 을 적용한 사본(/tmp/t3v2, 804 passed)을 /tmp/t4v2 로 복사해 Step 1~13 을 그대로 넣어 돌렸다. Task 2 는 없는 사본이라 마이그레이션 이름이 0012_remove_department_managers(의존 0011_boards_data)로 나왔다. Task 2 뒤에는 makemigrations 가 0015 / 0014_delete_controlduty 로 낸다.
- 실패 확인: Step 2 는 14 failed(ERROR 0), Step 9 는 4 failed 로 위 목록과 같았다.
- 통과: Step 6 뒤 818 passed, Step 11 뒤 824 passed, 경고 0. Task 2 의 새 테스트 2개를 더하면 820·826 이다.
- makemigrations --check: No changes detected.
- 일관성 지적 반영(stats_boards·통계 메뉴, DepartmentForm 입력 그룹 이름 검사, 새 테스트 2개)은 사본에서 다시 돌리지 않았다. 숫자는 각각 +1 로 계산했다(15 failed·821, 5 failed·828). 그 뒤 0015 의 부서 이동 테스트와 Task 1 의 이름 제약 테스트를 더해 기대는 16 failed·824·831 이다(Task 3 의 꺼진 근무조 입력 테스트까지 더한 계산값).
- Step 12 serve.py 로 이 사본과 main 사본을 띄워 member·manager·admin 의 상단 메뉴와 주간 화면 /cell/ 링크 수(0·0·70)가 같음을 확인했다.
- 처음 쓴 영상 테스트는 실패 단계에서 200 응답(파일)을 닫지 않았다. 그 ResourceWarning 이 다른 테스트의 ERROR 로 번져서 status() 도우미로 늘 닫게 고쳤다.
-->


---

### Task 5: 그날의 주인·근무표 단위 조회·근무 변경

설계 6.1(그날의 주인)과 6.4(근무 변경)를 1단계 범위에서 구현한다.
- `boards.owner/owners` 를 만들고, 이것을 기준으로 `roster.published_days/find_day/member_schedule` 과 `changes._owner/change_cell/exchange/swap` 이 근무표(board)를 인자로 받는다.
- Task 4 가 남긴 임시 `perms.assert_can_edit_date` 를 지우고, `changes` 가 `perms.assert_can_edit(user, board, d)` 를 부른다(지적 4).
- 사용법 영상 가짜 데이터 `tools/help_videos/seed.py` 를 IT 근무표·그룹 구조로 옮기고 `tests/test_help_seed.py` 로 고정한다(지적 15. 옛 Task 9 의 seed 부분을 여기로 옮겼다).
- 화면 글자, 알림 문구, 링크, 칸 순서는 바뀌지 않는다. 문서는 고치지 않는다(Task 10, 지적 17).

> **전제:** Task 1~4 가 끝나 있다.
> - Task 1: `Board`·`BoardShift`·`Period.board`·`Department.board/order/input_group`, fixture `it_board`·`depts`(board=it, order)·`admin_user`(IT 관리 그룹). 기존 테스트의 저장되는 회차는 모두 `board=it_board` 다(허용 변환 a, 지적 3).
> - Task 2: `DutyAssignment(period, date, cell, member)`. `services/roster.py`·`changes.py` 는 `DutyAssignment` 를 읽는다.
> - Task 3: `shifts.Def/by_key/ordered/cell_label(defs, cell)/SLOT_GROUP_NAME/KEYS/is_slot_cell/weekdays`, `services/boards.py`(`it_board`·`defs`·`board_of`). `views/roster.py` 의 roster·cell·day·me 첫머리에 `board = _board(request.user)` 가 있다(지적 12). `services/roster.py` 는 아직 `LEGACY_DEFS`·`CELLS` 를 쓴다.
> - Task 4: `perms.assert_can_edit(user, board, d)`·`can_edit`·`is_board_admin`·`is_admin`·`managed_departments`. 임시 `perms.assert_can_edit_date(user, d)` 가 있고 `services/changes.py` 68·133행이 그것을 부른다. `Department.managers` 는 property(입력 그룹, 없으면 `User.objects.none()`).
>
> **검증:** Task 1·3·4 사본(/tmp/t4v2)에 Task 2 를 얹은 사본(Task 2 마이그레이션 0012~0014, Task 4 의 `0015_remove_department_managers`)에서 출발했다. 그 사본은 826 passed 다. 아래 단계를 그대로 넣어 돌렸다.
> - 실패 확인: Step 2 는 6 failed, Step 5 는 3 failed, Step 11 은 6 failed, Step 17 은 1 failed 였다. 오류 메시지는 각 단계에 적은 그대로다.
> - 통과: Step 9 는 835 passed, Step 15 는 840 passed, Step 20 은 841 passed 였다. 모두 경고 0개다.
> - 검증 뒤 더한 것(일관성 지적: 근무 변경 창 To 후보 = 그 근무표 부서 재직자, 설계 6.4·7절): Step 5 의 `test_cell_to_options_only_board_members`(회귀 방지용). `_active_members(board, ...)` 는 Task 3 Step 9 가 이미 넣었으므로 이 테스트는 처음부터 통과하고, Step 5 의 실패 수는 그대로 3 이다. 테스트 하나가 늘어 아래 기대 수는 위 검증 수에 1을 더하고, 출발점을 Task 4 끝 831(검증 사본 826 + Task 4 의 일관성 지적 테스트 2 + 0015 마이그레이션 테스트 1 + Task 1 이름 제약 테스트 1 + Task 3 꺼진 근무조 입력 테스트 1)으로 맞춘 값(841·846·847)이다. 실행할 때 이 수로 확인한다.
> - 화면: Step 21 방법으로 이 사본과 main 을 띄웠다. member·admin 으로 주간·월간·하루·내 근무·근무 변경 창(normal·slot0)의 HTML 을 받아 비교했고, 바이트 단위로 같았다.
>
> 마이그레이션은 만들지 않는다. 다음 번호는 그대로 **0016** 이다.
>
> 두 서비스 파일(`services/roster.py`·`services/changes.py`)은 **파일 전체**를 아래 코드로 바꾼다. 앞 작업들의 기계적 변환이 어떤 모양을 남겼든 결과가 같게 하려는 것이다.

**Files:**
- Modify: `duty/services/boards.py`(전체 교체. `it_board`·`defs`·`active_defs`·`board_of` 는 Task 3 그대로 두고, `_ranked`·`owner`·`owners` 와 import 를 더한다)
- Modify(전체 교체): `duty/services/roster.py`
- Modify(전체 교체): `duty/services/changes.py`
- Modify: `duty/perms.py`
  - 14행 `from .services import boards` 삭제
  - 66–68행 임시 `assert_can_edit_date` 삭제(앞의 빈 줄 64–65행 포함)
- Modify: `duty/views/roster.py`(Task 4 상태 줄 번호)
  - 175행 `published_days`
  - 220–221행 `changes.exchange`
  - 230행 `find_day`(cell)
  - 249행 `find_day`(day)
  - 277행 `member_schedule`
  - `_active_members` 정의와 호출 두 곳: 바꾸지 않음(Task 3 이 이미 그 근무표 부서 재직자로 좁혔다)
- Modify(호출 모양만 맞춤. 근무표마다 도는 일은 뒤 작업이 한다):
  - `duty/services/calendar.py`: 18행 import, 82행. 근무표별 캘린더는 Task 8.
  - `duty/services/alarm_runner.py`: 18행 import, 98행. 근무표마다 `plan` 은 Task 8.
  - `duty/services/stats.py`: 7행 import, 37행. `member_stats(board, ...)` 는 Task 7.
- Modify: `tools/help_videos/seed.py`(main 과 같은 상태. 1–63행)
- Create(Test): `tests/test_board_owner.py`, `tests/test_help_seed.py`
- Modify(Test, 허용 변환 c: 헬퍼 호출에 IT 근무표를 인자로. 단언 불변):
  - `tests/test_changes.py`, `tests/test_roster.py`, `tests/test_period_lifecycle.py`, `tests/test_change_notice.py`, `tests/test_roster_prefs.py`
  - `tests/test_perms.py`: `test_past_date_is_admin_only` 를 `assert_can_edit(u, it_board, d)` 로 바꾼다. Task 4 가 더한 임시 함수 테스트 `test_assert_can_edit_date_is_it_board` 는 지운다.
- Modify(Test, 준비 코드 한 줄. 아래 '주의 1'): `tests/test_views_roster.py` 의 `publish_more`

**Interfaces:**
- Consumes:
  - `boards.it_board() -> Board`, `boards.defs(board) -> list[Def]`, `boards.active_defs(board) -> list[Def]`, `boards.board_of(user) -> Board | None`
  - `perms.assert_can_edit(user, board, d) -> None`(남의 근무표면 "이 근무표를 바꿀 권한이 없습니다.", 지난 날짜는 "지난 날짜는 어드민만 수정할 수 있습니다.")
  - `shifts.Def/by_key/ordered/cell_label/is_slot_cell/weekdays/KEYS/SLOT_GROUP_NAME`
  - 모델 `Board`(`save()` 가 "{name} 근무표 관리" 그룹을 만든다), `BoardShift`, `DutyAssignment`, `Period.board`, `Department.board/order/input_group`, `PeriodEvent`
  - fixture `it_board`, `depts`, `make_member`, `admin_user`, `fixed_today`
- Produces:
  - `boards.owner(board, d: date) -> Period | None`
  - `boards.owners(board, start: date | None, end: date | None) -> dict[date, Period]`
    - 평일만 담고, 주인이 없는 날은 빠진다. `None` 은 끝이 없다는 뜻이다.
  - `roster.published_days(board, start: date | None = None, end: date | None = None) -> list[Day]`
    - 주인이 있는 평일을 전부 만든다. 행이 없는 날은 빈 칸으로 넣는다.
    - 주인 회차의 행·기록만 쓴다.
    - 칸 순서는 `ordered(boards.defs(board))`, 곧 KEYS 순이다.
  - `roster.find_day(board, d) -> Day | None`
  - `roster.member_schedule(board, member, start, shown=lambda cell: True) -> list[tuple[date, list[str]]]`
  - `views.roster._active_members(board, depts: list[str] | None = None, types: list[str] | None = None) -> list[User]`
    - 그 근무표 부서(`department__board=board`)의 재직자만. 부서 필터가 비어 있어도(= 전체) 다른 근무표 사람은 나오지 않는다. 서비스 `changes._check_candidate(board, m)` 과 같은 범위다.
  - `changes._owner(board, d) -> Period`: 없으면 `DutyError("배포된 근무표에 없는 날짜입니다.")`
  - `changes.change_cell(user, board, d, cell, before, after) -> list[str]`
  - `changes.exchange(user, board, d, cell, before, after) -> list[str]`
  - `changes.swap(user, board, d, cell_a, a, cell_b, b) -> list[str]`
  - 셋 다 첫 줄이 `perms.assert_can_edit(user, board, d)` 다. 들어오는 사람은 그 근무표 부서 재직자만 받는다. 자격 경고는 정의(`eligible_types`·`eligible_shifts`·`name`)에서 읽는다.
  - `perms.assert_can_edit_date` 는 없어진다. `perms.py` 는 `services.boards` 를 import 하지 않는다.
  - 1단계 호출부 규칙:
    - 정기 알림(`alarm_runner`)과 캘린더는 `published_days` 결과에서 배정이 하나도 없는 날(`any(day.members.values())` 가 거짓)을 걸러 지금 동작을 유지한다.
    - 뷰는 Task 3 의 `board` 변수를 넘긴다.
  - `tools/help_videos/seed.py`
    - 부서 4개(MEMS·TMCH·MD·UI)를 `board=it, order=0..3` 으로, 회차 2개를 `board=it` 로 만든다.
    - manager 는 MEMS 입력 그룹, admin 은 슈퍼유저 + IT 관리 그룹이다.
  - `tests/test_help_seed.py::test_seed_uses_it_board_and_groups`

명령은 저장소 루트에서 실행한다. 실명 DB(`data/`, `*.sqlite3`), `.superpowers/`, `.env` 는 열지 않는다. `manage.py` 를 부르는 곳은 모두 `DJANGO_SETTINGS_MODULE=config.test_settings` 로 띄운다(지적 19). `DUTY_DEBUG=1` 은 쓰지 않는다.

---

- [ ] **Step 1: 그날의 주인 테스트를 쓴다(실패 확인용)**

`tests/test_board_owner.py` 를 새로 만든다. 두 번째 근무표는 `Board.objects.create` 로 만들어 관리 그룹을 `Board.save` 에 맡긴다(지적 13). 그룹 이름 규칙은 한 곳에만 둔다.

```python
"""그날의 주인(설계 6.1)과 근무표 단위 조회·근무 변경: 근무표끼리 서로 영향이 없다. 이름은 모두 가상."""
from datetime import date, datetime, time
from datetime import timezone as dt_timezone

import pytest
from django.core.exceptions import PermissionDenied

from duty import shifts
from duty.errors import DutyError
from duty.models import Board, BoardShift, ChangeLog, Commute, Department, DutyAssignment, Period, PeriodEvent, User
from duty.services import boards, changes
from duty.services.roster import find_day, member_schedule, published_days

S = Period.Status


def d(m, day):
    return date(2026, m, day)


def at(m, day):
    return datetime(2026, m, day, tzinfo=dt_timezone.utc)


def published(board, name, start, end, frm=None, when=None, event=True):
    p = Period.objects.create(board=board, name=name, start_date=start, end_date=end, status=S.PUBLISHED,
                              overwrite_from=frm, published_at=when)
    if event:
        PeriodEvent.objects.create(period=p, from_status=S.GENERATED, to_status=S.PUBLISHED)
    return p


@pytest.fixture
def ops(it_board):
    """가짜 두 번째 근무표 '운영팀'(관리 그룹은 Board.save 가 만든다): 근무조 normal(주간) + 관제 slot0(점검A)."""
    board = Board.objects.create(code="ops", name="운영팀", input_mode="direct")
    BoardShift.objects.create(board=board, key="normal", name="주간", start=time(9), end=time(18))
    BoardShift.objects.create(board=board, key="slot0", name="점검A", start=time(10), end=time(11),
                              eligible_shifts=["normal"], eligible_types=["개발자"])
    return board, Department.objects.create(code="OPS", name="운영", shifts="normal", board=board)


def ops_member(dept, name, type="직원"):
    return User.objects.create_user(f"OPS{User.objects.count():03d}", password="unused-Pw-123", name=name,
                                    department=dept, part="", type=type)


# ── 그날의 주인 ──

def test_owner_is_latest_publish_in_range(it_board):
    a = published(it_board, "A", d(11, 2), d(11, 27), frm=d(11, 2))
    b = published(it_board, "B", d(11, 16), d(12, 11), frm=d(11, 18))
    assert boards.owner(it_board, d(11, 17)) == a  # B 의 덮어쓰기 시작일 전
    assert boards.owner(it_board, d(11, 18)) == b
    assert boards.owner(it_board, d(12, 11)) == b
    assert boards.owner(it_board, d(12, 14)) is None
    assert boards.owner(it_board, d(10, 30)) is None


def test_owner_order_is_publish_event_not_clock(it_board):
    a = published(it_board, "A", d(11, 2), d(11, 27), when=at(11, 30))  # 시계는 늦지만 먼저 배포
    b = published(it_board, "B", d(11, 2), d(11, 27), when=at(11, 1))
    assert boards.owner(it_board, d(11, 10)) == b
    PeriodEvent.objects.create(period=a, from_status=S.GENERATED, to_status=S.PUBLISHED)  # A 를 다시 배포
    assert boards.owner(it_board, d(11, 10)) == a


def test_periods_without_publish_event_are_older(it_board):
    old1 = published(it_board, "옛1", d(11, 2), d(11, 27), when=at(11, 5), event=False)
    published(it_board, "옛2", d(11, 2), d(11, 27), when=at(11, 1), event=False)
    published(it_board, "옛3", d(11, 2), d(11, 27), when=None, event=False)  # published_at 없음 = 가장 오래됨
    assert boards.owner(it_board, d(11, 10)) == old1
    old4 = published(it_board, "옛4", d(11, 2), d(11, 27), when=at(11, 5), event=False)  # 같은 시각이면 pk 순
    assert boards.owner(it_board, d(11, 10)) == old4
    new = published(it_board, "새", d(11, 2), d(11, 27), when=at(10, 1))  # 이벤트 있는 회차가 더 최근
    assert boards.owner(it_board, d(11, 10)) == new


def test_owner_falls_back_to_start_date_and_ignores_unpublished(it_board):
    p = published(it_board, "p", d(11, 9), d(11, 13))  # overwrite_from 비어 있음 = 시작일부터
    Period.objects.create(board=it_board, name="g", start_date=d(11, 9), end_date=d(11, 13), status=S.GENERATED)
    assert boards.owner(it_board, d(11, 9)) == p


def test_owners_covers_weekdays_without_rows(it_board):
    a = published(it_board, "A", d(11, 2), d(11, 13), frm=d(11, 2))
    b = published(it_board, "B", d(11, 9), d(11, 20), frm=d(11, 11))
    assert boards.owners(it_board, d(11, 6), d(11, 23)) == {
        d(11, 6): a, d(11, 9): a, d(11, 10): a,
        d(11, 11): b, d(11, 12): b, d(11, 13): b,
        d(11, 16): b, d(11, 17): b, d(11, 18): b, d(11, 19): b, d(11, 20): b,
    }
    assert boards.owners(it_board, d(11, 19), None) == {d(11, 19): b, d(11, 20): b}  # None = 끝 없음
    assert boards.owners(it_board, d(12, 1), None) == {}


def test_owner_is_per_board(it_board, ops):
    board, _ = ops
    it = published(it_board, "IT", d(11, 9), d(11, 13))
    op = published(board, "운영", d(11, 9), d(11, 13))  # 나중에 배포했지만 다른 근무표
    assert boards.owner(it_board, d(11, 10)) == it
    assert boards.owner(board, d(11, 10)) == op
    assert set(boards.owners(it_board, d(11, 9), d(11, 13)).values()) == {it}
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_board_owner.py -q`
Expected: `6 failed`. 오류는 모두 `AttributeError: module 'duty.services.boards' has no attribute 'owner'` 이다(`owners` 도 같다).

- [ ] **Step 3: `boards.owner`·`owners` 를 구현한다**

`duty/services/boards.py` 를 통째로 바꾼다. 위 세 함수(`it_board`·`defs`·`board_of`)는 Task 3 과 글자 하나 다르지 않다.

```python
"""근무표(Board)와 근무 정의 읽기, 그날의 주인(설계 6.1). 1단계는 IT 근무표 하나."""
from datetime import date

from django.db.models import Exists, F, OuterRef, Subquery
from django.db.models.functions import Coalesce

from ..models import Board, BoardShift, Period, PeriodEvent
from ..shifts import Def, ordered, weekdays


def it_board() -> Board:
    return Board.objects.get(code="it")


def defs(board: Board) -> list[Def]:
    """그 근무표의 근무 정의 전부(꺼진 것 포함: 표시·라벨·지난 행·기록의 이름을 찾는다). KEYS 순."""
    return ordered([
        Def(s.key, s.name, s.start, s.end, tuple(s.eligible_shifts), tuple(s.eligible_types), s.default_alarm, s.active)
        for s in BoardShift.objects.filter(board=board)
    ])


def active_defs(board: Board) -> list[Def]:
    """켜진 정의만(설계 4.3 '끄면 새 입력에서만 빠진다'): 입력 표·CSV 열, 부서 출근조·스케줄·알림 규칙 선택지, 생성."""
    return [x for x in defs(board) if x.active]


def board_of(user) -> Board | None:
    dept = getattr(user, "department", None)  # 익명·부서 없는 계정은 근무표가 없다
    return dept.board if dept else None


def _ranked(board):
    """그 근무표의 배포 회차를 최근 배포 순으로. 배포 순번 = 배포 PeriodEvent 의 id(시계와 무관).
    배포 이벤트가 없는 옛 회차는 이벤트가 있는 회차보다 오래된 것으로 보고, 그들끼리는 published_at(없으면 가장 오래됨), pk 순."""
    ev = PeriodEvent.objects.filter(period=OuterRef("pk"), to_status=Period.Status.PUBLISHED)
    return (
        Period.objects.filter(board=board, status=Period.Status.PUBLISHED)
        .annotate(owns_from=Coalesce("overwrite_from", "start_date"),  # 마이그레이션 전 옛 배포 회차는 비어 있을 수 있다
                  has_publish=Exists(ev),
                  publish_seq=Subquery(ev.order_by("-id").values("id")[:1]))
        .order_by("-has_publish", "-publish_seq", F("published_at").desc(nulls_last=True), "-pk")
    )


def owner(board, d: date) -> Period | None:
    """(근무표, 날짜)의 주인: overwrite_from ≤ d ≤ end_date 인 배포 회차 중 가장 최근에 배포한 것. 배정 행과 무관."""
    return _ranked(board).filter(owns_from__lte=d, end_date__gte=d).first()


def owners(board, start: date | None, end: date | None) -> dict[date, Period]:
    """start~end(None = 끝 없음)의 평일마다 주인. 주인이 없는 날은 빠지고, 배정 없는 날도 들어간다."""
    qs = _ranked(board)
    if start:
        qs = qs.filter(end_date__gte=start)
    if end:
        qs = qs.filter(owns_from__lte=end)
    ranked = list(qs)
    if not ranked:
        return {}
    lo = start or min(p.owns_from for p in ranked)
    hi = end or max(p.end_date for p in ranked)
    out = {}
    for x in weekdays(lo, hi):
        p = next((p for p in ranked if p.owns_from <= x <= p.end_date), None)  # ranked 는 최근 배포 순
        if p is not None:
            out[x] = p
    return out
```

순환 import 는 없다. `boards` 는 `models`·`shifts` 만 import 한다.

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_board_owner.py -q`
Expected: `6 passed`

- [ ] **Step 5: 근무표 단위 조회 테스트를 덧붙인다(실패 확인용)**

`tests/test_board_owner.py` 끝에 덧붙인다.

```python
# ── 근무표 단위 조회 ──

def test_published_days_includes_owned_days_without_rows(it_board, make_member):
    p = published(it_board, "p", d(11, 9), d(11, 10))
    Commute.objects.create(period=p, date=d(11, 9), member=make_member("가"), shift="normal")
    days = published_days(it_board, d(11, 9), d(11, 10))
    assert [x.date for x in days] == [d(11, 9), d(11, 10)]
    assert days[1].period_id == p.pk and not any(days[1].members.values())
    assert list(days[0].cells) == shifts.KEYS  # 칸 순회 순서 = KEYS(알림 hash 불변)


def test_published_days_uses_only_owner_rows(it_board, make_member):
    a = published(it_board, "A", d(11, 9), d(11, 13))
    b = published(it_board, "B", d(11, 11), d(11, 13), frm=d(11, 11))
    ga, na = make_member("가"), make_member("나")
    Commute.objects.create(period=a, date=d(11, 11), member=ga, shift="normal")  # 덮어쓰인 회차의 행
    Commute.objects.create(period=b, date=d(11, 11), member=na, shift="normal")
    ChangeLog.objects.create(period=a, date=d(11, 11), cell="normal", before=None, after=ga)
    day = find_day(it_board, d(11, 11))
    assert day.period_id == b.pk and day.members["normal"] == ["나"] and not day.cells["normal"].changed


def test_published_days_per_board(it_board, ops, make_member):
    board, dept = ops
    it = published(it_board, "IT", d(11, 10), d(11, 10))
    op = published(board, "운영", d(11, 10), d(11, 10))
    Commute.objects.create(period=it, date=d(11, 10), member=make_member("가"), shift="normal")
    oa = ops_member(dept, "운영가")
    Commute.objects.create(period=op, date=d(11, 10), member=oa, shift="normal")
    [iday] = published_days(it_board, d(11, 10), d(11, 10))
    [oday] = published_days(board, d(11, 10), d(11, 10))
    assert iday.members["normal"] == ["가"] and oday.members["normal"] == ["운영가"]
    assert list(oday.cells) == ["normal", "slot0"]  # 그 근무표의 정의만
    assert member_schedule(board, oa, d(11, 10)) == [(d(11, 10), ["주간"])]


def test_cell_to_options_only_board_members(client, it_board, ops, make_member, fixed_today):
    """근무 변경 창 To 후보 = 그 근무표 부서의 재직자(설계 6.4·7절). 부서 필터가 비어(= 전체) 있어도 남의 근무표 사람은 없다."""
    fixed_today(d(11, 10))
    board, dept = ops
    p = published(it_board, "IT", d(11, 10), d(11, 10))
    a = make_member("가", user=True)
    make_member("나")
    Commute.objects.create(period=p, date=d(11, 10), member=a, shift="normal")
    ops_member(dept, "운영가")
    client.force_login(a)
    body = client.get("/cell/2026-11-10/normal/").content.decode()
    assert 'name="after"' in body and "나 · " in body  # 같은 근무표 사람은 To 에 있다
    assert "운영가" not in body
```

Run: `.venv/bin/pytest -W error tests/test_board_owner.py -q`
Expected: `3 failed, 7 passed`. 오류는 다음 두 가지다.
- `TypeError: published_days() takes from 0 to 2 positional arguments but 3 were given`
- `TypeError: find_day() takes 1 positional argument but 2 were given`

`test_cell_to_options_only_board_members` 는 Task 3 이 이미 좁혀 두어 통과한다(회귀 방지용).

- [ ] **Step 6: `duty/services/roster.py` 를 통째로 바꾼다**

지금 코드(Task 3 상태, 바뀌는 곳만 옮겼다):

```python
from ..models import ChangeLog, Commute, DutyAssignment, Period, User
from ..shifts import LEGACY_DEFS, CELLS, cell_label, is_slot_cell
...
def published_days(start: date | None = None, end: date | None = None) -> list[Day]:
    ...  # 행이 있는 날만 Day 를 만들고, 날짜의 회차는 처음 만난 회차(근무표 구분 없음)
def find_day(d: date) -> Day | None:
def member_schedule(member: User, start: date, shown=lambda cell: True) -> ...:
    for day in published_days(start, None):
        labels = [f"장중관제 {cell_label(LEGACY_DEFS, c)}" if is_slot_cell(c) else cell_label(LEGACY_DEFS, c)
                  for c in CELLS if shown(c) and member.name in day.members[c]]
```

바뀐 파일 전체:

```python
"""배포된 근무표 읽기 모델. 화면·통계·알림·캘린더가 공통으로 쓴다."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from django.db.models import F

from ..models import ChangeLog, Commute, DutyAssignment, User
from ..shifts import SLOT_GROUP_NAME, cell_label, is_slot_cell, ordered
from . import boards

Log = tuple[str | None, str | None]


@dataclass
class Cell:
    labels: list[str]
    removed: list[str]
    changed: bool


@dataclass
class Day:
    date: date
    period_id: int
    cells: dict[str, Cell]
    members: dict[str, list[str]]
    replaced: dict[tuple[str, str], str]


def chain(current: list[str], logs: list[Log]) -> tuple[list[str], list[str], dict[str, str]]:
    """ChangeLog 순서대로 표시 라벨을 만든다. A→B 후 B→C 면 'A>B>C', 추가는 '+B', 제거는 removed 목록."""
    label: dict[str, str] = {}
    removed: list[str] = []
    replaced: dict[str, str] = {}
    for before, after in logs:
        prev = label.pop(before, before) if before else None
        if after:
            label[after] = f"{prev}>{after}" if prev else f"+{after}"
            replaced.pop(after, None)
            if before:
                replaced[after] = before
        elif prev:
            removed.append(prev)
    return [label.get(n, n) for n in current], removed, replaced


def published_days(board, start: date | None = None, end: date | None = None) -> list[Day]:
    """그 근무표에서 주인(boards.owners)이 있는 평일마다 Day 하나. 주인 회차의 행·기록만 쓴다(행이 없으면 빈 칸).
    칸 순서 = 정의의 KEYS 순(알림 내용 hash 가 이 순서에 걸려 있다)."""
    owner_id = {d: p.pk for d, p in boards.owners(board, start, end).items()}
    if not owner_id:
        return []
    keys = [x.key for x in ordered(boards.defs(board))]
    rng = {"period_id__in": set(owner_id.values()), "date__gte": min(owner_id), "date__lte": max(owner_id)}

    names: dict[tuple[date, str], list[str]] = defaultdict(list)
    for model, field in ((Commute, "shift"), (DutyAssignment, "cell")):
        rows = model.objects.filter(**rng).order_by("date", "member__username")
        for d, pid, cell, name in rows.values_list("date", "period_id", field, "member__name"):
            if owner_id.get(d) == pid:
                names[(d, cell)].append(name)

    logs: dict[tuple[date, str], list[Log]] = defaultdict(list)
    # 배포 취소 이전 기록(log_floor 이하)은 다시 배포해도 쓰지 않는다(그사이 출근표·생성이 바뀌었을 수 있다)
    rows = (ChangeLog.objects.filter(**rng, id__gt=F("period__log_floor"))
            .order_by("at", "id").values_list("date", "period_id", "cell", "before__name", "after__name"))
    for d, pid, cell, before, after in rows:
        if owner_id.get(d) == pid:  # 덮어쓰인 회차의 이력은 숨긴다
            logs[(d, cell)].append((before, after))

    days = []
    for d in sorted(owner_id):
        cells, members, replaced = {}, {}, {}
        for cell in keys:
            current = names.get((d, cell), [])
            cell_logs = logs.get((d, cell), [])
            labels, removed, rep = chain(current, cell_logs)
            cells[cell] = Cell(labels, removed, bool(cell_logs))
            members[cell] = current
            replaced.update({(cell, name): prev for name, prev in rep.items()})
        days.append(Day(d, owner_id[d], cells, members, replaced))
    return days


def find_day(board, d: date) -> Day | None:
    days = published_days(board, d, d)
    return days[0] if days else None


def member_schedule(board, member: User, start: date, shown=lambda cell: True) -> list[tuple[date, list[str]]]:
    defs = boards.defs(board)
    out = []
    for day in published_days(board, start, None):
        labels = [f"{SLOT_GROUP_NAME} {cell_label(defs, c)}" if is_slot_cell(c) else cell_label(defs, c)
                  for c, names in day.members.items() if shown(c) and member.name in names]
        if labels:
            out.append((day.date, labels))
    return out
```

`Cell`·`Day`·`chain` 은 그대로다.
- `member_schedule` 은 `day.members` 의 순서(KEYS 순)로 돈다. 그래서 라벨 순서는 지금 `CELLS` 순과 같다.
- 근무표에 정의가 없는 키의 행은 읽지 않는다(IT 는 14개 키 전부 정의가 있다).

- [ ] **Step 7: 조회 호출부에 board 를 넘긴다(화면·알림 불변)**

`duty/views/roster.py`: 근무표는 Task 3 이 각 뷰 첫머리에 둔 `board` 변수를 그대로 쓴다(지적 12). 새로 `boards.it_board()` 나 `_board(...)` 를 부르지 않는다.
1. 175행
   - 지금: `    by_date = {d.date: d for d in published_days(first_day, last_day)}`
   - 바꾼 뒤: `    by_date = {d.date: d for d in published_days(board, first_day, last_day)}`
2. 230행
   - 지금: `    ctx = _cell_context(defs, find_day(d), cell, d, depts, types, _active_members(board, depts, types))`
   - 바꾼 뒤: `    ctx = _cell_context(defs, find_day(board, d), cell, d, depts, types, _active_members(board, depts, types))`(`find_day` 인자만 바꾼다)
3. 249행
   - 지금: `    found = find_day(d)`
   - 바꾼 뒤: `    found = find_day(board, d)`
4. 277행
   - 지금: `    items = member_schedule(member, perms.today(), _shown(shifts)) if member else []`
   - 바꾼 뒤: `    items = member_schedule(board, member, perms.today(), _shown(shifts)) if member else []`
   - `me` 의 `board` 는 `_board(request.user)` 이고, `member` 가 있으면 그 사람이 `request.user` 다. 그래서 내 근무표다.
`duty/services/calendar.py`:
- 18행
  - 지금: `from . import roster`
  - 바꾼 뒤: `from . import boards, roster`
- 82행 `    days = roster.published_days(since, None)` 을 아래 두 줄로 바꾼다. 피드는 바로 위 `feed()` 가 부서 있는 재직자만 넘기므로 `board_of(member)` 는 늘 근무표가 있다.

```python
    # 1단계 동작 유지: 배정이 하나도 없는 날은 넣지 않는다(그날 기록이 DTSTAMP 를 바꾸지 않게). 근무표별 캘린더는 Task 8
    days = [d for d in roster.published_days(boards.board_of(member), since, None) if any(d.members.values())]
```

`duty/services/alarm_runner.py`:
- 18행
  - 지금: `from . import alarm_settings`
  - 바꾼 뒤: `from . import alarm_settings, boards`
- 98행 `    dues = plan(specs, published_days(today, today + HORIZON), info,` 를 아래 세 줄로 바꾼다. 뒤따르는 인자 줄(99–102행)은 그대로 둔다.

```python
    # 1단계: IT 근무표 하나. 배정이 없는 날은 넘기지 않는다(빈 보고서 방지, 설계 6.1). 근무표마다 plan 은 Task 8
    days = [d for d in published_days(boards.it_board(), today, today + HORIZON) if any(d.members.values())]
    dues = plan(specs, days, info,
```

`duty/services/stats.py`:
- 7행 `from .roster import published_days` 바로 위에 `from . import boards` 를 더한다.
- 37행
  - 지금: `    days = published_days(start, end)`
  - 바꾼 뒤: `    days = published_days(boards.it_board(), start, end)  # 근무표별 통계(member_stats(board, ...))는 Task 7`
  - 빈 날은 `day.members` 가 모두 빈 목록이라 통계에 아무것도 더하지 않는다.

- [ ] **Step 8: 기존 테스트의 조회 호출을 기계적으로 바꾼다(허용 변환 c, 단언 불변)**

```bash
perl -pi -e 's/\bfind_day\(/find_day(boards.it_board(), /g; s/\bpublished_days\(\)/published_days(boards.it_board())/g; s/\bmember_schedule\(User/member_schedule(boards.it_board(), User/g' tests/test_changes.py tests/test_roster.py tests/test_period_lifecycle.py
```

바뀌는 줄은 `test_changes.py` 5줄(`find_day`), `test_roster.py` 3줄(`published_days()` 2, `member_schedule` 1), `test_period_lifecycle.py` 7줄(`find_day`)이다. `def`·`import` 줄에는 `(` 가 붙지 않아 걸리지 않는다.

import 는 이렇게 고친다.
- `tests/test_changes.py` 8행
  - 지금: `from duty.services import changes`
  - 바꾼 뒤: `from duty.services import boards, changes`
- `tests/test_roster.py` 4행 `from duty.services.roster import chain, member_schedule, published_days` 바로 위에 `from duty.services import boards` 를 더한다.
- `tests/test_period_lifecycle.py` 7행
  - 지금: `from duty.services import periods`
  - 바꾼 뒤: `from duty.services import boards, periods`

`tests/test_views_roster.py` 의 `publish_more`(23–28행)에 준비 코드 한 줄을 더한다('주의 1').

```python
def publish_more(member, *days):
    """world 의 배포 회차에 날짜를 더한다(배포된 근무표가 있는 날만 편집 링크가 생긴다)."""
    p = Period.objects.get()
    p.start_date = min(p.start_date, *days)  # 기간 밖 행은 그날의 주인(설계 6.1)이 없어 보이지 않는다
    p.end_date = date(2026, 12, 31)
    p.save()
    for x in days:
        Commute.objects.create(period=p, date=x, member=member, shift="normal")
```

Run: `.venv/bin/pytest -W error tests/test_board_owner.py tests/test_roster.py tests/test_changes.py tests/test_period_lifecycle.py tests/test_views_roster.py tests/test_calendar_feed.py tests/test_run_alarms.py tests/test_stats.py -q`
Expected: 모두 통과하고, 그중 `test_board_owner.py` 는 10 passed 다.
- 이 시점의 `test_changes.py` 는 `changes` 시그니처가 아직 그대로이고, `find_day` 호출만 바뀐 상태다.
- `publish_more` 줄을 빼면 `test_week_view_default` 하나만 `16 == (5 * 4)` 로 실패한다. 11-09 가 회차 기간 밖이라 빈 날이 되기 때문이다.

- [ ] **Step 9: 전체 테스트**

Run: `.venv/bin/pytest -W error -q`
Expected: `841 passed`(Task 4 끝 831 + 새 10), 경고 0개.

- [ ] **Step 10: 커밋**

```bash
git add duty/services/boards.py duty/services/roster.py duty/views/roster.py duty/services/calendar.py \
  duty/services/alarm_runner.py duty/services/stats.py tests/test_board_owner.py tests/test_changes.py \
  tests/test_roster.py tests/test_period_lifecycle.py tests/test_views_roster.py
git commit -m "$(cat <<'EOF'
feat: 그날의 주인(기간·배포 순번)과 근무표 단위 근무표 조회

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

- [ ] **Step 11: 근무표 단위 근무 변경 테스트를 덧붙인다(실패 확인용)**

`tests/test_board_owner.py` 끝에 덧붙인다.

```python
# ── 근무표 단위 근무 변경 ──

@pytest.fixture
def two(it_board, ops, make_member, fixed_today):
    fixed_today(d(11, 10))
    board, dept = ops
    it = published(it_board, "IT", d(11, 10), d(11, 11))  # pk 가 작다(옛 _owner 는 근무표 구분 없이 pk 순으로 골랐다)
    op = published(board, "운영", d(11, 10), d(11, 11))
    ga = make_member("가", user=True)
    oa, ob = ops_member(dept, "운영가"), ops_member(dept, "운영나")
    Commute.objects.create(period=it, date=d(11, 10), member=ga, shift="normal")
    Commute.objects.create(period=op, date=d(11, 10), member=oa, shift="normal")
    return it, op, ga, oa, ob


def test_change_on_ops_board_uses_ops_owner(two, ops, it_board):
    it, op, ga, oa, ob = two
    board, _ = ops
    changes.change_cell(oa, board, d(11, 10), "normal", oa, ob)
    assert Commute.objects.get(member=ob).period == op
    assert ChangeLog.objects.get().period == op
    assert Commute.objects.get(member=ga).period == it  # IT 근무표는 그대로
    assert find_day(it_board, d(11, 10)).members["normal"] == ["가"]


def test_add_on_owned_day_without_rows(two, ops):
    _, op, _, oa, ob = two
    board, _ = ops
    changes.change_cell(oa, board, d(11, 11), "normal", None, ob)  # 행이 없어도 기간으로 주인이 있다
    assert Commute.objects.get(member=ob, date=d(11, 11)).period == op


def test_other_board_member_cannot_be_assigned(two, it_board):
    _, _, ga, oa, _ = two
    with pytest.raises(DutyError, match="운영가은\\(는\\) 근무표 대상이 아닙니다"):
        changes.change_cell(ga, it_board, d(11, 10), "normal", ga, oa)
    assert not ChangeLog.objects.exists()


def test_other_board_user_cannot_edit(two, it_board):
    _, _, ga, oa, _ = two
    with pytest.raises(PermissionDenied, match="이 근무표를 바꿀 권한이 없습니다"):
        changes.exchange(oa, it_board, d(11, 10), "normal", ga, None)
    assert Commute.objects.filter(member=ga).exists()


def test_cell_must_be_defined_on_board(two, ops):
    _, _, _, oa, ob = two
    board, _ = ops
    with pytest.raises(DutyError, match="알 수 없는 칸"):
        changes.change_cell(oa, board, d(11, 10), "dawn", None, ob)


def test_eligibility_warning_reads_board_defs(two, ops):
    _, op, _, oa, ob = two
    board, dept = ops
    dev = ops_member(dept, "운영개발", type="개발자")
    DutyAssignment.objects.create(period=op, date=d(11, 10), cell="slot0", member=oa)
    w = changes.change_cell(oa, board, d(11, 10), "slot0", oa, dev)
    assert w == ["운영개발의 그날 출근조(없음)는 점검A 관제 자격이 아닙니다."]
    w = changes.change_cell(oa, board, d(11, 10), "slot0", dev, ob)
    assert w == ["운영나은(는) 개발자가 아닙니다.", "운영나의 그날 출근조(없음)는 점검A 관제 자격이 아닙니다."]
```

Run: `.venv/bin/pytest -W error tests/test_board_owner.py -q`
Expected: `6 failed, 10 passed`. 오류는 다음 두 가지다.
- `TypeError: change_cell() takes 5 positional arguments but 6 were given`
- `TypeError: exchange() takes 5 positional arguments but 6 were given`

- [ ] **Step 12: `duty/services/changes.py` 를 통째로 바꾼다**

지금 코드(Task 2 상태, 핵심만):

```python
def _owner(d: date) -> Period:
    p = (Period.objects.filter(status=Period.Status.PUBLISHED)
         .filter(Exists(Commute...date=d)) | Exists(DutyAssignment...date=d)))
         .order_by("pk").first())   # 근무표 구분 없이 행이 있는 회차 중 pk 가 가장 작은 것
def _eligibility_warnings(period, d, slot: int, m):  # CONTROL_SLOTS·DEVELOPER·COMMUTE_SHIFTS 상수
def _check_cell(*cells):  # CELLS 상수
def _check_candidate(m):  # 부서 있음만 확인
def change_cell(user, d, cell, before, after):  perms.assert_can_edit_date(user, d) ...
def exchange(user, d, cell, before, after):     # 권한 검사 없이 위임
def swap(user, d, cell_a, a, cell_b, b):        perms.assert_can_edit_date(user, d) ...
```

바뀐 파일 전체:

```python
from datetime import date

from django.db import transaction

from .. import perms
from ..errors import DutyError
from ..models import ChangeLog, Commute, DutyAssignment, Period, User
from ..shifts import Def, by_key, cell_label, is_slot_cell
from . import boards


def _owner(board, d: date) -> Period:
    p = boards.owner(board, d)  # 그날의 주인(설계 6.1): 기간·배포 순번으로 정한다. 행이 없는 날도 주인이 있다
    if p is None:
        raise DutyError("배포된 근무표에 없는 날짜입니다.")
    return p


def _slot_duties(period: Period, d: date, member: User):
    """그날 그 사람의 장중관제 배정(같은 묶음만. 다른 당번 칸과 섞지 않는다)."""
    return DutyAssignment.objects.filter(period=period, date=d, member=member, cell__startswith="slot")


def _eligibility_warnings(defs: list[Def], period: Period, d: date, cell: str, m: User) -> list[str]:
    df, names = by_key(defs)[cell], {x.key: x.name for x in defs}
    out = []
    if df.eligible_types and m.type not in df.eligible_types:
        out.append(f"{m.name}은(는) {'·'.join(df.eligible_types)}가 아닙니다.")
    shift = Commute.objects.filter(period=period, date=d, member=m).values_list("shift", flat=True).first()
    if shift not in df.eligible_shifts:
        out.append(f"{m.name}의 그날 출근조({names.get(shift, '없음')})는 {df.name} 관제 자격이 아닙니다.")
    return out


def _duty_warnings(defs: list[Def], period: Period, d: date, members) -> list[str]:
    """출근조가 바뀐 사람이 관제 칸을 갖고 있으면 자격을 다시 확인한다(경고만)."""
    out = []
    for m in members:
        if m is None:
            continue
        for duty in _slot_duties(period, d, m):
            out += _eligibility_warnings(defs, period, d, duty.cell, m)
    return out


def _check_cell(defs: list[Def], *cells: str) -> None:
    keys = {x.key for x in defs}
    if any(c not in keys for c in cells):
        raise DutyError("알 수 없는 칸입니다.")


def _check_active(m: User | None) -> None:
    if m is not None and not m.is_active:
        raise DutyError(f"{m.name}은(는) 재직 중이 아닙니다.")


def _check_candidate(board, m: User | None) -> None:
    """새로 들이는 사람은 그 근무표 부서의 재직자만(빼기만은 검사하지 않는다: 부서를 옮긴 사람의 옛 행 정리)."""
    _check_active(m)
    if m is not None and (m.department_id is None or m.department.board_id != board.pk):
        raise DutyError(f"{m.name}은(는) 근무표 대상이 아닙니다.")


@transaction.atomic
def change_cell(user, board, d: date, cell: str, before: User | None, after: User | None) -> list[str]:
    perms.assert_can_edit(user, board, d)
    period = _owner(board, d)
    defs = boards.defs(board)
    _check_cell(defs, cell)
    if (before is None and after is None) or before == after:
        raise DutyError("변경할 내용이 없습니다.")
    _check_candidate(board, after)
    warnings: list[str] = []
    if is_slot_cell(cell):
        if before is None or after is None:
            raise DutyError("관제 칸은 교체만 할 수 있습니다.")
        row = DutyAssignment.objects.filter(period=period, date=d, cell=cell).first()
        if row is None or row.member_id != before.pk:
            raise DutyError(f"{before.name}은(는) 이 칸에 없습니다.")
        row.member = after
        row.save()
        warnings = _eligibility_warnings(defs, period, d, cell, after)
        others = _slot_duties(period, d, after).exclude(cell=cell).order_by("cell")  # slot0~slot9: 글자 순 = 칸 순
        if others:
            labels = ", ".join(cell_label(defs, o.cell) for o in others)
            warnings.append(f"{after.name}은(는) 그날 다른 관제 칸({labels})도 맡고 있습니다.")
    else:
        row = None
        if before is not None:
            row = Commute.objects.filter(period=period, date=d, member=before, shift=cell).first()
            if row is None:
                raise DutyError(f"{before.name}은(는) 이 칸에 없습니다.")
        if after is not None and Commute.objects.filter(period=period, date=d, member=after).exists():
            raise DutyError(f"{after.name}은(는) 그날 이미 다른 출근조에 있습니다. 맞교환을 사용하세요.")
        if row is not None:
            row.delete()
        if after is not None:
            Commute.objects.create(period=period, date=d, member=after, shift=cell)
        warnings = _duty_warnings(defs, period, d, [before, after])
    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell, before=before, after=after)
    return warnings


@transaction.atomic
def exchange(user, board, d: date, cell: str, before: User | None, after: User | None) -> list[str]:
    """근무 변경 창의 저장. 둘 다 있으면 기본은 맞교환: To 가 그날 같은 묶음 다른 칸에 있으면 서로 바꾸고,
    없으면 From 대신 들어간다. 한쪽만 있으면 넣기·빼기(change_cell)."""
    perms.assert_can_edit(user, board, d)
    if before is None or after is None:
        return change_cell(user, board, d, cell, before, after)
    _check_cell(boards.defs(board), cell)
    period = _owner(board, d)
    if is_slot_cell(cell):
        rows = list(_slot_duties(period, d, after).exclude(cell=cell))
        if len(rows) > 1:
            raise DutyError(f"{after.name}은(는) 그날 장중관제가 여러 칸이라 맞바꿀 칸을 정할 수 없습니다. "
                            f"{after.name}의 칸을 눌러 거기서 바꿔 주세요.")
        if DutyAssignment.objects.filter(period=period, date=d, cell=cell, member=after).exists():
            raise DutyError(f"{after.name}은(는) 이미 이 칸에 있습니다.")
        other = rows[0].cell if rows else None
    else:
        other = Commute.objects.filter(period=period, date=d, member=after).values_list("shift", flat=True).first()
    if other == cell:
        raise DutyError(f"{after.name}은(는) 이미 이 칸에 있습니다.")
    if other:
        return swap(user, board, d, cell, before, other, after)
    return change_cell(user, board, d, cell, before, after)


@transaction.atomic
def swap(user, board, d: date, cell_a: str, a: User, cell_b: str, b: User) -> list[str]:
    perms.assert_can_edit(user, board, d)
    period = _owner(board, d)
    defs = boards.defs(board)
    _check_cell(defs, cell_a, cell_b)
    _check_candidate(board, a)  # 퇴사자·다른 근무표 사람을 다른 칸으로 옮기는 것도 새 배정이다
    _check_candidate(board, b)
    if a == b or cell_a == cell_b:
        raise DutyError("서로 다른 두 칸의 서로 다른 사람을 골라 주세요.")
    if is_slot_cell(cell_a) != is_slot_cell(cell_b):
        raise DutyError("출근조끼리 또는 관제 칸끼리만 맞교환할 수 있습니다.")
    warnings: list[str] = []
    if is_slot_cell(cell_a):
        ra = DutyAssignment.objects.filter(period=period, date=d, cell=cell_a, member=a).first()
        rb = DutyAssignment.objects.filter(period=period, date=d, cell=cell_b, member=b).first()
        if ra is None or rb is None:
            raise DutyError("선택한 사람이 해당 칸에 없습니다.")
        ra.delete()
        rb.delete()
        DutyAssignment.objects.create(period=period, date=d, cell=cell_a, member=b)
        DutyAssignment.objects.create(period=period, date=d, cell=cell_b, member=a)
        warnings = _eligibility_warnings(defs, period, d, cell_a, b) + _eligibility_warnings(defs, period, d, cell_b, a)
    else:
        ra = Commute.objects.filter(period=period, date=d, member=a, shift=cell_a).first()
        rb = Commute.objects.filter(period=period, date=d, member=b, shift=cell_b).first()
        if ra is None or rb is None:
            raise DutyError("선택한 사람이 해당 칸에 없습니다.")
        ra.shift, rb.shift = cell_b, cell_a
        ra.save()
        rb.save()
        warnings = _duty_warnings(defs, period, d, [a, b])
    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell_a, before=a, after=b)
    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell_b, before=b, after=a)
    return warnings
```

IT 문구는 그대로다.
- IT 정의가 `eligible_types=("개발자",)` 라서 첫 경고는 "○은(는) 개발자가 아닙니다." 가 된다.
- 근무조 이름과 관제 라벨은 IT 정의 값에서 읽는다. 그 값은 지금 상수와 같다.
- "다른 관제 칸" 경고와 맞교환의 다른 칸 개수 검사는 `_slot_duties`(`cell__startswith="slot"`)로 같은 묶음 안만 본다(설계 6.4). 1단계에는 당번 행이 전부 slot* 이라 결과가 같다.
- `exchange` 첫 줄에도 권한 검사를 둔다. 맞교환·교체로 위임하기 전에 남의 근무표 사용자를 막는다.
- 옛 `_owner` 의 EXISTS 주석(PR #35)이 다루던 성능 문제는 없어진다. 새 `owner` 는 출근·관제 행을 JOIN 하지 않고 그 근무표의 배포 회차만 본다. `has_publish=Exists(...)` 때문에 SQL 에는 `EXISTS` 가 있고 `DISTINCT` 는 없다(Step 14 의 기존 테스트가 고정한다).

- [ ] **Step 13: 임시 권한 함수를 지우고 근무 변경 호출부에 board 를 넘긴다**

`duty/perms.py`:
- 14행 `from .services import boards` 를 지운다. 임시 함수만 쓰던 import 다.
- 파일 끝의 임시 함수(66–68행, 앞의 빈 줄 64–65행 포함)를 지운다. 지울 코드는 다음과 같다.

```python


def assert_can_edit_date(user, d: date) -> None:
    """임시(Task 5 가 지운다): changes 가 아직 근무표를 받지 않아 IT 근무표로 검사한다."""
    assert_can_edit(user, boards.it_board(), d)
```

`duty/views/roster.py` 220–221행:

```python
            result = changes.exchange(request.user, d, cell, _member(None if before == "+" else before),
                                      _member(None if after == "-" else after))
```
→
```python
            result = changes.exchange(request.user, board, d, cell, _member(None if before == "+" else before),
                                      _member(None if after == "-" else after))
```

`tests/test_perms.py`:
- `test_past_date_is_admin_only`(11–17행)를 허용 변환 (c)로 바꾼다. fixture `it_board` 를 더하고, 단언은 그대로 둔다.

```python
def test_past_date_is_admin_only(fixed_today, make_member, admin_user, it_board):
    fixed_today(date(2026, 11, 10))
    m = make_member("가", user=True)
    perms.assert_can_edit(m, it_board, date(2026, 11, 10))  # 오늘은 누구나
    with pytest.raises(PermissionDenied):
        perms.assert_can_edit(m, it_board, date(2026, 11, 9))
    perms.assert_can_edit(admin_user, it_board, date(2026, 11, 9))
```

- 파일 끝의 `test_assert_can_edit_date_is_it_board`(90–95행, Task 4 가 임시 함수용으로 더한 테스트)를 앞의 빈 줄 88–89행과 함께 지운다. 파일은 87행 `    assert not perms.can_edit(a, it_board, date(2026, 11, 10))` 과 줄바꿈 하나로 끝난다. 같은 내용(남의 근무표 사람은 "이 근무표를 바꿀 권한이 없습니다")은 `test_can_edit_own_board_only` 와 `tests/test_board_owner.py::test_other_board_user_cannot_edit` 이 고정한다.

- [ ] **Step 14: 기존 테스트의 근무 변경 호출을 기계적으로 바꾼다(허용 변환 c, 단언 불변)**

```bash
perl -pi -e 's/changes\.(change_cell|exchange|swap)\((\w+(?:\["[^"]+"\])?), /changes.$1($2, boards.it_board(), /g; s/changes\._owner\(/changes._owner(boards.it_board(), /g' tests/test_changes.py tests/test_period_lifecycle.py tests/test_change_notice.py tests/test_roster_prefs.py
```

- 첫 인자 모양은 `m["가"]`·`admin_user`·`a`·`c`·`m["라"]`·`m["다"]` 뿐이다.
- 바뀌는 호출은 52곳이다. `test_changes.py` 38, `test_period_lifecycle.py` 5, `test_change_notice.py` 7, `test_roster_prefs.py` 2.
- 확인: `grep -n "changes\.\(change_cell\|exchange\|swap\|_owner\)(" tests/*.py | grep -v "boards.it_board()\|test_board_owner"` 은 아무것도 내지 않는다.

import 는 이렇게 고친다.
- `tests/test_change_notice.py` 9행
  - 지금: `from duty.services import alarm_settings, change_notice, changes`
  - 바꾼 뒤: `from duty.services import alarm_settings, boards, change_notice, changes`
- `tests/test_roster_prefs.py` 166행(함수 안)
  - 지금: `    from duty.services import changes`
  - 바꾼 뒤: `    from duty.services import boards, changes`
- `tests/test_changes.py`·`tests/test_period_lifecycle.py` 는 Step 8 에서 이미 `boards` 를 import 했다. `test_period_lifecycle.py` 의 함수 안 `from duty.services import changes` 는 그대로 둔다.

`tests/test_changes.py::test_owner_with_many_published_periods` 에서는 쿼리를 잡는 블록의 인자만 블록 밖 변수로 뺀다. 블록 안에서 `boards.it_board()` 를 부르면 그 조회가 첫 쿼리가 되기 때문이다. 단언은 그대로 둔다.

```python
    with CaptureQueriesContext(connection) as q:
        changes._owner(boards.it_board(), ps[-1][1])
```
→
```python
    it = boards.it_board()
    with CaptureQueriesContext(connection) as q:
        changes._owner(it, ps[-1][1])
```

이 테스트의 회차는 모두 하루짜리이고 `overwrite_from` 이 비어 있다(시작일로 본다). `only_control`(12-01, 당번 행만 있음)도 기간으로 주인이 정해지므로 앞쪽 단언도 그대로 맞다.

- [ ] **Step 15: 통과와 남은 이름을 확인한다**

Run:
```bash
.venv/bin/pytest -W error tests/test_board_owner.py tests/test_changes.py tests/test_change_notice.py tests/test_roster_prefs.py tests/test_period_lifecycle.py tests/test_views_roster.py tests/test_perms.py -q
grep -rn --include=*.py "assert_can_edit_date" duty tests tools; echo "exit=$?"
.venv/bin/pytest -W error -q
```
Expected:
- 첫 명령은 모두 통과한다. 그중 `test_board_owner.py` 는 16 passed 다.
- grep 은 출력이 없고 `exit=1` 이다.
- 전체는 `846 passed`(841 + 새 6 − 지운 임시 테스트 1), 경고 0개.

- [ ] **Step 16: 커밋**

```bash
git add duty/services/changes.py duty/perms.py duty/views/roster.py tests/test_board_owner.py tests/test_changes.py \
  tests/test_period_lifecycle.py tests/test_change_notice.py tests/test_roster_prefs.py tests/test_perms.py
git commit -m "$(cat <<'EOF'
feat: 근무 변경을 근무표 단위로(그날의 주인·근무표 권한·대상·정의 기반 자격 경고)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

- [ ] **Step 17: 사용법 영상 가짜 데이터 테스트를 쓴다(실패 확인용, 지적 15)**

`tests/test_help_seed.py` 를 새로 만든다.
- `depts` fixture 는 쓰지 않는다. seed 가 부서를 직접 만들기 때문에, 같이 쓰면 code 가 겹친다.
- seed 는 `manage.py shell < seed.py` 로 도는 스크립트라서 모듈 import 대신 `exec` 로 돌린다.

```python
"""사용법 영상 가짜 데이터(tools/help_videos/seed.py)가 근무표·그룹 구조에서 끝까지 도는지."""
from datetime import date
from pathlib import Path

import pytest

from duty import perms
from duty.models import ChangeLog, Department, DutyAssignment, Period, User

SEED = Path(__file__).resolve().parents[1] / "tools" / "help_videos" / "seed.py"


@pytest.mark.django_db
def test_seed_uses_it_board_and_groups(it_board, fixed_today, capsys):
    fixed_today(date(2026, 11, 11))  # 수요일
    exec(compile(SEED.read_text(encoding="utf-8"), str(SEED), "exec"), {"__name__": "seed"})
    assert capsys.readouterr().out.strip().endswith("seeded")

    assert list(Department.objects.order_by("order").values_list("code", flat=True)) == ["MEMS", "TMCH", "MD", "UI"]
    assert set(Department.objects.values_list("board", flat=True)) == {it_board.pk}
    assert set(Period.objects.values_list("board", flat=True)) == {it_board.pk}

    admin, manager, member = (User.objects.get(username=u) for u in ("admin", "manager", "member"))
    assert perms.is_board_admin(admin, it_board)
    assert not perms.is_admin(manager) and not perms.is_admin(member)
    assert list(perms.managed_departments(manager).values_list("code", flat=True)) == ["MEMS"]
    assert not perms.managed_departments(member).exists()

    now = Period.objects.get(name="이번 회차")
    assert now.status == Period.Status.PUBLISHED
    assert DutyAssignment.objects.filter(period=now, cell__startswith="slot").exists()
    assert ChangeLog.objects.filter(period=now, cell="normal").count() == 1
```

Run: `.venv/bin/pytest -W error tests/test_help_seed.py -q`
Expected: `1 failed`. 오류는 `tools/help_videos/seed.py:28` 의 `depts["MEMS"].managers.add(manager)` 에서 난 `AttributeError: 'QuerySet' object has no attribute 'add'` 다.
- 지금 seed 의 부서에는 근무표가 없어서 입력 그룹이 없다.
- 그래서 `managers` property 가 `User.objects.none()` 을 돌려준다.
- 이 줄을 넘겨도 `changes.change_cell(admin, d, ...)` 가 시그니처 오류로 멈춘다(Step 12 뒤).

- [ ] **Step 18: seed.py 를 IT 근무표·그룹으로 고친다**

`tools/help_videos/seed.py` 를 아래 내용으로 통째로 바꾼다. 바뀌는 곳은 다섯 군데다.
- `boards.it_board()` 로 근무표를 얻는다.
- 부서와 회차에 `board=it` 를 준다. 부서에는 지금 화면의 부서 순서(MEMS·TMCH·MD·UI)대로 `order` 를 준다.
- `managers.add` 대신 `input_group.user_set.add` 를 쓴다. managers property 는 2단계에 사라진다.
- admin 을 IT 관리 그룹에 넣는다. 슈퍼유저라고 자동으로 관리자가 되지 않는다.
- `change_cell` 에 board 를 넘긴다.

나머지 순서는 지금과 같다. 그래서 pk, 아이디, 생성 결과(seed=1)가 main 과 같다. `record.mjs` 는 고치지 않는다(화면·아이디·FREE 이름이 그대로다). GroupKeeper 는 넣지 않는다. 1단계에는 그룹 관리자를 쓰는 화면이 없다.

```python
"""사용법 영상 녹화용 가짜 데이터(실명 없음). record.mjs 가 빈 DUTY_DATA_DIR 에서 `manage.py shell < seed.py` 로 부른다.

계정(비밀번호 모두 Demo-pass-123): member(일반), manager(MEMS 출근표 입력 그룹), admin(슈퍼유저 + IT 근무표 관리 그룹)
"""
from datetime import timedelta

from duty import perms
from duty.models import Commute, Department, Period, User
from duty.services import alarm_settings, boards, changes, generate, publish

PW = "Demo-pass-123"
NAMES = "김가나 이다라 박마바 최사아 정자차 강카타 조파하 윤가람 장나래 임다솜 한라온 오마루 서바다 신사랑 권아름 황자람".split()
FREE = "문하늘 배다온 노은별".split()  # 근무가 없는 사람(근무 바꾸기에서 넣을 수 있게)
SHIFTS = ["normal", "dinner", "normal", "dinner", "normal", "night", "dinner", "dawn"]

it = boards.it_board()  # 마이그레이션이 빈 DB 에도 만들어 둔 IT 당번표
depts = {code: Department.objects.create(code=code, name=code, shifts=sh, board=it, order=i) for i, (code, sh) in enumerate([
    ("MEMS", "dawn,normal,dinner,night"), ("TMCH", "dawn,normal,dinner,night"),
    ("MD", "dawn,normal,dinner,night"), ("UI", "normal,dinner,night")])}
order = list(depts.values())
people = []
for i, n in enumerate(NAMES + FREE):
    d = order[i % 4]
    people.append(User.objects.create_user(f"{d.code}{i:02d}", password=PW, name=n, department=d,
                                           type="직원" if i in (5, 11) else "개발자", help_dismissed=True))
member = User.objects.create_user("member", password=PW, name="나사용", department=depts["MD"], type="개발자", help_dismissed=True)
manager = User.objects.create_user("manager", password=PW, name="나담당", department=depts["MEMS"], type="개발자", help_dismissed=True)
admin = User.objects.create_superuser("admin", password=PW, name="나관리", help_dismissed=True)
depts["MEMS"].input_group.user_set.add(manager)  # 출근표 입력 담당 = 부서 입력 그룹 멤버
it.admin_group.user_set.add(admin)  # 근무표 관리자 = IT 근무표 관리 그룹 멤버(슈퍼유저라고 자동으로 관리자가 아니다)
workers = people[:len(NAMES)] + [member, manager]


def fill(period, who):
    for x in period.dates():
        for i, u in enumerate(who):
            sh = SHIFTS[i % len(SHIFTS)]
            if "dawn" not in u.department.shift_keys() and sh == "dawn":
                sh = "normal"
            Commute.objects.create(period=period, date=x, member=u, shift=sh)


today = perms.today()
mon = today - timedelta(days=today.weekday())
now = Period.objects.create(board=it, name="이번 회차", start_date=mon, end_date=mon + timedelta(days=11),
                            status=Period.Status.CLOSED)
fill(now, workers)
generate.run_generation(now, seed=1, by=admin)
publish.publish(now, mon, by=admin)
d = today if today.weekday() < 5 else mon + timedelta(days=7)
row = Commute.objects.filter(period=now, date=d, shift="normal").exclude(member__in=[member, manager]).first()
changes.change_cell(admin, it, d, "normal", row.member, people[-1])  # 바뀐 칸 표시용

nxt = Period.objects.create(board=it, name="다음 회차", start_date=mon + timedelta(days=14), end_date=mon + timedelta(days=25),
                            status=Period.Status.COLLECTING)
fill(nxt, [u for u in workers if u.department.code != "MEMS"])  # MEMS 는 담당자 영상에서 입력
mems = [u for u in workers if u.department.code == "MEMS"]
for x in nxt.dates()[:-1]:  # 마지막 하루만 비워 둔다
    for i, u in enumerate(mems):
        Commute.objects.create(period=nxt, date=x, member=u, shift=SHIFTS[i % len(SHIFTS)])
# 알림 화면이 "봇 미설정" 안내 대신 평소 모습으로 보이게(가짜 값, 녹화 중 실제 발송·연결은 하지 않는다)
conf = alarm_settings.current()
conf.telegram_bot_token = "1" * 10 + ":" + "DEMO" + "x" * 31
conf.telegram_bot_username = "nxt_duty_demo_bot"
alarm_settings.save(conf)
print("seeded")
```

- [ ] **Step 19: 통과를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_help_seed.py -q`
Expected: `1 passed`

- [ ] **Step 20: 전체 테스트**

Run: `.venv/bin/pytest -W error -q`
Expected: `847 passed`(846 + 새 1), 경고 0개.

- [ ] **Step 21: 브라우저 확인(1단계 화면 불변)**

`config.test_settings` 로 띄워 실명 DB 를 열지 않는다. 이 설정은 프로세스마다 빈 임시 DATA_DIR 을 쓴다. 그래서 migrate·가짜 데이터·서버를 한 프로세스에서 돌린다. 스크립트는 저장소 밖 임시 폴더에 둔다.

이제 seed.py 가 근무표·그룹을 스스로 주므로, Task 3·4 의 serve.py 에 있던 보정 코드(부서에 근무표 붙이기, 관리자를 관리 그룹에 넣기)는 없다. 같은 serve.py 가 main 사본에서도 돈다.

```bash
W=$(mktemp -d)
cat > $W/serve.py <<'EOF'
"""브라우저 확인용: 임시 DATA_DIR(test_settings)에 가짜 데이터를 넣고 같은 프로세스에서 서버를 띄운다."""
import sys

import django

django.setup()
from django.core.management import call_command  # noqa: E402

call_command("migrate", verbosity=0)
exec(open("tools/help_videos/seed.py", encoding="utf-8").read())
call_command("runserver", sys.argv[1], use_reloader=False)
EOF
mkdir $W/main && git archive main | tar -x -C $W/main
DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. .venv/bin/python $W/serve.py 127.0.0.1:8795 &   # 이 브랜치
(cd $W/main && DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. $OLDPWD/.venv/bin/python $W/serve.py 127.0.0.1:8796) &   # main
# 확인이 끝나면: kill %1 %2; rm -rf $W
```

계정은 `member`·`manager`·`admin` 이고 비밀번호는 `Demo-pass-123` 이다(seed.py 머리말). 두 주소(8795 이 브랜치, 8796 main)를 PC 1400px와 모바일 390px에서 나란히 본다.
- 근무표(주·월): 칸 이름, 칸 순서, 바뀐 칸 표시(`>`), 편집 링크
- 하루 화면: 지난 날·오늘의 편집 가능 여부(member 와 admin)
- 근무 변경 창: 맞교환·넣기·빼기 저장 뒤 메시지와 경고 문구(normal 칸, slot0 칸)
- 내 근무: 날짜·라벨("장중관제 …")

기대: 글자·칸 순서·편집 링크가 하나도 다르지 않다.

보조 확인으로 HTML 을 비교할 수 있다. 두 서버에 같은 계정으로 로그인해 `/`, `/?view=month`, `/day/<오늘>/`, `/me/`, `/cell/<오늘>/normal/`, `/cell/<오늘>/slot0/` 을 받는다. csrf 토큰을 지우고 `diff` 하면 차이가 없어야 한다. 검증 때 member·admin 둘 다 차이가 없었다.

- [ ] **Step 22: 커밋**

```bash
git add tools/help_videos/seed.py tests/test_help_seed.py
git commit -m "$(cat <<'EOF'
feat: 사용법 영상 가짜 데이터가 IT 근무표·그룹(관리·입력)을 쓰게

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

---

**주의(오케스트레이터 확인 필요)**

1. **설계 11절 a~d 밖의 준비 코드 수정:** Step 8 에서 `tests/test_views_roster.py::publish_more` 에 `p.start_date = min(p.start_date, *days)` 한 줄을 더한다. 단언은 바꾸지 않는다.
   - 이유: 이 도우미는 회차 시작일(11-10)보다 앞인 11-09·11-02 에 행을 만든다. 6.1 규칙에서는 기간 밖 행에 주인이 없어 보이지 않는다. 실제 배포 경로로는 생길 수 없는 데이터다.
   - 결과: 이 줄이 없으면 `test_week_view_default` 의 `body.count('class="sec"') == 20` 이 16 으로 실패한다.
   - 검증: 이 줄을 넣으면 전체가 통과하고, 빼면 이 테스트 하나만 실패한다. 기존 테스트 전체에서 옛 `_owner`·`published_days` 와 새 주인 규칙이 다른 회차를 고른 경우는 없었다.
2. `perms.assert_can_edit` 은 "부서의 근무표 == board 또는 그 근무표 관리 그룹"만 통과시킨다. 그래서 seed.py 는 admin 을 IT 관리 그룹에 넣은 뒤 근무 변경을 부른다. 같은 줄을 다른 작업(Task 9 관리 화면 등)이 또 넣지 않는다(지적 15).
3. **범위 밖으로 남긴 것:**
   - `change_notice._live`, `publish.preview_publish`, `publish._others` 의 주인 기준 전환: Task 6(배포)·Task 8(알림)
   - 통계·이력의 근무표 거르기(지적 14): Task 6
   - calendar·alarm_runner·stats 의 근무표별 순회: Task 7·8. 이 작업은 호출 모양만 맞추고 1단계 동작을 유지한다.
   - `services/calendar.py` 의 `LEGACY_DEFS`·`CELLS`: Task 8
   - 문서(ARCHITECTURE.md "그날의 주인·근무 변경", 95행 `assert_can_edit_date`): Task 10(지적 17)
4. Task 6 의 board NOT NULL 마이그레이션보다 이 작업의 seed 수정이 앞선다(지적 7). 그래서 Task 6 시점에는 board 없는 부서·회차를 만드는 길이 관리 화면 회차 만들기 하나만 남는다.


---

### Task 6: 근무표 단위 회차·배포·배포 취소·회차 뷰 권한·NOT NULL

이 작업은 설계 다섯 곳을 구현한다.
- 6.1: 겹침 검사, `missing_dates`, 입력 현황(`collect.progress`), `publish._others`, 배포 취소 순서를 근무표 안에서 따진다. 배포 미리보기의 대상 회차와 폐기될 변경 기록 수는 그날의 주인(`boards.owners`)으로 정한다.
- 6.2(목록 부분): 출근표 입력 목록(`views.collect.index`)은 근무표가 같은 회차·부서만 짝짓는다.
- 7절: 회차 목록과 새 회차는 내가 관리하는 근무표만 다룬다. 근무표가 하나면 고르기 칸을 그리지 않는다.
- 9절: `_period(request, pid)` 도우미가 `is_board_admin` 을 검사한다(아니면 404). 이력과 통계도 내가 관리하는 근무표만 보인다(지적 14).
- 10절 1단계 3번: `Period.board`·`Department.board` 를 NOT NULL 로 바꾼다(`0016_boards_not_null`, 지적 7).

근무표가 하나면 사용자 화면은 바이트 하나 바뀌지 않는다. 검증 때 `/periods/`·`/collect/`·`/changes/`·`/stats/`·회차 상세 HTML 이 main 과 같았다(Step 20).

**Files:**
- Modify: `duty/services/periods.py`
  - `save_draft` 의 겹침 검사(25–30행)
  - `missing_dates`(75–84행)
- Modify: `duty/services/collect.py`: `progress`(104–112행)
- Modify: `duty/services/publish.py`
  - import(8–10행)
  - `_others`(30–31행)
  - `preview_publish`(34–46행)
  - `unpublish_info` 의 `top` 조회(86–87행)
  - `publish`·`unpublish` 본문은 건드리지 않는다. 둘 다 `_others` 를 거쳐 근무표 안으로 좁혀진다.
- Modify: `duty/views/manage.py`
  - 새 도우미 `_new_board`·`_period`
  - `period_list`(31–42행)
  - 다섯 회차 뷰의 첫 줄: `period_detail`·`period_action`·`period_delete`·`period_move`·`period_publish`
  - `stats_view`(150–155행)
  - `change_log` 의 첫 쿼리(160행)
- Modify: `duty/templates/duty/periods.html`: 새 회차 폼(5행)
- Modify: `duty/views/collect.py`: `index`(18–27행)
- Modify: `duty/services/stats.py`: import(5–7행), `member_stats`(37–39행)
- Modify: `duty/models.py`: `Department.board`(104–105행), `Period.board`(185–186행)
- Modify: `duty/admin.py`: `DepartmentForm.__init__` 의 `required = True` 줄(36행)
- Create: `duty/migrations/0016_boards_not_null.py`
- Create: `tests/test_boards_periods.py`
- Create: `tests/test_migration_boards_not_null.py`
- Modify(허용 변환 c): `tests/test_stats.py`. `member_stats` 첫 인자로 `boards.it_board()` 를 넘긴다(4곳).
- Modify: `tests/test_boards_models.py`(Task 1 이 만든 테스트). 근무표 없는 부서를 만드는 45행 한 줄을 지운다. main 의 기존 테스트가 아니고, NOT NULL 뒤에는 그런 부서가 있을 수 없다. 대신 `test_board_is_required` 가 그 경우를 고정한다.
- 줄 번호는 Task 1~5 를 적용한 뒤의 코드 기준이다. 어긋나면 함수 이름으로 찾는다.

**Interfaces:**
- Consumes (Task 1~5)
  - 모델: `Board(code, name, input_mode, admin_group)`. `Board.save()` 가 `"{name} 근무표 관리"` 그룹을 만든다.
  - 모델: `BoardShift(board, key, name, start, end, ...)`, `Department.board`·`.order`, `Period.board`(지금은 null 허용), `DutyAssignment(period, date, cell, member)`
  - `duty.services.boards.owners(board, start, end) -> dict[date, Period]`(Task 5)
    - 배포 회차의 `Coalesce(overwrite_from, start_date)` ≤ d ≤ `end_date` 인 평일마다 최근 배포 회차를 준다.
    - 배정 행이 없는 날도 들어간다.
  - `duty.services.boards.defs(board)`(Task 3), `published_days(board, start, end)`(Task 5)
  - `duty.perms`(Task 4): `admin_boards(user)`, `is_board_admin(user, board)`, `is_admin(user)`(`admin_required` 가 쓴다), `managed_departments(user)`
  - `views/manage.change_log` 의 칸 이름: `cell_label(defs[log.period.board_id], ...)`(Task 3)
  - conftest fixture: `it_board`, `depts`(board=it_board), `make_member`, `admin_user`(IT 관리 그룹), `admin_client_ok`
  - 마이그레이션 마지막 번호: `0015_remove_department_managers`(Task 4)
- Produces
  - `periods.save_draft(period, by=None)`: 겹침 검사를 `board_id=period.board_id` 안에서만 한다.
  - `periods.missing_dates(period) -> dict[str, list[date]]`: `period.board` 의 부서만, code 순
  - `collect.progress(period) -> dict[str, tuple[int, int]]`: `period.board` 의 부서만, code 순
  - `publish._others(period)`: 같은 근무표의 다른 배포 회차. 미리보기·배포가 이것을 쓴다.
  - `publish.preview_publish(period, overwrite_from) -> PublishPreview`: 대상 회차 이름과 폐기될 변경 기록 수를 `boards.owners` 로 정한다.
  - `publish.unpublish_info(period)`: "가장 최근 배포"를 근무표마다 따진다.
  - `views.manage._period(request, pid) -> Period`: `select_related("board")`. `is_board_admin` 이 아니면 `Http404`.
  - `views.manage._new_board(post, mine: list[Board]) -> Board`
    - 관리하는 근무표가 하나면 그것을 쓴다. POST `board` 는 무시한다.
    - 여럿이면 POST `board` 를 쓰되, 관리하는 근무표 중에서만 받는다. 없으면 `ValueError`. 화면에는 "이름과 기간을 확인해 주세요."가 나온다.
  - 템플릿 `duty/periods.html` 문맥에 `boards`(내가 관리하는 근무표, id 순)를 더한다. 두 개 이상일 때만 `<select name="board">` 를 그린다.
  - `views.collect.index`: 회차마다 그 근무표의 부서만 짝짓는다. 내 부서가 없는 근무표의 회차는 목록에 나오지 않는다.
  - `views.manage.change_log`: `period__board__in=perms.admin_boards(user)` 로 거른다.
  - `views.manage.stats_view`: `board = perms.stats_boards(request.user).order_by("id").first()`, `None` 이면 403(Task 4 의 `perms.stats_boards`: 관리 근무표 중 slot* 정의가 있는 것)
  - `services.stats.member_stats(board: Board, start: date | None, end: date | None)`
    - 반환 형은 그대로다.
    - `published_days(board, ...)` 를 쓰고, 0회 개발자 목록은 `department__board=board` 로 거른다.
    - 관제 유형을 정의에서 읽는 일과 `period_duty_counts` 는 Task 7 몫이다. Task 7 은 이 시그니처를 그대로 받아 본문을 바꾼다.
  - 마이그레이션 `0016_boards_not_null`: RunPython 으로 board null 인 부서·회차를 IT(code "it")로 채운다(reverse noop). 이어서 AlterField 두 개로 `Department.board`·`Period.board` 를 `null=False` 로 바꾸고 blank 도 뺀다. **다음 번호는 0017.**
  - `DepartmentForm`: board 칸은 Task 4 가 `Meta.fields` 에 넣었다. 이제 모델이 required 를 정하므로 `self.fields["board"].required = True` 줄을 지운다.

---

#### 커밋 1: 서비스(겹침·빈 날·입력 현황·배포·미리보기·배포 취소)

- [ ] **Step 1: 서비스 쪽 두 근무표 테스트를 먼저 쓴다**

`tests/test_boards_periods.py` 를 새로 만든다. `ops` fixture 는 Task 5 의 `tests/test_board_owner.py` 와 같은 방식이다(관리 그룹은 `Board.save` 가 만들고, direct 라 부서 입력 그룹은 없다). 이력 화면 테스트(Step 9)의 칸 이름에 쓰려고 근무 정의 `normal`("주간")을 하나 둔다.

```python
"""근무표 단위 회차·배포·배포 취소(설계 6.1)와 회차·이력·통계 화면 권한(설계 7·9절). 이름은 모두 가상."""
from datetime import date, time

import pytest

from duty.errors import DutyError
from duty.models import Board, BoardShift, ChangeLog, Commute, Department, DutyAssignment, Period, User
from duty.services import collect, periods
from duty.services.publish import preview_publish, publish, unpublish, unpublish_info
from duty.shifts import weekdays

S = Period.Status


def d(m, day):
    return date(2026, m, day)


@pytest.fixture
def ops(it_board):
    """가짜 두 번째 근무표 '운영팀'(관리 그룹은 Board.save 가 만든다)과 그 부서 하나."""
    board = Board.objects.create(code="ops", name="운영팀", input_mode="direct")
    BoardShift.objects.create(board=board, key="normal", name="주간", start=time(9), end=time(18))
    return board, Department.objects.create(code="OPS", name="운영", shifts="normal", board=board)


def ops_member(dept, name="운영가"):
    return User.objects.create_user(f"OPS{User.objects.count() + 1:03d}", password=None, name=name,
                                    department=dept, part="", type="직원")


def make_period(board, name, start, end, status, member, slots=True):
    p = Period.objects.create(board=board, name=name, start_date=start, end_date=end, status=status)
    for x in weekdays(start, end):
        Commute.objects.create(period=p, date=x, member=member, shift="normal")
        if slots:
            DutyAssignment.objects.create(period=p, date=x, cell="slot0", member=member)
    return p


def rows(p):
    c = sorted(Commute.objects.filter(period=p).values_list("date", "member_id", "shift"))
    a = sorted(DutyAssignment.objects.filter(period=p).values_list("date", "member_id", "cell"))
    return c, a


@pytest.fixture
def two(it_board, ops, make_member):
    board, dept = ops
    it = make_period(it_board, "IT회차", d(11, 2), d(11, 27), S.GENERATED, make_member("가"))
    op = make_period(board, "운영회차", d(11, 16), d(12, 11), S.GENERATED, ops_member(dept), slots=False)
    return it, op


# ── 배포·미리보기·배포 취소는 근무표 안에서만 ──

def test_publish_other_board_keeps_it_rows(two):
    it, op = two
    publish(it, d(11, 2))
    before = rows(it)
    publish(op, d(11, 18))
    assert rows(it) == before
    op.refresh_from_db()
    assert op.publish_undo and all(r[1] == op.pk for r in op.publish_undo)  # 지운 행은 이 회차의 S 이전 행뿐


def test_preview_ignores_other_board(two):
    it, op = two
    publish(it, d(11, 2))
    m = Commute.objects.filter(period=it).first().member
    ChangeLog.objects.create(period=it, date=d(11, 19), cell="normal", before=m, after=None)
    pv = preview_publish(op, d(11, 18))
    assert (pv.periods, pv.discarded_changes) == ([], 0)


def test_preview_uses_owner_even_without_rows(it_board, make_member):
    a = make_period(it_board, "A", d(11, 2), d(11, 27), S.GENERATED, make_member("가"))
    b = make_period(it_board, "B", d(11, 16), d(12, 11), S.GENERATED, make_member("나"))
    publish(a, d(11, 2))
    m = Commute.objects.filter(period=a).first().member
    Commute.objects.filter(period=a, date=d(11, 19)).delete()  # 그날 배정을 다 비워도 주인은 A
    DutyAssignment.objects.filter(period=a, date=d(11, 19)).delete()
    ChangeLog.objects.create(period=a, date=d(11, 19), cell="normal", before=m, after=None)
    pv = preview_publish(b, d(11, 18))
    assert (pv.periods, pv.discarded_changes) == (["A"], 1)


def test_unpublish_order_is_per_board(two):
    it, op = two
    publish(it, d(11, 2))
    publish(op, d(11, 18))  # 다른 근무표가 나중에 배포됐어도
    assert unpublish_info(it).blocker is None
    unpublish(it)
    it.refresh_from_db()
    op.refresh_from_db()
    assert (it.status, op.status) == (S.GENERATED, S.PUBLISHED)


# ── 겹침·빈 날·입력 현황은 근무표 안에서만 ──

def test_unpublished_overlap_checked_per_board(it_board, ops):
    board, _ = ops
    periods.save_draft(Period(board=it_board, name="IT", start_date=d(11, 9), end_date=d(11, 30)))
    p = periods.save_draft(Period(board=board, name="운영", start_date=d(11, 20), end_date=d(12, 31)))
    assert p.pk
    with pytest.raises(DutyError, match="겹칩니다: 운영"):
        periods.save_draft(Period(board=board, name="운영2", start_date=d(12, 1), end_date=d(12, 4)))


def test_missing_and_progress_only_own_departments(it_board, ops, depts):
    board, dept = ops
    p = Period.objects.create(board=board, name="운영", start_date=d(11, 9), end_date=d(11, 10))
    Commute.objects.create(period=p, date=d(11, 9), member=ops_member(dept), shift="normal")
    assert periods.missing_dates(p) == {"OPS": [d(11, 10)]}
    assert collect.progress(p) == {"OPS": (1, 2)}
    it = Period.objects.create(board=it_board, name="IT", start_date=d(11, 9), end_date=d(11, 9))
    assert "OPS" not in periods.missing_dates(it) and "OPS" not in collect.progress(it)
    assert set(collect.progress(it)) == {"MEMS", "TMCH", "MD", "UI"}
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `.venv/bin/pytest -W error tests/test_boards_periods.py -q`
Expected: 6 failed. 검증 때 나온 메시지는 다음과 같다.
- `test_publish_other_board_keeps_it_rows`: `AssertionError`. IT 의 11/18~11/27 행이 지워져 `rows(it) != before` 다.
- `test_preview_ignores_other_board`: `assert (['IT회차'], 1) == ([], 0)`
- `test_preview_uses_owner_even_without_rows`: `assert (['A'], 0) == (['A'], 1)`. 행이 없는 날의 기록을 세지 않는다.
- `test_unpublish_order_is_per_board`: `assert '나중에 배포된 회차(운영회차)부터 배포 취소해야 합니다.' is None`
- `test_unpublished_overlap_checked_per_board`: `DutyError: 배포 전 회차와 기간이 겹칩니다: IT`
- `test_missing_and_progress_only_own_departments`: `assert {'MD': [...], ...} == {'OPS': [...]}`. IT 부서 키가 섞인다.

- [ ] **Step 3: `periods.save_draft` 의 겹침 검사를 근무표 안으로 좁힌다**

`duty/services/periods.py` 의 지금 코드:

```python
    clash = (
        Period.objects.exclude(pk=period.pk)
        .exclude(status=S.PUBLISHED)
        .filter(start_date__lte=period.end_date, end_date__gte=period.start_date)
        .first()
    )
```

바뀐 코드:

```python
    clash = (
        Period.objects.exclude(pk=period.pk)
        .exclude(status=S.PUBLISHED)
        .filter(board_id=period.board_id, start_date__lte=period.end_date, end_date__gte=period.start_date)
        .first()
    )
```

- [ ] **Step 4: `periods.missing_dates` 를 그 근무표 부서로 좁힌다**

지금 코드:

```python
def missing_dates(period: Period) -> dict[str, list[date]]:
    have: dict[str, set[date]] = defaultdict(set)
    for code, d in Commute.objects.filter(period=period).values_list("member__department", "date"):
        have[code].add(d)
    out = {}
    for dept in Department.objects.order_by("code"):
        missing = [d for d in period.dates() if d not in have[dept.code]]
        if missing:
            out[dept.code] = missing
    return out
```

바뀐 코드:

```python
def missing_dates(period: Period) -> dict[str, list[date]]:
    """그 근무표 부서마다 출근표가 하나도 없는 평일."""
    have: dict[str, set[date]] = defaultdict(set)
    for code, d in Commute.objects.filter(period=period).values_list("member__department", "date"):
        have[code].add(d)
    out = {}
    for dept in Department.objects.filter(board_id=period.board_id).order_by("code"):
        missing = [d for d in period.dates() if d not in have[dept.code]]
        if missing:
            out[dept.code] = missing
    return out
```

- [ ] **Step 5: `collect.progress` 를 그 근무표 부서로 좁힌다**

`duty/services/collect.py` 의 `progress` 마지막 줄:

```python
    return {d.code: (filled.get(d.code, 0), total) for d in Department.objects.order_by("code")}
```

바뀐 코드(두 줄):

```python
    depts = Department.objects.filter(board_id=period.board_id).order_by("code")
    return {d.code: (filled.get(d.code, 0), total) for d in depts}
```

Run: `.venv/bin/pytest -W error tests/test_boards_periods.py -q -k "overlap or missing"`
Expected: 2 passed

- [ ] **Step 6: `publish._others` 에 근무표 필터를 넣고, 배포 취소 순서를 근무표마다 센다**

`duty/services/publish.py` 의 import 에 `from . import boards` 를 더한다. 모델 import 는 Task 2 뒤의 모양 그대로 둔다(`Commute`·`DutyAssignment` 는 `_MODELS` 가 쓴다).

```python
from ..errors import DutyError
from ..models import ChangeLog, Commute, DutyAssignment, Period, PeriodEvent, User
from . import boards
from .periods import record
```

`_others` 의 지금 코드:

```python
def _others(period: Period):
    return Period.objects.filter(status=S.PUBLISHED).exclude(pk=period.pk)
```

바뀐 코드:

```python
def _others(period: Period):
    # 근무표 필터가 빠지면 다른 근무표를 배포할 때 이 근무표의 같은 기간 행이 지워진다(설계 6.1)
    return Period.objects.filter(status=S.PUBLISHED, board_id=period.board_id).exclude(pk=period.pk)
```

`unpublish_info` 의 지금 코드:

```python
    top = (PeriodEvent.objects.filter(to_status=S.PUBLISHED, period__status=S.PUBLISHED)
           .order_by("-id").select_related("period").first())
```

바뀐 코드:

```python
    top = (PeriodEvent.objects.filter(to_status=S.PUBLISHED, period__status=S.PUBLISHED,
                                      period__board_id=period.board_id)  # 배포 취소 순서는 근무표마다
           .order_by("-id").select_related("period").first())
```

Run: `.venv/bin/pytest -W error tests/test_boards_periods.py -q -k "keeps_it_rows or unpublish_order"`
Expected: 2 passed

- [ ] **Step 7: `preview_publish` 가 그날의 주인(`boards.owners`)을 쓰게 한다**

함수 전체를 바꾼다. 지금 코드:

```python
def preview_publish(period: Period, overwrite_from: date) -> PublishPreview:
    _validate(period, overwrite_from)
    rng = {"date__gte": overwrite_from, "date__lte": period.end_date}
    names = set(Commute.objects.filter(period__in=_others(period), **rng).values_list("period__name", flat=True))
    names |= set(DutyAssignment.objects.filter(period__in=_others(period), **rng).values_list("period__name", flat=True))
    # 이미 덮어써져 행이 없는 날짜의 옛 이력은 세지 않는다
    live = set(Commute.objects.filter(period__in=_others(period), **rng).values_list("period_id", "date"))
    live |= set(DutyAssignment.objects.filter(period__in=_others(period), **rng).values_list("period_id", "date"))
    discarded = sum(
        1 for key in ChangeLog.objects.filter(period__in=_others(period), **rng).values_list("period_id", "date")
        if key in live
    )
    return PublishPreview(overwrite_from, period.end_date, sorted(names), discarded)
```

바뀐 코드:

```python
def preview_publish(period: Period, overwrite_from: date) -> PublishPreview:
    _validate(period, overwrite_from)
    # 덮어쓸 대상 = 범위 안 날짜마다의 주인(설계 6.1). 이 회차는 배포 전이라 주인이 아니다
    own = boards.owners(period.board, overwrite_from, period.end_date)
    # 이미 덮어써져 그날의 주인이 아닌 회차의 옛 이력은 세지 않는다
    discarded = sum(
        1 for pid, d in ChangeLog.objects.filter(
            period__in=_others(period), date__gte=overwrite_from, date__lte=period.end_date,
        ).values_list("period_id", "date")
        if d in own and own[d].pk == pid
    )
    return PublishPreview(overwrite_from, period.end_date, sorted({p.name for p in own.values()}), discarded)
```

`_validate` 가 `status == GENERATED` 를 요구하므로 `period` 는 `owners` 결과에 들어가지 않는다. 그래서 자기 자신을 빼는 조건은 따로 필요 없다.

Run: `.venv/bin/pytest -W error tests/test_boards_periods.py tests/test_publish.py tests/test_period_lifecycle.py tests/test_views_manage.py tests/test_periods.py tests/test_collect.py -q`
Expected: 모두 통과(검증 때 88 passed). 아래 기존 테스트는 단언을 바꾸지 않고 그대로 통과한다.
- `test_preview_counts_discarded_changes`: `["A"]`, 1건
- `test_publish_preview_content`: "옛회차", "사라지는 근무 변경: 1건"

둘 다 `overwrite_from` 이 빈 배포 회차를 쓴다. Task 5 의 `_ranked` 가 `Coalesce(overwrite_from, start_date)` 로 주인을 정하므로 통과한다. 실패하면 이 테스트를 고치지 말고 `boards._ranked` 를 확인한다.

- [ ] **Step 8: 전체 테스트와 커밋**

Run: `.venv/bin/pytest -W error -q`
Expected: `853 passed`(Task 5 끝 847 + 6), 경고 0개.

```bash
git add duty/services/periods.py duty/services/collect.py duty/services/publish.py tests/test_boards_periods.py
git commit -m "$(cat <<'EOF'
feat: 회차 겹침·빈 날·입력 현황·배포·배포 취소 순서를 근무표 단위로, 배포 미리보기는 그날의 주인 기준

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

---

#### 커밋 2: 화면(회차 뷰 권한·새 회차 근무표·출근표 입력 목록·이력·통계)

- [ ] **Step 9: 화면 테스트를 더하고, 통계 테스트에 근무표 인자를 넘긴다(허용 변환 c)**

`tests/test_boards_periods.py` 끝에 덧붙인다.

```python


# ── 회차·출근표 입력·이력·통계 화면: 내가 관리하는 근무표만 ──

@pytest.fixture
def op_period(ops):
    board, _ = ops
    return Period.objects.create(board=board, name="운영회차", start_date=d(11, 9), end_date=d(11, 13),
                                 status=S.GENERATED)


@pytest.fixture
def ops_admin_client(client, ops):
    board, _ = ops
    u = User.objects.create_user("opsadmin", password="unused-Pw-123", name="운영관리")
    u.groups.add(board.admin_group)
    client.force_login(u)
    return client


@pytest.mark.parametrize("method,url", [
    ("get", "/periods/{}/"),
    ("post", "/periods/{}/"),
    ("get", "/periods/{}/publish/"),
    ("post", "/periods/{}/publish/"),
    ("post", "/periods/{}/action/generate/"),
    ("post", "/periods/{}/action/unpublish/"),
    ("post", "/periods/{}/move/"),
    ("post", "/periods/{}/delete/"),
])
def test_period_views_404_for_other_board_admin(admin_client_ok, op_period, method, url):
    r = getattr(admin_client_ok, method)(url.format(op_period.pk))
    assert r.status_code == 404
    assert Period.objects.filter(pk=op_period.pk, status=S.GENERATED, name="운영회차").exists()


def test_period_list_only_my_boards(admin_client_ok, it_board, op_period):
    Period.objects.create(board=it_board, name="IT회차", start_date=d(11, 9), end_date=d(11, 13))
    html = admin_client_ok.get("/periods/").content.decode()
    assert "IT회차" in html and "운영회차" not in html
    assert 'name="board"' not in html  # 근무표가 하나면 고르기 칸을 그리지 않는다


def test_new_period_single_board_ignores_posted_board(admin_client_ok, it_board, ops):
    board, _ = ops
    admin_client_ok.post("/periods/", {"name": "새", "start_date": "2026-12-07", "end_date": "2026-12-11",
                                       "board": board.pk})
    assert Period.objects.get(name="새").board == it_board  # 관리하지 않는 근무표에는 만들 수 없다


def test_new_period_board_choice_for_two_boards(client, admin_user, it_board, ops):
    board, _ = ops
    admin_user.groups.add(board.admin_group)
    client.force_login(admin_user)
    assert 'name="board"' in client.get("/periods/").content.decode()
    client.post("/periods/", {"name": "운영 12월", "start_date": "2026-12-07", "end_date": "2026-12-11",
                              "board": board.pk})
    assert Period.objects.get(name="운영 12월").board == board
    client.post("/periods/", {"name": "고르지 않음", "start_date": "2026-12-07", "end_date": "2026-12-11"})
    assert not Period.objects.filter(name="고르지 않음").exists()


def test_collect_index_skips_other_board_period(admin_client_ok, depts, ops):
    board, _ = ops
    Period.objects.create(board=board, name="운영취합", start_date=d(11, 9), end_date=d(11, 13),
                          status=S.COLLECTING)
    r = admin_client_ok.get("/collect/")
    assert r.status_code == 200 and "운영취합" not in r.content.decode()


def test_change_log_only_my_boards(ops_admin_client, it_board, ops, make_member):
    board, dept = ops
    it = Period.objects.create(board=it_board, name="IT회차", start_date=d(11, 9), end_date=d(11, 9),
                               status=S.PUBLISHED)
    op = Period.objects.create(board=board, name="운영회차", start_date=d(11, 9), end_date=d(11, 9),
                               status=S.PUBLISHED)
    ChangeLog.objects.create(period=it, date=d(11, 9), cell="dawn", before=None, after=make_member("아이티갑"))
    ChangeLog.objects.create(period=op, date=d(11, 9), cell="normal", before=None, after=ops_member(dept, "운영을"))
    html = ops_admin_client.get("/changes/").content.decode()
    assert "운영을" in html and "주간" in html
    assert "아이티갑" not in html and "IT회차" not in html


def test_stats_view_uses_my_board(ops_admin_client, it_board, make_member):
    """관제(slot*) 정의가 없는 근무표의 관리자는 통계를 볼 수 없다(설계 7절). IT 통계가 새지 않는다."""
    p = Period.objects.create(board=it_board, name="IT회차", start_date=d(11, 9), end_date=d(11, 9),
                              status=S.PUBLISHED, overwrite_from=d(11, 9))
    m = make_member("아이티갑")
    Commute.objects.create(period=p, date=d(11, 9), member=m, shift="dawn")
    r = ops_admin_client.get("/stats/")
    assert r.status_code == 403 and "아이티갑" not in r.content.decode()
```

`tests/test_stats.py` 를 허용 변환 (c)로 바꾼다. 단언은 그대로 둔다.
- import 줄 `from duty.models import Board, Commute, DutyAssignment, Period` 바로 아래에 `from duty.services import boards` 를 더한다.
- `member_stats(None, None)` 3곳(`test_member_stats`, `test_departed_member_history_stays_in_stats`, `test_departed_developer_with_only_dawn_night_stays_in_stats`)을 `member_stats(boards.it_board(), None, None)` 으로 바꾼다.
- `member_stats(D2, D2)` 1곳(`test_member_stats_date_range`)을 `member_stats(boards.it_board(), D2, D2)` 로 바꾼다.

한 번에 바꾸는 명령:

```bash
sed -i -e 's/member_stats(None, None)/member_stats(boards.it_board(), None, None)/' \
       -e 's/member_stats(D2, D2)/member_stats(boards.it_board(), D2, D2)/' \
       -e 's/^from duty.models import Board, Commute, DutyAssignment, Period$/&\nfrom duty.services import boards/' \
       tests/test_stats.py
```

- [ ] **Step 10: 테스트가 실패하는지 확인한다**

Run: `.venv/bin/pytest -W error tests/test_boards_periods.py tests/test_stats.py -q`
Expected: 18 failed. 검증 때 나온 메시지는 다음과 같다.
- 404 테스트 8개: `assert 200 == 404`(GET 둘), `assert 302 == 404`(POST 여섯). `delete` 는 회차를 실제로 지운다.
- `test_period_list_only_my_boards`: "운영회차"가 보인다.
- `test_new_period_single_board_ignores_posted_board`: `assert None == <Board: IT 당번표>`. 회차 만들기가 board 를 주지 않는다.
- `test_new_period_board_choice_for_two_boards`: `name="board"` 가 없다.
- `test_collect_index_skips_other_board_period`: 500, `KeyError: 'MD'`. Step 5 뒤 `progress(운영취합)` 에는 OPS 만 있는데 `index` 가 IT 부서 키로 찾는다.
- `test_change_log_only_my_boards`: "아이티갑"이 보인다.
- `test_stats_view_uses_my_board`: `assert 200 == 403`(지금은 누구나 IT 통계를 본다).
- `tests/test_stats.py` 4개: `TypeError: member_stats() takes 2 positional arguments but 3 were given`

- [ ] **Step 11: `views/manage.py` 에 `_new_board`·`_period` 를 넣고 회차 뷰가 쓰게 한다**

import 는 Task 3 상태(`from ..models import Board, ChangeLog, Period`, `from ..services import boards, collect, generate, periods, stats`)를 그대로 쓴다. `Http404`·`get_object_or_404` 도 이미 import 되어 있다.

`_form_period` 는 그대로 두고, 바로 아래에 두 도우미를 더한다.

```python
def _new_board(post, mine: list[Board]) -> Board:
    """새 회차의 근무표: 관리하는 근무표가 하나면 그것, 여럿이면 폼에서 고른 것(내 근무표 중에서만)."""
    if len(mine) == 1:
        return mine[0]
    picked = [b for b in mine if str(b.pk) == post.get("board", "")]
    if not picked:
        raise ValueError("근무표를 고르세요.")
    return picked[0]


def _period(request, pid) -> Period:
    """회차 뷰 공통: 내가 관리하는 근무표의 회차만. 아니면 없는 회차처럼 404(설계 9절)."""
    period = get_object_or_404(Period.objects.select_related("board"), pk=pid)
    if not perms.is_board_admin(request.user, period.board):
        raise Http404
    return period
```

`period_list` 전체를 바꾼다. 지금 코드:

```python
@admin_required
def period_list(request):
    if request.method == "POST":
        try:
            p = periods.save_draft(_form_period(request.POST), by=request.user)
        except (KeyError, ValueError):
            messages.error(request, "이름과 기간을 확인해 주세요.")
        except DutyError as e:
            messages.error(request, str(e))
        else:
            return redirect("period_detail", p.pk)
        return redirect("periods")
    return render(request, "duty/periods.html", {"periods": Period.objects.order_by("-start_date")})
```

바뀐 코드:

```python
@admin_required
def period_list(request):
    mine = list(perms.admin_boards(request.user).order_by("id"))  # admin_required 를 지났으니 비어 있지 않다
    if request.method == "POST":
        try:
            period = _form_period(request.POST)
            period.board = _new_board(request.POST, mine)
            p = periods.save_draft(period, by=request.user)
        except (KeyError, ValueError):
            messages.error(request, "이름과 기간을 확인해 주세요.")
        except DutyError as e:
            messages.error(request, str(e))
        else:
            return redirect("period_detail", p.pk)
        return redirect("periods")
    return render(request, "duty/periods.html", {
        "periods": Period.objects.filter(board__in=mine).order_by("-start_date"), "boards": mine,
    })
```

다섯 뷰(`period_detail`, `period_action`, `period_delete`, `period_move`, `period_publish`)의 첫 줄 `    period = get_object_or_404(Period, pk=pid)` 를 `    period = _period(request, pid)` 로 바꾼다. 나머지 줄은 그대로 둔다.

```bash
sed -i 's/^    period = get_object_or_404(Period, pk=pid)$/    period = _period(request, pid)/' duty/views/manage.py
grep -n "get_object_or_404(Period\|_period(request, pid)" duty/views/manage.py
```

기대: `_period(request, pid)` 가 다섯 줄 나온다. `get_object_or_404(Period` 는 `_period` 안의 `get_object_or_404(Period.objects.select_related("board"), pk=pid)` 한 줄뿐이다.
- `period_detail` 의 POST(기간 고치기)는 `_form_period(request.POST, period)` 를 그대로 쓴다. 기존 회차의 board 는 폼에서 읽지 않으므로 근무표가 바뀌지 않는다.
- `period_action` 에서는 `_period` 가 `action` 검사(Http404)보다 먼저 온다. 관리하지 않는 회차면 어느 action 이든 404 다.

- [ ] **Step 12: 새 회차 폼에 근무표 칸을 넣는다(여럿일 때만)**

`duty/templates/duty/periods.html` 의 지금 코드:

```html
<form method="post" class="search labeled">{% csrf_token %}
  <label>이름 <input name="name" placeholder="예: 2026년 12월" required></label>
```

바뀐 코드:

```html
<form method="post" class="search labeled">{% csrf_token %}{% if boards|length > 1 %}
  <label>근무표 <select name="board" required>{% for b in boards %}<option value="{{ b.pk }}">{{ b.name }}</option>{% endfor %}</select></label>{% endif %}
  <label>이름 <input name="name" placeholder="예: 2026년 12월" required></label>
```

`{% if %}` 를 `{% csrf_token %}` 바로 뒤에 붙인다. 그래야 근무표가 하나일 때 HTML 이 main 과 바이트까지 같다. `{% if %}` 를 따로 한 줄에 두면 공백만 있는 줄이 하나 생긴다(검증 때 확인했다).

- [ ] **Step 13: 출근표 입력 목록이 회차와 같은 근무표의 부서만 짝짓게 한다**

`duty/views/collect.py` 의 `index` 지금 코드:

```python
    items = []
    for p in Period.objects.filter(status=Period.Status.COLLECTING).order_by("start_date"):
        prog = collect.progress(p)
        items.append({"period": p, "depts": [(d, prog[d.code]) for d in depts]})
    return render(request, "duty/collect_index.html", {"items": items})
```

바뀐 코드:

```python
    items = []
    mine = {d.board_id for d in depts}
    for p in Period.objects.filter(status=Period.Status.COLLECTING, board_id__in=mine).order_by("start_date"):
        prog = collect.progress(p)  # 그 회차 근무표의 부서만 있다
        items.append({"period": p, "depts": [(d, prog[d.code]) for d in depts if d.board_id == p.board_id]})
    return render(request, "duty/collect_index.html", {"items": items})
```

근무표가 하나면 목록과 순서가 지금과 같다. 출근표 표 화면의 회차·부서 근무표 짝 검사(`collect._require_input`)와 `is_admin` → `is_board_admin`(services/collect.py `validate_table`, views/collect.py `_render_table`)은 Task 7 몫이다.

- [ ] **Step 14: 이력·통계를 내가 관리하는 근무표로 거른다(지적 14)**

`duty/views/manage.py` 의 `change_log` 첫 줄. 지금 코드:

```python
    qs = ChangeLog.objects.select_related("by", "before", "after", "period").order_by("-at", "-id")
```

바뀐 코드:

```python
    qs = (ChangeLog.objects.filter(period__board__in=perms.admin_boards(request.user))  # 내가 관리하는 근무표만(설계 9절)
          .select_related("by", "before", "after", "period").order_by("-at", "-id"))
```

같은 파일 `stats_view` 의 지금 코드:

```python
    rows, duty_summary, total_summary = stats.member_stats(start, end)
```

바뀐 코드:

```python
    board = perms.stats_boards(request.user).order_by("id").first()  # 관제가 있는 내 근무표 중 첫 것(고르기는 2단계)
    if board is None:
        raise PermissionDenied
    rows, duty_summary, total_summary = stats.member_stats(board, start, end)
```

`views/manage.py` 맨 위 import 에 `from django.core.exceptions import PermissionDenied` 를 더한다(지금 없다).

`duty/services/stats.py` 의 import. 지금 코드:

```python
from ..models import Commute, DutyAssignment, Period, User
from ..shifts import CONTROL_SLOTS, DEVELOPER, TARGET_SPREAD, is_slot_cell
from . import boards
from .roster import published_days
```

바뀐 코드(`boards` 는 더 쓰지 않으므로 뺀다):

```python
from ..models import Board, Commute, DutyAssignment, Period, User
from ..shifts import CONTROL_SLOTS, DEVELOPER, TARGET_SPREAD, is_slot_cell
from .roster import published_days
```

`member_stats` 의 첫 세 줄. 지금 코드:

```python
def member_stats(start: date | None, end: date | None):
    days = published_days(boards.it_board(), start, end)  # 근무표별 통계(member_stats(board, ...))는 Task 7
    stats = {n: MemberStat(n) for n in User.objects.roster().filter(type=DEVELOPER).values_list("name", flat=True)}
```

바뀐 코드(나머지 줄은 그대로):

```python
def member_stats(board: Board, start: date | None, end: date | None):
    days = published_days(board, start, end)
    roster = User.objects.roster().filter(department__board=board, type=DEVELOPER)  # 그 근무표 부서 사람만
    stats = {n: MemberStat(n) for n in roster.values_list("name", flat=True)}
```

`department__board=board` 가 없으면, 다른 근무표 관리자의 통계에 IT 개발자 이름이 0회로 나온다(`test_stats_view_uses_my_board`). IT 부서는 모두 IT 근무표라 IT 통계는 지금과 같다.

- [ ] **Step 15: 통과 확인**

Run: `.venv/bin/pytest -W error tests/test_boards_periods.py tests/test_stats.py tests/test_views_manage.py tests/test_views_collect.py tests/test_collect.py -q`
Expected: 모두 통과(검증 때 78 passed). 아래 기존 테스트도 단언 그대로 통과한다.
- `test_create_period`: board 없이 POST 하면 IT 로 만들어진다(관리하는 근무표가 하나)
- `test_stats_and_changes_pages`, `test_change_log_filters`, `test_change_log_label_from_board_definitions`
- `test_admin_pages_forbidden_for_member`·`test_admin_pages_need_admin_group_not_staff`: 403(`admin_required` 가 먼저 막는다)
- `test_anonymous_redirected_to_login`: 302

- [ ] **Step 16: 전체 테스트와 커밋**

Run: `.venv/bin/pytest -W error -q`
Expected: `867 passed`(853 + 14), 경고 0개.

```bash
git add duty/views/manage.py duty/views/collect.py duty/templates/duty/periods.html duty/services/stats.py tests/test_boards_periods.py tests/test_stats.py
git commit -m "$(cat <<'EOF'
feat: 회차·이력·통계 화면은 내가 관리하는 근무표만, 새 회차는 관리 근무표에, 출근표 입력 목록은 같은 근무표끼리

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

---

#### 커밋 3: `Period.board`·`Department.board` NOT NULL(지적 7)

이 시점에 board 없는 부서·회차를 만드는 길은 없다. 회차 만들기는 Step 11 에서 막혔고, seed.py 는 Task 5 에서, 테스트 준비 코드는 Task 1 에서 고쳤다. 그래도 운영 DB 에는 0011 과 이 마이그레이션 사이에 관리 화면으로 만든 행이 있을 수 있으므로, RunPython 으로 IT 를 채운 뒤 NOT NULL 로 바꾼다.

- [ ] **Step 17: NOT NULL 테스트를 먼저 쓴다**

`tests/test_migration_boards_not_null.py` 를 새로 만든다. 마이그레이션 테스트 틀은 `tests/test_migration_boards.py` 와 같다.

```python
"""회차·부서의 근무표 NOT NULL(설계 10절 1단계 3번): 근무표 없는 회차는 IT 로 채우고, 근무표 없는 부서가 남아 있으면 멈춘다(0015 가 옮겼어야 한다). 이름은 모두 가상."""
from datetime import date

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from duty.models import Department, Period

BEFORE = [("duty", "0015_remove_department_managers")]
AFTER = [("duty", "0016_boards_not_null")]


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()  # 앞선 migrate 로 바뀐 적용 기록을 다시 읽는다
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_apps():
    apps = _migrate(BEFORE)
    yield apps
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())  # 다른 테스트를 위해 최신 스키마로


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_null_board_rows_become_it_and_reverse(old_apps):
    Board = old_apps.get_model("duty", "Board")
    Group = old_apps.get_model("auth", "Group")
    it = Board.objects.filter(code="it").first() or Board.objects.create(
        code="it", name="IT 당번표", input_mode="collect", admin_group=Group.objects.create(name="IT 근무표 관리"))
    pid = old_apps.get_model("duty", "Period").objects.create(
        name="근무표없음", start_date=date(2026, 12, 7), end_date=date(2026, 12, 11)).pk

    apps = _migrate(AFTER)
    assert apps.get_model("duty", "Period").objects.get(pk=pid).board_id == it.pk
    _migrate(BEFORE)  # 되돌리기: 다시 null 허용(채운 값은 그대로)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_null_board_department_stops(old_apps):
    Department = old_apps.get_model("duty", "Department")
    Department.objects.create(code="ZZ", name="무소속부서", shifts="normal")
    with pytest.raises(RuntimeError, match="ZZ"):  # 입력 그룹·담당자 복사는 0015 몫이라 여기서 조용히 채우지 않는다
        _migrate(AFTER)
    Department.objects.filter(code="ZZ").delete()  # fixture 가 최신 스키마로 다시 올릴 수 있게


def test_board_is_required(db):
    with pytest.raises(IntegrityError), transaction.atomic():
        Period.objects.create(name="근무표없음", start_date=date(2026, 12, 7), end_date=date(2026, 12, 11))
    with pytest.raises(IntegrityError), transaction.atomic():
        Department.objects.create(code="ZZ", name="무소속부서", shifts="normal")
```

- [ ] **Step 18: 테스트가 실패하는지 확인한다**

Run: `.venv/bin/pytest -W error tests/test_migration_boards_not_null.py -q`
Expected: 3 failed.
- `test_null_board_rows_become_it_and_reverse`·`test_null_board_department_stops`: `NodeNotFoundError: Node ('duty', '0016_boards_not_null') not a valid node`
- `test_board_is_required`: `Failed: DID NOT RAISE IntegrityError`

- [ ] **Step 19: 모델·마이그레이션·관리 화면 폼을 고친다**

`duty/models.py` 의 `Department.board`. 지금 코드:

```python
    board = models.ForeignKey(Board, on_delete=models.PROTECT, null=True, blank=True, related_name="departments",
                              verbose_name="근무표")
```

바뀐 코드:

```python
    board = models.ForeignKey(Board, on_delete=models.PROTECT, related_name="departments", verbose_name="근무표")
```

`Period.board`. 지금 코드:

```python
    board = models.ForeignKey(Board, on_delete=models.PROTECT, null=True, blank=True, related_name="periods",
                              verbose_name="근무표")
```

바뀐 코드:

```python
    board = models.ForeignKey(Board, on_delete=models.PROTECT, related_name="periods", verbose_name="근무표")
```

`Department.save()` 의 `self.board_id is not None` 검사는 그대로 둔다. 근무표 없이 저장하려 하면 `self.board` 를 읽다가 `RelatedObjectDoesNotExist` 가 나는 대신, DB 의 `IntegrityError` 가 난다(`test_board_is_required`).

`duty/migrations/0016_boards_not_null.py` 를 새로 만든다. 손으로 쓴다. `makemigrations` 는 NOT NULL 전환에서 일회용 기본값을 묻기 때문이다. 모양이 맞는지는 아래 `makemigrations --check` 로 확인한다.

```python
"""회차·부서의 근무표를 NOT NULL 로(설계 10절 1단계 3번). 0011 과 이 마이그레이션 사이에 근무표 없이 생긴 회차는 IT 로 채운다.
근무표 없는 부서는 0015 가 입력 그룹·담당자와 함께 옮겼어야 하므로, 남아 있으면 멈춘다."""
import django.db.models.deletion
from django.db import migrations, models


def fill_it(apps, schema_editor):
    Board = apps.get_model("duty", "Board")
    Department = apps.get_model("duty", "Department")
    Period = apps.get_model("duty", "Period")
    if left := sorted(Department.objects.filter(board=None).values_list("code", flat=True)):
        raise RuntimeError(f"근무표 없는 부서가 남아 있어 멈춥니다: {', '.join(left)}. "
                           "0015 가 옮겼어야 합니다(입력 그룹·담당자 복사). 업그레이드 전 백업으로 롤백한 뒤 업그레이드를 다시 하세요.")
    if not Period.objects.filter(board=None).exists():
        return
    it = Board.objects.get(code="it")  # 0011 이 만든 IT 근무표
    Period.objects.filter(board=None).update(board=it)


class Migration(migrations.Migration):

    dependencies = [
        ("duty", "0015_remove_department_managers"),
    ]

    operations = [
        migrations.RunPython(fill_it, migrations.RunPython.noop),  # 되돌릴 때 채운 값은 그대로 둔다
        migrations.AlterField(
            model_name="department",
            name="board",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="departments",
                                    to="duty.board", verbose_name="근무표"),
        ),
        migrations.AlterField(
            model_name="period",
            name="board",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="periods",
                                    to="duty.board", verbose_name="근무표"),
        ),
    ]
```

`duty/admin.py` 의 `DepartmentForm.__init__` 에서 아래 한 줄을 지운다. 이제 모델 칸이 required 다. board 칸은 Task 4 가 `Meta.fields = ["code", "name", "board", "order", "shifts"]` 에 이미 넣었다.

```python
        self.fields["board"].required = True  # 부서는 근무표 하나에 속한다(DB NOT NULL 은 Task 6)
```

`tests/test_boards_models.py`(Task 1 이 만든 파일)의 `test_department_without_collect_board_has_no_input_group` 에서 근무표 없는 부서를 만드는 줄을 지운다.

```python
    assert Department.objects.create(code="NB", name="무소속", shifts="normal").input_group is None
```

이 줄을 그대로 두면 `IntegrityError: NOT NULL constraint failed: duty_department.board_id` 로 실패한다. main 의 기존 테스트가 아니므로 1단계 단언 불변 원칙과 무관하다. direct 근무표 부서에 입력 그룹이 없다는 앞 줄의 단언은 그대로 남는다.

- [ ] **Step 20: 통과 확인·마이그레이션 검사·화면 비교**

Run:
```bash
DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/pytest -W error tests/test_migration_boards_not_null.py tests/test_boards_models.py tests/test_admin_department.py tests/test_migration_boards.py tests/test_migration_duty_assignment.py -q
.venv/bin/pytest -W error -q
```
Expected:
- `No changes detected`
- 모두 통과
- 전체 `870 passed`(867 + 3), 경고 0개

화면 확인(CLAUDE.md). `config.test_settings` 로 띄워 실명 DB 를 열지 않는다. 같은 프로세스에서 migrate·가짜 데이터·요청을 돌리고, main 사본과 HTML 을 비교한다. 스크립트는 저장소 밖 임시 폴더에 둔다.

```bash
W=$(mktemp -d); echo $W
cat > $W/pages.py <<'EOF'
"""화면 비교용: 임시 DATA_DIR(test_settings)에 가짜 데이터를 넣고 admin 으로 회차·출근표·이력·통계 화면 HTML 을 찍는다."""
import re

import django

django.setup()
from django.core.management import call_command  # noqa: E402
from django.test import Client  # noqa: E402

call_command("migrate", verbosity=0)
exec(open("tools/help_videos/seed.py", encoding="utf-8").read())
from duty.models import Period, User  # noqa: E402

c = Client(HTTP_HOST="localhost")
c.force_login(User.objects.get(username="admin"))  # axes 백엔드는 login() 에 request 를 요구한다
urls = ["/periods/", "/collect/", "/changes/", "/stats/"] + [f"/periods/{p.pk}/" for p in Period.objects.order_by("pk")]
for u in urls:
    r = c.get(u)
    print("=====", u, r.status_code)
    print(re.sub(r'csrfmiddlewaretoken" value="[^"]+"', "CSRF", r.content.decode()))
EOF
mkdir $W/main && git archive main | tar -x -C $W/main
DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. .venv/bin/python $W/pages.py > $W/new.html
(cd $W/main && DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. $OLDPWD/.venv/bin/python $W/pages.py > $W/old.html)
diff $W/old.html $W/new.html && echo SAME
```

Expected: 모든 주소가 200 이고 `SAME` 이 나온다(검증 때 그랬다). 끝나면 `echo` 로 찍힌 임시 폴더 경로를 직접 적어 지운다. 경로 대신 `$W` 를 `rm -rf` 에 넘기지 않는다.

이어서 Task 5 Step 21 의 serve.py 로 이 브랜치(8795)와 main(8796)을 띄운다. admin 으로 PC 1400px·모바일 390px 에서 `/periods/`(근무표 칸 없음), 회차 상세(입력 현황·빈 날), `/collect/`, `/changes/`, `/stats/` 가 나란히 같은지 본다.

배포 미리보기 화면은 seed 에 생성됨 회차가 없어 이 비교에 들어가지 않는다. 미리보기 글자는 기존 `test_publish_preview_content` 가 단언 그대로 지킨다.

- [ ] **Step 21: 커밋**

```bash
git add duty/models.py duty/admin.py duty/migrations/0016_boards_not_null.py tests/test_migration_boards_not_null.py tests/test_boards_models.py
git commit -m "$(cat <<'EOF'
feat: 회차·부서의 근무표를 필수로(비어 있던 행은 IT 로 채우는 마이그레이션 0016)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

---

**이 작업에서 빼는 것(뒤 작업 범위)**
- Task 7(생성·취합·통계)
  - 출근표 표 화면의 회차·부서 근무표 짝 검사: `collect._require_input`. `views/collect._load` 는 그 서비스를 거친다.
  - `is_admin` → `is_board_admin`: services/collect.py `validate_table`, views/collect.py `_render_table`
  - `member_stats` 본문을 관제 정의의 `eligible_types` 기준으로 바꾸는 일. `period_duty_counts` 도 같다.
- Task 8(알림·캘린더): `change_notice._live` 를 주인 기준으로 바꾼다.
- 2단계: 배포 취소 때 "근무 없음" 날 행을 빼는 일, 이력 근무표 열과 필터, 통계 근무표 고르기
- 3단계: direct 근무표 단계 묶음
- Task 10(지적 17): 문서. ARCHITECTURE.md 의 회차·배포 절, 권한 절(`_period`·이력·통계 범위), 마이그레이션 목록(0016)을 고친다.

**검증 기록**
- Task 1~5 를 적용한 사본(841 passed)에 Step 1~21 을 그대로 넣어 돌렸다.
  - 실패 확인: 6 → 18 → 2 failed. 메시지는 위에 적은 그대로 나왔다.
  - 통과: 847 → 861 → 863 passed, 경고 0. `makemigrations --check` 는 `No changes detected`.
- Step 20 의 HTML 비교에서 main 과 차이가 없었다.
  - 처음에는 템플릿의 `{% if %}` 를 따로 한 줄에 둬서, 공백만 있는 줄 하나가 달랐다. Step 12 의 모양으로 고친 뒤 같아졌다.
- 지적 반영
  - 지적 7: 0016 마이그레이션, NOT NULL, DepartmentForm 의 board 칸
  - 지적 10: missing_dates·progress·index 거르기는 이 작업에만 있다. Task 7 은 다시 하지 않는다.
  - 지적 14: 이력·통계 거르기와 테스트 2개
  - 지적 3: 기존 테스트의 board 지정은 Task 1 이 끝냈다. 이 작업에서는 기존 테스트 단언도 준비 코드도 고치지 않았다. `test_stats` 의 인자 (c)만 바꿨다.


---

### Task 7: 생성·취합·통계를 근무 정의로

이 작업은 설계 세 곳을 구현한다.
- 6.3: `generator.generate_control_duty` 가 칸 목록 `[(라벨, 자격 근무조, 자격 유형)]`(유형 빈 튜플 = 전원)을 **필수 인자**로 받는다(기본값 없음). 후보는 칸마다 거른다: 그 칸 자격 근무조에 출근했고 유형이 맞는 사람. 그래서 전역 `developers` 집합 대신 `{유형: 사람 코드 집합}` 을 받는다. `services/generate.run_generation` 은 그 근무표의 켜진 `slot*` 정의로 칸 목록을 만들고, 사람은 그 근무표 부서 재직자다. IT 는 모든 칸이 `("개발자",)` 라 같은 씨앗이면 결과가 지금과 같다. 인덱스와 키를 잇는 일(`slots[i].key`)도 여기서 한다. `slot*` 정의가 없는 근무표는 생성기를 부르지 않는다.
- 6.2: `collect._require_input` 에 `period.board_id == dept.board_id` 검사를 넣는다(CSV 경로도 막힌다). 읽기 경로도 같다: `views/collect._load` 는 짝이 다르면 404, 서비스 `load_table`·`export_csv` 는 같은 `DutyError` 를 낸다. 지난 날짜 판단은 `perms.is_admin` 대신 `perms.is_board_admin(user, period.board)` 로 한다. 고치는 곳은 services/collect.py `validate_table` 과 views/collect.py `_render_table` 두 군데뿐이다.
- 8.3: `stats.member_stats(board, ...)`·`period_duty_counts(period)` 가 그 근무표의 `slot*` 정의(자격 근무조·자격 유형)로 센다. 관제 정의가 없는 근무표는 빈 통계다.

1단계 원칙을 지킨다. IT 화면 글자, CSV 열, 생성 결과(같은 씨앗이면 같은 배정), 통계 숫자는 바뀌지 않는다. 검증 때 Task 6 사본과 이 사본의 `/periods/`·`/collect/`·`/changes/`·`/stats/`·회차 상세·출근표 표·CSV 내려받기 HTML/바이트가 같았다. 1년치 baseline 의 생성 결과 해시도 같았다(Step 5).

**지적 10 반영: 다시 하지 않는 것.** 아래는 앞 작업이 이미 끝냈다. 이 작업은 건드리지 않고, 처음부터 통과하는 중복 테스트도 더하지 않는다.
- `csv_io` 의 names dict, `collect.shift_names`(부서 출근조 순), `_render_table` 머리글: Task 3
- `views/manage._render_detail` 의 `slot_names`(지적 11): Task 3
- `periods.missing_dates`·`collect.progress` 의 근무표 거르기, `views/collect.index` 짝짓기: Task 6
- `stats.member_stats(board, ...)` 시그니처, 0회 명단의 `department__board=board`, `stats_view` 의 근무표 고르기: Task 6

**Files:**
- Modify: `duty/generator.py`
  - 13행 import(+ `Slots` 형 별칭)
  - 37–38행 `_eligible`(칸별 자격 유형)
  - 41–68행 `generate_control_duty` 시그니처와 첫 반복문(지역 변수 `slots` → `pools`, 동작 같음). 70행 `if failures:` 아래와 `_balance`·`_swap_once` 는 그대로 둔다.
- Modify: `duty/services/generate.py`(1–45행 전체)
- Modify: `duty/services/collect.py`
  - `_same_board` 를 새로 두고 `_require_input`(13–17행)·`load_table`·`export_csv` 첫 줄에서 부른다
  - `validate_table` 의 68행 `if not perms.is_admin(user):` 한 줄
- Modify: `duty/views/collect.py`: `_load` 에 근무표 짝 검사(404) 두 줄, `_render_table` 의 41행 한 줄
- Modify: `duty/services/stats.py`
  - import(5–7행)
  - `member_stats` 본문(36–60행)
  - `period_duty_counts`(63–72행)
- Modify: `tests/it_defs.py`: import 한 줄과 `IT_SLOTS` 한 줄
- Modify(허용 변환 c): `tests/test_generator.py`, `tests/test_baseline.py`. 호출에 IT 칸 목록을 인자로 넘기고, 셋째 인자(개발자 집합)를 `{"개발자": …}` 로 감싸고, `CONTROL_SLOTS[i][1]` 을 `IT_SLOTS[i][1]` 로 바꾼다. 단언은 그대로다.
- Modify(새 테스트 3개): `tests/test_generator.py` 끝
- Create: `tests/test_boards_generate.py`(새 테스트 11개)
- 줄 번호는 Task 1~6 을 적용한 뒤의 코드 기준이다. 어긋나면 함수 이름으로 찾는다.

**Interfaces:**
- Consumes (Task 1~6)
  - `duty.shifts`: `slot_defs(defs) -> list[Def]`(키 순), `is_slot_cell(cell)`, `Def.key/.name/.eligible_shifts/.eligible_types`(tuple), `MAX_SWAP_ITERATIONS`·`TARGET_SPREAD`
  - `duty.services.boards.defs(board) -> list[Def]`(Task 3, JSON 칸은 tuple), `active_defs(board)`(켜진 것만. 생성 칸 목록과 생성기 풀 통계가 쓴다)
  - `duty.services.roster.published_days(board, start, end)`(Task 5). `Day.members` 의 키는 그 근무표 정의의 키뿐이다.
  - `duty.perms.is_board_admin(user, board)`, `perms.can_input_department(user, dept)`, `perms.today()`(Task 4)
  - `periods.missing_dates(period)`(Task 6, 그 근무표 부서만)
  - `stats.member_stats(board, start, end)` 시그니처(Task 6)
  - 모델 `Board`(save 가 관리 그룹을 만든다), `BoardShift`, `Department.board`(NOT NULL), `Department.managers` property(입력 그룹), `DutyAssignment`
  - conftest fixture: `it_board`, `depts`, `make_member`, `fixed_today`, `client`
  - `tests/it_defs.py` 의 `IT_DEFS`
- Produces
  - `generator.Slots = list[tuple[str, tuple[str, ...], tuple[str, ...]]]`(라벨, 자격 근무조, 자격 유형. 유형 빈 튜플 = 전원)
  - `generator.generate_control_duty(dates: list[date], commutes: dict[date, dict[str, set[str]]], members_by_type: dict[str, set[str]], seed: int, slots: Slots) -> GenerationOutput`
    - `slots` 는 필수다. 인덱스 i 가 `slots[i]` 이고 `SlotFailure.slot` 도 그 인덱스다.
    - 칸 i 의 그날 후보 = 그 칸 자격 근무조에 출근한 사람 ∩ 그 칸 자격 유형의 사람(빈 튜플이면 `members_by_type` 의 모든 사람).
    - generator 는 더 이상 `CONTROL_SLOTS` 를 쓰지 않는다.
  - `services.generate.run_generation(period, seed=None, by=None) -> GenerationOutput`(시그니처 그대로)
    - 칸 목록 = `slot_defs(boards.active_defs(period.board))`. 저장 키 = `slots[i].key`.
    - 사람 = `User.objects.roster().filter(department__board=period.board)` 를 유형별로 묶은 `{유형: 코드 집합}`. 칸별 유형 거르기는 generator 가 한다.
    - slot 정의가 없으면 `GenerationOutput({}, {}, 0, True)` 를 내고 배정 행은 지운 채 상태만 생성됨으로 바꾼다.
    - `DEVELOPER`·`slot_cell` 을 쓰지 않는다.
  - `services.collect._require_input(user, period, dept)`: 근무표가 다르면 `DutyError("이 회차의 근무표에 속한 부서가 아닙니다.")`. 순서는 권한 → 근무표 → 상태다. `load_table`·`export_csv` 도 같은 검사(`_same_board`)를 먼저 한다.
  - `views.collect._load(request, pid, code)`: 권한 검사 뒤 `period.board_id != dept.board_id` 면 `Http404`(표 화면·저장·CSV 올리기·CSV 내려받기 모두).
  - `services.collect.validate_table`·`views.collect._render_table`: 지난 날짜는 `perms.is_board_admin(user, period.board)` 만 고친다.
  - `services.stats.member_stats(board: Board, start: date | None, end: date | None)`: 반환 형 그대로. 자격 유형 = 그 근무표 slot 정의의 `eligible_types` 합집합. 관제 정의가 없으면 `([], None, None)`.
  - `services.stats.period_duty_counts(period) -> tuple[list[tuple[str, int]], int, bool]`: 모집단 = 그 근무표 부서 재직자 중, 그 회차에서 어느 켜진 slot 정의든 그 칸의 자격 근무조 출근이 있고 그 칸의 자격 유형인 사람(칸별, 생성기 풀과 같다). 배정받은 사람은 퇴사했어도 배정 수로 남는다. 관제 정의가 없으면 `([], 0, True)`.
  - `services/stats.py` 는 `CONTROL_SLOTS`·`DEVELOPER` 를 쓰지 않는다.
  - (테스트 전용) `tests/it_defs.py` 의 `IT_SLOTS: list[tuple[str, tuple[str, ...], tuple[str, ...]]]`
  - (테스트 전용) `tests/test_boards_generate.py` 의 fixture `ops`(근무표, OPS 부서. 정의 normal "주간", slot 없음), `closed_period`, `collecting`, `other_admin`, 헬퍼 `ops_member(dept, name, type)`·`ops_period(board, member, status)`
  - 마이그레이션은 만들지 않는다. 다음 번호는 그대로 **0017**.

---

- [ ] **Step 1: 생성 테스트(변환 c) + 실패하는 새 테스트**

`tests/it_defs.py`:
- 4행 `from duty.shifts import Def` 를 `from duty.shifts import Def, slot_defs` 로 바꾼다.
- 파일 끝(`IT_DEFS` 정의 아래)에 더한다.
```python

IT_SLOTS = [(x.name, x.eligible_shifts, x.eligible_types) for x in slot_defs(IT_DEFS)]  # generator 칸 목록(옛 CONTROL_SLOTS 의 값·순서 + 개발자)
```

`tests/test_generator.py`(허용 변환 c):
- 6행 `from duty.shifts import CONTROL_SLOTS, TARGET_SPREAD, weekdays` 를 아래 두 줄로 바꾼다.
  ```python
  from duty.shifts import TARGET_SPREAD, weekdays
  from tests.it_defs import IT_SLOTS
  ```
- `generate_control_duty(...)` 호출 10곳(20, 30, 35, 41, 42, 47, 56, 64, 77, 109행)마다 셋째 인자(개발자 집합)를 `{"개발자": …}` 로 감싸고, 닫는 괄호 앞에 `, slots=IT_SLOTS` 를 붙인다. 예: `generate_control_duty(DATES, c, {"개발자": DEVS}, seed=1, slots=IT_SLOTS)`, `generate_control_duty(DATES, commutes(), {"개발자": DEVS - {"N0"}}, seed=1, slots=IT_SLOTS)`.
- 25행과 114행의 `CONTROL_SLOTS[i][1]` 을 `IT_SLOTS[i][1]` 로 바꾼다. 단언 기대 값은 그대로 둔다.
- 파일 끝에 새 테스트를 더한다.
```python


def test_it_slots_are_old_control_slots():
    both = ("normal", "dinner")
    middle = ["09:30~10:30", "10:30~11:30", "11:30~12:30", "12:30~13:30",
              "13:30~14:30", "14:30~15:30", "15:30~16:30", "16:30~17:00"]
    dev = ("개발자",)
    assert IT_SLOTS == [("08:30~09:30", ("normal",), dev), *[(x, both, dev) for x in middle],
                        ("17:00~18:00", ("dinner",), dev)]


def test_slots_argument_decides_cells_and_is_required():
    slots = [("A", ("normal",), ("개발자",)), ("B", ("dinner",), ("개발자",))]
    out = generate_control_duty(DATES, commutes(), {"개발자": DEVS}, seed=1, slots=slots)
    for picked in out.assignments.values():
        assert len(picked) == 2 and picked[0] in NORMAL and picked[1] in DINNER
    with pytest.raises(TypeError):
        generate_control_duty(DATES, commutes(), {"개발자": DEVS}, seed=1)  # 기본값 없음


def test_each_slot_filters_its_own_types():
    staff = {"S0", "S1"}
    slots = [("개발", ("normal",), ("개발자",)), ("직원", ("normal",), ("직원",)), ("전원", ("dinner",), ())]
    c = {d: {"normal": set(NORMAL) | staff, "dinner": set(DINNER)} for d in DATES}
    out = generate_control_duty(DATES, c, {"개발자": set(NORMAL), "직원": staff | set(DINNER)}, seed=1, slots=slots)
    for picked in out.assignments.values():
        assert picked[0] in NORMAL and picked[1] in staff and picked[2] in DINNER  # 칸마다 그 칸의 유형만, 빈 튜플 = 전원
```

`tests/test_baseline.py`(허용 변환 c):
- 8행 `from duty.generator import generate_control_duty` 아래에 `from tests.it_defs import IT_SLOTS` 를 더한다.
- 14행을 `    out = generate_control_duty(sorted(days), days, {"개발자": set(data["developers"])}, seed=20261109, slots=IT_SLOTS)` 로 바꾼다.

Create `tests/test_boards_generate.py`. import 는 Step 7·12 에서 쓸 것까지 지금 다 넣는다(모두 이미 있는 이름이다).
```python
"""근무표 단위 관제 생성·출근표 취합·통계(설계 6.2·6.3·8.3). 이름은 모두 가상."""
from datetime import date, time

import pytest

from duty.csv_io import CsvInvalid
from duty.errors import DutyError
from duty.models import Board, BoardShift, Commute, Department, DutyAssignment, Period, User
from duty.services import boards, collect
from duty.services.generate import run_generation
from duty.services.stats import member_stats, period_duty_counts
from duty.shifts import slot_defs
from tests.it_defs import IT_SLOTS

S = Period.Status
NOV9, NOV13 = date(2026, 11, 9), date(2026, 11, 13)
CSV = 'date,새벽,정상,석식교대,야간\n2026-11-09,가,"나,다",,\n'


@pytest.fixture
def ops(it_board):
    """가짜 두 번째 근무표 '운영팀'(관리 그룹은 Board.save 가 만든다)과 그 부서 하나. 장중관제 정의 없음."""
    board = Board.objects.create(code="ops", name="운영팀", input_mode="direct")
    BoardShift.objects.create(board=board, key="normal", name="주간", start=time(9), end=time(18))
    return board, Department.objects.create(code="OPS", name="운영", shifts="normal", board=board)


def ops_member(dept, name="운영가", type="직원"):
    return User.objects.create_user(f"OPS{User.objects.count() + 1:03d}", password=None, name=name,
                                    department=dept, part="", type=type)


def ops_period(board, member, status=S.CLOSED):
    p = Period.objects.create(board=board, name="운영회차", start_date=NOV9, end_date=NOV13, status=status)
    for x in p.dates():
        Commute.objects.create(period=p, date=x, member=member, shift="normal")
    return p


# ── 생성(6.3) ──

@pytest.fixture
def closed_period(make_member, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=NOV9, end_date=NOV13, status=S.CLOSED)
    for i in range(7):
        n, dn = make_member(f"N{i}", dept="MEMS"), make_member(f"D{i}", dept="TMCH")
        for x in p.dates():
            Commute.objects.create(period=p, date=x, member=n, shift="normal")
            Commute.objects.create(period=p, date=x, member=dn, shift="dinner")
    for code in ["MD", "UI"]:
        m = make_member(f"직{code}", dept=code, type="직원")
        for x in p.dates():
            Commute.objects.create(period=p, date=x, member=m, shift="normal")
    return p


def test_it_slot_definitions_are_generator_list(it_board):
    # 같은 씨앗이면 관제 결과가 그대로: 생성기에 넘기는 IT 칸 목록이 옛 CONTROL_SLOTS 와 같다
    assert [(x.name, x.eligible_shifts, x.eligible_types) for x in slot_defs(boards.defs(it_board))] == IT_SLOTS


def test_candidates_come_from_period_board_only(closed_period, ops):
    outsider = ops_member(ops[1], "운영개발", type="개발자")
    for x in closed_period.dates():
        Commute.objects.create(period=closed_period, date=x, member=outsider, shift="normal")
    out = run_generation(closed_period, seed=5)
    assert outsider.username not in out.counts
    assert not DutyAssignment.objects.filter(member=outsider).exists()


def test_board_without_slots_generates_nothing(ops):
    board, dept = ops
    p = ops_period(board, ops_member(dept))
    out = run_generation(p, seed=1)
    p.refresh_from_db()
    assert p.status == S.GENERATED and (out.counts, out.reached) == ({}, True)
    assert not DutyAssignment.objects.filter(period=p).exists()


def test_slot_keys_and_types_come_from_definitions(ops):
    board, dept = ops
    BoardShift.objects.create(board=board, key="slot3", name="점검", start=time(10), end=time(11),
                              eligible_shifts=["normal"], eligible_types=["직원"])
    m = ops_member(dept)
    p = ops_period(board, m)
    run_generation(p, seed=1)
    assert set(DutyAssignment.objects.filter(period=p).values_list("cell", "member")) == {("slot3", m.pk)}
    assert DutyAssignment.objects.filter(period=p).count() == 5
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest -W error tests/test_generator.py tests/test_baseline.py tests/test_boards_generate.py -q`

Expected: `15 failed, 2 passed`.
- 통과: `test_it_slots_are_old_control_slots`, `test_it_slot_definitions_are_generator_list`(이미 맞는 값을 고정하는 회귀 테스트)
- test_generator 12개와 test_baseline 1개: `TypeError: generate_control_duty() got an unexpected keyword argument 'slots'`
- `test_candidates_come_from_period_board_only`: `AssertionError: assert 'OPS017' not in {...}`(지금은 근무표와 상관없이 모든 개발자가 후보다)
- `test_board_without_slots_generates_nothing`, `test_slot_keys_and_types_come_from_definitions`: `GenerationError: 배정할 수 없는 칸 50개`(옛 IT 관제 목록과 개발자 유형으로 돌아 후보가 없다)

- [ ] **Step 3: generator 구현**

`duty/generator.py` 13행:
```python
from .shifts import CONTROL_SLOTS, MAX_SWAP_ITERATIONS, TARGET_SPREAD
```
→
```python
from .shifts import MAX_SWAP_ITERATIONS, TARGET_SPREAD

Slots = list[tuple[str, tuple[str, ...], tuple[str, ...]]]  # (라벨, 자격 근무조, 자격 유형 — 빈 튜플 = 전원). 인덱스 = 칸 번호, 키 변환은 services/generate.py
```
37행 `def _eligible(` 부터 68행 `        assignments[d] = picked` 까지를 아래로 바꾼다. 매개변수 `slots` 와 겹치지 않게 반복문의 지역 변수 `slots` 를 `pools` 로 바꾼다. IT 는 모든 칸의 유형이 `("개발자",)` 라 칸별 후보가 옛 `developers` 거르기와 같고, rng 호출 순서도 같으므로 같은 씨앗이면 결과가 같다. 그 아래(`if failures:` 부터)는 그대로 둔다.
```python
def _allowed(members_by_type: dict[str, set[str]], types: tuple[str, ...]) -> set[str]:
    """칸의 자격 유형에 드는 사람. 빈 튜플 = 전원."""
    return set().union(*(members_by_type.get(t, ()) for t in (types or members_by_type)))


def _eligible(day: dict[str, set[str]], allowed: list[set[str]], slots: Slots) -> list[set[str]]:
    # 칸별 자격 = 그 칸 자격 근무조에 출근 ∧ 그 칸 자격 유형
    return [{m for s in shifts for m in day.get(s, ()) if m in ok} for (_, shifts, _), ok in zip(slots, allowed)]


def generate_control_duty(
    dates: list[date],
    commutes: dict[date, dict[str, set[str]]],
    members_by_type: dict[str, set[str]],
    seed: int,
    slots: Slots,
) -> GenerationOutput:
    rng = random.Random(seed)
    allowed = [_allowed(members_by_type, types) for _, _, types in slots]
    eligible = {d: _eligible(commutes.get(d, {}), allowed, slots) for d in dates}
    counts = {m: 0 for m in sorted({m for d in dates for slot in eligible[d] for m in slot})}
    assignments: dict[date, list[str]] = {}
    failures: list[SlotFailure] = []

    for d in dates:
        pools = eligible[d]
        picked: list[str | None] = [None] * len(pools)
        used: set[str] = set()
        for i in sorted(range(len(pools)), key=lambda i: len(pools[i])):
            candidates = sorted(m for m in pools[i] if m not in used)  # set 순서는 해시에 따라 바뀌므로 정렬 후 섞는다
            if not candidates:
                # 그날 이 칸의 전체 자격자 수(다른 칸에 이미 배정된 사람 포함). 0이면 자격자 없음, N>0이면 N명 전원이 다른 칸에 사용됨.
                failures.append(SlotFailure(d, i, len(pools[i])))
                continue
            rng.shuffle(candidates)
            pick = min(candidates, key=lambda m: counts[m])  # 동점이면 섞인 순서의 첫 번째
            picked[i] = pick
            used.add(pick)
            counts[pick] += 1
        assignments[d] = picked
```

- [ ] **Step 4: 생성 서비스 구현**

`duty/services/generate.py` 전체:
```python
import random
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from ..errors import DutyError
from ..generator import GenerationOutput, generate_control_duty
from ..models import Commute, DutyAssignment, Period, User
from ..shifts import slot_defs
from . import boards
from .periods import missing_dates, record

S = Period.Status


@transaction.atomic  # 검사·입력 읽기·저장을 한 트랜잭션에(IMMEDIATE: 그동안 다른 쓰기는 기다린다)
def run_generation(period: Period, seed: int | None = None, by=None) -> GenerationOutput:
    period.refresh_from_db()
    if period.status not in {S.CLOSED, S.GENERATED}:
        raise DutyError("마감된 회차만 생성할 수 있습니다.")
    missing = missing_dates(period)
    if missing:
        detail = ", ".join(f"{code} {len(ds)}일" for code, ds in missing.items())
        raise DutyError(f"출근표가 비어 있는 날짜가 있습니다: {detail}")
    if seed is None:
        seed = random.SystemRandom().randrange(2**31)

    slots = slot_defs(boards.active_defs(period.board))  # 인덱스 i ↔ 칸 키 slots[i].key. 꺼진 관제는 생성하지 않는다
    if slots:
        commutes: dict = defaultdict(lambda: defaultdict(set))
        for d, shift, code in Commute.objects.filter(period=period).values_list("date", "shift", "member__username"):
            commutes[d][shift].add(code)
        members_by_type: dict = defaultdict(set)  # 그 근무표 부서 재직자. 칸별 유형 거르기는 generator 가 한다
        for typ, code in User.objects.roster().filter(department__board=period.board).values_list("type", "username"):
            members_by_type[typ].add(code)
        out = generate_control_duty(
            period.dates(), commutes, dict(members_by_type), seed,
            [(x.name, x.eligible_shifts, x.eligible_types) for x in slots],
        )  # GenerationError 전파
    else:  # 장중관제 정의가 없는 근무표는 생성기를 부르지 않는다
        out = GenerationOutput({}, {}, 0, True)

    by_code = {m.username: m for m in User.objects.filter(username__in=out.counts)}
    DutyAssignment.objects.filter(period=period).delete()
    DutyAssignment.objects.bulk_create(
        DutyAssignment(period=period, date=d, cell=slots[i].key, member=by_code[code])
        for d, picked in out.assignments.items()
        for i, code in enumerate(picked)
    )
    old = period.status
    period.status, period.seed, period.generated_at = S.GENERATED, seed, timezone.now()
    period.save()
    record(period, old, by, "재생성" if old == S.GENERATED else "")
    return out
```
`views/manage._render_detail` 의 실패 칸 이름(`slot_names[f.slot]`, Task 3)은 같은 `slot_defs` 순서라 인덱스가 맞는다. 고치지 않는다.

- [ ] **Step 5: 통과 확인·같은 씨앗 같은 결과 확인**

Run: `.venv/bin/pytest -W error tests/test_generator.py tests/test_baseline.py tests/test_boards_generate.py tests/test_generate.py tests/test_period_lifecycle.py tests/test_views_manage.py -q`

Expected: 모두 통과한다(검증 때 76 passed. 칸별 유형 테스트를 더해 이제 77 passed).

같은 씨앗이면 결과가 같은지 main 과 비교한다. 스크립트는 저장소 밖 임시 폴더에 둔다.
```bash
W=$(mktemp -d); echo $W
mkdir $W/main && git archive main | tar -x -C $W/main
cat > $W/cmpgen.py <<'EOF'
"""baseline 1년치 출근표로 생성 결과 해시를 찍는다. 인자: 저장소 경로, old(main: slots 인자 없음) | new"""
import hashlib, json, sys
from datetime import date
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from duty.generator import generate_control_duty
data = json.loads((Path(sys.argv[1]) / "tests/fixtures/baseline_commutes.json").read_text())
days = {date.fromisoformat(d): {k: set(v) for k, v in s.items()} for d, s in data["days"].items()}
devs, kw = set(data["developers"]), {}
if sys.argv[2] == "new":
    from tests.it_defs import IT_SLOTS
    devs, kw = {"개발자": devs}, {"slots": IT_SLOTS}  # 칸별 자격 유형(IT 는 모두 개발자)
out = generate_control_duty(sorted(days), days, devs, seed=20261109, **kw)
print(hashlib.sha256(repr(sorted(out.assignments.items())).encode()).hexdigest())
EOF
(cd /tmp && $OLDPWD/.venv/bin/python -I $W/cmpgen.py $W/main old)
(cd /tmp && $OLDPWD/.venv/bin/python -I $W/cmpgen.py $OLDPWD new)
```
Expected: 두 줄의 해시가 같다(검증 때 `02e3ab60…c910` 로 같았다). 끝나면 `echo` 로 찍힌 임시 폴더 경로를 직접 적어 지운다. `$W` 를 `rm -rf` 에 넘기지 않는다.

- [ ] **Step 6: 전체 테스트·커밋**

Run: `.venv/bin/pytest -W error -q`

Expected: `877 passed`(870 + 7), 경고 0개.

```bash
git add duty/generator.py duty/services/generate.py tests/it_defs.py tests/test_generator.py tests/test_baseline.py tests/test_boards_generate.py
git commit -m "$(cat <<'EOF'
feat: 관제 생성을 근무표의 관제 정의로(칸 목록 필수 인자, 후보는 칸마다 자격 근무조·자격 유형으로)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

- [ ] **Step 7: 취합 실패 테스트**

`tests/test_boards_generate.py` 끝에 더한다.
```python


# ── 출근표 취합(6.2) ──

@pytest.fixture
def collecting(depts, make_member, fixed_today, it_board):
    fixed_today(date(2026, 11, 1))
    p = Period.objects.create(board=it_board, name="p", start_date=NOV9, end_date=NOV13, status=S.COLLECTING)
    mgr = make_member("담당", user=True)
    depts["MEMS"].managers.add(mgr)
    for n in ["가", "나", "다"]:
        make_member(n)
    return p, depts["MEMS"], mgr


def test_department_of_other_board_rejected(collecting, ops, make_member):
    p, _, _ = collecting
    board, dept = ops
    ops_admin = make_member("운영관리", user=True)
    board.admin_group.user_set.add(ops_admin)  # 운영팀 부서는 입력할 수 있다
    with pytest.raises(DutyError, match="이 회차의 근무표에 속한 부서가 아닙니다"):
        collect.apply_table(ops_admin, p, dept, {})
    with pytest.raises(DutyError):
        collect.apply_csv(ops_admin, p, dept, "date,주간\n".encode())


@pytest.fixture
def other_admin(collecting, ops, make_member):
    """운영팀 관리자이면서 IT 부서(MEMS) 입력 담당. IT 근무표 관리자는 아니다(is_admin 은 참)."""
    _, dept, _ = collecting
    u = make_member("남관리", user=True)
    ops[0].admin_group.user_set.add(u)
    dept.managers.add(u)
    return u


def test_past_dates_need_this_board_admin(collecting, other_admin, fixed_today):
    p, dept, mgr = collecting
    collect.apply_csv(mgr, p, dept, CSV.encode())
    fixed_today(date(2026, 11, 11))
    with pytest.raises(CsvInvalid) as e:
        collect.apply_csv(other_admin, p, dept, "date,새벽,정상,석식교대,야간\n2026-11-09,나,가,,\n".encode())
    assert "지난 날짜" in " / ".join(x.reason for x in e.value.errors)


def test_past_rows_locked_for_other_board_admin(client, collecting, other_admin, fixed_today):
    p, _, _ = collecting
    fixed_today(date(2026, 11, 11))
    client.force_login(other_admin)
    body = client.get(f"/collect/{p.pk}/MEMS/").content.decode()
    assert 'name="c_2026-11-09_normal" value="" readonly' in body
    assert 'name="c_2026-11-11_normal" value="" >' in body


def test_other_board_department_page_and_csv_are_404(client, collecting, ops, make_member):
    p, _, _ = collecting
    board, dept = ops
    u = make_member("운영관리", user=True)
    board.admin_group.user_set.add(u)  # 운영팀 부서는 입력할 수 있다
    client.force_login(u)
    assert client.get(f"/collect/{p.pk}/OPS/").status_code == 404  # IT 회차에 운영팀 부서 표는 없다
    assert client.get(f"/collect/{p.pk}/OPS/export.csv").status_code == 404
    with pytest.raises(DutyError, match="이 회차의 근무표에 속한 부서가 아닙니다"):
        collect.export_csv(p, dept)
```

- [ ] **Step 8: 실패 확인**

Run: `.venv/bin/pytest -W error tests/test_boards_generate.py -q`

Expected: `4 failed, 4 passed`.
- `test_other_board_department_page_and_csv_are_404`: `assert 200 == 404`(지금은 다른 근무표 부서의 표가 그려진다)
- `test_department_of_other_board_rejected`: `Failed: DID NOT RAISE DutyError`(지금은 다른 근무표 부서가 그냥 저장된다)
- `test_past_dates_need_this_board_admin`: `Failed: DID NOT RAISE CsvInvalid`(지금은 다른 근무표 관리자도 `is_admin` 이라 지난 날짜를 고친다)
- `test_past_rows_locked_for_other_board_admin`: `assert 'name="c_2026-11-09_normal" value="" readonly' in ...`

- [ ] **Step 9: 취합 구현(두 파일)**

`duty/services/collect.py` 의 `_require_input`(13–17행)을 아래로 바꾼다. 근무표 짝 검사는 `_same_board` 하나로 두고, 권한 검사 바로 아래·상태 검사 위에서 부른다.
```python
def _same_board(period: Period, dept: Department) -> None:
    if period.board_id != dept.board_id:
        raise DutyError("이 회차의 근무표에 속한 부서가 아닙니다.")


def _require_input(user, period: Period, dept: Department) -> None:
    if not perms.can_input_department(user, dept):
        raise PermissionDenied("이 부서의 출근표를 입력할 권한이 없습니다.")
    _same_board(period, dept)
    if period.status != Period.Status.COLLECTING:
        raise DutyError("취합 중인 회차가 아닙니다.")
```
같은 파일 `load_table` 의 `    table: CommuteTable = {}` 위와 `export_csv` 의 `return` 위에 `    _same_board(period, dept)` 를 한 줄씩 넣는다(읽기 경로도 같은 규칙).
같은 파일 `validate_table` 의 68행:
```python
    if not perms.is_admin(user):
```
→
```python
    if not perms.is_board_admin(user, period.board):
```
`duty/views/collect.py` 의 `_render_table` 41행:
```python
    today, admin = perms.today(), perms.is_admin(request.user)
```
→
```python
    today, admin = perms.today(), perms.is_board_admin(request.user, period.board)
```
`duty/views/collect.py` 의 `_load` 에서 `raise PermissionDenied` 다음, `return period, dept` 위에 두 줄을 넣는다. import 는 `from django.http import Http404, HttpResponse` 로 고친다(지금 `HttpResponse` 만 있다).
```python
    if period.board_id != dept.board_id:  # 다른 근무표 부서의 표·CSV 는 없는 주소로(서비스는 같은 DutyError)
        raise Http404
```
나머지 줄은 건드리지 않는다.

- [ ] **Step 10: 통과 확인·전체 테스트·커밋**

Run:
```bash
.venv/bin/pytest -W error tests/test_boards_generate.py tests/test_collect.py tests/test_views_collect.py tests/test_boards_periods.py tests/test_period_lifecycle.py -q
.venv/bin/pytest -W error -q
```
Expected: 앞의 것은 모두 통과(검증 때 79 passed. 404 테스트를 더해 이제 80 passed). 전체는 `881 passed`(877 + 4), 경고 0개.

```bash
git add duty/services/collect.py duty/views/collect.py tests/test_boards_generate.py
git commit -m "$(cat <<'EOF'
feat: 출근표 입력은 회차와 같은 근무표의 부서만, 지난 날짜는 그 근무표 관리자만

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

- [ ] **Step 11: 통계 실패 테스트**

`tests/test_boards_generate.py` 끝에 더한다.
```python


# ── 통계(8.3) ──

def test_stats_board_without_slots_is_empty(ops):
    board, dept = ops
    p = ops_period(board, ops_member(dept, "운영개발", type="개발자"), status=S.PUBLISHED)
    assert member_stats(board, None, None) == ([], None, None)
    assert period_duty_counts(p) == ([], 0, True)


def test_stats_types_come_from_slot_definitions(ops):
    board, dept = ops
    BoardShift.objects.create(board=board, key="slot0", name="점검", start=time(10), end=time(11),
                              eligible_shifts=["normal"], eligible_types=["직원"])
    a, b = ops_member(dept, "운영가"), ops_member(dept, "운영나")
    p = ops_period(board, a, status=S.PUBLISHED)
    Commute.objects.create(period=p, date=NOV9, member=b, shift="normal")
    DutyAssignment.objects.create(period=p, date=NOV9, cell="slot0", member=a)
    assert {r.name: r.duty for r in member_stats(board, None, None)[0]} == {"운영나": 0, "운영가": 1}
    assert period_duty_counts(p) == ([("운영나", 0), ("운영가", 1)], 1, True)


def test_period_counts_pool_is_board_roster(ops, make_member):
    """모집단 = 생성기 members_by_type 와 같은 사람(그 근무표 부서 재직자). 다른 근무표 사람·퇴사자는 0회로 끼지 않는다."""
    board, dept = ops
    BoardShift.objects.create(board=board, key="slot0", name="점검", start=time(10), end=time(11),
                              eligible_shifts=["normal"], eligible_types=["직원"])
    p = ops_period(board, ops_member(dept, "운영가"), status=S.PUBLISHED)
    gone = ops_member(dept, "운영퇴사")
    gone.is_active = False
    gone.save()
    for m in (gone, make_member("남직원", type="직원")):  # 남직원 = IT 부서
        Commute.objects.create(period=p, date=NOV9, member=m, shift="normal")
    assert period_duty_counts(p) == ([("운영가", 0)], 0, True)
```

- [ ] **Step 12: 실패 확인**

Run: `.venv/bin/pytest -W error tests/test_boards_generate.py -q`

Expected: `3 failed, 8 passed`.
- 앞의 둘: `KeyError: 'dawn'`. 운영팀 근무표에는 dawn 정의가 없어 `Day.members` 에 그 칸이 없는데, 지금 `member_stats` 가 `day.members["dawn"]` 을 바로 읽는다.
- `test_period_counts_pool_is_board_roster`: AssertionError(지금은 IT 관제 칸·개발자 기준이라 운영팀 회차의 모집단이 비어 `([], 0, True)`).

- [ ] **Step 13: 통계 구현**

`duty/services/stats.py` 5–7행 import:
```python
from ..models import Board, Commute, DutyAssignment, Period, User
from ..shifts import CONTROL_SLOTS, DEVELOPER, TARGET_SPREAD, is_slot_cell
from .roster import published_days
```
→
```python
from django.db.models import Q

from ..models import Board, Commute, DutyAssignment, Period, User
from ..shifts import TARGET_SPREAD, is_slot_cell, slot_defs
from . import boards
from .roster import published_days
```
`member_stats`(36–60행)와 `period_duty_counts`(63–72행)를 아래로 바꾼다. `MemberStat`·`Summary`·`_summary` 는 그대로다.
```python
def member_stats(board: Board, start: date | None, end: date | None):
    days = published_days(board, start, end)
    # ponytail: 관제 칸들의 자격 유형 합집합(IT = 개발자). 칸마다 달라지면 칸별로 센다
    types = {t for x in slot_defs(boards.defs(board)) for t in x.eligible_types}  # 관제 정의가 없으면 비어 통계도 없다
    roster = User.objects.roster().filter(department__board=board, type__in=types)  # 그 근무표 부서 사람만
    stats = {n: MemberStat(n) for n in roster.values_list("name", flat=True)}
    # 퇴사·부서 해제된 사람도 이 기간에 근무가 있으면 통계에 남긴다(역사는 그대로)
    eligible = set(User.objects.filter(type__in=types).values_list("name", flat=True))
    for day in days:
        for names in day.members.values():
            for n in names:
                if n in eligible:
                    stats.setdefault(n, MemberStat(n))
    for day in days:
        for cell, names in day.members.items():
            if is_slot_cell(cell):
                for n in names:
                    stats.setdefault(n, MemberStat(n)).duty += 1
    for day in days:
        for n in day.members.get("dawn", ()):  # 근무표에 그 정의가 없으면 칸도 없다
            if n in stats:
                stats[n].dawn += 1
        for n in day.members.get("night", ()):
            if n in stats:
                stats[n].night += 1
    rows = sorted(stats.values(), key=lambda s: (s.duty, s.name))
    return rows, _summary([s.duty for s in rows]), _summary([s.total for s in rows])


def period_duty_counts(period: Period) -> tuple[list[tuple[str, int]], int, bool]:
    # 생성기 풀과 같은 모집단: 회차 안에 자격 근무조 출근이 있고 자격 유형인 사람. 0회 배정자도 포함한다.
    slots = slot_defs(boards.active_defs(period.board))  # 생성과 같은 칸(켜진 관제)
    q = Q(pk__in=[])  # 칸별 자격(generator 와 같다): 그 칸 자격 근무조 출근 ∧ 그 칸 자격 유형(빈 튜플 = 전원)
    for x in slots:
        q |= Q(shift__in=x.eligible_shifts, **({"member__type__in": x.eligible_types} if x.eligible_types else {}))
    # 사람은 생성기 members_by_type 와 같다: 그 근무표 부서의 재직자(배정받은 퇴사자는 아래 배정 수로 남는다)
    pool = Commute.objects.filter(q, period=period, member__department__board=period.board, member__is_active=True)
    n: dict[str, int] = dict.fromkeys(pool.values_list("member__name", flat=True), 0)
    for name in DutyAssignment.objects.filter(period=period).values_list("member__name", flat=True):
        n[name] = n.get(name, 0) + 1
    counts = sorted(n.items(), key=lambda x: (x[1], x[0]))
    spread = counts[-1][1] - counts[0][1] if counts else 0
    return counts, spread, spread <= TARGET_SPREAD
```
`views/manage.stats_view` 는 Task 6 이 근무표를 넘기게 했다. 고치지 않는다.

- [ ] **Step 14: 통과 확인·옛 상수 확인·화면 비교**

Run:
```bash
.venv/bin/pytest -W error tests/test_boards_generate.py tests/test_stats.py tests/test_views_manage.py tests/test_boards_periods.py -q
grep -nw "CONTROL_SLOTS\|DEVELOPER\|COMMUTE_SHIFTS\|slot_cell\|is_admin" duty/generator.py duty/services/generate.py duty/services/collect.py duty/services/stats.py duty/views/collect.py
DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/pytest -W error -q
```
Expected:
- 앞의 테스트는 모두 통과(검증 때 62 passed. 그 뒤 404·모집단 테스트를 더해 64 passed)
- grep 은 출력이 없다(`-w` 라 `is_slot_cell`·`is_board_admin` 은 걸리지 않는다)
- `No changes detected`
- 전체 `884 passed`(881 + 3), 경고 0개

화면 확인(CLAUDE.md). IT 화면은 바뀌지 않아야 한다. `config.test_settings` 로 같은 프로세스에서 migrate·가짜 데이터·요청을 돌려 main 사본과 비교한다. 실명 DB 는 열지 않는다.
```bash
W=$(mktemp -d); echo $W
mkdir $W/main && git archive main | tar -x -C $W/main
cat > $W/pages.py <<'EOF'
"""화면 비교용: 임시 DATA_DIR(test_settings)에 가짜 데이터를 넣고 admin 으로 회차·출근표·통계 화면과 CSV 를 찍는다."""
import re

import django

django.setup()
from django.core.management import call_command  # noqa: E402
from django.test import Client  # noqa: E402

call_command("migrate", verbosity=0)
exec(open("tools/help_videos/seed.py", encoding="utf-8").read())
from duty.models import Department, Period, User  # noqa: E402

c = Client(HTTP_HOST="localhost")
c.force_login(User.objects.get(username="admin"))
collecting = Period.objects.filter(status="collecting")
urls = ["/periods/", "/collect/", "/changes/", "/stats/"] + [f"/periods/{p.pk}/" for p in Period.objects.order_by("pk")]
urls += [f"/collect/{p.pk}/{d.code}/{x}" for p in collecting for d in Department.objects.order_by("code") for x in ("", "export.csv")]
for u in urls:
    r = c.get(u)
    print("=====", u, r.status_code)
    print(re.sub(r'csrfmiddlewaretoken" value="[^"]+"', "CSRF", r.content.decode("utf-8-sig")))
EOF
DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. .venv/bin/python $W/pages.py > $W/new.html
(cd $W/main && DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. $OLDPWD/.venv/bin/python $W/pages.py > $W/old.html)
diff $W/old.html $W/new.html && echo SAME
```
Expected: 모든 주소가 200 이고 `SAME` 이 나온다(검증 때 Task 6 사본과 비교해 그랬다). 끝나면 `echo` 로 찍힌 임시 폴더 경로를 직접 적어 지운다. `$W` 를 `rm -rf` 에 넘기지 않는다.

이어서 Task 5 Step 21 의 serve.py 로 이 브랜치(8795)와 main(8796)을 띄운다. admin 으로 PC 1400px·모바일 390px 에서 `/collect/` 와 출근표 표(지난 날짜 잠금), `/stats/`, 회차 상세(관제 횟수 표)가 나란히 같은지 본다.

- [ ] **Step 15: 커밋**

```bash
git add duty/services/stats.py tests/test_boards_generate.py
git commit -m "$(cat <<'EOF'
feat: 통계를 근무표의 관제 정의로(자격 근무조·유형, 관제 없는 근무표는 빈 통계)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

---

**이 작업에서 한 것 요약**
- 생성·`period_duty_counts` 는 켜진 slot 정의(`boards.active_defs`)만 보고, 칸마다 그 칸의 자격 근무조·자격 유형으로 후보를 거른다(Step 3·4·13). `member_stats` 의 자격 유형만 관제 칸들의 합집합이다(`ponytail:` 주석 1곳, 칸마다 유형이 다른 근무표가 생기면 칸별로 센다).
- 출근표 표·CSV 는 회차·부서 근무표가 다르면 뷰가 404, 서비스가 `DutyError` 다(Step 9).

**이 작업에서 빼는 것(뒤 작업 범위)**
- 휴장일·근무 없음 날 빼기, 점심당번, direct 확정 경고, 통계 근무표 고르기: 2·3단계
- Task 8: 알림·캘린더(`change_notice._live` 포함)
- Task 10(지적 17): 문서. ARCHITECTURE.md 의 생성 절(칸 목록 필수 인자, 후보 = 그 근무표 부서의 자격 유형), 취합 절(근무표 검사, 지난 날짜 = `is_board_admin`), 통계 절을 고친다.
- `shifts.CONTROL_SLOTS`·`COMMUTE_SHIFTS`·`DEVELOPER` 상수 자체는 지우지 않는다. 이 작업 뒤 generator·generate·stats·collect 는 쓰지 않지만, calendar·alarms 쪽(Task 8)이 아직 쓴다.

**검증 기록**
- Task 1~6 을 적용한 사본(/tmp/t6v2, 863 passed)을 복사한 /tmp/t7v2 에 Step 1~15 를 그대로 넣어 돌렸다(커밋 c7a·c7b·c7c).
  - 실패 확인: 14 → 3 → 2 failed. 메시지는 위에 적은 그대로 나왔다.
  - 통과: 869 → 872 → **874 passed**, 경고 0. `makemigrations --check` 는 `No changes detected`.
- baseline 생성 결과 해시가 Task 6 사본과 같았다.
- 화면: seed 를 넣고 admin 으로 `/periods/`·`/collect/`·`/changes/`·`/stats/`·회차 상세 2개·출근표 표 4개·CSV 4개를 Task 6 사본과 비교했고 차이가 없었다. seed 에는 마감·생성됨 회차가 없어 생성 결과 화면은 비교에 들어가지 않는다. 대신 위 해시 비교와 기존 `test_generation_writes_duties` 가 지킨다.
- 지적 반영
  - 지적 10: csv_io·shift_names·missing_dates·progress·index·_render_detail 은 고치지 않았다. collect.py 는 전체 교체 대신 필요한 곳만 고쳤다(검증 때는 `_require_input` 근무표 검사, `validate_table`·`_render_table` 의 `is_board_admin` 세 군데. 그 뒤 리뷰 반영으로 `_same_board`·`_load` 404·칸별 생성 자격·모집단 조건을 더했고, 이것은 사본에서 다시 돌리지 않았다). 앞 작업이 이미 통과시킨 중복 테스트(test_shift_names·test_old_csv·test_csv_columns·test_progress·test_index_skips_other_board_period·test_missing_dates_only_period_board·test_other_board_department_not_required·test_member_stats_only_board_members)는 넣지 않았다.
  - 지적 11: `_render_detail` 은 Task 3 의 `slot_names[f.slot]` 그대로다. generate 의 `slots[i].key` 와 같은 `slot_defs` 순서라 맞는다.
  - 지적 19: manage.py 명령은 모두 `DJANGO_SETTINGS_MODULE=config.test_settings` 로 돌린다.
  - 옛 계획은 generator 커밋과 생성 서비스 커밋을 나눴다. 그러면 첫 커밋 뒤 `services/generate` 가 `slots` 없이 호출해 test_generate 가 깨진다. 그래서 한 커밋으로 합쳤다(작업 중간 상태 금지).
  - 두 번째 근무표 fixture 는 conftest 에 더하지 않았다. test_boards_periods·test_board_owner 와 같은 모양의 `ops` 를 이 파일 안에 둔다.


---

### Task 8: 알림·캘린더·변경 알림을 근무 정의로

이 작업이 끝나면 다음이 바뀝니다.
- 알림 계획(`alarms/plan`)·발송 시각(`alarms/schedule`)·문구(`alarms/messages`)가 정의 목록 `defs` 를 첫 인자로 받습니다(순수 모듈 그대로).
- 작업자는 근무표마다 따로 계획합니다(개인 = 주인 부서의 근무표, 보고서 = 규칙의 근무표).
- 변경 알림은 그 기록의 회차 근무표 정의로 문구를 만들고, 그 회차가 아직 "그날의 주인"인지로 살아 있는지를 판단합니다(설계 6.1·8.1).
- 캘린더는 사용자 근무표의 정의를 씁니다(8.2).
- 알림 규칙에 근무표(board)가 붙습니다(4.9). 보고서 규칙 = 근무표 하나, 개인 규칙 = null.
- 부서를 옮겨 근무표가 바뀌면 개인 규칙의 오늘 이후 발송 기록을 지웁니다.
- 앱 코드가 더 쓰지 않는 옛 상수(`COMMUTE_SHIFTS`·`CONTROL_SLOTS`·`SHIFT_TIMES`·`LEGACY_DEFS`·`CELLS`·`slot_cell`)를 `duty/shifts.py` 에서 지웁니다.

IT 문구·칸 순서·링크·hash·캘린더 DTSTAMP 는 한 글자도 바뀌지 않습니다. Step 11 고정 테스트의 기대 문자열과 hash 는 Task 7 까지 적용한 코드(옛 시그니처)로 직접 계산해 맞춘 값입니다.

커밋은 셋입니다. 커밋마다 전체 테스트가 통과합니다.
1. 규칙에 근무표(제약·마이그레이션 0017·normalize·폼·화면)
2. 알림·변경 알림·캘린더를 근무 정의로(순수 모듈·작업자·변경 알림·캘린더, 옛 상수 삭제)
3. 부서 이동 때 개인 알림 발송 기록 정리

줄 번호는 Task 7 까지 적용한 상태 기준입니다.

**Files:**
- Modify: `duty/models.py`: `AlarmRule.Meta.constraints` 의 `alarmrule_unique`(403~404행)
- Create: `duty/migrations/0017_alarmrule_board_rules.py`(makemigrations 로 만듦, 의존 0016_boards_not_null)
- Modify: `duty/services/alarms.py`
  - import(16~17행)
  - `normalize`~`_key`(26~83행)를 `rule_board`·`normalize`·`create_defaults`·`RULE_FIELDS`·`save_rule`·`_key` 로 교체
- Modify: `duty/alarms/forms.py`(전체)
- Modify: `duty/views/alarms.py`
  - `_index`(51~75행: 53~55행, 68행)
  - `_rule_form`(103~119행)
  - services import(13행)는 Task 3 상태 `alarm_settings, alarms, boards, calendar, prefs` 그대로 둔다(지적 18).
- Modify: `duty/templates/duty/alarm_rule_form.html`: 21행(부서 fieldset) 앞에 근무표 칸
- Modify: `duty/alarms/messages.py`·`duty/alarms/schedule.py`·`duty/alarms/plan.py`(전체)
- Modify: `duty/services/alarm_runner.py`: models import(16~17행), `collect`(83~113행)
- Modify: `duty/services/change_notice.py`: import(8~9행), `tick`(16~40행), `_live`(48~54행)
- Modify: `duty/services/calendar.py`: shifts import(17행), `set_shifts` 의 54·60행, `_events`(80~108행)
- Modify: `duty/shifts.py`: `CELLS = KEYS`(14행), `slot_cell`(36~37행), "1단계 이행용 옛 상수" 블록(101행~끝) 삭제
- Modify: `duty/accounts.py`: import(6~7행), 새 함수 `on_department_change`(파일 끝)
- Modify: `duty/admin.py`: 12행 `from .accounts import ...`, `UserAdmin.save_model` 추가(`login_id` 아래)
- Test (새 파일): `tests/test_alarm_texts_it.py`, `tests/test_alarm_boards.py`
- Test (허용 변환): `tests/test_alarm_models.py`, `tests/test_run_alarms.py`, `tests/test_views_alarms.py`, `tests/test_alarm_plan.py`, `tests/test_change_notice.py`, `tests/test_shifts.py`

**Interfaces:**
- Consumes
  - `duty.shifts`
    - 상수: `KEYS`, `SLOT_GROUP`, `SLOT_GROUP_NAME`, `DAY_LABELS`, `DEVELOPER`, `STAFF`
    - 함수: `is_slot_cell`, `cell_label(defs, cell)`, `cell_start(defs, cell)`, `cell_end(defs, cell)`, `cells_of(defs, keys)`, `ordered(defs)`, `shift_defs(defs)`
    - `cells_of(defs, [])` 는 그 defs 의 키 전부(KEYS 순)를 돌려준다. defs 에 없는 키는 결과에서 빠진다.
  - `duty.services.boards`(Task 3·5): `it_board()`, `defs(board)`(표시·알림 문구·캘린더), `active_defs(board)`(규칙 선택지·`normalize`·기본 규칙), `board_of(user)`, `owner(board, d) -> Period | None`. `owner` 는 비어 있는 `overwrite_from` 을 `start_date` 로 본다.
  - `duty.services.roster.published_days(board, start, end)`(Task 5): 주인이 있는 평일을 모두 낸다(행 없는 날 포함).
  - `duty.services.prefs.choices(defs) -> dict`(Task 3): 스케줄 키 → 이름. 근무조(시작 시각 순) 다음에 `"slots"`(관제가 있으면). IT 는 dawn·normal·dinner·night·slots.
  - 모델(Task 1·6): `Board`(save 가 관리 그룹을 만든다), `BoardShift`, `AlarmRule.board`(FK PROTECT null), `Department.board`·`Period.board`(NOT NULL)
  - 테스트: `tests.it_defs.IT_DEFS`, fixture `it_board`·`depts`(board=it_board)·`admin_user`·`fixed_today`, pytest-django `rf`
- Produces
  - 순수 모듈(첫 인자 `defs`)
    - `messages.cell_span(defs, cell)`, `personal_text(defs, name, d, cell, today)`, `cancel_text(defs, name, d, cell, successor=None)`, `report_line(defs, cell, names)`
    - `messages.change_notice(defs, d, cell, before, after, by) -> (title, text)`, `messages.swap_notice(defs, d, cell_a, a, cell_b, b, by)`
    - `schedule.same_day_notice(defs, kind, timing, offset, at_minute, shifts) -> str | None`. 그 근무표에 없는 키만 골랐으면 None.
    - `plan.plan(defs, rules, days, info, deliveries, now, destinations=None, dept_names=None, extra_dates=None, today=None) -> list[Due]`. 그 근무표에 없는 키만 가진 규칙은 건너뛴다.
  - `services.alarms`
    - `rule_board(user, kind, board_id) -> Board`. 보고서는 규칙의 근무표이고, 없으면 `DutyError("근무표를 고르세요.")`. 개인은 `board_of(user) or it_board()`.
    - `normalize(kind, shifts, depts, types, board)`: 키는 `prefs.choices(boards.active_defs(board))`(켜진 정의만), 부서는 그 근무표 부서(code 순)로 검사한다.
    - `create_defaults(user)`: 근무표가 있으면 `default_alarm` 이 켜진 근무조 키를 명시적으로 저장한다(없으면 규칙을 만들지 않는다). 근무표 없는 계정은 `DEFAULT_RULES` 그대로.
    - `RULE_FIELDS = ("kind", "board_id", "timing", "offset", "at_minute", "shifts", "depts", "types")`. 그래서 `alarm_runner.SNAP`(코드 그대로)에도 board_id 가 들어간다.
    - `save_rule(user, data, rule=None)`: data 의 `"board_id"` 키를 받는다(없으면 None, 개인 규칙은 늘 None).
  - `alarm_runner.collect(now)`: 근무표마다 `plan` 을 부른다. 부서 없는 계정의 개인 규칙은 넘기지 않는다. extra_dates 는 그 근무표 규칙의 발송 기록 날짜만이다.
  - `change_notice._live(r, now, today)`: `boards.owner(r.period.board, r.date)` 가 그 회차일 때만 True.
  - `RuleForm`
    - `fields["board"]` 는 근무표가 둘 이상일 때만 있다.
    - `cleaned_data["rule"]["board_id"]`: 보고서는 고른 근무표(하나면 그것), 개인은 None.
    - `fixed_board`: 근무표가 하나일 때 그 근무표, 아니면 None.
    - `RuleForm(data=None, *, user=None, initial=None)`: `fields["shifts"].choices` 는 근무표가 하나면 그것, 보고서면 보낸(편집 땐 규칙의) `board`, 개인이면 `board_of(user) or it_board()` 의 정의로 정한다(설계 8.1).
  - 템플릿 문맥 `multi_board`(bool)
  - `accounts.on_department_change(user, old_department_id) -> None`
  - `UserAdmin.save_model`: 바꿀 때 `on_department_change` 를 부른다.
  - DB 제약 이름: `alarmrule_board_by_kind`, `alarmrule_unique_personal`, `alarmrule_unique_report`. `alarmrule_unique` 는 없앤다.
  - 마이그레이션 `0017_alarmrule_board_rules`. **다음 번호는 0018.**
  - `duty.shifts` 에서 사라지는 이름: `CELLS`, `slot_cell`, `COMMUTE_SHIFTS`, `CONTROL_SLOTS`, `SHIFT_TIMES`, `LEGACY_DEFS`, `_legacy_defs`

---

#### 커밋 1: 규칙에 근무표

- [ ] **Step 1: AlarmRule 근무표 제약 테스트를 쓴다**

`tests/test_alarm_models.py`
- 6행 → `from duty.models import AlarmDelivery, AlarmRule, Board, PushAlarmSubscription, TelegramAlarmProfile, User`
- 46~47행: 허용 변환 (a). 보고서 규칙 준비 코드에 IT 근무표를 넣는다.

  ```python
  def test_report_allows_filters(user, it_board):
      _rule(user, kind="report", board=it_board, depts=["MEMS"], types=["직원"])
  ```

- 파일 끝에 더한다:

```python


def test_rule_board_by_kind(user, it_board):
    _bad(lambda: _rule(user, board=it_board))   # 개인 규칙에는 근무표가 없다(주인의 근무표)
    _bad(lambda: _rule(user, kind="report"))    # 보고서 규칙은 근무표 하나
    _rule(user, kind="report", board=it_board)


def test_report_rule_unique_per_board(user, it_board):
    other = Board.objects.create(code="ops", name="운영팀", input_mode="direct")
    _rule(user, kind="report", board=it_board)
    _rule(user, kind="report", board=other)  # 근무표가 다르면 같은 조건도 된다
    _bad(lambda: _rule(user, kind="report", board=other, telegram=False, push=True))
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_alarm_models.py -q -k "board"`
Expected: `2 failed, 30 deselected`
- `test_rule_board_by_kind`: `Failed: DID NOT RAISE IntegrityError`
- `test_report_rule_unique_per_board`: 두 번째 `_rule` 이 옛 `alarmrule_unique` 에 걸려 `UNIQUE constraint failed: duty_alarmrule.user_id, ...`

- [ ] **Step 3: 모델 제약을 바꾸고 마이그레이션을 만든다**

`duty/models.py` 의 `AlarmRule.Meta.constraints` 에서 지금 403~404행을

```python
            models.UniqueConstraint(name="alarmrule_unique",
                                    fields=["user", "kind", "timing", "offset", "at_minute", "shifts", "depts", "types"]),
```

다음으로 바꾼다:

```python
            # 개인 = 주인의 근무표(null), 보고서 = 근무표 하나
            models.CheckConstraint(name="alarmrule_board_by_kind", condition=(
                Q(kind="personal", board__isnull=True) | Q(kind="report", board__isnull=False))),
            models.UniqueConstraint(name="alarmrule_unique_personal", condition=Q(kind="personal"),
                                    fields=["user", "kind", "timing", "offset", "at_minute", "shifts", "depts", "types"]),
            models.UniqueConstraint(name="alarmrule_unique_report", condition=Q(kind="report"),
                                    fields=["user", "kind", "board", "timing", "offset", "at_minute", "shifts", "depts",
                                            "types"]),
```

Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --name alarmrule_board_rules`
Expected: `duty/migrations/0017_alarmrule_board_rules.py` 하나가 생기고(의존 `0016_boards_not_null`), 연산은 다음 넷뿐이다. 다른 연산이 섞이면 멈추고 원인을 본다.
- `Remove constraint alarmrule_unique from model alarmrule`
- `Create constraint alarmrule_board_by_kind on model alarmrule`
- `Create constraint alarmrule_unique_personal on model alarmrule`
- `Create constraint alarmrule_unique_report on model alarmrule`

기존 보고서 규칙의 board=IT 는 Task 1 의 `0011_boards_data` 가 이미 채운다. 그래서 이 파일은 스키마만 바꾼다(운영 DB 의 개인 규칙은 board 가 비어 있어 새 제약을 통과한다).

Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations --check --dry-run`
Expected: `No changes detected`

- [ ] **Step 4: 보고서 규칙을 직접 만드는 준비 코드에 IT 근무표를 넣는다 (허용 변환 (a), 단언 그대로)**

`tests/test_run_alarms.py`
- 11행 → `from duty.services import alarm_runner, alarms, boards`
- `report_rule`(414~415행)의 create 를 다음으로 바꾼다:

  ```python
      return AlarmRule.objects.create(user=user, kind="report", board=boards.it_board(), timing="days", offset=1,
                                      at_minute=18 * 60, telegram=True, push=False, shifts=["dawn"], depts=[], types=[])
  ```

`tests/test_views_alarms.py`
- 7행 → `from duty.models import AlarmDelivery, AlarmRule, AlarmSettings, Board, TelegramAlarmProfile, User`
- `rule()` 도우미(45~47행) 전체를 다음으로 바꾼다. 71·419행의 보고서 규칙이 이 도우미를 거친다.

  ```python
  def rule(user, **kw):
      base = dict(kind="personal", timing="days", offset=1, at_minute=18 * 60, telegram=True, push=False, shifts=[])
      if kw.get("kind") == "report":
          kw.setdefault("board", Board.objects.get(code="it"))
      return AlarmRule.objects.create(user=user, **{**base, **kw})
  ```

- `test_rule_edit_shows_all_selected_as_checked` 의 789~790행을 다음으로 바꾼다. `me` → `depts` → `it_board` 순서라 IT 근무표가 있다.

  ```python
      r = AlarmRule.objects.create(user=me, kind="report", board=Board.objects.get(code="it"), timing="days", offset=2,
                                   at_minute=9 * 60, telegram=True, push=False, shifts=[], depts=[], types=[], enabled=True)
  ```

Run: `.venv/bin/pytest -W error tests/test_alarm_models.py tests/test_run_alarms.py -q`
Expected: PASS(새 제약 테스트 포함).

`tests/test_views_alarms.py` 의 다음 3개는 Step 8 까지 `CHECK constraint failed: alarmrule_board_by_kind` 로 실패한다. 화면 폼이 보고서 규칙을 board 없이 저장하기 때문이다.
- `test_create_days_rule`
- `test_edit_clears_future_deliveries[change1-False]`
- `test_same_day_notice_report`

- [ ] **Step 5: 근무표별 규칙·기본값·폼 테스트를 쓰고, normalize 테스트를 기계적으로 고친다**

`tests/test_alarm_models.py`: 허용 변환 (c). 기대 값은 그대로 둔다.
- 87~90행 `test_normalize` 를 다음으로 바꾼다:

  ```python
  def test_normalize(depts, it_board):
      assert alarms.normalize("report", ["night", "dawn"], ["UI", "MEMS"], ["개발자", "직원"], it_board) == (["dawn", "night"], ["MEMS", "UI"], [])
      assert alarms.normalize("report", ["dawn", "normal", "dinner", "night", "slots"], list(depts), [], it_board) == ([], [], [])
      assert alarms.normalize("personal", ["dawn"], ["MEMS"], ["직원"], it_board) == (["dawn"], [], [])
  ```

- 114행 `def test_normalize_rejects_unknown(depts):` → `def test_normalize_rejects_unknown(depts, it_board):`
  - 117행 `alarms.normalize("report", *args)` → `alarms.normalize("report", *args, it_board)`
  - 120행 `alarms.normalize("personal", *args)` → `alarms.normalize("personal", *args, it_board)`

`tests/test_alarm_boards.py`(새 파일). Step 14·20 에서 이 파일에 이어 붙인다.

```python
"""근무표가 둘일 때 알림 규칙·정기 알림·변경 알림·캘린더가 서로 영향 없음(1단계)."""
from datetime import date, time

import pytest

from duty.alarms.forms import RuleForm
from duty.errors import DutyError
from duty.models import AlarmDelivery, AlarmRule, Board, BoardShift, Department, User
from duty.services import alarms

D = date(2026, 11, 16)  # 월
SUN = date(2026, 11, 15)
OPS_DEFS = [("dawn", "오전", time(7, 30), time(16, 30)), ("normal", "주간", time(9), time(18)),
            ("dinner", "오후", time(11), time(20))]
FORM = dict(enabled="on", timing="before_start", hours="2", minutes="0", telegram="on")


@pytest.fixture
def ops(it_board):
    """가짜 두 번째 근무표 '운영팀'(관리 그룹은 Board.save 가 만든다): 근무조 셋(모두 기본 알림), 관제 없음."""
    board = Board.objects.create(code="ops", name="운영팀", input_mode="direct")
    for key, name, start, end in OPS_DEFS:
        BoardShift.objects.create(board=board, key=key, name=name, start=start, end=end, default_alarm=True)
    dept = Department.objects.create(code="OPS", name="운영팀", shifts="dawn,normal,dinner", board=board, order=0)
    return board, dept


def report_base(board_id, **kw):
    return {**dict(enabled=True, kind="report", timing="days", offset=1, at_minute=18 * 60, telegram=True,
                   push=False, shifts=["dawn"], depts=[], types=[], board_id=board_id), **kw}


# ---- 규칙 ----

def test_create_defaults_uses_board_default_alarm(depts, ops):
    _, dept = ops
    it = User.objects.create_user("it1", password=None, name="가상아이", department=depts["MEMS"], type="직원")
    op = User.objects.create_user("op1", password=None, name="가상운영", department=dept, type="직원")
    alarms.create_defaults(it)
    alarms.create_defaults(op)
    assert [r.shifts for r in AlarmRule.objects.filter(user=it)] == [["dawn", "dinner", "night"]] * 2
    assert [r.shifts for r in AlarmRule.objects.filter(user=op)] == [["dawn", "normal", "dinner"]] * 2
    assert not AlarmRule.objects.filter(board__isnull=False).exists()  # 기본 규칙은 개인 규칙


def test_normalize_by_board(depts, ops):
    board, _ = ops
    assert alarms.normalize("report", ["dinner", "dawn"], ["OPS"], [], board) == (["dawn", "dinner"], [], [])
    with pytest.raises(DutyError):
        alarms.normalize("report", ["night"], [], [], board)  # 운영팀에 없는 키
    with pytest.raises(DutyError):
        alarms.normalize("report", [], ["MEMS"], [], board)  # 다른 근무표의 부서


def test_report_rules_by_board_and_board_change_clears(fixed_today, depts, it_board, ops, admin_user):
    fixed_today(SUN)
    board, _ = ops
    a = alarms.save_rule(admin_user, report_base(it_board.pk))
    b = alarms.save_rule(admin_user, report_base(board.pk, shifts=["normal"]))
    assert (a.board_id, b.board_id) == (it_board.pk, board.pk)
    with pytest.raises(DutyError, match="같은 규칙이 이미 있습니다."):
        alarms.save_rule(admin_user, report_base(board.pk, shifts=["normal"]))
    with pytest.raises(DutyError, match="근무표를 고르세요."):
        alarms.save_rule(admin_user, report_base(None))
    assert alarms.save_rule(admin_user, report_base(board.pk, kind="personal")).board_id is None
    AlarmDelivery.objects.create(rule=b, date=D, cell="report", channel="telegram", destination="1",
                                 status="sent", content_hash="h")
    alarms.save_rule(admin_user, report_base(it_board.pk, shifts=["normal"]), b)  # 근무표만 바꿈
    assert not AlarmDelivery.objects.filter(rule=b).exists()


def test_rule_form_single_board(depts, it_board):
    f = RuleForm({**FORM, "kind": "report"})
    assert "board" not in f.fields and f.is_valid(), f.errors
    assert f.cleaned_data["rule"]["board_id"] == it_board.pk
    assert [c for c, _ in f.fields["depts"].choices] == ["MD", "MEMS", "TMCH", "UI"]


def test_rule_form_two_boards(depts, it_board, ops):
    board, _ = ops
    f = RuleForm({**FORM, "kind": "report", "board": str(board.pk)})
    assert "board" in f.fields and f.is_valid(), f.errors
    assert f.cleaned_data["rule"]["board_id"] == board.pk
    assert [c for c, _ in f.fields["shifts"].choices] == ["dawn", "normal", "dinner"]  # 고른 근무표의 스케줄
    f = RuleForm({**FORM, "kind": "report", "board": str(board.pk), "shifts": ["night"]})
    assert not f.is_valid() and "shifts" in f.errors  # 운영팀에 없는 키는 폼이 막는다(normalize DutyError 까지 안 감)
    f = RuleForm({**FORM, "kind": "report", "board": str(it_board.pk), "shifts": ["night"]})
    assert f.is_valid(), f.errors
    f = RuleForm({**FORM, "kind": "personal", "board": str(board.pk)})
    assert f.is_valid() and f.cleaned_data["rule"]["board_id"] is None
    op = User.objects.create_user("op2", password=None, name="가상운영", department=ops[1], type="직원")
    f = RuleForm({**FORM, "kind": "personal"}, user=op)
    assert [c for c, _ in f.fields["shifts"].choices] == ["dawn", "normal", "dinner"]  # 개인 = 주인의 근무표


def test_rule_page_board_field_only_with_two_boards(client, depts, request):
    client.force_login(User.objects.create_user("u9", password="unused-Pw-123", name="가상구"))
    assert "<legend>근무표</legend>" not in client.get("/alarms/rules/new/").content.decode()
    request.getfixturevalue("ops")
    assert "<legend>근무표</legend>" in client.get("/alarms/rules/new/").content.decode()


def test_rule_list_names_shifts_by_rule_board(client, depts, ops, admin_user):
    """규칙 목록의 스케줄 이름은 그 규칙의 근무표 정의로(보고서 = 규칙의 근무표)."""
    board, _ = ops
    AlarmRule.objects.create(user=admin_user, kind="report", board=board, timing="days", offset=1,
                             at_minute=18 * 60, telegram=True, shifts=["dawn"], depts=[], types=[])
    client.force_login(admin_user)
    assert "스케줄: 오전" in client.get("/alarms/").content.decode()
```

- [ ] **Step 6: 실패를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_alarm_boards.py tests/test_alarm_models.py -q`
Expected: `9 failed, 30 passed`
- `normalize()` 가 board 인자를 받지 않아 `TypeError`: `test_normalize`, `test_normalize_rejects_unknown`, `test_normalize_by_board`, `test_report_rules_by_board_and_board_change_clears`
- 운영팀 기본 규칙이 dawn·dinner·night 로 나옴: `test_create_defaults_uses_board_default_alarm`
- `KeyError: 'board_id'` 또는 board 칸 없음: `test_rule_form_single_board`, `test_rule_form_two_boards`
- 화면에 근무표 fieldset 이 없음: `test_rule_page_board_field_only_with_two_boards`
- 목록에 IT 이름 "새벽"이 나옴: `test_rule_list_names_shifts_by_rule_board`

- [ ] **Step 7: `duty/services/alarms.py` 의 규칙 부분을 바꾼다**

import 두 줄(16~17행)을 다음으로 바꾼다. 18행 `from . import alarm_settings, boards, prefs` 는 그대로 둔다.

```python
from ..models import AlarmRule, Board, Department, PushAlarmSubscription, TelegramAlarmProfile, User
from ..shifts import DEVELOPER, STAFF, shift_defs
```

`DEFAULT_RULES`(20~23행)는 그대로 둔다. 그 아래 `def normalize(kind, shifts, depts, types):` 부터 `def delete_rule(` 바로 앞까지(26~83행)를 다음으로 바꾼다. `delete_rule` 이하는 그대로다.

```python
def rule_board(user, kind, board_id) -> Board:
    """규칙 값을 검사할 근무표. 보고서 = 규칙의 근무표, 개인 = 주인 부서의 근무표(부서 없는 계정은 IT)."""
    if kind != "report":
        return boards.board_of(user) or boards.it_board()
    board = Board.objects.filter(pk=board_id).first() if board_id else None
    if board is None:
        raise DutyError("근무표를 고르세요.")
    return board


def normalize(kind, shifts, depts, types, board):
    """알려진 값만 남기고 정해진 순서로 정렬. 전부 선택 = [](전체). 스케줄 키·부서는 그 근무표 것만.
    개인 규칙은 부서·유형 필터 없음."""
    def pick(vals, order):
        bad = [v for v in vals if v not in order]
        if bad:
            raise DutyError(f"알 수 없는 값: {', '.join(map(str, bad))}")
        got = [v for v in order if v in set(vals)]
        return [] if len(got) == len(order) else got

    s = pick(shifts, list(prefs.choices(boards.active_defs(board))))  # 꺼진 정의는 새 규칙에 넣지 않는다
    d = pick(depts, sorted(Department.objects.filter(board=board).values_list("code", flat=True)))
    t = pick(types, [STAFF, DEVELOPER])
    return (s, [], []) if kind == "personal" else (s, d, t)


def create_defaults(user) -> None:
    """최초 발급 때 기본 규칙. 대상은 그 사람 근무표에서 default_alarm 이 켜진 근무조를 명시적으로 저장한다
    ([]는 관제까지 포함한 '전체'라 쓰지 않는다). 근무표 없는 계정은 DEFAULT_RULES 그대로."""
    if AlarmRule.objects.filter(user=user).exists():
        return
    board, rules = boards.board_of(user), DEFAULT_RULES
    if board is not None:
        keys = [x.key for x in shift_defs(boards.active_defs(board)) if x.default_alarm]
        if not keys:
            return  # 기본 알림 대상 근무조가 없는 근무표
        rules = [{**r, "shifts": keys} for r in DEFAULT_RULES]
    AlarmRule.objects.bulk_create([AlarmRule(user=user, **r) for r in rules])


# ---- 규칙 ----

# 바뀌면 오늘 이후 발송 기록 삭제. board_id = 보고서 규칙의 근무표(개인 = None, 주인의 근무표)
RULE_FIELDS = ("kind", "board_id", "timing", "offset", "at_minute", "shifts", "depts", "types")


MAX_RULES = 20  # 사람당 알림 규칙 수(무제한이면 한 사람이 작업자 발송을 몇 시간씩 막을 수 있다)


def save_rule(user, data: dict, rule: AlarmRule | None = None) -> AlarmRule:
    board_id = data.get("board_id") if data["kind"] == "report" else None
    shifts, depts, types = normalize(data["kind"], data["shifts"], data["depts"], data["types"],
                                     rule_board(user, data["kind"], board_id))
    new = {**data, "board_id": board_id, "shifts": shifts, "depts": depts, "types": types}
    rule = rule or AlarmRule(user=user)
    changed = rule.pk is not None and _key(rule) != tuple(new[f] for f in RULE_FIELDS)
    try:
        with transaction.atomic():
            if rule.pk is None and AlarmRule.objects.filter(user=user).count() >= MAX_RULES:
                raise DutyError(f"알림 규칙은 최대 {MAX_RULES}개입니다. 쓰지 않는 규칙을 먼저 지워 주세요.")
            for k, v in new.items():
                setattr(rule, k, v)
            rule.save()
            if changed:
                rule.deliveries.filter(date__gte=perms.today()).delete()
    except IntegrityError:
        key = tuple(new[f] for f in RULE_FIELDS)
        if any(_key(r) == key for r in AlarmRule.objects.filter(user=user).exclude(pk=rule.pk)):
            raise DutyError("같은 규칙이 이미 있습니다.") from None
        raise
    return rule


def _key(rule: AlarmRule) -> tuple:
    """정규화한 비교 키(RULE_FIELDS 순서). 저장값이 정규화 전 형태(순서·전부 선택)여도 같게 본다."""
    try:
        shifts, depts, types = normalize(rule.kind, rule.shifts, rule.depts, rule.types,
                                         rule_board(rule.user, rule.kind, rule.board_id))
    except DutyError:  # 지금은 없는 부서 등 → 저장값 그대로
        shifts, depts, types = rule.shifts, rule.depts, rule.types
    return rule.kind, rule.board_id, rule.timing, rule.offset, rule.at_minute, shifts, depts, types

```

`duty/services/calendar.py::set_shifts` 의 두 줄을 바꾼다.
- 54행 → `    from .alarms import normalize, rule_board  # 순환 import 피함`
- 60행 → `    row.shifts = normalize("personal", shifts, [], [], rule_board(user, "personal", None))[0]  # 모르는 값은 오류, 전부 = []`

Run: `.venv/bin/pytest -W error tests/test_alarm_models.py tests/test_alarm_boards.py -q -k "normalize or defaults or report_rules"`
Expected: PASS

- [ ] **Step 8: 폼·화면을 바꾼다**

`duty/alarms/forms.py` 전체(지적 6: `SHIFT_CHOICES` 는 Task 3 에서 없어졌다. 선택지는 `prefs.choices(boards.defs(...))`):

```python
from datetime import time

from django import forms

from ..models import AlarmKind, AlarmTiming, Board, Department
from ..services import boards, prefs
from ..shifts import DEVELOPER, STAFF


def _first_board_id():
    return Board.objects.order_by("id").values_list("pk", flat=True).first()


class RuleForm(forms.Form):
    enabled = forms.BooleanField(label="켬", required=False, initial=True)
    kind = forms.ChoiceField(label="종류", choices=AlarmKind.choices, initial="personal", widget=forms.RadioSelect)
    board = forms.ModelChoiceField(label="근무표", queryset=Board.objects.order_by("id"), required=False,
                                   empty_label=None)
    timing = forms.ChoiceField(label="기준", choices=AlarmTiming.choices, initial="before_start", widget=forms.RadioSelect)
    hours = forms.IntegerField(label="시간", min_value=0, max_value=168, required=False, initial=2)
    minutes = forms.IntegerField(label="분", min_value=0, max_value=59, required=False, initial=0)
    days = forms.IntegerField(label="일 수", min_value=0, max_value=30, required=False, initial=1)
    at_time = forms.TimeField(label="발송 시각", required=False, initial=time(18, 0),
                              widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))
    telegram = forms.BooleanField(label="텔레그램", required=False, initial=True)
    push = forms.BooleanField(label="푸시", required=False)
    shifts = forms.MultipleChoiceField(label="스케줄", required=False, widget=forms.CheckboxSelectMultiple)
    depts = forms.MultipleChoiceField(label="부서", required=False, widget=forms.CheckboxSelectMultiple)
    types = forms.MultipleChoiceField(label="유형", choices=[(STAFF, STAFF), (DEVELOPER, DEVELOPER)], required=False,
                                      widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        all_boards = list(Board.objects.order_by("id"))
        # 근무표가 하나면 칸을 숨기고 그 근무표로 고정(1단계 화면 그대로). 부서 선택지는 그 근무표의 부서
        self.fixed_board = all_boards[0] if len(all_boards) == 1 else None
        if self.fixed_board is None:
            self.fields["board"].label_from_instance = lambda b: b.name
            depts = Department.objects.all()  # 고른 근무표 밖의 부서는 normalize 가 막는다
        else:
            del self.fields["board"]
            depts = Department.objects.filter(board=self.fixed_board)
        self.fields["shifts"].choices = list(prefs.choices(boards.active_defs(self._shift_board(all_boards, user))).items())
        self.fields["depts"].choices = list(depts.values_list("code", "name"))

    def _shift_board(self, all_boards, user):
        """스케줄 선택지의 근무표(설계 8.1). 근무표가 하나면 그것, 보고서 = 보낸(편집 땐 규칙의) 근무표, 개인 = 주인의 근무표."""
        if self.fixed_board is not None:
            return self.fixed_board
        src = self.data if self.is_bound else self.initial
        if src.get("kind") == "report":
            picked = str(src.get("board") or "")
            return next((b for b in all_boards if str(b.pk) == picked), all_boards[0] if all_boards else boards.it_board())
        # ponytail: 빈 폼은 처음 그릴 때의 종류·근무표 기준이라 화면에서 종류·근무표를 바꿔도 체크박스는 그대로(저장 때 POST 값으로 다시 검사).
        # 고르는 즉시 다시 그리기는 2단계 근무표 고르기 화면과 함께
        return (boards.board_of(user) if user else None) or boards.it_board()

    @staticmethod
    def initial_from(rule) -> dict:
        h, m = divmod(rule.offset, 60)
        timed = rule.timing == "before_start"
        board_id = rule.board_id or _first_board_id()
        return dict(enabled=rule.enabled, kind=rule.kind, board=board_id, timing=rule.timing,
                    hours=h if timed else 2, minutes=m if timed else 0, days=1 if timed else rule.offset,
                    at_time=time(18, 0) if timed else time(*divmod(rule.at_minute, 60)),
                    telegram=rule.telegram, push=rule.push,
                    # 저장은 '전부 = 빈 목록'이라 그대로 그리면 전부 해제로 보인다 → 전부 체크로
                    shifts=rule.shifts or list(prefs.choices(boards.active_defs(Board.objects.get(pk=board_id)))),
                    depts=rule.depts or list(Department.objects.filter(board_id=board_id).values_list("code", flat=True)),
                    types=rule.types or [STAFF, DEVELOPER])

    def clean(self):
        c = super().clean()
        if self.errors:
            return c
        board = c.get("board") if "board" in self.fields else self.fixed_board
        if c["kind"] == "personal":  # 숨긴 체크박스 값이 와도 버린다. 개인 규칙의 근무표 = 주인의 근무표
            c["depts"], c["types"], board = [], [], None
        elif board is None:
            raise forms.ValidationError("근무표를 고르세요.")
        if c["timing"] == "before_start":
            offset, at_minute = (c["hours"] or 0) * 60 + (c["minutes"] or 0), 0
            if not 1 <= offset <= 10080:
                raise forms.ValidationError("시작 전 시간은 1분 이상 168시간 이하로 입력하세요.")
        else:
            offset, t = c["days"], c["at_time"]
            low = 1 if c["timing"] == "bizdays" else 0
            if offset is None or not low <= offset <= 30:
                raise forms.ValidationError(f"일 수는 {low}~30 사이로 입력하세요.")
            if t is None:
                raise forms.ValidationError("발송 시각을 입력하세요.")
            at_minute = t.hour * 60 + t.minute
        if not (c["telegram"] or c["push"]):
            raise forms.ValidationError("텔레그램이나 푸시 중 하나 이상 선택하세요.")
        c["rule"] = dict(enabled=c["enabled"], kind=c["kind"], board_id=board.pk if board else None,
                         timing=c["timing"], offset=offset, at_minute=at_minute, telegram=c["telegram"],
                         push=c["push"], shifts=c["shifts"], depts=c["depts"], types=c["types"])
        return c
```

`duty/views/alarms.py`. 13행 import 는 Task 3 상태(`alarm_settings, alarms, boards, calendar, prefs`)를 그대로 둔다(지적 18).
- `_index` 의 53행 `shift_names = prefs.choices(boards.defs(boards.it_board()))  # 1단계: ...` 줄과 54~55행 rules 첫 두 줄을 다음으로 바꾼다.

  ```python
      names_of = {}  # 근무표 → 스케줄 이름(규칙마다 그 규칙의 근무표: 개인 = 내 근무표, 보고서 = 규칙의 근무표)

      def shift_names(board):
          if board.pk not in names_of:
              names_of[board.pk] = prefs.choices(boards.defs(board))
          return names_of[board.pk]

      rules = [
          {"r": r, "timing": timing_label(r),
           "cond": condition_label(r, dept_names, shift_names(alarms.rule_board(request.user, r.kind, r.board_id))),
  ```

  바뀌기 전 54~55행은 다음과 같다.

  ```python
      rules = [
          {"r": r, "timing": timing_label(r), "cond": condition_label(r, dept_names, shift_names),
  ```

  다음 줄 `"channels": ...` 부터는 그대로 둔다.
- 같은 함수 68행 `"cal": CalendarFeed.objects.filter(user=request.user).first(), "shift_choices": list(shift_names.items()),` → 두 줄:

  ```python
          "cal": CalendarFeed.objects.filter(user=request.user).first(),
          "shift_choices": list(shift_names(alarms.rule_board(request.user, "personal", None)).items()),  # 캘린더 = 내 근무표
  ```

- `_rule_form` 의 폼 생성 두 줄에 `user=request.user` 를 넘긴다(개인 규칙의 스케줄 선택지 = 주인의 근무표).
  - 105행 `form = RuleForm(request.POST)` → `form = RuleForm(request.POST, user=request.user)`
  - 118행 `form = RuleForm(initial=RuleForm.initial_from(rule) if rule else None)` → `form = RuleForm(initial=RuleForm.initial_from(rule) if rule else None, user=request.user)`
- `_rule_form` 마지막 줄 `return render(request, "duty/alarm_rule_form.html", {"form": form, "rule": rule})` → 

  ```python
      return render(request, "duty/alarm_rule_form.html",
                    {"form": form, "rule": rule, "multi_board": "board" in form.fields})
  ```

  `same_day_notice` 호출은 커밋 2(Step 16)에서 바꾼다.

`duty/templates/duty/alarm_rule_form.html` 21행

```html
  <fieldset class="filter" data-kind="report"><legend>부서</legend>{{ form.depts }}</fieldset>
```

을 다음 두 줄로 바꾼다. 근무표가 하나면 출력 HTML 이 지금과 바이트까지 같다(`{% endif %}` 를 부서 fieldset 앞에 붙였기 때문).

```html
  {% if multi_board %}<fieldset class="filter" data-kind="report"><legend>근무표</legend>{{ form.board }}</fieldset>
  {% endif %}<fieldset class="filter" data-kind="report"><legend>부서</legend>{{ form.depts }}</fieldset>
```

- [ ] **Step 9: 전체 테스트**

Run: `.venv/bin/pytest -W error -q`
Expected: 모두 PASS, 경고 0. Task 7 끝 884 passed 에 새 테스트 9개를 더해 **893 passed**.

- [ ] **Step 10: 커밋**

```bash
git add duty/models.py duty/migrations/0017_alarmrule_board_rules.py duty/services/alarms.py duty/services/calendar.py \
  duty/alarms/forms.py duty/views/alarms.py duty/templates/duty/alarm_rule_form.html \
  tests/test_alarm_models.py tests/test_alarm_boards.py tests/test_run_alarms.py tests/test_views_alarms.py
git commit -m "feat: 알림 규칙에 근무표(보고서 = 근무표 하나), 스케줄·부서 검사와 기본 규칙을 근무표 정의로"
```

#### 커밋 2: 알림·변경 알림·캘린더를 근무 정의로

- [ ] **Step 11: IT 문구 고정 테스트를 쓴다 (순수, DB 없음)**

`tests/test_alarm_texts_it.py`(새 파일):

```python
"""IT 정의로 만든 알림 문구·hash 가 1단계 전과 한 글자도 같다(hash 가 달라지면 최근 45일 알림이 다시 나간다)."""
from datetime import date, datetime

from duty.alarms import messages as m
from duty.alarms.plan import RuleSpec, plan
from duty.alarms.schedule import same_day_notice
from duty.services.roster import Day
from duty.shifts import KEYS
from tests.it_defs import IT_DEFS

D = date(2026, 11, 16)  # 월
E = date(2026, 11, 10)  # 화
SUN18 = datetime(2026, 11, 15, 18)
INFO = {"가": ("MEMS", "개발자"), "나": ("MEMS", "직원"), "다": ("OTH", "개발자")}
DESTS = {(1, "telegram"): ["d"]}
REPORT_BODY = ("새벽(06:30~) 가\n정상(08:00~) 나\n석식교대(09:00~) -\n08:30~09:30 나\n09:30~10:30 -\n"
               "10:30~11:30 -\n11:30~12:30 -\n12:30~13:30 -\n13:30~14:30 -\n14:30~15:30 -\n15:30~16:30 -\n"
               "16:30~17:00 -\n17:00~18:00 -\n야간(13:30~) -")


def day(replaced=None, **cells):
    members = {c: [] for c in KEYS}
    members.update({k: list(v) for k, v in cells.items()})
    return Day(D, 1, {}, members, replaced or {})


def rule(**kw):
    base = dict(id=1, member_name="가", kind="personal", timing="days", offset=1, at_minute=18 * 60,
                channels=("telegram",), shifts=("dawn",), depts=(), types=())
    return RuleSpec(**{**base, **kw})


def run(r, d, deliveries=None, **kw):
    return plan(IT_DEFS, [r], [d], INFO, deliveries or {}, SUN18, destinations=DESTS, **kw)


def test_personal_shift():
    [due] = run(rule(), day(dawn=["가"]))
    assert (due.title, due.text, due.content_hash, due.url, due.expires_at) == (
        "당번 알림", "[당번 알림] 11/16(월) 새벽 06:30~15:30\n가님, 내일 새벽 당번입니다.", "in:b67c7c6d5f7f719a",
        "/day/2026-11-16/", datetime(2026, 11, 16, 6, 30))
    assert due.push_text == "[당번 알림] 11/16(월) 새벽 06:30~15:30 가님, 내일 새벽 당번입니다."


def test_personal_slot():
    [due] = run(rule(shifts=("slots",)), day(slot0=["가"]))
    assert (due.cell, due.text, due.content_hash, due.expires_at) == (
        "slot0", "[당번 알림] 11/16(월) 08:30~09:30\n가님, 내일 장중관제입니다.", "in:c4693d2be729b43f",
        datetime(2026, 11, 16, 8, 30))


def test_cancel():
    sent = {(1, D, "dawn", "telegram", "d"): "in:b67c7c6d5f7f719a"}
    [due] = run(rule(), day(dawn=["나"], replaced={("dawn", "나"): "가"}), sent)
    assert (due.title, due.text, due.content_hash) == (
        "당번 변경", "[당번 변경] 11/16(월) 새벽 06:30~15:30\n가님의 근무가 취소되었습니다. (후임: 나)",
        "out:3b1b539a890431ae")


def test_report_full_text():
    r = rule(kind="report", member_name=None, shifts=(), depts=("MEMS",))
    d = day(dawn=["가"], normal=["나"], slot0=["나"], night=["다"])
    [due] = run(r, d, dept_names={"MEMS": "매칭엔진실"})
    assert (due.title, due.text, due.content_hash, due.push_text, due.url, due.expires_at) == (
        "출근표", "[출근표] 11/16(월) — 매칭엔진실\n" + REPORT_BODY, "report:1b8af80d11eb4183",
        "[출근표] 11/16(월) — 매칭엔진실 · 2명", "/day/2026-11-16/", datetime(2026, 11, 16, 17, 0))
    [changed] = run(r, d, {(1, D, "report", "telegram", "d"): "old"}, dept_names={"MEMS": "매칭엔진실"})
    assert changed.text == "[출근표 변경] 11/16(월) — 매칭엔진실\n" + REPORT_BODY
    assert changed.content_hash == "report:1b8af80d11eb4183"


def test_change_notices():
    assert m.change_notice(IT_DEFS, E, "slot0", "가", "나", "관리자") == (
        "근무 변경", "[근무 변경] 11/10(화) 장중관제 08:30~09:30\n가 → 나\n바꾼 사람: 관리자")
    assert m.change_notice(IT_DEFS, E, "normal", None, "나", "관리자") == (
        "근무 변경", "[근무 변경] 11/10(화) 정상\n+나\n바꾼 사람: 관리자")
    assert m.change_notice(IT_DEFS, E, "night", "가", None, "관리자") == (
        "근무 변경", "[근무 변경] 11/10(화) 야간\n가 빠짐\n바꾼 사람: 관리자")
    assert m.swap_notice(IT_DEFS, E, "normal", "가", "dinner", "나", "다") == (
        "근무 변경", "[근무 변경] 11/10(화) 맞교환\n가 정상 → 석식교대\n나 석식교대 → 정상\n바꾼 사람: 다")


def test_same_day_notices():
    assert same_day_notice(IT_DEFS, "personal", "days", 0, 10 * 60, []) == \
        "새벽·정상·석식교대·장중관제 08:30~10:30은 발송 시각이 근무 시작 이후라 제외됩니다."
    assert same_day_notice(IT_DEFS, "report", "days", 0, 17 * 60, []) == "현재 선택으로는 보고서가 발송되지 않습니다."
    assert same_day_notice(IT_DEFS, "personal", "days", 0, 20 * 60, ["slots", "night"]) == \
        "현재 선택으로는 발송되는 근무가 없습니다."
```

Run: `.venv/bin/pytest -W error tests/test_alarm_texts_it.py -q`
Expected: `6 failed`. 모두 `TypeError` 다(`plan()`·`change_notice()`·`same_day_notice()` 가 아직 defs 첫 인자를 받지 않음).

- [ ] **Step 12: 순수 모듈 셋을 통째로 바꾼다**

Task 3 이 넣은 `LEGACY_DEFS` 자리를 `defs` 인자로 바꾼다. 문구 틀과 순서는 그대로다.

`duty/alarms/messages.py` 전체:

```python
"""알림 문구. ORM 없음. 칸 이름·시각은 근무표 정의 목록(defs)에서 읽는다."""
from datetime import date

from ..shifts import DAY_LABELS, SLOT_GROUP_NAME, cell_end, cell_label, cell_start, is_slot_cell

CUT = "…(이하 생략, 웹에서 확인)"
PERSONAL_TITLE, CANCEL_TITLE, REPORT_TITLE = "당번 알림", "당번 변경", "출근표"


def day_label(d: date) -> str:
    return f"{d.month}/{d.day}({DAY_LABELS[d.weekday()]})"


def relative_day(d: date, today: date) -> str:
    return {0: "오늘", 1: "내일"}.get((d - today).days, day_label(d))


def cell_span(defs, cell: str) -> str:
    """'새벽 06:30~15:30' 또는 '10:30~11:30'."""
    if is_slot_cell(cell):
        return cell_label(defs, cell)
    return f"{cell_label(defs, cell)} {cell_start(defs, cell):%H:%M}~{cell_end(defs, cell):%H:%M}"


def _kind(defs, cell: str) -> str:
    return SLOT_GROUP_NAME if is_slot_cell(cell) else f"{cell_label(defs, cell)} 당번"


def _where(defs, cell: str) -> str:
    return f"{SLOT_GROUP_NAME} {cell_label(defs, cell)}" if is_slot_cell(cell) else cell_label(defs, cell)


def change_notice(defs, d: date, cell: str, before: str | None, after: str | None, by: str) -> tuple[str, str]:
    """내 근무가 바뀌었을 때(제목, 본문). 교체 A → B, 넣기 +B, 빼기 A 빠짐."""
    what = f"{before} → {after}" if before and after else (f"+{after}" if after else f"{before} 빠짐")
    return "근무 변경", f"[근무 변경] {day_label(d)} {_where(defs, cell)}\n{what}\n바꾼 사람: {by}"


def swap_notice(defs, d: date, cell_a: str, a: str, cell_b: str, b: str, by: str) -> tuple[str, str]:
    """맞교환 한 번(기록 2건)을 한 통으로: A 는 cell_a → cell_b, B 는 반대로."""
    return "근무 변경", (f"[근무 변경] {day_label(d)} 맞교환\n{a} {_where(defs, cell_a)} → {_where(defs, cell_b)}\n"
                       f"{b} {_where(defs, cell_b)} → {_where(defs, cell_a)}\n바꾼 사람: {by}")


def personal_text(defs, name: str, d: date, cell: str, today: date) -> str:
    return (f"[{PERSONAL_TITLE}] {day_label(d)} {cell_span(defs, cell)}\n"
            f"{name}님, {relative_day(d, today)} {_kind(defs, cell)}입니다.")


def cancel_text(defs, name: str, d: date, cell: str, successor: str | None = None) -> str:
    tail = f" (후임: {successor})" if successor else ""
    return f"[{CANCEL_TITLE}] {day_label(d)} {cell_span(defs, cell)}\n{name}님의 근무가 취소되었습니다.{tail}"


def report_header(d: date, cond: str, changed: bool) -> str:
    title = f"{REPORT_TITLE} 변경" if changed else REPORT_TITLE
    return f"[{title}] {day_label(d)}" + (f" — {cond}" if cond else "")


def report_line(defs, cell: str, names: list[str]) -> str:
    label = cell_label(defs, cell) if is_slot_cell(cell) else f"{cell_label(defs, cell)}({cell_start(defs, cell):%H:%M}~)"
    return f"{label} {', '.join(names) if names else '-'}"


def clip(text: str, limit: int = 4000) -> str:
    return text if len(text) <= limit else text[: limit - len(CUT)] + CUT


def clip_bytes(text: str, limit: int = 1000) -> str:
    return text if len(text.encode()) <= limit else text.encode()[: limit - 3].decode(errors="ignore") + "..."
```

`duty/alarms/schedule.py` 전체:

```python
"""알림 발송 시각 계산. ORM 없음, Asia/Seoul naive datetime. 칸 시각·이름은 근무표 정의 목록(defs)에서."""
from datetime import date, datetime, time, timedelta

from ..shifts import SLOT_GROUP_NAME, cell_end, cell_label, cell_start, cells_of, is_slot_cell


def bizdays_back(d: date, n: int) -> date:
    if n < 0:
        raise ValueError("영업일 수는 0 이상이어야 합니다.")
    while n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def send_at(timing: str, offset: int, at_minute: int, day: date, start: datetime) -> datetime:
    if timing == "before_start":
        return start - timedelta(minutes=offset)
    if timing == "days":
        base = day - timedelta(days=offset)
    elif timing == "bizdays":
        base = bizdays_back(day, offset)
    else:
        raise ValueError("알 수 없는 발송 시점입니다.")
    return datetime.combine(base, time(at_minute // 60, at_minute % 60))


def _topic(word: str) -> str:
    """'새벽·정상' + 은/는 (마지막 글자 받침 기준)."""
    c = word[-1]
    return word + ("는" if "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 == 0 else "은")


def same_day_notice(defs, kind: str, timing: str, offset: int, at_minute: int, shifts: list[str]) -> str | None:
    """당일 발송 규칙에서 발송 시각이 근무 시작 이후라 빠지는 칸 안내. 없으면 None."""
    if timing != "days" or offset != 0:
        return None
    cells = cells_of(defs, shifts)
    if not cells:  # 이 근무표에 없는 키만 골랐다(plan 도 조용히 무시한다)
        return None
    starts = {c: cell_start(defs, c).hour * 60 + cell_start(defs, c).minute for c in cells}
    if kind == "report":
        return "현재 선택으로는 보고서가 발송되지 않습니다." if at_minute >= max(starts.values()) else None
    late = [c for c in cells if at_minute >= starts[c]]
    if not late:
        return None
    if len(late) == len(cells):
        return "현재 선택으로는 발송되는 근무가 없습니다."
    names = [cell_label(defs, c) for c in late if not is_slot_cell(c)]
    slots = [c for c in late if is_slot_cell(c)]  # 시작 순서라 항상 앞쪽부터 연속
    if slots:
        whole = len(slots) == sum(map(is_slot_cell, cells))
        names.append(SLOT_GROUP_NAME if whole else
                     f"{SLOT_GROUP_NAME} {cell_start(defs, slots[0]):%H:%M}~{cell_end(defs, slots[-1]):%H:%M}")
    return f"{_topic('·'.join(names))} 발송 시각이 근무 시작 이후라 제외됩니다."
```

`duty/alarms/plan.py` 전체:

```python
"""지금 보내야 할 알림 계산. ORM 없음. 모든 시각은 Asia/Seoul naive. 근무표 하나의 정의(defs)·근무표(days)·규칙만 받는다."""
import hashlib
from dataclasses import dataclass
from datetime import date, datetime

from ..services.roster import Day
from ..shifts import KEYS, cell_start, cells_of
from . import messages as m
from .schedule import send_at


@dataclass(frozen=True)
class RuleSpec:
    id: int
    member_name: str | None
    kind: str  # "personal" | "report"
    timing: str
    offset: int
    at_minute: int
    channels: tuple[str, ...]
    shifts: tuple[str, ...]
    depts: tuple[str, ...]
    types: tuple[str, ...]


@dataclass(frozen=True)
class Due:
    rule_id: int
    date: date
    cell: str  # 칸 키 또는 "report"
    channel: str
    title: str
    text: str
    content_hash: str
    url: str
    expires_at: datetime
    push_text: str
    destination: str = ""


def _empty(d: date) -> Day:
    return Day(d, 0, {}, {c: [] for c in KEYS}, {})


def _hash(prefix: str, text: str) -> str:
    return f"{prefix}:{hashlib.sha256(text.encode()).hexdigest()[:16]}"


def plan(defs, rules, days, info, deliveries, now, destinations=None, dept_names=None, extra_dates=None,
         today=None) -> list[Due]:
    """defs: 이 근무표의 정의. destinations: (rule_id, channel) → 목적지 목록.
    deliveries: (rule_id, date, cell, channel, destination) → 그 목적지에 마지막으로 성공한 내용 hash(없으면 None)."""
    today = today or now.date()
    destinations = destinations or {}
    by_date = {d.date: d for d in days}
    synthetic = {d for d in (extra_dates or ()) if d not in by_date}
    for d in synthetic:
        by_date[d] = _empty(d)
    dept_names = dept_names or {}
    out: list[Due] = []
    for day in sorted(by_date.values(), key=lambda x: x.date):
        for r in rules:
            cells = cells_of(defs, list(r.shifts))  # 이 근무표에 없는 키는 조용히 무시
            if not cells:
                continue
            starts = {c: datetime.combine(day.date, cell_start(defs, c)) for c in cells}
            if r.kind == "personal":
                if r.member_name:
                    out += _personal(defs, r, day, cells, starts, deliveries, now, destinations, today)
            elif r.kind == "report":
                out += _report(defs, r, day, cells, starts, info, deliveries, now, dept_names, day.date in synthetic,
                               destinations)
    return out


def _successor(day, cell, name):
    """replaced 간선을 모두 따라가 도달 가능한 사람 중 지금 칸에 있는 후임(최근 간선 우선)."""
    edges = [(old, new) for (c, new), old in day.replaced.items() if c == cell]
    seen, todo = {name}, [name]
    while todo:
        cur = todo.pop()
        for old, new in edges:
            if old == cur and new not in seen:
                seen.add(new)
                todo.append(new)
    now_in = day.members.get(cell, [])
    for _, new in reversed(edges):
        if new != name and new in seen and new in now_in:
            return new
    return None


def _targets(r, destinations):
    return [(ch, dest) for ch in r.channels for dest in destinations.get((r.id, ch), ())]


def _personal(defs, r, day, cells, starts, deliveries, now, destinations, today):
    out = []
    for c in cells:
        start = starts[c]
        if not send_at(r.timing, r.offset, r.at_minute, day.date, start) <= now < start:
            continue
        inside = r.member_name in day.members.get(c, [])
        if inside:
            title, text = m.PERSONAL_TITLE, m.personal_text(defs, r.member_name, day.date, c, today)
            # 오늘/내일 표기는 hash에서 뺀다(자정이 지났다고 다시 보내지 않게)
            h = _hash("in", m.personal_text(defs, r.member_name, day.date, c, day.date))
        else:
            title = m.CANCEL_TITLE
            text = m.cancel_text(defs, r.member_name, day.date, c, _successor(day, c, r.member_name))
            h = _hash("out", text)
        for ch, dest in _targets(r, destinations):
            last = deliveries.get((r.id, day.date, c, ch, dest))
            # 취소는 이 목적지에 무언가 성공적으로 알린 적이 있을 때만
            if last == h or (not inside and not (last or "").startswith(("in:", "out:"))):
                continue
            out.append(Due(r.id, day.date, c, ch, title, m.clip(text), h, f"/day/{day.date.isoformat()}/",
                           start, m.clip_bytes(text.replace("\n", " ")), dest))
    return out


def _report(defs, r, day, cells, starts, info, deliveries, now, dept_names, synthetic, destinations):
    first, last_start = min(starts.values()), max(starts.values())
    if not send_at(r.timing, r.offset, r.at_minute, day.date, first) <= now < last_start:
        return []

    def keep(name):
        dept, typ = info.get(name, ("", ""))
        return (not r.depts or dept in r.depts) and (not r.types or typ in r.types)

    lines, uniq = [], set()
    for c in cells:
        names = [n for n in day.members.get(c, []) if keep(n)]
        uniq.update(names)
        lines.append(m.report_line(defs, c, names))
    cond = "·".join([dept_names.get(x, x) for x in r.depts] + list(r.types))
    # 변경 표지만 빼고 보이는 내용 전체(머리·조건·근무표)
    h = _hash("report", "\n".join([m.report_header(day.date, cond, False), *lines]))
    out = []
    for ch, dest in _targets(r, destinations):
        prev = deliveries.get((r.id, day.date, "report", ch, dest))
        if prev == h or (prev is None and synthetic):
            continue
        head = m.report_header(day.date, cond, prev is not None)
        summary = f"{head} · {len(uniq)}명"
        out.append(Due(r.id, day.date, "report", ch, m.REPORT_TITLE, m.clip("\n".join([head, *lines])), h,
                       f"/day/{day.date.isoformat()}/", last_start, m.clip_bytes(summary), dest))
    return out
```

- [ ] **Step 13: 기존 순수 테스트를 기계적으로 고친다 (허용 변환 (c), 단언 그대로)**

`tests/test_alarm_plan.py`
- 5행 `from duty.shifts import CELLS` → 두 줄:

  ```python
  from duty.shifts import KEYS
  from tests.it_defs import IT_DEFS
  ```

- 12행 `members = {c: [] for c in CELLS}` → `members = {c: [] for c in KEYS}`
- 30행 `return plan(rules, days, INFO, deliveries or {}, now, **kw)` → `return plan(IT_DEFS, rules, days, INFO, deliveries or {}, now, **kw)`
- 163행 `due = plan([r], d, info, {}, SUN18, dests([r]))[0]` → `due = plan(IT_DEFS, [r], d, info, {}, SUN18, dests([r]))[0]`
- 166행 `p = plan([rule(shifts=("dawn",))], ...` → `p = plan(IT_DEFS, [rule(shifts=("dawn",))], ...`(나머지 인자 그대로)

`tests/test_change_notice.py`
- 9행 `from duty.services import alarm_settings, boards, change_notice, changes` 아래에 `from tests.it_defs import IT_DEFS` 를 더한다.
- 71행 `m.change_notice(D, "slot0", "가", "나", "관리자")` → `m.change_notice(IT_DEFS, D, "slot0", "가", "나", "관리자")`
- 74행 `m.change_notice(D, "normal", None, "나", "관리자")` → `m.change_notice(IT_DEFS, D, "normal", None, "나", "관리자")`

`tests/test_views_alarms.py::test_same_day_notice_collapses_slots`(436~438행)
- 함수 안 `from duty.alarms.schedule import same_day_notice` 아래에 `    from tests.it_defs import IT_DEFS` 를 더한다.
- `same_day_notice("personal", "days", 0, 10 * 60, [])` → `same_day_notice(IT_DEFS, "personal", "days", 0, 10 * 60, [])`

Run: `.venv/bin/pytest -W error tests/test_alarm_texts_it.py tests/test_alarm_plan.py tests/test_change_notice.py::test_message_text tests/test_views_alarms.py::test_same_day_notice_collapses_slots -q`
Expected: `29 passed`

호출부(alarm_runner·change_notice·views)는 아직 옛 인자를 쓴다. 그래서 `test_run_alarms`·`test_change_notice`·`test_ops` 의 일부는 Step 16 까지 `TypeError` 로 실패한다.

- [ ] **Step 14: 작업자·변경 알림·캘린더 테스트를 쓴다**

`tests/test_alarm_boards.py` 맨 위부터 `SUN = date(2026, 11, 15)` 줄까지를 다음으로 바꾼다:

```python
"""근무표가 둘일 때 알림 규칙·정기 알림·변경 알림·캘린더가 서로 영향 없음(1단계)."""
from datetime import date, datetime, time, timedelta

import pytest
from django.utils import timezone

from duty.alarms import senders
from duty.alarms.forms import RuleForm
from duty.errors import DutyError
from duty.models import (AlarmDelivery, AlarmRule, AlarmSettings, Board, BoardShift, ChangeLog, Commute, Department,
                         Period, PeriodEvent, TelegramAlarmProfile, User)
from duty.services import alarm_runner, alarms, calendar, change_notice

D = date(2026, 11, 16)  # 월
SUN = date(2026, 11, 15)
SUN18 = timezone.make_aware(datetime(2026, 11, 15, 18))
```

`def report_base(board_id, **kw):` 바로 앞에 더한다:

```python
@pytest.fixture
def env(settings, fixed_today, monkeypatch, db):
    """텔레그램만 켜고 보낸 것을 (chat_id, 본문)으로 모은다(실제 호출 없음)."""
    AlarmSettings.objects.update_or_create(pk=1, defaults=dict(telegram_bot_token="t"))
    settings.SITE_URL = ""
    fixed_today(SUN)
    sent = []
    monkeypatch.setattr(senders, "telegram_send", lambda cfg, chat, text: sent.append((chat, text)) or {})
    monkeypatch.setattr(senders, "push_send", lambda *a, **k: pytest.fail("푸시는 보내지 않는다"))
    return sent


def person(name, dept, chat):
    """발급된 계정(기본 알림 규칙 포함) + 확인된 텔레그램."""
    u = User.objects.create_user(f"{dept.code}{chat}", password="unused-Pw-123", name=name, department=dept,
                                 type="직원")
    alarms.create_defaults(u)
    TelegramAlarmProfile.objects.create(user=u, chat_id=chat, verified_at=timezone.now())
    return u


def published(board, *rows):
    p = Period.objects.create(board=board, name=board.code, start_date=D, end_date=D, overwrite_from=D,
                              status=Period.Status.PUBLISHED, published_at=timezone.now())
    for member, shift in rows:
        Commute.objects.create(period=p, date=D, member=member, shift=shift)
    return p


```

파일 끝에 더한다:

```python


# ---- 정기 알림 ----

def test_same_date_on_two_boards_no_cross_cancel(env, depts, it_board, ops):
    """같은 날짜에 다른 근무표가 있어도 IT 개인 규칙에 취소 알림이 나가지 않는다."""
    board, dept = ops
    it, op = person("가상아이", depts["MEMS"], "111"), person("가상운영", dept, "222")
    published(it_board, (it, "dawn"))
    published(board, (op, "dawn"))
    assert alarm_runner.tick(SUN18) == (2, 2, 0)
    assert sorted(env) == [("111", "[당번 알림] 11/16(월) 새벽 06:30~15:30\n가상아이님, 내일 새벽 당번입니다."),
                           ("222", "[당번 알림] 11/16(월) 오전 07:30~16:30\n가상운영님, 내일 오전 당번입니다.")]
    env.clear()
    assert alarm_runner.tick(SUN18 + timedelta(minutes=1)) == (0, 0, 0)
    assert env == []


def test_report_rule_reads_only_its_board(env, depts, it_board, ops, admin_user):
    board, dept = ops
    it, op = person("가상아이", depts["MEMS"], "111"), person("가상운영", dept, "222")
    AlarmRule.objects.filter(user__in=[it, op]).delete()
    published(it_board, (it, "dawn"))
    published(board, (op, "dawn"))
    AlarmRule.objects.create(user=admin_user, kind="report", board=board, timing="days", offset=1,
                             at_minute=18 * 60, telegram=True, shifts=[], depts=[], types=[])
    TelegramAlarmProfile.objects.create(user=admin_user, chat_id="999", verified_at=timezone.now())
    alarm_runner.tick(SUN18)
    assert env == [("999", "[출근표] 11/16(월)\n오전(07:30~) 가상운영\n주간(09:00~) -\n오후(11:00~) -")]


def test_owned_day_without_rows_sends_no_report(env, depts, it_board, admin_user):
    """그날의 주인은 있어도 배정이 하나도 없는 날은 정기 알림에 넘기지 않는다(빈 보고서 방지)."""
    published(it_board)
    AlarmRule.objects.create(user=admin_user, kind="report", board=it_board, timing="days", offset=1,
                             at_minute=18 * 60, telegram=True, shifts=[], depts=[], types=[])
    TelegramAlarmProfile.objects.create(user=admin_user, chat_id="999", verified_at=timezone.now())
    assert alarm_runner.tick(SUN18) == (0, 0, 0)


# ---- 변경 알림 ----

def test_change_notice_uses_period_board_names(env, depts, ops):
    board, dept = ops
    a, b = person("가상운영", dept, "222"), person("가상운영둘", dept, "333")
    p = published(board, (b, "dawn"))
    ChangeLog.objects.create(period=p, date=D, cell="dawn", before=a, after=b)
    change_notice.tick(timezone.now())
    assert sorted(env) == [(c, "[근무 변경] 11/16(월) 오전\n가상운영 → 가상운영둘\n바꾼 사람: -") for c in ("222", "333")]


def test_change_notice_sent_when_period_owns_empty_day(env, depts, it_board):
    """배정이 다 빠진 날도 그 회차가 그날의 주인이면 보낸다."""
    a = person("가상아이", depts["MEMS"], "111")
    p = published(it_board)
    ChangeLog.objects.create(period=p, date=D, cell="dawn", before=a, after=None)
    change_notice.tick(timezone.now())
    assert env == [("111", "[근무 변경] 11/16(월) 새벽\n가상아이 빠짐\n바꾼 사람: -")]


def test_change_notice_skipped_when_newer_period_owns_day(env, depts, it_board):
    a = person("가상아이", depts["MEMS"], "111")
    old, new = published(it_board, (a, "dawn")), published(it_board, (a, "dawn"))
    PeriodEvent.objects.create(period=old, from_status="generated", to_status="published")
    PeriodEvent.objects.create(period=new, from_status="generated", to_status="published")
    ChangeLog.objects.create(period=old, date=D, cell="dawn", before=a, after=None)
    change_notice.tick(timezone.now())
    assert env == []


# ---- 캘린더 ----

def test_calendar_uses_member_board_definitions(env, depts, it_board, ops):
    board, dept = ops
    it, op = person("가상아이", depts["MEMS"], "111"), person("가상운영", dept, "222")
    published(it_board, (it, "normal"))
    published(board, (op, "normal"))
    [e] = calendar._events(op)
    assert (e.summary, e.start.time(), e.end.time(), e.uid) == (
        "주간 출근 09:00~18:00", time(9), time(18), f"20261116-normal-{op.pk}@duty-generator")
    [e] = calendar._events(it)
    assert e.summary == "정상 출근 08:00~17:00"
```

Run: `.venv/bin/pytest -W error tests/test_alarm_boards.py -q`
Expected: `7 failed, 7 passed`
- 정기 알림 3개: `collect` 가 `plan` 을 옛 인자로 불러 `TypeError`
- 변경 알림 3개: `m.change_notice`·`m.swap_notice` 를 옛 인자로 불러 `TypeError`
- 캘린더 1개: `_events` 가 아직 `LEGACY_DEFS`(IT 정의)를 써서 운영팀 일정이 IT 이름·시각("정상 출근 08:00~17:00")으로 나와 단언이 실패한다.

- [ ] **Step 15: `alarm_runner.collect` 를 근무표마다로 바꾼다**

`duty/services/alarm_runner.py` 16~17행 models import 에 `Board` 를 더한다:

```python
from ..models import (AlarmDelivery, AlarmDeliveryStatus, AlarmRule, Board, Department,
                      PushAlarmSubscription, TelegramAlarmProfile, User)
```

60행 `SNAP = ("user_id", "enabled", "telegram", "push", *RULE_FIELDS)` 은 글자 그대로 둔다(`RULE_FIELDS` 에 `board_id` 가 들어 있다). `collect` 전체(83~113행)를 바꾼다:

```python
def collect(now):
    """보낼 (Due, 기존 기록, 규칙 스냅숏) 목록. 근무표마다 그 근무표의 근무표·규칙으로 따로 계획한다
    (개인 = 주인 부서의 근무표, 보고서 = 규칙의 근무표). 같은 내용의 backoff 중인 것은 뺀다."""
    if timezone.is_naive(now):
        raise ValueError("now는 aware datetime이어야 합니다.")
    today = perms.today()
    rules = [r for r in AlarmRule.objects.filter(enabled=True, user__is_active=True).select_related("user__department")
             if _valid(r, today)]
    snaps = {r.id: _snap(r) for r in rules}
    # 개인 알림 대상은 근무표 대상 계정(부서 있음)만. 부서 없는 어드민의 개인 규칙은 어느 근무표에도 넣지 않는다
    by_board = defaultdict(list)
    for r in rules:
        board_id = r.board_id if r.kind == "report" else (r.user.department.board_id if r.user.department_id else None)
        if board_id is not None:
            by_board[board_id].append(r)
    rows = {(d.rule_id, d.date, d.cell, d.channel, d.destination): d
            for d in AlarmDelivery.objects.filter(date__gte=today)}
    info = {n: (dept, typ) for n, dept, typ in User.objects.values_list("name", "department__code", "type")}
    deliveries = {k: d.last_sent_hash for k, d in rows.items()}
    destinations = _destinations(rules, alarm_settings.current())
    dept_names = dict(Department.objects.values_list("code", "name"))
    local_now = timezone.localtime(now).replace(tzinfo=None)
    dues = []
    for board in Board.objects.filter(pk__in=list(by_board)).order_by("id"):
        group = by_board[board.id]
        ids = {r.id for r in group}
        specs = [RuleSpec(r.id, r.user.name if r.user.department_id else None, r.kind, r.timing, r.offset,
                          r.at_minute, tuple(ch for ch in ("telegram", "push") if getattr(r, ch)),
                          tuple(r.shifts), tuple(r.depts), tuple(r.types)) for r in group]
        # 주인은 있어도 배정이 하나도 없는 날은 넘기지 않는다(빈 보고서 방지, 설계 6.1).
        # 그날의 옛 발송 기록은 extra_dates 의 빈 날로 계산돼 취소가 나간다(지금과 같다)
        days = [d for d in published_days(board, today, today + HORIZON) if any(d.members.values())]
        dues += plan(boards.defs(board), specs, days, info, deliveries, local_now,
                     destinations=destinations, dept_names=dept_names,
                     extra_dates={k[1] for k in rows if k[0] in ids}, today=today)
    out = []
    for due in dues:
        row = rows.get((due.rule_id, due.date, due.cell, due.channel, due.destination))
        if (row and row.status == AlarmDeliveryStatus.FAILED and row.content_hash == due.content_hash
                and row.next_attempt_at and row.next_attempt_at > now):
            continue
        out.append((due, row, snaps[due.rule_id]))
    return out
```

Run: `.venv/bin/pytest -W error tests/test_alarm_boards.py tests/test_run_alarms.py tests/test_ops.py -q`
Expected: 변경 알림 3개와 캘린더 1개만 실패한다(`4 failed, 75 passed`).

- [ ] **Step 16: 변경 알림·캘린더·규칙 저장 안내를 바꾼다**

`duty/services/change_notice.py` 8~9행 → (`Commute`·`DutyAssignment` 는 더 쓰지 않는다)

```python
from ..models import ChangeLog, Period, PushAlarmSubscription, TelegramAlarmProfile
from . import alarm_settings, boards
```

`tick` 전체(16~40행):

```python
def tick(now) -> int:
    rows = list(ChangeLog.objects.filter(notified=False)
                .select_related("by", "before", "after", "period__board").order_by("id"))
    if not rows:
        return 0
    # 먼저 표시하고 보낸다: 보내는 도중 작업자가 죽어도 다시 보내지 않는다(최대 한 번). 실패는 로그만
    ChangeLog.objects.filter(pk__in=[r.pk for r in rows]).update(notified=True)
    conf, today, sent, i = alarm_settings.current(), perms.today(), 0, 0
    defs_of = {}  # 근무표 id → 정의(문구는 그 기록의 회차 근무표 이름으로)
    while i < len(rows):
        r = rows[i]
        pair = rows[i + 1] if i + 1 < len(rows) and _is_swap(r, rows[i + 1]) else None
        i += 2 if pair else 1
        if not _live(r, now, today):
            continue
        board = r.period.board
        if board.pk not in defs_of:
            defs_of[board.pk] = boards.defs(board)
        defs = defs_of[board.pk]
        by = (r.by.name or r.by.username) if r.by else "-"
        if pair:
            title, text = m.swap_notice(defs, r.date, r.cell, r.before.name, pair.cell, r.after.name, by)
        else:
            title, text = m.change_notice(defs, r.date, r.cell, r.before and r.before.name,
                                          r.after and r.after.name, by)
        for u in {r.before, r.after} - {None, r.by}:
            if u.is_active and u.notify_changes:
                sent += _send(conf, u, title, text, f"/day/{r.date.isoformat()}/")
    if sent:
        log.info("change notices: sent=%d", sent)
    return sent
```

`_live` 전체(48~54행):

```python
def _live(r, now, today) -> bool:
    """지금 근무표에 살아 있는 기록만: 그 기록의 회차가 아직 그날의 주인(설계 6.1)이고 배포 취소 이전 기록이 아니다.
    배정이 하나도 없는 날도 주인이면 보낸다."""
    p = r.period
    if not (r.at >= now - FRESH and r.date >= today and p.status == Period.Status.PUBLISHED and r.id > p.log_floor):
        return False
    owner = boards.owner(p.board, r.date)
    return owner is not None and owner.pk == p.pk
```

`duty/services/calendar.py`
- 17행 → `from ..shifts import SLOT_GROUP, SLOT_GROUP_NAME, is_slot_cell, ordered`
- `_events` 전체(80행~끝):

```python
def _events(member, shifts=()) -> list[ics.Event]:
    since = perms.today() - WINDOW
    board = boards.board_of(member)  # feed()가 부서 있는 계정만 부른다
    defs = boards.defs(board)
    # 배정이 하나도 없는 날은 넣지 않는다(그날 기록이 DTSTAMP·ETag 를 바꾸지 않게)
    days = [d for d in roster.published_days(board, since, None) if any(d.members.values())]
    published = dict(Period.objects.filter(pk__in={d.period_id for d in days}).values_list("pk", "published_at"))
    for pid in sorted(pk for pk, at in published.items() if at is None):
        logger.warning("calendar feed: published_at 없는 배포 회차 %s 제외", pid)
    days = [d for d in days if published[d.period_id]]
    if not days:
        return []
    owner = {d.date: d.period_id for d in days}
    changes = ChangeLog.objects.filter(period_id__in=set(owner.values()), date__gte=since).values_list("period_id", "date", "at")
    dtstamp = max([published[pid] for pid in owner.values()] + [at for pid, d, at in changes if owner.get(d) == pid])  # 행 없는 날짜의 기록은 제외

    tz = timezone.get_default_timezone()
    url = settings.SITE_URL.rstrip("/") + reverse("me") if settings.SITE_URL else None
    events = []
    for day in days:
        for x in ordered(defs):  # KEYS 순(옛 CELLS 와 같다). 모르는 키는 정의에 없어 조용히 빠진다
            cell = x.key
            if member.name not in day.members.get(cell, ()) or \
                    (shifts and (SLOT_GROUP if is_slot_cell(cell) else cell) not in shifts):
                continue
            summary = f"{SLOT_GROUP_NAME} {x.name}" if is_slot_cell(cell) else f"{x.name} 출근 {x.start:%H:%M}~{x.end:%H:%M}"
            events.append(ics.Event(
                uid=f"{day.date:%Y%m%d}-{cell}-{member.pk}@duty-generator", dtstamp=dtstamp,
                start=datetime.combine(day.date, x.start, tz), end=datetime.combine(day.date, x.end, tz),
                summary=summary, url=url))
    return events
```

`duty/views/alarms.py::_rule_form` 의 `notice = same_day_notice(saved.kind, ...)` 한 줄을 두 줄로:

```python
                defs = boards.defs(alarms.rule_board(request.user, saved.kind, saved.board_id))
                notice = same_day_notice(defs, saved.kind, saved.timing, saved.offset, saved.at_minute, saved.shifts)
```

Run: `.venv/bin/pytest -W error tests/test_alarm_boards.py tests/test_change_notice.py tests/test_calendar_feed.py tests/test_views_calendar.py tests/test_views_alarms.py -q`
Expected: PASS. `test_calendar_feed.py::test_changelog_on_date_without_rows_keeps_feed_200`(DTSTAMP 그대로)도 통과한다.

- [ ] **Step 17: 더 쓰지 않는 옛 상수를 지운다**

확인: `grep -rnE "COMMUTE_SHIFTS|CONTROL_SLOTS|SHIFT_TIMES|LEGACY_DEFS|\bCELLS\b|slot_cell\b" duty tools --include=*.py | grep -v "^duty/shifts.py"`
Expected: `duty/services/calendar.py` 의 주석 한 줄("옛 CELLS 와 같다")만 나온다. 코드에서 쓰는 곳은 없다.

`duty/shifts.py`
- 14행 `CELLS = KEYS  # 1단계 동안 남기는 옛 이름` 을 지운다.
- 36~37행 `def slot_cell(i: int) -> str:` 함수(와 뒤 빈 줄 둘)를 지운다.
- 101행 `# ---- 1단계 이행용 옛 상수. ...` 부터 파일 끝(`LEGACY_DEFS: list[Def] = _legacy_defs() ...`)까지 지운다. 그 앞 빈 줄 둘도 지워 `weekdays` 의 `return out` 이 마지막 줄이 되게 한다.

`tests/test_shifts.py`
- 4행 import 의 `CELLS, LEGACY_DEFS, ` → `KEYS, `
- 42행 `assert cells_of(IT_DEFS, []) == CELLS` → `assert cells_of(IT_DEFS, []) == KEYS`(같은 값. `CELLS` 는 `KEYS` 의 옛 이름이었다)
- 72~75행 `test_legacy_defs_equal_it_defs` 를 지운다. Task 3 이 이행용으로 더한 테스트이고, 같은 내용은 `test_alarm_texts_it` 이 문구로 고정한다.

- [ ] **Step 18: 전체 테스트**

Run: `.venv/bin/pytest -W error -q`
Expected: 모두 PASS, 경고 0. 893 + 13(문구 6, 근무표 7) − 1(이행용 테스트 삭제) = **905 passed**

Run: `grep -rnE "LEGACY_DEFS|it_board\(\)" duty/alarms duty/services/alarm_runner.py duty/services/change_notice.py duty/services/calendar.py duty/views/alarms.py`
Expected: `duty/alarms/forms.py` 의 `_shift_board` 두 줄만 나온다. 근무표가 하나도 없을 때와 부서 없는 계정의 개인 규칙 기본값이다(`rule_board` 와 같은 규칙).

- [ ] **Step 19: 커밋**

```bash
git add duty/alarms/messages.py duty/alarms/schedule.py duty/alarms/plan.py duty/services/alarm_runner.py \
  duty/services/change_notice.py duty/services/calendar.py duty/views/alarms.py duty/shifts.py \
  tests/test_alarm_texts_it.py tests/test_alarm_boards.py tests/test_alarm_plan.py tests/test_change_notice.py \
  tests/test_views_alarms.py tests/test_shifts.py
git commit -m "feat: 알림·변경 알림·캘린더를 근무표 정의로(근무표마다 계획, 변경 알림은 그날의 주인 기준), 옛 칸 상수 삭제"
```

#### 커밋 3: 부서 이동 때 개인 알림 발송 기록 정리

- [ ] **Step 20: 테스트를 쓴다**

`tests/test_alarm_boards.py` 맨 위 import 블록(1행 ~ `from duty.services import alarm_runner, alarms, calendar, change_notice`)을 다음으로 바꾼다:

```python
"""근무표가 둘일 때 알림 규칙·정기 알림·변경 알림·캘린더가 서로 영향 없음(1단계)."""
from datetime import date, datetime, time, timedelta

import pytest
from django.contrib import admin as dj_admin
from django.utils import timezone

from duty import accounts
from duty.admin import UserAdmin
from duty.alarms import senders
from duty.alarms.forms import RuleForm
from duty.errors import DutyError
from duty.models import (AlarmDelivery, AlarmRule, AlarmSettings, Board, BoardShift, ChangeLog, Commute, Department,
                         Period, PeriodEvent, TelegramAlarmProfile, User)
from duty.services import alarm_runner, alarms, calendar, change_notice
```

파일 끝에 더한다:

```python


# ---- 부서 이동 ----

def _deliveries(u, it_board):
    personal = AlarmRule.objects.filter(user=u).first()
    report = AlarmRule.objects.create(user=u, kind="report", board=it_board, timing="days", offset=2,
                                      at_minute=9 * 60, telegram=True, shifts=[], depts=[], types=[])
    for r, cell in ((personal, "dawn"), (report, "report")):
        for d in (SUN - timedelta(days=1), D):
            AlarmDelivery.objects.create(rule=r, date=d, cell=cell, channel="telegram", destination="111",
                                         status="sent", content_hash="h")
    return personal, report


def test_department_change_to_other_board_clears_personal_deliveries(env, depts, it_board, ops):
    _, dept = ops
    u = person("가상아이", depts["MEMS"], "111")
    personal, report = _deliveries(u, it_board)
    old, u.department = u.department_id, depts["UI"]
    u.save()
    accounts.on_department_change(u, old)  # 같은 근무표(IT) 안 이동 → 그대로
    assert AlarmDelivery.objects.count() == 4
    old, u.department = u.department_id, dept
    u.save()
    accounts.on_department_change(u, old)
    assert sorted((x.rule_id, x.date) for x in AlarmDelivery.objects.all()) == sorted(
        [(personal.id, SUN - timedelta(days=1)), (report.id, SUN - timedelta(days=1)), (report.id, D)])


def test_admin_user_save_calls_department_change(env, depts, it_board, ops, rf, admin_user):
    _, dept = ops
    u = person("가상아이", depts["MEMS"], "111")
    _deliveries(u, it_board)
    u = User.objects.get(pk=u.pk)
    u.department = dept
    request = rf.post("/")
    request.user = admin_user
    UserAdmin(User, dj_admin.site).save_model(request, u, form=None, change=True)
    assert not AlarmDelivery.objects.filter(rule__kind="personal", date__gte=SUN).exists()
    assert AlarmDelivery.objects.filter(rule__kind="report").count() == 2
```

Run: `.venv/bin/pytest -W error tests/test_alarm_boards.py -q -k department`
Expected: `2 failed`
- `AttributeError: module 'duty.accounts' has no attribute 'on_department_change'`
- admin 테스트: 개인 규칙 발송 기록이 남아 `assert not True`

- [ ] **Step 21: `accounts` 와 관리 화면을 바꾼다**

`duty/accounts.py` 6~7행을 다음으로 바꾼다:

```python
from . import perms
from .models import AlarmDelivery, Department, User
from .services import alarms, calendar
```

파일 끝에 더한다:

```python


def on_department_change(user: User, old_department_id) -> None:
    """부서를 바꿔 근무표가 달라졌으면 개인 규칙의 오늘 이후 발송 기록을 지운다(옛 근무표의 기록이 남으면
    새 근무표에서 그 칸을 못 찾아 취소 알림이 나간다). 보고서 규칙은 근무표가 정해져 있어 그대로 둔다."""
    old = Department.objects.filter(pk=old_department_id).values_list("board_id", flat=True).first()
    new = user.department.board_id if user.department_id else None
    if old != new:
        AlarmDelivery.objects.filter(rule__user=user, rule__kind="personal", date__gte=perms.today()).delete()
```

`duty/admin.py`
- 12행 `from .accounts import issue_account` → `from .accounts import issue_account, on_department_change`
- `UserAdmin.login_id`(130~132행) 바로 아래, `issue_accounts` 앞에 더한다. `UserAdmin` 에는 지금 `save_model` 이 없다(215행의 것은 `AlarmSettingsAdmin`).

```python

    def save_model(self, request, obj, form, change):
        old = User.objects.filter(pk=obj.pk).values_list("department_id", flat=True).first() if change else None
        super().save_model(request, obj, form, change)
        if change:  # 부서를 옮겨 근무표가 바뀌면 개인 알림 발송 기록 정리
            on_department_change(obj, old)
```

Run: `.venv/bin/pytest -W error tests/test_alarm_boards.py tests/test_admin_users.py -q`
Expected: PASS

- [ ] **Step 22: 전체 테스트·마이그레이션·화면 확인**

Run: `.venv/bin/pytest -W error -q`
Expected: 모두 PASS, 경고 0. **907 passed**(905 + 2)

Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations --check --dry-run`
Expected: `No changes detected`

화면 확인(Task 3 Step 17 의 serve.py 방식. `config.test_settings` 를 쓰고 `DUTY_DEBUG=1` 은 쓰지 않는다).
1. 이 작업 전 사본과 이 작업 뒤 사본에서 같은 준비 데이터로 다음 화면의 HTML 을 받는다. 준비 데이터는 MEMS 사용자, 기본 규칙 2개, 보고서 규칙 1개(board=IT, 전부 선택)다.
   - `/alarms/`
   - `/alarms/rules/new/`
   - 보고서 규칙 수정 화면, 개인 규칙 수정 화면
2. csrf 토큰과 푸시 공개키(실행마다 새로 만듦)만 가리고 diff 한다. 차이가 없어야 한다.
3. 같은 화면을 브라우저 PC 1400px·모바일 390px(다크 모드 포함)로 연다. 다음을 눈으로 본다.
   - 근무표 칸이 없다.
   - 보고서 규칙 수정 화면에서 스케줄 5개·유형 2개·부서 4개가 모두 체크되어 있다.

검증할 때는 1~2를 pytest 임시 파일(client 로 네 화면을 받아 저장)로 Task 7 사본과 이 사본에서 돌렸다. 네 파일 모두 csrf·푸시 키 줄 말고는 같았다.

- [ ] **Step 23: 커밋**

```bash
git add duty/accounts.py duty/admin.py tests/test_alarm_boards.py
git commit -m "feat: 부서를 옮겨 근무표가 바뀌면 개인 알림 발송 기록 정리(관리 화면 사용자 저장)"
```

---

**판단이 필요한 곳 (Codex 리뷰 때 함께 보기):**
- **허용 변환을 넓혀 쓴 곳**
  - Step 4: 보고서 규칙을 직접 만드는 기존 준비 코드에 `board=IT` 를 더했다. 고친 곳은 `test_run_alarms.report_rule`, `test_views_alarms.rule()`·789행, `test_alarm_models.test_report_allows_filters` 다.
    - (a) 를 "회차·부서" 밖으로 넓혀 쓴 것이다. 새 CheckConstraint 때문에 준비 단계에서 바로 깨지기 때문이다.
  - Step 5: `test_normalize`·`test_normalize_rejects_unknown` 에 `it_board` 인자를 더했다. (c) 를 normalize 에까지 넓혀 쓴 것이다.
  - Step 13: `test_alarm_plan` 의 `CELLS`→`KEYS` 는 이름만 바꾼 것이고 값은 같다.
  - Step 17: `test_shifts` 의 `CELLS`→`KEYS` 도 이름만 바꾼 것이다. Task 3 이 더한 `test_legacy_defs_equal_it_defs` 는 지웠다(main 의 기존 테스트가 아님).
- **`board` 대신 `board_id`:** `RULE_FIELDS` 에 설계의 `board` 대신 속성 `board_id` 를 넣었다. 스냅숏을 뜨고 비교할 때 규칙마다 FK 쿼리를 하지 않으려는 것이다. 문구 hash 에는 영향이 없다.
- **`schedule_keys` 를 새로 만들지 않음:** normalize 의 스케줄 키 순서는 Task 3 의 `prefs.choices(defs)` 키를 그대로 쓴다. IT 는 dawn·normal·dinner·night·slots 로 옛 `SHIFT_KEYS` 와 같다(`test_normalize` 그대로 통과).
- **설계가 요구하는 동작 변화 두 가지**(6.1·8.1, 새 테스트로 고정)
  - `_live` 가 행 유무 대신 그날의 주인으로 판단한다. 그래서 행이 다 빠진 날의 기록도 보내고, 더 새 회차가 덮은 날의 옛 기록은 보내지 않는다.
  - 근무조 중 `default_alarm` 이 켜진 것이 없는 근무표에서는 `create_defaults` 가 규칙을 만들지 않는다.
- **근무표가 둘 이상일 때 규칙 폼(`ponytail:`)**
  - 스케줄 선택지는 POST(편집 땐 규칙)의 종류·근무표로 정한다: 보고서 = 고른 근무표, 개인 = 주인의 근무표(뷰가 `user=` 를 넘김). 그래서 운영팀 보고서 규칙에 IT 전용 키(night·slots)를 보내면 폼 오류로 막히고 `normalize` DutyError 까지 가지 않는다(`test_rule_form_two_boards`).
  - 부서 선택지는 모든 근무표의 부서다. 고른 근무표 밖의 부서는 `normalize` 가 막는다.
  - 남는 한계: 빈 폼은 처음 그릴 때 기준이라 화면에서 종류·근무표를 바꿔도 체크박스가 다시 그려지지 않는다. 2단계 근무표 고르기 화면과 함께 고친다. 1단계는 근무표가 하나라 화면 영향이 없다.
- **규칙 목록·캘린더 선택지:** `/alarms/` 의 조건 글자는 규칙마다 그 근무표 이름이다(개인 = 내 근무표, 보고서 = 규칙의 근무표). 캘린더 스케줄 선택지는 내 근무표다. 부서 없는 계정은 IT 다(`rule_board`).
- **행 없는 날 거르기:** `published_days` 가 행 없는 날도 내므로 정기 알림(`collect`)과 캘린더(`_events`) 둘 다 행 있는 날만 남긴다(Task 5 와 같다). 그래서 IT 보고서와 캘린더 DTSTAMP·ETag 는 그대로다.
- **꺼진 정의:** `Def` 에 `active` 가 없다. 그래서 꺼진 정의도 보고서 줄에 "이름 -"로 나올 수 있다. 1단계 IT 는 모두 켜져 있어 영향이 없다.
- **옛 상수 삭제:** 이 작업 뒤 앱 코드는 옛 상수를 하나도 쓰지 않아서 `shifts.py` 에서 지웠다. `DEVELOPER`·`STAFF` 는 사람 유형이라 남는다. `slot_index`·`is_slot_cell` 은 models·changes 등이 쓴다.
- **문서:** ARCHITECTURE "알림"·"캘린더 구독"·shifts 설명은 고치지 않았다(Task 10).

**검증:** Task 1~7 이 적용된 /tmp/t7v2(874 passed)를 /tmp/t8v2 로 복사해 모든 단계를 그대로 넣어 돌렸다.
- 실패 확인: 2 → 9 → 6 → 7 → 2 failed. 계획에 적은 메시지 그대로 나왔다.
- 통과: 883 → 895 → **897 passed**, 경고 0. `makemigrations --check` 결과는 No changes detected.
- Step 11 의 hash 4개(`in:b67c…`, `in:c469…`, `out:3b1b…`, `report:1b8a…`)와 보고서 본문은 Task 7 사본의 옛 시그니처 `plan` 으로 다시 계산해 일치를 확인했다.


---

### Task 9: 관리 화면(근무표·그룹·사용자)

슈퍼유저 전용 Django 관리 화면만 바뀐다(설계 7절 예외). 사용자 화면 글자·알림 문구·링크·칸 순서는 그대로이고, 기존 테스트 단언도 그대로다.
- 근무표(Board) 화면은 **보기만** 한다. 추가·수정·삭제 권한은 모두 False 이고, 보기는 슈퍼유저다(관리 화면 출입문과 같다). `boards.it_board()` 가 `code="it"` 로 찾으므로 code 를 바꾸면 근무표 화면·알림이 500 이 난다. 근무표 추가·편집은 3단계다(설계 11절).
- 근무 정의(BoardShift)와 그룹 관리자(GroupKeeper)는 인라인으로 **보기만** 한다. 설계 4.3 검증(`BoardShiftForm`·`BoardShiftFormSet`), 근무 정의 편집, 그룹 관리자 지정·그룹 화면은 3단계로 넘긴다(설계 11절 그대로).
- 관리 그룹은 `Board.save`(Task 1)가 `"{name} 근무표 관리"`로 만든다. 그래서 `BoardAdmin.save_model`은 두지 않는다(지적 13).
- 그룹(auth.Group) 관리 화면은 permissions 칸만 숨긴다(1단계는 Django 권한을 쓰지 않는다). 그룹 멤버(근무표 관리자 지정)는 사용자 화면의 "그룹" 칸으로 한다. 새 설치 때 슈퍼유저가 자신을 "IT 근무표 관리"에 넣는 것도 이 칸이다.
- 사용자 화면은 `user_permissions`를 숨기고, 목록·필터의 `is_staff`를 `groups`로 바꾼다.

커밋은 하나다. 줄 번호는 Task 8까지 적용한 상태 기준이다.

**Files:**
- Modify: `duty/admin.py`
  - import: `from .models import …` 줄
  - `UserAdmin.fieldsets`~`list_filter`(111~119행), `get_form`(124행) 앞
  - `class AlarmSettingsForm`(155행) 바로 앞에 근무표·그룹 관리 화면
- Modify(Test): `tests/test_admin_users.py`(끝에 2개)
- Create(Test): `tests/test_admin_boards.py`(5개)
- 바꾸지 않음: 맨 끝 `admin.site.has_permission = … is_staff and … is_superuser` 줄. 이 줄은 관리자 판정이 아니라 관리 화면 출입문이고, `test_admin_site_needs_staff_too`가 고정한다. 모델·마이그레이션·문서도 바꾸지 않는다(문서는 Task 10, 지적 17). 다음 마이그레이션 번호는 그대로 **0018**이다.

**Interfaces:**
- Consumes:
  - Task 1: `Board`(admin_group은 `editable=False`, `save()`가 그룹 생성), `BoardShift`(related_name `"shifts"`, key choices는 중립 이름 `_key_label`: "근무조 1"…, "관제 1"…), `GroupKeeper`(related_name `"keepers"`·`"kept_groups"`)
  - Task 4: `from django.contrib.auth.models import Group`·`FilteredSelectMultiple` import, `DepartmentForm`/`DepartmentAdmin`(그대로 둔다)
  - Task 8: `UserAdmin.save_model`(on_department_change, 그대로 둔다)
  - conftest: `it_board`, `admin_user`(is_staff, IT 관리 그룹), `make_member`
- Produces (`duty/admin.py`):
  - `_ViewOnly`(mixin): add·change·delete 권한 False, 보기는 슈퍼유저
  - `BoardShiftInline(_ViewOnly, TabularInline)`(extra 0, prefix `"shifts"`, `active` 칸은 보이지 않음)
  - `BoardAdmin(_ViewOnly, ModelAdmin)`(보기만, inlines BoardShiftInline, save_model 없음)
  - `GroupKeeperInline(_ViewOnly, TabularInline)`(prefix `"keepers"`)
  - `GroupAdmin`(기본 Group 등록을 unregister하고 다시 등록, `fields = ["name"]` 로 permissions 만 숨김, 멤버 이름 목록 칸)
  - `UserAdmin.group_names(obj)`, `UserAdmin.get_queryset`(prefetch groups)
- 3단계로 넘김(1단계 계획에서 지움): `KEY_LABELS`·`BoardShiftForm`·`BoardShiftFormSet`(설계 4.3 검증), `BoardForm`·`clean_name`(새 근무표 이름의 그룹 충돌), 그룹 화면의 멤버 편집(`GroupForm`)·그룹 관리자 편집, 그 검증·근무표 추가 테스트.

- [ ] **Step 1: 사용자·근무표·그룹 관리 화면 테스트를 쓴다(실패 확인용)**

`tests/test_admin_users.py` 끝에 더한다(파일의 `su_client` fixture를 쓴다).

```python


def test_changelist_shows_groups_not_staff(su_client, it_board):
    body = su_client.get(reverse("admin:duty_user_changelist")).content.decode()
    assert it_board.admin_group.name in body  # 목록의 그룹 칸·그룹 필터
    assert "groups__id__exact" in body and "is_staff__exact" not in body


def test_change_page_hides_user_permissions(su_client, make_member):
    m = make_member("가")
    body = su_client.get(reverse("admin:duty_user_change", args=[m.pk])).content.decode()
    assert 'name="groups"' in body and 'name="user_permissions"' not in body
```

`tests/test_admin_boards.py`를 새로 만든다. 근무 정의 편집·4.3 검증 테스트는 3단계에서 더한다.

```python
"""관리 화면(슈퍼유저 전용): 근무표·근무 정의·그룹 관리자는 1단계에서 보기만. 그룹 화면은 권한 칸만 숨긴다."""
import pytest
from django.urls import reverse

from duty.models import GroupKeeper


@pytest.fixture
def su(admin_user):
    admin_user.is_superuser = True
    admin_user.save()
    return admin_user


@pytest.fixture
def su_client(client, su):
    client.force_login(su)
    return client


def test_board_add_not_allowed(su_client, it_board):
    assert su_client.get(reverse("admin:duty_board_add")).status_code == 403  # 근무표 추가는 3단계
    assert reverse("admin:duty_board_add") not in su_client.get(reverse("admin:duty_board_changelist")).content.decode()


def test_board_fields_read_only(su_client, it_board):
    body = su_client.get(reverse("admin:duty_board_change", args=[it_board.pk])).content.decode()
    assert it_board.name in body and it_board.admin_group.name in body  # 이름·관리 그룹은 글자로 보인다
    assert 'name="name"' not in body and 'name="code"' not in body and 'name="input_mode"' not in body


def test_shift_definitions_read_only(su_client, it_board):
    body = su_client.get(reverse("admin:duty_board_change", args=[it_board.pk])).content.decode()
    assert "석식교대" in body and "근무조 1" in body and "관제 10" in body  # 키는 중립 이름으로 보인다
    assert 'name="shifts-0-name"' not in body and 'name="shifts-0-DELETE"' not in body
    assert 'name="shifts-0-active"' not in body


def test_board_cannot_be_changed(su_client, it_board):
    name, url = it_board.name, reverse("admin:duty_board_change", args=[it_board.pk])
    r = su_client.post(url, {"name": "바뀐 이름", "shifts-TOTAL_FORMS": "0", "shifts-INITIAL_FORMS": "0"})
    assert r.status_code == 403  # 수정 권한 없음(근무표 편집은 3단계)
    assert su_client.post(reverse("admin:duty_board_delete", args=[it_board.pk]), {"post": "yes"}).status_code == 403
    it_board.refresh_from_db()
    assert it_board.name == name


def test_group_page_hides_permissions_and_keepers_read_only(su_client, it_board, admin_user):
    GroupKeeper.objects.create(group=it_board.admin_group, user=admin_user)
    html = su_client.get(reverse("admin:auth_group_change", args=[it_board.admin_group.pk])).content.decode()
    assert 'name="name"' in html and 'name="permissions"' not in html
    assert 'name="members"' not in html  # 멤버는 사용자 화면의 '그룹' 칸에서 넣는다
    assert 'name="keepers-0-user"' not in html and admin_user.name in html  # 그룹 관리자는 보기만(편집은 3단계)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_admin_users.py -q`
Expected: `2 failed, 9 passed`
- FAIL `test_changelist_shows_groups_not_staff`: 필터가 아직 `is_staff`라서 `is_staff__exact`가 화면에 있다.
- FAIL `test_change_page_hides_user_permissions`: 아직 `user_permissions` 칸이 있다.

Run: `.venv/bin/pytest -W error tests/test_admin_boards.py -q`
Expected: `5 failed`
- 근무표 테스트 4개: `NoReverseMatch: Reverse for 'duty_board_add'`(또는 `'duty_board_change'`) — 아직 근무표 관리 화면이 없다.
- `test_group_page_hides_permissions_and_keepers_read_only`: 기본 그룹 화면이라 `name="permissions"` 가 있어 AssertionError.

- [ ] **Step 3: 사용자·근무표·그룹 관리 화면을 구현한다**

`duty/admin.py`를 네 군데 고친다.

(1) import. `from django.contrib.auth.models import Group` 과 `FilteredSelectMultiple` 은 Task 4 가 이미 넣었다(그대로 쓴다). `from .services import alarm_settings, boards` 줄과 `from .shifts import shift_defs` 줄(Task 3)도 그대로 둔다. `from .models import …` 줄만 아래로 바꾼다.

```python
from .models import AlarmSettings, Board, BoardShift, Department, GroupKeeper, User
```

(2) `UserAdmin`의 116~119행(`*DjangoUserAdmin.fieldsets[2:],  # 기본 "개인정보"…`부터 `list_filter = [...]`까지)을 아래로 바꾼다. 111~115행 앞부분과 120행 `search_fields` 이하는 그대로 둔다.

```python
        # 기본 "개인정보"(이름·성·이메일)는 근무표 "이름"과 헷갈려 숨긴다(칸은 유지).
        # Django 사용자 권한(user_permissions)은 쓰지 않는다: 근무표 관리자·입력 담당은 그룹으로 정한다
        (DjangoUserAdmin.fieldsets[2][0], {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
        *DjangoUserAdmin.fieldsets[3:],
    )
    list_display = ["login_id", "name", "department", "part", "type", "is_active", "group_names"]
    list_filter = ["department", "type", "is_active", "groups"]
```

(3) 124행 `def get_form` 바로 위에 더한다. `get_form`·`login_id`·`save_model`·`issue_accounts`는 그대로 둔다.

```python
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("groups")

    @admin.display(description="그룹")
    def group_names(self, obj):
        return ", ".join(g.name for g in obj.groups.all())

```

(4) 155행 `class AlarmSettingsForm(forms.ModelForm):` 바로 위(`UserAdmin` 다음)에 더한다.

```python
class _ViewOnly:
    """1단계 보기 전용(추가·수정·삭제는 3단계, 설계 11절). 보기는 슈퍼유저(관리 화면 출입문과 같다)."""

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class BoardShiftInline(_ViewOnly, admin.TabularInline):
    """근무 정의는 보기만 한다. 편집과 설계 4.3 검증은 3단계."""
    model = BoardShift
    fields = ["key", "name", "start", "end", "eligible_shifts", "eligible_types", "default_alarm"]  # active 는 3단계
    extra = 0


@admin.register(Board)
class BoardAdmin(_ViewOnly, admin.ModelAdmin):
    """1단계는 보기만. 근무표 추가·편집·근무 정의 편집은 3단계(boards.it_board() 가 code 로 찾는다).
    관리 그룹은 Board.save 가 만들고, 멤버는 사용자 화면의 '그룹' 칸에서 넣는다."""
    fields = ["code", "name", "input_mode", "admin_group"]
    list_display = ["name", "code", "input_mode", "admin_group"]
    inlines = [BoardShiftInline]


class GroupKeeperInline(_ViewOnly, admin.TabularInline):
    """그룹 관리자는 기록만 보인다. 지정·편집과 그룹 화면은 3단계."""
    model = GroupKeeper
    extra = 0


admin.site.unregister(Group)  # django.contrib.auth.admin 이 등록한 기본 그룹 화면(권한 칸)을 바꾼다


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    """permissions 칸만 숨긴다(1단계는 Django 권한을 쓰지 않는다). 멤버는 사용자 화면의 '그룹' 칸에서 넣는다."""
    fields = ["name"]
    list_display = ["name", "member_names"]
    search_fields = ["name"]
    inlines = [GroupKeeperInline]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("user_set")

    @admin.display(description="멤버")
    def member_names(self, obj):
        return ", ".join(u.name for u in obj.user_set.all()) or "(없음)"


```

키는 읽기 전용 칸이라 `BoardShift.key` 의 choices(Task 1 `_key_label`, 중립 이름 "근무조 1"·"관제 1")로 보인다. 수정 권한이 없으면 Django 는 변경 화면을 보기 전용으로 그리고([저장] 버튼 없음), POST 는 403 이다(`test_board_cannot_be_changed`). 그룹 화면은 이름만 고칠 수 있고, 그룹 관리자 인라인은 보기 전용이다.

(5) 그대로 둔다: 맨 끝 `admin.site.has_permission` 줄.

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_admin_users.py tests/test_admin_boards.py tests/test_admin_department.py tests/test_security_stage1.py tests/test_auth.py tests/test_alarm_settings.py -q`
Expected: `93 passed`(검증 때 104 passed 에서 3단계로 넘긴 근무표 테스트 16개를 빼고 새 5개를 더한 값)
- 기존 `test_changelist`의 `"관리자" not in body`도 통과한다. 그룹 이름이 "IT 근무표 관리"·"<부서> 출근표 입력"이라 "관리자"라는 글자가 없다.
- `test_admin_site_superuser_only`·`test_admin_site_needs_staff_too`(출입문)도 그대로 통과한다.

Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py check && DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations --check --dry-run`
Expected: `System check identified no issues (1 silenced).`, `No changes detected`

- [ ] **Step 5: 남은 is_staff 판정과 전체 테스트를 확인한다**

```bash
grep -rnE "\.is_staff\b" duty --include=*.py | grep -v migrations
.venv/bin/pytest -W error -q
```

Expected:
- grep 결과는 `duty/admin.py`의 `admin.site.has_permission = lambda request: … request.user.is_staff …` 한 줄뿐이다.
- pytest는 **914 passed**(Task 8 끝 907 + 새 7: 사용자 2·근무표 5), 경고 0개.

브라우저로 확인한다(CLAUDE.md, PC 1400px·모바일 390px). Task 3 Step 17의 serve.py(`config.test_settings`, 임시 DATA_DIR, migrate·seed·runserver를 한 프로세스에서)로 띄우고 seed의 슈퍼유저 admin으로 /admin/ 에 들어간다.
- 사용자 목록: 그룹 칸·그룹 필터가 있고 스태프 칸·필터는 없다. 변경 화면에 "사용자 권한" 칸이 없다.
- 근무표 > IT 당번표
  - 근무 정의 14줄이 읽기 전용 글자로 나오고 키는 "근무조 1…"·"관제 1…"다. 입력 칸·삭제 칸·줄 추가 링크가 없다.
  - 이름·code·입력 방식·관리 그룹 "IT 근무표 관리"가 모두 읽기 전용 글자이고 [저장]·[삭제] 버튼이 없다.
- 근무표 목록에 [근무표 추가] 버튼이 없다.
- 그룹 > IT 근무표 관리: 이름 칸과 보기 전용 그룹 관리자 인라인만 있고 권한·멤버 칸이 없다.
- 사용자 > (아무 사람) > "그룹" 칸에서 "IT 근무표 관리"를 넣고 빼어 관리자를 지정할 수 있다.
- 사용자 화면(/, /periods/)은 바뀌지 않았다(관리 화면만 고쳤다).

- [ ] **Step 6: 커밋**

```bash
git add duty/admin.py tests/test_admin_users.py tests/test_admin_boards.py
git commit -m "feat: 관리 화면에 근무표·근무 정의 보기, 그룹 화면은 권한 칸 숨김, 사용자 목록은 스태프 대신 그룹"
```

---

**이 작업에서 빼거나 바꾼 것**
- **옛 Task 8에서 고친 것**
  - 지적 13: `BoardAdmin.save_model`을 지웠다(`Board.save`가 이미 그룹을 만든다).
  - 옛 `NEUTRAL_KEY_NAMES` 는 지웠다. 키는 모델 choices(중립 이름)로 읽기 전용 표시된다.
  - `active`(사용) 칸은 보이지 않는다(일관성 지적). 코드는 Task 3 부터 `boards.active_defs` 로 "끄면 새 입력에서만 빠진다"(설계 4.3)를 따르지만, 1단계에는 꺼진 정의가 없고 끄는 화면은 근무 정의 편집과 함께 3단계에서 연다.
- **3단계로 넘긴 것(리뷰 반영):** 앞 판의 계획은 근무표 추가·code·input_mode 변경과 근무 정의 편집(`KEY_LABELS`·`BoardShiftForm`·`BoardShiftFormSet`·`BoardForm.clean_name`, 테스트 16개)을 1단계에 넣었다. 그런데 `boards.it_board()` 는 `Board.objects.get(code="it")` 이라, 관리 화면에서 code 를 한 번 잘못 고치면 근무표 화면·알림 기본값(`_board`·`rule_board`·`DepartmentForm`·prefs)이 `DoesNotExist` 로 500 이 난다. 근무표 추가도 Task 4 의 "새 부서 출근조 선택지는 3단계에서 고친다"와 어긋난다. 그래서 1단계 근무표 화면은 보기만 두고(이름 편집도 3단계), 나머지는 검증·테스트와 함께 3단계에서 넣는다. 그룹 화면의 멤버 편집(`GroupForm`)·그룹 관리자 편집도 3단계다(설계 11절). 관리자 지정은 사용자 화면의 "그룹" 칸으로 충분하다. 저장된 키 `disabled`·시각 칸 오류·`"Constraint" not in` 같은 앞 판의 결정은 3단계 계획에서 다시 쓴다.
  - 옛 Step 20(seed.py)은 Task 5로 옮겨 끝났다(지적 15). 옛 Step 21(문서)은 Task 10 몫이다(지적 17).
- **GroupKeeper 인라인 위치:** 설계 7절은 Board 화면에 둔다고 했지만 `GroupKeeper`에는 Board로 가는 FK가 없다. 그래서 그룹 화면에 보기 전용 인라인으로 둔다. Board 화면은 관리 그룹을 읽기 전용으로 보여 준다.
- **단계 차이:** 설계 11절대로 Board·BoardShift·GroupKeeper 편집과 검증은 모두 3단계다. 1단계 관리 화면은 근무표·근무 정의·그룹 관리자를 보기만 하고, 그룹 화면은 Django 권한 칸만 숨긴다. 슈퍼유저 관리 화면에만 생기므로 사용자 화면은 바뀌지 않는다.
- **그 밖:** 근무표 삭제도 막는다(`has_delete_permission` False, `test_board_cannot_be_changed`).

<!-- 검증 메모: Task 8까지 적용한 사본(/tmp/t8v2, 897 passed)을 /tmp/t9v2로 복사해 모든 단계를 그대로 넣어 돌렸다. Step 2는 2 failed + ImportError 수집 오류, Step 4는 104 passed, Step 5는 915 passed(경고 0)였고 check와 makemigrations --check도 깨끗했다. IT 근무표 변경 화면에 기존 정의 14행을 그대로 POST하면 302로 저장되는 것도 임시 테스트로 확인했다(계획에는 넣지 않음). /tmp/t9v2는 커밋 c9 상태로 남겨 두었다. 브라우저 확인은 하지 않았다. 관리 화면 GET 렌더는 테스트가 확인한다. active 칸을 뺀 수정(일관성 지적 반영)은 사본에 다시 돌려 보지 않았다. 테스트 수는 16 그대로라 915·104 기대는 바뀌지 않는다. 그 뒤 리뷰 반영으로 근무표 화면을 이름만 고치는 형태로 줄였고(근무표 테스트 16 → 5), 이 형태는 사본에서 다시 돌려 보지 않았다. 그 뒤 근무표 화면을 완전히 보기 전용으로, 그룹 화면을 권한 칸만 숨기는 형태로 다시 줄였다(테스트 수 5 그대로). 그래서 위 기대 수(93·914)는 계산값이다. -->


---

### Task 10: 문서·남은 상수 확인·화면 확인·PR

1단계의 마지막 작업이다. 코드는 Task 1~9 에서 끝났다. 여기서는 다섯 가지를 한다.
- 문서를 코드에 맞춘다. 대상은 ARCHITECTURE·OPERATIONS·OVERVIEW·DEVELOPMENT·PRINCIPLES 와 README 역할 표다. 앞 작업들은 문서를 하나도 고치지 않았으므로(지적 17) 문서 수정은 모두 여기서 한다.
- 남은 옛 상수와 옛 권한이 없는지 grep 으로 확인한다.
- 가짜 데이터 DB 로 화면이 `main` 과 같은지 HTML·1400px·390px 화면으로 확인한다.
- Codex 최종 리뷰를 받는다.
- PR 을 연다.

가짜 데이터(`tools/help_videos/seed.py`, `tests/test_help_seed.py`)는 Task 5 가 이미 옮겼다(지적 15). 이 작업은 seed 를 고치지 않는다.

실명 DB(`data/`, `*.sqlite3`), `.superpowers/`, `.env` 는 어느 단계에서도 열지 않는다. manage.py·Django 를 띄우는 명령에는 모두 `DJANGO_SETTINGS_MODULE=config.test_settings` 를 붙이고, `DUTY_DEBUG=1` 은 쓰지 않는다(지적 19). test_settings 는 `.env` 를 읽지 않고, 프로세스마다 새 임시 `DATA_DIR` 을 쓰며, 끝나면 지운다. 그래서 migrate·가짜 데이터·서버를 한 프로세스에서 돌린다(Task 3 Step 17 의 방식).

**Files:**
- Modify: `docs/ARCHITECTURE.md`
  - 24·29·30·33행
  - 40–46행(데이터 그림), 46행 뒤에 한 줄
  - 54–60행("근무조와 칸" 절 전체)
  - 62–69행("역할" 절 전체)
  - 79·82·83·86·87·88·89·95·96·103·104·120행
- Modify: `docs/OPERATIONS.md`: 62·297행, 301–302행, 323행 뒤에 한 항목
- Modify: `docs/OVERVIEW.md`: 28–29행
- Modify: `README.md`: 17–18행
- Modify: `docs/DEVELOPMENT.md`: 13행, 63행 뒤에 한 항목
- Modify: `docs/PRINCIPLES.md`: 결정 기록 표 끝(지금 99행) 뒤에 여섯 줄
- 코드와 테스트는 바꾸지 않는다. Step 1 의 grep 이 예상 밖의 줄을 내면 앞 작업이 덜 된 것이다. 그때는 멈추고 보고한다.
- 저장소에 넣지 않는 확인용 파일: `$W/serve.py`, `$W/shot.mjs`. `W=$(mktemp -d)` 아래에 두고, 끝나면 지운다.

줄 번호는 `main` 기준이다. 앞 작업들이 문서를 고치지 않았으므로 지금 브랜치에서도 같다. 아래 "지금:" 문장과 한 글자라도 다르면, 그 줄 전체를 "바꾼 뒤:" 로 바꾼다(앞 문장과 상관없이).

**Interfaces:**
- Consumes(문서 문장의 근거, Task 1~9 가 만든 것):
  - 모델
    - `Board(code, name, input_mode, admin_group)`: `save()` 가 `"{name} 근무표 관리"` 그룹을 만든다.
    - `BoardShift(board, key∈KEYS, name, start, end, eligible_shifts, eligible_types, default_alarm, active)`
    - `GroupKeeper(group, user)`
    - `Department.board`(NOT NULL), `.order`, `.input_group`(collect 근무표면 `"{name} 출근표 입력"` 자동 생성), `managers` property
    - `Period.board`(NOT NULL), `AlarmRule.board`, `DutyAssignment(period, date, cell=slotN, member)`
  - `duty.shifts`
    - `SHIFT_KEYS`, `SLOT_KEYS`, `KEYS`
    - `SLOT_GROUP="slots"`, `SLOT_GROUP_NAME="장중관제"`, `SLOT_GROUP_SHORT="관제"`
    - `by_key`·`ordered`·`shift_defs`·`slot_defs`·`display_order`·`cell_label`·`cell_start`·`cell_end`·`cells_of`(모두 첫 인자 defs)
  - `duty.services.boards`: `it_board()`, `defs(board)`, `board_of(user)`, `owner(board, d)`, `owners(board, start, end)`
  - `duty.perms`: `today`, `admin_boards`, `is_board_admin`, `is_admin`, `managed_departments`, `can_input_department`, `assert_can_edit(user, board, d)`, `can_edit`
  - `services.alarms.rule_board(user, kind, board_id)`, `RULE_FIELDS` 의 `"board_id"`
  - `alarm_runner.collect`: 근무표마다 plan
  - `accounts.on_department_change(user, old_department_id)`
  - `duty/admin.py`: `BoardAdmin`(보기만, +보기만 하는 `BoardShiftInline`), `GroupAdmin`(permissions 칸만 숨김, +보기만 하는 `GroupKeeperInline`), `DepartmentForm`(board·order·입력 담당자), `UserAdmin`(그룹 칸). `admin.site.has_permission` 이 `.is_staff` 를 쓰는 유일한 줄이다.
  - 마이그레이션 0010~0017
  - 전체 테스트 **914 passed**(Task 9 끝)
- Produces:
  - 문서 갱신 커밋 하나(`docs:`)
  - 1단계 PR(제목 `feat: 근무표 일반화 1단계 …`)
  - 마이그레이션은 만들지 않는다. 다음 번호는 그대로 **0018**(2단계 첫 마이그레이션)이다.

---

- [ ] **Step 1: 옛 상수·옛 권한 사용이 남지 않았는지 grep 으로 확인**

```bash
cd /home/dustbox/develop/nxt/duty_generator
grep -rnwE "COMMUTE_SHIFTS|CONTROL_SLOTS|SHIFT_TIMES|DEPT_ORDER|ControlDuty|assert_can_edit_date|LEGACY_DEFS|slot_cell|CELLS" duty config tools --include=*.py --include=*.html --include=*.mjs | grep -v "/migrations/"
grep -rnwE "COMMUTE_SHIFTS|CONTROL_SLOTS|SHIFT_TIMES|DEPT_ORDER|ControlDuty|assert_can_edit_date|LEGACY_DEFS|slot_cell|CELLS" tests --include=*.py
grep -rnE "\.is_staff\b" duty --include=*.py --include=*.html | grep -v "/migrations/"
grep -rnE "\.managers\b|managers\.(add|set|remove)|user\.managed_departments|\.managed_departments\.all" duty tools --include=*.py --include=*.html | grep -v "/migrations/"
DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations --check --dry-run
```

기대 결과(Task 9 까지 적용한 사본에서 확인한 그대로):
1. 첫 grep(앱 코드): `duty/services/calendar.py` 의 주석 한 줄(`# KEYS 순(옛 CELLS 와 같다). …`)만 나온다.
2. 두 번째 grep(tests): 주석·문서 문자열과 마이그레이션 테스트만 나온다.
   - `tests/it_defs.py` 1행 docstring, 30행 주석
   - `tests/conftest.py` 의 `depts` 주석(`DEPT_ORDER`)
   - `tests/test_boards_generate.py` 의 주석(`옛 CONTROL_SLOTS`)
   - `tests/test_migration_duty_assignment.py`: 옛 모델을 `apps.get_model("duty", "ControlDuty")` 로 읽는 줄들. 마이그레이션 테스트라 맞다.
3. 세 번째 grep: `duty/admin.py` 의 `admin.site.has_permission = lambda request: request.user.is_active and request.user.is_staff and request.user.is_superuser` **한 줄만** 나온다(지적 16). 사용자 편집 화면 fieldsets 의 `"is_staff"` 문자열은 속성 접근이 아니라서 이 패턴에 걸리지 않는다. `duty/perms.py`·`duty/context.py` 에 나오면 Task 4 가 덜 된 것이다.
4. 네 번째 grep: `duty/admin.py` 의 `DepartmentForm.__init__`(`self.instance.managers.all()`)과 `DepartmentAdmin.manager_names`(`obj.managers.all()`) 두 줄만 나온다. 둘 다 입력 그룹을 감싼 호환 property 를 읽는다. `tools/`·`duty/perms.py` 에는 나오지 않는다.
5. `makemigrations --check`: `No changes detected`.

위와 다른 줄이 하나라도 나오면, 고치지 말고 멈춘다. 파일과 줄을 보고한다(앞 작업 범위다). 이 단계는 커밋하지 않는다.

- [ ] **Step 2: 문서에 옛 이름이 남아 있는 것을 확인(고치기 전 "실패")**

이 작업은 문서만 바꾸므로 pytest 테스트 대신 이 grep 을 실패 확인으로 쓴다.

```bash
grep -nE "ControlDuty|is_staff|assert_can_edit_date|Department\.managers|관리자\(스태프\)|어드민 여부|근무조·관제 칸 상수|칸\(cell\) 키 14개" docs/ARCHITECTURE.md docs/OVERVIEW.md docs/OPERATIONS.md README.md
```

기대 결과: 아래 9줄이 나온다.
- `docs/ARCHITECTURE.md`: 24·29·43·56·67·68·95행
- `docs/OVERVIEW.md`: 28행
- `README.md`: 17행

(OPERATIONS 의 "스태프 권한" 문장은 뜻을 바꿔 남기므로 이 패턴에 넣지 않았다. 이 문장은 Step 3b 에서 고친다.)

- [ ] **Step 3: 문서 고치기**

문장마다 그 내용을 맡은 함수를 열어 코드와 같은지 확인한다. 함수는 각 항목 괄호 안에 적었다. 다르면 코드를 기준으로 문장을 고친다(ARCHITECTURE 3행의 규칙). 설계 문서 `docs/superpowers/specs/2026-11-15-boards-design.md` 는 지우지 않는다. 4단계 끝에 합치고 지운다.

**3a. `docs/ARCHITECTURE.md`**

코드 지도:
- 24행(`duty/shifts.py`)
  - 지금: `| `duty/shifts.py` | 근무조·관제 칸 상수, 날짜 계산 | 없음 |`
  - 바꾼 뒤: `| `duty/shifts.py` | 칸 키 목록(`KEYS`)과 키의 성격, 근무 정의 목록(defs)을 받는 헬퍼, 날짜 계산 | 없음 |`
- 29행(`perms.py`)
  - 지금: `| `duty/perms.py` | 오늘 날짜, 어드민 여부, 부서 담당, 지난 날짜 수정 검사 | |`
  - 바꾼 뒤: `| `duty/perms.py` | 오늘 날짜, 근무표 관리자·출근표 입력 담당(그룹), 근무 변경·지난 날짜 권한 | |`
- 30행(`services/boards.py`)
  - 지금: `| `duty/services/` | **DB를 바꾸는 규칙은 전부 여기**. 뷰·관리 명령은 서비스만 부른다 | O |`
  - 바꾼 뒤: `| `duty/services/` | **DB를 바꾸는 규칙은 전부 여기**. 뷰·관리 명령은 서비스만 부른다. 근무표·근무 정의 읽기와 그날의 주인은 `boards.py` | O |`
- 33행(`admin.py`)
  - 지금: `| `duty/admin.py` | Django 관리 화면(사용자·부서·계정 발급·알림 설정) | |`
  - 바꾼 뒤: `| `duty/admin.py` | Django 관리 화면(사용자·부서·근무표와 근무 정의 보기·그룹·계정 발급·알림 설정) | |`

데이터 그림: 41–45행(코드 블록 안 다섯 줄)을 아래 일곱 줄로 바꾼다(`models.py`).

```
Board(근무표) ─< BoardShift(근무 정의: 키·이름·시각·자격)
      ─< Department ─< User(멤버 겸 로그인 계정)
      ─< Period ─< Commute(날짜·멤버·출근조)         Period ─< PeriodEvent(상태 기록)
                ─< DutyAssignment(날짜·칸·멤버)      Period ─< ChangeLog(근무 변경 기록)
auth.Group: Board.admin_group(근무표 관리), Department.input_group(출근표 입력) ─< GroupKeeper(그룹 관리자)
User ─ RosterPref · CalendarFeed · TelegramAlarmProfile · PushAlarmSubscription · AlarmRule(─ Board) ─< AlarmDelivery
AlarmSettings(한 행: 봇 토큰, 장애 알림 chat_id, 푸시 키)
```

46행(코드 블록 끝 ```` ``` ````) 바로 뒤, `- **User**:` 줄 앞에 한 줄을 더한다(`services/boards.py`, `Department.save`, `Board.save`).
- `- **Board**(근무표): 지금은 IT 당번표(`code="it"`, 마이그레이션이 만든다) 하나. 부서·회차·근무 정의·보고서 알림 규칙이 근무표에 속하고, 사람은 부서를 통해 근무표 하나에 속한다(부서 없는 계정은 근무표 없음, `boards.board_of(user)`). 근무표를 만들면 관리 그룹 "<이름> 근무표 관리"가, 부서별 취합(`input_mode=collect`) 근무표에 부서를 만들면 입력 그룹 "<부서> 출근표 입력"이 저절로 생긴다. 회차 겹침·배포·배포 취소·그날의 주인·알림 계산은 근무표 안에서만 따진다. 서비스 함수는 근무표를 명시 인자로 받는다.`

"근무조와 칸" 절: 54–60행 전체를 아래로 바꾼다(`shifts.py`, `services/boards.defs`, 0011 의 IT 정의). 제목이 "근무표와 칸"으로 바뀐다.

```
## 근무표와 칸

칸(cell) 키는 코드에 고정된 목록 `shifts.KEYS`(dawn, normal, dinner, slot0~slot9, night)이고 화면·기록·알림이 똑같이 쓴다. 이 순서가 알림·캘린더·`published_days`의 순회 순서다(바꾸면 알림 내용 hash가 달라져 최근 알림이 다시 나간다).

- **키 글자가 성격을 정한다**: `dawn`·`normal`·`dinner`·`night` = 근무조(`SHIFT_KEYS`, 한 사람 하루 하나, DB 제약), `slot0`~`slot9` = 장중관제(`SLOT_KEYS`, 자동 생성, 칸당 1명, 묶음 키 `slots`·이름 "장중관제"·짧은 이름 "관제").
- 근무표는 쓸 키를 골라 이름·시각·자격을 붙인다(`BoardShift`, 근무 정의). IT 정의는 마이그레이션이 그전 값을 그대로 넣었다: 새벽 06:30~15:30, 정상 08:00~17:00, 석식교대 09:00~18:00, 야간 13:30~21:30, 장중관제 10칸(08:30~18:00, 자격 출근조는 08:30 칸 = 정상, 17:00 칸 = 석식교대, 나머지 = 정상·석식교대, 자격 구분 = 개발자), 기본 알림 대상 = 새벽·석식교대·야간. 끈 정의(`active`)는 새 입력(입력 표·CSV 열, 부서 출근조·스케줄·알림 규칙 선택지, 생성)에서 빠지고(`boards.active_defs(board)`), 표시·지난 행·기록의 이름 찾기에는 남는다(`boards.defs(board)`는 꺼진 것까지 KEYS 순으로 돌려준다).
- `shifts.py`의 헬퍼(`cell_label`·`cell_start`·`cell_end`·`cells_of`·`display_order`·`shift_defs`·`slot_defs`)는 정의 목록을 첫 인자로 받는 순수 함수다. 기본값이 없다. 알림 문구(`alarms/messages`)·일정(`schedule`·`plan`)도 같다.
- 화면 순서: 근무조(시작 시각 순) → 장중관제(키 순).
- 장중관제 배정은 `DutyAssignment(cell="slotN")` 행으로 저장한다(읽을 때 계산하지 않는다). 관제 칸당 한 명은 조건부 unique 제약이 보장한다. 배포 때 지운 행은 `publish_undo`에 `["c", 회차, 날짜, 멤버, 출근조]`(출근표)·`["a", 회차, 날짜, 멤버, "slotN"]`(배정)로 보관한다.
- 근무표와 근무 정의는 관리 화면 "근무표"에서 보기만 한다(1단계). 근무표 추가·편집·근무 정의 편집은 3단계에서 설계 4.3 검증과 함께 연다. code 는 `boards.it_board()` 가 IT 근무표를 찾는 열쇠라 바꾸지 않는다.
- 대상 날짜는 회차 기간의 월~금(휴장일 처리 없음).
```

"역할" 절: 62–69행 전체를 아래로 바꾼다(`perms.py`, `context.nav`, `views/manage._period`, `admin.py`).

```
## 역할

권한은 `auth.Group` 멤버십으로만 판단한다(`perms.py`: `admin_boards`·`is_board_admin`·`is_admin`·`managed_departments`·`can_edit`·`assert_can_edit`). Django permissions와 "스태프 권한"(`is_staff`)·슈퍼유저는 근무표 권한에 쓰지 않는다(`is_staff`는 관리 화면 출입 조건 `admin.site.has_permission`에만 남는다).

| 누가 | 무엇 |
|---|---|
| 멤버(로그인한 누구나) | 근무표·내 근무 조회, 내 근무표의 오늘·미래 근무 변경, 내 알림·캘린더 |
| 출근표 입력 담당(부서 입력 그룹 멤버, `Department.input_group`) | 취합 중인 회차에 자기 부서 출근표 입력 |
| 근무표 관리자(근무표 관리 그룹 멤버, IT = "IT 근무표 관리") | 그 근무표의 회차 관리·생성·배포, 통계, 변경 이력, 지난 날짜 수정, 그 근무표 전 부서 출근표. 회차 뷰는 `_period(request, pid)`가 검사(아니면 404). 메뉴 [회차]·[이력]은 어느 근무표든 관리자면 보인다. [통계]는 slot* 정의가 있는 근무표의 관리자에게만 보인다(perms.stats_boards). 통계 화면은 그중 id가 가장 작은 근무표를 보여 주고, 없으면 403이다(근무표 고르기는 2단계) |
| 그룹 관리자(`GroupKeeper`) | 그 그룹에 멤버를 넣고 빼는 사람으로 기록만 해 둔다(지정·멤버를 고치는 화면은 3단계. 그때까지 멤버는 슈퍼유저가 관리 화면 "사용자"의 "그룹" 칸에서 넣는다) |
| 슈퍼유저 | Django 관리 화면: 사용자("그룹" 칸으로 근무표 관리자 지정)·부서·근무표와 근무 정의(1단계는 보기만)·그룹(이름, 그룹 관리자는 보기만)·계정 발급·로그인 잠금 해제·알림 설정. 근무표 관리자 권한은 자동으로 받지 않는다(관리 그룹에 넣어야 한다) |

- 그룹 관리자는 `Group`에 걸린 표라서(근무표로 가는 FK가 없다) 관리 화면 "그룹"에 보기 전용 인라인으로 보인다(편집은 3단계). 근무표 화면에서는 관리 그룹이 읽기 전용으로만 보인다.
- 저장된 부서의 근무표는 바꿀 수 없다(`admin.DepartmentForm` 의 board 칸이 읽기 전용, 새 부서만 고른다. 옮기기는 필요해지면 별도 기능). 부서 순서(`Department.order`, 기본 99 = 맨 뒤)가 근무표 화면 부서 필터의 순서다.
```

회차·생성·배포:
- 79행(`periods.save_draft`)
  - 지금: `다른 배포 전 회차와 겹치면 막는다`
  - 바꾼 뒤: `같은 근무표의 다른 배포 전 회차와 겹치면 막는다`
  - 같은 줄 맨 앞 `- 작업 중·…` 앞에 `회차는 근무표 하나에 속한다(관리하는 근무표가 여럿이면 만들 때 고른다). ` 를 더한다(`views/manage._new_board`).
- 82행(`services/collect.py`, `_require_input`)
  - `**출근표 입력**(`services/collect.py`): ` 바로 뒤에 `회차와 같은 근무표의 부서만 받는다. ` 를 더한다.
- 83행(`periods.missing_dates`)
  - 지금: `- **생성**(`generator.py`, `services/generate.py`): 4개 부서의 평일이 다 차야 한다.`
  - 바꾼 뒤: `- **생성**(`generator.py`, `services/generate.py`): 그 근무표 부서마다 평일이 다 차야 한다(IT = 4개 부서). 칸 목록은 그 근무표의 관제 정의(`slot_defs`, 키 순)이고, 관제 정의가 없는 근무표는 생성할 것이 없다.`
- 86행(`services/generate.run_generation`, `services/stats`)
  - 지금: `횟수는 기간 중 한 번이라도 자격이 있던 개발자끼리만 비교한다.`
  - 바꾼 뒤: `후보는 그 근무표 부서의 재직자 중 관제 정의의 자격 구분(IT = 개발자)에 드는 사람이고, 횟수는 기간 중 한 번이라도 자격이 있던 사람끼리만 비교한다(통계도 같다).`
- 87행(`publish._others`)
  - 지금: `다른 배포 회차의 `[S, 이 회차 종료일]` 행`
  - 바꾼 뒤: `같은 근무표의 다른 배포 회차의 `[S, 이 회차 종료일]` 행`
- 88행(`- **조회**…` 줄 전체)은 아래로 바꾼다(`boards.owner`·`owners`·`_ranked`, `roster.published_days`, `changes._owner`, `change_notice._live`, `publish.preview_publish`).
  - `- **그날의 주인**(`boards.owner(board, d)`, 여러 날은 `owners`): 그 근무표의 배포 회차 중 `overwrite_from ≤ d ≤ end_date`인 것 가운데 가장 최근에 배포한 것(배포 `PeriodEvent` 순번. 배포 이벤트가 없는 옛 회차는 그보다 오래된 것으로 보고 `published_at`·pk 순). 배포 때 지우는 규칙과 같은 결과라 행이 없는 날에도 주인이 있다. 근무 변경(`changes._owner`), 조회(`services/roster.py`의 `published_days`: 주인이 있는 평일마다 그 회차의 행. 행이 없으면 빈 칸이고 정기 알림·캘린더에는 넘기지 않는다), 변경 알림의 `_live`, 배포 미리보기가 모두 이 함수를 쓴다. 화면 칸의 변경 기록도 주인 회차 것만 보이므로 덮어쓰인 회차의 ChangeLog는 숨겨진다.`
- 89행(`publish.unpublish_info`)에서는 두 군데를 바꾼다.
  - `가장 최근에 배포한 회차만` → `그 근무표에서 가장 최근에 배포한 회차만`
  - `순서는 `PeriodEvent` 순번으로 정한다` → `순서는 근무표마다 `PeriodEvent` 순번으로 정한다`

근무 변경:
- 95행(`perms.assert_can_edit`, `collect.validate_table`, `views/collect._render_table`)
  - 지금: `- 오늘 이전 날짜는 어드민만(`perms.assert_can_edit_date`). 출근표 입력·근무 변경·배포에 모두 적용된다.`
  - 바꾼 뒤: `- 서비스 공개 함수(`change_cell`·`exchange`·`swap`, 첫 인자 다음에 근무표) 첫 줄에 `perms.assert_can_edit(user, board, d)`: 그 근무표 부서 사람이거나 그 근무표 관리자만 바꾼다. 오늘 이전 날짜는 그 근무표 관리자만. 출근표 입력의 지난 날짜 판단도 `perms.is_board_admin(user, period.board)`.`
- 96행(`changes._check_candidate`)
  - 지금: `새로 들이는 사람은 근무표 후보(재직·부서 있음)만.`
  - 바꾼 뒤: `새로 들이는 사람은 그 근무표 부서의 재직자만.`

알림·캘린더:
- 103행(`services/alarms.rule_board`, `RuleForm`)
  - 지금 줄 끝 `채널은 텔레그램·웹 푸시.` 뒤에 한 문장을 더한다.
  - 더할 문장: ` 보고서 규칙은 근무표 하나에 속한다(근무표 선택 칸은 근무표가 둘 이상일 때만 보이고, 하나뿐이면 그 근무표). 개인 규칙은 내 부서의 근무표를 따른다. 기본 규칙(계정 첫 발급)은 근무 정의의 "기본 알림 대상" 근무조로 만든다.`
- 104행은 줄 전체를 아래로 바꾼다(`alarm_runner.collect`, `accounts.on_department_change`).
  - `- 작업자가 매분 `alarm_runner.tick`: 근무표마다 그 근무표의 `published_days`(배정 있는 날만)와 그 근무표 규칙(개인 = 주인 부서의 근무표, 보고서 = `rule.board`)만 넘겨 그 근무표 정의로 `alarms.plan`을 따로 부른다(같은 날 다른 근무표 때문에 취소 알림이 나가지 않게). 지금 보낼 것을 `senders`로 보낸 뒤 `AlarmDelivery`를 남긴다(목적지별, **보낸 뒤에** 기록). 같은 내용은 `last_sent_hash`로 다시 보내지 않고, 근무가 바뀌면 변경·취소 알림을 보낸다. 규칙의 근무표(`board_id`)도 `RULE_FIELDS`에 있다. 관리 화면에서 사람의 부서를 바꿔 근무표가 달라지면 그 사람 개인 규칙의 오늘 이후 `AlarmDelivery`를 지운다(`accounts.on_department_change`).`
- 120행(`calendar._events`, `calendar.set_shifts`)
  - 지금: `넣을 근무는 사용자가 고른다(`CalendarFeed.shifts`, 새벽·정상·석식교대·야간·장중관제, 빈 목록 = 전부).`
  - 바꾼 뒤: `넣을 근무는 사용자가 고른다(`CalendarFeed.shifts`, 내 근무표의 근무조와 장중관제. IT = 새벽·정상·석식교대·야간·장중관제, 빈 목록 = 전부).`

**3b. `docs/OPERATIONS.md`**

- 62행 주석
  - 지금: `# 첫 어드민: 아이디·이름·비밀번호를 묻는다(아래 "처음 한 번: 계정 만들기")`
  - 바꾼 뒤: `# 첫 어드민: 아이디·이름·비밀번호를 묻는다. 이어서 아래 "처음 한 번: 계정 만들기"대로 근무표 관리 그룹에 넣는다`
- 297행(`- 첫 어드민은 설치 때 …` 줄)은 아래 두 항목으로 바꾼다. 1단계 관리자 지정은 사용자 화면의 "그룹" 칸으로 한다(그룹 화면의 멤버·그룹 관리자 편집은 3단계).

```
- 첫 어드민은 설치 때 `sudo -u duty .venv/bin/python manage.py createsuperuser` 로 만든다. 아이디·비밀번호 말고 **이름**도 묻는다. 이 계정은 부서가 없어 근무표 대상이 아닌 어드민 전용 계정이고, "스태프 권한"·"슈퍼유저 권한"이 켜져 있어 관리 화면에 들어간다. 기본 알림 규칙은 생기지 않는다(필요하면 알림 화면에서 추가).
- **이어서 바로 (한 번)**: 슈퍼유저는 그것만으로 근무표 관리자가 아니다(마이그레이션이 `createsuperuser` 보다 먼저 돌아 "IT 근무표 관리" 그룹이 비어 있다). `/<DUTY_ADMIN_PATH>/` → "사용자" → 내 계정 → "그룹" 칸에서 **"IT 근무표 관리"** 를 오른쪽으로 옮기고 저장한다. 사이트에 다시 들어가 메뉴에 [회차]·[이력](관제 정의가 있으면 [통계]도)이 보이면 된다. 그룹 관리자 지정은 3단계 그룹 화면에서 한다.
```

- 301–302행은 아래 세 항목으로 바꾼다.

```
- 어드민 전용 계정(근무표에 안 들어감)은 부서를 비워 둔다. 관리 화면에 들어갈 사람(슈퍼유저)은 "스태프 권한"과 "슈퍼유저 권한"을 둘 다 켠다. Django 관리 화면(사용자·부서·근무표·그룹·입력 담당자, 계정 발급, 잠금 해제)은 슈퍼유저만 쓸 수 있다(스태프에게 모델 권한을 줘도 들어오지 못한다). 슈퍼유저는 1~2명을 가정한다.
- **근무표 관리자**(회차·생성·배포·통계·이력·지난 날짜 수정)는 그룹으로 정한다: "사용자" → 그 사람 → "그룹" 칸에서 "IT 근무표 관리"를 넣고 뺀다(관리 화면 "그룹"은 이름과 멤버 목록만 보인다). "스태프 권한" 체크는 관리자 판정에 쓰이지 않는다.
- 부서 입력 담당자는 부서 화면의 "입력 담당자"에서 지정한다(그 부서의 입력 그룹 "<부서> 출근표 입력" 멤버가 된다. 부서를 만들면 입력 그룹이 저절로 생긴다). 부서 화면에서 근무표(새 부서만. 저장한 부서의 근무표는 바꿀 수 없다)와 순서(근무표 화면 부서 필터 순서)도 고른다.
```

- 323행(`- **롤백**: …` 항목) 바로 뒤에 한 항목을 더한다(0011·0013·0016 의 동작).

```
- **근무표 일반화 1단계로 올릴 때 (한 번)**: `migrate` 가 데이터를 옮긴다. IT 근무표와 근무 정의(지금 값 그대로), "IT 근무표 관리" 그룹(지금 "스태프 권한"이 켜진 사람), 부서마다 "<부서> 출근표 입력" 그룹(지금 입력 담당자), 장중관제 행 변환, 지금 슈퍼유저를 모든 새 그룹의 그룹 관리자로. 같은 이름의 그룹이 이미 있으면 `migrate` 가 그 이름을 알려 주며 멈춘다. 그러면 위 "롤백"대로 되돌리고, 사이트를 켠 뒤 관리 화면 "그룹"에서 그 그룹 이름을 바꾸고 업그레이드를 처음부터 다시 한다. 이 버전부터 관리자 지정은 그룹으로 한다("처음 한 번: 계정 만들기"). "스태프 권한" 체크는 관리자 판정에 쓰이지 않는다(관리 화면 출입에만, 슈퍼유저와 함께).
```

**3c. `docs/OVERVIEW.md`** 28–29행
- 28행
  - 지금: `| 관리자(스태프) | IT 운영 담당 |`
  - 바꾼 뒤: `| 관리자(근무표 관리 그룹) | IT 운영 담당 |`
- 29행
  - 지금: `관리 화면: 계정 발급·부서·입력 담당자·로그인 잠금 해제·알림 설정`
  - 바꾼 뒤: `관리 화면: 계정 발급·부서·입력 담당자·관리자 지정(사용자의 그룹 칸)·근무표 보기·로그인 잠금 해제·알림 설정`

**3d. `README.md`** 17–18행
- 17행
  - 지금: `| 관리자(스태프) |`
  - 바꾼 뒤: `| 관리자(근무표 관리 그룹) |`
- 18행
  - 지금: `관리 화면: 계정 발급·부서·입력 담당자·로그인 잠금 해제·알림 설정(관리자 1~2명이 함께 가진다)`
  - 바꾼 뒤: `관리 화면: 계정 발급·부서·입력 담당자·관리자 지정(사용자의 그룹 칸)·근무표 보기·로그인 잠금 해제·알림 설정(관리자 1~2명이 함께 가진다)`

**3e. `docs/DEVELOPMENT.md`**
- 13행
  - 지금: `.venv/bin/python manage.py createsuperuser`
  - 바꾼 뒤: `.venv/bin/python manage.py createsuperuser   # 그다음 관리 화면 → 사용자 → 내 계정 → 그룹 칸에 "IT 근무표 관리"(OPERATIONS "처음 한 번")`
- 63행(`- 영상 하나만 다시 뽑으려면 …`) 바로 뒤에 한 항목을 더한다.
  - `- 가짜 데이터는 마이그레이션이 만든 IT 근무표(`boards.it_board()`)에 부서(order 0~3: MEMS·TMCH·MD·UI)·회차를 붙이고, admin 을 "IT 근무표 관리" 그룹에, manager 를 MEMS 입력 그룹에 넣는다(관리자·담당자 판정이 그룹이라서). `tests/test_help_seed.py` 가 seed.py 가 끝까지 도는지 확인한다.`

**3f. `docs/PRINCIPLES.md`**

결정 기록 표 끝에 여섯 줄을 더한다. 지금 마지막 줄은 `| 2026-11-13 | 웹 앞에 nginx … |` 이고, 그 뒤에 넣는다.

```
| 2026-11-15 | 근무표(Board) 단위로 회차 겹침·배포·배포 취소·그날의 주인·알림 계산을 따진다. IT 당번표도 근무표 하나 | 시장운영실 근무표를 같은 앱에서 운영하되, 서로의 행을 지우거나 알림을 취소하지 않게 |
| 2026-11-15 | 칸 키는 코드에 고정된 목록이고 키 글자가 성격(근무조·장중관제)을 정한다. 근무표는 이름·시각·자격만 붙인다 | 성격을 설정으로 열면 생성·알림·검증 코드가 갈래마다 는다. 근무조가 5개 이상 필요하면 키를 늘리는 마이그레이션 |
| 2026-11-15 | 그날의 주인 = 배포 회차의 기간(`overwrite_from`~종료일) 중 가장 최근 배포 | 행이 없는 날에도 주인을 잃지 않고, 배포 때 행을 지우는 규칙과 같은 결과가 나온다 |
| 2026-11-15 | 장중관제 배정은 `DutyAssignment` 행(cell="slotN")으로 저장한다 | 읽을 때 계산하면 변경 기록·알림·배포 취소가 다른 길을 타야 한다 |
| 2026-11-15 | 권한은 그룹(근무표 관리·부서 입력·그룹 관리자). 스태프 체크와 슈퍼유저는 근무표 관리자 판정에 쓰지 않는다 | 근무표마다 관리자가 다르고, 관리 화면 권한(슈퍼유저)과 근무 운영 권한을 떼어 둔다 |
| 2026-11-15 | 1단계 근무표 관리 화면은 보기만, 편집·추가·그룹 관리자 지정은 3단계. 관리자 지정은 사용자 화면의 그룹 칸 | `boards.it_board()` 가 code 로 IT 근무표를 찾아 잘못 고치면 화면·알림이 깨지고, 근무 정의 편집은 설계 4.3 검증과 함께 열어야 한다 |
```

휴장일·점심당번·보고서 재발송 결정은 2단계 PR 에서 더한다.

- [ ] **Step 4: 문서 grep 통과 확인**

```bash
grep -nE "ControlDuty|is_staff|assert_can_edit_date|Department\.managers|관리자\(스태프\)|어드민 여부|근무조·관제 칸 상수|칸\(cell\) 키 14개" docs/ARCHITECTURE.md docs/OVERVIEW.md docs/OPERATIONS.md README.md
grep -n "근무표와 칸\|boards.owner\|is_board_admin\|DutyAssignment" docs/ARCHITECTURE.md | wc -l
grep -c "^| 2026-11-15 |" docs/PRINCIPLES.md
```

기대 결과:
- 첫 grep: ARCHITECTURE 의 새 "역할" 절 첫 문단 한 줄만 나온다(`is_staff`는 근무표 권한에 쓰지 않고 `admin.site.has_permission`에만 남는다는 설명). 그 밖의 줄이 나오면 Step 3 을 빠뜨린 것이다.
- 두 번째: 5 이상
- 세 번째: `6`

- [ ] **Step 5: 화면이 `main` 과 같은지 확인(가짜 데이터, 1400·390px)**

`main` 과 이 브랜치를 각각 새 임시 DB 로 띄우고 같은 가짜 데이터(seed.py, 생성 씨앗 1)를 넣는다. 그다음 두 가지를 비교한다.
- HTML: 21쪽, 세 계정
- 화면: 1400px·390px 전체 길이

seed 는 실제 오늘 날짜를 쓰므로 두 쪽을 같은 날 연달아 띄운다. foreground `sleep` 은 쓰지 않는다. 서버 대기는 `curl --retry` 로 한다. 이 절차는 Task 9 까지 적용한 사본으로 미리 돌려 봤다. 결과는 HTML 차이 0, 가로 넘침 0 이었다. 화면은 도움말 영상의 버퍼 막대만 달랐다.

5-1. 준비. `main` 사본은 `git archive` 로 받는다(Task 3 Step 17 과 같다). 그리고 `$W/serve.py` 를 쓴다. 이 스크립트가 하는 일은 넷이다.
- migrate
- seed
- 쪽 HTML 저장, 세션 쿠키 저장
- (인자가 있으면) 같은 프로세스에서 runserver

CSRF 토큰과 DB 마다 다른 푸시 공개키는 가린다.

```bash
cd /home/dustbox/develop/nxt/duty_generator
W=$(mktemp -d); R=$PWD; echo $W   # 셸 상태가 이어지지 않으면 다음 명령에서 W·R 을 다시 정한다
mkdir $W/main && git archive main | tar -x -C $W/main
cat > $W/serve.py <<'EOF'
"""화면 확인용(저장소 밖): test_settings 의 임시 DATA_DIR 에 migrate·가짜 데이터를 넣고, 쪽 HTML·세션 쿠키를 OUT 에 남긴 뒤 같은 프로세스에서 서버를 띄운다."""
import json
import os
import re
import sys
from datetime import timedelta
from pathlib import Path

import django

django.setup()
from django.core.management import call_command  # noqa: E402
from django.test import Client  # noqa: E402

from duty import perms  # noqa: E402
from duty.models import User  # noqa: E402

call_command("migrate", verbosity=0)
exec(open("tools/help_videos/seed.py", encoding="utf-8").read(), {"__name__": "seed"})

out = Path(os.environ["OUT"])
out.mkdir(parents=True, exist_ok=True)
t = perms.today()
mon = t - timedelta(days=t.weekday())
d = t if t.weekday() < 5 else mon + timedelta(days=7)
PAGES = {
    "member": ["/", "/?view=month", "/?view=week", f"/day/{d}/", f"/cell/{d}/normal/", f"/cell/{d}/slot0/", "/me/", "/alarms/", "/help/"],
    "manager": ["/", "/collect/", "/collect/2/MEMS/", "/help/"],
    "admin": ["/", "/periods/", "/periods/1/", "/periods/2/", "/stats/", "/changes/", "/collect/", f"/day/{d}/"],
}
cookies = {}
for who, urls in PAGES.items():
    c = Client(HTTP_HOST="127.0.0.1")
    c.force_login(User.objects.get(username=who))
    cookies[who] = c.cookies["sessionid"].value
    for u in urls:
        r = c.get(u)
        html = r.content.decode()
        html = re.sub(r'const KEY = "[^"]*"', 'const KEY = "KEY"', html)  # 푸시 공개키(DB 마다 새로 만든다)
        html = re.sub(r"[A-Za-z0-9]{64}", "TOKEN", html)  # CSRF 토큰
        (out / f"{who}{re.sub(r'[^0-9A-Za-z]+', '_', u)}.html").write_text(f"{r.status_code}\n{html}")
(out / "cookies.json").write_text(json.dumps(cookies))
ADMIN_SITE = ["/admin/", "/admin/duty/board/", "/admin/duty/board/1/change/", "/admin/auth/group/", "/admin/auth/group/1/change/",
              "/admin/duty/user/", "/admin/duty/department/MEMS/change/"]  # 1단계에서 바뀐 관리 화면: main 과 비교하지 않고 이 브랜치만 본다
(out / "pages.json").write_text(json.dumps({**PAGES, "admin_site": ADMIN_SITE}))
print("pages saved", flush=True)
if len(sys.argv) > 1:
    call_command("runserver", sys.argv[1], use_reloader=False)
EOF
```

5-2. HTML 비교(서버 없이).

```bash
(cd $R && OUT=$W/out-new DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. $R/.venv/bin/python $W/serve.py)
(cd $W/main && OUT=$W/out-main DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. $R/.venv/bin/python $W/serve.py)
for f in $W/out-new/*.html; do head -1 $f; done | sort | uniq -c
diff -r $W/out-main $W/out-new -x cookies.json -x pages.json
```

기대 결과:
- 두 번 모두 `seeded`·`pages saved` 가 나온다.
- 상태 코드는 `21 200` 하나뿐이다.
- `diff` 는 아무것도 내지 않는다. seed 를 돌린 시각이 찍히는 줄(`/changes/` 의 변경 시각, `/periods/1/` 의 상태 기록 시각)이 분 단위로 갈리면, 그 시각 글자만 다른 것은 허용한다.
- 그 밖의 차이(글자, 칸 순서, 링크, 상태 코드)가 하나라도 있으면 원인을 고친다. 고치는 순서는 테스트 먼저 → 고침 → 전체 테스트 → `fix:` 커밋이다. 그다음 Step 5 를 처음부터 다시 한다.

5-3. `$W/shot.mjs` 를 쓴다. 같은 쪽을 1400px·390px 전체 길이로 찍고, 가로로 넘치는지 검사한다.

```bash
cat > $W/shot.mjs <<'EOF'
// 화면 확인용(저장소 밖): pages.json 의 쪽을 1400px·390px 전체 길이로 찍고 가로 넘침을 검사한다. node shot.mjs <BASE> <OUT> [main]
import {spawn} from 'node:child_process'; import fs from 'node:fs';
const [BASE, OUT, MODE] = process.argv.slice(2);
const cookies = JSON.parse(fs.readFileSync(`${OUT}/cookies.json`)), PAGES = JSON.parse(fs.readFileSync(`${OUT}/pages.json`));
if (MODE === 'main') delete PAGES.admin_site;  // main 의 관리 화면은 찍지 않는다(1단계에서 바뀐 화면)
const sleep = ms => new Promise(r => setTimeout(r, ms));
const port = 9300 + Math.floor(Math.random() * 500);
const chrome = spawn('google-chrome', ['--headless=new', '--no-sandbox', '--hide-scrollbars', `--remote-debugging-port=${port}`,
  `--user-data-dir=${OUT}/prof`, 'about:blank'], {stdio: 'ignore'});
let tabs; for (let i = 0; i < 50 && !tabs; i++) { try { tabs = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { await sleep(200); } }
const ws = new WebSocket(tabs.find(t => t.type === 'page').webSocketDebuggerUrl); await new Promise(r => ws.onopen = r);
let id = 0; const pend = {}; ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pend[m.id]) pend[m.id](m); };
const send = (method, params = {}) => new Promise(r => { const i = ++id; pend[i] = r; ws.send(JSON.stringify({id: i, method, params})); });
const ev = async x => (await send('Runtime.evaluate', {expression: x, returnByValue: true})).result.result.value;
await send('Page.enable'); await send('Network.enable');
for (const [who, urls] of Object.entries(PAGES)) {
  await send('Network.clearBrowserCookies');
  await send('Network.setCookie', {name: 'sessionid', value: cookies[who === 'admin_site' ? 'admin' : who], url: BASE});
  for (const u of urls) for (const w of [1400, 390]) {
    await send('Emulation.setDeviceMetricsOverride', {width: w, height: 900, deviceScaleFactor: 1, mobile: w < 500});
    await send('Page.navigate', {url: BASE + u}); await sleep(1500);
    const over = await ev('document.documentElement.scrollWidth > innerWidth');
    const h = await ev('document.documentElement.scrollHeight');
    await send('Emulation.setDeviceMetricsOverride', {width: w, height: h, deviceScaleFactor: 1, mobile: w < 500});
    const shot = await send('Page.captureScreenshot', {format: 'png'});
    const f = `${OUT}/${who}${u.replace(/[^0-9A-Za-z]+/g, '_')}-${w}.png`;
    fs.writeFileSync(f, Buffer.from(shot.result.data, 'base64'));
    console.log(over ? 'OVERFLOW' : 'ok', f);
  }
}
chrome.kill(); process.exit(0);
EOF
```

5-4. 두 서버를 띄우고 찍는다. `exec` 를 써서 `$!` 가 서버 프로세스 자신을 가리키게 한다. 서버는 5-2 와 같은 날 새 DB 로 다시 만든다. 그래서 HTML 과 쿠키 파일도 다시 쓰인다. 이 블록은 한 Bash 호출 안에서 잇는다(`OLD`·`NEW` 가 남게). 나누어 돌렸다면 끝에서 `pkill -f "serve.py 127.0.0.1:879[56]"` 로 끈다.

```bash
(cd $R && OUT=$W/out-new DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. exec $R/.venv/bin/python $W/serve.py 127.0.0.1:8795 >$W/new.log 2>&1) & NEW=$!
(cd $W/main && OUT=$W/out-main DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. exec $R/.venv/bin/python $W/serve.py 127.0.0.1:8796 >$W/main.log 2>&1) & OLD=$!
curl -s -o /dev/null --retry 60 --retry-connrefused --retry-delay 1 http://127.0.0.1:8795/login/
curl -s -o /dev/null --retry 60 --retry-connrefused --retry-delay 1 http://127.0.0.1:8796/login/
node $W/shot.mjs http://127.0.0.1:8796 $W/out-main main | grep -v "^ok"
node $W/shot.mjs http://127.0.0.1:8795 $W/out-new | grep -v "^ok"
ls $W/out-main/*.png | wc -l; ls $W/out-new/*.png | wc -l
for f in $W/out-main/*.png; do cmp -s "$f" "$W/out-new/$(basename $f)" || echo "다름: $(basename $f)"; done
kill $OLD $NEW
```

기대 결과:
- 두 node 실행 모두 아무것도 내지 않는다(`OVERFLOW` 없음).
- PNG 수는 `42`(main), `56`(new)이다. new 에는 관리 화면 7쪽 × 2폭이 더 있다.
- `다름:` 이 나와도 되는 것은 둘뿐이다.
  - 도움말 쪽(`*_help_-*.png`): 영상이 버퍼링한 양에 따라 재생 막대가 몇 px 다르다.
  - 시각이 들어간 쪽(`admin_changes_*`, `admin_periods_1_*`)
- `다름` 으로 나온 파일은 main·new 두 장을 Read 로 열어, 위 말고는 같은지 눈으로 본다.
- new 쪽 아래 파일들은 Read 로 열어, 빈 화면이나 오류 화면이 아니고 정상으로 그려졌는지 본다.
  - 사용자 화면: `member_-1400.png`, `member_-390.png`, `member_view_month-1400.png`, `member_day_*-390.png`, `admin_periods_1_-1400.png`
  - 관리 화면(1단계에서 새로 생기거나 바뀐 화면, 1400·390 둘 다):
    - `admin_site_admin_duty_board_1_change_-*`: 이름·code·입력 방식·관리 그룹과 근무 정의 14줄이 모두 읽기 전용 글자로 나오고, 키는 "근무조 1"·"관제 1" 꼴이다. 입력 칸과 [저장]·[삭제] 버튼이 없다.
    - `admin_site_admin_auth_group_-*`: 그룹 5개("IT 근무표 관리", 부서 입력 그룹 4개)와 멤버 이름
    - `admin_site_admin_auth_group_1_change_-*`: 이름 칸과 보기 전용 "그룹 관리자" 인라인. 권한·멤버 칸이 없다.
    - `admin_site_admin_duty_user_-*`: 그룹 칸이 있고, 스태프 칸은 없다.
    - `admin_site_admin_duty_department_MEMS_change_-*`: 근무표·순서·가능한 출근조·입력 담당자 칸

5-5. 정리한다.

```bash
rm -rf $W
```

- [ ] **Step 6: 전체 테스트**

```bash
.venv/bin/pytest -W error -q   # 약 8분. Bash 도구는 run_in_background 로 돌리거나 timeout 600000ms
```

기대 결과: `914 passed`, 경고 0 이다. Task 9 끝과 같은 수이고, 이 작업은 테스트를 더하지 않는다. 마지막 요약 줄을 그대로 적어 둔다(PR 본문에 넣는다).

- [ ] **Step 7: 테스트 단언이 바뀌지 않았는지 확인(설계 11절 a~d)**

```bash
git diff main...HEAD --stat -- tests/
git diff main...HEAD --diff-filter=M -- tests/ | grep -nE "^[-+][^-+].*\bassert\b"
git diff main...HEAD --diff-filter=D --name-only -- tests/
```

- 두 번째 명령이 낸 줄을 하나도 거르지 않고 모두 본다. `-` 줄과 그에 맞는 `+` 줄을 짝지어, 각각 허용 변환 (a)~(d) 중 무엇인지 적는다.
  - (a) 준비 코드의 근무표·관리 그룹
  - (b) ControlDuty → DutyAssignment, `slot=n` → `cell="slotN"`(단언문 안 포함)
  - (c) 헬퍼·서비스 호출에 근무표나 IT 정의를 인자로 넘김. 예: `find_day(D)` → `find_day(boards.it_board(), D)`, `cell_label("slot0")` → `cell_label(IT_DEFS, "slot0")`
  - (d) test_shifts 상수 단언 → IT 정의. 기대 값은 그대로다. `CELLS` → `KEYS` 이름 바꾸기도 여기에 넣는다(Task 8, 값은 같다).
- `--diff-filter=M` 이라 `main` 에 있던 파일만 본다. 새 테스트 파일(근무표 둘, 마이그레이션, 문구 고정, `test_help_seed.py` 등)은 새 단언이라 제외된다.
- 세 번째 명령은 아무것도 내지 않아야 한다(기존 테스트 파일 삭제 없음).
- 기존 파일에서 기대 값(`==` 오른쪽, 기대 문자열·숫자·목록)이 바뀐 줄이 하나라도 있으면, 그 테스트를 원래 기대 값으로 되돌리고 코드를 고친다. 그다음 Step 6 을 다시 한다.
- 단언이 아닌 준비 코드 가운데 a~d 밖의 수정은 하나다. PR 본문 "결정이 필요한 것"에 적는다.
  - `tests/test_views_roster.py::publish_more` 의 `p.start_date = min(p.start_date, *days)` 한 줄(Task 5). 그날의 주인이 회차 기간으로 정해지기 때문에 필요하다.

- [ ] **Step 8: 커밋(문서)**

```bash
git add docs/ARCHITECTURE.md docs/OPERATIONS.md docs/OVERVIEW.md docs/DEVELOPMENT.md docs/PRINCIPLES.md README.md
git commit -m "docs: 근무표·키와 성격·그날의 주인·그룹 권한 반영, 새 설치·1단계 업그레이드 안내

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

- [ ] **Step 9: Codex 최종 리뷰(읽기 전용, 여러 차례 토론)**

먼저 설계 문서가 이 브랜치에 있는지 본다. `test -f docs/superpowers/specs/2026-11-15-boards-design.md && echo ok` 가 `ok` 를 내야 한다. 없으면 설계 PR(`docs/boards-design`)이 아직 main 에 안 들어간 것이다. 그때는 그 PR 을 먼저 합치고 이 브랜치에 main 을 merge 한다.

```bash
codex exec -s read-only -C /home/dustbox/develop/nxt/duty_generator "이 저장소의 현재 브랜치(git diff main...HEAD)를 리뷰해 줘. 기준은 docs/superpowers/specs/2026-11-15-boards-design.md 의 11절 1단계 범위·완료 기준과 10절 1단계 마이그레이션, docs/ARCHITECTURE.md. 확인할 것: (1) 사용자 화면 글자·알림 문구·알림 링크·칸 순서가 main 과 같은가, (2) 기존 테스트 단언의 기대 값이 바뀐 곳이 없는가(허용 변환 a~d 만, tests/test_views_roster.py publish_more 의 준비 코드 한 줄은 따로 판단), (3) publish._others·배포 취소 순서·회차 겹침·그날의 주인(boards.owner)·알림 plan 이 근무표 단위인가, (4) 마이그레이션 0010~0017: 그룹 이름 충돌 중단, 되돌리기, NOT NULL 전 채우기, (5) 권한이 그룹으로만 판정되는가(perms.py, context.py, views/manage._period, collect), (6) 문서(ARCHITECTURE·OPERATIONS·OVERVIEW·DEVELOPMENT·PRINCIPLES·README)가 코드와 맞는가, (7) duty/admin.py 의 근무표·근무 정의·그룹 관리자가 보기 전용인지(추가·수정·삭제 불가), 그룹 화면이 권한 칸만 숨기는지. data/ 폴더, *.sqlite3 등 DB 파일, .superpowers/, .env 는 절대 열지 마(실명). manage.py 를 돌려야 하면 DJANGO_SETTINGS_MODULE=config.test_settings 만 쓰고 DUTY_DEBUG=1 은 쓰지 마. 지적은 파일:줄과 근거, 심각도 순으로 한국어로."
```

- 맞는 지적은 이 순서로 처리한다.
  1. 실패하는 테스트를 먼저 쓴다(문서 지적은 Step 4 의 grep 으로 대신한다).
  2. 고친다.
  3. 해당 테스트를 돌린다.
  4. 전체 테스트(Step 6)를 돌린다.
  5. 커밋한다(`fix:` 또는 `docs:` + 한국어). 바꾼 파일만 add 한다.
- 동의하지 않는 지적은 근거를 붙여 다시 묻는다. 같은 명령 끝에 "앞선 지적 N에 대한 반론: …" 을 더한다. 합의할 때까지 되풀이한다.
- Codex 사용량 한도에 걸리면, 안내된 재설정 시각까지 기다렸다가 같은 명령으로 이어서 한다.
- 고친 것이 화면에 닿으면 Step 5 를 다시 한다.

- [ ] **Step 10: PR 만들기**

`<Step 6 요약 줄>` 을 Step 6(또는 Codex 수정 뒤 마지막 전체 테스트)에서 실제로 나온 마지막 줄로 바꾼 다음 실행한다.

```bash
git push -u origin HEAD
gh pr create --base main --title "feat: 근무표 일반화 1단계 — 근무표·근무 정의·그룹 권한(화면·알림 변화 없음)" --body "$(cat <<'EOF'
## 요약
- 근무표(Board)·근무 정의(BoardShift)·GroupKeeper·DutyAssignment 모델과 1단계 마이그레이션 0010~0017
  - IT 근무표·정의 14개, 관리/입력 그룹, ControlDuty→DutyAssignment·publish_undo k→a, managers M2M→입력 그룹, board NOT NULL, 알림 규칙 근무표 제약
  - 되돌리기 포함. 같은 이름의 그룹이 있으면 migrate 가 멈춘다
- shifts.py 헬퍼가 정의 목록을 받는 순수 함수로 바뀌고, 모든 호출부가 근무표 정의를 읽는다. 옛 상수(COMMUTE_SHIFTS·CONTROL_SLOTS·SHIFT_TIMES·CELLS 등) 삭제
- 그날의 주인(boards.owner), 근무표 단위 회차 겹침·배포·배포 취소·생성·취합·통계, 근무표마다 알림 plan, RULE_FIELDS 에 board_id
- 권한은 그룹(perms.admin_boards·is_board_admin·managed_departments·assert_can_edit). is_staff 는 관리 화면 출입에만
- 관리 화면: 근무표·근무 정의 보기, 그룹 화면 권한 칸 숨김(관리자 지정은 사용자 화면 그룹 칸), 사용자 목록 그룹 칸, 부서의 근무표·순서
- 사용법 영상 가짜 데이터가 IT 근무표·그룹을 씀. 문서 갱신(새 설치 "처음 한 번" 그룹 지정, 1단계 업그레이드 안내)

## 확인
- 전체 테스트: <Step 6 요약 줄>
- 기존 테스트 단언의 기대 값 불변(허용 변환 a~d 만)
- main 과 같은 가짜 데이터로 HTML 21쪽 비교, 1400·390px 화면 비교: 차이 없음(도움말 영상 버퍼 막대·기록 시각 제외), 가로 넘침 없음
- 새 관리 화면(근무표·그룹·사용자·부서) 1400·390px 확인
- Codex 최종 리뷰 합의

## 결정이 필요한 것
- tests/test_views_roster.py publish_more 에 준비 코드 한 줄(`p.start_date = min(p.start_date, *days)`)을 더했다. 그날의 주인을 회차 기간으로 정하므로, 기간 밖 날짜에 행을 넣던 준비 코드를 기간 안으로 맞춘 것이다. 단언은 그대로다.

## 운영 반영 시
- 업그레이드 절차대로 한다(첫 줄 백업). 이 버전부터 관리자 지정은 관리 화면 "사용자 → 대상 계정 → 그룹 칸에서 IT 근무표 관리 선택"
- 같은 이름의 그룹이 이미 있으면 migrate 가 멈춘다 → 롤백한 뒤 그룹 이름을 바꾸고 다시

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

- [ ] **Step 11: 머지(따로 한다)**

머지 전에 확인할 것:
- 마지막 커밋 뒤의 전체 테스트 결과가 `passed` 이고, 실패·경고가 없다.
- Step 9 의 Codex 합의가 끝났다.
- `gh pr checks` 가 있으면 모두 통과다.

확인한 뒤 별도 명령으로 머지한다. 테스트 명령과 머지 명령을 `&&` 등으로 한 줄에 잇지 않는다(merge-after-green). CLAUDE.md 에 따라 머지는 Claude 가 직접 해도 된다. 머지 뒤 PR 링크를 보고한다.

```bash
gh pr merge --merge --delete-branch
```

---

참고 (Task 10 을 쓰면서 정한 것):
- 이 작업은 1단계 브랜치(Task 1 에서 main 으로부터 딴 브랜치)에서 한다고 가정했다. PR 은 `HEAD` 를 push 해 연다.
- 옛 Task 9 에서 seed 부분(옛 Step 1~6)은 뺐다. Task 5 가 이미 했다(지적 15). 옛 Step 7 의 "옛 상수 정의 지우기"도 뺐다. Task 8 이 `duty/shifts.py` 에서 이미 지웠다. 그래서 이 작업은 grep 확인만 하고 코드를 고치지 않는다.
- 지적 16: `.is_staff` 속성 접근만 찾도록 grep 을 좁혔다. 기대는 `has_permission` 한 줄이다.
- 지적 17: 앞 작업의 문서 수정을 모두 여기로 모았다. 담긴 것은 Task 2 의 DutyAssignment·publish_undo 행 모양, Task 3 의 shifts·boards.py 행, Task 7 의 생성·취합·통계 절, Task 8 의 알림·캘린더 절, Task 9 의 admin.py 행·역할 표 슈퍼유저 행·GroupKeeper 보기 전용 인라인을 그룹 화면에 둔 이유다.
- OPERATIONS 의 관리자 지정 문장: 1단계 그룹 화면은 그룹 관리자를 보기만 하므로(Task 9), 관리자 지정은 사용자 화면 "그룹" 칸 하나로 안내하고 그룹 관리자 지정은 3단계로 적는다.
- 화면 확인은 옛 계획의 `DUTY_DEBUG=1` + 빈 `DUTY_DATA_DIR` + worktree 대신, `config.test_settings` + 한 프로세스 serve.py + `git archive` 로 바꿨다(지적 19).
- 부서 관리 화면 주소는 `/admin/duty/department/MEMS/change/` 이다. 부서의 pk 가 code 라서, 옛 초안의 `…/department/1/…` 은 잘못된 주소였다.
- 다크 모드 화면 확인은 넣지 않았다. 1단계는 CSS 를 바꾸지 않는다.

<!-- 검증 메모: Task 1~9 를 적용한 /tmp/t9v2(915 passed)에서 Step 1 의 grep 다섯 개를 돌렸고, 결과가 위 기대와 같았다(앱 코드는 calendar.py 주석 1줄, .is_staff 는 admin.py:377 한 줄, managers 는 admin.py:40·78). Step 5 의 serve.py·shot.mjs 는 /tmp/t9v2 와 main(git archive)으로 그대로 돌렸다. 결과는 HTML 21쪽 모두 200, diff 0. PNG 는 main 42장·new 56장, OVERFLOW 0. cmp 차이는 manager_help 1400·390, member_help 390 셋뿐이었고, 잘라 보니 영상 버퍼 막대였다. 근무표 변경 화면(1400)이 정상으로 그려지는 것도 눈으로 봤다. 그룹 pk 1 = "IT 근무표 관리", 부서 pk = code 도 확인했다. 문서 줄 번호는 main 의 docs 를 읽어 맞췄다. -->


---

