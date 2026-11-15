# 근무표 일반화 2단계(공통 새 기능) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 1단계 구조 위에 휴장일·메모(근무 없음)·사유·점심당번·근무표 고르기·글씨 크기·로그인 유지를 더한다. IT 화면에도 바로 보인다.

**Architecture:** 휴장일은 DB 표(`Holiday`, 라이브러리로 자동 동기화 + 관리 화면), 메모는 (근무표, 날짜)에 붙는 `Memo`, 사유는 `Commute.reason`, 점심당번은 키 `lunch`(가장 이른 근무조를 따라 채우고 부서별 점심 시각으로 알림·캘린더). 만드는 도구(입력 표·CSV·생성·빈 날 검사)는 `boards.skip_dates(period)`(근무 없음 ∪ 새 회차의 휴장일)를 건너뛴다.

**Tech Stack:** Python 3.12, Django 5.2, SQLite(WAL), pytest + pytest-django, htmx, 새 의존성 `holidays`.

**Spec:** `docs/superpowers/specs/2026-11-15-boards-design.md` (2단계 = 11절 "2단계", 마이그레이션 = 10절 "2단계")

## Global Constraints

- 기존 IT 알림 문구·hash 는 점심당번 보고서 줄 추가(설계 8.1, 2단계 배포 때 보고서 한 번 재발송 허용) 외에는 바뀌지 않는다(`tests/test_alarm_texts_it.py` 유지).
- 각 작업이 끝난 시점에 `.venv/bin/pytest -W error -q` 전체가 통과한다(경고 0개). 기대 테스트 수는 참고값.
- TDD. DB를 바꾸는 규칙은 `duty/services/`(뷰·명령에서 모델을 직접 고치지 않는다). 순수 모듈(`shifts`·`generator`·`csv_io`·`ics`·`alarms/`, 새 `market_days`)에는 ORM 없음.
- 정해진 값 칸은 `choices` + DB `CheckConstraint`. 기록을 남길 FK는 `PROTECT`. 마이그레이션 파일은 지우지 않는다. 2단계 마이그레이션은 되돌리기를 만들지 않는다(백업 복원).
- manage.py 명령은 `DJANGO_SETTINGS_MODULE=config.test_settings`. 브라우저 확인용 서버는 `DUTY_ENV_FILE= DUTY_DEBUG=1 DUTY_DATA_DIR=<임시 폴더>` + 가짜 데이터(`tools/help_videos/seed.py`)로만 띄우고, 끝나면 임시 폴더·캡처를 지우고 서버는 PID로 끈다.
- 실명 데이터 금지. `data/`, DB 파일, `.superpowers/`, `.env` 는 열지 않는다.
- 화면 문구는 한국어. 커밋 메시지는 `feat:`/`fix:`/`docs:`/`style:` + 한국어 요약.

## 작업 순서와 마이그레이션 번호

| Task | 내용 | 마이그레이션 |
|---|---|---|
| 1 | 휴장일(Holiday 표·자동 동기화·관리 화면·표시), Period.skip_holidays, 이름 접미사 사전 검사 | 0018_holidays |
| 2 | 메모(날·주·달)와 근무 없음 | 0019_memo |
| 3 | 만드는 도구의 휴장일·근무 없음 건너뛰기, 영업일 알림 | 없음 |
| 4 | 사유(휴가·출장·교육) | 0020 |
| 5 | 점심당번 | 0021~ |
| 6 | 근무표 고르기·보기 전용·링크 규칙·이력 근무표 열 | (작업 본문) |
| 7 | 글씨 크기 3단계·로그인 유지 90일·managers 호환 제거 | 없음 |
| 8 | 도움말·영상·문서 | 없음 |

---

### Task 1: 휴장일(Holiday 표·자동 동기화·관리 화면·표시)

> 검증: 아래 코드를 `feat/boards-phase2` 사본(`git archive HEAD`, 83358c9)에 그대로 넣어 확인했다. 저장소는 고치지 않았다. holidays 는 사본 밖 폴더에 `pip install --target`으로 깔고 `PYTHONPATH`로 읽었다. 결과: `.venv/bin/pytest -W error -q` → **947 passed**(기존 919 + 새 28. 0018 맨 앞 이름 검사와 그 테스트는 일관성 지적 반영으로 옮겨 와 다시 확인), 경고 0개. `makemigrations duty --check --dry-run` → "No changes detected in app 'duty'". 단계별 실패도 사본에서 재현했다(Step 3 `ModuleNotFoundError: No module named 'duty.market_days'`, Step 6 `ImportError: cannot import name 'Holiday'`, Step 10 sync 테스트 3개 AssertionError, Step 15 `NoReverseMatch` 3개, Step 18 표시 테스트 5개 AssertionError). 가짜 데이터(`tools/help_videos/seed.py`) + 확인용 휴장일 하나로 `/?view=month`, `/day/<d>/` 응답에 휴장일 이름이 보이는 것까지 확인했다(seed 의 생성이 sync 를 불러 휴장일 49행이 채워진다).
>
> 이 작업의 범위: 휴장일 **표·채우기·관리 화면·이름 표시**만. `Period.skip_holidays` 칸은 만들지만 아무 도구도 아직 읽지 않는다. 휴장일 건너뛰기(입력 표 잠금·CSV 오류·관제·점심당번 채우기·`missing_dates`·입력 현황, `boards.skip_dates`)와 영업일 기준 알림(`bizdays`)은 뒤 작업이다.
> IT 알림 문구·hash 는 바뀌지 않는다(알림 코드를 건드리지 않는다, `tests/test_alarm_texts_it.py` 그대로 통과).

**Files:**
- Modify: `requirements.in`(끝에 한 줄), `requirements.lock`(`holidays`·`python-dateutil`·`six` 세 줄)
- Create: `duty/market_days.py`
- Modify: `duty/models.py` — `class Period` 의 `board = ...` 줄 뒤(`skip_holidays`), `class PeriodEvent` 바로 앞(`HolidaySource`·`Holiday`)
- Create: `duty/migrations/0018_holidays.py`(손으로 씀: 맨 앞 이름 접미사 검사(`check_names`) → `skip_holidays` 거짓으로 추가 → 같은 파일에서 기본값 참, `Holiday` 생성)
- Create: `duty/services/holidays.py`
- Modify: `duty/services/periods.py`(import, `save_draft` 의 `return period` 앞), `duty/services/generate.py`(import, `run_generation` 상태 검사 뒤)
- Modify: `duty/management/commands/run_worker.py`(머리말, import, `run_round` 의 `jobs` 첫 줄)
- Modify: `duty/admin.py`(models import, `admin.site.unregister(Group)` 앞에 `HolidayAdmin`)
- Modify: `duty/views/roster.py`(services import, `roster()` 의 `by_date` 뒤·`day_info`, `day()` 의 render 컨텍스트)
- Modify: `duty/templates/duty/_daycell.html`(첫 줄 뒤), `duty/templates/duty/day.html`(`</nav>` 뒤), `duty/templates/duty/base.html`(`table.roster .none` 줄 뒤 `.hol`)
- Modify(기대 값 변경: 작업자 작업 목록에 "holidays"가 맨 앞에 생김): `tests/test_ops.py`
- Test: `tests/test_market_days.py`, `tests/test_holidays.py`, `tests/test_migration_holidays.py`, `tests/test_admin_holidays.py`, `tests/test_views_holidays.py`(모두 새 파일)

**Interfaces:**
- Consumes: (1단계 결과) `duty.models.Period`(board FK, start_date, end_date), `duty.perms.today()`, `duty.services.periods.save_draft(period, by=None)`, `duty.services.generate.run_generation(period, seed=None, by=None)`, `run_worker.run_round(now, everything=False, skip_health=False)`, conftest 픽스처 `it_board`·`make_member`·`fixed_today`·`admin_user`
- Produces:
  - 의존성: `holidays==0.108`(+ 하위 의존성 `python-dateutil==2.9.0.post0`, `six==1.17.0`을 lock 에 고정). `requirements.in`: `holidays>=0.108`
  - `duty/market_days.py`(순수, ORM 없음): `YEAR_END = "연말 휴장"`, `holidays_for(year: int) -> dict[date, str]` = `holidays.country_holidays("KR", years=year, language="ko")` + `setdefault(date(year, 12, 31), "연말 휴장")`. **주말 공휴일도 들어 있다**(쓰는 쪽이 평일만 본다). 겹친 공휴일 이름은 라이브러리 그대로 `"부처님오신날; 어린이날"` 모양.
  - `duty.models.HolidaySource(TextChoices)`: `AUTO = "auto"`("자동"), `MANUAL = "manual"`("직접 추가"). `Holiday.Source` 는 별칭.
  - `duty.models.Holiday(date: DateField unique, name: CharField(64), source: CharField(8, choices, default="manual"), active: BooleanField(default=True))`. Meta: `verbose_name = "휴장일"`, `ordering = ["date"]`, 제약 `holiday_source_valid`. `__str__` = `"YYYY-MM-DD 이름"`.
  - `duty.models.Period.skip_holidays: BooleanField("휴장일 건너뛰기", default=True)`. 기존 행은 0018 에서 False.
  - 마이그레이션 `0018_holidays`(의존 `duty.0017_alarmrule_board_rules`). 2단계 첫 마이그레이션이므로 맨 앞에 `RunPython(check_names, noop)` — 이름이 `(휴가)`·`(출장)`·`(교육)`으로 끝나는 계정이 있으면 이름을 알려 주며 `RuntimeError`(설계 10절 2단계, 사유 칸은 Task 4 의 0020 이 더하지만 검사는 여기서 해야 걸려도 2단계 마이그레이션이 하나도 적용되지 않는다. 앱 코드 import 없음). 데이터 이전 없음, 표는 비어 있다. **다음 번호는 0019.**
  - `duty.services.holidays.sync(today: date) -> int`: 범위 = `min(today.year, 가장 이른 Period.start_date 해)` ~ `max(today.year + 1, 가장 늦은 Period.end_date 해)`(회차가 없으면 올해~내년, 모든 근무표·모든 상태의 회차). 그 범위의 표에 없는 날짜만 `source="auto"`로 `bulk_create(ignore_conflicts=True)`. 있는 행(이름·출처·active)은 건드리지 않고 지우지도 않는다. 돌려주는 값 = 넣으려 한 행 수(동시 호출로 무시된 행도 셈).
  - `duty.services.holidays.closed(start: date, end: date) -> dict[date, str]`: start~end(양끝 포함)의 `active=True` 휴장일 `{날짜: 이름}`.
  - 부르는 곳: `periods.save_draft`(저장·기간 정리 **뒤**, `holidays.sync(perms.today())`), `generate.run_generation`(상태 검사 뒤, `missing_dates` 앞), `run_worker.run_round` 맨 앞 작업 `("holidays", lambda t: holidays.sync(timezone.localdate(t)))`(실패는 다른 작업처럼 로그만). 화면 GET 은 부르지 않는다(테스트로 고정).
  - 관리 화면 `HolidayAdmin`: 목록(date·name·source·active, active 바로 고치기, 필터 active·source, 날짜 계층), 추가 폼 = date·name·active(출처는 기본값 manual), 고치기 폼 = date·source 읽기 전용, 지우기 금지.
  - 화면 컨텍스트: `roster()` 의 `day_info` 에 `"holiday": str`(휴장일 이름, 아니면 `""`), `day()` 컨텍스트에 `"holiday": str`. 템플릿 클래스 `.hol`(`<p class="hol">이름</p>`). 월간의 다른 달 날짜(`d.other`)에는 그리지 않는다. 뒤 작업(날 메모 한 줄, "근무 없음" 덮기)은 이 `<p class="hol">` 바로 아래에 붙인다.

- [ ] **Step 1: 의존성을 더하고 개발 PC 에 설치한다**

`requirements.in` 끝에 한 줄:
```
holidays>=0.108  # 휴장일 자동 계산(duty/market_days.py). 한국 공휴일·대체공휴일·선거일·임시공휴일, 오프라인
```

`requirements.lock` — pip-compile·`pip freeze` 로 다시 만들지 않고 정확한 버전 줄만 넣는다(알파벳 순 자리). `holidays` 는 `python-dateutil`(그리고 그것이 `six`)을 요구하므로 세 줄을 함께 고정한다(빠지면 운영 설치에서 버전이 풀린 채 깔린다):
```
gunicorn==26.2.0
holidays==0.108
http_ece==1.2.1
...
pycparser==3.12
python-dateutil==2.9.0.post0
pywebpush==2.5.0
requests==2.34.2
six==1.17.0
sqlparse==0.6.1
```
(`gunicorn`·`http_ece`·`pycparser`·`pywebpush`·`requests`·`sqlparse` 줄은 이미 있다. 새 줄은 `holidays`, `python-dateutil`, `six` 셋.)

Run: `.venv/bin/pip install -r requirements.lock -r requirements-dev.txt && .venv/bin/python -c "import holidays; print(holidays.__version__)"`
Expected: `0.108`

- [ ] **Step 2: market_days 실패 테스트를 쓴다**

`tests/test_market_days.py`(새 파일):
```python
"""휴장일 자동 계산(순수 모듈). 확인 값은 설계 5절(2025~2026)."""
from datetime import date

from duty.market_days import holidays_for


def test_2025_includes_temporary_and_election_days():
    h = holidays_for(2025)
    assert h[date(2025, 1, 27)] == "임시공휴일"
    assert date(2025, 6, 3) in h  # 대통령 선거일
    assert date(2025, 10, 8) in h  # 추석 대체 휴일


def test_2026_includes_labor_day_and_constitution_day():
    h = holidays_for(2026)
    assert date(2026, 5, 1) in h and date(2026, 7, 17) in h
    assert date(2026, 2, 17) in h  # 설날


def test_year_end_is_added_every_year():
    assert holidays_for(2026)[date(2026, 12, 31)] == "연말 휴장"
    assert holidays_for(2031)[date(2031, 12, 31)] == "연말 휴장"


def test_only_that_year_and_no_plain_weekday():
    h = holidays_for(2026)
    assert all(d.year == 2026 for d in h)
    assert date(2026, 11, 16) not in h  # 평범한 월요일
```

- [ ] **Step 3: 실패를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_market_days.py -q`
Expected: 수집 오류 `ModuleNotFoundError: No module named 'duty.market_days'`

- [ ] **Step 4: market_days 를 만든다**

`duty/market_days.py`(새 파일):
```python
"""휴장일 자동 계산(순수 모듈, ORM 없음). 결과는 services/holidays.sync 가 Holiday 표에 넣는다."""
from datetime import date

import holidays

YEAR_END = "연말 휴장"


def holidays_for(year: int) -> dict[date, str]:
    """그해 한국 공휴일(라이브러리 holidays, 대체공휴일·선거일·임시공휴일 포함) + 12/31 '연말 휴장'. 주말도 들어 있다."""
    out = dict(holidays.country_holidays("KR", years=year, language="ko"))
    out.setdefault(date(year, 12, 31), YEAR_END)
    return out
```

Run: `.venv/bin/pytest -W error tests/test_market_days.py -q`
Expected: `4 passed`

- [ ] **Step 5: 모델·마이그레이션·서비스 실패 테스트를 쓴다**

`tests/test_holidays.py`(새 파일. 위쪽 import 는 Step 10 의 테스트까지 쓰는 완성본이다):
```python
"""휴장일 표·자동 채우기와 부르는 곳(설계 5절). 이름은 모두 가상."""
from datetime import date

import pytest
from django.db import IntegrityError, transaction

from duty.errors import DutyError
from duty.models import Commute, Holiday, Period
from duty.services import holidays, periods
from duty.services.generate import run_generation

TODAY = date(2026, 11, 16)


def _years():
    return sorted({d.year for d in Holiday.objects.values_list("date", flat=True)})


def test_source_must_be_known(db):
    with pytest.raises(IntegrityError), transaction.atomic():
        Holiday.objects.create(date=date(2026, 11, 20), name="가짜", source="other")


def test_date_is_unique(db):
    Holiday.objects.create(date=date(2026, 11, 20), name="가짜")
    with pytest.raises(IntegrityError), transaction.atomic():
        Holiday.objects.create(date=date(2026, 11, 20), name="또")


def test_new_period_skips_holidays_by_default(it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 12, 7), end_date=date(2026, 12, 11))
    assert p.skip_holidays is True


def test_sync_without_periods_fills_this_and_next_year(db):
    added = holidays.sync(TODAY)
    assert _years() == [2026, 2027] and added == Holiday.objects.count()
    h = Holiday.objects.get(date=date(2026, 12, 31))
    assert h.name == "연말 휴장" and h.source == "auto" and h.active
    assert Holiday.objects.get(date=date(2027, 1, 1)).source == "auto"


def test_sync_range_follows_oldest_and_latest_period(it_board):
    Period.objects.create(board=it_board, name="옛", start_date=date(2024, 12, 30), end_date=date(2025, 1, 3))
    Period.objects.create(board=it_board, name="먼", start_date=date(2028, 3, 6), end_date=date(2028, 3, 10))
    holidays.sync(TODAY)
    assert _years() == [2024, 2025, 2026, 2027, 2028]


def test_sync_is_idempotent_and_keeps_existing_rows(db):
    Holiday.objects.create(date=date(2026, 12, 25), name="직접 고친 이름", source="manual", active=False)
    Holiday.objects.create(date=date(2026, 11, 20), name="임시 휴장")
    first = holidays.sync(TODAY)
    assert holidays.sync(TODAY) == 0 and Holiday.objects.count() == first + 2
    xmas = Holiday.objects.get(date=date(2026, 12, 25))
    assert (xmas.name, xmas.source, xmas.active) == ("직접 고친 이름", "manual", False)


def test_sync_does_not_delete_dates_gone_from_library(db):
    Holiday.objects.create(date=date(2026, 11, 18), name="옛 자동", source="auto")
    holidays.sync(TODAY)
    assert Holiday.objects.filter(date=date(2026, 11, 18)).exists()


def test_closed_returns_active_only_in_range(db):
    Holiday.objects.create(date=date(2026, 12, 24), name="꺼짐", active=False)
    Holiday.objects.create(date=date(2026, 12, 25), name="성탄")
    Holiday.objects.create(date=date(2027, 1, 1), name="신정")
    assert holidays.closed(date(2026, 12, 21), date(2026, 12, 31)) == {date(2026, 12, 25): "성탄"}
```

`tests/test_migration_holidays.py`(새 파일):
```python
"""0018: 이름이 (휴가)·(출장)·(교육)으로 끝나는 계정이 있으면 아무것도 적용하지 않고 멈춘다.
기존 회차는 휴장일 건너뛰기 거짓, 휴장일 표는 비어 있다(설계 10절 2단계). 이름은 모두 가상."""
from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0017_alarmrule_board_rules")]
AFTER = [("duty", "0018_holidays")]


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_apps():
    apps = _migrate(BEFORE)
    yield apps
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())  # 다른 테스트를 위해 최신 스키마로


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_existing_periods_do_not_skip_holidays(old_apps):
    Board = old_apps.get_model("duty", "Board")
    Group = old_apps.get_model("auth", "Group")
    it = Board.objects.filter(code="it").first() or Board.objects.create(
        code="it", name="IT 당번표", input_mode="collect", admin_group=Group.objects.create(name="IT 근무표 관리"))
    pid = old_apps.get_model("duty", "Period").objects.create(
        board=it, name="옛 회차", start_date=date(2026, 12, 7), end_date=date(2026, 12, 11)).pk

    apps = _migrate(AFTER)
    Period = apps.get_model("duty", "Period")
    assert Period.objects.get(pk=pid).skip_holidays is False
    assert Period.objects.create(board_id=it.pk, name="새 회차", start_date=date(2026, 12, 14),
                                 end_date=date(2026, 12, 18)).skip_holidays is True
    assert not apps.get_model("duty", "Holiday").objects.exists()  # 마이그레이션은 채우지 않는다


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_stops_before_anything_when_name_ends_with_reason(old_apps):
    User = old_apps.get_model("duty", "User")
    u = User.objects.create(username="T001", name="가상일(휴가)")
    User.objects.create(username="T002", name="가상이(A)")  # 괄호가 있어도 사유가 아니면 통과
    with pytest.raises(RuntimeError, match=r"가상일\(휴가\)") as e:
        _migrate(AFTER)
    assert "가상이" not in str(e.value)
    with connection.cursor() as c:  # 0018 이 통째로 되돌려져 표도 칸도 없다
        assert "duty_holiday" not in connection.introspection.table_names(c)
    User.objects.filter(pk=u.pk).delete()  # 정리해야 픽스처가 최신 스키마로 올릴 수 있다
```

- [ ] **Step 6: 실패를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_holidays.py tests/test_migration_holidays.py -q`
Expected: `tests/test_holidays.py` 수집 오류 `ImportError: cannot import name 'Holiday' from 'duty.models'`(마이그레이션 테스트 2개는 0018 이 없어 실패)

- [ ] **Step 7: 모델을 더한다**

`duty/models.py` — `class Period` 안, 지금 코드:
```python
    board = models.ForeignKey(Board, on_delete=models.PROTECT, related_name="periods", verbose_name="근무표")
    # 배포가 지운 행 목록: ["c", 회차 id, 날짜, 멤버 id, 출근조] | ["a", 회차 id, 날짜, 멤버 id, 당번 칸]. 배포 취소 때 되살린다. null = 되돌릴 정보 없음
```
바뀐 코드:
```python
    board = models.ForeignKey(Board, on_delete=models.PROTECT, related_name="periods", verbose_name="근무표")
    # 휴장일 건너뛰기(설계 5절): 근무표를 만드는 도구가 휴장일을 건너뛴다. 2단계 전 회차는 거짓(마이그레이션 0018), 새 회차는 참
    skip_holidays = models.BooleanField("휴장일 건너뛰기", default=True)
    # 배포가 지운 행 목록: ["c", 회차 id, 날짜, 멤버 id, 출근조] | ["a", 회차 id, 날짜, 멤버 id, 당번 칸]. 배포 취소 때 되살린다. null = 되돌릴 정보 없음
```

`duty/models.py` — `class PeriodEvent(models.Model):` 바로 앞에 넣는다:
```python
class HolidaySource(models.TextChoices):
    AUTO = "auto", "자동"
    MANUAL = "manual", "직접 추가"


class Holiday(models.Model):
    """휴장일(모든 근무표 공통, 설계 5절). auto = services/holidays.sync 가 넣은 행, manual = 슈퍼유저가 관리 화면에서 추가.
    sync 는 있는 행을 건드리지 않으므로 끈 자동 휴장일은 꺼진 채 남는다."""
    Source = HolidaySource

    date = models.DateField("날짜", unique=True)
    name = models.CharField("이름", max_length=64)
    source = models.CharField("출처", max_length=8, choices=Source.choices, default=Source.MANUAL)
    active = models.BooleanField("휴장", default=True, help_text="끄면 휴장일이 아닙니다(이미 있는 배정은 그대로).")

    class Meta:
        verbose_name = verbose_name_plural = "휴장일"
        ordering = ["date"]
        constraints = [_one_of("source", HolidaySource.values, "holiday_source_valid")]

    def __str__(self):
        return f"{self.date} {self.name}"


```

- [ ] **Step 8: 마이그레이션을 손으로 쓴다**

`makemigrations` 가 만드는 `AddField(default=True)` 는 기존 회차도 참으로 만든다. 설계 10절대로 거짓으로 추가한 뒤 같은 파일에서 기본값을 참으로 바꾼다. 맨 앞의 이름 검사는 데이터를 바꾸지 않는 확인뿐이라 스키마 파일에 둔다(2단계 첫 파일이어야 걸렸을 때 0018~0020 이 하나도 적용되지 않는다. SQLite 는 마이그레이션 하나를 한 트랜잭션으로 돌리므로 0018 자체도 통째로 되돌려진다).

`duty/migrations/0018_holidays.py`(새 파일):
```python
# 휴장일 표와 회차의 휴장일 건너뛰기(설계 5절·10절 2단계). 표만 만들고 채우지 않는다(라이브러리 버전에 따라 결과가 달라지지 않게,
# 채우기는 services/holidays.sync). 2단계부터 되돌리기는 백업 복원으로만 한다.
# 맨 앞 이름 검사: 2단계 첫 마이그레이션이라 여기서 멈추면 2단계 변경이 하나도 들어가지 않는다(사유 칸은 0020).

from django.db import migrations, models

SUFFIXES = ("(휴가)", "(출장)", "(교육)")


def check_names(apps, schema_editor):
    """표·CSV 의 "이름(휴가)"와 헷갈리는 계정 이름이 있으면 멈춘다(설계 10절 2단계). 앱 코드를 import 하지 않는다."""
    User = apps.get_model("duty", "User")
    taken = sorted(n for n in User.objects.values_list("name", flat=True) if n.endswith(SUFFIXES))
    if taken:
        raise RuntimeError(
            f"이름이 (휴가)·(출장)·(교육)으로 끝나는 계정이 있어 멈춥니다: {', '.join(taken)}. 업그레이드 전 백업으로 롤백한 뒤"
            '(docs/OPERATIONS.md "업그레이드·롤백") 옛 버전 관리 화면에서 그 이름을 바꾸고 업그레이드를 다시 하세요.')


class Migration(migrations.Migration):

    dependencies = [
        ('duty', '0017_alarmrule_board_rules'),
    ]

    operations = [
        migrations.RunPython(check_names, migrations.RunPython.noop),
        # 기존 회차는 거짓(사용자 결정 "다음에 만드는 회차부터"), 그다음 모델 기본값을 참으로(이후 만드는 회차)
        migrations.AddField(
            model_name='period',
            name='skip_holidays',
            field=models.BooleanField(default=False, verbose_name='휴장일 건너뛰기'),
        ),
        migrations.AlterField(
            model_name='period',
            name='skip_holidays',
            field=models.BooleanField(default=True, verbose_name='휴장일 건너뛰기'),
        ),
        migrations.CreateModel(
            name='Holiday',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True, verbose_name='날짜')),
                ('name', models.CharField(max_length=64, verbose_name='이름')),
                ('source', models.CharField(choices=[('auto', '자동'), ('manual', '직접 추가')], default='manual', max_length=8, verbose_name='출처')),
                ('active', models.BooleanField(default=True, help_text='끄면 휴장일이 아닙니다(이미 있는 배정은 그대로).', verbose_name='휴장')),
            ],
            options={
                'verbose_name': '휴장일',
                'verbose_name_plural': '휴장일',
                'ordering': ['date'],
                'constraints': [models.CheckConstraint(condition=models.Q(('source__in', ['auto', 'manual'])), name='holiday_source_valid')],
            },
        ),
    ]
```

Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --check --dry-run`
Expected: `No changes detected in app 'duty'`

- [ ] **Step 9: 서비스를 만들고 통과를 확인한다**

`duty/services/holidays.py`(새 파일):
```python
"""휴장일 표(Holiday) 채우기와 읽기(설계 5절)."""
from datetime import date

from django.db.models import Max, Min

from .. import market_days
from ..models import Holiday, Period


def sync(today: date) -> int:
    """(가장 오래된 회차 시작 해, 올해 중 이른 해) ~ (내년, 가장 늦은 회차 종료 해 중 늦은 해)의 자동 휴장일 중 표에 없는 날짜만 auto 로 넣는다.
    있는 행(사람이 추가·끈 행 포함)은 건드리지 않고, 라이브러리에서 사라진 날짜도 지우지 않는다. 몇 번 불러도 결과가 같다. 넣은 수를 돌려준다."""
    span = Period.objects.aggregate(lo=Min("start_date"), hi=Max("end_date"))
    lo = min(today.year, span["lo"].year) if span["lo"] else today.year
    hi = max(today.year + 1, span["hi"].year) if span["hi"] else today.year + 1
    have = set(Holiday.objects.filter(date__year__gte=lo, date__year__lte=hi).values_list("date", flat=True))
    new = [Holiday(date=d, name=name, source=Holiday.Source.AUTO)
           for y in range(lo, hi + 1) for d, name in sorted(market_days.holidays_for(y).items()) if d not in have]
    Holiday.objects.bulk_create(new, ignore_conflicts=True)  # 작업자와 화면 쓰기가 동시에 불러도 겹치는 날짜는 무시
    return len(new)


def closed(start: date, end: date) -> dict[date, str]:
    """start~end 의 켜진 휴장일 {날짜: 이름}."""
    return dict(Holiday.objects.filter(active=True, date__gte=start, date__lte=end).values_list("date", "name"))
```

Run: `.venv/bin/pytest -W error tests/test_holidays.py tests/test_migration_holidays.py -q`
Expected: `9 passed`

- [ ] **Step 10: 회차 만들기·기간 고치기·생성이 sync 를 부르는 실패 테스트를 쓴다**

`tests/test_holidays.py` 끝에 더한다:
```python


def test_save_draft_syncs_after_saving_so_its_year_is_covered(it_board, fixed_today):
    fixed_today(TODAY)
    periods.save_draft(Period(board=it_board, name="먼", start_date=date(2029, 1, 8), end_date=date(2029, 1, 12)))
    assert _years() == [2026, 2027, 2028, 2029]


def test_editing_dates_syncs(it_board, fixed_today):
    fixed_today(TODAY)
    p = periods.save_draft(Period(board=it_board, name="p", start_date=date(2026, 12, 7), end_date=date(2026, 12, 11)))
    p.end_date = date(2028, 1, 7)
    periods.save_draft(p)
    assert 2028 in _years()


def test_generation_syncs(make_member, it_board, fixed_today):
    fixed_today(TODAY)
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 12, 7), end_date=date(2026, 12, 7),
                              status=Period.Status.CLOSED)
    crew = [(make_member(f"정{i}", dept="MEMS"), "normal") for i in range(5)]  # 관제 10칸을 채울 개발자 10명
    crew += [(make_member(f"석{i}", dept="TMCH"), "dinner") for i in range(5)]
    crew += [(make_member("엠", dept="MD", type="직원"), "normal"), (make_member("유", dept="UI", type="직원"), "normal")]
    for m, shift in crew:
        Commute.objects.create(period=p, date=p.start_date, member=m, shift=shift)
    run_generation(p, seed=1)
    assert _years() == [2026, 2027]


def test_failed_save_draft_adds_nothing(it_board, fixed_today):
    fixed_today(TODAY)
    with pytest.raises(DutyError):
        periods.save_draft(Period(board=it_board, name="주말", start_date=date(2026, 11, 21), end_date=date(2026, 11, 22)))
    assert not Holiday.objects.exists()
```

Run: `.venv/bin/pytest -W error tests/test_holidays.py -q`
Expected: `3 failed, 9 passed` — `test_save_draft_syncs_after_saving_so_its_year_is_covered`·`test_editing_dates_syncs`·`test_generation_syncs` 가 AssertionError(표가 비어 있음). `test_failed_save_draft_adds_nothing` 은 지금도 통과한다(구현 뒤에도 실패한 저장이 휴장일을 남기지 않는지 지키는 테스트).

- [ ] **Step 11: save_draft·run_generation 에서 sync 를 부른다**

`duty/services/periods.py` — 지금 import:
```python
from ..errors import DutyError
from ..models import ChangeLog, Commute, Department, DutyAssignment, Period, PeriodEvent
```
바뀐 import:
```python
from .. import perms
from ..errors import DutyError
from ..models import ChangeLog, Commute, Department, DutyAssignment, Period, PeriodEvent
from . import holidays
```

`save_draft` 끝 — 지금 코드:
```python
    else:  # 되돌아온 회차는 출근표가 있을 수 있다: 줄어든 기간 밖은 지운다
        for model in (Commute, DutyAssignment):
            model.objects.filter(period=period).exclude(date__in=period.dates()).delete()
    return period
```
바뀐 코드:
```python
    else:  # 되돌아온 회차는 출근표가 있을 수 있다: 줄어든 기간 밖은 지운다
        for model in (Commute, DutyAssignment):
            model.objects.filter(period=period).exclude(date__in=period.dates()).delete()
    holidays.sync(perms.today())  # 저장한 뒤: 이 회차의 해가 범위에 들어야 입력 표가 휴장일을 안다
    return period
```

`duty/services/generate.py` — 지금 import:
```python
from ..errors import DutyError
from ..generator import GenerationOutput, generate_control_duty
from ..models import Commute, DutyAssignment, Period, User
from ..shifts import slot_defs
from . import boards
from .periods import missing_dates, record
```
바뀐 import:
```python
from .. import perms
from ..errors import DutyError
from ..generator import GenerationOutput, generate_control_duty
from ..models import Commute, DutyAssignment, Period, User
from ..shifts import slot_defs
from . import boards, holidays
from .periods import missing_dates, record
```

`run_generation` 앞부분 — 지금 코드:
```python
    period.refresh_from_db()
    if period.status not in {S.CLOSED, S.GENERATED}:
        raise DutyError("마감된 회차만 생성할 수 있습니다.")
    missing = missing_dates(period)
```
바뀐 코드:
```python
    period.refresh_from_db()
    if period.status not in {S.CLOSED, S.GENERATED}:
        raise DutyError("마감된 회차만 생성할 수 있습니다.")
    holidays.sync(perms.today())  # 작업자가 꺼져 있어도 휴장일 표가 비어 있지 않게
    missing = missing_dates(period)
```
(`missing_dates`·생성이 휴장일을 건너뛰는 것은 뒤 작업이다. 여기서는 표만 채운다. 둘 다 `@transaction.atomic` 안이라 저장·생성이 실패하면 넣은 휴장일도 함께 되돌아간다.)

Run: `.venv/bin/pytest -W error tests/test_holidays.py -q`
Expected: `12 passed`

- [ ] **Step 12: 작업자 테스트의 기대 값을 바꾼다(실패 확인)**

`tests/test_ops.py` — import, 지금:
```python
from duty.services import alarm_runner, backup, change_notice, health
```
바뀐:
```python
from duty.services import alarm_runner, backup, change_notice, health, holidays
```

`jobs` 픽스처 — 지금:
```python
    monkeypatch.setattr(alarm_runner, "tick", job("alarms", fail=True))
```
바뀐:
```python
    monkeypatch.setattr(holidays, "sync", job("holidays", fail=True))  # 받는 값은 오늘 날짜
    monkeypatch.setattr(alarm_runner, "tick", job("alarms", fail=True))
```

`test_round_isolates_failures` — 지금:
```python
    assert [n for n, _ in jobs] == ["backup", "health", "changes", "alarms"] and all(t == NOW for _, t in jobs)
    assert "worker job failed: alarms" in caplog.text
```
바뀐:
```python
    # 휴장일 채우기는 맨 앞, 실패해도 다른 작업은 돈다
    assert [n for n, _ in jobs] == ["holidays", "backup", "health", "changes", "alarms"]
    assert jobs[0] == ("holidays", timezone.localdate(NOW)) and all(t == NOW for _, t in jobs[1:])
    assert "worker job failed: alarms" in caplog.text and "worker job failed: holidays" in caplog.text
```

`test_once_runs_all_jobs_and_logs_to_file` — 지금:
```python
    assert [n for n, _ in jobs] == ["backup", "health", "changes", "alarms"]  # --once 는 시각과 상관없이 전부
```
바뀐:
```python
    assert [n for n, _ in jobs] == ["holidays", "backup", "health", "changes", "alarms"]  # --once 는 시각과 상관없이 전부
```

`test_loop_skips_health_on_first_round` — 지금:
```python
    assert [n for n, _ in jobs] == ["backup", "changes", "alarms", "backup", "health", "changes", "alarms"]
```
바뀐:
```python
    assert [n for n, _ in jobs] == ["holidays", "backup", "changes", "alarms",
                                    "holidays", "backup", "health", "changes", "alarms"]
```

Run: `.venv/bin/pytest -W error tests/test_ops.py -q -k "round or once_runs or loop_skips"`
Expected: `3 failed`(작업 목록에 "holidays"가 없어 AssertionError)

- [ ] **Step 13: 작업자가 매 바퀴 맨 앞에서 sync 를 부른다**

`duty/management/commands/run_worker.py` — 머리말, 지금:
```python
"""작업자: 웹과 따로 도는 프로세스 하나(deploy/duty-worker.service). 1분마다 한 바퀴.

- DB 백업: 하루 한 번, BACKUP_HOUR 시 이후(backup.daily)
```
바뀐:
```python
"""작업자: 웹과 따로 도는 프로세스 하나(deploy/duty-worker.service). 1분마다 한 바퀴.

- 휴장일 채우기: 매 바퀴 맨 앞(holidays.sync, 없는 날짜만 넣어 가볍다)
- DB 백업: 하루 한 번, BACKUP_HOUR 시 이후(backup.daily)
```

import, 지금:
```python
from duty.services import alarm_runner, backup, change_notice, health
```
바뀐:
```python
from duty.services import alarm_runner, backup, change_notice, health, holidays
```

`run_round` 첫 줄들, 지금:
```python
    # 백업·점검을 먼저: 알림 발송은 건마다 최대 10초라 네트워크가 느리면 오래 걸린다(그동안 백업·점검이 밀리지 않게)
    jobs = [("backup", backup.daily)]
```
바뀐:
```python
    # 백업·점검을 먼저: 알림 발송은 건마다 최대 10초라 네트워크가 느리면 오래 걸린다(그동안 백업·점검이 밀리지 않게)
    # 휴장일이 맨 앞: 영업일 기준 알림·근무표가 읽기 전에 올해·내년 휴장일이 표에 있게
    jobs = [("holidays", lambda t: holidays.sync(timezone.localdate(t))), ("backup", backup.daily)]
```
(lambda 가 호출 때 `holidays.sync` 를 찾으므로 테스트의 monkeypatch 가 먹는다. 실패 격리는 기존 `try/except` + `log.exception("worker job failed: %s", name)` 그대로.)

Run: `.venv/bin/pytest -W error tests/test_ops.py -q`
Expected: `30 passed`

- [ ] **Step 14: 관리 화면 실패 테스트를 쓴다**

`tests/test_admin_holidays.py`(새 파일):
```python
"""관리 화면 "휴장일"(슈퍼유저): 임시공휴일 추가·끄기(설계 5절). 이름은 모두 가상."""
from datetime import date

import pytest
from django.urls import reverse

from duty.models import Holiday


@pytest.fixture
def su_client(client, admin_user):
    admin_user.is_superuser = True
    admin_user.save()
    client.force_login(admin_user)
    return client


def test_admin_adds_manual_holiday(su_client):
    r = su_client.post(reverse("admin:duty_holiday_add"), {"date": "2026-11-20", "name": "임시 휴장", "active": "on"})
    assert r.status_code == 302
    h = Holiday.objects.get(date=date(2026, 11, 20))
    assert (h.name, h.source, h.active) == ("임시 휴장", "manual", True)


def test_admin_turns_off_but_cannot_move_or_delete(su_client):
    h = Holiday.objects.create(date=date(2026, 12, 25), name="성탄", source="auto")
    url = reverse("admin:duty_holiday_change", args=[h.pk])
    body = su_client.get(url).content.decode()
    assert 'name="date"' not in body and 'name="source"' not in body and 'name="active"' in body
    su_client.post(url, {"name": "성탄"})  # 체크 해제 = 끄기
    h.refresh_from_db()
    assert h.active is False and h.source == "auto"
    assert su_client.get(reverse("admin:duty_holiday_delete", args=[h.pk])).status_code == 403


def test_admin_holiday_list_needs_superuser(client, admin_user):
    client.force_login(admin_user)  # 근무표 관리자(스태프)지만 슈퍼유저 아님
    assert client.get(reverse("admin:duty_holiday_changelist")).status_code in (302, 403)
```

- [ ] **Step 15: 실패를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_admin_holidays.py -q`
Expected: `3 failed`(`NoReverseMatch: Reverse for 'duty_holiday_add' not found`)

- [ ] **Step 16: HolidayAdmin 을 등록한다**

`duty/admin.py` — models import, 지금:
```python
from .models import AlarmSettings, Board, BoardShift, Department, GroupKeeper, User
```
바뀐:
```python
from .models import AlarmSettings, Board, BoardShift, Department, GroupKeeper, Holiday, User
```

`admin.site.unregister(Group)  # django.contrib.auth.admin 이 등록한 ...` 줄 바로 앞에 넣는다:
```python
@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    """휴장일(설계 5절): 임시공휴일 추가(직접 추가), 휴장일이 아닌 날은 '휴장'을 끈다. 자동 행은 작업자가 채운다.
    지우기는 막는다(지운 자동 휴장일은 다음 바퀴에 다시 생긴다). 이미 있는 배정은 바뀌지 않는다."""
    list_display = ["date", "name", "source", "active"]
    list_filter = ["active", "source"]
    list_editable = ["active"]
    date_hierarchy = "date"

    def get_fields(self, request, obj=None):
        return ["date", "name", "active"] if obj is None else ["date", "name", "source", "active"]

    def get_readonly_fields(self, request, obj=None):
        return [] if obj is None else ["date", "source"]  # 날짜를 옮기면 자동 행과 겹친다: 끄고 새로 추가한다

    def has_delete_permission(self, request, obj=None):
        return False


```

Run: `.venv/bin/pytest -W error tests/test_admin_holidays.py -q`
Expected: `3 passed`

- [ ] **Step 17: 표시 실패 테스트를 쓴다**

`tests/test_views_holidays.py`(새 파일):
```python
"""휴장일 이름 표시: 날짜 칸 맨 위(주간·월간), 하루 화면(설계 5절·7절). 이름은 모두 가상."""
from datetime import date

import pytest

from duty.models import Commute, Holiday, Period

D = date(2026, 11, 18)  # 수요일


@pytest.fixture
def viewer(client, make_member, fixed_today, it_board):
    fixed_today(D)
    p = Period.objects.create(board=it_board, name="p", start_date=D, end_date=D, status=Period.Status.PUBLISHED,
                              skip_holidays=False)  # 옛 회차: 휴장일 배정도 그대로 보이고 이름만 붙는다
    m = make_member("가", user=True)
    Commute.objects.create(period=p, date=D, member=m, shift="normal")
    Holiday.objects.create(date=D, name="임시 휴장")
    client.force_login(m)
    return client


@pytest.mark.parametrize("url", [f"/?view=week&date={D}", f"/?view=month&date={D}", f"/day/{D}/"])
def test_holiday_name_shown_with_assignments(viewer, url):
    body = viewer.get(url).content.decode()
    assert '<p class="hol">임시 휴장</p>' in body
    assert ">가<" in body  # 배정은 숨기지 않는다


def test_holiday_name_shown_on_day_without_roster(viewer):
    Holiday.objects.create(date=date(2026, 11, 19), name="대체 휴장")
    body = viewer.get(f"/?view=week&date={D}").content.decode()
    assert '<p class="hol">대체 휴장</p>' in body and "근무표 없음" in body


def test_turned_off_holiday_not_shown(viewer):
    Holiday.objects.filter(date=D).update(active=False)
    for url in (f"/?view=week&date={D}", f"/day/{D}/"):
        assert 'class="hol"' not in viewer.get(url).content.decode()


def test_month_view_hides_holiday_of_other_month(viewer):
    Holiday.objects.create(date=date(2026, 11, 30), name="지난달 휴장")  # 12월 달력 첫 줄에 걸린 11월 월요일
    assert "지난달 휴장" not in viewer.get("/?view=month&date=2026-12-02").content.decode()
    assert "지난달 휴장" in viewer.get(f"/?view=month&date={D}").content.decode()


def test_screens_do_not_sync_on_get(viewer):
    viewer.get(f"/?view=month&date={D}")
    viewer.get(f"/day/{D}/")
    assert Holiday.objects.count() == 1  # 화면을 여는 것으로는 휴장일을 채우지 않는다
```

- [ ] **Step 18: 실패를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_views_holidays.py -q`
Expected: `5 failed, 2 passed` — `test_holiday_name_shown_with_assignments` 3개·`test_holiday_name_shown_on_day_without_roster`·`test_month_view_hides_holiday_of_other_month` 가 AssertionError(휴장일 이름이 화면에 없음). `test_turned_off_holiday_not_shown`·`test_screens_do_not_sync_on_get` 은 지금도 통과(구현 뒤 회귀 방지).(parametrize 3개 포함 7개 실행.)

- [ ] **Step 19: 뷰·템플릿에 휴장일 이름을 넣는다**

`duty/views/roster.py` — services import, 지금:
```python
from ..services import boards, changes, prefs
```
바뀐:
```python
from ..services import boards, changes, holidays, prefs
```

`roster()` — 지금 코드:
```python
    first_day, last_day = weeks[0][0], weeks[-1][-1]
    by_date = {d.date: d for d in published_days(board, first_day, last_day)}
```
바뀐 코드:
```python
    first_day, last_day = weeks[0][0], weeks[-1][-1]
    by_date = {d.date: d for d in published_days(board, first_day, last_day)}
    closed = holidays.closed(first_day, last_day)  # 휴장일 이름은 회차·배정과 상관없이 칸 맨 위에
```

`roster()` 안 `day_info` — 지금 코드:
```python
            "date": d, "is_today": d == today, "other": other, "empty": d not in by_date,
```
바뀐 코드:
```python
            "date": d, "is_today": d == today, "other": other, "empty": d not in by_date, "holiday": closed.get(d, ""),
```

`day()` 의 render — 지금 코드:
```python
    return render(request, "duty/day.html", {
        "d": d, "weekday": DAY_LABELS[d.weekday()], "found": found, "sections": sections,
        "editable": editable, "prev": _neighbor(d, -1), "next_day": _neighbor(d, 1),
```
바뀐 코드:
```python
    return render(request, "duty/day.html", {
        "d": d, "weekday": DAY_LABELS[d.weekday()], "found": found, "sections": sections,
        "holiday": holidays.closed(d, d).get(d, ""),
        "editable": editable, "prev": _neighbor(d, -1), "next_day": _neighbor(d, 1),
```

`duty/templates/duty/_daycell.html` — 첫 줄(날짜 링크) 바로 뒤에 한 줄:
```django
<a href="{% url 'day' d.date %}"><strong>{% if view == "week" %}{{ d.date.month }}/{{ d.date.day }}{% else %}{{ d.date.day }}{% endif %}</strong></a>
{% if d.holiday and not d.other %}<p class="hol">{{ d.holiday }}</p>{% endif %}
{% if d.empty and not d.other %}<p class="none">근무표 없음</p>{% elif not d.other %}
```
(첫 줄과 셋째 줄은 지금 그대로, 가운데 줄만 새로.)

`duty/templates/duty/day.html` — 지금:
```django
</nav>
<form method="get" class="search">
```
바뀐:
```django
</nav>
{% if holiday %}<p class="hol">{{ holiday }}</p>{% endif %}
<form method="get" class="search">
```

`duty/templates/duty/base.html` — 지금:
```css
    table.roster .none { margin: .5rem 0 0; font-size: .8rem; opacity: .5; }
```
바뀐(한 줄 추가, 색은 기존 토큰 `--nxt-red` 라 라이트·다크 모두 정의돼 있다):
```css
    table.roster .none { margin: .5rem 0 0; font-size: .8rem; opacity: .5; }
    .hol { margin: .2rem 0 0; font-weight: 700; color: var(--nxt-red); }  /* 휴장일 이름: 날짜 칸 맨 위·하루 화면 제목 아래 */
```

Run: `.venv/bin/pytest -W error tests/test_views_holidays.py -q`
Expected: `7 passed`

- [ ] **Step 20: 전체 테스트**

Run: `.venv/bin/pytest -W error -q`
Expected: `947 passed`(919 + 새 28: market_days 4, holidays 12, 마이그레이션 2, 관리 화면 3, 표시 7), 경고 0개. `tests/test_alarm_texts_it.py` 가 그대로 통과(IT 알림 문구·hash 불변).

Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --check --dry-run`
Expected: `No changes detected in app 'duty'`

- [ ] **Step 21: 브라우저로 확인한다(CLAUDE.md, PC 1400px·모바일 390px)**

`config.test_settings` 로 띄워 실명 DB 를 열지 않는다(프로세스마다 빈 임시 DATA_DIR). migrate·가짜 데이터·확인용 휴장일·서버를 한 프로세스에서 돌리고, 스크립트는 저장소 밖 임시 폴더에 둔다. seed.py 의 생성(`run_generation`)이 sync 를 불러 휴장일 표가 채워진다.

```bash
W=$(mktemp -d)
cat > $W/serve.py <<'EOF'
"""브라우저 확인용: 임시 DATA_DIR(test_settings)에 가짜 데이터 + 확인용 휴장일을 넣고 같은 프로세스에서 서버를 띄운다."""
import sys
from datetime import timedelta

import django

django.setup()
from django.core.management import call_command  # noqa: E402

call_command("migrate", verbosity=0)
exec(open("tools/help_videos/seed.py", encoding="utf-8").read())
from duty import perms  # noqa: E402
from duty.models import Holiday  # noqa: E402

d = perms.today()
while d.weekday() >= 5:
    d += timedelta(days=1)
Holiday.objects.update_or_create(date=d, defaults={"name": "임시 휴장(확인용)", "active": True})
print("확인용 휴장일:", d)
call_command("runserver", sys.argv[1], use_reloader=False)
EOF
DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. .venv/bin/python $W/serve.py 127.0.0.1:8795 &
# 확인이 끝나면: kill %1; rm -rf $W   (DB 는 임시 DATA_DIR 이라 프로세스와 함께 사라진다)
```

계정 `member`·`admin`(비밀번호 `Demo-pass-123`). PC 1400px·모바일 390px 에서:
- `/?view=week&date=<확인용 날짜>`: 그날 칸 맨 위(날짜 아래) 굵은 빨간 "임시 휴장(확인용)", 배정은 그대로 아래에 보인다. 390px 세로 쌓기에서도 날짜 바로 아래.
- `/?view=month&date=<확인용 날짜>`: 같은 칸 맨 위. 이름이 길어도 칸 폭 안에서 줄바꿈된다. 다른 달 날짜(흐린 칸)에는 없다.
- `/?view=month&date=2026-12-01`: 12/25 "기독탄신일", 12/31 "연말 휴장"(자동 채우기 결과).
- `/day/<확인용 날짜>/`: 날짜 이동 줄 아래 한 줄.
- admin 으로 `/admin/duty/holiday/`: 목록·"휴장" 체크 바로 끄기, 추가 폼(날짜·이름·휴장), 기존 행 고치기에서 날짜·출처는 글자, 지우기 버튼 없음. 끈 뒤 근무표에서 이름이 사라지는지.
- 라이트·다크 모드 둘 다 글자가 읽히는지.

- [ ] **Step 22: 커밋한다**

```bash
git add requirements.in requirements.lock duty/market_days.py duty/models.py duty/migrations/0018_holidays.py \
        duty/services/holidays.py duty/services/periods.py duty/services/generate.py \
        duty/management/commands/run_worker.py duty/admin.py duty/views/roster.py \
        duty/templates/duty/_daycell.html duty/templates/duty/day.html duty/templates/duty/base.html \
        tests/test_market_days.py tests/test_holidays.py tests/test_migration_holidays.py \
        tests/test_admin_holidays.py tests/test_views_holidays.py tests/test_ops.py
git commit -m "feat: 휴장일 표·자동 채우기(작업자·회차 저장·생성)·관리 화면, 날짜 칸에 휴장일 이름"
```
(커밋 메시지 끝에 세션의 Co-Authored-By·Claude-Session 줄을 붙인다.)

**뒤 작업이 알아야 할 점**
- 다음 마이그레이션 번호는 **0019**(의존 `duty.0018_holidays`).
- 이름 접미사 검사(`check_names`, `(휴가)`·`(출장)`·`(교육)`)는 0018 맨 앞에 있고 `tests/test_migration_holidays.py::test_stops_before_anything_when_name_ends_with_reason` 가 고정한다. Task 4 의 `0020_reasons` 는 스키마(AddField·AddConstraint)만 두고 `RunPython` 을 넣지 않는다. `tests/test_migration_reasons.py` 의 멈춤 테스트는 여기로 옮겨졌으므로 두지 않는다(남기려면 BEFORE·AFTER 를 0017→0018 로).
- 휴장일 건너뛰기는 아직 아무 데도 없다. `Period.skip_holidays` 는 칸만 있고(새 회차 참, 기존 회차 거짓), 입력 표·CSV·채우기·관제·점심당번·`missing_dates`·입력 현황·`bizdays` 는 뒤 작업이 `holidays.closed(...)`(또는 `boards.skip_dates(period)`)로 읽는다. 휴장일 판단은 언제나 `closed`(= `active=True`)를 쓴다. `Holiday.objects` 를 직접 거르지 않는다.
- `market_days.holidays_for` 는 주말도 돌려주고 `closed` 도 주말을 걸러내지 않는다. 평일만 필요하면 쓰는 쪽에서 `weekdays`/`period.dates()` 와 교집합을 낸다.
- sync 는 `save_draft`(새 회차·기간 수정)와 `run_generation` 안에서 이미 불린다. 3단계 direct 회차의 확정이 `run_generation` 을 쓰면 따로 부를 필요가 없다. 화면 GET 에서는 부르지 않는다(`tests/test_views_holidays.py::test_screens_do_not_sync_on_get`).
- 화면: 날짜 칸의 휴장일 줄은 `_daycell.html` 둘째 줄 `<p class="hol">`. 날 메모 한 줄·"근무 없음" 덮기는 이 줄 바로 아래에 붙이고 같은 `.hol` 모양을 재사용할 수 있다. `day_info["holiday"]`·`day` 컨텍스트 `holiday` 는 문자열(아니면 `""`).
- `tests/test_ops.py` 의 `jobs` 픽스처가 이제 `holidays.sync` 도 가로챈다. 작업자 작업을 더하는 뒤 작업은 기대 목록 맨 앞에 `"holidays"` 가 있는 것을 전제로 고친다.
- 기존 테스트 중 `save_draft`·`run_generation` 을 부르는 것들은 이제 holidays 라이브러리로 휴장일 표를 채운다(오프라인, 테스트 전체 시간 차이 1초 안쪽). 휴장일 행 수를 0으로 가정하는 새 테스트는 sync 를 거치지 않는 길(`Period.objects.create`)로 회차를 만든다.
- 문서(ARCHITECTURE.md 휴장일·작업자 순서, OPERATIONS.md "휴장일" 관리 화면 사용법과 업그레이드 때 라이브러리 버전 올리기, PRINCIPLES.md 결정 기록 "휴장일 = DB 표")는 2단계 문서 작업이 이 Task 의 동작대로 쓴다.


---

### Task 2: 메모(날·주·달)와 근무 없음

> 검증: Task 1 을 넣은 `feat/boards-phase2` 사본(83358c9 + Task 1, 946 passed)에 아래 코드를 그대로 넣어 확인했다. 저장소는 고치지 않았다. 결과: `.venv/bin/pytest -W error -q` → **980 passed**(946 + 새 34), 경고 0개. `makemigrations duty --check --dry-run` → "No changes detected in app 'duty'". 단계별 실패도 사본에서 하나씩 재현했다(Step 2 `ImportError: cannot import name 'Memo'`, Step 6 `ImportError: cannot import name 'memos' from 'duty.services'`, Step 9 2 failed(`DID NOT RAISE DutyError`, `assert 2 == 1`), Step 12 16 failed·1 passed — 통과한 하나는 `test_popup_requires_admin` 으로, 주소가 없어도 404 라서 미리 통과한다). 가짜 데이터(`tools/help_videos/seed.py`) + 메모 4개로 그린 화면을 headless Chrome 으로 1400·390px 캡처해 확인했다(주간·월간·하루 화면, 관리자·일반 멤버).
>
> 이 작업의 범위: `Memo` 표, `services/memos`(저장·정규화·지우기·근무 없음으로 배정 지우기·읽기), 근무 없음 날 근무 변경 막기, 배포 취소 때 근무 없음 날짜 행 빼기(`UnpublishInfo.restored_rows` 포함), 화면(날 메모 한 줄·근무 없음 칸 덮기·주 메모·달 메모·관리 그룹만 [메모] 팝업).
> 하지 않는 것(뒤 작업): 배포 전 회차 도구의 근무 없음 건너뛰기(입력 표 행 잠금·CSV 오류·채우기·생성·`missing_dates`·입력 현황 = `boards.skip_dates(period)`), 근무표 고르기에 따른 `?board=` 링크, 문서.
> IT 알림 문구·hash 는 바뀌지 않는다(알림 코드를 건드리지 않는다, `tests/test_alarm_texts_it.py` 그대로 통과). 근무 없음으로 지운 배정은 보통 근무 변경과 같은 `ChangeLog`(빼기)라 변경 알림이 평소 길로 나간다.

**Files:**
- Modify: `duty/models.py` — import 두 줄(`from django.db.models import Q` 줄), `class Holiday` 끝과 `class PeriodEvent` 사이(`_strftime`·`MemoScope`·`Memo`)
- Create: `duty/migrations/0019_memo.py`(makemigrations 가 만든 그대로)
- Create: `duty/services/memos.py`
- Modify: `duty/services/changes.py`(import, `_owner`)
- Modify: `duty/services/publish.py`(import, `unpublish_info` 의 마지막 return, 새 `_restorable`, `unpublish` 의 `undo = ...`)
- Modify: `duty/views/roster.py`(import 두 줄, `roster()` 의 `closed = ...` 뒤·`day_info`·`days` 뒤·`ctx.update`, `day()`, 새 `memo` 뷰)
- Modify: `duty/urls.py`(`cell` 줄 뒤)
- Create: `duty/templates/duty/_memo_form.html`, `duty/templates/duty/_memo.html`
- Modify: `duty/templates/duty/_daycell.html`(1~3줄), `duty/templates/duty/roster.html`(표 위·주 행 뒤·표 아래), `duty/templates/duty/day.html`(휴장일 줄 뒤·"배포된 근무표에 없는" 줄), `duty/templates/duty/base.html`(`.hol` 줄 뒤)
- Test: `tests/test_memo_model.py`, `tests/test_memos.py`, `tests/test_memo_guards.py`, `tests/test_views_memos.py`(모두 새 파일. 기존 테스트는 고치지 않는다)

**Interfaces:**
- Consumes: (1단계) `duty.models.Board`·`Period`·`Commute`·`DutyAssignment`·`ChangeLog`, `duty.perms.is_board_admin(user, board)`·`perms.today()`·`perms.can_edit(user, board, d)`, `duty.services.boards.owner(board, d)`, `changes._owner(board, d)`(`change_cell`·`exchange`·`swap` 이 모두 거친다), `publish.unpublish_info(period)`·`unpublish(period, by=None)`, 뷰 `views/roster._board(user)`·`safe_next`, conftest `it_board`·`make_member`·`admin_user`·`admin_client_ok`·`fixed_today`. (Task 1) 마이그레이션 `0018_holidays`, `day_info["holiday"]`·`_daycell.html` 의 `<p class="hol">`·`base.html` 의 `.hol`.
- Produces:
  - `duty.models.MemoScope(TextChoices)`: `DAY="day"`("날"), `WEEK="week"`("주"), `MONTH="month"`("달"). `Memo.Scope` 는 별칭.
  - `duty.models.Memo(board: FK(Board, PROTECT, related_name="memos"), scope: CharField(8, choices), date: DateField, text: CharField(500, blank=True), no_work: BooleanField(default=False))`. 제약: `memo_one_per_date`(board, scope, date unique), `memo_scope_valid`, `memo_no_work_day_only`(no_work 는 day 만), `memo_not_empty`(no_work 이거나 text 가 비지 않음), `memo_date_aligned`(week 는 월요일, month 는 1일. SQLite 내장 `strftime` 으로 써서 sqlite3 셸에서도 CHECK 가 돈다). verbose_name "메모". 관리 화면 등록 없음.
  - 마이그레이션 `0019_memo`(의존 `duty.0018_holidays`, 표 만들기만). **다음 번호는 0020.**
  - `duty.services.memos`(DB 를 바꾸는 규칙은 여기만):
    - 상수 `DAY, WEEK, MONTH`(= `Memo.Scope.*`), `MAX_TEXT = 500`
    - `normalize(scope: str, d: date) -> date`: week → 그 주 월요일, month → 그 달 1일, day → 그대로, 그 밖 → `DutyError`
    - `save(user, board, scope: str, d: date, text: str, no_work: bool = False, confirm: bool = False) -> int`: 관리 그룹만(`PermissionDenied("메모는 근무표 관리자만 고칠 수 있습니다.")`). 날짜를 맞추고 글 앞뒤 공백을 뗀다. 글이 비고 no_work 도 아니면 `delete`. no_work 는 day 만(`DutyError`), 500자 넘으면 `DutyError`. no_work 이고 그날 배정이 있으면 `confirm=True` 여야 한다(아니면 `DutyError("{n}명의 근무가 지워집니다. 확인하고 다시 저장해 주세요.")`). 돌려주는 값 = 지운 근무의 사람 수(0 = 지운 것 없음).
    - no_work 저장 때 지우는 것: 그날 **그 근무표의 모든 회차**의 `Commute`·`DutyAssignment`. 배포 회차(= 그날의 주인) 행마다 `ChangeLog(by=user, cell=그 칸, before=그 사람, after=None)` 를 남긴다(근무조 먼저, 그다음 당번, 각각 id 순). 배포 전 회차의 행은 기록 없이 지운다(근무 없음 날은 늘 비어 있다).
    - `delete(user, board, scope, d) -> None`: 관리 그룹만. 근무 없음 날이었으면 빈 날이 된다(되살리지 않는다)
    - `affected(board, d) -> int`: 근무 없음으로 저장하면 근무가 지워지는 사람 수(확인창용, 모든 회차)
    - `no_work_days(board, start, end) -> set[date]`: 그 근무표의 근무 없음 날(양끝 포함)
    - `for_range(board, start, end) -> dict[str, dict[date, Memo]]`: `{"day": {날짜: Memo}, "week": {월요일: Memo}, "month": {1일: Memo}}`. day 는 start~end, week·month 는 start 가 걸친 주·달부터 end 까지
  - `changes._owner(board, d)`: 주인을 찾은 **뒤** 그날이 근무 없음이면 `DutyError("근무 없는 날입니다.")`. `change_cell`·`exchange`·`swap`(뒤 작업의 `set_reason` 도 `_owner` 를 쓰면) 모두 막힌다. 휴장일은 막지 않는다.
  - `publish._restorable(period) -> list`: `period.publish_undo` 에서 그 근무표 근무 없음 날짜(`r[2]`, iso 문자열) 행을 뺀 목록. `unpublish` 와 `unpublish_info(...).restored_rows` 가 쓴다. 행 모양(5칸·6칸)과 무관하게 `r[2]` 만 본다.
  - 화면:
    - URL `memo/<str:scope>/<isodate:d>/`(name `"memo"`), 뷰 `views/roster.memo(request, scope, d)`. 근무표 = `_board(request.user)`. 관리 그룹이 아니거나 scope 가 틀리면 404. GET = 팝업 조각 `_memo_form.html`(컨텍스트 `scope`·`d`(맞춘 날짜)·`memo`(Memo 또는 None)·`next`·`title`·`affected`). POST 필드 `text`, `no_work`("1"), `confirm`("1"), `delete`("1"), `next` → `safe_next` 로 되돌아간다. 성공 메시지 "메모를 저장했습니다."(+ " {n}명의 근무를 지웠습니다.") / "메모를 지웠습니다.", 오류는 messages.error.
    - `roster()` 의 `day_info` 에 `"memo": str`(날 메모 글, 없으면 `""`), `"no_work": bool`, `"week_memo": Memo | None`(월요일 칸에만 값이 있다 → 템플릿은 `week.0.week_memo`), `"edit"` 은 근무 없음 날 거짓. 컨텍스트 `memo_admin: bool`(`is_board_admin`), `month_memos: list[{"date": 1일, "memo": Memo | None}]`(월간 = 그 달, 주간 = 그 주가 걸친 달 1~2개).
    - `day()` 컨텍스트 `note: Memo | None`, `memo_admin: bool`. 근무 없음 날은 `sections=[]`, `editable=False`.
    - 템플릿 클래스: `.memo`(날 메모 한 줄, `.hol` 바로 아래), `.nowork`(근무 없음 덮기, 글이 비면 "근무 없음"), `.memo-btn`([메모] 링크), `.memo-note`(주·달 메모 줄, `_memo.html`), `tr.wmemo`(월간 주 메모 행). 메모 글은 `linebreaksbr`(이스케이프됨).

- [ ] **Step 1: Memo 모델 제약 테스트를 먼저 쓴다**

`tests/test_memo_model.py`(새 파일):
```python
"""Memo 모델 제약(설계 4.8). 서비스를 거치지 않은 쓰기도 DB 가 막는다."""
from datetime import date

import pytest
from django.db import IntegrityError, transaction

from duty.models import Memo

D = date(2026, 11, 18)  # 수요일


# ── 모델 제약 ──

def _bad(**kw):
    with pytest.raises(IntegrityError), transaction.atomic():
        Memo.objects.create(**kw)


def test_constraints(it_board):
    _bad(board=it_board, scope="year", date=D, text="x")
    _bad(board=it_board, scope="week", date=D, text="x")  # 수요일
    _bad(board=it_board, scope="month", date=D, text="x")  # 18일
    _bad(board=it_board, scope="week", date=date(2026, 11, 16), text="x", no_work=True)  # 근무 없음은 날 메모만
    _bad(board=it_board, scope="day", date=D, text="")  # 빈 메모
    Memo.objects.create(board=it_board, scope="week", date=date(2026, 11, 16), text="x")
    Memo.objects.create(board=it_board, scope="month", date=date(2026, 11, 1), text="x")
    Memo.objects.create(board=it_board, scope="day", date=D, text="", no_work=True)
    _bad(board=it_board, scope="day", date=D, text="또")  # (근무표, 범위, 날짜)에 하나
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_memo_model.py -q`
Expected: 수집 오류 `ImportError: cannot import name 'Memo' from 'duty.models'`

- [ ] **Step 3: Memo 모델과 마이그레이션을 만든다**

`duty/models.py` 위쪽 import:
```python
from django.db.models import Q
```
를 다음으로 바꾼다:
```python
from django.db.models import F, Func, Q, Value
from django.db.models.lookups import Exact
```

`class Holiday` 의 `__str__` 뒤, `class PeriodEvent(models.Model):` 바로 앞에 넣는다(앞뒤 빈 줄 두 줄):
```python
def _strftime(fmt: str):
    """SQLite strftime(fmt, date). %w: 일요일 0 … 월요일 1, %d: 01~31."""
    return Func(Value(fmt), F("date"), function="strftime", output_field=models.CharField())


class MemoScope(models.TextChoices):
    DAY = "day", "날"
    WEEK = "week", "주"
    MONTH = "month", "달"


class Memo(models.Model):
    """메모(설계 4.8·6.5): 회차가 아니라 (근무표, 날짜)에 붙는다. week = 그 주 월요일, month = 그 달 1일에 저장한다.
    no_work(근무 없음)는 날 메모에만: 그날은 배정이 늘 비어 있고 근무 변경을 막는다(services/memos.save 가 배정을 지운다)."""
    Scope = MemoScope

    board = models.ForeignKey(Board, on_delete=models.PROTECT, related_name="memos", verbose_name="근무표")
    scope = models.CharField("범위", max_length=8, choices=Scope.choices)
    date = models.DateField("날짜")
    text = models.CharField("내용", max_length=500, blank=True)
    no_work = models.BooleanField("근무 없음", default=False)

    class Meta:
        verbose_name = verbose_name_plural = "메모"
        constraints = [
            models.UniqueConstraint(fields=["board", "scope", "date"], name="memo_one_per_date"),
            _one_of("scope", MemoScope.values, "memo_scope_valid"),
            models.CheckConstraint(name="memo_no_work_day_only", condition=Q(no_work=False) | Q(scope="day")),
            models.CheckConstraint(name="memo_not_empty", condition=Q(no_work=True) | ~Q(text="")),
            # 주 메모는 월요일, 달 메모는 1일에만(서비스가 맞춰 저장한다). __week_day 같은 lookup 은 Django 가 연결마다
            # 등록하는 함수(django_date_extract)를 CHECK 에 넣어 sqlite3 셸에서 쓰기가 깨지므로 SQLite 내장 strftime 으로
            models.CheckConstraint(name="memo_date_aligned", condition=(
                Q(scope="day") | Q(Exact(_strftime("%w"), "1"), scope="week") | Q(Exact(_strftime("%d"), "01"), scope="month"))),
        ]
```

마이그레이션은 손으로 쓰지 않고 만든다:

Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty -n memo`
Expected: `duty/migrations/0019_memo.py` + "Create model Memo". 내용은 아래와 같아야 한다(머리 주석의 날짜·시각만 다를 수 있다):
```python
# Generated by Django 5.2.19 on 2026-11-15 13:20

import django.db.models.deletion
import django.db.models.lookups
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('duty', '0018_holidays'),
    ]

    operations = [
        migrations.CreateModel(
            name='Memo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scope', models.CharField(choices=[('day', '날'), ('week', '주'), ('month', '달')], max_length=8, verbose_name='범위')),
                ('date', models.DateField(verbose_name='날짜')),
                ('text', models.CharField(blank=True, max_length=500, verbose_name='내용')),
                ('no_work', models.BooleanField(default=False, verbose_name='근무 없음')),
                ('board', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='memos', to='duty.board', verbose_name='근무표')),
            ],
            options={
                'verbose_name': '메모',
                'verbose_name_plural': '메모',
                'constraints': [models.UniqueConstraint(fields=('board', 'scope', 'date'), name='memo_one_per_date'), models.CheckConstraint(condition=models.Q(('scope__in', ['day', 'week', 'month'])), name='memo_scope_valid'), models.CheckConstraint(condition=models.Q(('no_work', False), ('scope', 'day'), _connector='OR'), name='memo_no_work_day_only'), models.CheckConstraint(condition=models.Q(('no_work', True), models.Q(('text', ''), _negated=True), _connector='OR'), name='memo_not_empty'), models.CheckConstraint(condition=models.Q(('scope', 'day'), models.Q(django.db.models.lookups.Exact(models.Func(models.Value('%w'), models.F('date'), function='strftime', output_field=models.CharField()), '1'), ('scope', 'week')), models.Q(django.db.models.lookups.Exact(models.Func(models.Value('%d'), models.F('date'), function='strftime', output_field=models.CharField()), '01'), ('scope', 'month')), _connector='OR'), name='memo_date_aligned')],
            },
        ),
    ]
```

CHECK 가 Django 함수가 아니라 SQLite 내장 함수로 들어갔는지 본다:

Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py sqlmigrate duty 0019 | grep -o 'CONSTRAINT "memo_date_aligned".*'`
Expected: `CONSTRAINT "memo_date_aligned" CHECK (("scope" = 'day' OR (strftime('%w', "date") = '1' AND "scope" = 'week') OR (strftime('%d', "date") = '01' AND "scope" = 'month'))));` (`django_date_extract` 가 없어야 한다)

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_memo_model.py -q && DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --check --dry-run`
Expected: `1 passed`, `No changes detected in app 'duty'`

- [ ] **Step 5: 메모 서비스 테스트를 쓴다**

`tests/test_memos.py`(새 파일):
```python
"""메모(날·주·달)와 근무 없음(설계 4.8·6.5). 이름은 모두 가상."""
from datetime import date

import pytest
from django.core.exceptions import PermissionDenied

from duty.errors import DutyError
from duty.models import Board, ChangeLog, Commute, DutyAssignment, Memo, Period
from duty.services import memos

S = Period.Status
D = date(2026, 11, 18)  # 수요일


@pytest.fixture
def world(make_member, admin_user, fixed_today, it_board):
    fixed_today(date(2026, 11, 16))
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 16), end_date=date(2026, 11, 20),
                              status=S.PUBLISHED, overwrite_from=date(2026, 11, 16))
    m = {n: make_member(n, user=True) for n in ["가", "나", "다"]}
    Commute.objects.create(period=p, date=D, member=m["가"], shift="dawn")
    Commute.objects.create(period=p, date=D, member=m["나"], shift="normal")
    DutyAssignment.objects.create(period=p, date=D, cell="slot0", member=m["가"])
    Commute.objects.create(period=p, date=date(2026, 11, 19), member=m["다"], shift="normal")
    return p, m


# ── 저장·정규화·권한 ──

def test_save_normalizes_week_and_month(admin_user, it_board):
    memos.save(admin_user, it_board, "week", D, "  주말 근무: 가  ")
    memos.save(admin_user, it_board, "month", D, "본부 점심: 나")
    assert Memo.objects.get(scope="week").date == date(2026, 11, 16)
    assert Memo.objects.get(scope="week").text == "주말 근무: 가"
    assert Memo.objects.get(scope="month").date == date(2026, 11, 1)
    memos.save(admin_user, it_board, "week", date(2026, 11, 20), "고침")  # 같은 주 다른 날 = 같은 메모
    assert Memo.objects.filter(scope="week").count() == 1 and Memo.objects.get(scope="week").text == "고침"


def test_empty_text_deletes(admin_user, it_board):
    memos.save(admin_user, it_board, "day", D, "행사")
    memos.save(admin_user, it_board, "day", D, "  ")
    assert not Memo.objects.exists()


def test_no_work_only_for_day(admin_user, it_board):
    with pytest.raises(DutyError, match="날 메모"):
        memos.save(admin_user, it_board, "week", D, "x", no_work=True)


def test_too_long_rejected(admin_user, it_board):
    with pytest.raises(DutyError, match="500"):
        memos.save(admin_user, it_board, "day", D, "가" * 501)


def test_only_board_admin(world, it_board):
    _, m = world
    with pytest.raises(PermissionDenied):
        memos.save(m["가"], it_board, "day", D, "x")
    Memo.objects.create(board=it_board, scope="day", date=D, text="x")
    with pytest.raises(PermissionDenied):
        memos.delete(m["가"], it_board, "day", D)
    assert Memo.objects.exists()


def test_admin_of_other_board_cannot_edit(admin_user):
    other = Board.objects.create(code="ops", name="운영팀")
    with pytest.raises(PermissionDenied):
        memos.save(admin_user, other, "day", D, "x")


# ── 근무 없음: 배정 지우기 ──

def test_no_work_needs_confirm_when_people_assigned(world, admin_user, it_board):
    assert memos.affected(it_board, D) == 2
    with pytest.raises(DutyError, match="2명의 근무가 지워집니다"):
        memos.save(admin_user, it_board, "day", D, "임시 휴무", no_work=True)
    assert not Memo.objects.exists() and Commute.objects.filter(date=D).count() == 2


def test_no_work_clears_day_and_logs_each_row(world, admin_user, it_board):
    p, m = world
    assert memos.save(admin_user, it_board, "day", D, "임시 휴무", no_work=True, confirm=True) == 2
    assert not Commute.objects.filter(date=D).exists() and not DutyAssignment.objects.filter(date=D).exists()
    logs = list(ChangeLog.objects.order_by("id").values_list("period_id", "date", "cell", "before__name", "after", "by"))
    assert logs == [(p.pk, D, "dawn", "가", None, admin_user.pk), (p.pk, D, "normal", "나", None, admin_user.pk),
                    (p.pk, D, "slot0", "가", None, admin_user.pk)]
    assert Commute.objects.filter(date=date(2026, 11, 19)).count() == 1  # 다른 날은 그대로
    assert not ChangeLog.objects.filter(notified=True).exists()  # 변경 알림은 작업자가 평소처럼 보낸다


def test_no_work_clears_unpublished_rows_without_log(world, admin_user, it_board, make_member):
    q = Period.objects.create(board=it_board, name="q", start_date=D, end_date=D, status=S.COLLECTING)
    Commute.objects.create(period=q, date=D, member=world[1]["다"], shift="night")
    assert memos.affected(it_board, D) == 3
    memos.save(admin_user, it_board, "day", D, "", no_work=True, confirm=True)
    assert not Commute.objects.filter(period=q).exists()
    assert not ChangeLog.objects.filter(period=q).exists()


def test_no_work_does_not_touch_other_board(world, admin_user, it_board):
    other = Board.objects.create(code="ops", name="운영팀")
    o = Period.objects.create(board=other, name="o", start_date=D, end_date=D, status=S.PUBLISHED)
    Commute.objects.create(period=o, date=D, member=world[1]["다"], shift="normal")
    memos.save(admin_user, it_board, "day", D, "", no_work=True, confirm=True)
    assert Commute.objects.filter(period=o).exists()


def test_past_day_no_work_by_admin(world, admin_user, it_board, fixed_today):
    fixed_today(date(2026, 11, 20))
    memos.save(admin_user, it_board, "day", D, "", no_work=True, confirm=True)
    assert Memo.objects.get().no_work


def test_turning_no_work_off_leaves_empty_day(world, admin_user, it_board):
    memos.save(admin_user, it_board, "day", D, "휴무", no_work=True, confirm=True)
    memos.save(admin_user, it_board, "day", D, "휴무 취소", no_work=False)
    assert not Memo.objects.get().no_work and not Commute.objects.filter(date=D).exists()


# ── 읽기 ──

def test_no_work_days_and_for_range(admin_user, it_board):
    memos.save(admin_user, it_board, "day", D, "휴무", no_work=True)
    memos.save(admin_user, it_board, "day", date(2026, 11, 19), "행사")
    memos.save(admin_user, it_board, "week", D, "주 메모")
    memos.save(admin_user, it_board, "month", date(2026, 12, 3), "12월")
    memos.save(admin_user, it_board, "day", date(2026, 11, 13), "범위 밖")
    assert memos.no_work_days(it_board, date(2026, 11, 16), date(2026, 11, 20)) == {D}
    r = memos.for_range(it_board, date(2026, 11, 16), date(2026, 12, 4))
    assert set(r["day"]) == {D, date(2026, 11, 19)}
    assert set(r["week"]) == {date(2026, 11, 16)}
    assert set(r["month"]) == {date(2026, 12, 1)}
    memos.save(admin_user, it_board, "month", date(2026, 11, 5), "11월")
    assert set(memos.for_range(it_board, date(2026, 11, 2), date(2026, 11, 6))["month"]) == {date(2026, 11, 1)}
```

- [ ] **Step 6: 실패를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_memos.py -q`
Expected: 수집 오류 `ImportError: cannot import name 'memos' from 'duty.services'`

- [ ] **Step 7: 메모 서비스를 만든다**

`duty/services/memos.py`(새 파일):
```python
"""메모(날·주·달)와 근무 없음(설계 4.8·6.5). 편집은 그 근무표 관리 그룹만."""
from datetime import date, timedelta

from django.core.exceptions import PermissionDenied
from django.db import transaction

from .. import perms
from ..errors import DutyError
from ..models import ChangeLog, Commute, DutyAssignment, Memo, Period

DAY, WEEK, MONTH = Memo.Scope.DAY, Memo.Scope.WEEK, Memo.Scope.MONTH
MAX_TEXT = 500


def normalize(scope: str, d: date) -> date:
    """주 메모는 그 주 월요일, 달 메모는 그 달 1일에 붙는다."""
    if scope == WEEK:
        return d - timedelta(days=d.weekday())
    if scope == MONTH:
        return d.replace(day=1)
    if scope == DAY:
        return d
    raise DutyError("알 수 없는 메모 범위입니다.")


def _require_admin(user, board) -> None:
    if not perms.is_board_admin(user, board):
        raise PermissionDenied("메모는 근무표 관리자만 고칠 수 있습니다.")


def _rows(board, d: date):
    """그날 그 근무표의 모든 배정(모든 회차: 배포 회차 = 그날의 주인, 배포 전 회차의 입력·생성 행)."""
    return (Commute.objects.filter(period__board=board, date=d).select_related("period", "member").order_by("id"),
            DutyAssignment.objects.filter(period__board=board, date=d).select_related("period", "member").order_by("id"))


def affected(board, d: date) -> int:
    """근무 없음으로 저장하면 근무가 지워지는 사람 수(확인창 '○명의 근무가 지워집니다')."""
    commutes, duties = _rows(board, d)
    return len({*commutes.values_list("member_id", flat=True), *duties.values_list("member_id", flat=True)})


def _clear_day(user, board, d: date) -> int:
    """그날 배정을 모두 지운다. 배포 회차(그날의 주인)의 행은 지운 것마다 ChangeLog(빼기)를 남겨
    근무표 이력·변경 알림이 평소처럼 돈다. 배포 전 회차 행은 기록 없이 지운다(근무 없음 날은 늘 비어 있다)."""
    n = affected(board, d)
    commutes, duties = _rows(board, d)
    for rows, field in ((commutes, "shift"), (duties, "cell")):
        for r in rows:
            if r.period.status == Period.Status.PUBLISHED:
                ChangeLog.objects.create(by=user, period=r.period, date=d, cell=getattr(r, field), before=r.member)
    commutes.delete()
    duties.delete()
    return n


@transaction.atomic
def save(user, board, scope: str, d: date, text: str, no_work: bool = False, confirm: bool = False) -> int:
    """메모를 저장하고 지운 근무의 사람 수를 돌려준다. 글이 비고 근무 없음도 아니면 지운다.
    근무 없음으로 저장할 때 그날 배정이 있으면 confirm=True 여야 한다(아니면 DutyError)."""
    _require_admin(user, board)
    d = normalize(scope, d)
    text = (text or "").strip()
    if no_work and scope != DAY:
        raise DutyError("근무 없음은 날 메모에만 달 수 있습니다.")
    if len(text) > MAX_TEXT:
        raise DutyError(f"메모는 {MAX_TEXT}자까지 쓸 수 있습니다.")
    if not text and not no_work:
        delete(user, board, scope, d)
        return 0
    cleared = 0
    if no_work:
        n = affected(board, d)
        if n and not confirm:
            raise DutyError(f"{n}명의 근무가 지워집니다. 확인하고 다시 저장해 주세요.")
        cleared = _clear_day(user, board, d)
    Memo.objects.update_or_create(board=board, scope=scope, date=d, defaults={"text": text, "no_work": no_work})
    return cleared


@transaction.atomic
def delete(user, board, scope: str, d: date) -> None:
    """메모를 지운다. 근무 없음 날이었으면 빈 날이 되고, 근무 변경 '넣기'로 다시 채운다."""
    _require_admin(user, board)
    Memo.objects.filter(board=board, scope=scope, date=normalize(scope, d)).delete()


def no_work_days(board, start: date, end: date) -> set[date]:
    return set(Memo.objects.filter(board=board, scope=DAY, no_work=True, date__gte=start, date__lte=end)
               .values_list("date", flat=True))


def for_range(board, start: date, end: date) -> dict[str, dict[date, Memo]]:
    """start~end 화면에 걸리는 메모: {"day": {날짜: 메모}, "week": {월요일: 메모}, "month": {1일: 메모}}."""
    lo = min(normalize(WEEK, start), normalize(MONTH, start))
    out = {DAY: {}, WEEK: {}, MONTH: {}}
    for m in Memo.objects.filter(board=board, date__gte=lo, date__lte=end):
        if m.scope != DAY or m.date >= start:
            out[m.scope][m.date] = m
    return out
```

- [ ] **Step 8: 통과를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_memos.py -q`
Expected: `13 passed`

- [ ] **Step 9: 근무 변경 막기·배포 취소 테스트를 쓰고 실패를 확인한다**

`tests/test_memo_guards.py`(새 파일):
```python
"""근무 없음 날: 근무 변경 막기(설계 6.4), 배포 취소가 그날 행을 되살리지 않기(설계 6.1). 이름은 모두 가상."""
from datetime import date

import pytest

from duty.errors import DutyError
from duty.models import Commute, DutyAssignment, Period
from duty.services import changes, memos
from duty.services.publish import publish, unpublish, unpublish_info

S = Period.Status
D = date(2026, 11, 18)  # 수요일


@pytest.fixture
def world(make_member, admin_user, fixed_today, it_board):
    fixed_today(date(2026, 11, 16))
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 16), end_date=date(2026, 11, 20),
                              status=S.PUBLISHED, overwrite_from=date(2026, 11, 16))
    m = {n: make_member(n, user=True) for n in ["가", "나", "다"]}
    Commute.objects.create(period=p, date=D, member=m["가"], shift="dawn")
    Commute.objects.create(period=p, date=D, member=m["나"], shift="normal")
    DutyAssignment.objects.create(period=p, date=D, cell="slot0", member=m["가"])
    Commute.objects.create(period=p, date=date(2026, 11, 19), member=m["다"], shift="normal")
    return p, m


# ── 근무 없음 날 근무 변경 막기 ──

def test_changes_blocked_on_no_work_day(world, admin_user, it_board):
    _, m = world
    memos.save(admin_user, it_board, "day", D, "휴무", no_work=True, confirm=True)
    with pytest.raises(DutyError, match="근무 없는 날입니다"):
        changes.change_cell(admin_user, it_board, D, "normal", None, m["다"])
    with pytest.raises(DutyError, match="근무 없는 날입니다"):
        changes.exchange(admin_user, it_board, D, "normal", m["가"], m["다"])
    with pytest.raises(DutyError, match="근무 없는 날입니다"):
        changes.swap(admin_user, it_board, D, "dawn", m["가"], "normal", m["나"])
    memos.delete(admin_user, it_board, "day", D)
    changes.change_cell(admin_user, it_board, D, "normal", None, m["다"])  # 메모를 지우면 넣기로 다시 채운다
    assert Commute.objects.filter(date=D, member=m["다"]).exists()


def test_plain_day_memo_does_not_block(world, admin_user, it_board):
    _, m = world
    memos.save(admin_user, it_board, "day", D, "행사")
    changes.change_cell(admin_user, it_board, D, "night", None, m["다"])


# ── 배포 취소는 근무 없음 날 행을 되살리지 않는다 ──

def test_unpublish_skips_no_work_days(make_member, admin_user, it_board, fixed_today):
    fixed_today(date(2026, 11, 2))
    ga, na = make_member("가"), make_member("나")
    a = Period.objects.create(board=it_board, name="A", start_date=date(2026, 11, 16), end_date=date(2026, 11, 20),
                              status=S.GENERATED)
    b = Period.objects.create(board=it_board, name="B", start_date=date(2026, 11, 16), end_date=date(2026, 11, 20),
                              status=S.GENERATED)
    for day in (17, 18):
        Commute.objects.create(period=a, date=date(2026, 11, day), member=ga, shift="normal")
        Commute.objects.create(period=b, date=date(2026, 11, day), member=na, shift="normal")
    publish(a, date(2026, 11, 16))
    publish(b, date(2026, 11, 16))  # A 의 17·18일 행이 publish_undo 로
    memos.save(admin_user, it_board, "day", D, "휴무", no_work=True, confirm=True)
    assert unpublish_info(b).restored_rows == 1
    unpublish(b)
    assert list(Commute.objects.filter(period=a).values_list("date", flat=True)) == [date(2026, 11, 17)]
```

Run: `.venv/bin/pytest -W error tests/test_memo_guards.py -q`
Expected: `2 failed, 1 passed` — `test_changes_blocked_on_no_work_day`(`Failed: DID NOT RAISE DutyError`), `test_unpublish_skips_no_work_days`(`assert 2 == 1`)

- [ ] **Step 10: 근무 변경과 배포 취소에 근무 없음을 반영한다**

`duty/services/changes.py`:
```python
from . import boards
```
→
```python
from . import boards, memos
```

`_owner` 를 다음으로 바꾼다. 근무 없음 검사는 주인 조회 **뒤**에 둔다(`tests/test_changes.py::test_owner_with_many_published_periods` 가 `_owner` 의 첫 SQL 이 주인 조회인지 본다):
```python
def _owner(board, d: date) -> Period:
    p = boards.owner(board, d)  # 그날의 주인(설계 6.1): 기간·배포 순번으로 정한다. 행이 없는 날도 주인이 있다
    if p is None:
        raise DutyError("배포된 근무표에 없는 날짜입니다.")
    if memos.no_work_days(board, d, d):  # 근무 없음 날은 늘 비어 있다(설계 6.4). 휴장일은 막지 않는다
        raise DutyError("근무 없는 날입니다.")
    return p
```

`duty/services/publish.py`:
```python
from . import boards
from .periods import record
```
→
```python
from . import boards, memos
from .periods import record
```

`unpublish_info` 의 마지막 줄:
```python
    return UnpublishInfo(None, len(period.publish_undo), ChangeLog.objects.filter(period=period, at__gte=period.published_at).count())
```
→
```python
    return UnpublishInfo(None, len(_restorable(period)), ChangeLog.objects.filter(period=period, at__gte=period.published_at).count())


def _restorable(period: Period) -> list:
    """배포 취소로 되살릴 행: 그 근무표의 근무 없음 날짜 행은 빼고(근무 없음 날은 늘 비어 있다, 설계 6.1)."""
    closed = {x.isoformat() for x in memos.no_work_days(period.board, date.min, date.max)}
    return [r for r in period.publish_undo if r[2] not in closed]
```

`unpublish` 안:
```python
    undo = period.publish_undo
```
→
```python
    undo = _restorable(period)
```
(바로 아래의 "되살릴 근무의 사용자가 삭제되어…" 검사와 `bulk_create` 는 이 `undo` 를 그대로 쓴다.)

- [ ] **Step 11: 통과를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_memo_guards.py tests/test_changes.py tests/test_period_lifecycle.py -q`
Expected: `63 passed`(새 3 + 기존 60)

- [ ] **Step 12: 화면 테스트를 쓰고 실패를 확인한다**

`tests/test_views_memos.py`(새 파일):
```python
"""메모 화면: 날 메모·근무 없음(칸 덮기), 주 메모(주간 표 위·월간 그 주 행 아래), 달 메모(표 아래), 관리 그룹만 [메모] 팝업.
이름은 모두 가상."""
from datetime import date

import pytest

from duty.models import ChangeLog, Commute, Memo, Period

D = date(2026, 11, 18)  # 수요일
MON = date(2026, 11, 16)


@pytest.fixture
def world(make_member, fixed_today, it_board):
    fixed_today(MON)
    p = Period.objects.create(board=it_board, name="p", start_date=MON, end_date=date(2026, 11, 20),
                              status=Period.Status.PUBLISHED, overwrite_from=MON)
    m = make_member("가", user=True)
    for x in (D, date(2026, 11, 19)):
        Commute.objects.create(period=p, date=x, member=m, shift="normal")
    return p, m


def memo(it_board, scope, d, text, no_work=False):
    return Memo.objects.create(board=it_board, scope=scope, date=d, text=text, no_work=no_work)


# ── 보이기 ──

@pytest.mark.parametrize("url", [f"/?view=week&date={D}", f"/?view=month&date={D}", f"/day/{D}/"])
def test_day_memo_line_above_assignments(client, world, it_board, url):
    memo(it_board, "day", D, "전산 점검")
    client.force_login(world[1])
    body = client.get(url).content.decode()
    assert '<p class="memo">전산 점검</p>' in body and ">가<" in body


@pytest.mark.parametrize("url", [f"/?view=week&date={D}", f"/?view=month&date={D}"])
def test_no_work_covers_cell(client, world, it_board, url):
    memo(it_board, "day", D, "임시 휴무", no_work=True)
    Commute.objects.filter(date=D).delete()
    ChangeLog.objects.create(by=world[1], period=world[0], date=D, cell="normal", before=world[1])  # 지운 기록
    client.force_login(world[1])
    body = client.get(url).content.decode()
    assert '<p class="nowork">임시 휴무</p>' in body
    assert "<s>가</s>" not in body  # 지운 사람 취소선도 덮는다
    assert f'/cell/{D}/' not in body and f'/cell/2026-11-19/' in body  # 근무 없음 날만 칸 링크가 없다


def test_no_work_without_text_and_without_roster(client, world, it_board):
    memo(it_board, "day", date(2026, 11, 23), "", no_work=True)  # 배포 회차 밖(근무표 없음) 날에도 보인다
    client.force_login(world[1])
    body = client.get("/?view=week&date=2026-11-23").content.decode()
    assert '<p class="nowork">근무 없음</p>' in body and "근무표 없음" in body  # 23일은 덮고, 24~27일은 근무표 없음


def test_day_page_no_work_hides_change_buttons(client, world, it_board):
    memo(it_board, "day", D, "임시 휴무", no_work=True)
    client.force_login(world[1])
    body = client.get(f"/day/{D}/").content.decode()
    assert '<p class="nowork">임시 휴무</p>' in body and 'class="dcell"' not in body and "배포된 근무표에 없는" not in body


def test_week_memo_above_table_in_week_view(client, world, it_board):
    memo(it_board, "week", MON, "토요일 근무: 가")
    client.force_login(world[1])
    body = client.get(f"/?view=week&date={D}").content.decode()
    assert "토요일 근무: 가" in body and body.index("토요일 근무: 가") < body.index('id="roster"')


def test_week_memo_row_under_its_week_in_month_view(client, world, it_board):
    memo(it_board, "week", MON, "셋째 주 메모")
    client.force_login(world[1])
    body = client.get(f"/?view=month&date={D}").content.decode()
    i = body.index("셋째 주 메모")
    assert body.rindex(">20<", 0, i) > body.rindex(">16<", 0, i)  # 그 주(16~20일) 행 뒤
    assert body.index(">23<") > i and 'class="wmemo"' in body  # 다음 주 행 앞
    assert body.count('class="wmemo"') == 1  # 메모 없는 주는 줄을 만들지 않는다(관리자가 아니면)


def test_month_memo_below_table(client, world, it_board):
    memo(it_board, "month", date(2026, 11, 1), "본부 점심: 가")
    client.force_login(world[1])
    for url in (f"/?view=month&date={D}", f"/?view=week&date={D}"):
        body = client.get(url).content.decode()
        assert body.index("본부 점심: 가") > body.index("</table>")
    assert "본부 점심: 가" not in client.get("/?view=month&date=2026-12-02").content.decode()  # 12월 달력엔 11월 메모 없음


def test_memo_text_is_escaped(client, world, it_board):
    memo(it_board, "day", D, "<b>x</b>")
    client.force_login(world[1])
    assert "&lt;b&gt;x&lt;/b&gt;" in client.get(f"/day/{D}/").content.decode()


# ── 관리 그룹만 [메모] ──

def test_memo_links_only_for_admin(client, world, admin_user):
    client.force_login(world[1])
    for url in (f"/?view=week&date={D}", f"/?view=month&date={D}", f"/day/{D}/"):
        assert "/memo/" not in client.get(url).content.decode()
    client.force_login(admin_user)
    week = client.get(f"/?view=week&date={D}").content.decode()
    assert f'hx-get="/memo/day/{D}/?next=' in week and f'/memo/week/{MON}/' in week and "/memo/month/2026-11-01/" in week
    month = client.get(f"/?view=month&date={D}").content.decode()
    assert month.count('class="wmemo"') == 5  # 11월 달력 5주 모두 [메모] 줄
    assert f"/memo/day/{D}/" in client.get(f"/day/{D}/").content.decode()


def test_popup_requires_admin(client, world):
    client.force_login(world[1])
    assert client.get(f"/memo/day/{D}/").status_code == 404
    assert client.post(f"/memo/day/{D}/", {"text": "x"}).status_code == 404
    assert not Memo.objects.exists()


def test_popup_form(admin_client_ok, world, it_board):
    memo(it_board, "week", MON, "기존 메모")
    body = admin_client_ok.get(f"/memo/week/{D}/").content.decode()  # 수요일로 열어도 그 주 월요일 메모
    assert "11/16 주 메모" in body and "기존 메모" in body and 'name="no_work"' not in body and "메모 지우기" in body
    body = admin_client_ok.get(f"/memo/day/{D}/").content.decode()
    assert 'name="no_work"' in body and 'data-affected="1"' in body and "메모 지우기" not in body
    assert admin_client_ok.get(f"/memo/year/{D}/").status_code == 404


def test_post_saves_and_redirects(admin_client_ok, world):
    r = admin_client_ok.post(f"/memo/month/{D}/", {"text": "본부 점심", "next": f"/?view=month&date={D}"})
    assert r.status_code == 302 and r.url == f"/?view=month&date={D}"
    assert Memo.objects.get().date == date(2026, 11, 1)


def test_post_no_work_needs_confirm(admin_client_ok, world):
    r = admin_client_ok.post(f"/memo/day/{D}/", {"text": "휴무", "no_work": "1"}, follow=True)
    assert "1명의 근무가 지워집니다" in r.content.decode() and not Memo.objects.exists()
    r = admin_client_ok.post(f"/memo/day/{D}/", {"text": "휴무", "no_work": "1", "confirm": "1"}, follow=True)
    assert "1명의 근무를 지웠습니다" in r.content.decode()
    assert Memo.objects.get().no_work and not Commute.objects.filter(date=D).exists()


def test_post_delete(admin_client_ok, world, it_board):
    memo(it_board, "day", D, "행사")
    admin_client_ok.post(f"/memo/day/{D}/", {"text": "행사", "delete": "1"})
    assert not Memo.objects.exists()
```

Run: `.venv/bin/pytest -W error tests/test_views_memos.py -q`
Expected: `16 failed, 1 passed`(`test_popup_requires_admin` 은 주소가 아직 없어 404 라 미리 통과한다)

- [ ] **Step 13: 메모 뷰·주소를 만들고 근무표·하루 화면에 메모를 넘긴다**

`duty/views/roster.py` import 두 줄:
```python
from ..models import Department, User
from ..services import boards, changes, holidays, prefs
```
→
```python
from ..models import Department, Memo, User
from ..services import boards, changes, holidays, memos, prefs
```

`roster()` 안, Task 1 이 넣은 줄 뒤에 한 줄:
```python
    closed = holidays.closed(first_day, last_day)  # 휴장일 이름은 회차·배정과 상관없이 칸 맨 위에
```
→
```python
    closed = holidays.closed(first_day, last_day)  # 휴장일 이름은 회차·배정과 상관없이 칸 맨 위에
    notes = memos.for_range(board, first_day, last_day)  # 메모도 회차가 아니라 (근무표, 날짜)에 붙는다
```

`day_info` 의 앞부분:
```python
        cells = day_cells(d)
        other = view == "month" and d.month != anchor.month
        return {
            "date": d, "is_today": d == today, "other": other, "empty": d not in by_date, "holiday": closed.get(d, ""),
            "edit": (edit_past if d < today else edit_now) and not other and d in by_date,  # 배포된 근무표가 있는 날만
```
→
```python
        cells = day_cells(d)
        other = view == "month" and d.month != anchor.month
        note = notes["day"].get(d)
        no_work = bool(note and note.no_work)
        return {
            "date": d, "is_today": d == today, "other": other, "empty": d not in by_date, "holiday": closed.get(d, ""),
            "memo": note.text if note else "", "no_work": no_work,
            "week_memo": notes["week"].get(d),  # 월요일 칸에만 붙는다(week.0 = 그 주 월요일)
            # 배포된 근무표가 있는 날만, 근무 없음 날은 못 바꾼다
            "edit": (edit_past if d < today else edit_now) and not other and d in by_date and not no_work,
```
(`"commute"`·`"duty"` 줄과 닫는 `}` 는 그대로.)

```python
    days = [[day_info(d) for d in w] for w in weeks]
```
→
```python
    days = [[day_info(d) for d in w] for w in weeks]
    months = sorted({d.replace(day=1) for w in weeks for d in w if view == "week" or d.month == anchor.month})
```

```python
    ctx.update(_filter_ctx(board, defs, depts, types, shifts, history), weeks=days)
```
→
```python
    ctx.update(_filter_ctx(board, defs, depts, types, shifts, history), weeks=days,
               memo_admin=perms.is_board_admin(request.user, board),
               month_memos=[{"date": m, "memo": notes["month"].get(m)} for m in months])
```

`day()` 안:
```python
    found = find_day(board, d)
    editable = perms.can_edit(request.user, board, d)
```
→
```python
    found = find_day(board, d)
    note = memos.for_range(board, d, d)["day"].get(d)
    no_work = bool(note and note.no_work)  # 근무 없음 날은 칸 대신 메모 글만, 바꾸기 없음
    editable = perms.can_edit(request.user, board, d) and not no_work
```

```python
    if found:
        for k in filter(shown, [x.key for x in display_order(defs)]):  # 출근조 먼저, 관제는 뒤에 묶어서
```
→
```python
    if found and not no_work:
        for k in filter(shown, [x.key for x in display_order(defs)]):  # 출근조 먼저, 관제는 뒤에 묶어서
```

`day()` 의 render 컨텍스트(Task 1 이 넣은 줄):
```python
        "holiday": holidays.closed(d, d).get(d, ""),
```
→
```python
        "holiday": holidays.closed(d, d).get(d, ""), "note": note,
        "memo_admin": perms.is_board_admin(request.user, board),
```

`@login_required` / `def me(request):` 바로 앞에 새 뷰:
```python
@login_required
def memo(request, scope, d):
    """[메모] 팝업(근무 변경 창과 같은 방식). 근무표 관리 그룹만."""
    board = _board(request.user)
    if scope not in Memo.Scope.values or not perms.is_board_admin(request.user, board):
        raise Http404
    d = memos.normalize(scope, d)
    fallback = reverse("day", args=[d]) if scope == Memo.Scope.DAY else reverse("roster")
    if request.method == "POST":
        try:
            if request.POST.get("delete"):
                memos.delete(request.user, board, scope, d)
                msg = "메모를 지웠습니다."
            else:
                cleared = memos.save(request.user, board, scope, d, request.POST.get("text", ""),
                                     no_work=bool(request.POST.get("no_work")), confirm=bool(request.POST.get("confirm")))
                msg = f"메모를 저장했습니다. {cleared}명의 근무를 지웠습니다." if cleared else "메모를 저장했습니다."
        except DutyError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, msg)
        return redirect(safe_next(request, fallback))
    return render(request, "duty/_memo_form.html", {
        "scope": scope, "d": d, "memo": memos.for_range(board, d, d)[scope].get(d), "next": safe_next(request, fallback),
        "title": {"day": f"{d:%Y-%m-%d} 메모", "week": f"{d.month}/{d.day} 주 메모", "month": f"{d.year}년 {d.month}월 메모"}[scope],
        "affected": memos.affected(board, d) if scope == Memo.Scope.DAY else 0,
    })
```

`duty/urls.py`:
```python
    path("cell/<isodate:d>/<str:cell>/", roster_views.cell, name="cell"),
```
→
```python
    path("cell/<isodate:d>/<str:cell>/", roster_views.cell, name="cell"),
    path("memo/<str:scope>/<isodate:d>/", roster_views.memo, name="memo"),
```

- [ ] **Step 14: 템플릿을 만든다**

`duty/templates/duty/_memo_form.html`(새 파일, 팝업 조각. 근무 변경 창 `_cell_form.html` 과 같은 방식):
```html
<form method="post" action="{% url 'memo' scope d %}" onsubmit="return memoConfirm(this, event.submitter)">{% csrf_token %}
  <input type="hidden" name="next" value="{{ next }}">
  <input type="hidden" name="confirm" value="">
  <p><strong>{{ title }}</strong></p>
  <label>내용
    <textarea name="text" rows="3" maxlength="500">{{ memo.text }}</textarea>
  </label>
  {% if scope == "day" %}<label><input type="checkbox" name="no_work" value="1" data-affected="{{ affected }}"{% if memo.no_work %} checked{% endif %}> 근무 없음 <small>(그날 칸 전체를 이 글로 덮고 근무를 지웁니다)</small></label>{% endif %}
  <button>저장</button>{% if memo %} <button name="delete" value="1" class="secondary">메모 지우기</button>{% endif %}
</form>
<script>
  // 근무 없음은 그날 근무를 지운다: 사람이 있으면 한 번 더 묻고 confirm 을 보낸다(서비스도 confirm 없으면 막는다)
  window.memoConfirm = window.memoConfirm || ((f, btn) => {
    if (btn && btn.name === "delete") return confirm("메모를 지울까요?");
    const nw = f.elements.no_work, n = nw ? Number(nw.dataset.affected) : 0;
    if (!nw || !nw.checked || !n) return true;
    if (!confirm(n + "명의 근무가 지워집니다. 저장할까요?")) return false;
    f.elements.confirm.value = "1";
    return true;
  });
</script>
```

`duty/templates/duty/_memo.html`(새 파일, 주·달 메모 한 줄. `scope`·`md`(맞춘 날짜)·`m`(Memo 또는 None)을 받고 `memo_admin` 은 부모 컨텍스트에서 읽는다):
```html
{% if m or memo_admin %}<div class="memo-note"><small>{% if scope == "week" %}주 메모{% else %}{{ md.month }}월 메모{% endif %}</small>{% if m %} <span>{{ m.text|linebreaksbr }}</span>{% endif %}{% if memo_admin %} <a class="memo-btn" href="{% url 'memo' scope md %}" hx-get="{% url 'memo' scope md %}?next={{ request.get_full_path|urlencode }}" hx-target="#dlg-body">[메모]</a>{% endif %}</div>{% endif %}
```

`duty/templates/duty/_daycell.html` 1~3줄(1줄 날짜 링크, 2줄 Task 1 의 휴장일, 3줄 "근무표 없음"):
```html
<a href="{% url 'day' d.date %}"><strong>{% if view == "week" %}{{ d.date.month }}/{{ d.date.day }}{% else %}{{ d.date.day }}{% endif %}</strong></a>
{% if d.holiday and not d.other %}<p class="hol">{{ d.holiday }}</p>{% endif %}
{% if d.empty and not d.other %}<p class="none">근무표 없음</p>{% elif not d.other %}
```
→
```html
<a href="{% url 'day' d.date %}"><strong>{% if view == "week" %}{{ d.date.month }}/{{ d.date.day }}{% else %}{{ d.date.day }}{% endif %}</strong></a>{% if memo_admin and not d.other %} <a class="memo-btn" href="{% url 'memo' 'day' d.date %}" hx-get="{% url 'memo' 'day' d.date %}?next={{ request.get_full_path|urlencode }}" hx-target="#dlg-body" aria-label="{{ d.date|date:'n/j' }} 메모">[메모]</a>{% endif %}
{% if d.holiday and not d.other %}<p class="hol">{{ d.holiday }}</p>{% endif %}
{% if d.memo and not d.no_work and not d.other %}<p class="memo">{{ d.memo|linebreaksbr }}</p>{% endif %}
{% if d.other %}{% elif d.no_work %}<p class="nowork">{{ d.memo|default:"근무 없음"|linebreaksbr }}</p>{% elif d.empty %}<p class="none">근무표 없음</p>{% else %}
```
(나머지 줄과 마지막 `{% endif %}` 는 그대로. 근무 없음 날은 근무조·관제·취소선 줄을 그리지 않는다.)

`duty/templates/duty/roster.html` — 표 위(주간):
```html
<div class="grid-wrap roster-scroll">
```
→
```html
{% if view == 'week' %}{% include "duty/_memo.html" with scope="week" md=weeks.0.0.date m=weeks.0.0.week_memo %}{% endif %}
<div class="grid-wrap roster-scroll">
```

주 행 뒤(월간):
```html
    {% endfor %}
    </tr>
  {% endfor %}
```
→
```html
    {% endfor %}
    </tr>
    {% if view == 'month' %}{% if week.0.week_memo or memo_admin %}<tr class="wmemo"><td colspan="5">{% include "duty/_memo.html" with scope="week" md=week.0.date m=week.0.week_memo %}</td></tr>{% endif %}{% endif %}
  {% endfor %}
```

표 아래(달 메모):
```html
</table>
</div>
```
→
```html
</table>
</div>
{% for mm in month_memos %}{% include "duty/_memo.html" with scope="month" md=mm.date m=mm.memo %}{% endfor %}
```

`duty/templates/duty/day.html`:
```html
{% if holiday %}<p class="hol">{{ holiday }}</p>{% endif %}
```
→
```html
{% if holiday %}<p class="hol">{{ holiday }}</p>{% endif %}
{% if note and not note.no_work %}<p class="memo">{{ note.text|linebreaksbr }}</p>{% endif %}
{% if memo_admin %}<p><a class="memo-btn" href="{% url 'memo' 'day' d %}" hx-get="{% url 'memo' 'day' d %}?next={{ request.get_full_path|urlencode }}" hx-target="#dlg-body">[메모]</a></p>{% endif %}
```

```html
{% if not found %}<p>배포된 근무표에 없는 날짜입니다.</p>{% endif %}
```
→
```html
{% if note.no_work %}<p class="nowork">{{ note.text|default:"근무 없음"|linebreaksbr }}</p>{% elif not found %}<p>배포된 근무표에 없는 날짜입니다.</p>{% endif %}
```

`duty/templates/duty/base.html` — Task 1 의 `.hol` 줄 바로 뒤:
```css
    /* 메모: 날 메모는 휴장일 아래 한 줄, 근무 없음은 칸 전체를 덮는다. 주·달 메모는 표 위·아래(월간 주 메모는 그 주 행 아래) */
    .memo { margin: .2rem 0 0; font-weight: 600; }
    .nowork { margin: .4rem 0 0; padding: 1.2rem .4rem; border-radius: .3rem; text-align: center; font-weight: 700; background: var(--duty-line); }
    .memo-btn { margin-left: .3rem; font-size: .8rem; white-space: nowrap; }
    .memo-note { margin: .3rem 0 .6rem; }
    .memo-note > small { margin-right: .3rem; opacity: .7; }
    table.roster tr.wmemo td { padding: .2rem .5rem; }
    table.roster tr.wmemo .memo-note { margin: 0; }
```
(`--duty-line` 은 라이트·다크 값이 이미 있어 다크 모드에서도 덮개가 보인다.)

- [ ] **Step 15: 통과를 확인한다**

Run: `.venv/bin/pytest -W error tests/test_views_memos.py -q`
Expected: `17 passed`

- [ ] **Step 16: 전체 테스트·마이그레이션 검사**

Run: `.venv/bin/pytest -W error -q && DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --check --dry-run`
Expected: `980 passed`(Task 1 끝 946 + 새 34), 경고 0개. `No changes detected in app 'duty'`. `tests/test_alarm_texts_it.py` 포함 기존 테스트는 하나도 고치지 않았다.

- [ ] **Step 17: 브라우저로 확인한다(CLAUDE.md, PC 1400px·모바일 390px)**

`config.test_settings` 로 띄워 실명 DB 를 열지 않는다(프로세스마다 빈 임시 DATA_DIR). migrate·가짜 데이터·확인용 메모·서버를 한 프로세스에서 돌리고, 스크립트는 저장소 밖 임시 폴더에 둔다.

```bash
W=$(mktemp -d)
cat > $W/serve.py <<'EOF'
"""브라우저 확인용: 임시 DATA_DIR(test_settings)에 가짜 데이터 + 확인용 메모를 넣고 같은 프로세스에서 서버를 띄운다."""
import sys
from datetime import timedelta

import django

django.setup()
from django.core.management import call_command  # noqa: E402

call_command("migrate", verbosity=0)
exec(open("tools/help_videos/seed.py", encoding="utf-8").read())
from duty import perms  # noqa: E402
from duty.models import User  # noqa: E402
from duty.services import boards, memos  # noqa: E402

it, admin = boards.it_board(), User.objects.get(username="admin")
mon = perms.today() - timedelta(days=perms.today().weekday())
memos.save(admin, it, "day", mon + timedelta(days=1), "전산 점검 18시 이후")
memos.save(admin, it, "day", mon + timedelta(days=2), "임시 휴무(확인용)", no_work=True, confirm=True)
memos.save(admin, it, "week", mon, "토요일 근무: 김가나, 이다라")
memos.save(admin, it, "month", mon, "본부 점심: 박마바, 최사아, 정자차")
print("확인 주:", mon)
call_command("runserver", sys.argv[1], use_reloader=False)
EOF
DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. .venv/bin/python $W/serve.py 127.0.0.1:8795 &
# 확인이 끝나면: kill %1; rm -rf $W   (DB 는 임시 DATA_DIR 이라 프로세스와 함께 사라진다)
```

계정 `member`·`admin`(비밀번호 `Demo-pass-123`). PC 1400px·모바일 390px 에서:
- admin `/?view=week&date=<확인 주>`: 표 위 "주 메모 토요일 근무: …  [메모]". 날짜마다 `[메모]`. 화요일 칸 날짜 아래 굵은 "전산 점검 18시 이후", 그 아래 배정. 수요일 칸은 회색 덮개 "임시 휴무(확인용)"만(근무조·관제·칸 링크 없음). 표 아래 "N월 메모 본부 점심: …". 390px 세로 쌓기에서도 같은 순서.
- admin `/?view=month&date=<확인 주>`: 주마다 행 아래 "주 메모 [메모]" 줄, 확인 주 행 아래에 주 메모 글. 표 아래 달 메모 하나. 다른 달 흐린 칸에는 [메모]·메모가 없다.
- `[메모]` 를 누르면 팝업: 날 메모는 "근무 없음" 체크가 보이고, 근무가 있는 날에 체크해 저장하면 "○명의 근무가 지워집니다. 저장할까요?" 확인창 → 저장 뒤 칸이 덮이고 "메모를 저장했습니다. ○명의 근무를 지웠습니다." 메시지. 이력 화면에 지운 칸마다 빼기 기록. 주·달 메모 팝업에는 근무 없음 체크가 없다. "메모 지우기" → 확인창 → 사라짐.
- 근무 없음 날 `/day/<수요일>/`: 덮개만 있고 [바꾸기] 없음. 근무 없음을 끄면(체크 해제 저장) 빈 날이 되고 [바꾸기]의 "새로 넣기만"으로 다시 채워진다.
- member 로 같은 화면: 메모 글·덮개는 보이고 `[메모]` 링크는 하나도 없다. `/memo/day/<날짜>/` 직접 열면 404.
- 라이트·다크 모드 둘 다 덮개 글자가 읽히는지.

- [ ] **Step 18: 커밋한다**

```bash
git add duty/models.py duty/migrations/0019_memo.py duty/services/memos.py duty/services/changes.py \
        duty/services/publish.py duty/views/roster.py duty/urls.py \
        duty/templates/duty/_memo_form.html duty/templates/duty/_memo.html duty/templates/duty/_daycell.html \
        duty/templates/duty/roster.html duty/templates/duty/day.html duty/templates/duty/base.html \
        tests/test_memo_model.py tests/test_memos.py tests/test_memo_guards.py tests/test_views_memos.py
git commit -m "feat: 날·주·달 메모와 근무 없음(그날 배정 지우기·근무 변경 막기·배포 취소 제외), 관리 그룹 [메모] 팝업"
```
(커밋 메시지 끝에 세션의 Co-Authored-By·Claude-Session 줄을 붙인다.)

**뒤 작업이 알아야 할 점**
- 다음 마이그레이션 번호는 **0020**(의존 `duty.0019_memo`).
- 근무 없음 판단은 언제나 `memos.no_work_days(board, start, end)` 로 한다(`Memo.objects` 를 직접 거르지 않는다). `boards.skip_dates(period)` 는 `memos.no_work_days(period.board, period.start_date, period.end_date)` ∪ (`period.skip_holidays` 면 `holidays.closed(...)` 의 날짜)로 만들면 된다. 배포 전 회차 도구(입력 표 잠금·CSV 오류·채우기·생성·`missing_dates`·입력 현황)는 아직 근무 없음을 모른다. 다만 `memos.save` 가 근무 없음 저장 때 배포 전 회차의 그날 행도 지우므로, 저장 시점에는 그날이 비어 있다.
- 근무 없음 저장이 남기는 기록은 보통 빼기 `ChangeLog(after=None)` 이다. 사유(Task 3 이후)가 붙은 근무조 행을 지울 때 `reason_before` 를 채우려면 `memos._clear_day` 의 `ChangeLog.objects.create(...)` 에 `reason_before=r.reason` 을 더한다. 점심당번(`cell="lunch"`) 행도 `DutyAssignment` 라 같은 길로 지워지고 기록된다(근무조 기록 뒤에 남는다).
- 근무 변경 막기는 `changes._owner` 한 곳이다. 새로 만드는 근무 변경 함수(`set_reason` 등)가 `_owner` 를 거치면 따로 막을 필요가 없다. 오류 문구는 "근무 없는 날입니다."
- 배포 취소의 복원 행은 `publish._restorable(period)` 이 정한다(`r[2]` 날짜 문자열만 본다). publish_undo 행 모양을 바꾸는 작업(사유 여섯째 칸)도 이 함수는 그대로 쓴다.
- 메모 화면의 근무표는 지금 `_board(request.user)`(내 근무표)다. 근무표 고르기 작업은 `memo` 뷰가 고른 근무표를 쓰게 하고, `_daycell.html`·`_memo.html`·`day.html` 의 `{% url 'memo' ... %}` 링크(href·hx-get 둘 다)에 공통 함수의 `?board=` 를 붙인다(쿼리에 이미 `?next=` 가 있으니 `&board=` 로 잇는 것에 주의). `memo_admin` 은 보이는 근무표 기준 `perms.is_board_admin(user, board)` 라 그대로 맞다.
- 화면 컨텍스트: `day_info["memo"]`(str)·`["no_work"]`(bool)·`["week_memo"]`(Memo|None, 월요일만), `memo_admin`, `month_memos`. 날짜 칸 순서는 날짜·[메모] → `.hol` 휴장일 → `.memo` 날 메모 → (근무 없음이면 `.nowork` 하나로 끝) → 근무조 → 관제. 점심당번 칸을 더하는 작업은 근무조와 관제 사이에 넣는다(근무 없음이면 그리지 않는 `{% else %}` 가지 안).
- Django 관리 화면에는 Memo 를 등록하지 않았다(편집은 근무표 관리 그룹의 화면 팝업). 문서(ARCHITECTURE.md 메모·근무 없음, OVERVIEW.md, 사용법 `help.py` STEPS)는 2단계 문서 작업이 이 동작대로 쓴다.


---

### Task 3: 만드는 도구의 휴장일·근무 없음 건너뛰기

> 검증: Task 1·2 를 넣은 `feat/boards-phase2` 사본(980 passed)에 아래 코드를 그대로 넣어 확인했다. 저장소는 고치지 않았다. 결과: `.venv/bin/pytest -W error -q` → **999 passed**(980 + 새 19), 경고 0개. `makemigrations duty --check` → "No changes detected in app 'duty'"(마이그레이션 없음). 단계별 실패도 사본에서 하나씩 재현했다(Step 2 6 failed `AttributeError: module 'duty.services.boards' has no attribute 'skip_dates'`, Step 5 3 failed·2 passed, Step 8 1 failed·1 passed, Step 12 3 failed, Step 15 3 failed — 각 단계에 적었다). 가짜 데이터(가상 이름, 끝나면 지움)로 그린 입력 표를 headless Chrome 으로 1400·390px 캡처해 확인했다.
>
> 이 작업의 범위: `boards.skip_reasons(period)`·`boards.skip_dates(period)`, 출근표 입력 표의 그날 행 잠금, CSV·표 저장에서 그날 이름이 있으면 오류, 이미 있는 행은 남기기, CSV 내려받기의 그날 빈 줄, `run_generation` 의 관제 생성에서 제외, `missing_dates`·입력 현황(`collect.progress`)에서 제외, 영업일 기준 알림(`bizdays`)이 켜진 휴장일을 영업일에서 뺌.
> 규칙: 근무 없음 날은 늘 건너뛴다. 휴장일은 `period.skip_holidays` 가 참인 회차에서만 건너뛴다(Task 1 마이그레이션이 기존 회차를 거짓으로 둔다). 영업일 계산은 회차와 무관하게 켜진 휴장일 전부를 뺀다(설계 5 "영업일 기준 알림은 휴장일을 영업일에서 뺀다").
> 하지 않는 것(뒤 작업): 점심당번 채우기(그 작업이 `boards.skip_dates(period)` 로 같은 날을 뺀다), 채우기 버튼(3단계), direct 확정의 빈 평일 경고, 문서.
> IT 알림 문구·hash 는 바뀌지 않는다. 영업일 발송일만 휴장일 앞으로 당겨지고, 발송 기록 hash 에는 발송일이 없어 이미 보낸 알림은 다시 나가지 않는다(설계 5). `tests/test_alarm_texts_it.py` 그대로 통과. 휴장일 표가 비어 있는 기존 테스트는 결과가 같다.

**Files:**
- Modify: `duty/services/boards.py`(import 한 줄, 끝에 `skip_reasons`·`skip_dates`)
- Modify: `duty/services/periods.py`(import, `missing_dates`)
- Modify: `duty/services/collect.py`(`validate_table`, `apply_table` 의 지우기 줄, `export_csv`, `progress`)
- Modify: `duty/views/collect.py`(import, `_render_table`), `duty/templates/duty/collect_table.html`(본문 행 두 줄)
- Modify: `duty/services/generate.py`(`run_generation` 의 관제 생성 부분)
- Modify: `duty/alarms/schedule.py`(`bizdays_back`, `send_at`), `duty/alarms/plan.py`(`plan`, `_personal`, `_report`), `duty/services/alarm_runner.py`(import, `BIZ_BACK`, `collect`)
- Test: `tests/test_skip_days.py`(새 파일), `tests/test_alarm_schedule.py`·`tests/test_alarm_plan.py`·`tests/test_run_alarms.py`(끝에 테스트 하나씩 더함. 기존 테스트는 고치지 않는다. `test_run_alarms.py` 는 import 줄에 `Holiday` 를 더한다)

**Interfaces:**
- Consumes: (1단계) `Period(board, start_date, end_date, dates())`, `collect.validate_table/apply_table/apply_csv/export_csv/load_table/progress`, `periods.missing_dates(period)`, `generate.run_generation(period, seed=None, by=None)`, `alarms.schedule.bizdays_back/send_at`, `alarms.plan.plan(...)`, `alarm_runner.collect(now)`·`HORIZON`, conftest `it_board`·`depts`·`make_member`·`fixed_today`. (Task 1) `Holiday(date, name, source, active)`, `Period.skip_holidays`, `services.holidays.closed(start, end) -> dict[date, str]`(active 만, 주말 포함), `run_generation` 이 상태 검사 뒤 `holidays.sync(perms.today())` 를 부름, `base.html` 의 `.hol`. (Task 2) `Memo(board, scope, date, text, no_work)`, `services.memos.DAY`·`memos.for_range(board, start, end) -> {"day"|"week"|"month": {date: Memo}}`.
- Produces:
  - `duty.services.boards.skip_reasons(period: Period) -> dict[date, str]`: 만드는 도구가 건너뛰는 날 {날짜: 까닭}. `period.skip_holidays` 면 `holidays.closed(start_date, end_date)`(이름), 그 위에 그 근무표의 근무 없음 날 메모(까닭 = 메모 글, 비면 `"근무 없음"`)를 덮어쓴다. 주말 휴장일도 들어 있을 수 있다(쓰는 곳은 모두 `period.dates()` 와 겹쳐 본다).
  - `duty.services.boards.skip_dates(period: Period) -> set[date]` = `set(skip_reasons(period))`. 뒤 작업(점심당번 채우기·채우기 버튼)은 이것으로 같은 날을 뺀다.
  - `collect.validate_table`: 건너뛰는 날에 이름이 있으면 `CsvError(0, 날짜iso, f"{까닭}: 근무를 넣지 않는 날입니다.")`. 빈 줄은 괜찮다. 지난 날짜 검사(일반 담당자)에서 건너뛰는 날은 뺀다.
  - `collect.apply_table`: 건너뛰는 날의 기존 행은 지우지 않는다(휴장일을 나중에 추가해도 이미 넣은 배정이 남는다, 설계 5 "이미 배정된 행은 숨기지 않는다"). 근무 없음 날은 Task 2 의 `memos.save` 가 이미 비웠다.
  - `collect.export_csv`: 건너뛰는 날은 날짜·요일만 있는 빈 줄(내려받은 그대로 다시 올려도 오류가 없다).
  - `collect.progress(period)`: (건너뛰는 날을 뺀 출근표 있는 날 수, 건너뛰는 날을 뺀 평일 수).
  - `periods.missing_dates(period)`: 건너뛰는 날을 빼고 본다(따라서 `run_generation` 의 빈 날 오류·회차 화면의 빈 날 목록도).
  - `run_generation`: 관제 generator 에 건너뛰는 날을 뺀 날짜 목록과 그 날짜의 출근만 넘긴다. 건너뛰는 날에 남은 `Commute` 는 건드리지 않는다. 건너뛰는 날이 없으면 generator 입력이 지금과 같아 같은 씨앗이면 같은 결과다.
  - 입력 표 화면: `_render_table` 의 행 사전에 `"closed": str`(까닭, 아니면 `""`). 템플릿은 그 행의 입력 칸을 `disabled`(보내지 않는다)로, 날짜 칸 아래에 `<small class="hol" title="까닭">까닭(12자까지)</small>`.
  - `duty.alarms.schedule.bizdays_back(d, n, closed=frozenset()) -> date`, `send_at(timing, offset, at_minute, day, start, closed=frozenset()) -> datetime`: 영업일 = 평일 ∧ `closed` 에 없는 날. 순수 그대로(휴장일 날짜 집합을 인자로).
  - `duty.alarms.plan.plan(..., today=None, closed=frozenset())`: `closed` 를 `_personal`·`_report` 의 `send_at` 에 넘긴다(두 내부 함수의 마지막 인자 `closed`).
  - `duty.services.alarm_runner.BIZ_BACK = timedelta(days=90)`; `collect(now)` 가 `frozenset(holidays.closed(today - BIZ_BACK, today + HORIZON))` 를 모든 근무표의 `plan(..., closed=...)` 에 넘긴다. `_valid` 는 그대로(시각 계산 가능 여부만 본다).
  - 마이그레이션 없음. **다음 번호는 그대로 0020.**

- [ ] **Step 1: 건너뛰는 날·빈 날 검사·입력 현황 테스트를 먼저 쓴다**

`tests/test_skip_days.py`(새 파일. 뒤 단계가 끝에 이어 붙인다. import 는 처음부터 다 넣는다):
```python
"""만드는 도구의 휴장일·근무 없음 건너뛰기(설계 5·6.3·6.5). 이름은 모두 가상."""
from datetime import date

import pytest

from duty.csv_io import CsvInvalid
from duty.models import Board, Commute, DutyAssignment, Holiday, Memo, Period, User
from duty.services import boards, collect, periods
from duty.services.generate import run_generation

S = Period.Status
HOL = date(2026, 11, 11)     # 수: 시험용 휴장일(사람이 추가)
NOWORK = date(2026, 11, 12)  # 목: 근무 없음 날
CSV_HEAD = "date,새벽,정상,석식교대,야간\n"


def d(day):
    return date(2026, 11, day)


@pytest.fixture
def period(it_board, fixed_today):
    fixed_today(d(1))
    Holiday.objects.create(date=HOL, name="시험 휴장")
    Memo.objects.create(board=it_board, scope="day", date=NOWORK, text="워크숍", no_work=True)
    return Period.objects.create(board=it_board, name="p", start_date=d(9), end_date=d(13), status=S.COLLECTING)


# ── skip_dates ──

def test_skip_dates_are_no_work_days_and_holidays(period):
    assert boards.skip_dates(period) == {HOL, NOWORK}
    assert boards.skip_reasons(period) == {HOL: "시험 휴장", NOWORK: "워크숍"}


def test_old_period_keeps_holidays_but_never_no_work_days(period):
    period.skip_holidays = False  # 2단계 전에 만든 회차: 휴장일 규칙 미적용
    period.save()
    assert boards.skip_dates(period) == {NOWORK}


def test_inactive_holiday_and_other_board_memo_do_not_count(period, it_board):
    Holiday.objects.filter(date=HOL).update(active=False)
    other = Board.objects.create(code="ops", name="시장운영실", input_mode="direct")
    Memo.objects.create(board=other, scope="day", date=d(13), text="딴 근무표", no_work=True)
    Memo.objects.create(board=it_board, scope="day", date=d(10), text="그냥 메모")
    assert boards.skip_dates(period) == {NOWORK}


def test_empty_no_work_memo_reason(period):
    Memo.objects.filter(date=NOWORK).update(text="")
    assert boards.skip_reasons(period)[NOWORK] == "근무 없음"


# ── 빈 날 검사·입력 현황 ──

def _fill(period, members, days):
    for day in days:
        for m in members:
            Commute.objects.create(period=period, date=day, member=m, shift="normal")


def test_missing_dates_and_progress_skip_closed_days(period, make_member):
    ms = [make_member(n, dept=c) for n, c in [("가", "MEMS"), ("나", "TMCH"), ("다", "MD"), ("라", "UI")]]
    _fill(period, ms, [d(9), d(10), d(13)])
    assert periods.missing_dates(period) == {}
    assert collect.progress(period)["MEMS"] == (3, 3)
    Commute.objects.filter(date=d(13), member=ms[3]).delete()
    assert periods.missing_dates(period) == {"UI": [d(13)]}
    assert collect.progress(period)["UI"] == (2, 3)


def test_missing_dates_old_period_counts_holiday(period, make_member):
    period.skip_holidays = False
    period.save()
    ms = [make_member(n, dept=c) for n, c in [("가", "MEMS"), ("나", "TMCH"), ("다", "MD"), ("라", "UI")]]
    _fill(period, ms, [d(9), d(10), d(13)])
    assert periods.missing_dates(period) == {c: [HOL] for c in ["MD", "MEMS", "TMCH", "UI"]}
    assert collect.progress(period)["MEMS"] == (3, 4)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_skip_days.py`
Expected: 6 failed — `AttributeError: module 'duty.services.boards' has no attribute 'skip_dates'`(또는 `skip_reasons`), 빈 날 테스트 둘은 `assert {...} == {}` 류로 실패.

- [ ] **Step 3: `skip_dates` 를 만들고 빈 날 검사·입력 현황에 쓴다**

`duty/services/boards.py` — import 한 줄을 더하고 파일 끝에 두 함수를 붙인다(`memos`·`holidays` 는 `boards` 를 import 하지 않아 순환이 없다):
```diff
@@ -6,6 +6,7 @@ from django.db.models.functions import Coalesce
 
 from ..models import Board, BoardShift, Period, PeriodEvent
 from ..shifts import Def, ordered, weekdays
+from . import holidays, memos
 
 
 def it_board() -> Board:
@@ -66,3 +67,17 @@ def owners(board, start: date | None, end: date | None) -> dict[date, Period]:
         if p is not None:
             out[x] = p
     return out
+
+
+def skip_reasons(period: Period) -> dict[date, str]:
+    """만드는 도구(입력 표·CSV·생성·빈 날 검사)가 건너뛰는 날 {날짜: 까닭}(설계 5·6.5).
+    근무 없음 날은 늘(까닭 = 메모 글), 휴장일은 period.skip_holidays 일 때만(2단계 전 회차는 거짓)."""
+    out = holidays.closed(period.start_date, period.end_date) if period.skip_holidays else {}
+    for x, memo in memos.for_range(period.board, period.start_date, period.end_date)[memos.DAY].items():
+        if memo.no_work:
+            out[x] = memo.text or "근무 없음"
+    return out
+
+
+def skip_dates(period: Period) -> set[date]:
+    return set(skip_reasons(period))
```

`duty/services/periods.py` — `missing_dates`:
```diff
@@ -6,7 +6,7 @@ from django.db import transaction
 from .. import perms
 from ..errors import DutyError
 from ..models import ChangeLog, Commute, Department, DutyAssignment, Period, PeriodEvent
-from . import holidays
+from . import boards, holidays
 
 S = Period.Status
 
@@ -76,13 +76,14 @@ def delete(period: Period) -> None:
 
 
 def missing_dates(period: Period) -> dict[str, list[date]]:
-    """그 근무표 부서마다 출근표가 하나도 없는 평일."""
+    """그 근무표 부서마다 출근표가 하나도 없는 평일. 건너뛰는 날(근무 없음·휴장일)은 빼고 본다."""
     have: dict[str, set[date]] = defaultdict(set)
     for code, d in Commute.objects.filter(period=period).values_list("member__department", "date"):
         have[code].add(d)
+    skip = boards.skip_dates(period)
     out = {}
     for dept in Department.objects.filter(board_id=period.board_id).order_by("code"):
-        missing = [d for d in period.dates() if d not in have[dept.code]]
+        missing = [d for d in period.dates() if d not in have[dept.code] and d not in skip]
         if missing:
             out[dept.code] = missing
     return out
```

`duty/services/collect.py` — `progress`:
```diff
 def progress(period: Period) -> dict[str, tuple[int, int]]:
-    total = len(period.dates())
+    """부서마다 (출근표가 있는 날 수, 입력할 날 수). 건너뛰는 날은 양쪽에서 뺀다."""
+    skip = boards.skip_dates(period)
+    total = len([d for d in period.dates() if d not in skip])
     filled = dict(
-        Commute.objects.filter(period=period)
+        Commute.objects.filter(period=period).exclude(date__in=skip)
         .values("member__department")
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_skip_days.py tests/test_periods.py tests/test_boards_periods.py tests/test_collect.py`
Expected: 모두 passed.

- [ ] **Step 5: 출근표 서비스(CSV·표 저장·내려받기) 테스트를 붙이고 실패를 확인한다**

`tests/test_skip_days.py` 끝에 붙인다:
```python


# ── 출근표 입력(서비스·CSV) ──

@pytest.fixture
def mems(period, depts, make_member):
    mgr = make_member("담당", user=True)
    depts["MEMS"].managers.add(mgr)
    for n in ["가", "나"]:
        make_member(n)
    return period, depts["MEMS"], mgr


def test_csv_with_names_on_closed_day_is_rejected(mems):
    p, dept, user = mems
    raw = CSV_HEAD + f"{d(10)},가,,,\n{HOL},나,,,\n{NOWORK},,가,,\n"
    with pytest.raises(CsvInvalid) as e:
        collect.apply_csv(user, p, dept, raw.encode())
    got = {(x.column, x.reason) for x in e.value.errors}
    assert got == {(HOL.isoformat(), "시험 휴장: 근무를 넣지 않는 날입니다."),
                   (NOWORK.isoformat(), "워크숍: 근무를 넣지 않는 날입니다.")}
    assert not Commute.objects.exists()


def test_empty_closed_day_row_is_fine(mems):
    p, dept, user = mems
    raw = CSV_HEAD + f"{d(10)},가,,,\n{HOL},,,,\n"
    assert collect.apply_csv(user, p, dept, raw.encode()) == 1


def test_old_period_accepts_names_on_holiday(mems):
    p, dept, user = mems
    p.skip_holidays = False
    p.save()
    assert collect.apply_csv(user, p, dept, (CSV_HEAD + f"{HOL},나,,,\n").encode()) == 1


def test_save_keeps_rows_already_on_closed_day(mems, fixed_today):
    """휴장일을 나중에 추가해도 이미 넣은 행은 지우지 않는다(설계 5). 지난 날짜여도 일반 담당자의 저장을 막지 않는다."""
    p, dept, user = mems
    na = User.objects.get(name="나")
    Commute.objects.create(period=p, date=HOL, member=na, shift="dawn")
    fixed_today(d(12))  # HOL 은 지난 날짜
    assert collect.apply_table(user, p, dept, {d(13): {"normal": ["가"]}}) == 1
    assert set(Commute.objects.values_list("date", flat=True)) == {HOL, d(13)}


def test_export_leaves_closed_day_empty(mems):
    p, dept, user = mems
    Commute.objects.create(period=p, date=HOL, member=User.objects.get(name="나"), shift="dawn")
    lines = collect.export_csv(p, dept).decode("utf-8-sig").splitlines()
    assert lines[3] == f"{HOL},수,,,,"
    collect.apply_csv(user, p, dept, collect.export_csv(p, dept))  # 내려받은 그대로 다시 올려도 된다
```

Run: `.venv/bin/pytest -W error -q tests/test_skip_days.py`
Expected: 3 failed, 8 passed — `test_csv_with_names_on_closed_day_is_rejected`(`DID NOT RAISE CsvInvalid`), `test_save_keeps_rows_already_on_closed_day`(`CsvInvalid: CSV 오류 1건` — 지난 날짜 검사에 걸림), `test_export_leaves_closed_day_empty`(`'2026-11-11,수,나,,,' == '2026-11-11,수,,,,'`). 빈 줄·옛 회차 테스트 둘은 지금도 통과한다(바뀌면 안 되는 동작을 고정).

- [ ] **Step 6: `validate_table`·`apply_table`·`export_csv` 에 건너뛰는 날을 넣는다**

`duty/services/collect.py`:
```diff
@@ -67,11 +67,16 @@ def validate_table(user, period: Period, dept: Department, table: CommuteTable)
     existing = {d: {k: v for k, v in day.items() if k not in kept_keys} for d, day in loaded.items()}
     kept = {d: {n for k, v in day.items() if k in kept_keys for n in v} for d, day in loaded.items()}
     members = set(User.objects.roster().filter(department=dept).values_list("name", flat=True))
+    skip = boards.skip_reasons(period)
     for d in sorted(table):
         col = d.isoformat()
         if d not in valid_dates:
             add_error(errors, CsvError(0, col, "회차 기간의 평일이 아닙니다."))
             continue
+        if d in skip:  # 건너뛰는 날은 비워 둔다. 이미 있는 행은 저장해도 남는다(apply_table)
+            if any(table[d].values()):
+                add_error(errors, CsvError(0, col, f"{skip[d]}: 근무를 넣지 않는 날입니다."))
+            continue
         if _norm(table[d]) == _norm(existing.get(d, {})):
             continue  # 변경 없는 날짜는 재검증하지 않는다 (퇴사자 이름이 남아 있어도 다른 수정을 막지 않음)
         seen: dict[str, str] = {}
@@ -90,7 +95,7 @@ def validate_table(user, period: Period, dept: Department, table: CommuteTable)
                     seen[name] = key
     if not perms.is_board_admin(user, period.board):
         today = perms.today()
-        for d in sorted(x for x in set(table) | set(existing) if x < today):
+        for d in sorted(x for x in set(table) | set(existing) if x < today and x not in skip):
             if _norm(table.get(d, {})) != _norm(existing.get(d, {})):
                 add_error(errors, CsvError(0, d.isoformat(), "지난 날짜는 어드민만 수정할 수 있습니다."))
     return errors
@@ -104,7 +109,8 @@ def apply_table(user, period: Period, dept: Department, table: CommuteTable) ->
     if errors:
         raise CsvInvalid(errors)
     by_name = {m.name: m for m in User.objects.filter(department=dept)}
-    Commute.objects.filter(period=period, member__department=dept).exclude(shift__in=_kept_keys(dept)).delete()
+    (Commute.objects.filter(period=period, member__department=dept)
+     .exclude(shift__in=_kept_keys(dept)).exclude(date__in=boards.skip_dates(period)).delete())
     rows = [
         Commute(period=period, date=d, member=by_name[n], shift=key)
         for d, day in table.items()
@@ def export_csv @@
 def export_csv(period: Period, dept: Department) -> bytes:
     _same_board(period, dept)
-    return export_commute_csv(period.dates(), shift_names(dept), load_table(period, dept))
+    skip = boards.skip_dates(period)  # 건너뛰는 날은 빈 줄로(내려받은 그대로 다시 올려도 오류가 없게)
+    table = {d: day for d, day in load_table(period, dept).items() if d not in skip}
+    return export_commute_csv(period.dates(), shift_names(dept), table)
```

- [ ] **Step 7: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_skip_days.py tests/test_collect.py tests/test_views_collect.py tests/test_csv_io.py`
Expected: 모두 passed.

- [ ] **Step 8: 입력 표 화면 테스트를 붙이고 실패를 확인한다**

`tests/test_skip_days.py` 끝에 붙인다:
```python


# ── 출근표 입력 표(화면) ──

def test_table_locks_closed_rows(client, mems):
    p, dept, user = mems
    client.force_login(user)
    body = client.get(f"/collect/{p.pk}/MEMS/").content.decode()
    assert f'name="c_{HOL}_dawn" value="" disabled' in body
    assert f'name="c_{NOWORK}_normal" value="" disabled' in body
    assert f'name="c_{d(10)}_dawn" value="" >' in body
    assert '<small class="hol" title="시험 휴장">시험 휴장</small>' in body
    assert '<small class="hol" title="워크숍">워크숍</small>' in body


def test_table_post_on_closed_day_is_rejected(client, mems):
    p, dept, user = mems
    client.force_login(user)
    r = client.post(f"/collect/{p.pk}/MEMS/", {f"c_{HOL}_dawn": "가", f"c_{d(10)}_dawn": "나"})
    assert r.status_code == 400 and "시험 휴장: 근무를 넣지 않는 날입니다." in r.content.decode()
    assert not Commute.objects.exists()
```

Run: `.venv/bin/pytest -W error -q tests/test_skip_days.py -k table`
Expected: 1 failed(`test_table_locks_closed_rows`: `disabled` 가 없다), 1 passed(POST 거절은 Step 6 의 서비스 검사로 이미 된다 — 화면에서 보낸 값도 같은 길을 탄다는 고정).

- [ ] **Step 9: 입력 표의 그날 행을 잠근다**

`duty/views/collect.py`:
```diff
@@ -9,7 +9,7 @@ from .. import perms
 from ..csv_io import CsvInvalid, split_names
 from ..errors import DutyError
 from ..models import Department, Period, User
-from ..services import collect
+from ..services import boards, collect
 from ..shifts import DAY_LABELS
 
 MAX_UPLOAD = 1_000_000
@@ -41,9 +41,10 @@ def _load(request, pid, code):
 def _render_table(request, period, dept, table, errors):
     keys = collect.input_keys(dept)
     today, admin = perms.today(), perms.is_board_admin(request.user, period.board)
+    skip = boards.skip_reasons(period)  # 건너뛰는 날: 칸을 잠그고(disabled 라 보내지 않는다) 까닭을 보인다
     rows = [
         {
-            "date": d, "weekday": DAY_LABELS[d.weekday()], "locked": d < today and not admin,
+            "date": d, "weekday": DAY_LABELS[d.weekday()], "locked": d < today and not admin, "closed": skip.get(d, ""),
             "cells": [{"name": f"c_{d.isoformat()}_{k}", "value": ", ".join(table.get(d, {}).get(k, []))} for k in keys],
         }
         for d in period.dates()
```

`duty/templates/duty/collect_table.html` — 본문 행:
```diff
@@ -21,8 +21,8 @@
 <table class="roster">
   <thead><tr><th>날짜</th><th>요일</th>{% for s in shift_labels %}<th>{{ s }}</th>{% endfor %}</tr></thead>
   <tbody>{% for r in rows %}
-    <tr><td class="nw">{{ r.date|date:"Y-m-d" }}</td><td>{{ r.weekday }}</td>
-      {% for c in r.cells %}<td><input name="{{ c.name }}" value="{{ c.value }}" {% if r.locked %}readonly{% endif %}></td>{% endfor %}
+    <tr><td class="nw">{{ r.date|date:"Y-m-d" }}{% if r.closed %}<br><small class="hol" title="{{ r.closed }}">{{ r.closed|truncatechars:12 }}</small>{% endif %}</td><td>{{ r.weekday }}</td>
+      {% for c in r.cells %}<td><input name="{{ c.name }}" value="{{ c.value }}" {% if r.closed %}disabled{% elif r.locked %}readonly{% endif %}></td>{% endfor %}
     </tr>{% endfor %}</tbody>
 </table>
 </div>
```

`disabled` 칸은 폼에 실리지 않으므로 표 저장 때 그날은 빈 날로 오고, `apply_table` 은 그날의 기존 행을 남긴다. 까닭은 날짜 칸(`td.nw`, 줄바꿈 없음)에 넣는다 — 요일 칸에 넣으면 390px 에서 한 글자씩 접힌다(캡처로 확인). 긴 메모 글은 12자에서 자르고 `title` 에 전체를 둔다.

- [ ] **Step 10: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_skip_days.py tests/test_views_collect.py`
Expected: 모두 passed.

- [ ] **Step 11: 브라우저로 확인한다(CLAUDE.md, PC 1400px·모바일 390px)**

가짜 데이터 DB 를 따로 만들어 확인하고 끝나면 지운다(실제 `data/` 는 쓰지 않고, `DUTY_ENV_FILE=` 로 루트 `.env` 도 읽지 않는다. Task 8 과 같은 방식):
```bash
W=$(mktemp -d)
export DUTY_ENV_FILE= DUTY_DEBUG=1 DUTY_DATA_DIR=$W/data
.venv/bin/python manage.py migrate
.venv/bin/python manage.py shell -c '
from datetime import date
from duty.models import Board, Department, Holiday, Memo, Period, User
b = Board.objects.get(code="it")
dept, _ = Department.objects.get_or_create(code="MEMS", defaults=dict(name="매칭엔진실", shifts="dawn,normal,dinner,night", board=b))
u = User.objects.create_user("mgr1", password="unused-Pw-123", name="담당자", department=dept, part="", type="개발자", help_dismissed=True)
u.groups.add(b.admin_group)
for i in range(3):
    User.objects.create_user(f"m{i}", password=None, name=f"가상{i}", department=dept, part="", type="개발자")
Holiday.objects.create(date=date(2026, 11, 11), name="시험 휴장")
Memo.objects.create(board=b, scope="day", date=date(2026, 11, 12), text="워크숍", no_work=True)
print(Period.objects.create(board=b, name="확인용", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13), status="collecting").pk)'
.venv/bin/python manage.py runserver
```
`mgr1` / `unused-Pw-123` 로 로그인해 `/collect/<pk>/MEMS/` 를 1400px·390px 에서 본다:
- 11일 행은 칸이 흐리게 잠기고 날짜 아래 빨간 "시험 휴장", 12일 행은 "워크숍". 다른 날은 지금과 같다.
- 390px 에서 까닭이 한 글자씩 접히지 않는다(날짜 칸에 한 줄).
- 11일에 이름을 넣을 수 없고, CSV 로 11일에 이름을 넣으면 "시험 휴장: 근무를 넣지 않는 날입니다." 오류.
- `/collect/` 목록의 입력 현황이 "0 / 3일" 로 보인다(5일 중 2일을 뺌).
확인 뒤 서버를 끄고 `rm -rf "$W"`.

- [ ] **Step 12: 생성 테스트를 붙이고 실패를 확인한다**

`tests/test_skip_days.py` 끝에 붙인다:
```python


# ── 생성 ──

@pytest.fixture
def staffed(period, make_member):
    """test_generate 와 같은 인원(관제 10칸이 다 차는). days 에만 출근표를 넣는다."""
    normal = [make_member(f"N{i}", dept="MEMS") for i in range(7)] + [make_member("엠", dept="MD", type="직원"),
                                                                     make_member("유", dept="UI", type="직원")]
    dinner = [make_member(f"D{i}", dept="TMCH") for i in range(7)]

    def fill(days):
        for x in days:
            Commute.objects.bulk_create([Commute(period=period, date=x, member=m, shift="normal") for m in normal]
                                        + [Commute(period=period, date=x, member=m, shift="dinner") for m in dinner])
    period.status = S.CLOSED
    period.save()
    return period, fill


def test_generation_skips_closed_days(staffed):
    p, fill = staffed
    fill([d(9), d(10), d(13)])  # 건너뛰는 날은 출근표가 비어도 생성된다
    run_generation(p, seed=5)
    assert set(DutyAssignment.objects.values_list("date", flat=True)) == {d(9), d(10), d(13)}


def test_generation_ignores_rows_left_on_holiday(staffed):
    p, fill = staffed
    fill(p.dates())  # 휴장일을 나중에 추가해 행이 남아 있어도 관제는 만들지 않는다
    run_generation(p, seed=5)
    assert HOL not in set(DutyAssignment.objects.values_list("date", flat=True))
    assert Commute.objects.filter(date=HOL).exists()


def test_old_period_generates_on_holiday(staffed):
    p, fill = staffed
    p.skip_holidays = False
    p.save()
    fill([d(9), d(10), HOL, d(13)])
    run_generation(p, seed=5)
    assert set(DutyAssignment.objects.values_list("date", flat=True)) == {d(9), d(10), HOL, d(13)}
```

Run: `.venv/bin/pytest -W error -q tests/test_skip_days.py -k generat`
Expected: 3 failed — 둘은 `GenerationError: 배정할 수 없는 칸 20개`/`10개`(건너뛰는 날에 출근이 없어 칸을 못 채움), `test_generation_ignores_rows_left_on_holiday` 는 `assert datetime.date(2026, 11, 11) not in {...}`. (빈 날 오류는 Step 3 의 `missing_dates` 로 이미 나지 않는다.)

- [ ] **Step 13: 생성에서 건너뛰는 날을 뺀다**

`duty/services/generate.py` — `run_generation`(Task 1 의 `holidays.sync` 뒤라 표가 채워진 상태에서 읽는다):
```diff
@@ -28,16 +28,19 @@ def run_generation(period: Period, seed: int | None = None, by=None) -> Generati
     if seed is None:
         seed = random.SystemRandom().randrange(2**31)
 
+    skip = boards.skip_dates(period)  # 근무 없음 날·휴장일(skip_holidays)은 당번을 만들지 않는다. 남은 출근 행은 그대로 둔다
+    dates = [d for d in period.dates() if d not in skip]
     slots = slot_defs(boards.active_defs(period.board))  # 인덱스 i ↔ 칸 키 slots[i].key. 꺼진 관제는 생성하지 않는다
     if slots:
         commutes: dict = defaultdict(lambda: defaultdict(set))
-        for d, shift, code in Commute.objects.filter(period=period).values_list("date", "shift", "member__username"):
+        rows = Commute.objects.filter(period=period).exclude(date__in=skip)
+        for d, shift, code in rows.values_list("date", "shift", "member__username"):
             commutes[d][shift].add(code)
         members_by_type: dict = defaultdict(set)  # 그 근무표 부서 재직자. 칸별 유형 거르기는 generator 가 한다
         for typ, code in User.objects.roster().filter(department__board=period.board).values_list("type", "username"):
             members_by_type[typ].add(code)
         out = generate_control_duty(
-            period.dates(), commutes, dict(members_by_type), seed,
+            dates, commutes, dict(members_by_type), seed,
             [(x.name, x.eligible_shifts, x.eligible_types) for x in slots],
         )  # GenerationError 전파
     else:  # 장중관제 정의가 없는 근무표는 생성기를 부르지 않는다
```

- [ ] **Step 14: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_skip_days.py tests/test_generate.py tests/test_boards_generate.py tests/test_generator.py`
Expected: 모두 passed(기존 생성 테스트는 휴장일·근무 없음이 없는 11월이라 결과가 같다).

- [ ] **Step 15: 영업일 테스트를 붙이고 실패를 확인한다**

`tests/test_alarm_schedule.py` 끝에:
```python


def test_bizdays_skip_closed_days():
    """영업일 기준은 휴장일을 영업일에서 뺀다(설계 5·8.1). 휴장일 집합은 인자로(순수 모듈)."""
    fri, thu = date(2026, 11, 13), date(2026, 11, 12)
    assert bizdays_back(MON, 1, {fri}) == thu
    assert bizdays_back(MON, 2, {fri, date(2026, 11, 14)}) == date(2026, 11, 11)  # 주말 휴장일은 영향 없음
    start = datetime(2026, 11, 16, 6, 30)
    assert send_at("bizdays", 1, 17 * 60, MON, start, {fri}) == datetime(2026, 11, 12, 17, 0)
    assert send_at("days", 1, 18 * 60, MON, start, {date(2026, 11, 15)}) == datetime(2026, 11, 15, 18, 0)  # 날 기준은 그대로
```

`tests/test_alarm_plan.py` 끝에:
```python


def test_bizdays_rule_moves_before_holiday():
    r = rule(timing="bizdays", offset=1, at_minute=17 * 60, shifts=("dawn",))
    thu17 = datetime(2026, 11, 12, 17)
    assert run([r], [day(dawn=["가"])], thu17) == []
    assert len(run([r], [day(dawn=["가"])], thu17, closed={date(2026, 11, 13)})) == 1
```

`tests/test_run_alarms.py` — import 줄에 `Holiday` 를 더하고 끝에:
```diff
@@ -6,7 +6,7 @@ from django.core.management import call_command
 from django.utils import timezone
 
 from duty.alarms import senders
-from duty.models import (AlarmDelivery, AlarmRule, AlarmSettings, Commute, Period, PushAlarmSubscription,
+from duty.models import (AlarmDelivery, AlarmRule, AlarmSettings, Commute, Holiday, Period, PushAlarmSubscription,
                          TelegramAlarmProfile)
 from duty.services import alarm_runner, alarms, boards
 
@@ -503,3 +503,19 @@ def test_push_owner_changed_during_send(member, fake, make_member):
     alarm_runner.tick(SUN18)
     assert fake.dests() == ["111"]
     assert not AlarmDelivery.objects.filter(destination=f"sub:{s.id}").exists()
+
+
+def test_bizdays_rule_uses_holiday_table(member, fake, fixed_today):
+    """작업자는 휴장일 표(켜진 것)를 계획에 넘긴다: 금요일이 휴장일이면 '1영업일 전'은 목요일."""
+    verify(member)
+    keep = AlarmRule.objects.filter(user=member).first()
+    AlarmRule.objects.exclude(pk=keep.pk).delete()
+    AlarmRule.objects.filter(pk=keep.pk).update(timing="bizdays", offset=1, at_minute=17 * 60, shifts=["dawn"])
+    fixed_today(date(2026, 11, 12))
+    thu17 = at(2026, 11, 12, 17)
+    assert alarm_runner.tick(thu17) == (0, 0, 0)
+    h = Holiday.objects.create(date=date(2026, 11, 13), name="시험 휴장", active=False)
+    assert alarm_runner.tick(thu17) == (0, 0, 0)  # 꺼진 휴장일은 영업일
+    h.active = True
+    h.save()
+    assert alarm_runner.tick(thu17) == (1, 1, 0)
```

Run: `.venv/bin/pytest -W error -q tests/test_alarm_schedule.py tests/test_alarm_plan.py tests/test_run_alarms.py`
Expected: 3 failed — `TypeError: bizdays_back() takes 2 positional arguments but 3 were given`, `TypeError: plan() got an unexpected keyword argument 'closed'`, `assert (0, 0, 0) == (1, 1, 0)`.

- [ ] **Step 16: 영업일 계산에 휴장일 집합을 넘긴다**

`duty/alarms/schedule.py`(순수 그대로, 집합은 인자):
```diff
@@ -4,23 +4,24 @@ from datetime import date, datetime, time, timedelta
 from ..shifts import SLOT_GROUP_NAME, cell_end, cell_label, cell_start, cells_of, is_slot_cell
 
 
-def bizdays_back(d: date, n: int) -> date:
+def bizdays_back(d: date, n: int, closed=frozenset()) -> date:
+    """d 에서 n 영업일 전. 영업일 = 평일 중 closed(휴장일 날짜 집합)에 없는 날."""
     if n < 0:
         raise ValueError("영업일 수는 0 이상이어야 합니다.")
     while n:
         d -= timedelta(days=1)
-        if d.weekday() < 5:
+        if d.weekday() < 5 and d not in closed:
             n -= 1
     return d
 
 
-def send_at(timing: str, offset: int, at_minute: int, day: date, start: datetime) -> datetime:
+def send_at(timing: str, offset: int, at_minute: int, day: date, start: datetime, closed=frozenset()) -> datetime:
     if timing == "before_start":
         return start - timedelta(minutes=offset)
     if timing == "days":
         base = day - timedelta(days=offset)
     elif timing == "bizdays":
-        base = bizdays_back(day, offset)
+        base = bizdays_back(day, offset, closed)
     else:
         raise ValueError("알 수 없는 발송 시점입니다.")
     return datetime.combine(base, time(at_minute // 60, at_minute % 60))
```

`duty/alarms/plan.py`:
```diff
@@ -47,8 +47,8 @@ def _hash(prefix: str, text: str) -> str:
 
 
 def plan(defs, rules, days, info, deliveries, now, destinations=None, dept_names=None, extra_dates=None,
-         today=None) -> list[Due]:
-    """defs: 이 근무표의 정의. destinations: (rule_id, channel) → 목적지 목록.
+         today=None, closed=frozenset()) -> list[Due]:
+    """defs: 이 근무표의 정의. destinations: (rule_id, channel) → 목적지 목록. closed: 휴장일 날짜 집합(영업일 계산).
     deliveries: (rule_id, date, cell, channel, destination) → 그 목적지에 마지막으로 성공한 내용 hash(없으면 None)."""
     today = today or now.date()
     destinations = destinations or {}
@@ -66,10 +66,10 @@ def plan(defs, rules, days, info, deliveries, now, destinations=None, dept_names
             starts = {c: datetime.combine(day.date, cell_start(defs, c)) for c in cells}
             if r.kind == "personal":
                 if r.member_name:
-                    out += _personal(defs, r, day, cells, starts, deliveries, now, destinations, today)
+                    out += _personal(defs, r, day, cells, starts, deliveries, now, destinations, today, closed)
             elif r.kind == "report":
                 out += _report(defs, r, day, cells, starts, info, deliveries, now, dept_names, day.date in synthetic,
-                               destinations)
+                               destinations, closed)
     return out
 
 
@@ -94,11 +94,11 @@ def _targets(r, destinations):
     return [(ch, dest) for ch in r.channels for dest in destinations.get((r.id, ch), ())]
 
 
-def _personal(defs, r, day, cells, starts, deliveries, now, destinations, today):
+def _personal(defs, r, day, cells, starts, deliveries, now, destinations, today, closed):
     out = []
     for c in cells:
         start = starts[c]
-        if not send_at(r.timing, r.offset, r.at_minute, day.date, start) <= now < start:
+        if not send_at(r.timing, r.offset, r.at_minute, day.date, start, closed) <= now < start:
             continue
         inside = r.member_name in day.members.get(c, [])
         if inside:
@@ -119,9 +119,9 @@ def _personal(defs, r, day, cells, starts, deliveries, now, destinations, today)
     return out
 
 
-def _report(defs, r, day, cells, starts, info, deliveries, now, dept_names, synthetic, destinations):
+def _report(defs, r, day, cells, starts, info, deliveries, now, dept_names, synthetic, destinations, closed):
     first, last_start = min(starts.values()), max(starts.values())
-    if not send_at(r.timing, r.offset, r.at_minute, day.date, first) <= now < last_start:
+    if not send_at(r.timing, r.offset, r.at_minute, day.date, first, closed) <= now < last_start:
         return []
 
     def keep(name):
```

`duty/services/alarm_runner.py`:
```diff
@@ -15,12 +15,13 @@ from ..alarms.plan import RuleSpec, plan
 from ..alarms.schedule import send_at
 from ..models import (AlarmDelivery, AlarmDeliveryStatus, AlarmRule, Board, Department,
                       PushAlarmSubscription, TelegramAlarmProfile, User)
-from . import alarm_settings, boards
+from . import alarm_settings, boards, holidays
 from .alarms import RULE_FIELDS
 from .roster import published_days
 
 log = logging.getLogger(__name__)
 HORIZON = timedelta(days=45)
+BIZ_BACK = timedelta(days=90)  # 영업일 기준 최대 30영업일 전 + 긴 연휴 여유: 이만큼 앞의 휴장일까지 읽는다
 KEEP = timedelta(days=7)
 LIMIT = 4000  # 텔레그램 본문 최대 길이
 
@@ -102,6 +103,7 @@ def collect(now):
     destinations = _destinations(rules, alarm_settings.current())
     dept_names = dict(Department.objects.values_list("code", "name"))
     local_now = timezone.localtime(now).replace(tzinfo=None)
+    closed = frozenset(holidays.closed(today - BIZ_BACK, today + HORIZON))  # 모든 근무표 공통(설계 5)
     dues = []
     for board in Board.objects.filter(pk__in=list(by_board)).order_by("id"):
         group = by_board[board.id]
@@ -114,7 +116,7 @@ def collect(now):
         days = [d for d in published_days(board, today, today + HORIZON) if any(d.members.values())]
         dues += plan(boards.defs(board), specs, days, info, deliveries, local_now,
                      destinations=destinations, dept_names=dept_names,
-                     extra_dates={k[1] for k in rows if k[0] in ids}, today=today)
+                     extra_dates={k[1] for k in rows if k[0] in ids}, today=today, closed=closed)
     out = []
     for due in dues:
         row = rows.get((due.rule_id, due.date, due.cell, due.channel, due.destination))
```

`BIZ_BACK`: 규칙의 영업일 수는 1~30(DB 제약), 30영업일은 달력으로 약 42일이고 설·추석 같은 연휴를 더해도 90일 안이다. `HORIZON`(45일) 끝까지의 휴장일도 읽어야 먼 날 근무의 발송일을 맞게 센다.

- [ ] **Step 17: 통과·전체 테스트·마이그레이션 검사**

Run: `.venv/bin/pytest -W error -q tests/test_alarm_schedule.py tests/test_alarm_plan.py tests/test_run_alarms.py tests/test_alarm_texts_it.py`
Expected: 모두 passed(IT 문구 고정 테스트 그대로).

Run: `.venv/bin/pytest -W error -q`
Expected: 경고 0개, 모두 passed(참고값: Task 2 뒤 980 + 새 19 = **999 passed**).

Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --check`
Expected: `No changes detected in app 'duty'`

- [ ] **Step 18: 커밋한다**

```bash
git add duty/services/boards.py duty/services/periods.py duty/services/collect.py duty/services/generate.py \
  duty/views/collect.py duty/templates/duty/collect_table.html \
  duty/alarms/schedule.py duty/alarms/plan.py duty/services/alarm_runner.py \
  tests/test_skip_days.py tests/test_alarm_schedule.py tests/test_alarm_plan.py tests/test_run_alarms.py
git commit -m "feat: 입력 표·CSV·생성·빈 날 검사가 휴장일·근무 없음 날을 건너뛰고, 영업일 알림은 휴장일을 영업일에서 뺌"
```
(커밋 메시지 끝에 대화의 attribution 줄을 붙인다.)

**뒤 작업이 알아야 할 점**
- 점심당번 채우기(`run_generation` 3단계)는 Step 13 의 `skip`·`dates` 를 그대로 쓰면 된다(같은 함수 안, 관제 다음).
- direct 확정의 "빈 평일 경고 목록"은 `missing_dates` 를 쓰면 이미 건너뛰는 날이 빠져 있다.
- 입력 표에서 건너뛰는 날의 기존 행은 보이기만 하고(잠김) 지울 길은 근무 없음 메모(Task 2, 모든 회차 행을 지움)뿐이다. 휴장일을 끄면 다시 열린다.
- 문서(ARCHITECTURE·OPERATIONS)에 적을 것: 건너뛰는 날 = 근무 없음(늘) ∪ 휴장일(`skip_holidays` 회차만), 영업일은 켜진 휴장일 전부를 뺌, 휴장일을 나중에 추가해도 이미 넣은 출근 행은 남음.


---

### Task 4: 사유(휴가·출장·교육)

> 검증: Task 1·2·3 을 넣은 `feat/boards-phase2` 사본(999 passed)에 아래 코드를 그대로 넣어 확인했다. 저장소는 고치지 않았다. 결과: `.venv/bin/pytest -W error -q` → **1043 passed**(999 + 새 44), 경고 0개. `makemigrations duty --check` → "No changes detected in app 'duty'". 단계별 실패도 사본에서 하나씩 재현했다(각 단계에 적었다). 가짜 데이터(가상 이름, 끝나면 지움)로 그린 주간·월간·하루 화면과 근무 변경 창을 headless Chrome 으로 1400·390px 캡처해 확인했다. 클릭으로 하는 팝업 동작은 직접 해 보지 않았다(Step 16 에서 사람이 확인). 검증 뒤 일관성 리뷰로 이름 검사를 0020 에서 0018 맨 앞으로 옮기고(마이그레이션 테스트 2건 수정, 개수 같음) 브라우저 확인 환경을 `DUTY_ENV_FILE=` 방식으로 바꿨다. 이 둘은 사본에서 다시 돌리지 않았으니 Step 2·23 에서 확인한다.
>
> 이 작업의 범위(설계 2·3·4.6·4.7·6.2·6.4·7·8.1~8.3·10): `Commute.reason`, `ChangeLog.reason_before/after`, 마이그레이션 0020(스키마만) 과 0018 맨 앞의 이름 검사(이름이 (휴가)·(출장)·(교육)으로 끝나는 계정이 있으면 2단계 마이그레이션이 하나도 적용되기 전에 멈춤), `validate_member_name` 금지 추가, `csv_io` 의 사유 접미 순수 함수(`split_reason`·`join_reason`), 입력 표·CSV 의 `이름(휴가)`, 근무 변경 창 근무조 칸의 사유 선택과 `changes.set_reason`(기록만, 변경 알림 없음, 당번 칸에 남아 있으면 경고), 화면 이름 뒤 작은 "(휴가)"(변경 내역을 꺼도 보임), `published_days`·`change_notice` 가 사유만 바뀐 기록을 건너뜀, 근무로 치지 않음(개인 알림·캘린더·관제 생성 후보·통계에서 빠짐), 보고서 "이름(휴가)", 이력 화면 "가 → 가(휴가)", `publish_undo` c 행의 여섯째 칸.
> 규칙: 사유는 **근무조 배정(Commute)에만** 붙는다. 사람이 옮겨 가면(맞교환) 사유도 따라가고, 빠지면(빼기·교체·근무 없음) 그 기록의 `reason_before` 에 남는다. 사유만 바뀐 기록은 `before == after`(같은 사람)이다.
> 하지 않는 것(뒤 작업): 점심당번(Task 5 — `set_reason` 의 경고는 그날 그 사람의 모든 당번 배정을 보므로 lunch 행이 생기면 "점심당번 칸에 남아 있습니다"가 따로 손대지 않아도 나온다. 점심당번 채우기는 `Commute.reason == ""` 인 사람만 본다), 채우기 버튼의 "사유 제외"(3단계), 문서(ARCHITECTURE·OPERATIONS·OVERVIEW·help STEPS).
> IT 알림 문구·hash 는 사유가 없으면 바뀌지 않는다(보고서 줄은 사유가 있는 이름만 `가(휴가)`). `tests/test_alarm_texts_it.py` 그대로 통과. 기존 테스트는 하나도 고치지 않는다.

**Files:**
- Modify: `duty/shifts.py`(상수 `REASONS` 한 줄)
- Modify: `duty/csv_io.py`(import, `split_reason`·`join_reason`)
- Modify: `duty/models.py`(import, `validate_member_name`, `REASON_CHOICES`, `Period.publish_undo` 주석, `Commute.reason`, `ChangeLog.reason_before/after` 와 제약 3개)
- Create: `duty/migrations/0020_reasons.py`(스키마만)
- Modify: `duty/migrations/0018_holidays.py`(Task 1 이 만든 같은 브랜치의 미배포 파일. 맨 앞에 `check_names` 하나)
- Modify: `duty/services/collect.py`(import, `load_table`, `validate_table`, `apply_table`)
- Modify: `duty/services/changes.py`(import, `change_cell` 의 기록 한 줄, 새 `set_reason`)
- Modify: `duty/services/memos.py`(`_clear_day` 의 기록 한 줄)
- Modify: `duty/services/roster.py`(import, `Day.reasons`, `published_days`, `member_schedule`)
- Modify: `duty/services/change_notice.py`(`tick` 의 사유만 바뀐 기록 건너뛰기)
- Modify: `duty/views/manage.py`(import, `change_log` 의 before/after 표시)
- Modify: `duty/views/roster.py`(import, `_item`·`_items`·`_lines`·새 `_why`, `_cell_context`, `roster` 의 `day_cells`, `cell` POST, `day` 의 items)
- Modify: `duty/templates/duty/_labels.html`, `_cell_form.html`, `day.html`, `collect_table.html`, `base.html`(`.rsn`)
- Modify: `duty/alarms/plan.py`(import, `_personal`, `_report`), `duty/services/calendar.py`(`_events`), `duty/services/generate.py`(`run_generation` 의 출근 읽기), `duty/services/stats.py`(`member_stats`, `period_duty_counts`)
- Modify: `duty/services/publish.py`(`_MODELS`, `publish`, `unpublish`)
- Test: `tests/test_reasons.py`(새 파일. 뒤 단계가 끝에 이어 붙인다), `tests/test_migration_reasons.py`(새 파일)

**Interfaces:**
- Consumes: (1단계) `Commute(period, date, member, shift)`, `DutyAssignment(period, date, cell, member)`, `ChangeLog(by, period, date, cell, before, after, notified)`, `Period.publish_undo`, `changes._owner(board, d)`·`change_cell`·`exchange`·`swap`, `perms.assert_can_edit(user, board, d)`, `boards.defs(board)`, `shifts.cell_label(defs, key)`·`is_slot_cell`·`SLOT_GROUP_NAME`, `roster.Day(date, period_id, cells, members, replaced)`·`published_days`·`find_day`·`member_schedule`, `alarms.plan.plan`·`_personal`·`_report`, `messages.report_line(defs, cell, names)`, `calendar._events(member, shifts)`, `stats.member_stats`·`period_duty_counts`, `collect.load_table/validate_table/apply_table/apply_csv/export_csv`, `views/roster._cell_context`·`cell`·`day`, conftest `it_board`·`depts`·`make_member`·`admin_user`·`admin_client_ok`·`fixed_today`. (Task 2) `memos.save(..., no_work=True, confirm=True)`·`memos._clear_day`, `changes._owner` 의 근무 없음 검사. (Task 3) `boards.skip_reasons/skip_dates`, `run_generation` 의 `skip`·`dates`, `collect.validate_table` 의 건너뛰는 날 검사.
- Produces:
  - `duty.shifts.REASONS = ("휴가", "출장", "교육")`. `duty.models` 가 같은 이름으로 다시 내보낸다(`from duty.models import REASONS`). `duty.models.REASON_CHOICES = [("", "없음"), ("휴가", "휴가"), ("출장", "출장"), ("교육", "교육")]`.
  - `Commute.reason = CharField(max_length=4, choices=REASON_CHOICES, blank=True, default="")` + 제약 `commute_reason_valid`. 빈 값 = 근무로 친다.
  - `ChangeLog.reason_before`, `ChangeLog.reason_after`(같은 꼴) + 제약 `changelog_reason_before_valid`·`changelog_reason_after_valid`.
  - 마이그레이션 `0018_holidays`(2단계 첫 마이그레이션) 맨 앞에 `RunPython(check_names, noop)` — 이름이 `(휴가)`·`(출장)`·`(교육)`으로 끝나는 계정이 있으면 이름을 알려 주며 `RuntimeError`. 앱 코드를 import 하지 않는다. 마이그레이션은 파일 단위 트랜잭션(SQLite)이므로 걸리면 0018 도 되돌려져 DB 는 0017 그대로다(0018·0019 가 반쯤 올라간 채 멈추지 않는다). 나머지 0018 작업(AddField·AlterField·CreateModel)은 그대로.
  - 마이그레이션 `0020_reasons`(의존 0019_memo): 스키마만 — AddField 3개·AddConstraint 3개(설계 10절 "스키마와 데이터 이전은 파일로 나눈다"). **다음 번호 0021.**
  - `duty.models.validate_member_name`: `split_reason(value)[1]` 이 있으면 `ValidationError("이름이 (휴가)·(출장)·(교육)으로 끝날 수 없습니다.")`.
  - `duty.csv_io.split_reason(text: str) -> tuple[str, str]`: 끝이 정확히 `(휴가)`·`(출장)`·`(교육)`이고 앞 이름이 비지 않을 때만 `(이름(앞 공백 지움), 사유)`, 아니면 `(text, "")`. `duty.csv_io.join_reason(name: str, reason: str) -> str`: `"이름(사유)"` 또는 `name`.
  - `collect.load_table`: 이름 칸이 `join_reason(이름, 사유)`(따라서 입력 표·CSV 내려받기에 `가(휴가)`). `validate_table`: 사람 검사·중복 검사·꺼진 근무조 검사는 사유를 뗀 이름으로, 사유만 바꿔도 "바뀐 날"이다(지난 날짜 검사에 걸린다). `apply_table`: `Commute(..., reason=사유)`. 모르는 접미(`가(병가)`)는 그대로 이름으로 보아 "재직 멤버가 아닙니다".
  - `duty.services.changes.set_reason(user, board, d: date, member: User, reason: str) -> list[str]`: `assert_can_edit` → `_owner`(근무 없음 날 막힘) → 사유 검사(`"알 수 없는 사유입니다."`) → 그날 그 사람 근무조 행(없으면 `"{이름}은(는) 그날 근무조에 없습니다."`, 같으면 `"변경할 내용이 없습니다."`) → `ChangeLog(cell=행의 근무조, before=after=member, reason_before=옛 사유, reason_after=새 사유)` → 저장. 사유를 붙였고 그날 그 사람의 당번 배정(`DutyAssignment`, 회차 = 주인)이 있으면 경고 `"{이름}은(는) 그날 {칸들} 칸에 남아 있습니다. 다른 사람으로 바꾸세요."`(관제는 "장중관제 08:30~09:30", 그 밖의 당번은 정의 이름 — Task 5 뒤 "점심당번"). 당번 칸을 자동으로 빼지 않는다. 변경 알림·개인 알림 취소 없음.
  - `changes.change_cell`: 근무조 행을 빼거나 교체할 때 `ChangeLog.reason_before = 빠진 행의 사유`. `swap` 은 행의 근무조만 바꾸므로 사유가 사람을 따라간다. `memos._clear_day` 도 지운 근무조 행의 사유를 `reason_before` 에 남긴다.
  - `duty.services.roster.Day.reasons: dict[tuple[str, str], str]`(기본 빈 사전, `(칸 키, 이름) → 사유`). 위치 인자 다섯 개로 만드는 기존 코드(`plan._empty`, 테스트)는 그대로 된다. `published_days` 가 주인 회차의 근무조 행에서 채운다. 사유만 바뀐 기록(`before == after`)은 `logs` 에 넣지 않으므로 `chain` 의 A>B·취소선과 `Cell.changed` 에 나타나지 않는다(이력 화면에는 남는다).
  - `member_schedule`: 근무조 라벨이 `정상(휴가)`.
  - `change_notice.tick`: `before_id == after_id` 인 기록은 짝짓기 전에 건너뛴다(표시는 다른 기록과 같이 notified=True).
  - 이력 화면(`views/manage.change_log`): before/after 칸이 `join_reason(이름, reason_before/after)`, 예 `가 → 가(휴가)`.
  - 화면: `views/roster._item(label, names, removed=False, reasons=None)` 의 사전에 `"reason"`(마지막 이름의 사유, 빠진 사람은 `""`), `_items`·`_lines(..., reasons=None)` 가 넘긴다. `_why(day, cell) -> dict[str, str]`(그 칸 {이름: 사유}). `_labels.html` 이 이름 뒤에 `<small class="rsn">(휴가)</small>`. `_cell_context` 의 `current_members` 객체에 `.reason`, 사전에 `"reason_choices": REASONS`. `_cell_form.html` 은 근무조 칸이고 지금 사람이 있을 때 두 번째 폼(`<hr>` 아래): `member`(User **pk** — 위 폼의 username option 과 겹치지 않게), `reason`(빈 값 = 없음), 버튼 `name="set_reason" value="1"`. `cell` 뷰 POST 에 `set_reason` 이 있으면 `changes.set_reason` 을 부르고 성공 메시지 `"사유를 저장했습니다."`, 경고는 messages.warning. `day.html` 의 include 에 `reason_choices=s.reason_choices`.
  - 근무로 치지 않음: `plan._personal` 은 `(칸, 이름) in day.reasons` 면 그 칸을 건너뛴다(알림도, 이미 보낸 알림의 취소도 없다). `plan._report` 는 줄의 이름을 `join_reason` 으로(`새벽(06:30~) 가(출장), 나`), 요약 인원(`· N명`)은 사유 없는 사람만. `calendar._events` 는 사유가 있는 근무조 일정을 뺀다(남은 당번 일정은 그대로). `run_generation` 의 관제 후보 출근은 `reason=""` 만. `stats.member_stats` 의 새벽·야간 횟수는 사유 없는 배정만, `period_duty_counts` 의 모집단도 `reason=""`(생성 후보와 같게).
  - `publish._MODELS = {"c": (Commute, ("shift", "reason")), "a": (DutyAssignment, ("cell",))}`. `publish_undo` c 행 = `["c", 회차, 날짜, 멤버, 근무조, 사유]`(여섯째 칸, 빈 값 포함), a 행은 다섯 칸 그대로. `unpublish` 는 `zip(fields, 남은 칸)` 으로 읽어 다섯 칸짜리 옛 c 행은 사유 없음으로 되살린다. Task 5 의 마이그레이션이 lunch `a` 행을 더할 때 `["a", p, d, m, "lunch"]` 다섯 칸이면 된다.

- [ ] **Step 1: 값·이름 규칙·마이그레이션 테스트를 먼저 쓴다**

`tests/test_reasons.py`(새 파일. 뒤 단계가 끝에 이어 붙인다. import 는 처음부터 다 넣는다):
```python
"""사유(휴가·출장·교육, 설계 2·4.6·4.7·6.2·6.4·7·8). 사유가 붙은 배정은 근무로 치지 않는다. 이름은 모두 가상."""
from datetime import date, datetime, timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from duty.csv_io import CsvInvalid, join_reason, split_reason
from duty.errors import DutyError
from duty.models import (REASONS, ChangeLog, Commute, DutyAssignment, Period, RosterPref, TelegramAlarmProfile,
                         validate_member_name)
from duty.alarms.plan import RuleSpec, plan
from duty.services import alarm_settings, calendar, change_notice, changes, collect, memos, publish, stats
from duty.services.generate import run_generation
from duty.services.roster import Day, find_day
from duty.shifts import KEYS
from tests.it_defs import IT_DEFS

S = Period.Status


# ── 값·이름 규칙·순수 함수 ──

def test_reasons_constant():
    assert REASONS == ("휴가", "출장", "교육")


@pytest.mark.parametrize("raw, expected", [
    ("가상일(휴가)", ("가상일", "휴가")),
    ("가상일(출장)", ("가상일", "출장")),
    ("가상일 (교육)", ("가상일", "교육")),
    ("가상일", ("가상일", "")),
    ("가상일(휴가) ", ("가상일(휴가) ", "")),  # 끝이 정확히 (사유)일 때만(split_names 가 이미 양끝 공백을 뗀다)
    ("가상일(병가)", ("가상일(병가)", "")),
    ("가상일(휴가)x", ("가상일(휴가)x", "")),
    ("(휴가)", ("(휴가)", "")),  # 이름이 비면 사유로 떼지 않는다
])
def test_split_reason(raw, expected):
    assert split_reason(raw) == expected


def test_join_reason():
    assert join_reason("가상일", "휴가") == "가상일(휴가)"
    assert join_reason("가상일", "") == "가상일"
    assert split_reason(join_reason("가상일", "출장")) == ("가상일", "출장")


@pytest.mark.parametrize("name", ["가상일(휴가)", "가상일(출장)", "가상일 (교육)"])
def test_member_name_cannot_end_with_reason(name):
    with pytest.raises(ValidationError, match="휴가"):
        validate_member_name(name)


def test_member_name_other_parentheses_ok():
    validate_member_name("가상일(A)")


def test_reason_db_constraints(make_member, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=date(2026, 11, 16), end_date=date(2026, 11, 20))
    m = make_member("가")
    c = Commute.objects.create(period=p, date=date(2026, 11, 16), member=m, shift="dawn")
    assert c.reason == ""
    Commute.objects.filter(pk=c.pk).update(reason="휴가")
    with pytest.raises(IntegrityError), transaction.atomic():
        Commute.objects.filter(pk=c.pk).update(reason="병가")
    log = ChangeLog.objects.create(period=p, date=c.date, cell="dawn", before=m, after=m, reason_after="출장")
    assert log.reason_before == ""
    with pytest.raises(IntegrityError), transaction.atomic():
        ChangeLog.objects.filter(pk=log.pk).update(reason_before="병가")
```

`tests/test_migration_reasons.py`(새 파일. `test_migration_holidays.py` 와 같은 틀):
```python
"""2단계 첫 마이그레이션 0018 이 맨 앞에서 이름이 (휴가)·(출장)·(교육)으로 끝나는 계정을 찾으면 아무것도 적용하지 않고 멈춘다.
0020 은 사유 칸을 더한다(설계 10절 2단계). 이름은 모두 가상."""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0017_alarmrule_board_rules")]
AFTER = [("duty", "0018_holidays")]
REASONS = [("duty", "0020_reasons")]


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_apps():
    apps = _migrate(BEFORE)
    yield apps
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())  # 다른 테스트를 위해 최신 스키마로


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_stops_when_name_ends_with_reason(old_apps):
    User = old_apps.get_model("duty", "User")
    u = User.objects.create(username="T001", name="가상일(휴가)")
    with pytest.raises(RuntimeError, match=r"가상일\(휴가\)"):
        _migrate(AFTER)
    # 0018 이 통째로 되돌려졌다: 휴장일 표도 skip_holidays 도 없다
    tables = connection.introspection.table_names()
    assert "duty_holiday" not in tables
    assert "skip_holidays" not in {c.name for c in connection.introspection.get_table_description(connection.cursor(), "duty_period")}
    User.objects.filter(pk=u.pk).delete()  # 정리해야 픽스처가 최신 스키마로 올릴 수 있다


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_passes_and_adds_empty_reason(old_apps):
    old_apps.get_model("duty", "User").objects.create(username="T002", name="가상이(A)")
    _migrate(AFTER)
    apps = _migrate(REASONS)
    assert apps.get_model("duty", "User").objects.filter(name="가상이(A)").exists()
    assert {f.name for f in apps.get_model("duty", "Commute")._meta.fields} >= {"reason"}
    assert {f.name for f in apps.get_model("duty", "ChangeLog")._meta.fields} >= {"reason_before", "reason_after"}
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_reasons.py tests/test_migration_reasons.py`
Expected: `tests/test_reasons.py` 수집 오류 1건 — `ImportError: cannot import name 'join_reason' from 'duty.csv_io'`. `tests/test_migration_reasons.py` 는 2건 실패 — `test_stops_when_name_ends_with_reason` 은 `Failed: DID NOT RAISE <class 'RuntimeError'>`(0018 에 검사가 아직 없다), `test_passes_and_adds_empty_reason` 은 `0020_reasons` 가 없어 `KeyError`/`NodeNotFoundError`.

- [ ] **Step 3: 상수·순수 함수·모델·마이그레이션을 만든다**

`duty/shifts.py`·`duty/csv_io.py`·`duty/models.py`(`csv_io` 는 `shifts` 만 import 하므로 `models` → `csv_io` 순환이 없다):
```diff
diff --git a/duty/csv_io.py b/duty/csv_io.py
--- a/duty/csv_io.py
+++ b/duty/csv_io.py
@@ -6,7 +6,7 @@ import re
 from dataclasses import dataclass
 from datetime import date
 
-from .shifts import DAY_LABELS
+from .shifts import DAY_LABELS, REASONS
 
 CommuteTable = dict[date, dict[str, list[str]]]
 
@@ -51,6 +51,19 @@ def split_names(cell: str) -> list[str]:
     return [n.strip() for n in _NAME_SPLIT.split(cell or "") if n.strip()]
 
 
+def split_reason(text: str) -> tuple[str, str]:
+    """'이름(휴가)' → ('이름', '휴가'). 끝이 정확히 (휴가)·(출장)·(교육)일 때만 떼고(앞 공백은 지운다), 아니면 (text, '')."""
+    for r in REASONS:
+        name = text.removesuffix(f"({r})").rstrip()
+        if name != text.rstrip() and name:
+            return name, r
+    return text, ""
+
+
+def join_reason(name: str, reason: str) -> str:
+    return f"{name}({reason})" if reason else name
+
+
 def header_key(h: str) -> str:
     return re.split(r"[\n(]", h, maxsplit=1)[0].strip()
 
diff --git a/duty/models.py b/duty/models.py
--- a/duty/models.py
+++ b/duty/models.py
@@ -6,7 +6,11 @@ from django.db import models
 from django.db.models import F, Func, Q, Value
 from django.db.models.lookups import Exact
 
-from .shifts import DEVELOPER, KEYS, SHIFT_KEYS, SLOT_KEYS, STAFF, is_slot_cell, slot_index, weekdays
+from .csv_io import split_reason
+from .shifts import DEVELOPER, KEYS, REASONS, SHIFT_KEYS, SLOT_KEYS, STAFF, is_slot_cell, slot_index, weekdays
+
+
+REASON_CHOICES = [("", "없음"), *((r, r) for r in REASONS)]
 
 
 def _one_of(field: str, values, name: str) -> models.CheckConstraint:
@@ -25,6 +29,8 @@ def validate_member_name(value: str) -> None:
     # 앞 = - @ 탭은 CSV 를 엑셀로 열 때 수식으로 실행된다
     if any(c in value for c in ">,\n\r") or value.startswith(("+", "=", "-", "@", "\t")):
         raise ValidationError("이름에 > , 줄바꿈을 쓸 수 없고 + = - @ 탭으로 시작할 수 없습니다.")
+    if split_reason(value)[1]:  # 표·CSV 의 "이름(휴가)"와 헷갈린다
+        raise ValidationError("이름이 (휴가)·(출장)·(교육)으로 끝날 수 없습니다.")
 
 
 class InputMode(models.TextChoices):
@@ -288,11 +294,13 @@ class Commute(models.Model):
     date = models.DateField()
     member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
     shift = models.CharField(max_length=8, choices=[(k, k) for k in SHIFT_KEYS])
+    reason = models.CharField(max_length=4, choices=REASON_CHOICES, blank=True, default="")  # 있으면 근무로 치지 않는다
 
     class Meta:
         constraints = [
             models.UniqueConstraint(fields=["period", "date", "member"], name="commute_one_shift_per_day"),
             _one_of("shift", SHIFT_KEYS, "commute_shift_valid"),
+            _one_of("reason", ["", *REASONS], "commute_reason_valid"),
         ]
         indexes = [models.Index(fields=["date"])]
 
@@ -324,11 +332,16 @@ class ChangeLog(models.Model):
     before = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
     after = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
     notified = models.BooleanField(default=False)  # 당사자에게 '근무 변경' 알림을 보냈는지(작업자가 표시)
+    # 사유(근무조 칸만). 사유만 바뀐 기록은 before == after: 이력에만 보이고 화면 변경 표시·변경 알림은 건너뛴다
+    reason_before = models.CharField(max_length=4, choices=REASON_CHOICES, blank=True, default="")
+    reason_after = models.CharField(max_length=4, choices=REASON_CHOICES, blank=True, default="")
 
     class Meta:
         ordering = ["at", "id"]
         constraints = [
             _one_of("cell", KEYS, "changelog_cell_valid"),
+            _one_of("reason_before", ["", *REASONS], "changelog_reason_before_valid"),
+            _one_of("reason_after", ["", *REASONS], "changelog_reason_after_valid"),
             models.CheckConstraint(condition=models.Q(before__isnull=False) | models.Q(after__isnull=False), name="changelog_not_empty"),
         ]
 
diff --git a/duty/shifts.py b/duty/shifts.py
--- a/duty/shifts.py
+++ b/duty/shifts.py
@@ -18,6 +18,7 @@ STAFF = "직원"
 TARGET_SPREAD = 2
 MAX_SWAP_ITERATIONS = 10000
 DAY_LABELS = "월화수목금토일"
+REASONS = ("휴가", "출장", "교육")  # 사유: 붙으면 그날 근무로 치지 않는다(설계 2절). 표·CSV 에는 "이름(휴가)"
 
 
 @dataclass(frozen=True)
```

이름 검사는 2단계 첫 마이그레이션 `0018_holidays` 맨 앞에 넣는다(Task 1 이 같은 브랜치에서 만든 미배포 파일이므로 고쳐도 된다). 걸리면 0018 트랜잭션이 통째로 되돌려져 아무것도 적용되지 않는다. `duty/migrations/0018_holidays.py` 에 더하는 부분(나머지 operations 는 그대로):
```diff
--- a/duty/migrations/0018_holidays.py
+++ b/duty/migrations/0018_holidays.py
@@
 from django.db import migrations, models
 
+SUFFIXES = ("(휴가)", "(출장)", "(교육)")
+
+
+def check_names(apps, schema_editor):
+    """표·CSV 의 "이름(휴가)"와 헷갈리는 계정 이름이 있으면 2단계를 시작하기 전에 멈춘다(설계 10절 2단계, Task 4).
+    2단계 첫 마이그레이션의 맨 앞이라 걸리면 아무것도 적용되지 않는다. 앱 코드를 import 하지 않는다."""
+    User = apps.get_model("duty", "User")
+    taken = sorted(n for n in User.objects.values_list("name", flat=True) if n.endswith(SUFFIXES))
+    if taken:
+        raise RuntimeError(
+            f"이름이 (휴가)·(출장)·(교육)으로 끝나는 계정이 있어 멈춥니다: {', '.join(taken)}. DB 는 바뀌지 않았습니다. "
+            '옛 버전 코드로 되돌려(docs/OPERATIONS.md "업그레이드·롤백") 관리 화면에서 그 이름을 바꾸고 업그레이드를 다시 하세요.')
+
 
 class Migration(migrations.Migration):
 
     dependencies = [
         ('duty', '0017_alarmrule_board_rules'),
     ]
 
     operations = [
+        migrations.RunPython(check_names, migrations.RunPython.noop),
         # 기존 회차는 거짓(사용자 결정 "다음에 만드는 회차부터"), 그다음 모델 기본값을 참으로(이후 만드는 회차)
         migrations.AddField(
```

사유 칸은 `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty -n reasons` 로 만든다(스키마만, 손대지 않음). 완성본 `duty/migrations/0020_reasons.py`:
```python
# Generated by Django 5.2.19 on 2026-11-15 13:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('duty', '0019_memo'),
    ]

    operations = [
        migrations.AddField(
            model_name='changelog',
            name='reason_after',
            field=models.CharField(blank=True, choices=[('', '없음'), ('휴가', '휴가'), ('출장', '출장'), ('교육', '교육')], default='', max_length=4),
        ),
        migrations.AddField(
            model_name='changelog',
            name='reason_before',
            field=models.CharField(blank=True, choices=[('', '없음'), ('휴가', '휴가'), ('출장', '출장'), ('교육', '교육')], default='', max_length=4),
        ),
        migrations.AddField(
            model_name='commute',
            name='reason',
            field=models.CharField(blank=True, choices=[('', '없음'), ('휴가', '휴가'), ('출장', '출장'), ('교육', '교육')], default='', max_length=4),
        ),
        migrations.AddConstraint(
            model_name='changelog',
            constraint=models.CheckConstraint(condition=models.Q(('reason_before__in', ['', '휴가', '출장', '교육'])), name='changelog_reason_before_valid'),
        ),
        migrations.AddConstraint(
            model_name='changelog',
            constraint=models.CheckConstraint(condition=models.Q(('reason_after__in', ['', '휴가', '출장', '교육'])), name='changelog_reason_after_valid'),
        ),
        migrations.AddConstraint(
            model_name='commute',
            constraint=models.CheckConstraint(condition=models.Q(('reason__in', ['', '휴가', '출장', '교육'])), name='commute_reason_valid'),
        ),
    ]
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_reasons.py tests/test_migration_reasons.py tests/test_user_model.py tests/test_csv_io.py`
Expected: 모두 통과(사본 39 passed).
Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --check`
Expected: `No changes detected in app 'duty'`

- [ ] **Step 5: 입력 표·CSV 테스트를 붙인다**

`tests/test_reasons.py` 끝에:
```python
# ── 출근표 입력 표·CSV ──

D = date(2026, 11, 9)  # 월
HEAD = "date,새벽,정상,석식교대,야간\n"


@pytest.fixture
def collecting(depts, make_member, fixed_today, it_board):
    fixed_today(date(2026, 11, 1))
    p = Period.objects.create(board=it_board, name="p", start_date=D, end_date=date(2026, 11, 13), status=S.COLLECTING)
    mgr = make_member("담당", user=True)
    depts["MEMS"].managers.add(mgr)
    for n in ["가", "나", "다"]:
        make_member(n)
    return p, depts["MEMS"], mgr


def test_table_reads_and_writes_reason(collecting):
    p, dept, user = collecting
    assert collect.apply_table(user, p, dept, {D: {"dawn": ["가(휴가)"], "normal": ["나", "다(출장)"]}}) == 3
    assert dict(Commute.objects.values_list("member__name", "reason")) == {"가": "휴가", "나": "", "다": "출장"}
    assert collect.load_table(p, dept)[D] == {"dawn": ["가(휴가)"], "normal": ["나", "다(출장)"]}


def test_csv_reason_roundtrip(collecting):
    p, dept, user = collecting
    collect.apply_csv(user, p, dept, (HEAD + '2026-11-09,가(교육),"나, 다",,\n').encode())
    assert Commute.objects.get(member__name="가").reason == "교육"
    out = collect.export_csv(p, dept).decode("utf-8-sig")
    assert "2026-11-09,월,가(교육),\"나, 다\"" in out
    assert collect.apply_csv(user, p, dept, out.encode()) == 3  # 내려받은 그대로 다시 올려도 된다
    assert Commute.objects.get(member__name="가").reason == "교육"


def test_unknown_reason_is_not_a_member(collecting):
    p, dept, user = collecting
    with pytest.raises(CsvInvalid) as e:
        collect.apply_table(user, p, dept, {D: {"dawn": ["가(병가)"]}})
    assert "재직 멤버가 아닙니다: 가(병가)" in e.value.errors[0].reason


def test_reason_does_not_hide_double_shift(collecting):
    p, dept, user = collecting
    with pytest.raises(CsvInvalid) as e:
        collect.apply_table(user, p, dept, {D: {"dawn": ["가(휴가)"], "night": ["가"]}})
    assert "가: 새벽·야간에 중복" in e.value.errors[0].reason


def test_changing_only_reason_is_a_change(collecting, fixed_today):
    p, dept, user = collecting
    collect.apply_table(user, p, dept, {D: {"dawn": ["가"]}})
    fixed_today(date(2026, 11, 10))  # 일반 담당자에게 지난 날짜
    with pytest.raises(CsvInvalid) as e:
        collect.apply_table(user, p, dept, {D: {"dawn": ["가(휴가)"]}})
    assert "지난 날짜" in e.value.errors[0].reason
```

- [ ] **Step 6: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_reasons.py`
Expected: 4 failed, 16 passed — 사유 붙은 이름이 "재직 멤버가 아닙니다: 가(휴가)" 로 막히고(`CsvInvalid`), `test_unknown_reason_is_not_a_member` 만 이미 통과.

- [ ] **Step 7: 출근표 서비스가 사유를 읽고 쓰게 한다**

`duty/services/collect.py`:
```diff
diff --git a/duty/services/collect.py b/duty/services/collect.py
--- a/duty/services/collect.py
+++ b/duty/services/collect.py
@@ -3,7 +3,8 @@ from django.db import transaction
 from django.db.models import Count
 
 from .. import perms
-from ..csv_io import CommuteTable, CsvError, CsvInvalid, add_error, export_commute_csv, parse_commute_csv
+from ..csv_io import (CommuteTable, CsvError, CsvInvalid, add_error, export_commute_csv, join_reason, parse_commute_csv,
+                      split_reason)
 from ..errors import DutyError
 from ..models import Commute, Department, Period, User
 from ..shifts import by_key, shift_defs
@@ -41,6 +42,7 @@ def shift_names(dept: Department) -> dict[str, str]:
 
 
 def load_table(period: Period, dept: Department) -> CommuteTable:
+    """표·CSV 의 이름은 사유가 있으면 "이름(휴가)"."""
     _same_board(period, dept)
     table: CommuteTable = {}
     rows = (
@@ -49,7 +51,7 @@ def load_table(period: Period, dept: Department) -> CommuteTable:
         .order_by("date", "member__username")
     )
     for c in rows:
-        table.setdefault(c.date, {}).setdefault(c.shift, []).append(c.member.name)
+        table.setdefault(c.date, {}).setdefault(c.shift, []).append(join_reason(c.member.name, c.reason))
     return table
 
 
@@ -65,7 +67,7 @@ def validate_table(user, period: Period, dept: Department, table: CommuteTable)
     kept_keys = _kept_keys(dept)
     loaded = load_table(period, dept)
     existing = {d: {k: v for k, v in day.items() if k not in kept_keys} for d, day in loaded.items()}
-    kept = {d: {n for k, v in day.items() if k in kept_keys for n in v} for d, day in loaded.items()}
+    kept = {d: {split_reason(n)[0] for k, v in day.items() if k in kept_keys for n in v} for d, day in loaded.items()}
     members = set(User.objects.roster().filter(department=dept).values_list("name", flat=True))
     skip = boards.skip_reasons(period)
     for d in sorted(table):
@@ -84,7 +86,7 @@ def validate_table(user, period: Period, dept: Department, table: CommuteTable)
             if names and key not in shift_keys:
                 add_error(errors, CsvError(0, col, f"{dept.name}에는 {labels[key].name} 출근조가 없습니다."))
                 continue
-            for name in names:
+            for name in (split_reason(n)[0] for n in names):  # 사유는 떼고 사람만 본다
                 if name not in members:
                     add_error(errors, CsvError(0, col, f"{dept.name}의 재직 멤버가 아닙니다: {name}"))
                 elif name in kept.get(d, ()):
@@ -112,10 +114,10 @@ def apply_table(user, period: Period, dept: Department, table: CommuteTable) ->
     (Commute.objects.filter(period=period, member__department=dept)
      .exclude(shift__in=_kept_keys(dept)).exclude(date__in=boards.skip_dates(period)).delete())
     rows = [
-        Commute(period=period, date=d, member=by_name[n], shift=key)
+        Commute(period=period, date=d, member=by_name[name], shift=key, reason=why)
         for d, day in table.items()
         for key, names in day.items()
-        for n in names
+        for name, why in map(split_reason, names)
     ]
     Commute.objects.bulk_create(rows)
     return len(rows)
```

입력 표 화면(`views/collect.py`)은 고치지 않는다: 칸 값이 `load_table` 의 문자열이고 POST 도 `split_names` 로 읽어 `apply_table` 로 넘기므로 `가(휴가)` 가 그대로 오간다. 안내 문구는 Step 15 에서 바꾼다.

- [ ] **Step 8: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_reasons.py tests/test_collect.py tests/test_views_collect.py tests/test_skip_days.py`
Expected: 모두 통과(사본 63 passed).

- [ ] **Step 9: 사유 바꾸기·기록·변경 표시·변경 알림 테스트를 붙인다**

`tests/test_reasons.py` 끝에:
```python
# ── 사유 바꾸기(근무 변경 창)·기록·변경 표시·변경 알림 ──

T = date(2026, 11, 10)  # 화
NOW = timezone.make_aware(datetime(2026, 11, 10, 9, 0))


@pytest.fixture
def pub(make_member, fixed_today, it_board):
    fixed_today(T)
    p = Period.objects.create(board=it_board, name="p", start_date=T, end_date=T, status=S.PUBLISHED,
                              overwrite_from=T, published_at=NOW - timedelta(days=1))
    m = {n: make_member(n, user=True) for n in ["가", "나", "다"]}
    Commute.objects.create(period=p, date=T, member=m["가"], shift="normal")
    Commute.objects.create(period=p, date=T, member=m["나"], shift="dawn")
    DutyAssignment.objects.create(period=p, date=T, cell="slot0", member=m["가"])
    return p, m


def test_set_reason_records_without_changing_people(pub, it_board):
    p, m = pub
    warnings = changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    assert Commute.objects.get(member=m["가"]).reason == "휴가"
    log = ChangeLog.objects.get()
    assert (log.cell, log.before, log.after, log.reason_before, log.reason_after, log.by) == (
        "normal", m["가"], m["가"], "", "휴가", m["다"])
    # 당번 칸은 자동으로 빼지 않고 경고만(점심당번이 생기면 같은 경고가 "점심당번 칸"으로 나온다)
    assert warnings == ["가은(는) 그날 장중관제 08:30~09:30 칸에 남아 있습니다. 다른 사람으로 바꾸세요."]
    assert changes.set_reason(m["다"], it_board, T, m["나"], "출장") == []
    changes.set_reason(m["다"], it_board, T, m["가"], "")
    assert Commute.objects.get(member=m["가"]).reason == ""
    assert ChangeLog.objects.last().reason_before == "휴가"


@pytest.mark.parametrize("who, reason, msg", [
    ("가", "병가", "알 수 없는 사유"),
    ("가", "", "변경할 내용이 없습니다"),
    ("다", "휴가", "그날 근무조에 없습니다"),
])
def test_set_reason_rejects(pub, it_board, who, reason, msg):
    _, m = pub
    with pytest.raises(DutyError, match=msg):
        changes.set_reason(m["나"], it_board, T, m[who], reason)
    assert not ChangeLog.objects.exists()


def test_set_reason_needs_edit_permission(pub, it_board, fixed_today):
    _, m = pub
    fixed_today(T + timedelta(days=1))
    with pytest.raises(PermissionDenied):
        changes.set_reason(m["나"], it_board, T, m["가"], "휴가")  # 지난 날짜는 관리자만


def test_reason_only_log_is_not_a_change_on_screen(pub, it_board):
    _, m = pub
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    day = find_day(it_board, T)
    assert day.cells["normal"].labels == ["가"] and not day.cells["normal"].changed
    assert day.reasons == {("normal", "가"): "휴가"}
    changes.change_cell(m["다"], it_board, T, "normal", m["가"], m["다"])  # 뒤 기록의 A>B 는 그대로
    day = find_day(it_board, T)
    assert day.cells["normal"].labels == ["가>다"] and day.reasons == {}


def test_moves_keep_reason_with_person_and_log_it(pub, it_board):
    _, m = pub
    changes.set_reason(m["다"], it_board, T, m["가"], "교육")
    changes.swap(m["다"], it_board, T, "normal", m["가"], "dawn", m["나"])
    assert Commute.objects.get(member=m["가"]).reason == "교육" and Commute.objects.get(member=m["가"]).shift == "dawn"
    changes.change_cell(m["다"], it_board, T, "dawn", m["가"], None)  # 빼면 빠진 사람의 사유를 기록에 남긴다
    assert ChangeLog.objects.last().reason_before == "교육"


def test_change_notice_skips_reason_only_logs(pub, it_board, monkeypatch):
    _, m = pub
    conf = alarm_settings.current()
    conf.telegram_bot_token = "1234567890:" + "FAKE" + "x" * 31
    alarm_settings.save(conf)  # 토큰을 바꾸면 연결이 풀리므로 연결보다 먼저
    TelegramAlarmProfile.objects.create(user=m["가"], chat_id="11", verified_at=NOW)
    TelegramAlarmProfile.objects.create(user=m["나"], chat_id="22", verified_at=NOW)
    sent = []
    monkeypatch.setattr("duty.alarms.senders.telegram_send", lambda cfg, chat, text: sent.append((chat, text)) or {})
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    changes.exchange(m["다"], it_board, T, "normal", m["가"], m["나"])  # 맞교환 두 기록의 짝짓기도 그대로
    change_notice.tick(NOW)
    assert sorted(chat for chat, _ in sent) == ["11", "22"] and all("맞교환" in t for _, t in sent)
    assert not ChangeLog.objects.filter(notified=False).exists()


def test_clearing_no_work_day_logs_reason(pub, it_board, admin_user):
    _, m = pub
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    memos.save(admin_user, it_board, "day", T, "워크숍", no_work=True, confirm=True)
    assert ChangeLog.objects.get(cell="normal", after=None).reason_before == "휴가"


def test_history_page_shows_reason(pub, it_board, admin_client_ok):
    _, m = pub
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    body = admin_client_ok.get("/changes/").content.decode()
    assert "가 → 가(휴가)" in body
```

- [ ] **Step 10: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_reasons.py`
Expected: 10 failed, 20 passed — `AttributeError: module 'duty.services.changes' has no attribute 'set_reason'`.

- [ ] **Step 11: `set_reason`·기록의 사유·사유만 바뀐 기록 건너뛰기·이력 표시를 만든다**

`duty/services/changes.py`·`memos.py`·`roster.py`·`change_notice.py`, `duty/views/manage.py`:
```diff
diff --git a/duty/services/change_notice.py b/duty/services/change_notice.py
--- a/duty/services/change_notice.py
+++ b/duty/services/change_notice.py
@@ -24,6 +24,9 @@ def tick(now) -> int:
     defs_of = {}  # 근무표 id → 정의(문구는 그 기록의 회차 근무표 이름으로)
     while i < len(rows):
         r = rows[i]
+        if r.before_id == r.after_id:  # 사유만 바뀐 기록: 알림 없음(설계 6.4)
+            i += 1
+            continue
         pair = rows[i + 1] if i + 1 < len(rows) and _is_swap(r, rows[i + 1]) else None
         i += 2 if pair else 1
         if not _live(r, now, today):
diff --git a/duty/services/changes.py b/duty/services/changes.py
--- a/duty/services/changes.py
+++ b/duty/services/changes.py
@@ -5,7 +5,7 @@ from django.db import transaction
 from .. import perms
 from ..errors import DutyError
 from ..models import ChangeLog, Commute, DutyAssignment, Period, User
-from ..shifts import Def, by_key, cell_label, is_slot_cell
+from ..shifts import REASONS, SLOT_GROUP_NAME, Def, by_key, cell_label, is_slot_cell
 from . import boards, memos
 
 
@@ -99,10 +99,37 @@ def change_cell(user, board, d: date, cell: str, before: User | None, after: Use
         if after is not None:
             Commute.objects.create(period=period, date=d, member=after, shift=cell)
         warnings = _duty_warnings(defs, period, d, [before, after])
-    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell, before=before, after=after)
+    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell, before=before, after=after,
+                             reason_before=getattr(row, "reason", ""))  # 빠진 사람의 사유는 기록에 남긴다(관제 행에는 없다)
     return warnings
 
 
+@transaction.atomic
+def set_reason(user, board, d: date, member: User, reason: str) -> list[str]:
+    """근무조 배정에 사유(휴가·출장·교육, 빈 값 = 없음)를 붙이거나 뗀다. 사람은 그대로라 기록은 before == after 이고
+    변경 알림은 나가지 않는다(설계 6.4). 당번 칸은 자동으로 빼지 않고 경고만 한다. 이미 보낸 개인 알림은 되돌리지 않는다."""
+    perms.assert_can_edit(user, board, d)
+    period = _owner(board, d)
+    if reason not in ("", *REASONS):
+        raise DutyError("알 수 없는 사유입니다.")
+    row = Commute.objects.filter(period=period, date=d, member=member).first()
+    if row is None:
+        raise DutyError(f"{member.name}은(는) 그날 근무조에 없습니다.")
+    if row.reason == reason:
+        raise DutyError("변경할 내용이 없습니다.")
+    ChangeLog.objects.create(by=user, period=period, date=d, cell=row.shift, before=member, after=member,
+                             reason_before=row.reason, reason_after=reason)
+    row.reason = reason
+    row.save(update_fields=["reason"])
+    duties = DutyAssignment.objects.filter(period=period, date=d, member=member).order_by("cell") if reason else []
+    if not duties:
+        return []
+    defs = boards.defs(board)
+    labels = ", ".join(f"{SLOT_GROUP_NAME} {cell_label(defs, x.cell)}" if is_slot_cell(x.cell) else cell_label(defs, x.cell)
+                       for x in duties)
+    return [f"{member.name}은(는) 그날 {labels} 칸에 남아 있습니다. 다른 사람으로 바꾸세요."]
+
+
 @transaction.atomic
 def exchange(user, board, d: date, cell: str, before: User | None, after: User | None) -> list[str]:
     """근무 변경 창의 저장. 둘 다 있으면 기본은 맞교환: To 가 그날 같은 묶음 다른 칸에 있으면 서로 바꾸고,
diff --git a/duty/services/memos.py b/duty/services/memos.py
--- a/duty/services/memos.py
+++ b/duty/services/memos.py
@@ -48,7 +48,8 @@ def _clear_day(user, board, d: date) -> int:
     for rows, field in ((commutes, "shift"), (duties, "cell")):
         for r in rows:
             if r.period.status == Period.Status.PUBLISHED:
-                ChangeLog.objects.create(by=user, period=r.period, date=d, cell=getattr(r, field), before=r.member)
+                ChangeLog.objects.create(by=user, period=r.period, date=d, cell=getattr(r, field), before=r.member,
+                                         reason_before=getattr(r, "reason", ""))
     commutes.delete()
     duties.delete()
     return n
diff --git a/duty/services/roster.py b/duty/services/roster.py
--- a/duty/services/roster.py
+++ b/duty/services/roster.py
@@ -1,7 +1,7 @@
 """배포된 근무표 읽기 모델. 화면·통계·알림·캘린더가 공통으로 쓴다."""
 
 from collections import defaultdict
-from dataclasses import dataclass
+from dataclasses import dataclass, field
 from datetime import date
 
 from django.db.models import F
@@ -27,6 +27,7 @@ class Day:
     cells: dict[str, Cell]
     members: dict[str, list[str]]
     replaced: dict[tuple[str, str], str]
+    reasons: dict[tuple[str, str], str] = field(default_factory=dict)  # (칸, 이름) → 사유. 있으면 근무로 치지 않는다
 
 
 def chain(current: list[str], logs: list[Log]) -> tuple[list[str], list[str], dict[str, str]]:
@@ -56,18 +57,25 @@ def published_days(board, start: date | None = None, end: date | None = None) ->
     rng = {"period_id__in": set(owner_id.values()), "date__gte": min(owner_id), "date__lte": max(owner_id)}
 
     names: dict[tuple[date, str], list[str]] = defaultdict(list)
-    for model, field in ((Commute, "shift"), (DutyAssignment, "cell")):
-        rows = model.objects.filter(**rng).order_by("date", "member__username")
-        for d, pid, cell, name in rows.values_list("date", "period_id", field, "member__name"):
-            if owner_id.get(d) == pid:
-                names[(d, cell)].append(name)
+    reasons: dict[date, dict[tuple[str, str], str]] = defaultdict(dict)
+    rows = Commute.objects.filter(**rng).order_by("date", "member__username")
+    for d, pid, cell, name, why in rows.values_list("date", "period_id", "shift", "member__name", "reason"):
+        if owner_id.get(d) == pid:
+            names[(d, cell)].append(name)
+            if why:
+                reasons[d][(cell, name)] = why
+    rows = DutyAssignment.objects.filter(**rng).order_by("date", "member__username")
+    for d, pid, cell, name in rows.values_list("date", "period_id", "cell", "member__name"):
+        if owner_id.get(d) == pid:
+            names[(d, cell)].append(name)
 
     logs: dict[tuple[date, str], list[Log]] = defaultdict(list)
     # 배포 취소 이전 기록(log_floor 이하)은 다시 배포해도 쓰지 않는다(그사이 출근표·생성이 바뀌었을 수 있다)
     rows = (ChangeLog.objects.filter(**rng, id__gt=F("period__log_floor"))
             .order_by("at", "id").values_list("date", "period_id", "cell", "before__name", "after__name"))
     for d, pid, cell, before, after in rows:
-        if owner_id.get(d) == pid:  # 덮어쓰인 회차의 이력은 숨긴다
+        # 덮어쓰인 회차의 이력은 숨긴다. 사유만 바뀐 기록(before == after)은 변경 표시(A>B·취소선)에서 뺀다
+        if owner_id.get(d) == pid and before != after:
             logs[(d, cell)].append((before, after))
 
     days = []
@@ -80,7 +88,7 @@ def published_days(board, start: date | None = None, end: date | None = None) ->
             cells[cell] = Cell(labels, removed, bool(cell_logs))
             members[cell] = current
             replaced.update({(cell, name): prev for name, prev in rep.items()})
-        days.append(Day(d, owner_id[d], cells, members, replaced))
+        days.append(Day(d, owner_id[d], cells, members, replaced, reasons[d]))
     return days
 
 
diff --git a/duty/views/manage.py b/duty/views/manage.py
--- a/duty/views/manage.py
+++ b/duty/views/manage.py
@@ -8,6 +8,7 @@ from django.shortcuts import get_object_or_404, redirect, render
 from django.views.decorators.http import require_POST
 
 from .. import perms
+from ..csv_io import join_reason
 from ..errors import DutyError
 from ..generator import GenerationError
 from ..models import Board, ChangeLog, Period
@@ -201,8 +202,9 @@ def change_log(request):
     logs = [
         {
             "at": log.at, "by": (log.by.name or log.by.username) if log.by else "시트 가져오기", "date": log.date,
-            "cell": cell_label(defs[log.period.board_id], log.cell), "before": log.before.name if log.before else "",
-            "after": log.after.name if log.after else "", "period": log.period.name,
+            "cell": cell_label(defs[log.period.board_id], log.cell),
+            "before": join_reason(log.before.name, log.reason_before) if log.before else "",
+            "after": join_reason(log.after.name, log.reason_after) if log.after else "", "period": log.period.name,
         }
         for log in qs[:500]
     ]
```

`roster.py` 의 `field` 는 이제 `dataclasses.field` 다(옛 반복 변수 `field` 를 없앴다). `change_cell` 의 관제 분기에서 `row` 는 `DutyAssignment` 라 `getattr(row, "reason", "")` 로 읽는다.

- [ ] **Step 12: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_reasons.py tests/test_changes.py tests/test_change_notice.py tests/test_memos.py tests/test_views_manage.py tests/test_board_owner.py`
Expected: 모두 통과.
Run: `.venv/bin/pytest -W error -q`
Expected: 전체 통과(사본 1031 passed).

- [ ] **Step 13: 화면 테스트를 붙인다**

`tests/test_reasons.py` 끝에:
```python
# ── 화면: 이름 뒤 작은 (휴가), 근무 변경 창의 사유 선택, 입력 표 안내 ──

RSN = '<small class="rsn">(휴가)</small>'


def test_roster_and_day_show_reason_even_without_history(pub, it_board, client):
    _, m = pub
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    client.force_login(m["나"])
    for url in ["/?date=2026-11-10", "/?view=month&date=2026-11-10", "/day/2026-11-10/"]:
        body = client.get(url).content.decode()
        assert f"가{RSN}" in body and "<s>가</s>" not in body, url
        assert body.count(RSN) == 1, url  # 관제 칸의 가에는 붙지 않는다(사유는 근무조 배정에 붙는다)
    RosterPref.objects.update_or_create(user=m["나"], defaults={"history": False})  # 변경 내역을 꺼도 보인다
    assert f"가{RSN}" in client.get("/?date=2026-11-10").content.decode()


def test_cell_form_offers_reason_for_shift_cells_only(pub, client):
    _, m = pub
    client.force_login(m["나"])
    body = client.get("/cell/2026-11-10/normal/").content.decode()
    assert 'name="reason"' in body and "<option>휴가</option>" in body and "<option>교육</option>" in body
    assert 'name="reason"' not in client.get("/cell/2026-11-10/slot0/").content.decode()


def test_cell_post_sets_reason(pub, client):
    _, m = pub
    client.force_login(m["나"])
    r = client.post("/cell/2026-11-10/normal/", {"set_reason": "1", "member": m["가"].pk, "reason": "출장",
                                                 "next": "/day/2026-11-10/"}, follow=True)
    assert Commute.objects.get(member=m["가"]).reason == "출장"
    body = r.content.decode()
    assert "사유를 저장했습니다." in body and "장중관제 08:30~09:30 칸에 남아 있습니다" in body
    assert "가 (출장)" in client.get("/cell/2026-11-10/normal/").content.decode()  # From 목록에 지금 사유
    r = client.post("/cell/2026-11-10/normal/", {"set_reason": "1", "member": m["가"].pk, "reason": "출장"},
                    follow=True)
    assert "변경할 내용이 없습니다." in r.content.decode()
    r = client.post("/cell/2026-11-10/normal/", {"set_reason": "1", "member": "x", "reason": "휴가"}, follow=True)
    assert "사유를 붙일 사람을 골라 주세요." in r.content.decode()


def test_collect_table_explains_reason(collecting, client):
    p, dept, user = collecting
    client.force_login(user)
    assert "(휴가)처럼" in client.get(f"/collect/{p.pk}/{dept.code}/").content.decode()


def test_me_page_shows_reason(pub, it_board, client):
    _, m = pub
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    client.force_login(m["가"])
    assert "정상(휴가)" in client.get("/me/").content.decode()
```

- [ ] **Step 14: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_reasons.py`
Expected: 5 failed, 30 passed — 화면에 `<small class="rsn">` 이 없고, 근무 변경 창에 `name="reason"` 이 없고, 입력 표 안내·내 근무에 사유가 없다.

- [ ] **Step 15: 이름 뒤 작은 (휴가)·근무 변경 창의 사유 선택·안내 문구**

`duty/views/roster.py`, `duty/services/roster.py`(`member_schedule`), `_labels.html`·`day.html`·`collect_table.html`:
```diff
diff --git a/duty/services/roster.py b/duty/services/roster.py
--- a/duty/services/roster.py
+++ b/duty/services/roster.py
@@ -6,6 +6,7 @@ from datetime import date
 
 from django.db.models import F
 
+from ..csv_io import join_reason
 from ..models import ChangeLog, Commute, DutyAssignment, User
 from ..shifts import SLOT_GROUP_NAME, cell_label, is_slot_cell, ordered
 from . import boards
@@ -101,7 +102,8 @@ def member_schedule(board, member: User, start: date, shown=lambda cell: True) -
     defs = boards.defs(board)
     out = []
     for day in published_days(board, start, None):
-        labels = [f"{SLOT_GROUP_NAME} {cell_label(defs, c)}" if is_slot_cell(c) else cell_label(defs, c)
+        labels = [f"{SLOT_GROUP_NAME} {cell_label(defs, c)}" if is_slot_cell(c)
+                  else join_reason(cell_label(defs, c), day.reasons.get((c, member.name), ""))  # 정상(휴가)
                   for c, names in day.members.items() if shown(c) and member.name in names]
         if labels:
             out.append((day.date, labels))
diff --git a/duty/templates/duty/_labels.html b/duty/templates/duty/_labels.html
--- a/duty/templates/duty/_labels.html
+++ b/duty/templates/duty/_labels.html
@@ -1 +1 @@
-{% for l in line %}<span class="lb{% if l.changed %} chg{% endif %}">{% for t in l.tokens %}{% if t.hl %}<span class="hl{{ t.hl }}">{% endif %}{% if t.struck %}<s>{{ t.name }}</s>{% else %}{{ t.name }}{% endif %}{% if t.hl %}</span>{% endif %}{% if not forloop.last %}&gt;{% endif %}{% endfor %}</span>{% if not forloop.last %}, {% endif %}{% endfor %}
+{% for l in line %}<span class="lb{% if l.changed %} chg{% endif %}">{% for t in l.tokens %}{% if t.hl %}<span class="hl{{ t.hl }}">{% endif %}{% if t.struck %}<s>{{ t.name }}</s>{% else %}{{ t.name }}{% endif %}{% if t.hl %}</span>{% endif %}{% if not forloop.last %}&gt;{% endif %}{% endfor %}{% if l.reason %}<small class="rsn">({{ l.reason }})</small>{% endif %}</span>{% if not forloop.last %}, {% endif %}{% endfor %}
diff --git a/duty/templates/duty/collect_table.html b/duty/templates/duty/collect_table.html
--- a/duty/templates/duty/collect_table.html
+++ b/duty/templates/duty/collect_table.html
@@ -15,7 +15,7 @@
   <ul>{% for e in errors %}<li>{% if e.row %}{{ e.row }}행 {% endif %}{{ e.column }}: {{ e.reason }}</li>{% endfor %}</ul>
 </article>
 {% endif %}
-<p class="guide"><small>칸마다 그 출근조에 들어갈 사람 이름을 쉼표(,)로 구분해 적습니다. 한 사람은 하루에 한 출근조만.{% if names %}<br>{{ dept.name }} 인원: {{ names|join:", " }}{% endif %}</small></p>
+<p class="guide"><small>칸마다 그 출근조에 들어갈 사람 이름을 쉼표(,)로 구분해 적습니다. 한 사람은 하루에 한 출근조만. 휴가·출장·교육은 이름 뒤에 이름(휴가)처럼 붙입니다(근무로 치지 않음).{% if names %}<br>{{ dept.name }} 인원: {{ names|join:", " }}{% endif %}</small></p>
 <form method="post">{% csrf_token %}
 <div class="grid-wrap">
 <table class="roster">
diff --git a/duty/templates/duty/day.html b/duty/templates/duty/day.html
--- a/duty/templates/duty/day.html
+++ b/duty/templates/duty/day.html
@@ -19,7 +19,7 @@
   <p>{% with line=s.items %}{% include "duty/_labels.html" %}{% endwith %}{% if not s.items %}-{% endif %}{% if s.removed_items %} {% with line=s.removed_items %}{% include "duty/_labels.html" %}{% endwith %}{% endif %}</p>
   {% if editable %}
   <details><summary role="button" class="outline secondary">바꾸기</summary>
-    {% include "duty/_cell_form.html" with cell=s.cell label=s.label slot=s.slot current_members=s.current_members to_options=s.to_options next=s.next inline=True %}
+    {% include "duty/_cell_form.html" with cell=s.cell label=s.label slot=s.slot current_members=s.current_members reason_choices=s.reason_choices to_options=s.to_options next=s.next inline=True %}
   </details>
   {% endif %}
 </article>
diff --git a/duty/views/roster.py b/duty/views/roster.py
--- a/duty/views/roster.py
+++ b/duty/views/roster.py
@@ -14,24 +14,31 @@ from ..models import Department, Memo, User
 from ..services import boards, changes, holidays, memos, prefs
 from ..services.roster import find_day, member_schedule, published_days
 from ..shifts import (
-    DAY_LABELS, DEVELOPER, SLOT_GROUP, STAFF, by_key, cell_label, display_order, is_slot_cell, ordered, shift_defs,
+    DAY_LABELS, DEVELOPER, REASONS, SLOT_GROUP, STAFF, by_key, cell_label, display_order, is_slot_cell, ordered, shift_defs,
     slot_defs,
 )
 from .common import date_param, safe_next
 
 
-def _item(label: str, names: list[str], removed: bool = False) -> dict:
-    """라벨(A, A>B>C, +B)을 이름 토큰으로 나눈다. 마지막 이름 앞은 취소선, hl은 검색어 번호(1..3)."""
+def _item(label: str, names: list[str], removed: bool = False, reasons: dict[str, str] | None = None) -> dict:
+    """라벨(A, A>B>C, +B)을 이름 토큰으로 나눈다. 마지막 이름 앞은 취소선, hl은 검색어 번호(1..3).
+    reason = 지금 배정된(마지막) 사람의 사유. 이름 뒤에 작게 붙는다(변경 내역을 꺼도 보인다)."""
     parts = [p.strip().lstrip("+") for p in label.split(">")]
     tokens = [
         {"name": n, "struck": removed or k < len(parts) - 1, "hl": next((i for i, q in enumerate(names, 1) if q == n), 0)}
         for k, n in enumerate(parts)
     ]
-    return {"tokens": tokens, "changed": len(parts) > 1 or label.startswith("+") or removed}
+    return {"tokens": tokens, "changed": len(parts) > 1 or label.startswith("+") or removed,
+            "reason": "" if removed else (reasons or {}).get(parts[-1], "")}
 
 
-def _items(labels: list[str], names: list[str], removed: bool = False) -> list[dict]:
-    return [_item(lb, names, removed) for lb in labels]
+def _items(labels: list[str], names: list[str], removed: bool = False, reasons: dict[str, str] | None = None) -> list[dict]:
+    return [_item(lb, names, removed, reasons) for lb in labels]
+
+
+def _why(day, cell: str) -> dict[str, str]:
+    """그 칸 사람들의 사유 {이름: 사유}(사유는 근무조 배정에만 있다)."""
+    return {n: r for (c, n), r in day.reasons.items() if c == cell} if day else {}
 
 
 def _latest(labels: list[str]) -> list[str]:
@@ -39,8 +46,9 @@ def _latest(labels: list[str]) -> list[str]:
     return [lb.split(">")[-1].strip().lstrip("+") for lb in labels]
 
 
-def _lines(labels: list[str], names: list[str], removed: bool = False, per_line: int = 3) -> list[list[dict]]:
-    items = _items(labels, names, removed)
+def _lines(labels: list[str], names: list[str], removed: bool = False, per_line: int = 3,
+           reasons: dict[str, str] | None = None) -> list[list[dict]]:
+    items = _items(labels, names, removed, reasons)
     return [items[i:i + per_line] for i in range(0, len(items), per_line)]
 
 
@@ -112,15 +120,19 @@ def _active_members(board, depts: list[str] | None = None, types: list[str] | No
 def _cell_context(defs, day, cell: str, d, depts: list[str] | None = None, types: list[str] | None = None, members=()):
     current = day.members[cell] if day else []
     qs = User.objects.filter(name__in=current).order_by("name")
+    why = _why(day, cell)
     # To 목록에 그날 같은 종류 근무를 붙인다(맞교환이 기본이라 무엇과 바뀌는지 보이게)
     kinds = [x.key for x in ordered(defs) if is_slot_cell(x.key) == is_slot_cell(cell)]
     where = {}
     for k in kinds:
         for n in (day.members[k] if day else []):
             where[n] = f"{where[n]}·{cell_label(defs, k)}" if n in where else cell_label(defs, k)  # 관제 여러 칸이면 모두
+    current_members = list(_filtered(qs, depts or [], types or []))
+    for m in current_members:
+        m.reason = why.get(m.name, "")  # 사유 선택의 지금 값 표시
     return {
         "d": d, "cell": cell, "label": cell_label(defs, cell), "slot": is_slot_cell(cell),
-        "current_members": list(_filtered(qs, depts or [], types or [])),
+        "current_members": current_members, "reason_choices": REASONS,
         "to_options": [{"username": m.username, "name": m.name, "dept": m.department.name,
                         "where": where.get(m.name, "근무 없음")} for m in members if m.name not in current],
     }
@@ -183,7 +195,8 @@ def roster(request):
         return {
             x.key: {
                 "key": x.key, "slot": is_slot_cell(x.key), "label": x.name,
-                "lines": _lines(show([lb for lb in found.cells[x.key].labels if keep(lb)]), names) if found else [],
+                "lines": _lines(show([lb for lb in found.cells[x.key].labels if keep(lb)]), names,
+                                reasons=_why(found, x.key)) if found else [],
                 "removed": _lines([lb for lb in found.cells[x.key].removed if keep(lb)], names, True) if found and history else [],
             }
             for x in display_order(defs) if shown(x.key)
@@ -226,15 +239,23 @@ def cell(request, d, cell):
         raise Http404
     fallback = reverse("day", args=[d])
     if request.method == "POST":
+        reason_form = bool(request.POST.get("set_reason"))  # 근무조 칸의 사유 선택(같은 창의 두 번째 폼)
         try:
-            # "+"·"-" = 없음(넣기만·빼기만). 기본은 둘 다 고른 맞교환
-            before, after = request.POST.get("before"), request.POST.get("after")
-            result = changes.exchange(request.user, board, d, cell, _member(None if before == "+" else before),
-                                      _member(None if after == "-" else after))
+            if reason_form:
+                pk = request.POST.get("member", "")  # 위 폼과 option 값이 겹치지 않게 아이디 대신 번호
+                member = User.objects.filter(pk=pk).first() if pk.isdigit() else None
+                if member is None:
+                    raise DutyError("사유를 붙일 사람을 골라 주세요.")
+                result = changes.set_reason(request.user, board, d, member, request.POST.get("reason", ""))
+            else:
+                # "+"·"-" = 없음(넣기만·빼기만). 기본은 둘 다 고른 맞교환
+                before, after = request.POST.get("before"), request.POST.get("after")
+                result = changes.exchange(request.user, board, d, cell, _member(None if before == "+" else before),
+                                          _member(None if after == "-" else after))
         except DutyError as e:
             messages.error(request, str(e))
         else:
-            messages.success(request, "변경했습니다.")
+            messages.success(request, "사유를 저장했습니다." if reason_form else "변경했습니다.")
             for w in result:
                 messages.warning(request, w)
         return redirect(safe_next(request, fallback))
@@ -270,7 +291,7 @@ def day(request, d):
             ctx = _cell_context(defs, found, k, d, depts, types, members)
             ctx.update(
                 next=request.path,
-                items=_items(show([x for x in found.cells[k].labels if keep(x)]), []),
+                items=_items(show([x for x in found.cells[k].labels if keep(x)]), [], reasons=_why(found, k)),
                 removed_items=_items([x for x in found.cells[k].removed if keep(x)], [], True) if history else [],
             )
             sections.append(ctx)
```

`_cell_form.html`(두 번째 폼)·`base.html`(`.rsn`: 바뀐 칸 `.chg` 안에서도 굵은 기울임·분홍을 물려받지 않게 보통 글씨·흐린 색):
```diff
diff --git a/duty/templates/duty/_cell_form.html b/duty/templates/duty/_cell_form.html
--- a/duty/templates/duty/_cell_form.html
+++ b/duty/templates/duty/_cell_form.html
@@ -17,6 +17,21 @@
   </label>
   <button>저장</button>
 </form>
+{% if not slot and current_members %}
+<hr>
+<form method="post" action="{% url 'cell' d cell %}">{% csrf_token %}
+  <input type="hidden" name="next" value="{{ next }}">
+  <p><small>휴가·출장·교육이면 사유를 붙입니다. 사유가 붙으면 그날 근무로 치지 않습니다(알림·캘린더·관제에서 빠짐).</small></p>
+  <label>사유
+    <select name="member" aria-label="사유를 붙일 사람">
+      {% for m in current_members %}<option value="{{ m.pk }}">{{ m.name }}{% if m.reason %} ({{ m.reason }}){% endif %}</option>
+      {% endfor %}
+    </select>
+  </label>
+  <select name="reason" aria-label="사유"><option value="">없음</option>{% for r in reason_choices %}<option>{{ r }}</option>{% endfor %}</select>
+  <button class="secondary" name="set_reason" value="1">사유 저장</button>
+</form>
+{% endif %}
 <script>
   // 넣기만·빼기만은 드물다: 한 번 더 묻는다
   window.cellConfirm = window.cellConfirm || (f => {
diff --git a/duty/templates/duty/base.html b/duty/templates/duty/base.html
--- a/duty/templates/duty/base.html
+++ b/duty/templates/duty/base.html
@@ -67,6 +67,7 @@
     .hol { margin: .2rem 0 0; font-weight: 700; color: var(--nxt-red); }  /* 휴장일 이름: 날짜 칸 맨 위·하루 화면 제목 아래 */
     /* 메모: 날 메모는 휴장일 아래 한 줄, 근무 없음은 칸 전체를 덮는다. 주·달 메모는 표 위·아래(월간 주 메모는 그 주 행 아래) */
     .memo { margin: .2rem 0 0; font-weight: 600; }
+    .rsn { font-size: .8em; font-weight: 400; font-style: normal; color: var(--pico-muted-color); }  /* 사유: 이름 뒤 작은 (휴가). 바뀐 칸(.chg)에서도 보통 글씨 */
     .nowork { margin: .4rem 0 0; padding: 1.2rem .4rem; border-radius: .3rem; text-align: center; font-weight: 700; background: var(--duty-line); }
     .memo-btn { margin-left: .3rem; font-size: .8rem; white-space: nowrap; }
     .memo-note { margin: .3rem 0 .6rem; }
```

사유 폼의 `member` 값을 username 이 아니라 pk 로 둔 까닭: 기존 `test_views_roster.py` 가 창 안의 `<option value="{username}"` 개수와 To 목록 뒤쪽의 `value="{username}"` 을 단언한다(기존 단언을 바꾸지 않는다).

- [ ] **Step 16: 통과를 확인하고 브라우저로 본다(CLAUDE.md, PC 1400px·모바일 390px)**

Run: `.venv/bin/pytest -W error -q`
Expected: 전체 통과(사본 1036 passed).

가짜 데이터 DB 를 임시 폴더에 따로 만들어 확인하고 끝나면 지운다(실제 `data/`·`.env` 는 쓰지 않는다):
```bash
W=$(mktemp -d)
export DUTY_ENV_FILE= DUTY_DEBUG=1 DUTY_DATA_DIR=$W/data   # 루트 .env 를 읽지 않는다(Task 8 과 같은 방식)
.venv/bin/python manage.py migrate
.venv/bin/python manage.py shell -c '
from datetime import date, datetime, timezone
from duty.models import Board, Commute, Department, DutyAssignment, Period, User
from duty.services import changes
b = Board.objects.get(code="it")
dept, _ = Department.objects.get_or_create(code="MEMS", defaults=dict(name="매칭엔진실", shifts="dawn,normal,dinner,night", board=b))
mgr = User.objects.create_user("mgr1", password="unused-Pw-123", name="담당자", department=dept, part="", type="개발자", help_dismissed=True)
mgr.groups.add(b.admin_group)
ms = [User.objects.create_user(f"m{i}", password=None, name=f"가상{i}", department=dept, part="", type="개발자") for i in range(5)]
D = date(2026, 11, 16)
p = Period.objects.create(board=b, name="확인용", start_date=D, end_date=date(2026, 11, 20), status="published",
                          overwrite_from=D, published_at=datetime(2026, 11, 14, tzinfo=timezone.utc))
for x in p.dates():
    for m, s in ((ms[0], "dawn"), (ms[1], "normal"), (ms[2], "normal"), (ms[3], "dinner")):
        Commute.objects.create(period=p, date=x, member=m, shift=s)
    DutyAssignment.objects.create(period=p, date=x, cell="slot0", member=ms[1])
changes.set_reason(mgr, b, D, ms[1], "휴가")
changes.set_reason(mgr, b, date(2026, 11, 17), ms[0], "출장")
changes.change_cell(mgr, b, date(2026, 11, 17), "dinner", ms[3], ms[4])
changes.set_reason(mgr, b, date(2026, 11, 17), ms[4], "교육")'
.venv/bin/python manage.py runserver
```
`mgr1` / `unused-Pw-123` 로 로그인해 1400px·390px 에서 본다(날짜는 오늘 이후여야 칸 링크가 생긴다. 지났으면 위 날짜를 다음 주로 바꾼다):
- `/?date=2026-11-16`: 16일 정상 "가상1(휴가), 가상2", 17일 새벽 "가상0(출장)", 17일 석식교대 "~~가상3~~>가상4(교육)". "(휴가)" 는 이름보다 작고 흐린 보통 글씨(바뀐 칸에서도 분홍·굵은 기울임이 아니다). 16일 관제 칸의 가상1 에는 붙지 않는다.
- 필터의 "변경 내역 표시(A>B·취소선)" 를 끄고 보면 17일 석식교대가 "가상4(교육)" 로 남는다. 월간(`?view=month`)·390px 에서도 칸 밖으로 넘치지 않는다.
- 16일 정상 칸을 누르면 창 아래 `<hr>` 뒤에 "사유" 폼: 사람 선택에 "가상1 (휴가)", 사유 선택 없음/휴가/출장/교육, [사유 저장]. 가상2 에 "교육" 저장 → "사유를 저장했습니다.", 칸에 "가상2(교육)". 가상1 의 사유를 다시 "휴가"로 저장 → "변경할 내용이 없습니다." 오류. 관제 칸 창에는 사유 폼이 없다.
- 가상0(16일 새벽)에 "휴가" 를 붙이면 경고 없음, 16일 가상1 처럼 관제 칸이 있는 사람이면 "…장중관제 08:30~09:30 칸에 남아 있습니다. 다른 사람으로 바꾸세요." 경고.
- `/day/2026-11-16/` 의 [바꾸기] 를 펼쳐도 같은 두 폼. `/changes/` 이력에 "가상1 → 가상1(휴가)".
- 출근표 입력 표 안내에 "휴가·출장·교육은 이름 뒤에 이름(휴가)처럼 붙입니다(근무로 치지 않음)."
확인 뒤 서버를 끄고 `rm -rf "$W"`.

- [ ] **Step 17: 근무로 치지 않음 테스트를 붙인다**

`tests/test_reasons.py` 끝에:
```python
# ── 근무로 치지 않음: 개인 알림·보고서·캘린더·관제 생성 후보·통계 ──

SUN18 = datetime(2026, 11, 15, 18)
MON = date(2026, 11, 16)


def _day(reasons=None, **cells):
    members = {c: [] for c in KEYS}
    members.update(cells)
    return Day(MON, 1, {}, members, {}, reasons or {})


def _rule(**kw):
    base = dict(id=1, member_name="가", kind="personal", timing="days", offset=1, at_minute=18 * 60,
                channels=("telegram",), shifts=("dawn",), depts=(), types=())
    return RuleSpec(**{**base, **kw})


def _plan(rules, days, deliveries=None):
    dests = {(r.id, ch): ["d"] for r in rules for ch in r.channels}
    return plan(IT_DEFS, rules, days, {"가": ("MEMS", "개발자"), "나": ("MEMS", "개발자")}, deliveries or {}, SUN18,
                destinations=dests)


def test_personal_alarm_skips_reason_and_sends_no_cancel():
    r = _rule()
    h_in = _plan([r], [_day(dawn=["가"])])[0].content_hash
    away = _day({("dawn", "가"): "휴가"}, dawn=["가"])
    assert _plan([r], [away]) == []
    assert _plan([r], [away], {(1, MON, "dawn", "telegram", "d"): h_in}) == []  # 이미 보낸 알림은 되돌리지 않는다


def test_report_shows_name_with_reason():
    r = _rule(kind="report", member_name=None, shifts=("dawn", "normal"))
    plain = _plan([r], [_day(dawn=["가", "나"])])[0]
    due = _plan([r], [_day({("dawn", "가"): "출장"}, dawn=["가", "나"])])[0]
    assert due.text.split("\n")[1] == "새벽(06:30~) 가(출장), 나"
    assert plain.text.split("\n")[1] == "새벽(06:30~) 가, 나"  # 사유가 없으면 지금 문구 그대로
    assert due.content_hash != plain.content_hash
    assert due.push_text.endswith("· 1명")  # 근무로 치는 사람만 센다


def test_calendar_skips_reason_day(pub, it_board, settings):
    _, m = pub
    settings.SITE_URL = "https://duty.example"
    assert [e.summary for e in calendar._events(m["가"])] == ["정상 출근 08:00~17:00", "장중관제 08:30~09:30"]
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    assert [e.summary for e in calendar._events(m["가"])] == ["장중관제 08:30~09:30"]  # 남은 당번 칸은 그대로(경고로 알림)


def test_generation_skips_reason_commutes(make_member, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=MON, end_date=MON, status=S.CLOSED)
    away = make_member("휴가자", dept="MEMS")
    Commute.objects.create(period=p, date=MON, member=away, shift="normal", reason="휴가")
    for i in range(5):
        Commute.objects.create(period=p, date=MON, member=make_member(f"N{i}", dept="MEMS"), shift="normal")
        Commute.objects.create(period=p, date=MON, member=make_member(f"D{i}", dept="TMCH"), shift="dinner")
    for dept in ("MD", "UI"):
        Commute.objects.create(period=p, date=MON, member=make_member(f"직원{dept}", dept=dept, type="직원"), shift="normal")
    run_generation(p, seed=3)
    assert DutyAssignment.objects.filter(period=p).count() == 10
    assert not DutyAssignment.objects.filter(member=away).exists()


def test_stats_count_only_real_work(make_member, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=MON, end_date=MON + timedelta(days=1),
                              status=S.PUBLISHED, overwrite_from=MON)
    a, b = make_member("가"), make_member("나")
    Commute.objects.create(period=p, date=MON, member=a, shift="dawn", reason="교육")
    Commute.objects.create(period=p, date=MON + timedelta(days=1), member=a, shift="night")
    Commute.objects.create(period=p, date=MON, member=b, shift="normal", reason="휴가")
    rows, _, _ = stats.member_stats(it_board, None, None)
    assert {(r.name, r.dawn, r.night) for r in rows} == {("가", 0, 1), ("나", 0, 0)}
    assert stats.period_duty_counts(p)[0] == []  # 관제 자격 출근이 사유뿐이면 모집단에서 빠진다(생성 후보와 같다)
```

- [ ] **Step 18: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_reasons.py`
Expected: 5 failed, 35 passed — 개인 알림 `Due` 가 나오고, 보고서 줄이 `가, 나`, 캘린더에 "정상 출근" 이 남고, 씨앗 3 에서 휴가자가 관제에 뽑히고(`DutyAssignment` 있음), 통계의 새벽이 1.

- [ ] **Step 19: 알림·캘린더·생성·통계에서 사유 있는 배정을 뺀다**

`duty/alarms/plan.py`(순수 유지: `csv_io.join_reason` 도 ORM 없음), `duty/services/calendar.py`, `generate.py`, `stats.py`:
```diff
diff --git a/duty/alarms/plan.py b/duty/alarms/plan.py
--- a/duty/alarms/plan.py
+++ b/duty/alarms/plan.py
@@ -3,6 +3,7 @@ import hashlib
 from dataclasses import dataclass
 from datetime import date, datetime
 
+from ..csv_io import join_reason
 from ..services.roster import Day
 from ..shifts import KEYS, cell_start, cells_of
 from . import messages as m
@@ -97,6 +98,8 @@ def _targets(r, destinations):
 def _personal(defs, r, day, cells, starts, deliveries, now, destinations, today, closed):
     out = []
     for c in cells:
+        if (c, r.member_name) in day.reasons:  # 사유가 있으면 근무로 치지 않는다. 이미 보낸 알림의 취소도 보내지 않는다
+            continue
         start = starts[c]
         if not send_at(r.timing, r.offset, r.at_minute, day.date, start, closed) <= now < start:
             continue
@@ -131,8 +134,8 @@ def _report(defs, r, day, cells, starts, info, deliveries, now, dept_names, synt
     lines, uniq = [], set()
     for c in cells:
         names = [n for n in day.members.get(c, []) if keep(n)]
-        uniq.update(names)
-        lines.append(m.report_line(defs, c, names))
+        uniq.update(n for n in names if (c, n) not in day.reasons)  # 요약 인원은 근무로 치는 사람만
+        lines.append(m.report_line(defs, c, [join_reason(n, day.reasons.get((c, n), "")) for n in names]))  # 가(휴가)
     cond = "·".join([dept_names.get(x, x) for x in r.depts] + list(r.types))
     # 변경 표지만 빼고 보이는 내용 전체(머리·조건·근무표)
     h = _hash("report", "\n".join([m.report_header(day.date, cond, False), *lines]))
diff --git a/duty/services/calendar.py b/duty/services/calendar.py
--- a/duty/services/calendar.py
+++ b/duty/services/calendar.py
@@ -99,7 +99,7 @@ def _events(member, shifts=()) -> list[ics.Event]:
     for day in days:
         for x in ordered(defs):  # KEYS 순(옛 CELLS 와 같다). 모르는 키는 정의에 없어 조용히 빠진다
             cell = x.key
-            if member.name not in day.members.get(cell, ()) or \
+            if member.name not in day.members.get(cell, ()) or (cell, member.name) in day.reasons or \
                     (shifts and (SLOT_GROUP if is_slot_cell(cell) else cell) not in shifts):
                 continue
             summary = f"{SLOT_GROUP_NAME} {x.name}" if is_slot_cell(cell) else f"{x.name} 출근 {x.start:%H:%M}~{x.end:%H:%M}"
diff --git a/duty/services/generate.py b/duty/services/generate.py
--- a/duty/services/generate.py
+++ b/duty/services/generate.py
@@ -33,7 +33,7 @@ def run_generation(period: Period, seed: int | None = None, by=None) -> Generati
     slots = slot_defs(boards.active_defs(period.board))  # 인덱스 i ↔ 칸 키 slots[i].key. 꺼진 관제는 생성하지 않는다
     if slots:
         commutes: dict = defaultdict(lambda: defaultdict(set))
-        rows = Commute.objects.filter(period=period).exclude(date__in=skip)
+        rows = Commute.objects.filter(period=period, reason="").exclude(date__in=skip)  # 사유가 있으면 후보가 아니다
         for d, shift, code in rows.values_list("date", "shift", "member__username"):
             commutes[d][shift].add(code)
         members_by_type: dict = defaultdict(set)  # 그 근무표 부서 재직자. 칸별 유형 거르기는 generator 가 한다
diff --git a/duty/services/stats.py b/duty/services/stats.py
--- a/duty/services/stats.py
+++ b/duty/services/stats.py
@@ -57,12 +57,12 @@ def member_stats(board: Board, start: date | None, end: date | None):
             if is_slot_cell(cell):
                 for n in names:
                     stats.setdefault(n, MemberStat(n)).duty += 1
-    for day in days:
+    for day in days:  # 근무로 친 배정만(사유가 있으면 세지 않는다)
         for n in day.members.get("dawn", ()):  # 근무표에 그 정의가 없으면 칸도 없다
-            if n in stats:
+            if n in stats and ("dawn", n) not in day.reasons:
                 stats[n].dawn += 1
         for n in day.members.get("night", ()):
-            if n in stats:
+            if n in stats and ("night", n) not in day.reasons:
                 stats[n].night += 1
     rows = sorted(stats.values(), key=lambda s: (s.duty, s.name))
     return rows, _summary([s.duty for s in rows]), _summary([s.total for s in rows])
@@ -74,7 +74,8 @@ def period_duty_counts(period: Period) -> tuple[list[tuple[str, int]], int, bool
     q = Q(pk__in=[])  # 칸별 자격(generator 와 같다): 그 칸 자격 근무조 출근 ∧ 그 칸 자격 유형(빈 튜플 = 전원)
     for x in slots:
         q |= Q(shift__in=x.eligible_shifts, **({"member__type__in": x.eligible_types} if x.eligible_types else {}))
-    pool = Commute.objects.filter(q, period=period)  # 회차의 출근표가 곧 그 근무표 사람(퇴사자도 출근이 있으면 0회로 남는다)
+    # 회차의 출근표가 곧 그 근무표 사람(퇴사자도 출근이 있으면 0회로 남는다). 사유가 있는 출근은 생성 후보가 아니다
+    pool = Commute.objects.filter(q, period=period, reason="")
     n: dict[str, int] = dict.fromkeys(pool.values_list("member__name", flat=True), 0)
     for name in DutyAssignment.objects.filter(period=period).values_list("member__name", flat=True):
         n[name] = n.get(name, 0) + 1
```

사유가 없으면 보고서 줄 문자열이 지금과 같아(`join_reason(n, "") == n`) IT 보고서 hash 가 바뀌지 않는다.

- [ ] **Step 20: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_reasons.py tests/test_alarm_plan.py tests/test_alarm_texts_it.py tests/test_run_alarms.py tests/test_calendar_feed.py tests/test_generate.py tests/test_boards_generate.py tests/test_stats.py`
Expected: 모두 통과.

- [ ] **Step 21: 배포·배포 취소 테스트를 붙이고 실패를 확인한다**

`tests/test_reasons.py` 끝에:
```python
# ── 배포·배포 취소: publish_undo 의 c 행 여섯째 칸 ──

def test_publish_undo_keeps_reason(make_member, it_board):
    a = Period.objects.create(board=it_board, name="A", start_date=MON, end_date=MON + timedelta(days=1),
                              status=S.PUBLISHED, overwrite_from=MON, published_at=NOW)
    b = Period.objects.create(board=it_board, name="B", start_date=MON, end_date=MON + timedelta(days=1), status=S.GENERATED)
    ga, na = make_member("가"), make_member("나")
    Commute.objects.create(period=a, date=MON, member=ga, shift="dawn", reason="휴가")
    Commute.objects.create(period=a, date=MON + timedelta(days=1), member=na, shift="normal")
    DutyAssignment.objects.create(period=a, date=MON, cell="slot0", member=na)
    publish.publish(b, MON)
    b.refresh_from_db()
    assert sorted(b.publish_undo) == sorted([
        ["c", a.pk, "2026-11-16", ga.pk, "dawn", "휴가"], ["c", a.pk, "2026-11-17", na.pk, "normal", ""],
        ["a", a.pk, "2026-11-16", na.pk, "slot0"]])
    publish.unpublish(b)
    assert Commute.objects.get(period=a, member=ga).reason == "휴가"


def test_unpublish_reads_old_rows_without_reason(make_member, it_board):
    a = Period.objects.create(board=it_board, name="A", start_date=MON, end_date=MON, status=S.GENERATED)
    b = Period.objects.create(board=it_board, name="B", start_date=MON, end_date=MON, status=S.GENERATED)
    publish.publish(b, MON)
    ga = make_member("가")
    Period.objects.filter(pk=b.pk).update(publish_undo=[["c", a.pk, "2026-11-16", ga.pk, "dawn"]])  # 2단계 전 배포
    publish.unpublish(Period.objects.get(pk=b.pk))
    assert Commute.objects.get(period=a, member=ga).reason == ""
```

Run: `.venv/bin/pytest -W error -q tests/test_reasons.py`
Expected: 1 failed, 41 passed — `test_publish_undo_keeps_reason` 의 c 행이 다섯 칸(`['c', …, 'dawn'] != ['c', …, 'dawn', '휴가']`). 옛 행 읽기 테스트는 지금도 통과한다(회귀 방지용).

- [ ] **Step 22: `publish_undo` c 행에 사유를 싣는다**

`duty/services/publish.py`, `duty/models.py`(주석):
```diff
diff --git a/duty/models.py b/duty/models.py
--- a/duty/models.py
+++ b/duty/models.py
@@ -193,7 +193,8 @@ class Period(models.Model):
     board = models.ForeignKey(Board, on_delete=models.PROTECT, related_name="periods", verbose_name="근무표")
     # 휴장일 건너뛰기(설계 5절): 근무표를 만드는 도구가 휴장일을 건너뛴다. 2단계 전 회차는 거짓(마이그레이션 0018), 새 회차는 참
     skip_holidays = models.BooleanField("휴장일 건너뛰기", default=True)
-    # 배포가 지운 행 목록: ["c", 회차 id, 날짜, 멤버 id, 출근조] | ["a", 회차 id, 날짜, 멤버 id, 당번 칸]. 배포 취소 때 되살린다. null = 되돌릴 정보 없음
+    # 배포가 지운 행 목록: ["c", 회차 id, 날짜, 멤버 id, 출근조, 사유] | ["a", 회차 id, 날짜, 멤버 id, 당번 칸]. 배포 취소 때 되살린다.
+    # 사유 칸이 없는 옛 c 행(2단계 전 배포)도 읽는다. null = 되돌릴 정보 없음
     publish_undo = models.JSONField(null=True, blank=True, editable=False)
     # 이 번호 이하의 ChangeLog 는 근무표·알림에 쓰지 않는다(배포 취소 때 그 시점 최대 번호로 정함). 시각 대신 번호라 시계와 무관
     log_floor = models.BigIntegerField(default=0, editable=False)
diff --git a/duty/services/publish.py b/duty/services/publish.py
--- a/duty/services/publish.py
+++ b/duty/services/publish.py
@@ -47,7 +47,9 @@ def preview_publish(period: Period, overwrite_from: date) -> PublishPreview:
     return PublishPreview(overwrite_from, period.end_date, sorted({p.name for p in own.values()}), discarded)
 
 
-_MODELS = {"c": (Commute, "shift"), "a": (DutyAssignment, "cell")}  # 옛 "k"(관제 숫자) 행은 마이그레이션 0013 이 "a" 로 바꿨다
+# 행 종류 → (모델, 넷째 칸부터의 필드). 옛 "k"(관제 숫자) 행은 마이그레이션 0013 이 "a" 로 바꿨다.
+# c 행의 여섯째 칸(reason)은 2단계부터: 그 전에 배포한 회차의 다섯 칸짜리 c 행은 사유 없음으로 되살린다
+_MODELS = {"c": (Commute, ("shift", "reason")), "a": (DutyAssignment, ("cell",))}
 
 
 @transaction.atomic
@@ -55,12 +57,13 @@ def publish(period: Period, overwrite_from: date, by=None) -> None:
     period.refresh_from_db()  # 화면이 트랜잭션 밖에서 읽은 상태를 믿지 않는다(동시 배포)
     _validate(period, overwrite_from)
     undo = []
-    for key, (model, field) in _MODELS.items():
+    for key, (model, fields) in _MODELS.items():
         doomed = (
             model.objects.filter(period__in=_others(period), date__gte=overwrite_from, date__lte=period.end_date)
             | model.objects.filter(period=period, date__lt=overwrite_from)
         )
-        undo += [[key, p, d.isoformat(), m, v] for p, d, m, v in doomed.values_list("period_id", "date", "member_id", field)]
+        undo += [[key, p, d.isoformat(), m, *vals]
+                 for p, d, m, *vals in doomed.values_list("period_id", "date", "member_id", *fields)]
         doomed.delete()
     period.status, period.overwrite_from, period.published_at = S.PUBLISHED, overwrite_from, timezone.now()
     period.publish_undo = undo
@@ -108,10 +111,10 @@ def unpublish(period: Period, by=None) -> None:
     undo = _restorable(period)
     if User.objects.filter(pk__in={r[3] for r in undo}).count() != len({r[3] for r in undo}):
         raise DutyError("되살릴 근무의 사용자가 삭제되어 배포를 취소할 수 없습니다.")
-    for key, (model, field) in _MODELS.items():
+    for key, (model, fields) in _MODELS.items():
         model.objects.bulk_create(
-            model(period_id=p, date=date.fromisoformat(d), member_id=m, **{field: v})
-            for k, p, d, m, v in undo if k == key
+            model(period_id=p, date=date.fromisoformat(d), member_id=m, **dict(zip(fields, vals)))
+            for k, p, d, m, *vals in undo if k == key
         )
     period.status, period.overwrite_from, period.published_at, period.publish_undo = S.GENERATED, None, None, None
     period.log_floor = ChangeLog.objects.aggregate(m=Max("id"))["m"] or 0  # 지금까지의 기록은 다시 배포해도 쓰지 않는다
```

`_restorable` 은 `r[2]`(날짜)만 보므로 그대로다.

- [ ] **Step 23: 전체 테스트·마이그레이션 검사**

Run: `.venv/bin/pytest -W error -q`
Expected: 전체 통과, 경고 0개(사본 1043 passed = 999 + 새 44).
Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --check`
Expected: `No changes detected in app 'duty'`

- [ ] **Step 24: 커밋한다**

```bash
git add duty/shifts.py duty/csv_io.py duty/models.py duty/migrations/0018_holidays.py duty/migrations/0020_reasons.py \
  duty/services/collect.py duty/services/changes.py duty/services/memos.py duty/services/roster.py \
  duty/services/change_notice.py duty/services/calendar.py duty/services/generate.py duty/services/stats.py \
  duty/services/publish.py duty/alarms/plan.py duty/views/manage.py duty/views/roster.py \
  duty/templates/duty/_labels.html duty/templates/duty/_cell_form.html duty/templates/duty/day.html \
  duty/templates/duty/collect_table.html duty/templates/duty/base.html \
  tests/test_reasons.py tests/test_migration_reasons.py
git commit -m "feat: 사유(휴가·출장·교육) — 입력 표·CSV·근무 변경 창·화면 표시, 근무로 치지 않음(알림·캘린더·관제·통계), 이력·배포 취소"
```


---

### Task 5: 점심당번

> 검증: Task 1~4 를 넣은 `feat/boards-phase2` 사본(1043 passed)에 아래 코드를 그대로 넣어 확인했다. 저장소는 고치지 않았다. 결과: `.venv/bin/pytest -W error -q` → **1076 passed**(1043 + 새 33), 경고 0개. `makemigrations duty --check` → "No changes detected in app 'duty'". 단계별 실패도 사본에서 하나씩 재현했다(각 단계의 Expected). 가짜 데이터(가상 이름, 임시 DB, 끝나면 지움)로 그린 주간·월간·하루 화면과 근무 변경 창(근무조 칸·점심당번 칸)을 headless Chrome 으로 1400·390px 캡처해 확인했다. 클릭으로 하는 팝업 동작은 직접 해 보지 않았다(Step 20 에서 사람이 확인).
>
> 이 작업의 범위(설계 2·4.1·4.3·4.4·4.6·6.3·6.4·7·8.1~8.3·10): `KEYS` 끝에 `lunch`와 관련 제약(`boardshift_key_valid`·`boardshift_times_valid`·`dutyassignment_cell_valid`·`changelog_cell_valid`·`alarmdelivery_cell_valid`), `Department.lunch_start/lunch_end`(둘 다 비었거나 둘 다 있고 시작 < 끝, DB 제약 + 관리 화면), 마이그레이션 0021(스키마)·0022(데이터: IT 점심당번 정의, IT 부서 11:30–12:30, 오늘 이후 배포됨·생성됨 회차 새벽 근무자 채우기, publish_undo lunch a 행), `run_generation` 의 점심당번 채우기, 근무 변경(넣기·빼기·교체, 관제와 안 섞임, "점심당번도 같이 넘기기"), 화면(근무조 → 점심당번 → 관제, 시각 없이 "점심당번"), 스케줄 선택지, 알림(문구 틀 셋·부서 점심 시각·보고서 줄·발송 창 제외·점심당번만 고른 보고서 금지), 캘린더 일정, 통계 제외.
> 규칙: 점심당번은 **혼자인 당번 칸**이다(`shifts.kind(key) == SOLO`). 묶음이 혼자라 맞교환이 없고(늘 교체), 같은 날 같은 사람만 두 번 못 들어가며 인원 제한은 없다(조건부 unique 는 `slot*` 만). 정의(`BoardShift`)에는 시각이 없고, 알림·캘린더 시각은 그 사람 부서의 `lunch_start/lunch_end` 다. 그날 사유가 있는 사람의 점심당번은 근무로 치지 않는다(`Day.excused`).
> 테스트 DB: 마이그레이션 0022 가 테스트 DB 의 IT 근무표에도 점심당번 정의를 넣는다. conftest `it_board` 는 그 정의를 지워 **기존 테스트가 1단계 IT 정의 그대로 돌게** 하고, 점심당번 테스트는 새 `lunch` 픽스처로 켠다. 기존 테스트에서 고치는 것은 `KEYS` 가 길어져 깨지는 상수 단언 5곳뿐이다(Step 1, 기대 값의 뜻은 그대로 "IT 정의 = KEYS 에서 lunch 를 뺀 것").
> IT 알림 문구·hash: 기존 칸의 문구·hash 는 그대로다(`tests/test_alarm_texts_it.py` 그대로 통과, 점심당번 정의가 있어도 새벽 개인 알림 hash 가 1단계와 같음을 새 테스트로 고정). 스케줄이 "전부"(`[]`)인 IT 보고서 규칙만 끝에 `점심당번 이름…` 줄이 붙어 그날 발송 창이 열린 보고서가 한 번 다시 나간다(설계 8.1, 결정 기록은 문서 작업).
> 지시와 다른 점: (1) 설계 10절은 "reverse 는 만들지 않는다"이지만, 0022 의 되돌리기를 `None`(IrreversibleError)으로 두면 기존 마이그레이션 테스트(0019·0009 등으로 내려가는 11개)가 모두 깨진다. 그래서 되돌리기 함수 `reverse_if_unused` 는 **점심당번 배정·기록·발송 기록·publish_undo lunch 행이 하나라도 있으면 "백업으로 복원하세요" RuntimeError 로 멈추고**, 하나도 없을 때(새 설치·테스트 DB)만 정의와 부서 시각을 지운다. 운영은 0022 가 바로 lunch 행을 만들므로 사실상 되돌릴 수 없다(파일 머리말에 명시, 테스트로 고정). 이 차이는 Task 8 의 PRINCIPLES 결정 기록에 "0022 는 점심당번 흔적이 없을 때만 내려간다(테스트 DB용), 운영 되돌리기는 백업 복원" 한 줄로 남기고, 최종 리뷰 때 사용자에게 알린다. (2) `generator.GenerationOutput` 에 `warnings` 칸을 더해 생성 경고("점심당번을 채우지 못한 날")를 회차 화면 messages.warning 으로 보인다. 3단계 direct 확정 경고 목록도 이 칸을 쓰면 된다.
> 하지 않는 것(뒤 작업): 근무표 고르기의 `?board=` 링크(이 작업의 `cell` 뷰·폼은 지금 `_board(user)` 그대로), 시장운영실 "기본 07:30 조·예외만 굵게" 표시, 문서(ARCHITECTURE·OPERATIONS·PRINCIPLES 결정 기록 "점심당번 부서별 시각"·"2단계 보고서 한 번 재발송", help STEPS).

**Files:**
- Modify: `duty/shifts.py`(머리말, `LUNCH`, `DUTY_KEYS`, `KEYS` 끝 `lunch`, 성격 상수 `SHIFT`·`SLOT`·`SOLO`, 새 `kind`·`lunch_defs`, `display_order`)
- Modify: `duty/models.py`(import, `_key_label`, `BoardShift` 제약 `boardshift_times_valid`, `Department.lunch_start/lunch_end` + 제약 `department_lunch_valid`, `DutyAssignment.cell` choices·제약, `ChangeLog.cell` 주석)
- Modify: `duty/admin.py`(`DepartmentForm.Meta.fields`)
- Create: `duty/migrations/0021_lunch.py`(makemigrations), `duty/migrations/0022_lunch_data.py`
- Modify: `duty/generator.py`(`GenerationOutput.warnings`), `duty/services/generate.py`(`run_generation`, 새 `_fill_lunch`), `duty/views/manage.py`(`period_action` 경고), `duty/services/stats.py`(`period_duty_counts`)
- Modify: `duty/services/changes.py`(import, 새 `_carry_lunch`, `change_cell`·`exchange`·`swap` 의 lunch 갈래·`carry_lunch`)
- Modify: `duty/services/prefs.py`(`choices`), `duty/views/roster.py`(import, `_cell_context`, `roster` 의 `day_info["commute"]`, `cell` POST), `duty/templates/duty/_cell_form.html`, `duty/templates/duty/day.html`
- Modify: `duty/services/roster.py`(`Day.excused`), `duty/alarms/messages.py`(문구 틀 셋), `duty/alarms/plan.py`(`RuleSpec.lunch`, 새 `_lunch_start`, `plan`·`_personal`·`_report`), `duty/alarms/schedule.py`(`same_day_notice`), `duty/services/alarm_runner.py`(새 `_lunch`, `collect`), `duty/services/alarms.py`(`save_rule`), `duty/services/calendar.py`(`_events`)
- Test: `tests/test_lunch.py`(새 파일. 뒤 단계가 끝에 이어 붙인다), `tests/test_migration_lunch.py`(새 파일), `tests/conftest.py`(`it_board` 가 lunch 정의를 지움, 새 `lunch` 픽스처), `tests/it_defs.py`(`IT_LUNCH`·`IT_DEFS2`), 상수 단언 5곳: `tests/test_alarm_models.py`·`test_board_owner.py`·`test_boards.py`·`test_boards_models.py`·`test_shifts.py`

**Interfaces:**
- Consumes: (1단계) `shifts.Def`·`by_key`·`ordered`·`shift_defs`·`slot_defs`·`cells_of`·`cell_label`·`cell_start`·`is_slot_cell`·`SLOT_GROUP_NAME`, `boards.defs/active_defs(board)`, `DutyAssignment(period, date, cell, member)`, `ChangeLog`, `changes._owner`·`_check_cell`·`_check_candidate`·`_slot_duties`, `roster.Day`·`published_days`, `alarms.plan.plan(defs, rules, days, info, deliveries, now, destinations=, dept_names=, extra_dates=, today=, closed=)`, `messages.personal_text/cancel_text/report_line/change_notice`, `schedule.same_day_notice(defs, kind, timing, offset, at_minute, shifts)`, `alarms.save_rule(user, data, rule=None)`·`normalize`, `alarm_runner.collect(now)`, `calendar._events(member, shifts=())`, `stats.period_duty_counts(period)`·`member_stats`, `prefs.choices(defs)`, `views/roster._cell_context`·`roster`·`cell`·`day`, conftest `it_board`·`depts`·`make_member`·`admin_user`·`admin_client_ok`·`fixed_today`. (Task 1) `Holiday`, `holidays.sync`. (Task 2) `memos.no_work_days`, `changes._owner` 의 근무 없음 검사. (Task 3) `boards.skip_dates(period)`, `run_generation` 의 `skip`·`dates`. (Task 4) `Commute.reason`, `Day.reasons`, `changes.set_reason`(당번 칸 경고), `REASONS`.
- Produces:
  - `duty.shifts`: `LUNCH = "lunch"`, `DUTY_KEYS = (*SLOT_KEYS, LUNCH)`, `KEYS = ["dawn", "normal", "dinner", *SLOT_KEYS, "night", "lunch"]`, `SHIFT, SLOT, SOLO = "shift", "slot", "solo"`, `kind(key: str) -> str`(근무조 SHIFT / `slot*` SLOT / `lunch` SOLO), `lunch_defs(defs) -> list[Def]`, `display_order(defs)` = 근무조(시작 순) → 점심당번 → 관제.
  - `BoardShift`: 키 선택지 표시 "점심당번", 제약 `boardshift_times_valid` = (lunch 이고 시각 둘 다 없음) 또는 (lunch 아니고 시각 둘 다 있고 start < end).
  - `Department.lunch_start`, `lunch_end`: `TimeField(null=True, blank=True)`, 제약 `department_lunch_valid`(violation_error_message "점심 시각은 둘 다 비우거나, 둘 다 넣고 시작을 끝보다 이르게 하세요."). 관리 화면 부서 폼에 두 칸.
  - `DutyAssignment.cell`: `DUTY_KEYS`(choices·`dutyassignment_cell_valid`). lunch 는 같은 날 여러 명(조건부 unique `dutyassignment_one_per_slot` 은 slot 만).
  - 마이그레이션 `0021_lunch`(의존 0020_reasons, auth 0012): 제약 다시 만들기·AddField 2개·AlterField 2개. `0022_lunch_data`(의존 0021): `RunPython(fill, reverse_if_unused)`. **다음 번호 0023.**
  - `generator.GenerationOutput.warnings: list[str]`(기본 빈 목록). `generate._fill_lunch(period, dates, skip, early: Def) -> list[str]`: `run_generation` 이 관제 저장 뒤 부른다(켜진 lunch 정의와 근무조가 있을 때만, 가장 이른 근무조 = `shift_defs(active)[0]`). 경고 문구 `"점심당번을 채우지 못한 날({근무조 이름} 출근 없음): 11/16, 11/17"`. `period_action` 이 `messages.warning` 으로 보인다.
  - `stats.period_duty_counts`: `cell__startswith="slot"` 만 센다(`member_stats` 는 원래 slot 만).
  - `changes.change_cell(user, board, d, cell, before, after, carry_lunch: bool = True)`, `exchange(..., carry_lunch: bool = True)`, `swap(user, board, d, cell_a, a, cell_b, b, carry_lunch: bool = True)`. lunch: 넣기·빼기·교체(오류 "…은(는) 이 칸에 없습니다." / "…은(는) 이미 이 칸에 있습니다."), `exchange` 는 lunch 를 늘 교체로, `swap` 은 `kind` 가 다르면 "출근조끼리 또는 관제 칸끼리만 맞교환할 수 있습니다.". `_carry_lunch(user, period, d, before, after)`: 근무조 칸에서 From·To 가 모두 있고 From 이 그날 점심당번, To 는 아니면 넘기고 `ChangeLog(cell="lunch")` 를 근무조 기록(맞교환이면 두 기록) **뒤에** 남긴다. 맞교환(`swap`)은 두 사람 다 떠나는 사람이라 둘 중 점심당번인 쪽이 상대에게 넘긴다(From·To 어느 쪽이 점심당번이어도, 둘 다면 그대로).
  - `prefs.choices(defs)`: 근무조 → `slots`(관제가 있으면) → `lunch`(정의가 있으면).
  - 화면: `day_info["commute"]` = 근무조 + 점심당번 칸(같은 마크업, 라벨 "점심당번", 시각 없음). `_cell_context` 사전에 `"lunch": bool`(사유 폼 숨김, 안내 "From 대신 To 가 점심당번이 됩니다."), `"carry": bool`(근무조 칸이고 켜진 lunch 정의가 있을 때 체크박스 `name="carry_lunch" value="1" checked` "점심당번도 같이 넘기기"). `cell` POST 는 `carry_lunch=request.POST.get("carry_lunch") == "1"`.
  - `roster.Day.excused(cell, name) -> bool`: 사유가 붙은 근무조 배정, 또는 그날 사유가 있는 사람의 점심당번.
  - 알림: `RuleSpec.lunch: tuple[time, time] | None = None`(개인 규칙 주인 부서의 점심 시각, `alarm_runner._lunch(rule)` 이 채움). `messages.cell_span(defs, cell, lunch=None)`·`personal_text(..., today, lunch=None)`·`cancel_text(..., successor=None, lunch=None)`. 문구: 개인 `"[당번 알림] 11/16(월) 점심당번 11:30~12:30\n가님, 내일 점심당번입니다."`(시각 없으면 `"… 점심당번\n…"`), 보고서 줄 `"점심당번 가, 나"`(KEYS 끝이라 기존 줄 뒤), 변경 알림 위치 `"점심당번"`. `plan._lunch_start(r, d)`: 부서 시각이 있으면 그 시작, 없으면 시각 기준 규칙은 None(빠짐)·날짜 기준 규칙은 다음 날 00:00(발송 창 끝·만료). 보고서 발송 창·만료와 `same_day_notice` 는 lunch 를 뺀 칸으로. `alarms.save_rule`: 보고서 스케줄이 `["lunch"]` 뿐이면 `DutyError("보고서는 시각이 있는 근무를 하나 이상 고르세요. 점심당번만으로는 보낼 수 없습니다.")`.
  - 캘린더: 점심당번 일정 summary = 정의 이름("점심당번"), 시각 = 부서 점심 시각(없으면 일정 없음), UID `날짜-lunch-pk`, 사유가 있는 날 빠짐.
  - 테스트 도구: conftest `lunch` 픽스처(IT 점심당번 `BoardShift`), `tests/it_defs.IT_LUNCH`·`IT_DEFS2`(= IT_DEFS + IT_LUNCH, KEYS 순).

- [ ] **Step 1: 키·성격·모델·관리 화면 테스트를 먼저 쓰고, 테스트 도구와 상수 단언을 맞춘다**

`tests/test_lunch.py`(새 파일. 뒤 단계가 끝에 이어 붙인다. import 는 처음부터 다 넣는다):
```python
"""점심당번(설계 2·4.1·4.4·6.3·6.4·7·8). 혼자인 당번 칸: 가장 이른 근무조를 따라가고 인원 제한 없음, 정의에는 시각이
없고 알림·캘린더 시각은 사람 부서의 점심 시각. 이름은 모두 가상."""
from datetime import date, datetime, time, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from duty.admin import DepartmentForm
from duty.alarms import messages as m
from duty.alarms.plan import RuleSpec, plan
from duty.alarms.schedule import same_day_notice
from duty.errors import DutyError
from duty.models import (AlarmRule, Board, BoardShift, ChangeLog, Commute, Department, DutyAssignment, Holiday, Period,
                         TelegramAlarmProfile)
from duty.services import alarm_runner, alarm_settings, alarms, calendar, change_notice, changes, prefs, stats
from duty.services.generate import run_generation
from duty.services.roster import Day
from duty.shifts import DUTY_KEYS, KEYS, LUNCH, SHIFT, SLOT, SLOT_KEYS, SOLO, cells_of, display_order, kind
from tests.it_defs import IT_DEFS, IT_DEFS2
from tests.test_alarm_texts_it import REPORT_BODY

S = Period.Status
T = date(2026, 11, 10)  # 화
NOW = timezone.make_aware(datetime(2026, 11, 10, 9, 0))
MON, TUE = date(2026, 11, 16), date(2026, 11, 17)
NOON = (time(11, 30), time(12, 30))


def _bad(fn):
    with pytest.raises(IntegrityError), transaction.atomic():
        fn()


# ── 키·성격·모델·관리 화면 ──

def test_keys_kind_and_order():
    assert KEYS[-1] == LUNCH == "lunch" and DUTY_KEYS == (*SLOT_KEYS, LUNCH)  # 순회 순서의 끝(기존 칸 hash 불변)
    assert [kind(k) for k in ("dawn", "night", "slot0", "slot9", "lunch")] == [SHIFT, SHIFT, SLOT, SLOT, SOLO]
    assert [x.key for x in display_order(IT_DEFS2)][:6] == ["dawn", "normal", "dinner", "night", "lunch", "slot0"]
    assert cells_of(IT_DEFS2, []) == KEYS and cells_of(IT_DEFS2, ["lunch", "dawn"]) == ["dawn", "lunch"]


def test_lunch_definition_has_no_times(it_board):
    ops = Board.objects.create(code="ops", name="운영팀", input_mode=Board.InputMode.DIRECT)
    BoardShift.objects.create(board=ops, key="dawn", name="이른조", start=time(7), end=time(16))
    BoardShift.objects.create(board=ops, key="lunch", name="점심당번")
    _bad(lambda: BoardShift.objects.create(board=ops, key="normal", name="가운데조"))  # 근무조는 시각 필수
    _bad(lambda: BoardShift.objects.filter(board=ops, key="lunch").update(start=time(11), end=time(12)))


def test_lunch_rows_have_no_head_limit(lunch, make_member, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=T, end_date=T)
    a, b = make_member("가"), make_member("나")
    DutyAssignment.objects.create(period=p, date=T, cell="lunch", member=a)
    DutyAssignment.objects.create(period=p, date=T, cell="lunch", member=b)  # 인원 제한 없음
    _bad(lambda: DutyAssignment.objects.create(period=p, date=T, cell="lunch", member=a))  # 같은 사람 두 번은 안 됨
    _bad(lambda: DutyAssignment.objects.create(period=p, date=T, cell="dawn", member=a))  # 근무조 키는 당번 칸이 아니다
    ChangeLog.objects.create(period=p, date=T, cell="lunch", before=a, after=b)


def test_department_lunch_times(depts):
    ui = Department.objects.filter(pk=depts["UI"].pk)
    _bad(lambda: ui.update(lunch_start=time(11, 30)))
    _bad(lambda: ui.update(lunch_start=time(12, 30), lunch_end=time(11, 30)))
    ui.update(lunch_start=time(11, 30), lunch_end=time(12, 30))


def test_admin_department_form_lunch(depts):
    ui = depts["UI"]
    data = {"code": ui.code, "name": ui.name, "board": ui.board_id, "order": ui.order, "shifts": ["normal"],
            "managers": []}
    form = DepartmentForm({**data, "lunch_start": "11:30", "lunch_end": ""}, instance=ui)
    assert not form.is_valid() and "점심 시각은 둘 다 비우거나" in str(form.errors)
    form = DepartmentForm({**data, "lunch_start": "11:30", "lunch_end": "12:30"}, instance=ui)
    assert form.is_valid(), form.errors
    assert form.save().lunch_end == time(12, 30)
```

`tests/conftest.py`·`tests/it_defs.py`(테스트 DB 의 IT 근무표는 마이그레이션 0022 뒤 점심당번 정의를 갖는다. 기본 테스트는 그 정의를 지운 1단계 IT 로, 점심당번 테스트는 `lunch` 픽스처로):
```diff
diff --git a/tests/conftest.py b/tests/conftest.py
--- a/tests/conftest.py
+++ b/tests/conftest.py
@@ -3,6 +3,7 @@ from itertools import count
 import pytest
 
 from duty.models import Board, BoardShift, Department, User
+from duty.shifts import LUNCH
 from tests.it_defs import IT_DEFS
 
 DEPTS = [
@@ -21,9 +22,17 @@ def it_board(db):
         BoardShift.objects.get_or_create(board=board, key=d.key, defaults=dict(
             name=d.name, start=d.start, end=d.end, eligible_shifts=list(d.eligible_shifts),
             eligible_types=list(d.eligible_types), default_alarm=d.default_alarm))
+    # 마이그레이션 0022 가 넣은 점심당번 정의는 뺀다: 기본 테스트는 1단계 IT 정의로 돌고, 점심당번 테스트는 lunch 픽스처로 켠다
+    BoardShift.objects.filter(board=board, key=LUNCH).delete()
     return board
 
 
+@pytest.fixture
+def lunch(it_board):
+    """IT 근무표에 점심당번 정의(시각 없음, 운영 마이그레이션 0022 와 같은 값)."""
+    return BoardShift.objects.create(board=it_board, key=LUNCH, name="점심당번")
+
+
 @pytest.fixture
 def depts(it_board):
     # order = 지금 근무표 부서 필터 순서(views/roster.py DEPT_ORDER: MEMS·TMCH·MD·UI = DEPTS 순서)
diff --git a/tests/it_defs.py b/tests/it_defs.py
--- a/tests/it_defs.py
+++ b/tests/it_defs.py
@@ -27,4 +27,7 @@ IT_DEFS: list[Def] = [  # KEYS 순. active 는 기본값 True(IT 정의는 모
     Def("night", "야간", time(13, 30), time(21, 30), default_alarm=True),
 ]
 
+IT_LUNCH = Def("lunch", "점심당번", None, None)  # 2단계 점심당번 정의(마이그레이션 0022, conftest lunch 픽스처와 같은 값)
+IT_DEFS2: list[Def] = [*IT_DEFS, IT_LUNCH]  # 2단계 IT 정의(KEYS 순)
+
 IT_SLOTS = [(x.name, x.eligible_shifts, x.eligible_types) for x in slot_defs(IT_DEFS)]  # generator 칸 목록(옛 CONTROL_SLOTS 의 값·순서 + 개발자)
```

`KEYS` 끝에 lunch 가 붙어 깨지는 기존 상수 단언 5곳(뜻은 그대로: IT 정의·칸 순회 = KEYS 에서 lunch 를 뺀 것. `test_alarm_models` 는 lunch 가 이제 맞는 칸이라 틀린 값을 `slot10` 으로):
```diff
diff --git a/tests/test_alarm_models.py b/tests/test_alarm_models.py
--- a/tests/test_alarm_models.py
+++ b/tests/test_alarm_models.py
@@ -59,7 +59,7 @@ def test_delivery_constraints(user):
     _bad(lambda: _delivery(r))
     _delivery(r, destination="2")  # 목적지가 다르면 허용
     _bad(lambda: _delivery(r, channel="sms", cell="normal"))
-    _bad(lambda: _delivery(r, cell="lunch"))
+    _bad(lambda: _delivery(r, cell="slot10"))
     _bad(lambda: _delivery(r, cell="normal", status="x"))
     _bad(lambda: _delivery(r, cell="normal", attempts=-1))
     _delivery(r, cell="report", status="failed", attempts=1, next_attempt_at=timezone.now())
diff --git a/tests/test_board_owner.py b/tests/test_board_owner.py
--- a/tests/test_board_owner.py
+++ b/tests/test_board_owner.py
@@ -111,7 +111,7 @@ def test_published_days_includes_owned_days_without_rows(it_board, make_member):
     days = published_days(it_board, d(11, 9), d(11, 10))
     assert [x.date for x in days] == [d(11, 9), d(11, 10)]
     assert days[1].period_id == p.pk and not any(days[1].members.values())
-    assert list(days[0].cells) == shifts.KEYS  # 칸 순회 순서 = KEYS(알림 hash 불변)
+    assert list(days[0].cells) == [k for k in shifts.KEYS if k != shifts.LUNCH]  # 칸 순회 순서 = KEYS(알림 hash 불변)
 
 
 def test_published_days_uses_only_owner_rows(it_board, make_member):
diff --git a/tests/test_boards.py b/tests/test_boards.py
--- a/tests/test_boards.py
+++ b/tests/test_boards.py
@@ -7,7 +7,7 @@ from tests.it_defs import IT_DEFS
 def test_it_board_defs_match_it_definitions(it_board):
     assert boards.it_board() == it_board
     got = boards.defs(it_board)
-    assert [d.key for d in got] == KEYS
+    assert [d.key for d in got] == [k for k in KEYS if k != "lunch"]
     assert by_key(got) == by_key(IT_DEFS)
 
 
diff --git a/tests/test_boards_models.py b/tests/test_boards_models.py
--- a/tests/test_boards_models.py
+++ b/tests/test_boards_models.py
@@ -7,7 +7,7 @@ from django.db import IntegrityError, transaction
 
 from duty.models import Board, BoardShift, Department, GroupKeeper
 from duty.shifts import KEYS
-from tests.it_defs import IT_DEFS
+from tests.it_defs import IT_DEFS2
 
 
 def _bad(fn):
@@ -16,12 +16,12 @@ def _bad(fn):
 
 
 def test_it_defs_match_keys_order():
-    assert [d.key for d in IT_DEFS] == KEYS
+    assert [d.key for d in IT_DEFS2] == KEYS
 
 
 def test_it_board_fixture_has_14_defs_and_admin_group(it_board):
     assert it_board.code == "it" and it_board.input_mode == "collect"
-    assert sorted(it_board.shifts.values_list("key", flat=True)) == sorted(KEYS)
+    assert sorted(it_board.shifts.values_list("key", flat=True)) == sorted(k for k in KEYS if k != "lunch")
     assert it_board.admin_group_id is not None
 
 
diff --git a/tests/test_shifts.py b/tests/test_shifts.py
--- a/tests/test_shifts.py
+++ b/tests/test_shifts.py
@@ -39,7 +39,7 @@ def test_cell_times():
 
 
 def test_cells_of():
-    assert cells_of(IT_DEFS, []) == KEYS
+    assert cells_of(IT_DEFS, []) == [k for k in KEYS if k != "lunch"]
     assert cells_of(IT_DEFS, ["night", "dawn"]) == ["dawn", "night"]
     assert cells_of(IT_DEFS, ["slots"]) == [f"slot{i}" for i in range(10)]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_lunch.py`
Expected: conftest 를 읽다 멈춘다 — `ImportError while loading conftest … cannot import name 'LUNCH' from 'duty.shifts'`(conftest 를 고치기 전이면 `cannot import name 'DUTY_KEYS'` 수집 오류).

- [ ] **Step 3: 키·성격 상수와 모델·관리 화면·스키마 마이그레이션을 만든다**
```diff
diff --git a/duty/admin.py b/duty/admin.py
--- a/duty/admin.py
+++ b/duty/admin.py
@@ -30,7 +30,7 @@ class DepartmentForm(forms.ModelForm):
 
     class Meta:
         model = Department
-        fields = ["code", "name", "board", "order", "shifts"]
+        fields = ["code", "name", "board", "order", "shifts", "lunch_start", "lunch_end"]
 
     def __init__(self, *args, **kwargs):
         super().__init__(*args, **kwargs)
diff --git a/duty/models.py b/duty/models.py
--- a/duty/models.py
+++ b/duty/models.py
@@ -7,7 +7,9 @@ from django.db.models import F, Func, Q, Value
 from django.db.models.lookups import Exact
 
 from .csv_io import split_reason
-from .shifts import DEVELOPER, KEYS, REASONS, SHIFT_KEYS, SLOT_KEYS, STAFF, is_slot_cell, slot_index, weekdays
+from .shifts import (
+    DEVELOPER, DUTY_KEYS, KEYS, LUNCH, REASONS, SHIFT_KEYS, STAFF, is_slot_cell, slot_index, weekdays,
+)
 
 
 REASON_CHOICES = [("", "없음"), *((r, r) for r in REASONS)]
@@ -64,6 +66,8 @@ class Board(models.Model):
 
 def _key_label(key: str) -> str:
     # 관리 화면 표시는 중립적으로(시장운영실이 dawn 을 '새벽'으로 오해하지 않게). DB 값은 키 그대로
+    if key == LUNCH:
+        return "점심당번"
     return f"관제 {slot_index(key) + 1}" if is_slot_cell(key) else f"근무조 {SHIFT_KEYS.index(key) + 1}"
 
 
@@ -86,9 +90,10 @@ class BoardShift(models.Model):
             # 이름은 CSV 열 이름·화면 라벨이 된다. 겹치면 CSV 열이 하나로 합쳐져 값이 사라지므로 DB 가 막는다
             models.UniqueConstraint(fields=["board", "name"], name="boardshift_one_per_name"),
             _one_of("key", KEYS, "boardshift_key_valid"),
-            # 1단계 키(근무조·관제)는 시각이 필수이고 당일 근무만(2단계에 시각 없는 점심당번을 더한다)
-            models.CheckConstraint(name="boardshift_times_valid",
-                                   condition=Q(start__isnull=False, end__isnull=False, start__lt=models.F("end"))),
+            # 근무조·관제는 시각이 필수이고 당일 근무만. 점심당번은 시각을 비운다(시각은 부서마다 Department.lunch_*)
+            models.CheckConstraint(name="boardshift_times_valid", condition=(
+                Q(key=LUNCH, start__isnull=True, end__isnull=True)
+                | (~Q(key=LUNCH) & Q(start__isnull=False, end__isnull=False, start__lt=models.F("end"))))),
         ]
 
     def __str__(self):
@@ -114,10 +119,19 @@ class Department(models.Model):
     order = models.IntegerField("순서", default=99, help_text="근무표 부서 필터 순서(작은 값이 앞, 기본 99는 맨 뒤)")
     input_group = models.OneToOneField(Group, on_delete=models.PROTECT, null=True, blank=True, editable=False,
                                        related_name="input_department", verbose_name="입력 그룹")
+    # 점심당번 시각(개인 알림·캘린더). 비우면 시각 기준 알림·캘린더 일정에서 점심당번이 빠진다
+    lunch_start = models.TimeField("점심 시작", null=True, blank=True)
+    lunch_end = models.TimeField("점심 끝", null=True, blank=True)
 
     class Meta:
         verbose_name = verbose_name_plural = "부서"
         ordering = ["code"]
+        constraints = [models.CheckConstraint(
+            name="department_lunch_valid",
+            condition=Q(lunch_start__isnull=True, lunch_end__isnull=True)
+            | Q(lunch_start__isnull=False, lunch_end__isnull=False, lunch_start__lt=F("lunch_end")),
+            violation_error_message="점심 시각은 둘 다 비우거나, 둘 다 넣고 시작을 끝보다 이르게 하세요.",
+        )]
 
     def __str__(self):
         return self.name
@@ -307,10 +321,10 @@ class Commute(models.Model):
 
 
 class DutyAssignment(models.Model):
-    """당번 배정 한 칸(1단계는 장중관제 slot0~slot9). 생성이 만들고 근무 변경이 바꾼다."""
+    """당번 배정 한 칸(장중관제 slot0~slot9, 점심당번 lunch). 생성이 만들고 근무 변경이 바꾼다."""
     period = models.ForeignKey(Period, on_delete=models.CASCADE, related_name="duty_assignments")
     date = models.DateField()
-    cell = models.CharField(max_length=8, choices=[(k, k) for k in SLOT_KEYS])
+    cell = models.CharField(max_length=8, choices=[(k, k) for k in DUTY_KEYS])
     member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
 
     class Meta:
@@ -319,7 +333,7 @@ class DutyAssignment(models.Model):
             # 관제 칸은 칸당 한 명(DB가 계속 보장)
             models.UniqueConstraint(fields=["period", "date", "cell"], condition=Q(cell__startswith="slot"),
                                     name="dutyassignment_one_per_slot"),
-            _one_of("cell", SLOT_KEYS, "dutyassignment_cell_valid"),
+            _one_of("cell", DUTY_KEYS, "dutyassignment_cell_valid"),
         ]
         indexes = [models.Index(fields=["date"])]
 
@@ -329,7 +343,7 @@ class ChangeLog(models.Model):
     by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)  # null = 예전 시트 가져오기 기록. 계정은 삭제 대신 비활성화
     period = models.ForeignKey(Period, on_delete=models.PROTECT)  # 변경 기록은 남긴다: 기록 있는 회차는 삭제 불가
     date = models.DateField()
-    cell = models.CharField(max_length=8)  # dawn|normal|dinner|night|slot0..slot9
+    cell = models.CharField(max_length=8)  # KEYS 중 하나(근무조·slot0..slot9·lunch)
     before = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
     after = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
     notified = models.BooleanField(default=False)  # 당사자에게 '근무 변경' 알림을 보냈는지(작업자가 표시)
diff --git a/duty/shifts.py b/duty/shifts.py
--- a/duty/shifts.py
+++ b/duty/shifts.py
@@ -1,6 +1,7 @@
 """칸 키와 근무 정의(Def) 헬퍼. ORM 없음.
 
-칸 키(KEYS)는 고정 목록이고 키 글자가 성격을 정한다: dawn·normal·dinner·night = 근무조, slot* = 장중관제.
+칸 키(KEYS)는 고정 목록이고 키 글자가 성격을 정한다: dawn·normal·dinner·night = 근무조, slot* = 장중관제,
+lunch = 점심당번.
 이름·시각·자격은 근무표마다 DB(BoardShift)에 있고, 아래 헬퍼는 그 정의 목록(defs)을 인자로 받는다(기본값 없음).
 """
 
@@ -9,9 +10,14 @@ from datetime import date, time, timedelta
 
 SHIFT_KEYS = ("dawn", "normal", "dinner", "night")  # 근무조 키(한 사람 하루 하나)
 SLOT_KEYS = tuple(f"slot{i}" for i in range(10))  # 장중관제 칸 키(자동 생성, 칸당 1명)
-# 근무표가 쓸 수 있는 키 전부. 순서 = 알림·캘린더 칸 순회 순서(바꾸면 알림 hash 가 달라져 다시 나간다)
-KEYS: list[str] = ["dawn", "normal", "dinner", *SLOT_KEYS, "night"]
+# 점심당번: 혼자인 당번 칸. 그 근무표의 가장 이른 근무조에 근무로 친 사람이 기본, 인원 제한 없음.
+# 정의에는 시각이 없고(화면은 "점심당번"만) 알림·캘린더 시각은 사람 부서의 Department.lunch_start/end
+LUNCH = "lunch"
+DUTY_KEYS = (*SLOT_KEYS, LUNCH)  # 당번 칸 키(DutyAssignment.cell)
+# 근무표가 쓸 수 있는 키 전부. 순서 = 알림·캘린더 칸 순회 순서(바꾸면 알림 hash 가 달라져 다시 나간다). lunch 는 2단계에 끝에 붙였다
+KEYS: list[str] = ["dawn", "normal", "dinner", *SLOT_KEYS, "night", LUNCH]
 SLOT_GROUP, SLOT_GROUP_NAME, SLOT_GROUP_SHORT = "slots", "장중관제", "관제"  # 장중관제 묶음 키·이름·짧은 이름
+SHIFT, SLOT, SOLO = "shift", "slot", "solo"  # 키의 성격: 근무조 / 묶음 당번 칸(장중관제) / 혼자인 당번 칸(점심당번)
 
 DEVELOPER = "개발자"
 STAFF = "직원"
@@ -38,6 +44,11 @@ def is_slot_cell(cell: str) -> bool:
     return cell.startswith("slot")
 
 
+def kind(key: str) -> str:
+    """키의 성격(SHIFT·SLOT·SOLO). 같은 성격끼리만 맞교환하고, 알림 문구 틀도 이것으로 고른다."""
+    return SLOT if is_slot_cell(key) else SOLO if key == LUNCH else SHIFT
+
+
 def slot_index(cell: str) -> int:
     return int(cell[4:])
 
@@ -61,9 +72,14 @@ def slot_defs(defs: list[Def]) -> list[Def]:
     return ordered([x for x in defs if is_slot_cell(x.key)])
 
 
+def lunch_defs(defs: list[Def]) -> list[Def]:
+    """점심당번 정의(없으면 빈 목록)."""
+    return [x for x in defs if x.key == LUNCH]
+
+
 def display_order(defs: list[Def]) -> list[Def]:
-    """화면 순서: 근무조(시작 시각 순) → 장중관제(키 순)."""
-    return shift_defs(defs) + slot_defs(defs)
+    """화면 순서: 근무조(시작 시각 순) → 점심당번 → 장중관제(키 순)."""
+    return shift_defs(defs) + lunch_defs(defs) + slot_defs(defs)
 
 
 def cell_label(defs: list[Def], cell: str) -> str:
```

마이그레이션은 손으로 쓰지 않고 만든다: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty -n lunch`. 결과 `duty/migrations/0021_lunch.py`(머리 줄의 생성 시각만 다를 수 있다):
```python
# Generated by Django 5.2.19 on 2026-11-15 14:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('duty', '0020_reasons'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='alarmdelivery',
            name='alarmdelivery_cell_valid',
        ),
        migrations.RemoveConstraint(
            model_name='boardshift',
            name='boardshift_key_valid',
        ),
        migrations.RemoveConstraint(
            model_name='boardshift',
            name='boardshift_times_valid',
        ),
        migrations.RemoveConstraint(
            model_name='changelog',
            name='changelog_cell_valid',
        ),
        migrations.RemoveConstraint(
            model_name='dutyassignment',
            name='dutyassignment_cell_valid',
        ),
        migrations.AddField(
            model_name='department',
            name='lunch_end',
            field=models.TimeField(blank=True, null=True, verbose_name='점심 끝'),
        ),
        migrations.AddField(
            model_name='department',
            name='lunch_start',
            field=models.TimeField(blank=True, null=True, verbose_name='점심 시작'),
        ),
        migrations.AlterField(
            model_name='boardshift',
            name='key',
            field=models.CharField(choices=[('dawn', '근무조 1'), ('normal', '근무조 2'), ('dinner', '근무조 3'), ('slot0', '관제 1'), ('slot1', '관제 2'), ('slot2', '관제 3'), ('slot3', '관제 4'), ('slot4', '관제 5'), ('slot5', '관제 6'), ('slot6', '관제 7'), ('slot7', '관제 8'), ('slot8', '관제 9'), ('slot9', '관제 10'), ('night', '근무조 4'), ('lunch', '점심당번')], max_length=8, verbose_name='키'),
        ),
        migrations.AlterField(
            model_name='dutyassignment',
            name='cell',
            field=models.CharField(choices=[('slot0', 'slot0'), ('slot1', 'slot1'), ('slot2', 'slot2'), ('slot3', 'slot3'), ('slot4', 'slot4'), ('slot5', 'slot5'), ('slot6', 'slot6'), ('slot7', 'slot7'), ('slot8', 'slot8'), ('slot9', 'slot9'), ('lunch', 'lunch')], max_length=8),
        ),
        migrations.AddConstraint(
            model_name='alarmdelivery',
            constraint=models.CheckConstraint(condition=models.Q(('cell__in', ['dawn', 'normal', 'dinner', 'slot0', 'slot1', 'slot2', 'slot3', 'slot4', 'slot5', 'slot6', 'slot7', 'slot8', 'slot9', 'night', 'lunch', 'report'])), name='alarmdelivery_cell_valid'),
        ),
        migrations.AddConstraint(
            model_name='boardshift',
            constraint=models.CheckConstraint(condition=models.Q(('key__in', ['dawn', 'normal', 'dinner', 'slot0', 'slot1', 'slot2', 'slot3', 'slot4', 'slot5', 'slot6', 'slot7', 'slot8', 'slot9', 'night', 'lunch'])), name='boardshift_key_valid'),
        ),
        migrations.AddConstraint(
            model_name='boardshift',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('end__isnull', True), ('key', 'lunch'), ('start__isnull', True)), models.Q(models.Q(('key', 'lunch'), _negated=True), ('end__isnull', False), ('start__isnull', False), ('start__lt', models.F('end'))), _connector='OR'), name='boardshift_times_valid'),
        ),
        migrations.AddConstraint(
            model_name='changelog',
            constraint=models.CheckConstraint(condition=models.Q(('cell__in', ['dawn', 'normal', 'dinner', 'slot0', 'slot1', 'slot2', 'slot3', 'slot4', 'slot5', 'slot6', 'slot7', 'slot8', 'slot9', 'night', 'lunch'])), name='changelog_cell_valid'),
        ),
        migrations.AddConstraint(
            model_name='department',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('lunch_end__isnull', True), ('lunch_start__isnull', True)), models.Q(('lunch_end__isnull', False), ('lunch_start__isnull', False), ('lunch_start__lt', models.F('lunch_end'))), _connector='OR'), name='department_lunch_valid', violation_error_message='점심 시각은 둘 다 비우거나, 둘 다 넣고 시작을 끝보다 이르게 하세요.'),
        ),
        migrations.AddConstraint(
            model_name='dutyassignment',
            constraint=models.CheckConstraint(condition=models.Q(('cell__in', ['slot0', 'slot1', 'slot2', 'slot3', 'slot4', 'slot5', 'slot6', 'slot7', 'slot8', 'slot9', 'lunch'])), name='dutyassignment_cell_valid'),
        ),
    ]
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_lunch.py tests/test_alarm_models.py tests/test_board_owner.py tests/test_boards.py tests/test_boards_models.py tests/test_shifts.py`
Expected: 모두 통과. 전체 `.venv/bin/pytest -W error -q` → 1048 passed(사본 기준).

- [ ] **Step 5: 데이터 마이그레이션 테스트를 쓴다**

`tests/test_migration_lunch.py`(새 파일. `test_migration_reasons.py` 와 같은 틀. 마이그레이션의 "오늘"은 `django.utils.timezone.localdate` 를 가로채 정한다):
```python
"""0022: IT 점심당번 정의·부서 점심 시각, 오늘 이후 배포됨·생성됨 회차의 새벽 근무자로 점심당번 채우기(설계 10절 2단계).
되돌리기는 없다(점심당번이 쓰인 DB 는 멈춘다). 이름은 모두 가상."""
from datetime import date, time

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0021_lunch")]
AFTER = [("duty", "0022_lunch_data")]
TODAY = date(2026, 11, 16)  # 월. 마이그레이션의 "오늘"


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_apps(monkeypatch):
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *a, **kw: TODAY)
    apps = _migrate(BEFORE)  # 테스트 DB 에는 점심당번 배정이 없어 내려갈 수 있다
    yield apps
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())  # 다른 테스트를 위해 최신 스키마로


def _world(apps):
    Board, Department, User = (apps.get_model("duty", n) for n in ("Board", "Department", "User"))
    Period, Commute = apps.get_model("duty", "Period"), apps.get_model("duty", "Commute")
    it = Board.objects.get(code="it")
    Department.objects.create(code="MEMS", name="매칭엔진실", shifts="dawn,normal", board=it)
    m = {n: User.objects.create(username=f"T{i}", name=n) for i, n in enumerate(["가", "나", "다", "라"])}

    def period(name, status, **kw):
        return Period.objects.create(board=it, name=name, start_date=date(2026, 11, 13), end_date=date(2026, 11, 20),
                                     status=status, **kw)

    pub, gen, closed = period("배포", "published", publish_undo=[]), period("생성", "generated"), period("마감", "closed")
    for p in (pub, gen, closed):
        Commute.objects.create(period=p, date=date(2026, 11, 13), member=m["가"], shift="dawn")  # 지난 금요일
        Commute.objects.create(period=p, date=TODAY, member=m["가"], shift="dawn")
        Commute.objects.create(period=p, date=TODAY, member=m["나"], shift="dawn", reason="휴가")
        Commute.objects.create(period=p, date=TODAY, member=m["다"], shift="normal")
    pub.publish_undo = [
        ["c", gen.pk, "2026-11-13", m["라"].pk, "dawn", ""],  # 지난 날
        ["c", gen.pk, "2026-11-17", m["라"].pk, "dawn"],  # 2단계 전 다섯 칸 행
        ["c", gen.pk, "2026-11-18", m["라"].pk, "dawn", "출장"],
        ["c", gen.pk, "2026-11-18", m["다"].pk, "normal", ""],
        ["a", gen.pk, "2026-11-18", m["다"].pk, "slot0"],
    ]
    pub.save()
    return it, m, pub, gen, closed


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_fills_it_lunch_from_dawn_workers(old_apps):
    it, m, pub, gen, closed = _world(old_apps)
    apps = _migrate(AFTER)
    BoardShift, Department = apps.get_model("duty", "BoardShift"), apps.get_model("duty", "Department")
    lunch = BoardShift.objects.get(board_id=it.pk, key="lunch")
    assert (lunch.name, lunch.start, lunch.end) == ("점심당번", None, None)
    assert Department.objects.filter(code="MEMS").values_list("lunch_start", "lunch_end").get() == (time(11, 30), time(12, 30))
    rows = apps.get_model("duty", "DutyAssignment").objects.filter(cell="lunch")
    # 오늘(포함) 이후, 배포됨·생성됨 회차, 새벽, 사유 없음만
    assert sorted(rows.values_list("period_id", "date", "member_id")) == sorted(
        [(pub.pk, TODAY, m["가"].pk), (gen.pk, TODAY, m["가"].pk)])
    assert not apps.get_model("duty", "ChangeLog").objects.exists()  # 기록·알림 없음
    undo = apps.get_model("duty", "Period").objects.get(pk=pub.pk).publish_undo
    assert undo[5:] == [["a", gen.pk, "2026-11-17", m["라"].pk, "lunch"]]  # 기존 행 뒤에 하나만


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_no_reverse_once_lunch_is_used(old_apps):
    _world(old_apps)
    _migrate(AFTER)
    with pytest.raises(RuntimeError, match="백업"):
        _migrate(BEFORE)
```

- [ ] **Step 6: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_migration_lunch.py`
Expected: 2 failed — `NodeNotFoundError: Node ('duty', '0022_lunch_data') not a valid node`.

- [ ] **Step 7: 데이터 마이그레이션을 쓴다**

`duty/migrations/0022_lunch_data.py`(새 파일, 앱 코드를 import 하지 않는다):
```python
"""IT 근무표에 점심당번을 넣는다(설계 10절 2단계). 앱 코드를 import 하지 않고 값을 그대로 적는다.

- IT 점심당번 정의(시각 없음), IT 부서 점심 11:30–12:30.
- 오늘(마이그레이션이 도는 날, Asia/Seoul)부터 배포됨·생성됨 회차의 새벽 근무자(사유 없음)를 점심당번으로 채운다.
  ChangeLog·알림은 남기지 않는다. 배포됨 회차의 publish_undo 새벽 c 행(오늘 이후)에도 lunch a 행을 더한다
  (배포 취소로 되살아난 날에도 점심당번이 있게).
- 되돌리기는 만들지 않는다: 운영에 점심당번 행·기록·발송 기록이 쌓이므로 되돌리기는 업그레이드 전 백업 복원으로만 한다.
  점심당번 행·기록이 하나도 없는 DB(새 설치·테스트)에서만 정의와 부서 시각을 지우고 내려간다.
"""
from datetime import time

from django.db import migrations
from django.utils import timezone

IT_LUNCH = (time(11, 30), time(12, 30))


def fill(apps, schema_editor):
    Board, BoardShift, Department = (apps.get_model("duty", n) for n in ("Board", "BoardShift", "Department"))
    Period, Commute, DutyAssignment = (apps.get_model("duty", n) for n in ("Period", "Commute", "DutyAssignment"))
    board = Board.objects.filter(code="it").first()
    if board is None:  # 0011 이 IT 근무표를 만든다. 지워진 DB 면 할 일이 없다
        return
    BoardShift.objects.get_or_create(board=board, key="lunch", defaults={"name": "점심당번"})
    Department.objects.filter(board=board).update(lunch_start=IT_LUNCH[0], lunch_end=IT_LUNCH[1])
    today = timezone.localdate()
    periods = Period.objects.filter(board=board, status__in=["published", "generated"])
    dawn = Commute.objects.filter(period__in=periods, date__gte=today, shift="dawn", reason="")
    DutyAssignment.objects.bulk_create(
        [DutyAssignment(period_id=c.period_id, date=c.date, member_id=c.member_id, cell="lunch") for c in dawn],
        ignore_conflicts=True)
    for p in periods.filter(status="published").exclude(publish_undo=None):
        add = [["a", r[1], r[2], r[3], "lunch"] for r in p.publish_undo
               if r[0] == "c" and r[4] == "dawn" and (r[5:] or [""])[0] == "" and r[2] >= today.isoformat()]
        if add:
            p.publish_undo = p.publish_undo + add
            p.save(update_fields=["publish_undo"])


def reverse_if_unused(apps, schema_editor):
    """되돌리기 없음. 점심당번이 한 번도 쓰이지 않은 DB 만 정의·부서 시각을 지우고 내려간다(0021 의 제약이 통과하게)."""
    BoardShift, Department, Period = (apps.get_model("duty", n) for n in ("BoardShift", "Department", "Period"))
    used = any(apps.get_model("duty", n).objects.filter(cell="lunch").exists()
               for n in ("DutyAssignment", "ChangeLog", "AlarmDelivery"))
    used = used or any(r[0] == "a" and r[4] == "lunch"
                       for undo in Period.objects.exclude(publish_undo=None).values_list("publish_undo", flat=True)
                       for r in undo)
    if used:
        raise RuntimeError("점심당번 배정·기록이 있어 되돌릴 수 없습니다. 업그레이드 전 백업으로 복원하세요"
                           '(docs/OPERATIONS.md "업그레이드·롤백").')
    BoardShift.objects.filter(key="lunch").delete()
    Department.objects.update(lunch_start=None, lunch_end=None)


class Migration(migrations.Migration):

    dependencies = [
        ('duty', '0021_lunch'),
    ]

    operations = [
        migrations.RunPython(fill, reverse_if_unused),
    ]
```

- [ ] **Step 8: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_migration_lunch.py tests/test_migration_reasons.py tests/test_migration_holidays.py tests/test_migration_boards.py`
Expected: 모두 통과(다른 마이그레이션 테스트가 0022 아래로 내려갈 때 `reverse_if_unused` 가 점심당번 배정이 없는 테스트 DB 에서 정의만 지우고 내려간다). 전체 → 1050 passed.

- [ ] **Step 9: 생성 테스트를 붙인다**

`tests/test_lunch.py` 끝에:
```python
# ── 생성: 가장 이른 근무조의 근무로 친 출근 전원 ──

@pytest.fixture
def gen(lunch, make_member, it_board):
    """관제를 만들 수 있는 이틀짜리 마감 회차(새벽 출근은 각 테스트가 넣는다)."""
    p = Period.objects.create(board=it_board, name="p", start_date=MON, end_date=TUE, status=S.CLOSED)
    normal = [make_member(f"N{i}", dept="MEMS") for i in range(5)]
    normal += [make_member(f"직원{x}", dept=x, type="직원") for x in ("MD", "UI")]
    dinner = [make_member(f"D{i}", dept="TMCH") for i in range(5)]
    for d in (MON, TUE):
        Commute.objects.bulk_create([Commute(period=p, date=d, member=x, shift="normal") for x in normal]
                                    + [Commute(period=p, date=d, member=x, shift="dinner") for x in dinner])
    return p


def _dawn(p, d, make_member, *names, reason=""):
    for n in names:
        Commute.objects.create(period=p, date=d, member=make_member(n), shift="dawn", reason=reason)


def test_generation_fills_lunch_with_earliest_shift(gen, make_member):
    _dawn(gen, MON, make_member, "가", "나")
    _dawn(gen, MON, make_member, "다", reason="휴가")  # 근무로 치지 않는다
    out = run_generation(gen, seed=3)
    lunch = DutyAssignment.objects.filter(period=gen, cell="lunch")
    assert sorted(lunch.values_list("date", "member__name")) == [(MON, "가"), (MON, "나")]
    assert DutyAssignment.objects.filter(period=gen, cell__startswith="slot").count() == 20
    assert out.warnings == ["점심당번을 채우지 못한 날(새벽 출근 없음): 11/17"]  # 아무도 없으면 비우고 경고


def test_lunch_does_not_change_slot_result(gen, make_member, lunch):
    _dawn(gen, MON, make_member, "가")
    run_generation(gen, seed=7)
    with_lunch = sorted(DutyAssignment.objects.filter(period=gen, cell__startswith="slot")
                        .values_list("date", "cell", "member__name"))
    lunch.delete()
    out = run_generation(gen, seed=7)
    assert sorted(DutyAssignment.objects.filter(period=gen).values_list("date", "cell", "member__name")) == with_lunch
    assert out.warnings == []  # 점심당번 정의가 없으면 채우지도 경고하지도 않는다


def test_generation_skips_closed_days(gen, make_member):
    Holiday.objects.create(date=TUE, name="임시 휴장")  # 새 회차는 skip_holidays 가 참
    _dawn(gen, MON, make_member, "가")
    out = run_generation(gen, seed=3)
    assert list(DutyAssignment.objects.filter(period=gen, cell="lunch").values_list("date", flat=True)) == [MON]
    assert out.warnings == []  # 건너뛰는 날은 빈 날로 경고하지 않는다


def test_generate_page_shows_lunch_warning(gen, admin_client_ok):
    r = admin_client_ok.post(f"/periods/{gen.pk}/action/generate/", follow=True)
    assert "점심당번을 채우지 못한 날(새벽 출근 없음): 11/16, 11/17" in r.content.decode()


def test_counts_leave_lunch_out(gen, make_member, it_board):
    run_generation(gen, seed=3)
    DutyAssignment.objects.create(period=gen, date=MON, cell="lunch", member=make_member("가"))
    counts, _, _ = stats.period_duty_counts(gen)
    assert sum(n for _, n in counts) == 20 and "가" not in dict(counts)
    Period.objects.filter(pk=gen.pk).update(status=S.PUBLISHED, overwrite_from=MON)
    rows, _, _ = stats.member_stats(it_board, None, None)
    assert sum(r.duty for r in rows) == 20
```

- [ ] **Step 10: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_lunch.py`
Expected: 5 failed — 점심당번 행이 없고(`assert [] == …`), `AttributeError: 'GenerationOutput' object has no attribute 'warnings'`, 경고 문구 없음, `period_duty_counts` 합이 21.

- [ ] **Step 11: 점심당번 채우기·생성 경고·관제 횟수 거르기**
```diff
diff --git a/duty/generator.py b/duty/generator.py
--- a/duty/generator.py
+++ b/duty/generator.py
@@ -7,7 +7,7 @@ Phase 2 Swap:   최다 배정자의 slot을 최소 배정자(그 slot 자격 있
 """
 
 import random
-from dataclasses import dataclass
+from dataclasses import dataclass, field
 from datetime import date
 
 from .shifts import MAX_SWAP_ITERATIONS, TARGET_SPREAD
@@ -34,6 +34,7 @@ class GenerationOutput:
     counts: dict[str, int]
     spread: int
     reached: bool
+    warnings: list[str] = field(default_factory=list)  # 생성은 했지만 알려야 할 것(점심당번을 못 채운 날 등)
 
 
 def _allowed(members_by_type: dict[str, set[str]], types: tuple[str, ...]) -> set[str]:
diff --git a/duty/services/generate.py b/duty/services/generate.py
--- a/duty/services/generate.py
+++ b/duty/services/generate.py
@@ -8,7 +8,7 @@ from .. import perms
 from ..errors import DutyError
 from ..generator import GenerationOutput, generate_control_duty
 from ..models import Commute, DutyAssignment, Period, User
-from ..shifts import slot_defs
+from ..shifts import LUNCH, by_key, shift_defs, slot_defs
 from . import boards, holidays
 from .periods import missing_dates, record
 
@@ -30,7 +30,8 @@ def run_generation(period: Period, seed: int | None = None, by=None) -> Generati
 
     skip = boards.skip_dates(period)  # 근무 없음 날·휴장일(skip_holidays)은 당번을 만들지 않는다. 남은 출근 행은 그대로 둔다
     dates = [d for d in period.dates() if d not in skip]
-    slots = slot_defs(boards.active_defs(period.board))  # 인덱스 i ↔ 칸 키 slots[i].key. 꺼진 관제는 생성하지 않는다
+    active = boards.active_defs(period.board)
+    slots = slot_defs(active)  # 인덱스 i ↔ 칸 키 slots[i].key. 꺼진 관제는 생성하지 않는다
     if slots:
         commutes: dict = defaultdict(lambda: defaultdict(set))
         rows = Commute.objects.filter(period=period, reason="").exclude(date__in=skip)  # 사유가 있으면 후보가 아니다
@@ -53,8 +54,25 @@ def run_generation(period: Period, seed: int | None = None, by=None) -> Generati
         for d, picked in out.assignments.items()
         for i, code in enumerate(picked)
     )
+    if LUNCH in by_key(active) and shift_defs(active):
+        out.warnings += _fill_lunch(period, dates, skip, shift_defs(active)[0])
     old = period.status
     period.status, period.seed, period.generated_at = S.GENERATED, seed, timezone.now()
     period.save()
     record(period, old, by, "재생성" if old == S.GENERATED else "")
     return out
+
+
+def _fill_lunch(period: Period, dates: list, skip: set, early) -> list[str]:
+    """점심당번 = 날짜마다 가장 이른 근무조(early)에 근무로 친(사유 없는) 출근을 한 사람 전원(설계 6.3). 무작위 없음.
+    아무도 없는 날은 비우고 경고 한 줄."""
+    by_day: dict = defaultdict(list)
+    rows = Commute.objects.filter(period=period, shift=early.key, reason="").exclude(date__in=skip)
+    for d, member_id in rows.order_by("date", "member__username").values_list("date", "member_id"):
+        by_day[d].append(member_id)
+    DutyAssignment.objects.bulk_create(
+        DutyAssignment(period=period, date=d, cell=LUNCH, member_id=m) for d in dates for m in by_day[d])
+    empty = [d for d in dates if not by_day[d]]
+    if not empty:
+        return []
+    return [f"점심당번을 채우지 못한 날({early.name} 출근 없음): {', '.join(f'{d.month}/{d.day}' for d in empty)}"]
diff --git a/duty/services/stats.py b/duty/services/stats.py
--- a/duty/services/stats.py
+++ b/duty/services/stats.py
@@ -77,7 +77,8 @@ def period_duty_counts(period: Period) -> tuple[list[tuple[str, int]], int, bool
     # 회차의 출근표가 곧 그 근무표 사람(퇴사자도 출근이 있으면 0회로 남는다). 사유가 있는 출근은 생성 후보가 아니다
     pool = Commute.objects.filter(q, period=period, reason="")
     n: dict[str, int] = dict.fromkeys(pool.values_list("member__name", flat=True), 0)
-    for name in DutyAssignment.objects.filter(period=period).values_list("member__name", flat=True):
+    # 장중관제 칸만 센다(점심당번은 횟수에 넣지 않는다, 설계 8.3)
+    for name in DutyAssignment.objects.filter(period=period, cell__startswith="slot").values_list("member__name", flat=True):
         n[name] = n.get(name, 0) + 1
     counts = sorted(n.items(), key=lambda x: (x[1], x[0]))
     spread = counts[-1][1] - counts[0][1] if counts else 0
diff --git a/duty/views/manage.py b/duty/views/manage.py
--- a/duty/views/manage.py
+++ b/duty/views/manage.py
@@ -111,13 +111,15 @@ def period_action(request, pid, action):
     if action not in actions:
         raise Http404
     try:
-        actions[action](period, by=request.user)
+        result = actions[action](period, by=request.user)
     except GenerationError as e:
         return _render_detail(request, period, e.failures)
     except DutyError as e:
         messages.error(request, str(e))
     else:
         messages.success(request, "완료했습니다.")
+        for w in getattr(result, "warnings", ()):  # 생성: 점심당번을 못 채운 날
+            messages.warning(request, w)
     return redirect("period_detail", pid)
```

- [ ] **Step 12: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_lunch.py tests/test_generate.py tests/test_boards_generate.py tests/test_stats.py tests/test_skip_days.py`
Expected: 모두 통과(점심당번 정의가 없는 기존 생성 결과·같은 씨앗 결과 그대로). 전체 → 1055 passed.

- [ ] **Step 13: 근무 변경 테스트를 붙인다**

`tests/test_lunch.py` 끝에(`test_lunch_needs_definition`·`test_carry_lunch_skips_when_incoming_has_it`·`test_set_reason_warns_lunch` 는 지금도 통과한다 — 앞 작업이 만든 검사·경고를 점심당번에 대해 고정한다):
```python
# ── 근무 변경: 넣기·빼기·교체, 묶음이 달라 관제와 안 섞임, 같이 넘기기 ──

@pytest.fixture
def pub(lunch, make_member, fixed_today, it_board):
    fixed_today(T)
    p = Period.objects.create(board=it_board, name="p", start_date=T, end_date=T, status=S.PUBLISHED,
                              overwrite_from=T, published_at=NOW - timedelta(days=1))
    m = {n: make_member(n, user=True) for n in ["가", "나", "다", "라"]}
    for n, shift in (("가", "dawn"), ("나", "normal"), ("다", "dinner")):
        Commute.objects.create(period=p, date=T, member=m[n], shift=shift)
    DutyAssignment.objects.create(period=p, date=T, cell="slot0", member=m["나"])
    DutyAssignment.objects.create(period=p, date=T, cell="lunch", member=m["가"])
    return p, m


def _lunch_names(p):
    return sorted(DutyAssignment.objects.filter(period=p, cell="lunch").values_list("member__name", flat=True))


def test_lunch_add_remove_replace(pub, it_board):
    p, m = pub
    changes.change_cell(m["라"], it_board, T, "lunch", None, m["라"])  # 넣기만
    assert _lunch_names(p) == ["가", "라"]
    changes.change_cell(m["라"], it_board, T, "lunch", m["가"], m["다"])  # 교체
    changes.change_cell(m["라"], it_board, T, "lunch", m["라"], None)  # 빼기만
    assert _lunch_names(p) == ["다"]
    assert list(ChangeLog.objects.values_list("cell", "before__name", "after__name")) == [
        ("lunch", None, "라"), ("lunch", "가", "다"), ("lunch", "라", None)]
    with pytest.raises(DutyError, match="가은\\(는\\) 이 칸에 없습니다"):
        changes.change_cell(m["라"], it_board, T, "lunch", m["가"], m["나"])
    with pytest.raises(DutyError, match="다은\\(는\\) 이미 이 칸에 있습니다"):
        changes.exchange(m["라"], it_board, T, "lunch", None, m["다"])


def test_lunch_and_slots_do_not_mix(pub, it_board):
    p, m = pub
    assert changes.exchange(m["라"], it_board, T, "lunch", m["가"], m["나"]) == []  # 나의 관제 칸과 맞바꾸지 않는다
    assert _lunch_names(p) == ["나"] and DutyAssignment.objects.get(cell="slot0").member == m["나"]
    # 관제 칸 To 가 점심당번이어도 "다른 관제 칸" 경고·맞교환 개수 검사에 들지 않는다
    warnings = changes.exchange(m["라"], it_board, T, "slot0", m["나"], m["다"])
    assert not any("다른 관제 칸" in w for w in warnings)
    assert DutyAssignment.objects.get(cell="slot0").member == m["다"] and _lunch_names(p) == ["나"]
    with pytest.raises(DutyError, match="출근조끼리 또는 관제 칸끼리만"):
        changes.swap(m["라"], it_board, T, "lunch", m["나"], "normal", m["다"])


def test_lunch_needs_definition(pub, it_board, lunch):
    _, m = pub
    lunch.delete()
    with pytest.raises(DutyError, match="알 수 없는 칸"):
        changes.change_cell(m["라"], it_board, T, "lunch", m["가"], m["라"])


def test_carry_lunch_on_replace(pub, it_board):
    p, m = pub
    changes.change_cell(m["라"], it_board, T, "dawn", m["가"], m["라"])
    assert _lunch_names(p) == ["라"]
    assert list(ChangeLog.objects.values_list("cell", "before__name", "after__name")) == [
        ("dawn", "가", "라"), ("lunch", "가", "라")]  # 근무조 기록 뒤에
    changes.change_cell(m["다"], it_board, T, "dawn", m["라"], m["가"], carry_lunch=False)
    assert _lunch_names(p) == ["라"] and ChangeLog.objects.count() == 3
    changes.change_cell(m["다"], it_board, T, "dawn", m["가"], None)  # 빼기만은 넘길 사람이 없다
    assert _lunch_names(p) == ["라"]


def test_carry_lunch_skips_when_incoming_has_it(pub, it_board):
    p, m = pub
    DutyAssignment.objects.create(period=p, date=T, cell="lunch", member=m["라"])
    changes.change_cell(m["다"], it_board, T, "dawn", m["가"], m["라"])
    assert _lunch_names(p) == ["가", "라"] and ChangeLog.objects.count() == 1


def test_carry_lunch_on_swap_keeps_notice_pairing(pub, it_board, monkeypatch):
    p, m = pub
    conf = alarm_settings.current()
    conf.telegram_bot_token = "1234567890:" + "FAKE" + "x" * 31
    alarm_settings.save(conf)
    TelegramAlarmProfile.objects.create(user=m["가"], chat_id="11", verified_at=NOW)
    TelegramAlarmProfile.objects.create(user=m["나"], chat_id="22", verified_at=NOW)
    sent = []
    monkeypatch.setattr("duty.alarms.senders.telegram_send", lambda cfg, chat, text: sent.append((chat, text)) or {})
    changes.exchange(m["다"], it_board, T, "dawn", m["가"], m["나"])  # 나는 정상 → 맞교환
    assert list(ChangeLog.objects.values_list("cell", "before__name", "after__name")) == [
        ("dawn", "가", "나"), ("normal", "나", "가"), ("lunch", "가", "나")]
    assert _lunch_names(p) == ["나"]
    change_notice.tick(NOW)
    texts = sorted(t.split("\n")[0] + "|" + chat for chat, t in sent)
    assert texts == ["[근무 변경] 11/10(화) 맞교환|11", "[근무 변경] 11/10(화) 맞교환|22",
                     "[근무 변경] 11/10(화) 점심당번|11", "[근무 변경] 11/10(화) 점심당번|22"]


def test_carry_lunch_on_swap_from_other_side(pub, it_board):
    p, m = pub
    changes.exchange(m["다"], it_board, T, "normal", m["나"], m["가"])  # To(가)가 새벽·점심당번 → 맞교환
    assert list(ChangeLog.objects.values_list("cell", "before__name", "after__name")) == [
        ("normal", "나", "가"), ("dawn", "가", "나"), ("lunch", "가", "나")]
    assert _lunch_names(p) == ["나"]  # 새벽을 떠난 가에게 남지 않는다


def test_set_reason_warns_lunch(pub, it_board):
    _, m = pub
    assert changes.set_reason(m["다"], it_board, T, m["가"], "휴가") == [
        "가은(는) 그날 점심당번 칸에 남아 있습니다. 다른 사람으로 바꾸세요."]  # 자동으로 빼지 않는다
```

- [ ] **Step 14: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_lunch.py`
Expected: 5 failed — `IntegrityError`(lunch 를 Commute 로 넣으려 함, `commute_shift_valid`), `DutyError: … 그날 이미 다른 출근조에 있습니다`(lunch 를 근무조로 다룸), 같이 넘기기 없음(`['가'] == ['라']`), 기록 순서, 반대 방향 맞교환에 lunch 기록 없음.

- [ ] **Step 15: 점심당번 넣기·빼기·교체와 같이 넘기기**
```diff
diff --git a/duty/services/changes.py b/duty/services/changes.py
--- a/duty/services/changes.py
+++ b/duty/services/changes.py
@@ -5,7 +5,7 @@ from django.db import transaction
 from .. import perms
 from ..errors import DutyError
 from ..models import ChangeLog, Commute, DutyAssignment, Period, User
-from ..shifts import REASONS, SLOT_GROUP_NAME, Def, by_key, cell_label, is_slot_cell
+from ..shifts import LUNCH, REASONS, SHIFT, SLOT_GROUP_NAME, Def, by_key, cell_label, is_slot_cell, kind
 from . import boards, memos
 
 
@@ -63,8 +63,21 @@ def _check_candidate(board, m: User | None) -> None:
         raise DutyError(f"{m.name}은(는) 근무표 대상이 아닙니다.")
 
 
+def _carry_lunch(user, period: Period, d: date, before: User, after: User) -> None:
+    """점심당번도 같이 넘기기(설계 6.4): 떠나는 사람이 그날 점심당번이고 들어오는 사람은 아니면 넘긴다.
+    기록은 근무조 기록 **뒤에** 남긴다(맞교환 기록 둘 사이에 끼면 변경 알림의 짝짓기가 깨진다)."""
+    rows = DutyAssignment.objects.filter(period=period, date=d, cell=LUNCH)
+    row = rows.filter(member=before).first()
+    if row is None or rows.filter(member=after).exists():
+        return
+    row.member = after
+    row.save()
+    ChangeLog.objects.create(by=user, period=period, date=d, cell=LUNCH, before=before, after=after)
+
+
 @transaction.atomic
-def change_cell(user, board, d: date, cell: str, before: User | None, after: User | None) -> list[str]:
+def change_cell(user, board, d: date, cell: str, before: User | None, after: User | None,
+                carry_lunch: bool = True) -> list[str]:
     perms.assert_can_edit(user, board, d)
     period = _owner(board, d)
     defs = boards.defs(board)
@@ -86,6 +99,17 @@ def change_cell(user, board, d: date, cell: str, before: User | None, after: Use
         if others:
             labels = ", ".join(cell_label(defs, o.cell) for o in others)
             warnings.append(f"{after.name}은(는) 그날 다른 관제 칸({labels})도 맡고 있습니다.")
+    elif cell == LUNCH:  # 혼자인 당번 칸: 넣기·빼기·교체, 인원 제한 없음
+        rows = DutyAssignment.objects.filter(period=period, date=d, cell=cell)
+        row = rows.filter(member=before).first() if before is not None else None
+        if before is not None and row is None:
+            raise DutyError(f"{before.name}은(는) 이 칸에 없습니다.")
+        if after is not None and rows.filter(member=after).exists():
+            raise DutyError(f"{after.name}은(는) 이미 이 칸에 있습니다.")
+        if row is not None:
+            row.delete()
+        if after is not None:
+            DutyAssignment.objects.create(period=period, date=d, cell=cell, member=after)
     else:
         row = None
         if before is not None:
@@ -101,6 +125,8 @@ def change_cell(user, board, d: date, cell: str, before: User | None, after: Use
         warnings = _duty_warnings(defs, period, d, [before, after])
     ChangeLog.objects.create(by=user, period=period, date=d, cell=cell, before=before, after=after,
                              reason_before=getattr(row, "reason", ""))  # 빠진 사람의 사유는 기록에 남긴다(관제 행에는 없다)
+    if carry_lunch and kind(cell) == SHIFT and before is not None and after is not None:
+        _carry_lunch(user, period, d, before, after)
     return warnings
 
 
@@ -131,12 +157,14 @@ def set_reason(user, board, d: date, member: User, reason: str) -> list[str]:
 
 
 @transaction.atomic
-def exchange(user, board, d: date, cell: str, before: User | None, after: User | None) -> list[str]:
+def exchange(user, board, d: date, cell: str, before: User | None, after: User | None,
+             carry_lunch: bool = True) -> list[str]:
     """근무 변경 창의 저장. 둘 다 있으면 기본은 맞교환: To 가 그날 같은 묶음 다른 칸에 있으면 서로 바꾸고,
-    없으면 From 대신 들어간다. 한쪽만 있으면 넣기·빼기(change_cell)."""
+    없으면 From 대신 들어간다. 한쪽만 있으면 넣기·빼기(change_cell). 점심당번은 묶음이 혼자라 늘 교체.
+    carry_lunch: 근무조 칸에서 From 이 점심당번이면 To 에게 넘긴다."""
     perms.assert_can_edit(user, board, d)
     if before is None or after is None:
-        return change_cell(user, board, d, cell, before, after)
+        return change_cell(user, board, d, cell, before, after, carry_lunch)
     _check_cell(boards.defs(board), cell)
     period = _owner(board, d)
     if is_slot_cell(cell):
@@ -147,17 +175,19 @@ def exchange(user, board, d: date, cell: str, before: User | None, after: User |
         if DutyAssignment.objects.filter(period=period, date=d, cell=cell, member=after).exists():
             raise DutyError(f"{after.name}은(는) 이미 이 칸에 있습니다.")
         other = rows[0].cell if rows else None
+    elif cell == LUNCH:
+        other = None  # 같은 묶음에 다른 칸이 없다(관제와 맞교환하지 않는다)
     else:
         other = Commute.objects.filter(period=period, date=d, member=after).values_list("shift", flat=True).first()
     if other == cell:
         raise DutyError(f"{after.name}은(는) 이미 이 칸에 있습니다.")
     if other:
-        return swap(user, board, d, cell, before, other, after)
-    return change_cell(user, board, d, cell, before, after)
+        return swap(user, board, d, cell, before, other, after, carry_lunch)
+    return change_cell(user, board, d, cell, before, after, carry_lunch)
 
 
 @transaction.atomic
-def swap(user, board, d: date, cell_a: str, a: User, cell_b: str, b: User) -> list[str]:
+def swap(user, board, d: date, cell_a: str, a: User, cell_b: str, b: User, carry_lunch: bool = True) -> list[str]:
     perms.assert_can_edit(user, board, d)
     period = _owner(board, d)
     defs = boards.defs(board)
@@ -166,7 +196,7 @@ def swap(user, board, d: date, cell_a: str, a: User, cell_b: str, b: User) -> li
     _check_candidate(board, b)
     if a == b or cell_a == cell_b:
         raise DutyError("서로 다른 두 칸의 서로 다른 사람을 골라 주세요.")
-    if is_slot_cell(cell_a) != is_slot_cell(cell_b):
+    if kind(cell_a) != kind(cell_b):  # 점심당번끼리는 위의 같은 칸 검사에 걸린다(혼자인 칸)
         raise DutyError("출근조끼리 또는 관제 칸끼리만 맞교환할 수 있습니다.")
     warnings: list[str] = []
     if is_slot_cell(cell_a):
@@ -190,4 +220,7 @@ def swap(user, board, d: date, cell_a: str, a: User, cell_b: str, b: User) -> li
         warnings = _duty_warnings(defs, period, d, [a, b])
     ChangeLog.objects.create(by=user, period=period, date=d, cell=cell_a, before=a, after=b)
     ChangeLog.objects.create(by=user, period=period, date=d, cell=cell_b, before=b, after=a)
+    if carry_lunch and kind(cell_a) == SHIFT:  # 맞교환은 두 사람 다 떠나는 사람: 점심당번인 쪽이 상대에게 넘긴다
+        holder, other = (a, b) if DutyAssignment.objects.filter(period=period, date=d, cell=LUNCH, member=a).exists() else (b, a)
+        _carry_lunch(user, period, d, holder, other)
     return warnings
```

- [ ] **Step 16: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_lunch.py tests/test_changes.py tests/test_change_notice.py tests/test_reasons.py tests/test_board_owner.py`
Expected: 모두 통과. 전체 → 1063 passed.

- [ ] **Step 17: 화면 테스트를 붙인다**

`tests/test_lunch.py` 끝에:
```python
# ── 화면: 근무조 → 점심당번 → 관제, 시각 없이 "점심당번", 근무 변경 창 ──

def test_roster_and_day_order(pub, client):
    _, m = pub
    client.force_login(m["나"])
    for url in ["/?date=2026-11-10", "/?view=month&date=2026-11-10"]:
        body = client.get(url).content.decode()
        assert body.index("<small>야간</small>") < body.index("<small>점심당번</small>") < body.index("<small>관제</small>")
        assert 'href="/day/2026-11-10/#lunch"' in body  # 칸을 눌러 바꾼다
    body = client.get("/day/2026-11-10/").content.decode()
    assert body.index("<strong>야간</strong>") < body.index("<strong>점심당번</strong>") < body.index("<strong>08:30~09:30</strong>")
    assert "11:30~12:30</strong>" not in body.split("<strong>점심당번</strong>")[1][:50]  # 시각 없이


def test_schedule_filter_and_me(pub, client):
    assert list(prefs.choices(IT_DEFS2).items())[-2:] == [("slots", "장중관제"), ("lunch", "점심당번")]
    assert "lunch" not in prefs.choices(IT_DEFS)
    _, m = pub
    client.force_login(m["가"])
    body = client.get("/?date=2026-11-10&f=1&shift=lunch").content.decode()
    assert "<small>점심당번</small>" in body and "<small>새벽</small>" not in body and "<small>관제</small>" not in body
    me = client.get("/me/").content.decode()
    assert 'value="lunch"' in me and "점심당번" in me


def test_cell_form_for_lunch_and_carry(pub, client, lunch):
    _, m = pub
    client.force_login(m["나"])
    body = client.get("/cell/2026-11-10/lunch/").content.decode()
    assert "From 대신 To 가 점심당번이 됩니다." in body
    assert "(없음 — 새로 넣기만)" in body and "(없음 — 빼기만)" in body
    assert 'name="reason"' not in body and "carry_lunch" not in body
    assert 'name="carry_lunch" value="1" checked' in client.get("/cell/2026-11-10/dawn/").content.decode()
    assert "carry_lunch" not in client.get("/cell/2026-11-10/slot0/").content.decode()
    lunch.delete()
    assert "carry_lunch" not in client.get("/cell/2026-11-10/dawn/").content.decode()  # 정의가 없으면 숨김


def test_cell_post_carry_lunch(pub, client):
    p, m = pub
    client.force_login(m["다"])
    client.post("/cell/2026-11-10/dawn/", {"before": m["가"].username, "after": m["라"].username})  # 체크 해제
    assert _lunch_names(p) == ["가"]
    client.post("/cell/2026-11-10/dawn/", {"before": m["라"].username, "after": m["나"].username, "carry_lunch": "1"})
    assert _lunch_names(p) == ["가"]  # 떠나는 라는 점심당번이 아니다
    client.post("/cell/2026-11-10/lunch/", {"before": m["가"].username, "after": m["라"].username})
    assert _lunch_names(p) == ["라"]
```

- [ ] **Step 18: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_lunch.py`
Expected: 4 failed — 주간 칸에 `<small>점심당번</small>` 없음(`ValueError: substring not found`), 스케줄 선택지에 lunch 없음, 근무 변경 창 안내·`carry_lunch` 없음, POST 의 같이 넘기기가 체크와 상관없이 켜짐(`['라'] == ['가']`).

- [ ] **Step 19: 날짜 칸·스케줄 선택지·근무 변경 창**
```diff
diff --git a/duty/services/prefs.py b/duty/services/prefs.py
--- a/duty/services/prefs.py
+++ b/duty/services/prefs.py
@@ -1,15 +1,17 @@
 from ..models import Department, RosterPref
-from ..shifts import DEVELOPER, SLOT_GROUP, SLOT_GROUP_NAME, STAFF, shift_defs, slot_defs
+from ..shifts import DEVELOPER, SLOT_GROUP, SLOT_GROUP_NAME, STAFF, lunch_defs, shift_defs, slot_defs
 from . import boards
 
 _KEYS = ("f", "dept", "type", "shift", "hist")
 
 
 def choices(defs) -> dict[str, str]:
-    """스케줄 선택지 {키: 이름}. 근무조(시작 시각 순) → 장중관제 묶음(관제 칸이 있을 때). 화면 순서 = 키 순서."""
+    """스케줄 선택지 {키: 이름}. 근무조(시작 시각 순) → 장중관제 묶음(관제 칸이 있을 때) → 점심당번(있을 때).
+    화면 순서 = 키 순서."""
     out = {x.key: x.name for x in shift_defs(defs)}
     if slot_defs(defs):
         out[SLOT_GROUP] = SLOT_GROUP_NAME
+    out.update({x.key: x.name for x in lunch_defs(defs)})
     return out
 
 
diff --git a/duty/templates/duty/_cell_form.html b/duty/templates/duty/_cell_form.html
--- a/duty/templates/duty/_cell_form.html
+++ b/duty/templates/duty/_cell_form.html
@@ -1,7 +1,7 @@
 <form method="post" action="{% url 'cell' d cell %}" onsubmit="return cellConfirm(this)">{% csrf_token %}
   <input type="hidden" name="next" value="{{ next }}">
   {% if not inline %}<p><strong>{{ d|date:"Y-m-d" }} {% if slot %}장중관제 {% endif %}{{ label }}</strong></p>{% endif %}
-  <p><small>From 과 To 의 근무를 서로 맞바꿉니다. To 가 그날 {% if slot %}장중관제가{% else %}근무가{% endif %} 없으면 From 대신 들어갑니다.</small></p>
+  <p><small>{% if lunch %}From 대신 To 가 점심당번이 됩니다.{% else %}From 과 To 의 근무를 서로 맞바꿉니다. To 가 그날 {% if slot %}장중관제가{% else %}근무가{% endif %} 없으면 From 대신 들어갑니다.{% endif %}</small></p>
   <label>From
     <select name="before">
       {% for m in current_members %}<option value="{{ m.username }}">{{ m.name }}</option>
@@ -15,9 +15,10 @@
       {% endfor %}{% if not slot %}<option value="-">(없음 — 빼기만)</option>{% endif %}
     </select>
   </label>
+  {% if carry %}<label><input type="checkbox" name="carry_lunch" value="1" checked> 점심당번도 같이 넘기기</label>{% endif %}
   <button>저장</button>
 </form>
-{% if not slot and current_members %}
+{% if not slot and not lunch and current_members %}
 <hr>
 <form method="post" action="{% url 'cell' d cell %}">{% csrf_token %}
   <input type="hidden" name="next" value="{{ next }}">
diff --git a/duty/templates/duty/day.html b/duty/templates/duty/day.html
--- a/duty/templates/duty/day.html
+++ b/duty/templates/duty/day.html
@@ -19,7 +19,7 @@
   <p>{% with line=s.items %}{% include "duty/_labels.html" %}{% endwith %}{% if not s.items %}-{% endif %}{% if s.removed_items %} {% with line=s.removed_items %}{% include "duty/_labels.html" %}{% endwith %}{% endif %}</p>
   {% if editable %}
   <details><summary role="button" class="outline secondary">바꾸기</summary>
-    {% include "duty/_cell_form.html" with cell=s.cell label=s.label slot=s.slot current_members=s.current_members reason_choices=s.reason_choices to_options=s.to_options next=s.next inline=True %}
+    {% include "duty/_cell_form.html" with cell=s.cell label=s.label slot=s.slot lunch=s.lunch carry=s.carry current_members=s.current_members reason_choices=s.reason_choices to_options=s.to_options next=s.next inline=True %}
   </details>
   {% endif %}
 </article>
diff --git a/duty/views/roster.py b/duty/views/roster.py
--- a/duty/views/roster.py
+++ b/duty/views/roster.py
@@ -14,8 +14,8 @@ from ..models import Department, Memo, User
 from ..services import boards, changes, holidays, memos, prefs
 from ..services.roster import find_day, member_schedule, published_days
 from ..shifts import (
-    DAY_LABELS, DEVELOPER, REASONS, SLOT_GROUP, STAFF, by_key, cell_label, display_order, is_slot_cell, ordered, shift_defs,
-    slot_defs,
+    DAY_LABELS, DEVELOPER, LUNCH, REASONS, SHIFT, SLOT, SLOT_GROUP, STAFF, by_key, cell_label, display_order, is_slot_cell,
+    kind, lunch_defs, ordered, shift_defs, slot_defs,
 )
 from .common import date_param, safe_next
 
@@ -121,8 +121,9 @@ def _cell_context(defs, day, cell: str, d, depts: list[str] | None = None, types
     current = day.members[cell] if day else []
     qs = User.objects.filter(name__in=current).order_by("name")
     why = _why(day, cell)
-    # To 목록에 그날 같은 종류 근무를 붙인다(맞교환이 기본이라 무엇과 바뀌는지 보이게)
-    kinds = [x.key for x in ordered(defs) if is_slot_cell(x.key) == is_slot_cell(cell)]
+    # To 목록에 그날 같은 종류 근무를 붙인다(맞교환이 기본이라 무엇과 바뀌는지 보이게). 점심당번 칸은 그날 근무조를
+    want = SLOT if is_slot_cell(cell) else SHIFT
+    kinds = [x.key for x in ordered(defs) if kind(x.key) == want]
     where = {}
     for k in kinds:
         for n in (day.members[k] if day else []):
@@ -132,6 +133,9 @@ def _cell_context(defs, day, cell: str, d, depts: list[str] | None = None, types
         m.reason = why.get(m.name, "")  # 사유 선택의 지금 값 표시
     return {
         "d": d, "cell": cell, "label": cell_label(defs, cell), "slot": is_slot_cell(cell),
+        "lunch": cell == LUNCH,  # 사유 선택 없음, 늘 교체
+        # 근무조 칸: "점심당번도 같이 넘기기"(그 근무표에 켜진 점심당번 정의가 있을 때만)
+        "carry": kind(cell) == SHIFT and any(x.key == LUNCH and x.active for x in defs),
         "current_members": current_members, "reason_choices": REASONS,
         "to_options": [{"username": m.username, "name": m.name, "dept": m.department.name,
                         "where": where.get(m.name, "근무 없음")} for m in members if m.name not in current],
@@ -213,7 +217,7 @@ def roster(request):
             "week_memo": notes["week"].get(d),  # 월요일 칸에만 붙는다(week.0 = 그 주 월요일)
             # 배포된 근무표가 있는 날만, 근무 없음 날은 못 바꾼다
             "edit": (edit_past if d < today else edit_now) and not other and d in by_date and not no_work,
-            "commute": [cells[x.key] for x in shift_defs(defs) if x.key in cells],
+            "commute": [cells[x.key] for x in shift_defs(defs) + lunch_defs(defs) if x.key in cells],  # 근무조 → 점심당번
             "duty": [{"time": cells[x.key]["label"][:5], **cells[x.key]} for x in slot_defs(defs) if x.key in cells],
         }
 
@@ -251,7 +255,8 @@ def cell(request, d, cell):
                 # "+"·"-" = 없음(넣기만·빼기만). 기본은 둘 다 고른 맞교환
                 before, after = request.POST.get("before"), request.POST.get("after")
                 result = changes.exchange(request.user, board, d, cell, _member(None if before == "+" else before),
-                                          _member(None if after == "-" else after))
+                                          _member(None if after == "-" else after),
+                                          carry_lunch=request.POST.get("carry_lunch") == "1")
         except DutyError as e:
             messages.error(request, str(e))
         else:
```

- [ ] **Step 20: 통과를 확인하고 브라우저로 본다(CLAUDE.md, PC 1400px·모바일 390px)**

Run: `.venv/bin/pytest -W error -q tests/test_lunch.py tests/test_views_roster.py tests/test_roster_prefs.py tests/test_reasons.py tests/test_views_memos.py`
Expected: 모두 통과. 전체 → 1067 passed.

가짜 데이터로 확인한다(가상 이름만, 운영·개발 DB 를 쓰지 않는다). 아래는 임시 데이터 폴더를 쓰고 끝나면 지운다:
```bash
export DUTY_ENV_FILE= DUTY_DEBUG=1 DUTY_DATA_DIR=$(mktemp -d) DUTY_SECRET_KEY=dev-only   # DUTY_ENV_FILE= : 루트 .env 를 읽지 않는다(Task 8 과 같은 방식)
.venv/bin/python manage.py migrate
.venv/bin/python manage.py shell -c '
from datetime import date
from duty.models import Board, Commute, Department, DutyAssignment, Period, User
from duty.services import changes
b = Board.objects.get(code="it"); d0 = date(2026, 11, 16)
dept = Department.objects.create(code="MEMS", name="매칭엔진실", shifts="dawn,normal,dinner,night", board=b)
mgr = User.objects.create_user("mgr1", password="unused-Pw-123", name="담당자", department=dept, part="", type="개발자", help_dismissed=True)
mgr.groups.add(b.admin_group)
ms = [User.objects.create_user(f"m{i}", password=None, name=f"가상{i}", department=dept, part="", type="개발자") for i in range(5)]
p = Period.objects.create(board=b, name="확인용", start_date=d0, end_date=date(2026, 11, 20), status="published", overwrite_from=d0)
for x in p.dates():
    for m, s in ((ms[0], "dawn"), (ms[4], "dawn"), (ms[1], "normal"), (ms[3], "dinner")):
        Commute.objects.create(period=p, date=x, member=m, shift=s)
    DutyAssignment.objects.create(period=p, date=x, cell="slot0", member=ms[1])
    for m in (ms[0], ms[4]):
        DutyAssignment.objects.create(period=p, date=x, cell="lunch", member=m)
changes.change_cell(mgr, b, date(2026, 11, 17), "lunch", ms[4], ms[2])
'
.venv/bin/python manage.py runserver
```
`mgr1` / `unused-Pw-123` 로 로그인해 1400px·390px 에서 본다: (1) `/?view=week&date=2026-11-16`·`?view=month` — 날짜 칸이 근무조(새벽·정상·석식교대·야간) → **점심당번**(시각 없이, 11/17 은 `가상4>가상2` 변경 표시) → 관제 순서, 스케줄 필터에 "점심당번". (2) `/day/2026-11-16/` — 야간과 관제 사이에 "점심당번". (3) 새벽 칸 팝업 — "점심당번도 같이 넘기기"가 켜진 채로 보이고, 가상0 → 가상3 으로 바꾸면 점심당번도 가상3 으로 넘어간다. 체크를 끄면 그대로. (4) 점심당번 칸 팝업 — 안내 "From 대신 To 가 점심당번이 됩니다.", 넣기만·빼기만이 있고 사유 폼이 없다. (5) 관리 화면 부서에서 점심 시작만 넣고 저장하면 한국어 오류. 확인이 끝나면 서버를 끄고 `rm -rf "$DUTY_DATA_DIR"`.

- [ ] **Step 21: 알림·캘린더 테스트를 붙인다(2단계 문구 고정)**

`tests/test_lunch.py` 끝에:
```python
# ── 알림: 문구 틀 셋, 개인 = 부서 점심 시각, 보고서 줄은 기존 줄 뒤(2단계 문구 고정) ──

SUN18 = datetime(2026, 11, 15, 18)
INFO = {"가": ("MEMS", "개발자"), "나": ("MEMS", "직원"), "다": ("OTH", "개발자")}


def _day(reasons=None, replaced=None, **cells):
    members = {c: [] for c in KEYS}
    members.update({k: list(v) for k, v in cells.items()})
    return Day(MON, 1, {}, members, replaced or {}, reasons or {})


def _rule(**kw):
    base = dict(id=1, member_name="가", kind="personal", timing="days", offset=1, at_minute=18 * 60,
                channels=("telegram",), shifts=("lunch",), depts=(), types=())
    return RuleSpec(**{**base, **kw})


def _plan(rules, days, deliveries=None, now=SUN18, **kw):
    dests = {(r.id, ch): ["d"] for r in rules for ch in r.channels}
    return plan(IT_DEFS2, rules, days, INFO, deliveries or {}, now, destinations=dests, **kw)


def test_personal_lunch_with_department_time():
    [due] = _plan([_rule(lunch=NOON)], [_day(lunch=["가"])])
    assert (due.cell, due.title, due.text, due.content_hash, due.expires_at) == (
        "lunch", "당번 알림", "[당번 알림] 11/16(월) 점심당번 11:30~12:30\n가님, 내일 점심당번입니다.",
        "in:c19e395c7a14672c", datetime(2026, 11, 16, 11, 30))
    [due] = _plan([_rule(lunch=NOON, timing="before_start", offset=120, at_minute=0)], [_day(lunch=["가"])],
                  now=datetime(2026, 11, 16, 9, 30))
    assert due.text.startswith("[당번 알림] 11/16(월) 점심당번 11:30~12:30\n가님, 오늘 점심당번")


def test_personal_lunch_without_department_time():
    [due] = _plan([_rule()], [_day(lunch=["가"])])
    assert (due.text, due.content_hash, due.expires_at) == (
        "[당번 알림] 11/16(월) 점심당번\n가님, 내일 점심당번입니다.", "in:b9b22baa48acedca",
        datetime(2026, 11, 17))  # 날짜 기준: 그날 끝까지
    assert _plan([_rule(timing="before_start", offset=120, at_minute=0)], [_day(lunch=["가"])],
                 now=datetime(2026, 11, 16, 10)) == []  # 시각 기준 규칙에서는 빠진다


def test_personal_lunch_cancel_and_reason():
    sent = {(1, MON, "lunch", "telegram", "d"): "in:c19e395c7a14672c"}
    [due] = _plan([_rule(lunch=NOON)], [_day(lunch=["나"], replaced={("lunch", "나"): "가"})], sent)
    assert due.text == "[당번 변경] 11/16(월) 점심당번 11:30~12:30\n가님의 근무가 취소되었습니다. (후임: 나)"
    away = _day({("dawn", "가"): "휴가"}, dawn=["가"], lunch=["가"])  # 사유가 있는 날의 점심당번은 근무로 치지 않는다
    assert _plan([_rule(lunch=NOON)], [away]) == [] and _plan([_rule(lunch=NOON)], [away], sent) == []


def test_existing_cells_unchanged_with_lunch_defined():
    [due] = _plan([_rule(shifts=("dawn",), lunch=NOON)], [_day(dawn=["가"], lunch=["가"])])
    assert (due.text, due.content_hash) == ("[당번 알림] 11/16(월) 새벽 06:30~15:30\n가님, 내일 새벽 당번입니다.",
                                            "in:b67c7c6d5f7f719a")  # 1단계와 같은 hash


def test_report_appends_lunch_line_without_time():
    r = _rule(kind="report", member_name=None, shifts=(), depts=("MEMS",))
    d = _day(dawn=["가"], normal=["나"], slot0=["나"], night=["다"], lunch=["가", "다"])
    [due] = _plan([r], [d], dept_names={"MEMS": "매칭엔진실"})
    assert (due.text, due.content_hash, due.push_text, due.expires_at) == (
        "[출근표] 11/16(월) — 매칭엔진실\n" + REPORT_BODY + "\n점심당번 가", "report:37fb102d22a93e95",
        "[출근표] 11/16(월) — 매칭엔진실 · 2명", datetime(2026, 11, 16, 17, 0))  # 발송 창·만료는 시각 있는 칸으로
    assert _plan([_rule(kind="report", member_name=None, shifts=("lunch",))], [d]) == []


def test_lunch_message_kinds_and_same_day_notice():
    assert m.change_notice(IT_DEFS2, T, "lunch", "가", "나", "관리자") == (
        "근무 변경", "[근무 변경] 11/10(화) 점심당번\n가 → 나\n바꾼 사람: 관리자")
    assert m.report_line(IT_DEFS2, "lunch", []) == "점심당번 -"
    assert same_day_notice(IT_DEFS2, "personal", "days", 0, 10 * 60, []) == \
        "새벽·정상·석식교대·장중관제 08:30~10:30은 발송 시각이 근무 시작 이후라 제외됩니다."
    assert same_day_notice(IT_DEFS2, "personal", "days", 0, 13 * 60, ["lunch"]) is None
    assert same_day_notice(IT_DEFS2, "report", "days", 0, 17 * 60, []) == "현재 선택으로는 보고서가 발송되지 않습니다."


def test_report_rule_needs_timed_cell(lunch, admin_user, it_board):
    base = dict(enabled=True, kind="report", timing="days", offset=1, at_minute=18 * 60, telegram=True, push=False,
                depts=[], types=[], board_id=it_board.pk)
    with pytest.raises(DutyError, match="점심당번만으로는"):
        alarms.save_rule(admin_user, {**base, "shifts": ["lunch"]})
    assert alarms.save_rule(admin_user, {**base, "shifts": ["lunch", "dawn"]}).shifts == ["dawn", "lunch"]


def test_runner_uses_department_lunch_time(pub, it_board, fixed_today):
    p, m = pub
    fixed_today(T - timedelta(days=1))
    Department.objects.filter(code="MEMS").update(lunch_start=time(11, 40), lunch_end=time(12, 40))
    conf = alarm_settings.current()
    conf.telegram_bot_token = "1234567890:" + "FAKE" + "x" * 31
    alarm_settings.save(conf)
    TelegramAlarmProfile.objects.create(user=m["가"], chat_id="11", verified_at=NOW)
    AlarmRule.objects.create(user=m["가"], kind="personal", timing="days", offset=1, at_minute=18 * 60, telegram=True,
                             shifts=["lunch"])
    [(due, _, _)] = alarm_runner.collect(timezone.make_aware(datetime(2026, 11, 9, 18)))
    assert due.text == "[당번 알림] 11/10(화) 점심당번 11:40~12:40\n가님, 내일 점심당번입니다."


# ── 캘린더: 부서 점심 시각이 있으면 일정 하나 ──

def test_calendar_lunch_event(pub, it_board, settings):
    _, m = pub
    settings.SITE_URL = "https://duty.example"
    assert [e.summary for e in calendar._events(m["가"])] == ["새벽 출근 06:30~15:30"]  # 부서 시각이 없으면 없음
    Department.objects.filter(code="MEMS").update(lunch_start=time(11, 30), lunch_end=time(12, 30))
    m["가"].refresh_from_db()
    events = calendar._events(m["가"])
    assert [e.summary for e in events] == ["새벽 출근 06:30~15:30", "점심당번"]
    assert (events[1].start.hour, events[1].start.minute, events[1].end.hour) == (11, 30, 12)
    assert events[1].uid.startswith("20261110-lunch-")
    changes.set_reason(m["다"], it_board, T, m["가"], "휴가")
    assert calendar._events(m["가"]) == []  # 사유가 있는 날은 빠진다
```

- [ ] **Step 22: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_lunch.py`
Expected: 9 failed — `TypeError: RuleSpec.__init__() got an unexpected keyword argument 'lunch'`, `TypeError: combine() argument 2 must be datetime.time, not None`(점심당번 정의에 시각이 없음), `TypeError: unsupported format string passed to NoneType.__format__`(보고서 줄·`same_day_notice`·캘린더), 저장 금지 없음.

- [ ] **Step 23: 문구 틀 셋·부서 점심 시각·보고서 줄·캘린더 일정**
```diff
diff --git a/duty/alarms/messages.py b/duty/alarms/messages.py
--- a/duty/alarms/messages.py
+++ b/duty/alarms/messages.py
@@ -1,7 +1,10 @@
 """알림 문구. ORM 없음. 칸 이름·시각은 근무표 정의 목록(defs)에서 읽는다."""
 from datetime import date
 
-from ..shifts import DAY_LABELS, SLOT_GROUP_NAME, cell_end, cell_label, cell_start, is_slot_cell
+from ..shifts import DAY_LABELS, SHIFT, SLOT, SLOT_GROUP_NAME, cell_end, cell_label, cell_start, is_slot_cell, kind
+
+# 문구 틀은 키의 성격으로 셋: 근무조("새벽 06:30~15:30", "새벽 당번"), 묶음 당번 칸("08:30~09:30", "장중관제"),
+# 혼자인 당번 칸(점심당번: 정의에 시각이 없다. 개인 알림은 그 사람 부서 점심 시각 lunch=(시작, 끝)이 있으면 붙인다)
 
 CUT = "…(이하 생략, 웹에서 확인)"
 PERSONAL_TITLE, CANCEL_TITLE, REPORT_TITLE = "당번 알림", "당번 변경", "출근표"
@@ -15,15 +18,17 @@ def relative_day(d: date, today: date) -> str:
     return {0: "오늘", 1: "내일"}.get((d - today).days, day_label(d))
 
 
-def cell_span(defs, cell: str) -> str:
-    """'새벽 06:30~15:30' 또는 '10:30~11:30'."""
-    if is_slot_cell(cell):
+def cell_span(defs, cell: str, lunch=None) -> str:
+    """'새벽 06:30~15:30', '10:30~11:30', '점심당번 11:30~12:30'(부서 점심 시각이 없으면 '점심당번')."""
+    if kind(cell) == SLOT:
         return cell_label(defs, cell)
+    if kind(cell) != SHIFT:
+        return cell_label(defs, cell) + (f" {lunch[0]:%H:%M}~{lunch[1]:%H:%M}" if lunch else "")
     return f"{cell_label(defs, cell)} {cell_start(defs, cell):%H:%M}~{cell_end(defs, cell):%H:%M}"
 
 
 def _kind(defs, cell: str) -> str:
-    return SLOT_GROUP_NAME if is_slot_cell(cell) else f"{cell_label(defs, cell)} 당번"
+    return {SHIFT: f"{cell_label(defs, cell)} 당번", SLOT: SLOT_GROUP_NAME}.get(kind(cell), cell_label(defs, cell))
 
 
 def _where(defs, cell: str) -> str:
@@ -42,14 +47,14 @@ def swap_notice(defs, d: date, cell_a: str, a: str, cell_b: str, b: str, by: str
                        f"{b} {_where(defs, cell_b)} → {_where(defs, cell_a)}\n바꾼 사람: {by}")
 
 
-def personal_text(defs, name: str, d: date, cell: str, today: date) -> str:
-    return (f"[{PERSONAL_TITLE}] {day_label(d)} {cell_span(defs, cell)}\n"
+def personal_text(defs, name: str, d: date, cell: str, today: date, lunch=None) -> str:
+    return (f"[{PERSONAL_TITLE}] {day_label(d)} {cell_span(defs, cell, lunch)}\n"
             f"{name}님, {relative_day(d, today)} {_kind(defs, cell)}입니다.")
 
 
-def cancel_text(defs, name: str, d: date, cell: str, successor: str | None = None) -> str:
+def cancel_text(defs, name: str, d: date, cell: str, successor: str | None = None, lunch=None) -> str:
     tail = f" (후임: {successor})" if successor else ""
-    return f"[{CANCEL_TITLE}] {day_label(d)} {cell_span(defs, cell)}\n{name}님의 근무가 취소되었습니다.{tail}"
+    return f"[{CANCEL_TITLE}] {day_label(d)} {cell_span(defs, cell, lunch)}\n{name}님의 근무가 취소되었습니다.{tail}"
 
 
 def report_header(d: date, cond: str, changed: bool) -> str:
@@ -58,7 +63,8 @@ def report_header(d: date, cond: str, changed: bool) -> str:
 
 
 def report_line(defs, cell: str, names: list[str]) -> str:
-    label = cell_label(defs, cell) if is_slot_cell(cell) else f"{cell_label(defs, cell)}({cell_start(defs, cell):%H:%M}~)"
+    # 점심당번 줄은 시각 없이 "점심당번 가, 나"(기존 줄 뒤: 순회 순서 KEYS 의 끝)
+    label = f"{cell_label(defs, cell)}({cell_start(defs, cell):%H:%M}~)" if kind(cell) == SHIFT else cell_label(defs, cell)
     return f"{label} {', '.join(names) if names else '-'}"
 
 
diff --git a/duty/alarms/plan.py b/duty/alarms/plan.py
--- a/duty/alarms/plan.py
+++ b/duty/alarms/plan.py
@@ -1,11 +1,11 @@
 """지금 보내야 할 알림 계산. ORM 없음. 모든 시각은 Asia/Seoul naive. 근무표 하나의 정의(defs)·근무표(days)·규칙만 받는다."""
 import hashlib
 from dataclasses import dataclass
-from datetime import date, datetime
+from datetime import date, datetime, time, timedelta
 
 from ..csv_io import join_reason
 from ..services.roster import Day
-from ..shifts import KEYS, cell_start, cells_of
+from ..shifts import KEYS, LUNCH, cell_start, cells_of
 from . import messages as m
 from .schedule import send_at
 
@@ -22,6 +22,7 @@ class RuleSpec:
     shifts: tuple[str, ...]
     depts: tuple[str, ...]
     types: tuple[str, ...]
+    lunch: tuple[time, time] | None = None  # 개인 규칙 주인 부서의 점심 시각(점심당번 시작·문구). 없으면 None
 
 
 @dataclass(frozen=True)
@@ -64,16 +65,28 @@ def plan(defs, rules, days, info, deliveries, now, destinations=None, dept_names
             cells = cells_of(defs, list(r.shifts))  # 이 근무표에 없는 키는 조용히 무시
             if not cells:
                 continue
-            starts = {c: datetime.combine(day.date, cell_start(defs, c)) for c in cells}
+            # 점심당번은 정의에 시각이 없어 여기서 빠진다(보고서 발송 창·만료는 시각 있는 칸으로만)
+            starts = {c: datetime.combine(day.date, cell_start(defs, c)) for c in cells if c != LUNCH}
             if r.kind == "personal":
                 if r.member_name:
-                    out += _personal(defs, r, day, cells, starts, deliveries, now, destinations, today, closed)
-            elif r.kind == "report":
+                    if LUNCH in cells and (lunch := _lunch_start(r, day.date)):
+                        starts[LUNCH] = lunch
+                    out += _personal(defs, r, day, [c for c in cells if c in starts], starts, deliveries, now,
+                                     destinations, today, closed)
+            elif r.kind == "report" and starts:  # 점심당번만 고른 보고서는 저장 때 막는다(services.alarms.save_rule)
                 out += _report(defs, r, day, cells, starts, info, deliveries, now, dept_names, day.date in synthetic,
                                destinations, closed)
     return out
 
 
+def _lunch_start(r, d: date) -> datetime | None:
+    """개인 알림의 점심당번 시작 = 그 사람 부서 점심 시각. 시각이 없으면 시각 기준 규칙에서 빼고(None),
+    날짜 기준 규칙은 그날 끝(다음 날 00:00)까지 보낸다(만료도 그때)."""
+    if r.lunch:
+        return datetime.combine(d, r.lunch[0])
+    return None if r.timing == "before_start" else datetime.combine(d + timedelta(days=1), time())
+
+
 def _successor(day, cell, name):
     """replaced 간선을 모두 따라가 도달 가능한 사람 중 지금 칸에 있는 후임(최근 간선 우선)."""
     edges = [(old, new) for (c, new), old in day.replaced.items() if c == cell]
@@ -98,19 +111,19 @@ def _targets(r, destinations):
 def _personal(defs, r, day, cells, starts, deliveries, now, destinations, today, closed):
     out = []
     for c in cells:
-        if (c, r.member_name) in day.reasons:  # 사유가 있으면 근무로 치지 않는다. 이미 보낸 알림의 취소도 보내지 않는다
+        if day.excused(c, r.member_name):  # 사유가 있으면 근무로 치지 않는다. 이미 보낸 알림의 취소도 보내지 않는다
             continue
         start = starts[c]
         if not send_at(r.timing, r.offset, r.at_minute, day.date, start, closed) <= now < start:
             continue
         inside = r.member_name in day.members.get(c, [])
         if inside:
-            title, text = m.PERSONAL_TITLE, m.personal_text(defs, r.member_name, day.date, c, today)
+            title, text = m.PERSONAL_TITLE, m.personal_text(defs, r.member_name, day.date, c, today, r.lunch)
             # 오늘/내일 표기는 hash에서 뺀다(자정이 지났다고 다시 보내지 않게)
-            h = _hash("in", m.personal_text(defs, r.member_name, day.date, c, day.date))
+            h = _hash("in", m.personal_text(defs, r.member_name, day.date, c, day.date, r.lunch))
         else:
             title = m.CANCEL_TITLE
-            text = m.cancel_text(defs, r.member_name, day.date, c, _successor(day, c, r.member_name))
+            text = m.cancel_text(defs, r.member_name, day.date, c, _successor(day, c, r.member_name), r.lunch)
             h = _hash("out", text)
         for ch, dest in _targets(r, destinations):
             last = deliveries.get((r.id, day.date, c, ch, dest))
@@ -134,7 +147,7 @@ def _report(defs, r, day, cells, starts, info, deliveries, now, dept_names, synt
     lines, uniq = [], set()
     for c in cells:
         names = [n for n in day.members.get(c, []) if keep(n)]
-        uniq.update(n for n in names if (c, n) not in day.reasons)  # 요약 인원은 근무로 치는 사람만
+        uniq.update(n for n in names if not day.excused(c, n))  # 요약 인원은 근무로 치는 사람만
         lines.append(m.report_line(defs, c, [join_reason(n, day.reasons.get((c, n), "")) for n in names]))  # 가(휴가)
     cond = "·".join([dept_names.get(x, x) for x in r.depts] + list(r.types))
     # 변경 표지만 빼고 보이는 내용 전체(머리·조건·근무표)
diff --git a/duty/alarms/schedule.py b/duty/alarms/schedule.py
--- a/duty/alarms/schedule.py
+++ b/duty/alarms/schedule.py
@@ -1,7 +1,7 @@
 """알림 발송 시각 계산. ORM 없음, Asia/Seoul naive datetime. 칸 시각·이름은 근무표 정의 목록(defs)에서."""
 from datetime import date, datetime, time, timedelta
 
-from ..shifts import SLOT_GROUP_NAME, cell_end, cell_label, cell_start, cells_of, is_slot_cell
+from ..shifts import LUNCH, SLOT_GROUP_NAME, cell_end, cell_label, cell_start, cells_of, is_slot_cell
 
 
 def bizdays_back(d: date, n: int, closed=frozenset()) -> date:
@@ -37,7 +37,7 @@ def same_day_notice(defs, kind: str, timing: str, offset: int, at_minute: int, s
     """당일 발송 규칙에서 발송 시각이 근무 시작 이후라 빠지는 칸 안내. 없으면 None."""
     if timing != "days" or offset != 0:
         return None
-    cells = cells_of(defs, shifts)
+    cells = [c for c in cells_of(defs, shifts) if c != LUNCH]  # 점심당번은 정의에 시각이 없어 안내에서 뺀다
     if not cells:  # 이 근무표에 없는 키만 골랐다(plan 도 조용히 무시한다)
         return None
     starts = {c: cell_start(defs, c).hour * 60 + cell_start(defs, c).minute for c in cells}
diff --git a/duty/services/alarm_runner.py b/duty/services/alarm_runner.py
--- a/duty/services/alarm_runner.py
+++ b/duty/services/alarm_runner.py
@@ -81,6 +81,12 @@ def _valid(rule, today) -> bool:
     return True
 
 
+def _lunch(rule):
+    """개인 규칙 주인 부서의 점심 시각(점심당번 알림 시작·문구). 보고서·시각 없는 부서는 None."""
+    dept = rule.user.department if rule.kind == "personal" and rule.user.department_id else None
+    return (dept.lunch_start, dept.lunch_end) if dept and dept.lunch_start else None
+
+
 def collect(now):
     """보낼 (Due, 기존 기록, 규칙 스냅숏) 목록. 근무표마다 그 근무표의 근무표·규칙으로 따로 계획한다
     (개인 = 주인 부서의 근무표, 보고서 = 규칙의 근무표). 같은 내용의 backoff 중인 것은 뺀다."""
@@ -110,7 +116,7 @@ def collect(now):
         ids = {r.id for r in group}
         specs = [RuleSpec(r.id, r.user.name if r.user.department_id else None, r.kind, r.timing, r.offset,
                           r.at_minute, tuple(ch for ch in ("telegram", "push") if getattr(r, ch)),
-                          tuple(r.shifts), tuple(r.depts), tuple(r.types)) for r in group]
+                          tuple(r.shifts), tuple(r.depts), tuple(r.types), _lunch(r)) for r in group]
         # 주인은 있어도 배정이 하나도 없는 날은 넘기지 않는다(빈 보고서 방지, 설계 6.1).
         # 그날의 옛 발송 기록은 extra_dates 의 빈 날로 계산돼 취소가 나간다(지금과 같다)
         days = [d for d in published_days(board, today, today + HORIZON) if any(d.members.values())]
diff --git a/duty/services/alarms.py b/duty/services/alarms.py
--- a/duty/services/alarms.py
+++ b/duty/services/alarms.py
@@ -14,7 +14,7 @@ from .. import perms
 from ..alarms import senders
 from ..errors import DutyError
 from ..models import AlarmRule, Board, Department, PushAlarmSubscription, TelegramAlarmProfile, User
-from ..shifts import DEVELOPER, STAFF, shift_defs
+from ..shifts import DEVELOPER, LUNCH, STAFF, shift_defs
 from . import alarm_settings, boards, prefs
 
 DEFAULT_RULES = [
@@ -76,6 +76,8 @@ def save_rule(user, data: dict, rule: AlarmRule | None = None) -> AlarmRule:
     board_id = data.get("board_id") if data["kind"] == "report" else None
     shifts, depts, types = normalize(data["kind"], data["shifts"], data["depts"], data["types"],
                                      rule_board(user, data["kind"], board_id))
+    if data["kind"] == "report" and shifts == [LUNCH]:  # 보고서 발송 창은 시각 있는 칸으로 정한다(설계 8.1)
+        raise DutyError("보고서는 시각이 있는 근무를 하나 이상 고르세요. 점심당번만으로는 보낼 수 없습니다.")
     new = {**data, "board_id": board_id, "shifts": shifts, "depts": depts, "types": types}
     rule = rule or AlarmRule(user=user)
     changed = rule.pk is not None and _key(rule) != tuple(new[f] for f in RULE_FIELDS)
diff --git a/duty/services/calendar.py b/duty/services/calendar.py
--- a/duty/services/calendar.py
+++ b/duty/services/calendar.py
@@ -14,7 +14,7 @@ from django.utils import timezone
 from .. import ics, perms
 from ..errors import DutyError
 from ..models import CalendarFeed, ChangeLog, Period
-from ..shifts import SLOT_GROUP, SLOT_GROUP_NAME, is_slot_cell, ordered
+from ..shifts import LUNCH, SLOT_GROUP, SLOT_GROUP_NAME, is_slot_cell, ordered
 from . import boards, roster
 
 logger = logging.getLogger(__name__)
@@ -99,12 +99,19 @@ def _events(member, shifts=()) -> list[ics.Event]:
     for day in days:
         for x in ordered(defs):  # KEYS 순(옛 CELLS 와 같다). 모르는 키는 정의에 없어 조용히 빠진다
             cell = x.key
-            if member.name not in day.members.get(cell, ()) or (cell, member.name) in day.reasons or \
+            if member.name not in day.members.get(cell, ()) or day.excused(cell, member.name) or \
                     (shifts and (SLOT_GROUP if is_slot_cell(cell) else cell) not in shifts):
                 continue
-            summary = f"{SLOT_GROUP_NAME} {x.name}" if is_slot_cell(cell) else f"{x.name} 출근 {x.start:%H:%M}~{x.end:%H:%M}"
+            start, end = x.start, x.end
+            if cell == LUNCH:  # 점심당번 = 부서 점심 시각. 시각이 없는 부서는 일정을 만들지 않는다
+                start, end = member.department.lunch_start, member.department.lunch_end
+                if start is None:
+                    continue
+                summary = x.name
+            else:
+                summary = f"{SLOT_GROUP_NAME} {x.name}" if is_slot_cell(cell) else f"{x.name} 출근 {x.start:%H:%M}~{x.end:%H:%M}"
             events.append(ics.Event(
                 uid=f"{day.date:%Y%m%d}-{cell}-{member.pk}@duty-generator", dtstamp=dtstamp,
-                start=datetime.combine(day.date, x.start, tz), end=datetime.combine(day.date, x.end, tz),
+                start=datetime.combine(day.date, start, tz), end=datetime.combine(day.date, end, tz),
                 summary=summary, url=url))
     return events
diff --git a/duty/services/roster.py b/duty/services/roster.py
--- a/duty/services/roster.py
+++ b/duty/services/roster.py
@@ -8,7 +8,7 @@ from django.db.models import F
 
 from ..csv_io import join_reason
 from ..models import ChangeLog, Commute, DutyAssignment, User
-from ..shifts import SLOT_GROUP_NAME, cell_label, is_slot_cell, ordered
+from ..shifts import LUNCH, SLOT_GROUP_NAME, cell_label, is_slot_cell, ordered
 from . import boards
 
 Log = tuple[str | None, str | None]
@@ -30,6 +30,10 @@ class Day:
     replaced: dict[tuple[str, str], str]
     reasons: dict[tuple[str, str], str] = field(default_factory=dict)  # (칸, 이름) → 사유. 있으면 근무로 치지 않는다
 
+    def excused(self, cell: str, name: str) -> bool:
+        """그 칸의 그 사람을 근무로 치지 않는가: 사유가 붙은 근무조 배정, 그날 사유가 있는 사람의 점심당번."""
+        return (cell, name) in self.reasons or (cell == LUNCH and any(n == name for _, n in self.reasons))
+
 
 def chain(current: list[str], logs: list[Log]) -> tuple[list[str], list[str], dict[str, str]]:
     """ChangeLog 순서대로 표시 라벨을 만든다. A→B 후 B→C 면 'A>B>C', 추가는 '+B', 제거는 removed 목록."""
```

- [ ] **Step 24: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_lunch.py tests/test_alarm_texts_it.py tests/test_alarm_plan.py tests/test_alarm_schedule.py tests/test_run_alarms.py tests/test_alarm_boards.py tests/test_views_alarms.py tests/test_calendar_feed.py tests/test_change_notice.py`
Expected: 모두 통과. `test_alarm_texts_it.py` 는 한 글자도 고치지 않았다(기존 칸 문구·hash 불변).

- [ ] **Step 25: 전체 테스트·마이그레이션 검사**

Run: `.venv/bin/pytest -W error -q`
Expected: 1076 passed(사본 기준 1043 + 새 33), 경고 0개.
Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --check`
Expected: `No changes detected in app 'duty'`

- [ ] **Step 26: 커밋한다**

```bash
git add duty/shifts.py duty/models.py duty/admin.py duty/migrations/0021_lunch.py duty/migrations/0022_lunch_data.py \
  duty/generator.py duty/services/generate.py duty/views/manage.py duty/services/stats.py duty/services/changes.py \
  duty/services/prefs.py duty/views/roster.py duty/templates/duty/_cell_form.html duty/templates/duty/day.html \
  duty/services/roster.py duty/alarms/messages.py duty/alarms/plan.py duty/alarms/schedule.py \
  duty/services/alarm_runner.py duty/services/alarms.py duty/services/calendar.py \
  tests/test_lunch.py tests/test_migration_lunch.py tests/conftest.py tests/it_defs.py \
  tests/test_alarm_models.py tests/test_board_owner.py tests/test_boards.py tests/test_boards_models.py tests/test_shifts.py
git commit -m "feat: 점심당번(가장 이른 근무조를 따라가는 당번 칸, 부서별 점심 시각, IT 새벽 근무자로 채우기, 같이 넘기기, 알림·캘린더)"
```


---

### Task 6: 근무표 고르기·보기 전용·링크 규칙·이력 근무표 열

> 검증: Task 1~5 를 넣은 `feat/boards-phase2` 사본(1075 passed)에 아래 코드를 그대로 넣어 확인했다. 저장소는 고치지 않았다. 결과: `.venv/bin/pytest -W error -q` → **1089 passed**(1075 + 새 14), 경고 0개. `makemigrations duty --check --dry-run` → "No changes detected in app 'duty'". Step 1 의 실패(새 테스트 14개 모두 실패)도 사본에서 재현했다. 가짜 데이터(가상 이름, 임시 DB, 끝나면 지움)로 근무표 둘(IT + "시장운영실")을 만들어 주간(내 근무표·보기 전용)·월간(남의 근무표 관리자)·하루(보기 전용)·이력(근무표 열)·알림 규칙 화면을 headless Chrome 으로 1400·390px 캡처해 확인했다. 클릭(고르기 버튼·htmx 팝업·알림 규칙의 다시 그리기)은 직접 해 보지 않았다(Step 9 에서 사람이 확인).
>
> 이 작업의 범위(설계 4.2·4.9·7·8.1·11 "2단계"): 보일 근무표 결정, 근무표 고르기 버튼(근무표가 둘 이상일 때만, 주간/월간 앞 `.seg`, id 순), 보기 전용(제목 옆 "보기 전용", 칸 링크·"칸을 누르면…" 안내·[바꾸기] 숨김), 내 근무표가 아니면 필터 없이 전체·본인 필터 덮어쓰지 않음, 공통 함수 `boards.board_query` 로 `?board=` 는 내 근무표가 아닐 때만(날짜 이동·필터 폼·htmx·변경 POST·메모), 알림 링크(보고서 규칙·변경 알림의 근무표가 받는 사람의 근무표와 다를 때만 `?board=`, hash 영향 없음), 이력 근무표 열·필터, 알림 규칙 화면의 근무표·종류를 바꾸면 스케줄·부서 선택지를 다시 그림(1단계 남은 한계), 개인 규칙 "전부" 기본값을 주인의 근무표로(1단계 deferred minor).
> 규칙:
> - **내 근무표**(`boards.home(user)`) = 내 부서의 근무표 → 내가 관리하는 첫 근무표 → 첫 근무표(id 순). `?board=` 를 붙일지는 이것 하나로 정한다.
> - **보일 근무표**: 근무표 화면(`/`)은 `?board=` → `RosterPref.board` → 내 근무표. `/day/`·`/cell/`·`/memo/` 는 `?board=` → 내 근무표(기억을 읽지 않는다). `/me/` 는 늘 내 근무표. 없는 코드는 404.
> - 근무표 화면에서 `?board=` 로 고르면 `RosterPref.board` 에 기억한다. 내 근무표를 고르면 기억을 비운다(null). 고르기 버튼은 늘 `?board=<code>` 를 단다(기억을 이기도록).
> - **보기 전용** = 보이는 근무표가 내 부서의 근무표도 아니고 그 근무표 관리자도 아님. 숨김은 원래 권한 판단(`perms.can_edit`·`is_board_admin`)이 하고, 이 작업은 "보기 전용" 글자만 더한다.
> - 내 근무표가 아니면(관리자라도) 부서·유형·스케줄 필터를 그리지 않고 늘 전체를 보이며 저장된 필터를 덮어쓰지 않는다. 주간/월간과 "변경 내역 표시"는 근무표와 상관없이 따르고 저장한다.
> - IT 사람이 IT 를 볼 때 HTML·링크·알림 주소·hash 는 지금과 같다(근무표가 하나면 버튼도 없다). `tests/test_alarm_texts_it.py` 는 그대로 통과한다.
>
> 지시와 다른 점:
> 1. 설계 7 의 사슬 "`?board=` → `RosterPref.board` → …" 가운데 `RosterPref.board` 단계는 **근무표 화면(`/`)에서만** 쓴다. `/day/`·`/cell/`·`/memo/` 까지 기억을 읽으면, `?board=` 없는 IT 알림 링크(`/day/<d>/`, 설계 8.1 "같으면 그대로")나 내 근무표 화면에서 연 변경 창의 POST 가 마지막으로 본 남의 근무표를 가리키게 된다.
> 2. 공통 함수는 `views/roster.py` 가 아니라 `services/boards.py` 의 `board_query(user, board)` 다. 알림(`alarm_runner`·`change_notice`)도 같은 함수를 써야 하기 때문이다. 뷰는 `_board_ctx` 로 `bq`("?board=x" 또는 "")·`bqa`("&board=x" 또는 "")를 템플릿에 넘긴다.
> 3. 알림 규칙 화면의 근무표 선택 칸은 1단계에 이미 있다(근무표가 둘 이상일 때). 이 작업은 그 칸이나 종류를 바꾸면 저장하지 않고 다시 그리는 것(`RuleForm.redraw`, 숨은 `redraw` 버튼)과, 보고서 부서 선택지를 고른 근무표 부서로 좁히는 것만 한다.
> 4. 이력 근무표 열·필터는 **내가 관리하는 근무표가 둘 이상일 때만** 보인다. IT 만 관리하면 이력 화면은 지금 그대로다.
>
> 하지 않는 것(다른 작업): 통계 근무표 고르기, 글씨 크기, 문서(ARCHITECTURE "근무표 고르기·링크 규칙", OPERATIONS, help STEPS). 사본에서 본 기존 문제 하나: 이력 화면 입력칸이 headless 캡처에서 세로로 길게 그려진다(`form.search input` 의 `flex: 1 1 9rem` 이 `form.labeled label` 의 세로 flex 안에서 높이가 됨). 이 작업 전에도 같아서 고치지 않았다.

**Files:**
- Modify: `duty/services/boards.py`(import `perms`, 새 `home`·`link_query`·`board_query`)
- Modify: `duty/services/prefs.py`(`resolve` 의 `mine`, 새 `remember_board`)
- Modify: `duty/views/roster.py`(import, `_board`, 새 `_board_ctx`, `_filter_ctx`, `roster`·`cell`·`day`·`memo`·`me`)
- Modify: `duty/templates/duty/roster.html`, `_filters.html`, `_daycell.html`, `_memo.html`, `day.html`, `_cell_form.html`, `_memo_form.html`
- Modify: `duty/alarms/plan.py`(`RuleSpec.query`, 링크 두 곳), `duty/services/alarm_runner.py`(`collect`), `duty/services/change_notice.py`(`tick`)
- Modify: `duty/views/manage.py`(`change_log`), `duty/templates/duty/changes.html`, `duty/templates/duty/base.html`(이력 select 한 줄)
- Modify: `duty/alarms/forms.py`(`RuleForm.__init__`·새 `redraw`·`initial_from`, `_first_board_id` 삭제), `duty/views/alarms.py`(`_rule_form`), `duty/templates/duty/alarm_rule_form.html`
- Test: `tests/test_board_pick.py`(새 파일, 14개). 기존 테스트는 고치지 않는다.

**Interfaces:**
- Consumes: (1단계) `Board`(code, name, `admin_group`, ordering id), `RosterPref.board`(SET_NULL), `boards.board_of(user)`·`defs`·`active_defs`·`it_board`, `perms.admin_boards`·`is_board_admin`·`can_edit`, `prefs.clean`·`choices`, `views/roster._filters`·`_cell_context`·`_active_members`, `alarm_runner.collect`·`tick`·`telegram_text`, `change_notice.tick`·`_send`, `RuleForm`(`fixed_board`, `_shift_board`), `alarms.rule_board`, 테스트 `tests/test_alarm_boards.py` 의 `ops`·`env` 픽스처와 `person`·`published`·`FORM`·`D`·`SUN18`. (Task 2) `memos.for_range`·`affected`, `views/roster.memo`, `_memo.html`·`_memo_form.html`. (Task 4) `_cell_form.html` 의 사유 폼. (Task 5) `RuleSpec.lunch`, `_cell_form.html` 의 `carry_lunch`, `prefs.choices` 의 `lunch`.
- Produces:
  - `duty.services.boards.home(user) -> Board | None`: 내 부서의 근무표 → 내가 관리하는 첫 근무표 → 첫 근무표.
  - `duty.services.boards.board_query(user, board: Board) -> str`: `""`(board 가 내 근무표) 또는 `"?board=<code>"`.
  - `duty.services.boards.link_query(mine: Board | None, board: Board) -> str`: 내 근무표를 이미 알 때 쓰는 같은 규칙(`board_query` 가 이것을 부른다).
  - `duty.services.prefs.remember_board(user, board: Board, home: Board | None) -> None`: 근무표 화면의 `?board=` 를 `RosterPref.board` 에 기억(내 근무표면 None, 같으면 쓰지 않음). 뷰는 `RosterPref` 를 고치지 않는다.
  - `duty.services.prefs.resolve(user, get, board, with_view: bool = True, mine: bool = True) -> dict`: `mine=False` 면 depts·types·shifts 가 늘 `[]` 이고 저장값을 바꾸지 않는다(view·history 만 저장).
  - `duty.views.roster._board(request, remember: bool = False) -> Board`(이전 `_board(user)`), `_board_ctx(request, board) -> {"bq", "bqa", "board_code", "mine", "view_only"}`, `_filter_ctx(..., history=True, mine=True)` 가 `"filterable"` 을 더한다.
  - 템플릿 컨텍스트: roster `board_links: list[{"name", "href", "current"}]`(근무표가 하나면 `[]`), `view_only`, `bq`, `bqa`, `board_code`, `filterable`. day 도 `bq`·`bqa`·`board_code`·`view_only`·`filterable`. cell(GET)·memo(GET) 은 `bq`. `filter_qs` 끝에 `bqa` 가 붙는다.
  - `duty.alarms.plan.RuleSpec.query: str = ""`(마지막 칸): `Due.url = f"/day/{d}/{query}"`. hash·문구와 무관.
  - `alarm_runner.collect`: 개인 규칙은 `RuleSpec.query=""`(주인 부서의 근무표에서만 돈다), 보고서 규칙은 `boards.link_query(home, board)`(`home` 은 사용자별 dict 캐시로 한 번만 조회). `change_notice.tick`: 받는 사람마다 `boards.board_query(u, r.period.board)`.
  - 이력: `?board=<code>` 필터, 컨텍스트 `board_choices`(내가 관리하는 근무표가 둘 이상일 때만, 아니면 `[]`)·`board_code`, 행 `"board"`(근무표 이름).
  - `RuleForm.redraw(data, user=None) -> RuleForm`(검사·저장 없는 빈 폼, 스케줄·부서는 새 근무표의 전부로 체크). `RuleForm` 부서 선택지 = 근무표가 하나면 그 근무표, 보고서면 고른 근무표의 부서, 개인이면 전체(숨기고 버림). `RuleForm.initial_from(rule)`: "전부" 기본값과 `board` 초깃값 = 보고서는 규칙의 근무표, 개인은 주인 부서의 근무표(없으면 IT).
  - 뷰 `_rule_form`: POST 에 `redraw` 가 있으면 `RuleForm.redraw` 로 다시 그린다(저장 안 함).
  - 마이그레이션 없음. **다음 번호는 그대로 0023.**

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_board_pick.py`(새 파일):
```python
"""근무표 고르기·보기 전용·?board= 링크 규칙·이력 근무표 열·알림 규칙 화면(설계 7·8.1). 이름은 모두 가상."""
from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from duty.alarms.forms import RuleForm
from duty.alarms.plan import RuleSpec, plan
from duty.models import AlarmRule, ChangeLog, Commute, Memo, Period, RosterPref, User
from duty.services import alarm_runner, boards, change_notice
from duty.services.roster import Day
from duty.shifts import KEYS
from tests.it_defs import IT_DEFS
from tests.test_alarm_boards import FORM, D, SUN18, env, ops, person, published  # noqa: F401 (env·ops 는 픽스처)

WEEK = f"/?view=week&date={D.isoformat()}"


def member(username, name, dept):
    return User.objects.create_user(username, password="unused-Pw-123", name=name, department=dept, type="직원")


@pytest.fixture
def two(depts, it_board, ops, fixed_today):
    """IT 근무표(가상다 새벽)와 운영팀 근무표(가상나 오전)가 D 에 배포. 로그인하는 사람은 IT 의 가상가. 오늘 = D 앞 금요일."""
    fixed_today(D - timedelta(days=3))
    board, dept = ops
    ga, da = member("it01", "가상가", depts["MEMS"]), member("it02", "가상다", depts["MEMS"])
    na = member("op01", "가상나", dept)
    published(it_board, (da, "dawn"))
    published(board, (na, "dawn"))
    return board, ga, na


# ── 보일 근무표 ──

def test_home_and_board_query(two, it_board, admin_user):
    board, ga, na = two
    assert boards.home(ga) == it_board and boards.board_query(ga, it_board) == ""
    assert boards.board_query(ga, board) == "?board=ops" and boards.board_query(na, it_board) == "?board=it"
    keeper = User.objects.create_user("opadm", password=None, name="가상관리")  # 부서 없음, 운영팀 관리 그룹
    keeper.groups.add(board.admin_group)
    assert boards.home(keeper) == board  # 내가 관리하는 첫 근무표
    assert boards.home(admin_user) == it_board
    assert boards.home(User.objects.create_user("nobody", password=None, name="가상무")) == it_board  # 첫 근무표


def test_roster_board_order_and_memory(client, two):
    board, ga, _ = two
    client.force_login(ga)
    assert "가상다" in client.get(WEEK).content.decode()
    body = client.get(WEEK + "&board=ops").content.decode()
    assert "가상나" in body and "가상다" not in body
    assert RosterPref.objects.get(user=ga).board == board
    assert "가상나" in client.get(WEEK).content.decode()  # ?board= 가 없으면 기억한 근무표
    assert "가상다" in client.get(WEEK + "&board=it").content.decode()
    assert RosterPref.objects.get(user=ga).board is None  # 내 근무표를 고르면 기억을 비운다
    assert client.get("/?board=nope").status_code == 404


def test_board_buttons_only_with_two_boards(client, depts, request):
    client.force_login(member("it01", "가상가", depts["MEMS"]))
    assert 'aria-label="근무표"' not in client.get("/").content.decode()  # 근무표가 하나면 그리지 않는다
    request.getfixturevalue("ops")
    body = client.get("/").content.decode()
    assert 'aria-label="근무표"' in body
    assert body.index('aria-current="page">IT 당번표</a>') < body.index(">운영팀</a>") < body.index(">주간</a>")  # id 순, 주간/월간 앞
    assert "?board=ops&amp;view=week&amp;date=" in body


# ── 보기 전용·필터 ──

def test_view_only_other_board(client, two):
    _, ga, _ = two
    client.force_login(ga)
    body = client.get(WEEK + "&board=ops").content.decode()
    assert "보기 전용" in body and 'class="cell"' not in body and "칸을 누르면" not in body
    day = client.get(f"/day/{D}/?board=ops").content.decode()
    assert "보기 전용" in day and "가상나" in day and "바꾸기</summary>" not in day
    mine = client.get(WEEK + "&board=it").content.decode()
    assert "보기 전용" not in mine and 'class="cell"' in mine


def test_other_board_admin_gets_board_links(client, two):
    board, ga, _ = two
    ga.groups.add(board.admin_group)  # IT 사람이면서 운영팀 관리자: 편집은 되지만 내 근무표는 아니다
    client.force_login(ga)
    body = client.get(WEEK + "&board=ops").content.decode()
    assert "보기 전용" not in body
    assert f'href="/day/{D}/?board=ops#dawn"' in body  # 칸 링크
    assert f'hx-get="/cell/{D}/dawn/?next=' in body and "&amp;board=ops" in body  # htmx 주소
    assert f'href="/memo/day/{D}/?board=ops"' in body
    assert 'name="board" value="ops"' in body  # 필터 폼
    assert "?board=ops&amp;view=week&amp;date=2026-11-09" in body  # 날짜 이동
    mine = client.get(WEEK + "&board=it").content.decode()
    assert f'href="/day/{D}/#dawn"' in mine and 'name="board"' not in mine  # 내 근무표는 ?board= 없이 그대로


def test_other_board_shows_all_and_keeps_my_filters(client, two):
    board, ga, _ = two
    ga.groups.add(board.admin_group)  # 관리자라도 내 근무표가 아니면 필터 없이
    client.force_login(ga)
    client.get(WEEK + "&f=1&dept=MEMS")
    assert RosterPref.objects.get(user=ga).depts == ["MEMS"]
    body = client.get(WEEK + "&board=ops&f=1&dept=TMCH&hist=0").content.decode()
    assert "가상나" in body and "<legend>부서</legend>" not in body and "<legend>보기</legend>" in body
    p = RosterPref.objects.get(user=ga)
    assert p.depts == ["MEMS"] and p.history is False  # 필터는 그대로, 변경 내역 표시는 따른다
    assert "<legend>부서</legend>" in client.get(WEEK + "&board=it").content.decode()


# ── /day/·/cell/·/memo/ ──

def test_day_cell_memo_use_board_query(client, two):
    board, ga, na = two
    ga.groups.add(board.admin_group)
    nb = member("op02", "가상라", na.department)
    client.force_login(ga)
    client.get(WEEK + "&board=ops")  # 근무표 화면의 기억은 /day/ 가 읽지 않는다(알림 링크는 늘 내 근무표)
    assert "가상다" in client.get(f"/day/{D}/").content.decode()
    body = client.get(f"/day/{D}/?board=ops").content.decode()
    assert f'action="/cell/{D}/dawn/?board=ops"' in body
    assert 'href="/day/2026-11-13/?board=ops&amp;f=1' in body  # 앞 날짜
    assert f'value="/day/{D}/?board=ops"' in body  # 저장 뒤 돌아올 주소
    r = client.post(f"/cell/{D}/dawn/?board=ops", {"before": na.username, "after": nb.username})
    assert r.url == f"/day/{D}/?board=ops"
    assert Commute.objects.get(period__board=board, date=D).member == nb
    assert client.get(f"/memo/day/{D}/").status_code == 404  # IT 관리자는 아니다
    assert f'action="/memo/day/{D}/?board=ops"' in client.get(f"/memo/day/{D}/?board=ops").content.decode()
    r = client.post(f"/memo/day/{D}/?board=ops", {"text": "가상 메모"})
    assert r.url == f"/day/{D}/?board=ops" and Memo.objects.get().board == board


# ── 알림 링크 ──

def test_plan_link_query_keeps_hash():
    day = Day(D, 1, {}, {**{c: [] for c in KEYS}, "dawn": ["가상가"]}, {})
    now = datetime(2026, 11, 15, 18)  # plan 은 naive 시각
    base = RuleSpec(1, None, "report", "days", 1, 18 * 60, ("telegram",), (), (), ())
    dues = [plan(IT_DEFS, [r], [day], {}, {}, now, destinations={(1, "telegram"): ["9"]})[0]
            for r in (base, RuleSpec(**{**base.__dict__, "query": "?board=ops"}))]
    assert [x.url for x in dues] == [f"/day/{D}/", f"/day/{D}/?board=ops"]
    assert dues[0].content_hash == dues[1].content_hash and dues[0].text == dues[1].text


def test_report_link_has_board_only_for_other_board(env, settings, depts, it_board, ops):
    settings.SITE_URL = "https://duty.example"
    board, dept = ops
    it, op = person("가상아이", depts["MEMS"], "111"), person("가상운영", dept, "222")
    AlarmRule.objects.filter(user__in=[it, op]).delete()
    published(it_board, (it, "dawn"))
    published(board, (op, "dawn"))
    for b in (it_board, board):
        AlarmRule.objects.create(user=it, kind="report", board=b, timing="days", offset=1, at_minute=18 * 60,
                                 telegram=True, shifts=[], depts=[], types=[])
    alarm_runner.tick(SUN18)
    assert sorted(t.rsplit("\n", 1)[1] for _, t in env) == [
        "https://duty.example/day/2026-11-16/", "https://duty.example/day/2026-11-16/?board=ops"]


def test_change_notice_link_by_recipient_board(env, settings, depts, ops):
    settings.SITE_URL = "https://duty.example"
    board, dept = ops
    a, b = person("가상운영", dept, "222"), person("가상운영둘", dept, "333")
    p = published(board, (b, "dawn"))
    a.department = depts["MEMS"]  # IT 로 옮겨 간 사람에게는 운영팀 링크에 ?board=ops
    a.save()
    ChangeLog.objects.create(period=p, date=D, cell="dawn", before=a, after=b)
    change_notice.tick(timezone.now())
    assert sorted((c, t.rsplit("\n", 1)[1]) for c, t in env) == [
        ("222", "https://duty.example/day/2026-11-16/?board=ops"), ("333", "https://duty.example/day/2026-11-16/")]


# ── 이력 ──

def test_change_log_board_column_and_filter(admin_client_ok, admin_user, two, it_board):
    board, _, na = two
    da = User.objects.get(name="가상다")
    ChangeLog.objects.create(period=Period.objects.get(board=it_board), date=D, cell="dawn", before=da, after=None)
    ChangeLog.objects.create(period=Period.objects.get(board=board), date=D, cell="dawn", before=na, after=None)
    body = admin_client_ok.get("/changes/").content.decode()
    assert "<th>근무표</th>" not in body and "가상다" in body and "가상나" not in body  # IT 만 관리: 열·필터 없음
    admin_user.groups.add(board.admin_group)
    body = admin_client_ok.get("/changes/").content.decode()
    assert "<th>근무표</th>" in body and '<td class="nw">운영팀</td>' in body and '<option value="ops">운영팀</option>' in body
    body = admin_client_ok.get("/changes/?board=ops").content.decode()
    assert "가상나" in body and "가상다" not in body and '<option value="ops" selected>' in body


# ── 알림 규칙 화면 ──

def test_rule_initial_all_uses_owner_board(two):
    board, _, na = two
    rule = AlarmRule.objects.create(user=na, kind="personal", timing="before_start", offset=120, telegram=True,
                                    shifts=[], depts=[], types=[])
    init = RuleForm.initial_from(rule)
    assert init["board"] == board.pk and init["shifts"] == ["dawn", "normal", "dinner"] and init["depts"] == ["OPS"]
    assert [c for c, _ in RuleForm(initial=init, user=na).fields["shifts"].choices] == init["shifts"]


def test_rule_form_report_depts_follow_board(two):
    board, _, _ = two
    f = RuleForm({**FORM, "kind": "report", "board": str(board.pk)})
    assert [c for c, _ in f.fields["depts"].choices] == ["OPS"]
    assert not RuleForm({**FORM, "kind": "report", "board": str(board.pk), "depts": ["MEMS"]}).is_valid()


def test_rule_page_redraws_without_saving(client, two):
    board, ga, _ = two
    client.force_login(ga)
    r = client.post("/alarms/rules/new/", {**FORM, "kind": "report", "board": str(board.pk), "hours": "3",
                                           "shifts": ["night"], "redraw": "1"})
    assert r.status_code == 200 and not AlarmRule.objects.filter(kind="report").exists()
    init = r.context["form"].initial
    assert init["shifts"] == ["dawn", "normal", "dinner"] and init["depts"] == ["OPS"] and init["hours"] == "3"
    assert 'value="night"' not in r.content.decode()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_pick.py`
Expected: **14 failed**. `test_home_and_board_query` 는 AttributeError(`boards.home` 없음), `test_plan_link_query_keeps_hash` 는 TypeError(`RuleSpec` 에 `query` 없음), `test_rule_page_redraws_without_saving` 은 KeyError(redraw 가 저장 경로로 가서 폼 컨텍스트가 없음), 나머지는 assert 실패(버튼·"보기 전용"·`?board=` 링크·근무표 열이 없고, `/?board=nope` 가 200, 개인 규칙 "전부"가 첫 근무표 기준).

- [ ] **Step 3: 내 근무표와 공통 URL 함수, 필터 저장 규칙**

`duty/services/boards.py`, `duty/services/prefs.py`:
```diff
diff --git a/duty/services/boards.py b/duty/services/boards.py
--- a/duty/services/boards.py
+++ b/duty/services/boards.py
@@ -4,6 +4,7 @@ from datetime import date
 from django.db.models import Exists, F, OuterRef, Subquery
 from django.db.models.functions import Coalesce
 
+from .. import perms
 from ..models import Board, BoardShift, Period, PeriodEvent
 from ..shifts import Def, ordered, weekdays
 from . import holidays, memos
@@ -31,6 +32,19 @@ def board_of(user) -> Board | None:
     return dept.board if dept else None
 
 
+def home(user) -> Board | None:
+    """내 근무표(설계 7): 내 부서의 근무표 → 내가 관리하는 첫 근무표 → 첫 근무표.
+    ?board= 없는 /day/·/cell/·/memo/·/me/ 가 보는 근무표이고, 링크에 ?board= 를 붙일지 정하는 기준이다."""
+    return board_of(user) or perms.admin_boards(user).order_by("id").first() or Board.objects.order_by("id").first()
+
+
+def link_query(mine: Board | None, board: Board) -> str:
+    """board 가 내 근무표(mine)가 아닐 때만 "?board=<code>". 내 근무표를 이미 아는 호출(작업자)이 다시 조회하지 않게 나눴다."""
+    return "" if mine is not None and mine.pk == board.pk else f"?board={board.code}"
+
+
+def board_query(user, board: Board) -> str:
+    """보이는 근무표가 내 근무표가 아닐 때만 "?board=<code>"(날짜 이동·필터 폼·htmx·변경 POST·알림 링크 공통).
+    내 근무표면 "" 라 IT 사람의 링크·알림 주소는 1단계 그대로다."""
+    return link_query(home(user), board)
+
+
 def _ranked(board):
     """그 근무표의 배포 회차를 최근 배포 순으로. 배포 순번 = 배포 PeriodEvent 의 id(시계와 무관).
     배포 이벤트가 없는 옛 회차는 이벤트가 있는 회차보다 오래된 것으로 보고, 그들끼리는 published_at(없으면 가장 오래됨), pk 순."""
diff --git a/duty/services/prefs.py b/duty/services/prefs.py
--- a/duty/services/prefs.py
+++ b/duty/services/prefs.py
@@ -28,19 +28,21 @@ def clean(board, depts, types, shifts) -> tuple[list[str], list[str], list[str]]
     )
 
 
-def resolve(user, get, board, with_view: bool = True) -> dict:
-    """요청에 필터 값이 있으면 그 값을 쓰고 저장, 없으면 저장값을 불러온다. 빈 목록 = 전체."""
+def resolve(user, get, board, with_view: bool = True, mine: bool = True) -> dict:
+    """요청에 필터 값이 있으면 그 값을 쓰고 저장, 없으면 저장값을 불러온다. 빈 목록 = 전체.
+    mine=False(보이는 근무표가 내 근무표가 아님, 설계 7): 부서·유형·스케줄은 늘 전체이고 저장된 필터를 덮어쓰지 않는다.
+    보기(주간·월간)와 변경 내역 표시는 근무표와 상관없이 따르고 저장한다."""
     pref = RosterPref.objects.filter(user=user).first()
-    if not any(k in get for k in _KEYS) and not (with_view and "view" in get):
+    if not any(k in get for k in (_KEYS if mine else ("hist",))) and not (with_view and "view" in get):
         if pref is None:
             return {"depts": [], "types": [], "shifts": [], "view": "week", "history": True}
-        return dict(zip(("depts", "types", "shifts"), clean(board, pref.depts, pref.types, pref.shifts)),
-                    view=pref.view, history=pref.history)
-    d, t, s = clean(board, get.getlist("dept"), get.getlist("type"), get.getlist("shift"))
+        d, t, s = clean(board, pref.depts, pref.types, pref.shifts) if mine else ([], [], [])
+        return {"depts": d, "types": t, "shifts": s, "view": pref.view, "history": pref.history}
+    d, t, s = clean(board, get.getlist("dept"), get.getlist("type"), get.getlist("shift")) if mine else ([], [], [])
     view = get["view"] if with_view and get.get("view") in ("week", "month") else (pref.view if pref else "week")
     # 체크박스는 hidden hist=0 뒤에 오므로 마지막 값을 본다. hist 가 없는 주소(날짜 이동 등)는 저장값 유지
     history = get.getlist("hist")[-1] == "1" if "hist" in get else (pref.history if pref else True)
-    new = {"depts": d, "types": t, "shifts": s, "view": view, "history": history}
+    new = {"view": view, "history": history, **({"depts": d, "types": t, "shifts": s} if mine else {})}
     if pref is None or any(getattr(pref, k) != v for k, v in new.items()):
         RosterPref.objects.update_or_create(user=user, defaults=new)  # 첫 저장 동시 요청도 안전
-    return new
+    return {"depts": d, "types": t, "shifts": s, **new}
+
+
+def remember_board(user, board, home) -> None:
+    """근무표 화면에서 ?board= 로 고른 근무표를 기억한다(설계 7). 내 근무표(home)를 고르면 비운다(None).
+    기억이 이미 같으면 쓰지 않는다(없던 사용자가 내 근무표를 골라도 행을 만들지 않는다)."""
+    keep = None if home is not None and board.pk == home.pk else board
+    pref = RosterPref.objects.filter(user=user).first()
+    if (pref.board_id if pref else None) != (keep.pk if keep else None):
+        RosterPref.objects.update_or_create(user=user, defaults={"board": keep})
```

- [ ] **Step 4: 근무표 화면·하루·변경 창·메모의 보일 근무표와 링크**

`duty/views/roster.py`:
```diff
diff --git a/duty/views/roster.py b/duty/views/roster.py
--- a/duty/views/roster.py
+++ b/duty/views/roster.py
@@ -10,7 +10,7 @@ from django.urls import reverse
 from .. import perms
 from ..csv_io import split_names
 from ..errors import DutyError
-from ..models import Department, Memo, User
+from ..models import Board, Department, Memo, RosterPref, User
 from ..services import boards, changes, holidays, memos, prefs
 from ..services.roster import find_day, member_schedule, published_days
 from ..shifts import (
@@ -61,9 +61,37 @@ def _member(username: str | None) -> User | None:
     return m
 
 
-def _board(user):
-    """이 사용자가 보는 근무표. 1단계: 내 부서의 근무표, 없으면 IT(근무표 고르기는 2단계). 모든 뷰가 이것 하나를 쓴다."""
-    return boards.board_of(user) or boards.it_board()
+def _board(request, remember: bool = False) -> Board:
+    """보일 근무표(설계 7): ?board= → (근무표 화면만) RosterPref.board → 내 근무표(boards.home).
+    remember=True(근무표 화면): ?board= 로 고른 근무표를 기억한다(내 근무표를 고르면 비운다).
+    /day/·/cell/·/memo/ 는 기억을 읽지 않는다: ?board= 없는 주소(알림 링크, 내 근무표 화면의 링크·POST)는 늘 내 근무표다."""
+    user, code = request.user, request.GET.get("board")
+    home = boards.home(user)
+    if code:
+        board = Board.objects.filter(code=code).first()
+        if board is None:
+            raise Http404
+        if remember:
+            prefs.remember_board(user, board, home)  # DB 쓰기는 services(뷰는 읽기만)
+        return board
+    if remember:
+        pref = RosterPref.objects.filter(user=user).select_related("board").first()
+        if pref and pref.board:
+            return pref.board
+    return home
+
+
+def _board_ctx(request, board) -> dict:
+    """근무표 고르기 공통 값. bq = "?board=<code>" 또는 ""(내 근무표), bqa = 같은 값을 "&" 로 이어 붙일 때.
+    mine = 내 근무표(필터를 쓰고 저장), view_only = 내 근무표도 아니고 그 근무표 관리자도 아님(설계 7)."""
+    bq = boards.board_query(request.user, board)
+    return {
+        "bq": bq, "bqa": "&" + bq[1:] if bq else "", "board_code": board.code, "mine": not bq,
+        "view_only": board != boards.board_of(request.user) and not perms.is_board_admin(request.user, board),
+    }
 
 
 def _filters(request, board) -> tuple[list[str], list[str]]:
@@ -93,9 +121,10 @@ def _shown(shifts: list[str]):
     return lambda k: not shifts or (SLOT_GROUP if is_slot_cell(k) else k) in shifts
 
 
-def _filter_ctx(board, defs, depts, types, shifts, history: bool = True) -> dict:
+def _filter_ctx(board, defs, depts, types, shifts, history: bool = True, mine: bool = True) -> dict:
     return {
         "history": history,
+        "filterable": mine,  # 내 근무표가 아니면 부서·유형·스케줄 필터를 그리지 않는다(늘 전체)
         "filter_on": bool(depts or types or shifts),
         "type_choices": [{"code": t, "name": t, "checked": not types or t in types} for t in (STAFF, DEVELOPER)],
         "dept_choices": [
@@ -155,11 +184,12 @@ def roster(request):
     names = split_names(request.GET.get("q", ""))[:3]  # 구버전 ?q=a,b,c
     names = [request.GET.get(f"q{i}", "").strip() or (names[i - 1] if i <= len(names) else "") for i in (1, 2, 3)]
     today = perms.today()
-    board = _board(request.user)
+    board = _board(request, remember=True)
+    bc = _board_ctx(request, board)
     defs = boards.defs(board)
     # 칸 링크 권한: 날짜마다 묻지 않고 지난 날·오늘 이후 두 번만 묻는다
     edit_past, edit_now = (perms.can_edit(request.user, board, x) for x in (today - timedelta(days=1), today))
-    pref = prefs.resolve(request.user, request.GET, board)
+    pref = prefs.resolve(request.user, request.GET, board, mine=bc["mine"])
     view, depts, types, shifts, history = pref["view"], pref["depts"], pref["types"], pref["shifts"], pref["history"]
     show = (lambda x: x) if history else _latest
     anchor = date_param(request, "date") or today
@@ -171,7 +201,7 @@ def roster(request):
         if not LOW <= d <= HIGH:
             return None  # 범위 밖으로 가는 링크는 만들지 않는다
         params = {"view": v, "date": d.isoformat(), **{f"q{i}": n for i, n in enumerate(names, 1) if n}, "dept": depts, "type": types, "shift": shifts}
-        return "?" + urlencode(params, doseq=True)
+        return (bc["bq"] + "&" if bc["bq"] else "?") + urlencode(params, doseq=True)
 
     if view == "week":
         monday = anchor - timedelta(days=anchor.weekday())
@@ -223,13 +253,19 @@ def roster(request):
 
     days = [[day_info(d) for d in w] for w in weeks]
     months = sorted({d.replace(day=1) for w in weeks for d in w if view == "week" or d.month == anchor.month})
+    all_boards = list(Board.objects.order_by("id"))
     ctx = {
         "view": view, "title": title, "names": names, "date": anchor, "today_link": (link(view, today) or f"?view={view}&date={today.isoformat()}") + "#today",
         "prev": link(view, prev_d), "next": link(view, next_d),
         "week_link": link("week", anchor), "month_link": link("month", anchor),
-        "filter_qs": "".join("&" + urlencode({k: v}) for k, vs in (("dept", depts), ("type", types)) for v in vs),
+        "filter_qs": "".join("&" + urlencode({k: v}) for k, vs in (("dept", depts), ("type", types)) for v in vs) + bc["bqa"],
+        # 근무표 고르기: 근무표가 둘 이상일 때만, id 순(설계 4.2). 고르면 기억한다(내 근무표를 고르면 기억을 비운다)
+        "board_links": [{"name": b.name, "current": b == board,
+                         "href": "?" + urlencode({"board": b.code, "view": view, "date": anchor.isoformat()})}
+                        for b in all_boards] if len(all_boards) > 1 else [],
+        **bc,
     }
-    ctx.update(_filter_ctx(board, defs, depts, types, shifts, history), weeks=days,
+    ctx.update(_filter_ctx(board, defs, depts, types, shifts, history, bc["mine"]), weeks=days,
                memo_admin=perms.is_board_admin(request.user, board),
                month_memos=[{"date": m, "memo": notes["month"].get(m)} for m in months])
     return render(request, "duty/roster.html", ctx)
@@ -237,11 +273,12 @@ def roster(request):
 
 @login_required
 def cell(request, d, cell):
-    board = _board(request.user)
+    board = _board(request)
+    bq = boards.board_query(request.user, board)
     defs = boards.defs(board)
     if cell not in by_key(defs):
         raise Http404
-    fallback = reverse("day", args=[d])
+    fallback = reverse("day", args=[d]) + bq
     if request.method == "POST":
         reason_form = bool(request.POST.get("set_reason"))  # 근무조 칸의 사유 선택(같은 창의 두 번째 폼)
         try:
@@ -266,7 +303,7 @@ def cell(request, d, cell):
         return redirect(safe_next(request, fallback))
     depts, types = _filters(request, board)
     ctx = _cell_context(defs, find_day(board, d), cell, d, depts, types, _active_members(board, depts, types))
-    ctx.update(next=safe_next(request, fallback))
+    ctx.update(next=safe_next(request, fallback), bq=bq)
     return render(request, "duty/_cell_form.html", ctx)
 
 
@@ -279,9 +316,10 @@ def _neighbor(d, step: int):
 
 @login_required
 def day(request, d):
-    board = _board(request.user)
+    board = _board(request)
+    bc = _board_ctx(request, board)
     defs = boards.defs(board)
-    pref = prefs.resolve(request.user, request.GET, board, with_view=False)
+    pref = prefs.resolve(request.user, request.GET, board, with_view=False, mine=bc["mine"])
     depts, types, shifts, history = pref["depts"], pref["types"], pref["shifts"], pref["history"]
     show = (lambda x: x) if history else _latest
     found = find_day(board, d)
@@ -295,29 +333,31 @@ def day(request, d):
         for k in filter(shown, [x.key for x in display_order(defs)]):  # 출근조 먼저, 관제는 뒤에 묶어서
             ctx = _cell_context(defs, found, k, d, depts, types, members)
             ctx.update(
-                next=request.path,
+                next=request.path + bc["bq"],
                 items=_items(show([x for x in found.cells[k].labels if keep(x)]), [], reasons=_why(found, k)),
                 removed_items=_items([x for x in found.cells[k].removed if keep(x)], [], True) if history else [],
             )
             sections.append(ctx)
-    qs = "?" + urlencode({"f": 1, "dept": depts, "type": types, "shift": shifts}, doseq=True)
+    qs = "?" + urlencode({**({"board": board.code} if bc["bq"] else {}), "f": 1, "dept": depts, "type": types,
+                          "shift": shifts}, doseq=True)
     return render(request, "duty/day.html", {
         "d": d, "weekday": DAY_LABELS[d.weekday()], "found": found, "sections": sections,
         "holiday": holidays.closed(d, d).get(d, ""), "note": note,
         "memo_admin": perms.is_board_admin(request.user, board),
         "editable": editable, "prev": _neighbor(d, -1), "next_day": _neighbor(d, 1),
-        "qs": qs, **_filter_ctx(board, defs, depts, types, shifts, history),
+        "qs": qs, **_filter_ctx(board, defs, depts, types, shifts, history, bc["mine"]), **bc,
     })
 
 
 @login_required
 def memo(request, scope, d):
     """[메모] 팝업(근무 변경 창과 같은 방식). 근무표 관리 그룹만."""
-    board = _board(request.user)
+    board = _board(request)
     if scope not in Memo.Scope.values or not perms.is_board_admin(request.user, board):
         raise Http404
+    bq = boards.board_query(request.user, board)
     d = memos.normalize(scope, d)
-    fallback = reverse("day", args=[d]) if scope == Memo.Scope.DAY else reverse("roster")
+    fallback = (reverse("day", args=[d]) if scope == Memo.Scope.DAY else reverse("roster")) + bq
     if request.method == "POST":
         try:
             if request.POST.get("delete"):
@@ -335,14 +375,14 @@ def memo(request, scope, d):
     return render(request, "duty/_memo_form.html", {
         "scope": scope, "d": d, "memo": memos.for_range(board, d, d)[scope].get(d), "next": safe_next(request, fallback),
         "title": {"day": f"{d:%Y-%m-%d} 메모", "week": f"{d.month}/{d.day} 주 메모", "month": f"{d.year}년 {d.month}월 메모"}[scope],
-        "affected": memos.affected(board, d) if scope == Memo.Scope.DAY else 0,
+        "affected": memos.affected(board, d) if scope == Memo.Scope.DAY else 0, "bq": bq,
     })
 
 
 @login_required
 def me(request):
     member = request.user if request.user.department_id else None
-    board = _board(request.user)
+    board = boards.home(request.user)  # 내 스케줄은 늘 내 근무표
     _, _, shifts = prefs.clean(board, [], [], request.GET.getlist("shift"))
     items = member_schedule(board, member, perms.today(), _shown(shifts)) if member else []
     return render(request, "duty/me.html", {
```

템플릿(`roster.html` 은 제목 옆 "보기 전용"과 주간/월간 앞 고르기 버튼, `_filters.html` 은 남의 근무표에서 부서·유형·스케줄을 그리지 않고 `board` 숨은 값을 보냄, 나머지는 링크·`action` 뒤에 `bq`/`bqa`):
```diff
diff --git a/duty/templates/duty/_cell_form.html b/duty/templates/duty/_cell_form.html
--- a/duty/templates/duty/_cell_form.html
+++ b/duty/templates/duty/_cell_form.html
@@ -1,4 +1,4 @@
-<form method="post" action="{% url 'cell' d cell %}" onsubmit="return cellConfirm(this)">{% csrf_token %}
+<form method="post" action="{% url 'cell' d cell %}{{ bq }}" onsubmit="return cellConfirm(this)">{% csrf_token %}
   <input type="hidden" name="next" value="{{ next }}">
   {% if not inline %}<p><strong>{{ d|date:"Y-m-d" }} {% if slot %}장중관제 {% endif %}{{ label }}</strong></p>{% endif %}
   <p><small>{% if lunch %}From 대신 To 가 점심당번이 됩니다.{% else %}From 과 To 의 근무를 서로 맞바꿉니다. To 가 그날 {% if slot %}장중관제가{% else %}근무가{% endif %} 없으면 From 대신 들어갑니다.{% endif %}</small></p>
@@ -20,7 +20,7 @@
 </form>
 {% if not slot and not lunch and current_members %}
 <hr>
-<form method="post" action="{% url 'cell' d cell %}">{% csrf_token %}
+<form method="post" action="{% url 'cell' d cell %}{{ bq }}">{% csrf_token %}
   <input type="hidden" name="next" value="{{ next }}">
   <p><small>휴가·출장·교육이면 사유를 붙입니다. 사유가 붙으면 그날 근무로 치지 않습니다(알림·캘린더·관제에서 빠짐).</small></p>
   <label>사유
diff --git a/duty/templates/duty/_daycell.html b/duty/templates/duty/_daycell.html
--- a/duty/templates/duty/_daycell.html
+++ b/duty/templates/duty/_daycell.html
@@ -1,10 +1,10 @@
-<a href="{% url 'day' d.date %}"><strong>{% if view == "week" %}{{ d.date.month }}/{{ d.date.day }}{% else %}{{ d.date.day }}{% endif %}</strong></a>{% if memo_admin and not d.other %} <a class="memo-btn" href="{% url 'memo' 'day' d.date %}" hx-get="{% url 'memo' 'day' d.date %}?next={{ request.get_full_path|urlencode }}" hx-target="#dlg-body" aria-label="{{ d.date|date:'n/j' }} 메모">[메모]</a>{% endif %}
+<a href="{% url 'day' d.date %}{{ bq }}"><strong>{% if view == "week" %}{{ d.date.month }}/{{ d.date.day }}{% else %}{{ d.date.day }}{% endif %}</strong></a>{% if memo_admin and not d.other %} <a class="memo-btn" href="{% url 'memo' 'day' d.date %}{{ bq }}" hx-get="{% url 'memo' 'day' d.date %}?next={{ request.get_full_path|urlencode }}{{ bqa }}" hx-target="#dlg-body" aria-label="{{ d.date|date:'n/j' }} 메모">[메모]</a>{% endif %}
 {% if d.holiday and not d.other %}<p class="hol">{{ d.holiday }}</p>{% endif %}
 {% if d.memo and not d.no_work and not d.other %}<p class="memo">{{ d.memo|linebreaksbr }}</p>{% endif %}
 {% if d.other %}{% elif d.no_work %}<p class="nowork">{{ d.memo|default:"근무 없음"|linebreaksbr }}</p>{% elif d.empty %}<p class="none">근무표 없음</p>{% else %}
 {% for c in d.commute %}<div class="sec"><small>{{ c.label }}</small>
-  {% if d.edit %}<a class="cell" href="{% url 'day' d.date %}#{{ c.key }}" hx-get="{% url 'cell' d.date c.key %}?next={{ request.get_full_path|urlencode }}{{ filter_qs }}" hx-target="#dlg-body" aria-label="{{ d.date|date:'n/j' }} {{ c.label }} 바꾸기">{% include "duty/_cellbody.html" %}</a>{% else %}{% for line in c.lines %}{% include "duty/_line.html" %}{% endfor %}{% endif %}
+  {% if d.edit %}<a class="cell" href="{% url 'day' d.date %}{{ bq }}#{{ c.key }}" hx-get="{% url 'cell' d.date c.key %}?next={{ request.get_full_path|urlencode }}{{ filter_qs }}" hx-target="#dlg-body" aria-label="{{ d.date|date:'n/j' }} {{ c.label }} 바꾸기">{% include "duty/_cellbody.html" %}</a>{% else %}{% for line in c.lines %}{% include "duty/_line.html" %}{% endfor %}{% endif %}
   {% for line in c.removed %}<div>{% include "duty/_labels.html" %}</div>{% endfor %}</div>{% endfor %}
 {% if d.duty %}<div class="sec slot"><small>관제</small>
-  {% for c in d.duty %}{% if c.lines or c.removed or d.edit %}<div>{% if d.edit %}<a class="cell" href="{% url 'day' d.date %}#{{ c.key }}" hx-get="{% url 'cell' d.date c.key %}?next={{ request.get_full_path|urlencode }}{{ filter_qs }}" hx-target="#dlg-body" aria-label="{{ d.date|date:'n/j' }} 관제 {{ c.label }} 바꾸기">{% endif %}{{ c.time }} {% for line in c.lines %}{% include "duty/_labels.html" %}{% if not forloop.last %}, {% endif %}{% empty %}{% if d.edit %}<span class="add">+</span>{% endif %}{% endfor %}{% if d.edit %}</a>{% endif %}{% for line in c.removed %} {% include "duty/_labels.html" %}{% endfor %}</div>{% endif %}{% endfor %}</div>{% endif %}
+  {% for c in d.duty %}{% if c.lines or c.removed or d.edit %}<div>{% if d.edit %}<a class="cell" href="{% url 'day' d.date %}{{ bq }}#{{ c.key }}" hx-get="{% url 'cell' d.date c.key %}?next={{ request.get_full_path|urlencode }}{{ filter_qs }}" hx-target="#dlg-body" aria-label="{{ d.date|date:'n/j' }} 관제 {{ c.label }} 바꾸기">{% endif %}{{ c.time }} {% for line in c.lines %}{% include "duty/_labels.html" %}{% if not forloop.last %}, {% endif %}{% empty %}{% if d.edit %}<span class="add">+</span>{% endif %}{% endfor %}{% if d.edit %}</a>{% endif %}{% for line in c.removed %} {% include "duty/_labels.html" %}{% endfor %}</div>{% endif %}{% endfor %}</div>{% endif %}
 {% endif %}
diff --git a/duty/templates/duty/_filters.html b/duty/templates/duty/_filters.html
--- a/duty/templates/duty/_filters.html
+++ b/duty/templates/duty/_filters.html
@@ -1,10 +1,10 @@
-<input type="hidden" name="f" value="1">
+<input type="hidden" name="f" value="1">{% if bq %}<input type="hidden" name="board" value="{{ board_code }}">{% endif %}
 {% if not nested %}<details class="filters"><summary>필터{% if filter_on %} <span class="on">적용 중</span>{% endif %}</summary><div class="filters-body">{% endif %}
-  <fieldset class="filter"><legend>부서</legend>{% for c in dept_choices %}<label><input type="checkbox" name="dept" value="{{ c.code }}"{% if c.checked %} checked{% endif %}> {{ c.name }}</label>{% endfor %}</fieldset>
+  {% if filterable %}<fieldset class="filter"><legend>부서</legend>{% for c in dept_choices %}<label><input type="checkbox" name="dept" value="{{ c.code }}"{% if c.checked %} checked{% endif %}> {{ c.name }}</label>{% endfor %}</fieldset>
   <fieldset class="filter"><legend>유형</legend>{% for c in type_choices %}<label><input type="checkbox" name="type" value="{{ c.code }}"{% if c.checked %} checked{% endif %}> {{ c.name }}</label>{% endfor %}</fieldset>
-  <fieldset class="filter"><legend>스케줄</legend>{% for c in shift_choices %}<label><input type="checkbox" name="shift" value="{{ c.code }}"{% if c.checked %} checked{% endif %}> {{ c.name }}</label>{% endfor %}</fieldset>
+  <fieldset class="filter"><legend>스케줄</legend>{% for c in shift_choices %}<label><input type="checkbox" name="shift" value="{{ c.code }}"{% if c.checked %} checked{% endif %}> {{ c.name }}</label>{% endfor %}</fieldset>{% endif %}
   <fieldset class="filter"><legend>보기</legend><input type="hidden" name="hist" value="0"><label><input type="checkbox" name="hist" value="1"{% if history %} checked{% endif %}> 변경 내역 표시(A&gt;B·취소선)</label></fieldset>
-  <small class="hint">부서·유형·스케줄은 모두 해제하면 전체 표시</small>
+  {% if filterable %}<small class="hint">부서·유형·스케줄은 모두 해제하면 전체 표시</small>{% endif %}
 {% if not nested %}</div></details>{% endif %}
   <script>{
     // 체크박스를 바꾸면 바로 다시 불러온다. 그때 스크롤 위치와 필터 펼침을 기억했다가 되살린다(맨 위로 튀거나 다시 접히지 않게)
diff --git a/duty/templates/duty/_memo.html b/duty/templates/duty/_memo.html
--- a/duty/templates/duty/_memo.html
+++ b/duty/templates/duty/_memo.html
@@ -1 +1 @@
-{% if m or memo_admin %}<div class="memo-note"><small>{% if scope == "week" %}주 메모{% else %}{{ md.month }}월 메모{% endif %}</small>{% if m %} <span>{{ m.text|linebreaksbr }}</span>{% endif %}{% if memo_admin %} <a class="memo-btn" href="{% url 'memo' scope md %}" hx-get="{% url 'memo' scope md %}?next={{ request.get_full_path|urlencode }}" hx-target="#dlg-body">[메모]</a>{% endif %}</div>{% endif %}
+{% if m or memo_admin %}<div class="memo-note"><small>{% if scope == "week" %}주 메모{% else %}{{ md.month }}월 메모{% endif %}</small>{% if m %} <span>{{ m.text|linebreaksbr }}</span>{% endif %}{% if memo_admin %} <a class="memo-btn" href="{% url 'memo' scope md %}{{ bq }}" hx-get="{% url 'memo' scope md %}?next={{ request.get_full_path|urlencode }}{{ bqa }}" hx-target="#dlg-body">[메모]</a>{% endif %}</div>{% endif %}
diff --git a/duty/templates/duty/_memo_form.html b/duty/templates/duty/_memo_form.html
--- a/duty/templates/duty/_memo_form.html
+++ b/duty/templates/duty/_memo_form.html
@@ -1,4 +1,4 @@
-<form method="post" action="{% url 'memo' scope d %}" onsubmit="return memoConfirm(this, event.submitter)">{% csrf_token %}
+<form method="post" action="{% url 'memo' scope d %}{{ bq }}" onsubmit="return memoConfirm(this, event.submitter)">{% csrf_token %}
   <input type="hidden" name="next" value="{{ next }}">
   <input type="hidden" name="confirm" value="">
   <p><strong>{{ title }}</strong></p>
diff --git a/duty/templates/duty/day.html b/duty/templates/duty/day.html
--- a/duty/templates/duty/day.html
+++ b/duty/templates/duty/day.html
@@ -2,12 +2,12 @@
 {% block content %}
 <nav aria-label="날짜 이동">
   <ul><li><a href="{% url 'day' prev %}{{ qs }}">◀</a></li></ul>
-  <ul><li><strong>{{ d|date:"Y-m-d" }} ({{ weekday }})</strong></li></ul>
+  <ul><li><strong>{{ d|date:"Y-m-d" }} ({{ weekday }})</strong>{% if view_only %} <small>보기 전용</small>{% endif %}</li></ul>
   <ul><li><a href="{% url 'day' next_day %}{{ qs }}">▶</a></li></ul>
 </nav>
 {% if holiday %}<p class="hol">{{ holiday }}</p>{% endif %}
 {% if note and not note.no_work %}<p class="memo">{{ note.text|linebreaksbr }}</p>{% endif %}
-{% if memo_admin %}<p><a class="memo-btn" href="{% url 'memo' 'day' d %}" hx-get="{% url 'memo' 'day' d %}?next={{ request.get_full_path|urlencode }}" hx-target="#dlg-body">[메모]</a></p>{% endif %}
+{% if memo_admin %}<p><a class="memo-btn" href="{% url 'memo' 'day' d %}{{ bq }}" hx-get="{% url 'memo' 'day' d %}?next={{ request.get_full_path|urlencode }}{{ bqa }}" hx-target="#dlg-body">[메모]</a></p>{% endif %}
 <form method="get" class="search">
   {% include "duty/_filters.html" %}
 </form>
diff --git a/duty/templates/duty/roster.html b/duty/templates/duty/roster.html
--- a/duty/templates/duty/roster.html
+++ b/duty/templates/duty/roster.html
@@ -1,7 +1,8 @@
 {% extends "duty/base.html" %}
 {% block content %}
 <div class="cal-nav">
-  <h3 class="cal-title">{{ title }}</h3>
+  <h3 class="cal-title">{{ title }}{% if view_only %} <small>보기 전용</small>{% endif %}</h3>
+  {% if board_links %}<span class="seg" role="group" aria-label="근무표">{% for b in board_links %}<a href="{{ b.href }}"{% if b.current %} aria-current="page"{% endif %}>{{ b.name }}</a>{% endfor %}</span>{% endif %}
   <span class="seg" role="group" aria-label="보기">
     <a href="{{ week_link }}"{% if view == 'week' %} aria-current="page"{% endif %}>주간</a><a href="{{ month_link }}"{% if view == 'month' %} aria-current="page"{% endif %}>월간</a>
   </span>
```

- [ ] **Step 5: 알림 링크(남의 근무표일 때만 `?board=`)**

`duty/alarms/plan.py`(순수 유지: 문자열만 받는다), `duty/services/alarm_runner.py`, `duty/services/change_notice.py`:
```diff
diff --git a/duty/alarms/plan.py b/duty/alarms/plan.py
--- a/duty/alarms/plan.py
+++ b/duty/alarms/plan.py
@@ -23,6 +23,7 @@ class RuleSpec:
     depts: tuple[str, ...]
     types: tuple[str, ...]
     lunch: tuple[time, time] | None = None  # 개인 규칙 주인 부서의 점심 시각(점심당번 시작·문구). 없으면 None
+    query: str = ""  # 링크 뒤에 붙일 "?board=<code>"(알림의 근무표가 받는 사람의 근무표와 다를 때만). hash 와 무관
 
 
 @dataclass(frozen=True)
@@ -130,7 +131,7 @@ def _personal(defs, r, day, cells, starts, deliveries, now, destinations, today,
             # 취소는 이 목적지에 무언가 성공적으로 알린 적이 있을 때만
             if last == h or (not inside and not (last or "").startswith(("in:", "out:"))):
                 continue
-            out.append(Due(r.id, day.date, c, ch, title, m.clip(text), h, f"/day/{day.date.isoformat()}/",
+            out.append(Due(r.id, day.date, c, ch, title, m.clip(text), h, f"/day/{day.date.isoformat()}/{r.query}",
                            start, m.clip_bytes(text.replace("\n", " ")), dest))
     return out
 
@@ -160,5 +161,5 @@ def _report(defs, r, day, cells, starts, info, deliveries, now, dept_names, synt
         head = m.report_header(day.date, cond, prev is not None)
         summary = f"{head} · {len(uniq)}명"
         out.append(Due(r.id, day.date, "report", ch, m.REPORT_TITLE, m.clip("\n".join([head, *lines])), h,
-                       f"/day/{day.date.isoformat()}/", last_start, m.clip_bytes(summary), dest))
+                       f"/day/{day.date.isoformat()}/{r.query}", last_start, m.clip_bytes(summary), dest))
     return out
diff --git a/duty/services/alarm_runner.py b/duty/services/alarm_runner.py
--- a/duty/services/alarm_runner.py
+++ b/duty/services/alarm_runner.py
@@ -113,10 +113,20 @@ def collect(now):
     dues = []
+    homes = {}  # 사용자별 내 근무표. 매분 도는 작업자가 규칙마다 부서·관리 그룹을 다시 조회하지 않게
+
+    def query(r, board) -> str:
+        """알림 링크의 ?board=(설계 8.1): 남의 근무표 보고서만. 개인 규칙은 주인 부서의 근무표에서만 돌아 늘 ""."""
+        if r.kind != "report":
+            return ""
+        if r.user_id not in homes:
+            homes[r.user_id] = boards.home(r.user)
+        return boards.link_query(homes[r.user_id], board)
+
     for board in Board.objects.filter(pk__in=list(by_board)).order_by("id"):
         group = by_board[board.id]
         ids = {r.id for r in group}
         specs = [RuleSpec(r.id, r.user.name if r.user.department_id else None, r.kind, r.timing, r.offset,
                           r.at_minute, tuple(ch for ch in ("telegram", "push") if getattr(r, ch)),
-                          tuple(r.shifts), tuple(r.depts), tuple(r.types), _lunch(r)) for r in group]
+                          tuple(r.shifts), tuple(r.depts), tuple(r.types), _lunch(r),
+                          query(r, board)) for r in group]
         # 주인은 있어도 배정이 하나도 없는 날은 넘기지 않는다(빈 보고서 방지, 설계 6.1).
         # 그날의 옛 발송 기록은 extra_dates 의 빈 날로 계산돼 취소가 나간다(지금과 같다)
         days = [d for d in published_days(board, today, today + HORIZON) if any(d.members.values())]
diff --git a/duty/services/change_notice.py b/duty/services/change_notice.py
--- a/duty/services/change_notice.py
+++ b/duty/services/change_notice.py
@@ -43,7 +43,7 @@ def tick(now) -> int:
                                           r.after and r.after.name, by)
         for u in {r.before, r.after} - {None, r.by}:
             if u.is_active and u.notify_changes:
-                sent += _send(conf, u, title, text, f"/day/{r.date.isoformat()}/")
+                sent += _send(conf, u, title, text, f"/day/{r.date.isoformat()}/{boards.board_query(u, board)}")
     if sent:
         log.info("change notices: sent=%d", sent)
     return sent
```

- [ ] **Step 6: 이력 근무표 열과 필터**

`duty/views/manage.py`, `duty/templates/duty/changes.html`, `duty/templates/duty/base.html`(select 를 입력칸과 같은 줄 높이로):
```diff
diff --git a/duty/templates/duty/base.html b/duty/templates/duty/base.html
--- a/duty/templates/duty/base.html
+++ b/duty/templates/duty/base.html
@@ -49,6 +49,7 @@
     form.labeled { align-items: flex-end; }
     form.labeled label { display: flex; flex-direction: column; flex: 1 1 9rem; margin: 0; font-size: .8rem; }
     form.labeled label input { width: 100%; margin-top: .2rem; font-size: 1rem; }
+    form.labeled label select { width: 100%; margin: .2rem 0 0; font-size: 1rem; }
     td.nw { white-space: nowrap; }
     nav a, nav button, nav strong, .lb, .hl1, .hl2, .hl3 { white-space: nowrap; }
     nav ul { flex-wrap: wrap; }
diff --git a/duty/templates/duty/changes.html b/duty/templates/duty/changes.html
--- a/duty/templates/duty/changes.html
+++ b/duty/templates/duty/changes.html
@@ -6,13 +6,14 @@
   <label>까지 <input type="date" name="to" value="{{ end|date:'Y-m-d' }}"></label>
   <label>바뀐 사람 <input name="name" value="{{ name }}" placeholder="이름"></label>
   <label>수정자 <input name="by" value="{{ by }}" placeholder="이름 또는 아이디"></label>
+  {% if board_choices %}<label>근무표 <select name="board"><option value="">전부</option>{% for b in board_choices %}<option value="{{ b.code }}"{% if b.code == board_code %} selected{% endif %}>{{ b.name }}</option>{% endfor %}</select></label>{% endif %}
   <button>보기</button>
 </form>
 <div class="grid-wrap"><table>
-  <thead><tr><th>시각</th><th>수정자</th><th>근무일</th><th>칸</th><th>변경</th><th>회차</th></tr></thead>
+  <thead><tr><th>시각</th><th>수정자</th>{% if board_choices %}<th>근무표</th>{% endif %}<th>근무일</th><th>칸</th><th>변경</th><th>회차</th></tr></thead>
   <tbody>{% for l in logs %}
-    <tr><td class="nw">{{ l.at|date:"Y-m-d H:i" }}</td><td class="nw">{{ l.by }}</td><td class="nw">{{ l.date|date:"Y-m-d" }}</td><td class="nw">{{ l.cell }}</td>
+    <tr><td class="nw">{{ l.at|date:"Y-m-d H:i" }}</td><td class="nw">{{ l.by }}</td>{% if board_choices %}<td class="nw">{{ l.board }}</td>{% endif %}<td class="nw">{{ l.date|date:"Y-m-d" }}</td><td class="nw">{{ l.cell }}</td>
       <td class="nw">{{ l.before|default:"(없음)" }} → {{ l.after|default:"(없음)" }}</td><td class="nw">{{ l.period }}</td></tr>
-  {% empty %}<tr><td colspan="6">이력이 없습니다.</td></tr>{% endfor %}</tbody>
+  {% empty %}<tr><td colspan="{% if board_choices %}7{% else %}6{% endif %}">이력이 없습니다.</td></tr>{% endfor %}</tbody>
 </table></div>
 {% endblock %}
diff --git a/duty/views/manage.py b/duty/views/manage.py
--- a/duty/views/manage.py
+++ b/duty/views/manage.py
@@ -187,8 +187,12 @@ def stats_view(request):
 
 @admin_required
 def change_log(request):
-    qs = (ChangeLog.objects.filter(period__board__in=perms.admin_boards(request.user))  # 내가 관리하는 근무표만(설계 9절)
-          .select_related("by", "before", "after", "period").order_by("-at", "-id"))
+    mine = list(perms.admin_boards(request.user).order_by("id"))
+    qs = (ChangeLog.objects.filter(period__board__in=mine)  # 내가 관리하는 근무표만(설계 9절)
+          .select_related("by", "before", "after", "period__board").order_by("-at", "-id"))
+    board_code = request.GET.get("board", "")
+    if board_code:  # 근무표 필터(내가 관리하는 근무표가 둘 이상일 때 보인다). 남의 근무표 코드는 빈 결과
+        qs = qs.filter(period__board__code=board_code)
     start, end = date_param(request, "from"), date_param(request, "to")
     if start:
         qs = qs.filter(date__gte=start)
@@ -207,8 +211,10 @@ def change_log(request):
             "cell": cell_label(defs[log.period.board_id], log.cell),
             "before": join_reason(log.before.name, log.reason_before) if log.before else "",
             "after": join_reason(log.after.name, log.reason_after) if log.after else "", "period": log.period.name,
+            "board": log.period.board.name,
         }
         for log in qs[:500]
     ]
-    return render(request, "duty/changes.html", {"logs": logs, "name": name, "by": by, "start": start, "end": end})
+    return render(request, "duty/changes.html", {"logs": logs, "name": name, "by": by, "start": start, "end": end,
+                                                 "board_choices": mine if len(mine) > 1 else [], "board_code": board_code})
```

- [ ] **Step 7: 알림 규칙 화면(다시 그리기, 부서 선택지, 개인 규칙 "전부" 기본값)**

`duty/alarms/forms.py`, `duty/views/alarms.py`, `duty/templates/duty/alarm_rule_form.html`:
```diff
diff --git a/duty/alarms/forms.py b/duty/alarms/forms.py
--- a/duty/alarms/forms.py
+++ b/duty/alarms/forms.py
@@ -7,10 +7,6 @@ from ..services import boards, prefs
 from ..shifts import DEVELOPER, STAFF
 
 
-def _first_board_id():
-    return Board.objects.order_by("id").values_list("pk", flat=True).first()
-
-
 class RuleForm(forms.Form):
     enabled = forms.BooleanField(label="켬", required=False, initial=True)
     kind = forms.ChoiceField(label="종류", choices=AlarmKind.choices, initial="personal", widget=forms.RadioSelect)
@@ -32,15 +28,17 @@ class RuleForm(forms.Form):
     def __init__(self, *args, user=None, **kwargs):
         super().__init__(*args, **kwargs)
         all_boards = list(Board.objects.order_by("id"))
-        # 근무표가 하나면 칸을 숨기고 그 근무표로 고정(1단계 화면 그대로). 부서 선택지는 그 근무표의 부서
+        # 근무표가 하나면 칸을 숨기고 그 근무표로 고정(1단계 화면 그대로)
         self.fixed_board = all_boards[0] if len(all_boards) == 1 else None
         if self.fixed_board is None:
             self.fields["board"].label_from_instance = lambda b: b.name
-            depts = Department.objects.all()  # 고른 근무표 밖의 부서는 normalize 가 막는다
         else:
             del self.fields["board"]
-            depts = Department.objects.filter(board=self.fixed_board)
-        self.fields["shifts"].choices = list(prefs.choices(boards.active_defs(self._shift_board(all_boards, user))).items())
+        board = self._shift_board(all_boards, user)
+        self.fields["shifts"].choices = list(prefs.choices(boards.active_defs(board)).items())
+        # 부서 선택지 = 고른 근무표의 부서(설계 8.1). 개인 규칙은 부서 칸을 숨기고 저장 때 버리므로 막지 않는다
+        report = (self.data if self.is_bound else self.initial).get("kind") == "report"
+        depts = Department.objects.filter(board=board) if self.fixed_board or report else Department.objects.all()
         self.fields["depts"].choices = list(depts.values_list("code", "name"))
 
     def _shift_board(self, all_boards, user):
@@ -51,22 +49,31 @@ class RuleForm(forms.Form):
         if src.get("kind") == "report":
             picked = str(src.get("board") or "")
             return next((b for b in all_boards if str(b.pk) == picked), all_boards[0] if all_boards else boards.it_board())
-        # ponytail: 빈 폼은 처음 그릴 때의 종류·근무표 기준이라 화면에서 종류·근무표를 바꿔도 체크박스는 그대로(저장 때 POST 값으로 다시 검사).
-        # 고르는 즉시 다시 그리기는 2단계 근무표 고르기 화면과 함께
+        # 화면에서 종류·근무표를 바꾸면 redraw 로 다시 그린다(alarm_rule_form.html)
         return (boards.board_of(user) if user else None) or boards.it_board()
 
+    @classmethod
+    def redraw(cls, data, user=None):
+        """종류·근무표를 바꿨을 때 다시 그리는 빈 폼(검사·저장 없음): 입력한 값은 두고 스케줄·부서는 새 근무표의 '전부'로."""
+        probe = cls(data, user=user)  # 바뀐 종류·근무표 기준의 선택지
+        initial = {n: f.widget.value_from_datadict(data, None, n) for n, f in probe.fields.items()}
+        initial.update(shifts=[c for c, _ in probe.fields["shifts"].choices],
+                       depts=[c for c, _ in probe.fields["depts"].choices])
+        return cls(initial=initial, user=user)
+
     @staticmethod
     def initial_from(rule) -> dict:
         h, m = divmod(rule.offset, 60)
         timed = rule.timing == "before_start"
-        board_id = rule.board_id or _first_board_id()
-        return dict(enabled=rule.enabled, kind=rule.kind, board=board_id, timing=rule.timing,
+        # '전부'를 체크로 그릴 근무표: 보고서 = 규칙의 근무표, 개인 = 주인의 근무표(부서 없는 계정은 IT)
+        board = rule.board if rule.board_id else (boards.board_of(rule.user) or boards.it_board())
+        return dict(enabled=rule.enabled, kind=rule.kind, board=board.pk, timing=rule.timing,
                     hours=h if timed else 2, minutes=m if timed else 0, days=1 if timed else rule.offset,
                     at_time=time(18, 0) if timed else time(*divmod(rule.at_minute, 60)),
                     telegram=rule.telegram, push=rule.push,
                     # 저장은 '전부 = 빈 목록'이라 그대로 그리면 전부 해제로 보인다 → 전부 체크로
-                    shifts=rule.shifts or list(prefs.choices(boards.active_defs(Board.objects.get(pk=board_id)))),
-                    depts=rule.depts or list(Department.objects.filter(board_id=board_id).values_list("code", flat=True)),
+                    shifts=rule.shifts or list(prefs.choices(boards.active_defs(board))),
+                    depts=rule.depts or list(Department.objects.filter(board=board).values_list("code", flat=True)),
                     types=rule.types or [STAFF, DEVELOPER])
 
     def clean(self):
diff --git a/duty/templates/duty/alarm_rule_form.html b/duty/templates/duty/alarm_rule_form.html
--- a/duty/templates/duty/alarm_rule_form.html
+++ b/duty/templates/duty/alarm_rule_form.html
@@ -22,6 +22,7 @@
   {% endif %}<fieldset class="filter" data-kind="report"><legend>부서</legend>{{ form.depts }}</fieldset>
   <fieldset class="filter" data-kind="report"><legend>유형</legend>{{ form.types }}</fieldset>
   <small>모두 해제하면 전부</small>
+  <button name="redraw" value="1" formnovalidate hidden></button>
   <div class="row-btns"><button>저장</button><a href="{% url 'alarms' %}" role="button" class="secondary">취소</a></div>
 </form>
 <style>
@@ -48,7 +49,14 @@
       f.querySelectorAll("[data-timing]").forEach(el => el.hidden = !el.dataset.timing.split(" ").includes(timing));
       document.getElementById("days-unit").textContent = timing === "bizdays" ? "영업일 전" : "일 전";
     };
-    f.addEventListener("change", sync);
+    f.addEventListener("change", e => {
+      // 근무표가 둘 이상이면 종류·근무표에 따라 스케줄·부서 선택지가 달라진다: 저장하지 않고 다시 그린다
+      if ({{ multi_board|yesno:"true,false" }} && (e.target.name === "kind" || e.target.name === "board")) {
+        f.requestSubmit(f.querySelector("button[name=redraw]"));
+        return;
+      }
+      sync();
+    });
     sync();
   })();
 </script>
diff --git a/duty/views/alarms.py b/duty/views/alarms.py
--- a/duty/views/alarms.py
+++ b/duty/views/alarms.py
@@ -109,7 +109,9 @@ def telegram_link_check(request):
 
 
 def _rule_form(request, rule=None):
-    if request.method == "POST":
+    if request.method == "POST" and request.POST.get("redraw"):  # 종류·근무표를 바꿈: 저장하지 않고 다시 그린다
+        form = RuleForm.redraw(request.POST, user=request.user)
+    elif request.method == "POST":
         form = RuleForm(request.POST, user=request.user)
         if form.is_valid():
             try:
```

- [ ] **Step 8: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_pick.py`
Expected: **14 passed**.

Run: `.venv/bin/pytest -W error -q`
Expected: **1089 passed**(참고값: 1075 + 14), 경고 0개. `tests/test_alarm_texts_it.py`·`test_roster_prefs.py`·`test_views_roster.py`·`test_alarm_boards.py` 를 포함해 기존 테스트는 그대로 통과한다(IT 하나일 때 HTML·링크가 같다).

Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --check --dry-run`
Expected: `No changes detected in app 'duty'`

- [ ] **Step 9: 브라우저에서 확인한다(PC 1400px, 모바일 390px)**

가짜 데이터 DB(가상 이름만, 끝나면 지움)로 확인한다. `config.test_settings` 는 임시 폴더 DB 를 쓰고 프로세스가 끝나면 지운다.

```bash
DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py shell -c '
from datetime import date, datetime, time, timezone
from django.core.management import call_command
call_command("migrate", verbosity=0)
from duty.models import Board, BoardShift, ChangeLog, Commute, Department, Period, User
D = date(2026, 11, 16)
it = Board.objects.get(code="it")
ops = Board.objects.create(code="ops", name="시장운영실", input_mode="direct")
for k, n, s, e in [("dawn", "오전", time(7, 30), time(16, 30)), ("normal", "주간", time(9), time(18))]:
    BoardShift.objects.create(board=ops, key=k, name=n, start=s, end=e)
dit = Department.objects.create(code="MEMS", name="매칭엔진실", shifts="dawn,normal,dinner,night", board=it)
dop = Department.objects.create(code="OPS", name="운영", shifts="dawn,normal", board=ops)
me = User.objects.create_user("me", password="unused-Pw-123", name="가상가", department=dit, type="개발자", help_dismissed=True)
adm = User.objects.create_user("adm", password="unused-Pw-123", name="가상관리", department=dit, type="개발자", help_dismissed=True)
adm.groups.add(it.admin_group, ops.admin_group)
for b, d, pre in ((it, dit, "아이"), (ops, dop, "운영")):
    ms = [User.objects.create_user(f"{b.code}{i}", password=None, name=f"{pre}{i}", department=d, type="직원") for i in range(3)]
    p = Period.objects.create(board=b, name="확인용", start_date=D, end_date=date(2026, 11, 20), status="published",
                              overwrite_from=D, published_at=datetime(2026, 11, 14, tzinfo=timezone.utc))
    for x in p.dates():
        Commute.objects.create(period=p, date=x, member=ms[0], shift="dawn")
        Commute.objects.create(period=p, date=x, member=ms[1], shift="normal")
    ChangeLog.objects.create(period=p, date=D, cell="dawn", before=ms[2], after=ms[0], by=adm)
from django.core.management import call_command as cc
cc("runserver", "127.0.0.1:8765", "--noreload")
'
```

브라우저(1400px, 390px)로 `http://127.0.0.1:8765/` 에 `me`·`adm`(비밀번호 `unused-Pw-123`)으로 로그인해 본다.
- `me`: 근무표 화면 주간/월간 앞에 [IT 당번표][시장운영실] 버튼. [시장운영실] → 제목 옆 "보기 전용", 칸 링크·"칸을 누르면…" 없음, 필터에 부서·유형·스케줄 없음(보기만). [근무표] 메뉴를 다시 누르면 시장운영실이 그대로 보이고, [IT 당번표] 를 누르면 IT 로 돌아오며 주소·링크에 `board=` 가 없다. 날짜 칸을 눌러 하루 화면으로 가도 시장운영실이고 [바꾸기] 가 없다.
- `adm`: 시장운영실 월간에서 칸을 누르면 변경 창이 뜨고, 저장 뒤 시장운영실 화면으로 돌아온다. [메모] 저장도 시장운영실에 붙는다. 날짜 이동(◀ ▶ 오늘)·필터 체크·검색 뒤에도 시장운영실이다.
- `adm`: [이력] 에 "근무표" 열과 근무표 선택(전부/IT 당번표/시장운영실)이 있고, 고르면 그 근무표 기록만 보인다.
- `adm`: [알림·캘린더] → 규칙 추가에서 종류를 "보고서형"으로 바꾸면 다시 그려지고(근무표 칸 보임), 근무표를 시장운영실로 바꾸면 스케줄이 오전·주간, 부서가 운영으로 바뀌어 모두 체크된다. 입력해 둔 시간·채널은 남는다. 저장되지는 않는다.
- 390px: 근무표 화면 위쪽(제목·근무표 버튼·주간/월간·이동)이 줄바꿈되어 가로로 넘치지 않는다.

확인 뒤 서버를 끄면(Ctrl+C) 임시 DB 가 지워진다.

- [ ] **Step 10: 전체 테스트와 커밋**

Run: `.venv/bin/pytest -W error -q`
Expected: **1089 passed**, 경고 0개.

```bash
git add duty/services/boards.py duty/services/prefs.py duty/views/roster.py duty/views/manage.py duty/views/alarms.py \
  duty/alarms/plan.py duty/alarms/forms.py duty/services/alarm_runner.py duty/services/change_notice.py \
  duty/templates/duty/roster.html duty/templates/duty/_filters.html duty/templates/duty/_daycell.html \
  duty/templates/duty/_memo.html duty/templates/duty/day.html duty/templates/duty/_cell_form.html \
  duty/templates/duty/_memo_form.html duty/templates/duty/changes.html duty/templates/duty/base.html \
  duty/templates/duty/alarm_rule_form.html tests/test_board_pick.py
git commit -m "feat: 근무표 고르기·보기 전용·?board= 링크 규칙(남의 근무표일 때만), 이력 근무표 열·필터, 알림 규칙 화면 다시 그리기"
```


---

### Task 7: 글씨 크기 3단계·로그인 유지 90일·managers 호환 제거

> 검증: Task 1~6 을 넣은 `feat/boards-phase2` 사본(1089 passed)에 아래 코드를 그대로 넣어 확인했다. 저장소는 고치지 않았다. 결과: `.venv/bin/pytest -W error -q` → **1091 passed**(1089 + 새 2), 경고 0개. `makemigrations duty --check --dry-run` → "No changes detected in app 'duty'". Step 2(2 failed)·Step 6(1 failed)의 실패도 사본에서 재현했다. `tests/test_alarm_texts_it.py` 는 고치지 않았고 그대로 통과한다(알림 코드를 건드리지 않음). 가짜 데이터(가상 이름, 임시 DB, 끝나면 지움)로 월간·주간을 `data-size="xl"` 로 그려 headless Chrome 1400·390px 에서 캡처하고 `scrollWidth` 를 쟀다. 처음엔 390px 아주 크게에서 상단 계정 줄(이름·◐·가·비밀번호·로그아웃)이 로고와 겹치며 20px 넘쳤다. 그래서 `.brand-row` 에 `flex-wrap: wrap` 을 더했고, 그 뒤로는 보통·크게·아주 크게 모두 넘치지 않는다(390px 375/390, 1400px 1385/1400. 월간 표는 원래대로 자기 칸 안에서 가로로 스크롤된다). 버튼을 직접 눌러 보지는 않았다(Step 9 에서 사람이 확인).
>
> 이 작업의 범위(설계 2 표 "로그인·화면", 4.4 managers, 6 "글씨 크기", 9 "로그인 유지", 11 "2단계"):
> - **글씨 크기**: 오른쪽 위 화면 모드 버튼(◐) 바로 옆에 [가] 버튼을 둔다. 누를 때마다 보통 → 크게(×1.15) → 아주 크게(×1.3) → 보통으로 돈다. 고른 값은 `localStorage` `duty-size`(`"l"`·`"xl"`, 보통이면 지움)와 `<html data-size>` 에 둔다. 화면 모드와 같은 head 스크립트가 스타일보다 먼저 붙여서 깜빡이지 않는다. CSS 는 `:root[data-size]` 두 줄이다. Pico 는 `:where(:root)` 의 `font-size: var(--pico-font-size)`(화면 폭마다 100%~131.25%)로 기본 크기를 정하므로, 거기에 곱하면 rem·em 으로 쓴 화면 규칙이 모두 같이 커진다. 로그인 화면도 base.html 을 쓰니 똑같이 보인다.
> - **로그인 유지 90일**: `SESSION_COOKIE_AGE = 90일`. `SESSION_SAVE_EVERY_REQUEST` 는 기본값(False) 그대로 둔다. 그래서 로그인할 때부터 90일이고, 화면을 열 때 세션 DB 쓰기가 생기지 않는다. 비밀번호 변경·[계정 발급] 때 끊기는 동작은 그대로다.
> - **managers 호환 제거**: `Department.managers` property 를 지운다. 남은 사용처는 관리 화면 두 곳(`DepartmentForm.__init__`, `DepartmentAdmin.manager_names`)인데, 둘 다 admin.py 안의 `_input_users(dept)` 로 바꾼다. 관리 화면 폼 칸 이름 `managers` 는 화면·POST 이름이므로 그대로 둔다(`save_related` 는 이미 `input_group.user_set.set`). 테스트의 `X.managers.add(u)` 12곳은 `X.input_group.user_set.add(u)` 로 바꾼다. 마이그레이션 테스트(`test_migration_boards.py`, `test_migration_department_managers.py`)는 옛 스키마의 진짜 M2M(`old_apps`)을 쓰므로 그대로 둔다.
>
> 하지 않는 것: 글씨 크기를 서버(계정)에 저장하는 것. 설계상 기기마다 기억한다. 마이그레이션도 없다. **다음 번호는 그대로 0023.**

**Files:**
- Modify: `duty/templates/duty/base.html`(head 스크립트, `:root[data-size]` 두 줄, `.brand-row` 줄바꿈, `.size-btn`, [가] 버튼, 클릭 스크립트)
- Modify: `config/settings.py`(`SESSION_COOKIE_AGE`)
- Modify: `duty/models.py`(`Department.managers` 삭제), `duty/admin.py`(새 `_input_users`, 사용처 두 곳)
- Modify: `docs/ARCHITECTURE.md`(화면 모드 다음에 글씨 크기, 보안 절에 로그인 유지), `docs/PRINCIPLES.md`(결정 기록 한 줄)
- Test: `tests/test_ui_prefs.py`(새 파일, 2개), `tests/test_admin_department.py`(호환 테스트를 "지웠음" 테스트로 고침, `.managers.add` 1곳)
- Test(`.managers.add(` → `.input_group.user_set.add(` 만): `tests/test_admin_users.py`, `test_boards_generate.py`(2), `test_collect.py`, `test_help.py`, `test_perms.py`(3), `test_views_collect.py`, `test_reasons.py`(Task 4), `test_skip_days.py`(Task 3)

**Interfaces:**
- Consumes: (1단계) `Department.input_group`(FK Group, 직접 입력 근무표 부서는 None), `DepartmentForm`(폼 칸 `managers`), `DepartmentAdmin.manager_names`·`save_related`·`get_queryset` 의 `prefetch_related("input_group__user_set")`, base.html 의 `#theme-btn`·`duty-theme` head 스크립트. 테스트 픽스처 `make_member(name, dept="MEMS", type=..., user=False)`·`depts`·`su_client`·`it_board`.
- Produces:
  - `localStorage["duty-size"] in {"l", "xl"}`(없으면 보통), `<html data-size="l"|"xl">`, 버튼 `#size-btn.size-btn`(글자 "가", 화면 모드 버튼 바로 뒤).
  - CSS `:root[data-size=l] { font-size: calc(var(--pico-font-size) * 1.15); }`, `:root[data-size=xl] { … * 1.3 }`. 화면 규칙은 rem·em 으로 쓰면 따라 커진다(px 은 안 커짐).
  - `settings.SESSION_COOKIE_AGE == 90 * 24 * 3600`, `SESSION_SAVE_EVERY_REQUEST` 는 기본 False.
  - `duty.admin._input_users(dept) -> QuerySet[User]`: 입력 그룹 멤버, 그룹이 없으면 `User.objects.none()`.
  - **없어짐**: `Department.managers`. 뒤 작업과 테스트는 `dept.input_group.user_set` 을 쓴다(그룹이 없을 수 있으면 `input_group_id` 를 먼저 본다). 권한 판단은 지금처럼 `perms` 가 한다.
  - 마이그레이션 없음. **다음 번호 0023.**

- [ ] **Step 1: 글씨 크기·로그인 유지 실패 테스트를 쓴다**

`tests/test_ui_prefs.py`(새 파일):
```python
"""글씨 크기 3단계(기기마다 기억)와 로그인 유지 90일."""
from django.conf import settings

DAYS90 = 90 * 24 * 3600


def test_size_button_next_to_theme_button(client, make_member):
    client.force_login(make_member("가", user=True))
    body = client.get("/me/").content.decode()
    head = body.split("</head>")[0]
    assert "duty-size" in head.split('<link rel="stylesheet"')[0]  # 스타일보다 먼저 적용(깜빡임 없게)
    assert ":root[data-size=l]" in head and ":root[data-size=xl]" in head
    assert "* 1.15" in head and "* 1.3" in head
    top = body.split('id="theme-btn"')[1].split("</div>")[0]
    assert 'id="size-btn"' in top and ">가</button>" in top  # 화면 모드 버튼 바로 옆
    assert "duty-size" in client.get("/login/").content.decode()  # 로그인 화면도


def test_login_lasts_90_days_from_login(client, make_member):
    assert settings.SESSION_COOKIE_AGE == DAYS90
    assert settings.SESSION_SAVE_EVERY_REQUEST is False  # 화면을 열 때 세션 DB 쓰기를 만들지 않는다
    client.force_login(make_member("가", user=True))
    assert client.session.get_expiry_age() == DAYS90
    client.get("/me/")  # 로그인 뒤 첫 화면은 사용법 안내 표시(show_help)를 세션에서 꺼내며 한 번 쓴다
    r = client.get("/me/")
    assert r.status_code == 200 and settings.SESSION_COOKIE_NAME not in r.cookies  # 요청마다 늘리지 않는다
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_ui_prefs.py`
Expected: **2 failed**. `test_size_button_next_to_theme_button` 은 `assert 'duty-size' in …` 에서 실패하고, `test_login_lasts_90_days_from_login` 은 `assert 1209600 == 7776000` 에서 실패한다.

- [ ] **Step 3: [가] 버튼과 90일을 넣는다**

`duty/templates/duty/base.html`(바뀐 곳 전부):
```diff
diff --git a/duty/templates/duty/base.html b/duty/templates/duty/base.html
--- a/duty/templates/duty/base.html
+++ b/duty/templates/duty/base.html
@@ -4,5 +4,6 @@
   <meta charset="utf-8">
   <meta name="viewport" content="width=device-width, initial-scale=1">
-  <script>try { const t = localStorage.getItem("duty-theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; } catch (e) {}</script>
+  <script>try { const t = localStorage.getItem("duty-theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; } catch (e) {}
+    try { const z = localStorage.getItem("duty-size"); if (z === "l" || z === "xl") document.documentElement.dataset.size = z; } catch (e) {}</script>
   <title>{% block title %}NXT 당번표{% endblock %}</title>
   <link rel="manifest" href="/manifest.webmanifest">
@@ -15,4 +16,7 @@
     /* NEXTRADE BI: RED #E50038(로고·위험), PURPLE #2B1B40(주요 동작). 지정 서체 Noto Sans CJK KR(없으면 시스템 글꼴) */
     /* 화면 모드: <html data-theme="light|dark">(사용자가 고름) 또는 없음(시스템 설정). 다크 값은 아래 두 곳에 같이 둔다 */
+    /* 글씨 크기: <html data-size="l|xl">(사용자가 고름, 없으면 보통). Pico 가 화면 폭마다 바꾸는 기본 크기에 곱한다 */
+    :root[data-size=l] { font-size: calc(var(--pico-font-size) * 1.15); }
+    :root[data-size=xl] { font-size: calc(var(--pico-font-size) * 1.3); }
     :root { --pico-font-family-sans-serif: "Noto Sans KR", "Noto Sans CJK KR", "Apple SD Gothic Neo", "Malgun Gothic", system-ui, sans-serif; }
     :root:not([data-theme=dark]) {
@@ -116,5 +120,5 @@
     /* 상단바: 위 줄 = 로고 + 계정, 아래 줄 = 메뉴 알약(좁으면 여러 줄로 — 숨은 메뉴가 없게) */
     .topbar { border-bottom: 1px solid var(--duty-line); margin-bottom: 1rem; }
-    .topbar .brand-row { display: flex; align-items: center; justify-content: space-between; gap: .5rem; padding: .6rem 0; }
+    .topbar .brand-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem; padding: .6rem 0; }  /* 아주 크게 + 휴대폰: 계정 줄이 아래로 내려간다 */
     .topbar a.brand, .topbar a.brand:hover { color: var(--pico-color); }
     .topbar .brand { display: flex; align-items: center; gap: .5rem; font-weight: 700; font-size: 1.15rem; text-decoration: none; color: var(--pico-color); white-space: nowrap; }
@@ -126,5 +130,5 @@
     .topbar .account form { margin: 0; }
     .topbar .account button { width: auto; margin: 0; min-height: 40px; padding: .25rem .8rem; font-size: .85rem; }
-    .topbar .account .theme-btn { min-width: 40px; padding: .25rem .5rem; font-size: 1rem; line-height: 1; }
+    .topbar .account .theme-btn, .topbar .account .size-btn { min-width: 40px; padding: .25rem .5rem; font-size: 1rem; line-height: 1; }
     .topbar nav.menu ul { display: flex; flex-wrap: wrap; gap: .4rem; margin: 0; padding: 0 0 .7rem; }
     .topbar nav.menu li { list-style: none; margin: 0; padding: 0; }
@@ -159,4 +163,5 @@
         {% if user.is_authenticated %}<span class="who">{{ user.name|default:user.username }}</span>{% endif %}
         <button type="button" id="theme-btn" class="outline secondary theme-btn" aria-label="화면 모드 바꾸기" title="화면 모드 바꾸기">◐</button>
+        <button type="button" id="size-btn" class="outline secondary size-btn" aria-label="글씨 크기 바꾸기" title="글씨 크기 바꾸기">가</button>
         {% if user.is_authenticated %}<a href="{% url 'password_change' %}">비밀번호</a>
         <form method="post" action="{% url 'logout' %}">{% csrf_token %}<button class="outline secondary">로그아웃</button></form>{% endif %}
@@ -203,4 +208,22 @@
     draw();
   })();
+  // 글씨 크기: 보통 → 크게 → 아주 크게 → 보통. 기기마다(localStorage) 기억한다
+  (() => {
+    const b = document.getElementById("size-btn");
+    if (!b) return;
+    const NAMES = {"": "보통", l: "크게", xl: "아주 크게"}, ORDER = ["", "l", "xl"];
+    const now = () => document.documentElement.dataset.size || "";
+    const draw = () => {
+      const m = now(), next = ORDER[(ORDER.indexOf(m) + 1) % 3];
+      b.title = b.ariaLabel = `글씨 크기: ${NAMES[m]} (누르면 ${NAMES[next]})`;
+    };
+    b.addEventListener("click", () => {
+      const next = ORDER[(ORDER.indexOf(now()) + 1) % 3];
+      if (next) document.documentElement.dataset.size = next; else delete document.documentElement.dataset.size;
+      try { next ? localStorage.setItem("duty-size", next) : localStorage.removeItem("duty-size"); } catch (e) {}
+      draw();
+    });
+    draw();
+  })();
   document.body.addEventListener("htmx:afterSwap", e => {
     if (e.detail.target.id === "dlg-body") document.getElementById("dlg").showModal();
```

`config/settings.py`:
```diff
diff --git a/config/settings.py b/config/settings.py
--- a/config/settings.py
+++ b/config/settings.py
@@ -145,5 +145,5 @@ LOGIN_URL = "/login/"
 LOGIN_REDIRECT_URL = "/"
 LOGOUT_REDIRECT_URL = "/login/"
-SESSION_COOKIE_AGE = 14 * 24 * 3600
+SESSION_COOKIE_AGE = 90 * 24 * 3600  # 로그인할 때부터 90일. 요청마다 늘리지 않는다(SESSION_SAVE_EVERY_REQUEST 기본 False: 화면을 열 때 DB 쓰기 없음)
 SESSION_COOKIE_SECURE = not DEBUG
 CSRF_COOKIE_SECURE = not DEBUG
```

`.brand-row` 의 `flex-wrap: wrap` 은 화면 확인에서 나온 것이다. 390px 아주 크게에서 계정 줄이 로고와 겹쳐 20px 넘쳤다. 보통·크게에서는 한 줄에 다 들어가서 줄이 바뀌지 않는다.

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_ui_prefs.py tests/test_views_roster.py`
Expected: 모두 통과. 기존 `test_theme_switch_in_topbar` 도 그대로 통과한다.

- [ ] **Step 5: managers 호환 제거 테스트로 바꾼다**

`tests/test_admin_department.py`:
```diff
diff --git a/tests/test_admin_department.py b/tests/test_admin_department.py
--- a/tests/test_admin_department.py
+++ b/tests/test_admin_department.py
@@ -47,5 +47,5 @@ def test_changelist_shows_labels_count_and_managers(su_client, make_member):
     m = make_member("가", dept="UI")
     make_member("나", dept="UI")
-    m.department.managers.add(m)
+    m.department.input_group.user_set.add(m)
     html = su_client.get(reverse("admin:duty_department_changelist")).content.decode()
     assert "정상·석식교대·야간" in html
@@ -62,12 +62,12 @@ def test_shift_choices_and_labels_come_from_board_definitions(su_client, depts,
 
 
-def test_managers_is_input_group_not_a_field(depts, make_member):
+def test_managers_compat_removed(depts):
+    """2단계 끝: 1단계 호환 property 를 지웠다. 입력 담당자 = 입력 그룹 멤버(관리 화면 폼 칸 이름만 managers)."""
     with pytest.raises(FieldDoesNotExist):
         Department._meta.get_field("managers")
-    a = make_member("가")
-    depts["UI"].managers.add(a)
-    assert list(depts["UI"].input_group.user_set.all()) == [a]
+    assert not hasattr(Department, "managers")
     direct = Board.objects.create(code="ops", name="운영팀", input_mode="direct")
-    assert list(Department.objects.create(code="OPS", name="운영", shifts="normal", board=direct).managers.all()) == []
+    dept = Department.objects.create(code="OPS", name="운영", shifts="normal", board=direct)
+    assert dept.input_group_id is None and list(DepartmentForm(instance=dept).initial["managers"]) == []
```

나머지 테스트의 `.managers.add(` 를 모두 `.input_group.user_set.add(` 로 바꾼다. 이 파일들의 그 줄들은 모두 출근표 취합 근무표(IT)의 부서여서 입력 그룹이 있다.
```bash
sed -i 's/\.managers\.add(/.input_group.user_set.add(/' tests/test_admin_users.py tests/test_boards_generate.py \
  tests/test_collect.py tests/test_help.py tests/test_perms.py tests/test_views_collect.py tests/test_reasons.py tests/test_skip_days.py
grep -rn "\.managers\b" tests | grep -v "tests/test_migration_"   # 아무것도 나오지 않아야 한다
```

- [ ] **Step 6: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_admin_department.py`
Expected: **1 failed**(`test_managers_compat_removed`: `assert not hasattr(Department, "managers")`), 나머지 12개는 통과. sed 로 바꾼 다른 파일들은 property 가 아직 있어도 통과한다.

- [ ] **Step 7: property 를 지우고 관리 화면 사용처를 바꾼다**

`duty/models.py`:
```diff
diff --git a/duty/models.py b/duty/models.py
--- a/duty/models.py
+++ b/duty/models.py
@@ -146,9 +146,4 @@ class Department(models.Model):
         return [s for s in self.shifts.split(",") if s]
 
-    @property
-    def managers(self):
-        """1단계 호환(2단계 끝에 지운다): 출근표 입력 담당 = 입력 그룹 멤버. 그룹이 없으면(직접 입력 근무표) 빈 목록."""
-        return self.input_group.user_set if self.input_group_id else User.objects.none()
-
 
 class UserManager(DjangoUserManager):
```

`duty/admin.py`:
```diff
diff --git a/duty/admin.py b/duty/admin.py
--- a/duty/admin.py
+++ b/duty/admin.py
@@ -17,4 +17,9 @@ from .shifts import shift_defs
 
 
+def _input_users(dept):
+    """부서 입력 그룹 멤버. 새 부서·직접 입력 근무표 부서(그룹 없음)는 빈 목록."""
+    return dept.input_group.user_set.all() if dept.input_group_id else User.objects.none()
+
+
 class DepartmentForm(forms.ModelForm):
     # DB에는 지금처럼 "normal,dinner,night" 문자열로 저장하고, 입력만 체크박스로 받는다
@@ -23,5 +28,5 @@ class DepartmentForm(forms.ModelForm):
         error_messages={"required": "출근조를 하나 이상 선택하세요."},
     )
-    # 1단계 호환: 입력 담당자 = 부서 입력 그룹 멤버. 모델 칸이 아니라 DepartmentAdmin.save_related 가 그룹에 넣는다
+    # 입력 담당자 = 부서 입력 그룹 멤버. 모델 칸이 아니라 DepartmentAdmin.save_related 가 그룹에 넣는다
     managers = forms.ModelMultipleChoiceField(
         label="입력 담당자", queryset=User.objects.none(), required=False,
@@ -40,5 +45,5 @@ class DepartmentForm(forms.ModelForm):
         self.fields["shifts"].choices = [(x.key, x.name) for x in shift_defs(boards.active_defs(board))]
         # 후보는 roster()만. 지금 담당자는 퇴사·부서 해제됐어도 보여야 저장할 때 조용히 빠지지 않는다
-        current = self.instance.managers.all()  # 새 부서·직접 입력 근무표 부서는 빈 목록
+        current = _input_users(self.instance)
         self.fields["managers"].queryset = (User.objects.roster() | current).distinct()
         self.initial.setdefault("managers", list(current))
@@ -81,5 +86,5 @@ class DepartmentAdmin(admin.ModelAdmin):
     @admin.display(description="입력 담당자")
     def manager_names(self, obj):
-        return ", ".join(m.name for m in obj.managers.all()) or "(없음)"
+        return ", ".join(m.name for m in _input_users(obj)) or "(없음)"
 
     def save_related(self, request, form, formsets, change):
```

- [ ] **Step 8: 남은 사용처가 없는지, 전체 테스트가 통과하는지 확인한다**

Run:
```bash
grep -rn "\.managers\b" duty config tests --include=*.py --include=*.html | grep -v "duty/migrations/" | grep -v "tests/test_migration_"
.venv/bin/pytest -W error -q
DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --check --dry-run
```
Expected:
- grep 결과는 없다. `fields["managers"]`·`initial["managers"]`·`cleaned_data["managers"]` 같은 폼 칸 이름은 `.managers` 에 걸리지 않는다.
- 전체 **1091 passed**(참고값), 경고 0.
- "No changes detected in app 'duty'". property 는 스키마가 아니다.

- [ ] **Step 9: 브라우저로 확인한다(아주 크게 + 월간, PC 1400px·휴대폰 390px)**

가짜 데이터 DB 를 임시 폴더에 만든다. 가상 이름만 쓰고, 끝나면 지운다. 루트 `.env` 는 읽지 않는다(`DUTY_ENV_FILE=`, Task 8 과 같은 방식).
```bash
W=$(mktemp -d)
export DUTY_ENV_FILE= DUTY_DEBUG=1 DUTY_DATA_DIR=$W/data
.venv/bin/python manage.py migrate
.venv/bin/python manage.py shell -c '
from datetime import date
from django.utils import timezone
from duty.models import Board, Commute, Department, Period, User
it = Board.objects.get(code="it"); D = date(2026, 11, 16)
d = Department.objects.create(code="MEMS", name="매칭엔진실", shifts="dawn,normal,dinner,night", board=it)
adm = User.objects.create_user("adm", password="unused-Pw-123", name="가상관리", department=d, type="개발자", help_dismissed=True)
adm.groups.add(it.admin_group)
ms = [User.objects.create_user(f"i{i}", password=None, name=f"가상이름{i}", department=d, type="개발자") for i in range(4)]
p = Period.objects.create(board=it, name="확인용", start_date=D, end_date=date(2026, 12, 11), status="published", overwrite_from=D,
                          published_at=timezone.now())
for x in p.dates():
    for m, s in zip(ms, ["dawn", "normal", "dinner", "night"]):
        Commute.objects.create(period=p, date=x, member=m, shift=s)'
.venv/bin/python manage.py runserver
```
`adm` 로 로그인한다. 비밀번호는 위 문자열이다. 첫 로그인 비밀번호 변경이 뜨면 바꾼다. 그다음 `/?view=month&date=2026-11-16` 를 연다.
- [가]를 누를 때마다 글씨가 보통 → 크게 → 아주 크게 → 보통으로 바뀐다. 버튼 title 은 "글씨 크기: 아주 크게 (누르면 보통)" 처럼 지금 값과 다음 값을 보인다.
- 아주 크게에서 새로 고침하거나 다른 메뉴로 가도 그대로다. 처음 그려질 때 작은 글씨가 잠깐 보이는 깜빡임도 없다. 로그아웃해도 로그인 화면이 아주 크게다.
- 1400px·390px(개발자 도구 기기 모드 390×844) 모두, 아주 크게 + 월간에서 `document.documentElement.scrollWidth > innerWidth` 가 false 다.
  - 390px 에서는 계정 줄(◐·가·비밀번호·로그아웃)이 로고 아래로 내려가고, 로고와 겹치지 않는다.
  - 월간 표는 원래대로 자기 칸 안에서 가로로 스크롤된다.
- 다크 모드(◐)와 같이 써도 깨지지 않는다. 주간·하루 화면과 근무 변경 팝업도 한 번씩 연다.
- 확인이 끝나면 서버를 멈추고 `rm -rf "$W"` 로 지운다.

- [ ] **Step 10: 문서를 고친다**

`docs/ARCHITECTURE.md`, `docs/PRINCIPLES.md`:
```diff
diff --git a/docs/ARCHITECTURE.md b/docs/ARCHITECTURE.md
--- a/docs/ARCHITECTURE.md
+++ b/docs/ARCHITECTURE.md
@@ -145,4 +145,5 @@ AlarmSettings(한 행: 봇 토큰, 장애 알림 chat_id, 푸시 키)
 - Pico.css + `base.html`의 공통 스타일. NEXTRADE BI를 따른다: 로고·심볼은 `duty/static/duty/`의 원본 그대로(비율·색 변경 금지), 어두운 배경(다크 모드)은 흰색 단색(CSS `filter`). 지정 서체 Noto Sans KR(없으면 시스템 글꼴, 글꼴 파일은 싣지 않는다).
 - 화면 모드: 상단 버튼으로 시스템·라이트·다크(기기마다 localStorage, `<html data-theme>`). 다크용 색은 `base.html` 맨 위 변수 두 곳(시스템 다크·직접 다크)에만 두고, 화면 규칙은 변수(`--chg`·`--logo-filter` 등)만 쓴다.
+- 글씨 크기: 화면 모드 버튼 옆 [가]로 보통 → 크게(×1.15) → 아주 크게(×1.3)(기기마다 localStorage `duty-size`, `<html data-size="l|xl">`). 화면 모드와 같은 head 스크립트가 스타일보다 먼저 붙여 깜빡이지 않는다. `base.html` 의 `:root[data-size]` 두 줄이 Pico 의 화면 폭별 기본 크기(`--pico-font-size`)에 곱하므로, 화면 규칙은 rem·em 으로 쓰면 함께 커진다. 상단 계정 줄은 넘치면 아래로 내려간다(아주 크게 + 390px).
 - 색: PURPLE `#2B1B40` = 주요 동작 버튼·현재 위치, RED `#E50038`(`--nxt-red`) = 로고·오류·위험 동작, 그리고 "오늘" 표시(달력처럼 읽힌다)만. 일반 버튼에 빨강을 쓰지 않는다(빨강 = 위험으로 읽힌다).
 - 화면마다 다음 단계 하나만 채운 버튼, 되돌리기·다시 하기는 테두리 버튼, 지우기는 맨 아래 "위험 구역"(빨간 테두리) + 확인창.
@@ -160,4 +161,5 @@ AlarmSettings(한 행: 봇 토큰, 장애 알림 chat_id, 푸시 키)
 ## 보안·개인정보
 
+- 로그인은 90일 유지된다(`SESSION_COOKIE_AGE`, 로그인할 때부터. 요청마다 늘리지 않아 화면을 열 때 세션 DB 쓰기가 없다). 비밀번호를 바꾸면 다른 기기의 로그인이, [계정 발급]으로 초기화하면 모든 로그인이 끊긴다.
 - 로그인 5회 실패 시 그 아이디가 15분 잠긴다(django-axes). 비밀번호 변경의 '지금 비밀번호' 확인도 같이 센다.
 - `config/wsgi.py` 가 Django 앞에 `duty/guard.py` 를 둔다: 본문 2MB 초과 413, 15초 안에 본문이 다 오지 않으면 408, 로그인·비밀번호 변경 POST 는 동시에 2개까지(넘치면 429). nginx 가 느린 연결을 먼저 받아 주고, 가드는 nginx 없이 돌 때(개발 PC)나 nginx 설정이 빠졌을 때의 한 번 더 막는 장치다.

diff --git a/docs/PRINCIPLES.md b/docs/PRINCIPLES.md
--- a/docs/PRINCIPLES.md
+++ b/docs/PRINCIPLES.md
@@ -104,2 +104,3 @@
 | 2026-11-15 | 권한은 그룹(근무표 관리·부서 입력·그룹 관리자). 스태프 체크와 슈퍼유저는 근무표 관리자 판정에 쓰지 않는다 | 근무표마다 관리자가 다르고, 관리 화면 권한(슈퍼유저)과 근무 운영 권한을 떼어 둔다 |
 | 2026-11-15 | 1단계 근무표 관리 화면은 보기만, 편집·추가·그룹 관리자 지정은 3단계. 관리자 지정은 사용자 화면의 그룹 칸 | `boards.it_board()` 가 code 로 IT 근무표를 찾아 잘못 고치면 화면·알림이 깨지고, 근무 정의 편집은 설계 4.3 검증과 함께 열어야 한다 |
+| 2026-11-15 | 로그인 유지 90일(로그인할 때부터, 요청마다 늘리지 않음), 글씨 크기 3단계는 기기마다(localStorage) | 휴대폰으로 가끔 보는 사람이 2주마다 다시 로그인하지 않게. 요청마다 늘리면 화면을 열 때마다 세션 DB 쓰기가 생긴다. 글씨 크기는 같은 사람도 PC·휴대폰에서 다르게 고른다 |
```

- [ ] **Step 11: 전체 테스트**

Run: `.venv/bin/pytest -W error -q`
Expected: 모두 통과(참고 1091 passed), 경고 0.

- [ ] **Step 12: 커밋**

```bash
git add duty/templates/duty/base.html config/settings.py duty/models.py duty/admin.py docs/ARCHITECTURE.md docs/PRINCIPLES.md \
  tests/test_ui_prefs.py tests/test_admin_department.py tests/test_admin_users.py tests/test_boards_generate.py tests/test_collect.py \
  tests/test_help.py tests/test_perms.py tests/test_views_collect.py tests/test_reasons.py tests/test_skip_days.py
git commit -m "feat: 글씨 크기 3단계([가] 버튼, 기기마다 기억), 로그인 유지 90일, 부서 managers 호환 property 제거"
```


---

### Task 8: 도움말·영상·문서

> 검증: Task 1~7 을 넣은 `feat/boards-phase2` 사본(1091 passed)에 아래 내용을 그대로 넣어 확인했다. 저장소는 고치지 않았다.
> - `.venv/bin/pytest -W error -q` → **1092 passed**(1091 + 새 1, `test_help_seed.py` 는 단언을 더한 것), 경고 0개. `makemigrations duty --check --dry-run` → "No changes detected in app 'duty'". `tests/test_alarm_texts_it.py` 는 고치지 않았고 그대로 통과한다(알림 코드를 건드리지 않음).
> - Step 2(`AssertionError: 근무표 이름`)·Step 6(`Holiday.DoesNotExist`)의 실패를 재현했다. Step 7 첫 판에서는 점심당번이 비었다. 옛 `SHIFTS` 의 새벽(8번째)이 늘 UI 부서(새벽 없음)에 떨어져 정상으로 바뀌었기 때문이다. 그래서 7번째와 8번째를 맞바꿨다(아래 코드에 반영).
> - Step 10 의 녹화 절차를 사본에서 그대로 돌려 `member.mp4` 를 뽑았다(664 프레임, 99초, 약 2MB). 프레임을 뽑아 [가] 누르기, 휴장일 "임시 휴장일", 날·주 메모, "이다라(휴가)", 점심당번 줄, 근무 변경 창의 "점심당번도 같이 넘기기"·[사유 저장] 자막을 눈으로 확인했다.
> - Step 13 은 같은 가짜 데이터로 member 로그인 화면(주간·월간·도움말)을 headless Chrome 1400·390px 로 찍었다. `scrollWidth` 는 1385/1400·390/390 으로 넘치지 않았다. 다크 모드와 관리자 [메모] 팝업은 사본에서 직접 보지 못했다(Step 13 에서 사람이 확인).
>
> 이 작업의 범위(설계 11절 "2단계" 마지막 줄, 13절 문서):
> - **도움말 글**: `duty/help.py` 의 `STEPS["member"]` 에 다섯 줄을 더한다. 글씨 크기, 근무표 고르기·보기 전용, 휴장일·메모·근무 없음, 점심당번·사유, 근무 변경 창의 "같이 넘기기"·[사유 저장]이다. manager·admin 글과 영상은 그대로 둔다. 입력 표는 3단계에서 또 바뀌므로 그때 함께 고친다. 메모 쓰기는 관리자 기능이지만 이번에는 member 글에 "관리자가 씁니다"로만 적는다.
> - **영상 가짜 데이터**(`tools/help_videos/seed.py`):
>   - 부서 점심 시각 11:30~12:30(0022 와 같은 값)
>   - `holidays.sync` 와 가짜 임시 휴장일. 오늘이 월~목이면 이번 주 금요일, 아니면 다음 주 금요일이다.
>   - 다음 회차의 근무 없음 날
>   - 오늘(주말이면 다음 평일)의 날 메모·주 메모·달 메모, 석식교대 한 명의 사유(휴가)
>   - 점심당번은 생성이 MD 새벽 근무자로 채운다.
>   - 출근표는 건너뛰는 날을 비운다(`boards.skip_dates`).
>   - 근무표 고르기·보기 전용은 근무표가 하나라 영상에 나오지 않는다. 시장운영실을 붙이는 4단계에 다시 녹화한다.
> - **자막**(`record.mjs` member):
>   - [가]를 세 번 눌러 보통으로 돌려 놓는다.
>   - 휴장일·메모 자막, 사유·점심당번 자막을 넣는다.
>   - 근무 변경 창에 "같이 넘기기"·[사유 저장] 자막을 넣는다.
>   - 누를 칸을 마지막 정상 칸(-1)에서 첫 바꿀 수 있는 정상 칸(0 = 오늘)으로 바꾼다. 금요일이 휴장일이면 빈 칸을 누르게 되기 때문이다.
> - **문서**: ARCHITECTURE(키와 성격·점심당번·건너뛰는 날·휴장일·메모·사유·보일 근무표·알림·캘린더·작업자), OVERVIEW(여러 근무표·범위·용어), OPERATIONS(2단계 업그레이드, 휴장일 절, 부서 점심 시각, 캘린더), PRINCIPLES 결정 기록 여섯 줄, DEVELOPMENT(영상 가짜 데이터). 1~6 작업이 미뤄 둔 문서 몫을 여기서 모두 한다(Task 7 의 글씨 크기·로그인 90일 문서는 이미 들어가 있다).
>
> 하지 않는 것: 앱 동작 변경, 마이그레이션(**다음 번호는 그대로 0023**), manager·admin 영상, 통계의 근무표 고르기, 설계 파일 삭제(4단계까지 끝난 뒤).

**Files:**
- Modify: `duty/help.py`(`STEPS["member"]` 다섯 줄)
- Modify: `tools/help_videos/seed.py`(전체 교체, 아래), `tools/help_videos/record.mjs`(`VIDEOS.member` 앞부분)
- Modify(바이너리): `duty/help_videos/member.mp4`(Step 10 에서 다시 녹화)
- Modify: `docs/ARCHITECTURE.md`, `docs/OVERVIEW.md`, `docs/OPERATIONS.md`, `docs/PRINCIPLES.md`, `docs/DEVELOPMENT.md`
- Test: `tests/test_help.py`(새 테스트 1개), `tests/test_help_seed.py`(import·`lunch` 픽스처·단언 추가)

**Interfaces:**
- Consumes:
  - (Task 1) `Holiday`(`Source.MANUAL`, `active`), `services.holidays.sync(today)`
  - (Task 2) `services.memos.save(user, board, scope, d, text, no_work=False, confirm=False)`
  - (Task 3) `services.boards.skip_dates(period)`
  - (Task 4) `services.changes.set_reason(user, board, d, member, reason)`, `.rsn` 클래스
  - (Task 5) `Department.lunch_start/lunch_end`, 생성의 점심당번 채우기, 테스트 픽스처 `lunch`, 폼 체크박스 "점심당번도 같이 넘기기"
  - (Task 6) 근무표 버튼 `.seg`(둘 이상일 때), "보기 전용"
  - (Task 7) `#size-btn`
  - 기존: `.hol`·`.memo`·`[name=set_reason]`·`#dlg` 선택자, 픽스처 `it_board`·`fixed_today`·`videos`·`people`
- Produces:
  - `duty.help.STEPS["member"]`: 15줄. 새 줄에 "근무표 이름"·"보기 전용"·"[가]"·"점심당번"·"(휴가)"·"사유"·"메모"·"근무 없음"·"휴장일"이 들어간다.
  - `tools/help_videos/seed.py` 가 만드는 가짜 데이터:
    - 부서 4개 모두 점심 11:30~12:30
    - `Holiday(source=manual, name="임시 휴장일")` 하나. 이번 회차 안의 평일이고 출근 행이 없다.
    - `Memo` 날·주·달 각 하나 이상, 다음 회차 안의 근무 없음 날 하나
    - 이번 회차 사유 행 하나(휴가), 이번 회차 `DutyAssignment(cell="lunch")`
    - `SHIFTS` 순서가 바뀌었다(7번째 = dawn).
  - 문서의 새 절: ARCHITECTURE "휴장일·메모·사유"·"보일 근무표", OPERATIONS "휴장일".
  - 마이그레이션 없음. **다음 번호 0023.**

- [ ] **Step 1: 도움말 글 실패 테스트를 쓴다**

`tests/test_help.py` 끝에 더한다:
```python


def test_steps_cover_phase2_member_features():
    """2단계 새 기능(근무표 고르기·글씨 크기·점심당번·사유·보기 전용·메모·휴장일)이 사용법 글에 있다."""
    from duty.help import STEPS
    text = "\n".join(STEPS["member"])
    for word in ("근무표 이름", "보기 전용", "[가]", "점심당번", "(휴가)", "사유", "메모", "근무 없음", "휴장일"):
        assert word in text, word
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_help.py -k phase2`
Expected: FAIL, `AssertionError: 근무표 이름`

- [ ] **Step 3: `STEPS["member"]` 에 다섯 줄을 더한다**

`duty/help.py` 에서 아래 줄 **바로 뒤에**:
```python
        "근무표는 이번 주 근무를 하루씩 보여 줍니다. 빨간 테두리가 오늘입니다. 휴대폰에서는 하루씩 세로로 나옵니다.",
```
네 줄을 넣는다:
```python
        "오른쪽 위 [가]를 누를 때마다 글씨가 크게 → 아주 크게 → 보통으로 바뀝니다. 고른 크기는 그 기기에 남습니다.",
        "근무표가 둘 이상이면 [주간]·[월간] 앞에 근무표 이름 버튼이 보이고, 눌러서 다른 근무표를 봅니다. 내 근무표가 아니면 제목 옆에 '보기 전용'이 붙고, 바꿀 수 없으며 필터 없이 전체가 보입니다.",
        "날짜 칸 맨 위에 휴장일 이름과 날 메모가 한 줄씩 보입니다. '근무 없음'인 날은 칸 전체가 메모 글로 덮입니다. 주 메모는 표 위(월간은 그 주 아래), 달 메모는 표 아래에 있고, 메모는 근무표 관리자가 씁니다.",
        "근무조 아래 '점심당번' 줄이 그날 점심당번입니다. 이름 뒤 작은 (휴가)·(출장)·(교육)은 사유로, 그날 근무로 치지 않습니다(알림·캘린더에서 빠짐).",
```
그리고 아래 줄 **바로 뒤에**:
```python
        "빼기만·넣기만은 목록 맨 끝의 '(없음)'을 고르면 되고, 저장 전에 한 번 더 묻습니다.",
```
한 줄을 넣는다:
```python
        "근무조 칸에서는 '점심당번도 같이 넘기기'(기본 켬)로 From의 점심당번을 To에게 함께 넘깁니다. 창 아래 [사유 저장]으로 휴가·출장·교육 사유를 붙이거나 뗍니다.",
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_help.py`
Expected: 모두 PASS. 기존 `test_steps_mention_month_view`·`test_help_page_has_text_steps` 도 통과한다.

- [ ] **Step 5: 영상 가짜 데이터 실패 테스트를 쓴다**

`tests/test_help_seed.py` 를 세 군데 고친다.

import 줄:
```python
from duty.models import ChangeLog, Department, DutyAssignment, Period, User
```
→
```python
from duty.models import ChangeLog, Commute, Department, DutyAssignment, Holiday, Memo, Period, User
```

함수 머리. `it_board` 픽스처가 0022 의 점심당번 정의를 지우므로 `lunch` 로 다시 켠다:
```python
def test_seed_uses_it_board_and_groups(it_board, fixed_today, capsys):
```
→
```python
def test_seed_uses_it_board_and_groups(it_board, lunch, fixed_today, capsys):
```

`now = Period.objects.get(name="이번 회차")` 줄 바로 뒤에 `nxt = Period.objects.get(name="다음 회차")` 한 줄을 넣는다. 함수 끝(`ChangeLog … == 1` 줄 뒤)에는 아래를 더한다:
```python

    # 2단계 화면 예시(member 영상): 휴장일·메모·사유·점심당번
    hol = Holiday.objects.get(source=Holiday.Source.MANUAL)
    assert hol.active and now.start_date <= hol.date <= now.end_date and hol.date.weekday() < 5
    assert not Commute.objects.filter(period=now, date=hol.date).exists()  # 건너뛰는 날은 비어 있다
    assert set(Memo.objects.values_list("scope", flat=True)) == {"day", "week", "month"}
    nowork = Memo.objects.get(no_work=True)
    assert nxt.start_date <= nowork.date <= nxt.end_date
    assert not Commute.objects.filter(period=nxt, date=nowork.date).exists()
    assert Commute.objects.filter(period=now).exclude(reason="").count() == 1
    assert DutyAssignment.objects.filter(period=now, cell="lunch").exists()
    assert Department.objects.exclude(lunch_start=None).count() == 4
```

- [ ] **Step 6: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_help_seed.py`
Expected: FAIL, `duty.models.Holiday.DoesNotExist: Holiday matching query does not exist.`

- [ ] **Step 7: `tools/help_videos/seed.py` 를 아래 내용으로 바꾼다**

바뀌는 점:
- `SHIFTS` 7·8번째를 맞바꾼다. 7번째는 MD 부서라 새벽이 남고, 그래서 점심당번이 생긴다. 옛 순서는 새벽이 늘 UI 부서에 떨어져 정상으로 바뀌었다.
- 부서에 점심 시각을 넣는다.
- 다음 회차를 이번 회차 출근표보다 먼저 만든다. 근무 없음 날 메모를 출근표 전에 달아야 `fill` 이 그날을 비우기 때문이다.
- 이번 회차 배포 뒤 사유와 메모를 단다.
- `d` 는 건너뛰는 날이 아닌 첫 날짜(오늘 이후)다. 오늘이 실제 공휴일이어도 행이 있는 날을 고른다.
- 데이터를 고치는 길은 다른 줄처럼 서비스(`memos`·`changes`·`holidays`)를 쓴다. 다만 `Holiday` 한 행은 관리 화면이 하는 일이라 ORM 으로 넣는다(seed 는 원래 `Commute.objects.create` 도 쓴다).

```python
"""사용법 영상 녹화용 가짜 데이터(실명 없음). record.mjs 가 빈 DUTY_DATA_DIR 에서 `manage.py shell < seed.py` 로 부른다.

계정(비밀번호 모두 Demo-pass-123): member(일반), manager(MEMS 출근표 입력 그룹), admin(슈퍼유저 + IT 근무표 관리 그룹)
2단계 화면 예시: 휴장일(이번 회차), 날·주·달 메모, 근무 없음 날(다음 회차), 사유(휴가) 한 명, 점심당번(생성이 새벽 근무자로 채움)
"""
from datetime import time, timedelta

from duty import perms
from duty.models import Commute, Department, Holiday, Period, User
from duty.services import alarm_settings, boards, changes, generate, holidays, memos, publish

PW = "Demo-pass-123"
NAMES = "김가나 이다라 박마바 최사아 정자차 강카타 조파하 윤가람 장나래 임다솜 한라온 오마루 서바다 신사랑 권아름 황자람".split()
FREE = "문하늘 배다온 노은별".split()  # 근무가 없는 사람(근무 바꾸기에서 넣을 수 있게)
SHIFTS = ["normal", "dinner", "normal", "dinner", "normal", "night", "dawn", "dinner"]  # 7번째(MD 부서) = 새벽 → 점심당번
LUNCH = (time(11, 30), time(12, 30))  # 운영 마이그레이션 0022 가 IT 부서에 넣는 점심 시각과 같다

it = boards.it_board()  # 마이그레이션이 빈 DB 에도 만들어 둔 IT 당번표
depts = {code: Department.objects.create(code=code, name=code, shifts=sh, board=it, order=i, lunch_start=LUNCH[0], lunch_end=LUNCH[1])
         for i, (code, sh) in enumerate([
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
    skip = boards.skip_dates(period)  # 휴장일·근무 없음 날은 비운다(입력 표가 그날 행을 잠그는 것과 같게)
    for x in period.dates():
        if x in skip:
            continue
        for i, u in enumerate(who):
            sh = SHIFTS[i % len(SHIFTS)]
            if "dawn" not in u.department.shift_keys() and sh == "dawn":
                sh = "normal"
            Commute.objects.create(period=period, date=x, member=u, shift=sh)


today = perms.today()
mon = today - timedelta(days=today.weekday())
now = Period.objects.create(board=it, name="이번 회차", start_date=mon, end_date=mon + timedelta(days=11),
                            status=Period.Status.CLOSED)
nxt = Period.objects.create(board=it, name="다음 회차", start_date=mon + timedelta(days=14), end_date=mon + timedelta(days=25),
                            status=Period.Status.COLLECTING)
holidays.sync(today)  # 실제 공휴일(작업자가 하는 일)
# 가짜 임시 휴장일: 오늘이 월~목이면 이번 주 금요일, 아니면 다음 주 금요일(영상 첫 화면 또는 [월간]에 보이게)
Holiday.objects.update_or_create(date=mon + timedelta(days=4 if today.weekday() < 4 else 11),
                                 defaults={"name": "임시 휴장일", "source": Holiday.Source.MANUAL, "active": True})
memos.save(admin, it, "day", nxt.start_date + timedelta(days=2), "부서 워크숍", no_work=True)  # 근무 없음 날
fill(now, workers)
generate.run_generation(now, seed=1, by=admin)  # 장중관제 + 점심당번(새벽 근무자)
publish.publish(now, mon, by=admin)
skip = boards.skip_dates(now)
d = next(x for x in now.dates() if x >= today and x not in skip)  # 오늘(주말이면 다음 평일)
row = Commute.objects.filter(period=now, date=d, shift="normal").exclude(member__in=[member, manager]).first()
changes.change_cell(admin, it, d, "normal", row.member, people[-1])  # 바뀐 칸 표시용
off = Commute.objects.filter(period=now, date=d, shift="dinner").exclude(member__in=[member, manager]).first()
changes.set_reason(admin, it, d, off.member, "휴가")  # 이름 뒤 (휴가)
memos.save(admin, it, "day", d, "분기 보고 마감")
memos.save(admin, it, "week", d, "목요일 오후 전산 점검")
memos.save(admin, it, "month", d, "본부 점심: 김가나, 이다라")

fill(nxt, [u for u in workers if u.department.code != "MEMS"])  # MEMS 는 담당자 영상에서 입력
mems = [u for u in workers if u.department.code == "MEMS"]
nskip = boards.skip_dates(nxt)
for x in [x for x in nxt.dates() if x not in nskip][:-1]:  # 마지막 하루만 비워 둔다
    for i, u in enumerate(mems):
        Commute.objects.create(period=nxt, date=x, member=u, shift=SHIFTS[i % len(SHIFTS)])
# 알림 화면이 "봇 미설정" 안내 대신 평소 모습으로 보이게(가짜 값, 녹화 중 실제 발송·연결은 하지 않는다)
conf = alarm_settings.current()
conf.telegram_bot_token = "1" * 10 + ":" + "DEMO" + "x" * 31
conf.telegram_bot_username = "nxt_duty_demo_bot"
alarm_settings.save(conf)
print("seeded")
```

- [ ] **Step 8: 통과와 전체 테스트를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_help_seed.py tests/test_help.py`
Expected: 모두 PASS

Run: `.venv/bin/pytest -W error -q`
Expected: 모두 PASS(사본 기준 1092 passed), 경고 0개

- [ ] **Step 9: member 영상 자막을 고친다**

`tools/help_videos/record.mjs` 의 `VIDEOS.member` 에서 아래 덩어리를 찾는다:
```js
    await s.say('근무표: 이번 주 근무를 하루씩 봅니다.\n빨간 테두리가 오늘입니다.', 3000);
    await s.scroll(700, 1500);
    await s.say('굵은 기울임 글씨는 배포 뒤에 바뀐 근무,\n취소선은 빠진 사람입니다.', 3000);
    await s.say('바꿀 칸을 누릅니다.', 1200);
    await s.tap('a.cell[hx-get*="/normal/"]', 1600, -1);
    await s.say('From(이 칸 사람)과 To(바꿀 사람)를 고르면\n두 사람의 근무를 서로 맞바꿉니다.', 3400);
    await s.pick('#dlg select[name=after]', '');
    await s.say('To 목록 괄호 안이 그 사람의 그날 근무입니다.\n근무가 없는 사람이면 From 대신 들어갑니다.', 3400);
    await s.tap('#dlg form button', 1800);
```
아래로 바꾼다(그 뒤 줄은 그대로). `#dlg form button` 의 첫 번째는 변경 폼의 [저장]이다. [사유 저장]은 두 번째 폼에 있다.
```js
    await s.say('근무표: 이번 주 근무를 하루씩 봅니다.\n빨간 테두리가 오늘입니다.', 3000);
    await s.tap('#size-btn', 900);
    await s.say('오른쪽 위 [가]를 누를 때마다 글씨가\n크게 → 아주 크게 → 보통으로 바뀝니다.', 2200);
    await s.tap('#size-btn', 1500);
    await s.tap('#size-btn', 900);  // 보통으로 돌려 놓는다
    // seed.py: 휴장일(이번 주 또는 다음 주 금요일), 오늘(주말이면 다음 평일)의 날 메모·사유·바뀐 칸·점심당번
    await s.ev(`(document.querySelector('.hol') || document.querySelector('.memo')).scrollIntoView({block: 'center', behavior: 'smooth'})`); await sleep(1200);
    await s.say('날짜 칸 맨 위에 휴장일 이름과 날 메모가 보입니다.\n주 메모는 표 위, 달 메모는 표 아래에 있습니다.', 3400);
    await s.ev(`document.querySelector('.rsn').scrollIntoView({block: 'center', behavior: 'smooth'})`); await sleep(1200);
    await s.say('이름 뒤 (휴가)는 그날 근무로 치지 않는 사람입니다.\n근무조 아래 점심당번 줄이 그날 점심당번입니다.', 3400);
    await s.say('굵은 기울임 글씨는 배포 뒤에 바뀐 근무,\n취소선은 빠진 사람입니다.', 3000);
    await s.say('바꿀 칸을 누릅니다.', 1200);
    await s.tap('a.cell[hx-get*="/normal/"]', 1600);  // 첫 번째 바꿀 수 있는 날(오늘)
    await s.say('From(이 칸 사람)과 To(바꿀 사람)를 고르면\n두 사람의 근무를 서로 맞바꿉니다.', 3400);
    await s.pick('#dlg select[name=after]', '');
    await s.say('To 목록 괄호 안이 그 사람의 그날 근무입니다.\n근무가 없는 사람이면 From 대신 들어갑니다.', 3400);
    await s.say('\'점심당번도 같이 넘기기\'(기본 켬)로\nFrom의 점심당번을 To에게 함께 넘깁니다.', 3000);
    await s.ev(`document.querySelector('#dlg [name=set_reason]').scrollIntoView({block: 'center', behavior: 'smooth'})`); await sleep(1000);
    await s.say('창 아래 [사유 저장]으로 휴가·출장·교육 사유를 붙입니다.\n사유가 붙으면 알림·캘린더에서 빠집니다.', 3400);
    await s.tap('#dlg form button', 1800);
```

Run: `node --check tools/help_videos/record.mjs`
Expected: 출력 없음(문법 통과)

- [ ] **Step 10: member 영상을 다시 녹화한다(docs/DEVELOPMENT.md "사용법 영상 다시 만들기" 그대로, 개발 PC)**

새 빈 DB 에서 뽑는다. 지금 `data/` 와 `.env` 는 건드리지 않는다(`DUTY_ENV_FILE=` 로 `.env` 를 읽지 않음). `requirements.lock` 으로 `holidays` 가 깔려 있어야 한다(Task 1).
```bash
W=$(mktemp -d)
python3 -m venv $W/ff && $W/ff/bin/pip install imageio-ffmpeg
FF=$($W/ff/bin/python -c "import imageio_ffmpeg as i; print(i.get_ffmpeg_exe())")
export DUTY_ENV_FILE= DUTY_DEBUG=1 DUTY_DATA_DIR=$W/data
.venv/bin/python manage.py migrate && .venv/bin/python manage.py shell < tools/help_videos/seed.py   # 끝에 "seeded"
.venv/bin/python manage.py runserver 127.0.0.1:8795 --noreload & SRV=$!
node tools/help_videos/record.mjs http://127.0.0.1:8795 $W $FF member   # "member … frames … s … KB"
kill $SRV
```
Expected: `duty/help_videos/member.mp4` 가 바뀐다(사본 기준 약 100초·2MB).

녹화 결과는 프레임을 뽑아 눈으로 본다. 아래 시각은 사본 기준이고, 요일에 따라 조금 다르다.
```bash
for t in 15 22 28 45 50; do $FF -loglevel error -y -ss $t -i duty/help_videos/member.mp4 -frames:v 1 $W/s$t.png; done
```
확인할 것:
- [가]가 눌려 글씨가 커졌다가 보통으로 돌아온다.
- 날짜 칸 맨 위에 "임시 휴장일"(빨간 글씨)과 "분기 보고 마감", 표 위에 "주 메모"가 보인다.
- "(휴가)"가 붙은 이름과 "점심당번" 줄이 보인다.
- 근무 변경 창에 "점심당번도 같이 넘기기"와 [사유 저장]이 보인다.
- 자막이 버튼을 가리지 않는다.

다 보면 지운다: `rm -rf $W`.

manager·admin 영상은 다시 뽑지 않는다. manager 영상만 다시 뽑으려면 새 데이터에서 `manager admin` 을 함께 뽑는다. seed 가 다음 회차에 근무 없음 날을 넣어도, 담당자 영상이 쓰는 마지막 날짜 행은 여전히 비어 있다.

- [ ] **Step 11: 커밋(도움말·영상)**

```bash
git add duty/help.py duty/help_videos/member.mp4 tools/help_videos/seed.py tools/help_videos/record.mjs tests/test_help.py tests/test_help_seed.py
git commit -m "feat: 도움말 글·member 영상에 근무표 고르기·글씨 크기·점심당번·사유·메모·휴장일"
```

- [ ] **Step 12: 문서를 고친다(28곳)**

아래 순서대로 "찾을 글"을 찾아 "바꿀 글"로 바꾼다. 찾을 글은 파일 안에 한 번씩만 있다(사본에서 확인). 마크다운 덩어리 안의 줄은 파일 그대로다.

1. `docs/ARCHITECTURE.md` — 찾을 글:

```markdown
작업자 run_worker(duty-worker) ── 1분마다: 백업 → 상태 점검 → 알림 발송(텔레그램·웹 푸시)
```

   바꿀 글:

```markdown
작업자 run_worker(duty-worker) ── 1분마다: 휴장일 채우기 → 백업 → 상태 점검 → 알림 발송(텔레그램·웹 푸시)
```

2. `docs/ARCHITECTURE.md` — 찾을 글:

```markdown
| `duty/shifts.py` | 칸 키 목록(`KEYS`)과 키의 성격, 근무 정의 목록(defs)을 받는 헬퍼, 날짜 계산 | 없음 |
```

   바꿀 글:

```markdown
| `duty/shifts.py` | 칸 키 목록(`KEYS`)과 키의 성격(`kind`), 사유 목록(`REASONS`), 근무 정의 목록(defs)을 받는 헬퍼, 날짜 계산 | 없음 |
| `duty/market_days.py` | 해마다 휴장일 계산(`holidays_for(year)`: 공휴일 라이브러리 `holidays` + 12/31 "연말 휴장") | 없음 |
```

3. `docs/ARCHITECTURE.md` — 찾을 글:

```markdown
| `duty/admin.py` | Django 관리 화면(사용자·부서·근무표와 근무 정의 보기·그룹·계정 발급·알림 설정) | |
```

   바꿀 글:

```markdown
| `duty/admin.py` | Django 관리 화면(사용자·부서(점심 시각)·근무표와 근무 정의 보기·그룹·휴장일·계정 발급·알림 설정) | |
```

4. `docs/ARCHITECTURE.md` — 찾을 글:

```markdown
      ─< Period ─< Commute(날짜·멤버·출근조)         Period ─< PeriodEvent(상태 기록)
                ─< DutyAssignment(날짜·칸·멤버)      Period ─< ChangeLog(근무 변경 기록)
```

   바꿀 글:

```markdown
      ─< Period ─< Commute(날짜·멤버·출근조·사유)    Period ─< PeriodEvent(상태 기록)
                ─< DutyAssignment(날짜·칸·멤버)      Period ─< ChangeLog(근무 변경 기록, 사유 전후)
      ─< Memo(날·주·달 메모, 근무 없음)
Holiday(휴장일, 모든 근무표 공통)
```

5. `docs/ARCHITECTURE.md` — 찾을 글:

```markdown
칸(cell) 키는 코드에 고정된 목록 `shifts.KEYS`(dawn, normal, dinner, slot0~slot9, night)이고
```

   바꿀 글:

```markdown
칸(cell) 키는 코드에 고정된 목록 `shifts.KEYS`(dawn, normal, dinner, slot0~slot9, night, lunch)이고
```

6. `docs/ARCHITECTURE.md` — 찾을 글:

```markdown
- **키 글자가 성격을 정한다**: `dawn`·`normal`·`dinner`·`night` = 근무조(`SHIFT_KEYS`, 한 사람 하루 하나, DB 제약), `slot0`~`slot9` = 장중관제(`SLOT_KEYS`, 자동 생성, 칸당 1명, 묶음 키 `slots`·이름 "장중관제"·짧은 이름 "관제").
```

   바꿀 글:

```markdown
- **키 글자가 성격을 정한다**(`shifts.kind`): `dawn`·`normal`·`dinner`·`night` = 근무조(`SHIFT`, `SHIFT_KEYS`, 한 사람 하루 하나, DB 제약), `slot0`~`slot9` = 장중관제(`SLOT`, `SLOT_KEYS`, 자동 생성, 칸당 1명, 묶음 키 `slots`·이름 "장중관제"·짧은 이름 "관제"), `lunch` = 점심당번(`SOLO`, 혼자인 당번 칸, 인원 제한 없음, 정의에 시각이 없다). 같은 성격끼리만 맞교환한다.
```

7. `docs/ARCHITECTURE.md` — 찾을 글:

```markdown
- 화면 순서: 근무조(시작 시각 순) → 장중관제(키 순).
```

   바꿀 글:

```markdown
- 화면 순서: 근무조(시작 시각 순) → 점심당번 → 장중관제(키 순).
- **점심당번**: 생성(`generate._fill_lunch`)이 날짜마다 가장 이른 근무조(IT = 새벽)에 사유 없이 출근한 사람 전원을 넣는다(무작위 없음, 아무도 없는 날은 비우고 회차 화면에 경고). 시각은 정의가 아니라 부서(`Department.lunch_start`·`lunch_end`, 둘 다 있거나 둘 다 없음)에 두고 개인 알림·캘린더만 쓴다(IT 4부서 11:30~12:30, 마이그레이션 0022). 0022 는 그날(포함) 이후의 배포됨·생성됨 회차와 `publish_undo` 의 새벽 행에도 점심당번을 채웠다. 근무 변경 창의 "점심당번도 같이 넘기기"(기본 켬)가 근무조를 넘길 때 From 의 점심당번도 To 에게 넘긴다(`changes._carry_lunch`, 기록은 `cell="lunch"`).
```

8. `docs/ARCHITECTURE.md` — 찾을 글:

```markdown
배포 때 지운 행은 `publish_undo`에 `["c", 회차, 날짜, 멤버, 출근조]`(출근표)·`["a", 회차, 날짜, 멤버, "slotN"]`(배정)로 보관한다.
```

   바꿀 글:

```markdown
점심당번도 같은 표(`cell="lunch"`, 하루 여러 명)다. 배포 때 지운 행은 `publish_undo`에 `["c", 회차, 날짜, 멤버, 출근조, 사유]`(출근표, 사유 칸이 없는 옛 다섯 칸 행도 읽는다)·`["a", 회차, 날짜, 멤버, 칸]`(배정)로 보관한다.
```

9. `docs/ARCHITECTURE.md` — 찾을 글:

```markdown
- 대상 날짜는 회차 기간의 월~금(휴장일 처리 없음).
```

   바꿀 글:

```markdown
- 대상 날짜는 회차 기간의 월~금이다. 그중 **건너뛰는 날**(`boards.skip_reasons(period)`·`skip_dates`)은 만드는 도구가 비워 둔다: 입력 표(그날 행 잠금, 까닭 표시), CSV(그날 이름이 있으면 오류, 내려받기는 빈 줄), 생성(관제·점심당번), 빈 날 검사(`periods.missing_dates`·입력 현황). 건너뛰는 날 = 근무 없음 날 메모(늘) ∪ 켜진 휴장일(`Period.skip_holidays` 인 회차만. 2단계 마이그레이션 전 회차는 거짓, 새 회차는 참). 이미 들어 있는 행은 지우지 않고 보인다(휴장일을 나중에 추가했을 때).

## 휴장일·메모·사유

- **휴장일**(`Holiday`, 모든 근무표 공통): `services/holidays.sync(today)` 가 (가장 이른 회차의 해, 올해 중 이른 해)~(내년, 가장 늦은 회차의 해 중 늦은 해)의 `market_days.holidays_for` 날짜 중 표에 없는 것만 `source=auto` 로 넣는다(있는 행·끈 행은 건드리지 않고, 라이브러리에서 사라져도 지우지 않는다). 부르는 곳은 작업자 매 바퀴 맨 앞, 회차 저장(`periods.save_draft`) 뒤, 생성 — 화면 GET 은 부르지 않는다. 슈퍼유저는 관리 화면 "휴장일"에서 임시공휴일을 추가(`manual`)하거나 끈다(`active`, 지우기는 막음). 읽기는 `holidays.closed(start, end)`(켜진 것만, 주말 포함). 날짜 칸 맨 위에 이름이 보이고(`.hol`), 영업일 기준 알림(`alarms/schedule.bizdays_back`)은 켜진 휴장일을 영업일에서 뺀다(회차와 무관). 휴장일을 고쳐 발송일이 바뀌어도 이미 보낸 알림은 다시 보내지 않는다.
- **메모**(`Memo`, `services/memos.py`): (근무표, 범위, 날짜)에 하나. 범위는 날(`day`)·주(`week`, 월요일에 저장)·달(`month`, 1일에 저장). 쓰기는 그 근무표 관리 그룹만(`[메모]` 팝업). 날 메모는 날짜 칸 맨 위 한 줄, 주 메모는 표 위(월간은 그 주 행 아래), 달 메모는 표 아래. 날 메모의 **근무 없음**은 그날 칸 전체를 글로 덮는다: 저장할 때 배정이 있으면 확인(`confirm`)을 받고 그날의 모든 배정을 지운다(배포 회차 행은 지운 것마다 `ChangeLog`, 변경 알림은 평소처럼. 배포 전 회차 행은 기록 없이). 그날은 근무 변경이 막히고(`changes._owner`), 배포 취소로 되살아나지도 않는다(`publish._restorable`). 메모를 지우거나 근무 없음을 끄면 빈 날이 되고 넣기로 채운다.
- **사유**(`Commute.reason`: 휴가·출장·교육, 빈 값 = 없음): 사유가 붙은 근무조 배정은 그날 근무로 치지 않는다 — 개인 알림·캘린더·점심당번 채우기·관제 생성 후보·통계(새벽·야간 횟수, 배정 횟수 모집단)에서 빠지고, 근무표·보고서에는 "이름(휴가)"로 보인다(변경 내역을 꺼도 보임). 입력 표·CSV 는 "이름(휴가)"로 읽고 쓰고(`csv_io.split_reason`·`join_reason`), 그래서 이름이 (휴가)·(출장)·(교육)으로 끝나는 계정은 만들 수 없다(마이그레이션 0020 도 그런 계정이 있으면 멈춘다). 근무 변경 창의 [사유 저장]은 `changes.set_reason`: 사람은 그대로라 기록은 before = after 에 `reason_before`·`reason_after` 를 남기고, 변경 알림은 없다(이력에만 "가 → 가(휴가)"). 그 사람이 그날 당번 칸에 남아 있으면 빼지 않고 경고만 한다. 맞교환에서는 사유가 사람을 따라간다.
```

10. `docs/ARCHITECTURE.md` — 찾을 글:

```markdown
통계 화면은 그중 id가 가장 작은 근무표를 보여 주고, 없으면 403이다(근무표 고르기는 2단계) |
```

   바꿀 글:

```markdown
통계 화면은 그중 id가 가장 작은 근무표를 보여 주고, 없으면 403이다(통계의 근무표 고르기는 관제 있는 근무표가 둘이 되면) |
```

11. `docs/ARCHITECTURE.md` — 찾을 글:

```markdown
- 모든 변경은 ChangeLog(`before`/`after`)에 남는다. 화면은 이를 이어 붙여 교체 `A>B`, 추가 `+B`, 제거(취소선)로 그린다. 동시 수정은 먼저 저장한 쪽이 이긴다.
```

   바꿀 글:

```markdown
- 점심당번 칸은 넣기·빼기·교체만 한다(맞교환 없음). 근무조 칸에서는 사유([사유 저장])와 "점심당번도 같이 넘기기"가 함께 보인다.
- 모든 변경은 ChangeLog(`before`/`after`)에 남는다. 화면은 이를 이어 붙여 교체 `A>B`, 추가 `+B`, 제거(취소선)로 그린다. 사유만 바뀐 기록(before = after)은 이어 붙이지 않는다. 동시 수정은 먼저 저장한 쪽이 이긴다.

## 보일 근무표

- 근무표 화면(`/`)의 근무표 = `?board=<code>` → 마지막에 본 근무표(`RosterPref.board`) → 내 근무표(`boards.home(user)`: 내 부서의 근무표 → 내가 관리하는 첫 근무표 → 첫 근무표). 근무표가 둘 이상이면 [주간]·[월간] 앞에 근무표 버튼(`.seg`, id 순)이 보인다. `RosterPref.board` 는 `/` 에서만 읽고 쓴다: `/day/`·`/cell/`·`/memo/` 는 `?board=` 가 없으면 늘 내 근무표라, `?board=` 없는 알림 링크나 변경 POST 가 마지막에 본 남의 근무표로 가지 않는다. 없는 코드는 404.
- 링크(날짜 이동·필터 폼·htmx·변경 POST·알림 링크)는 공통 함수 `boards.board_query(user, board)` 로 만든다: 보이는 근무표가 내 근무표가 아닐 때만 `?board=<code>`, 내 근무표면 빈 글자라 IT 사람의 주소·알림 링크(`Due.url`, hash 와 무관)는 1단계 그대로다.
- **보기 전용** = 내 근무표도 아니고 그 근무표의 관리자도 아님: 제목 옆 "보기 전용", 칸 링크·[바꾸기] 숨김(서버도 `assert_can_edit` 로 막는다). 내 근무표가 아니면(관리자라도) 부서·유형·스케줄 필터 없이 전체를 보이고 저장된 내 필터를 바꾸지 않는다(`prefs.resolve(..., mine=False)`).
- 이력(`/changes/`)은 근무표 열과 `?board=` 필터가 있다(관리하는 근무표가 둘 이상일 때만 고르기가 보인다).
```

12. `docs/ARCHITECTURE.md` — 찾을 글:

```markdown
- 사용자가 규칙(`AlarmRule`)을 만든다.
```

   바꿀 글:

```markdown
- 점심당번 문구는 "혼자인 당번 칸" 틀이다: 개인 알림 "점심당번 11:30~12:30"(부서 시각이 없으면 "점심당번", 그때는 시각 기준 규칙에서 빠지고 날짜 기준 규칙은 다음 날 00:00 에 만료), 보고서는 기존 줄 **뒤에** "점심당번 가, 나"(발송 창·만료·`same_day_notice` 계산에서는 뺀다. 점심당번만 고른 보고서 규칙은 저장 때 막는다), 변경 알림 위치 "점심당번". 사유가 있는 배정은 개인 알림에서 빠지고(취소 알림도 없음) 보고서에는 "가(출장)", 요약 인원은 사유 없는 사람만 센다.
- 사용자가 규칙(`AlarmRule`)을 만든다.
```

13. `docs/ARCHITECTURE.md` — 찾을 글:

```markdown
- 넣을 근무는 사용자가 고른다(`CalendarFeed.shifts`, 내 근무표의 근무조와 장중관제. IT = 새벽·정상·석식교대·야간·장중관제, 빈 목록 = 전부). 주소는 그대로이고 재발급해도 고른 값은 남는다.
```

   바꿀 글:

```markdown
- 넣을 근무는 사용자가 고른다(`CalendarFeed.shifts`, 내 근무표의 근무조와 장중관제·점심당번. 빈 목록 = 전부). 주소는 그대로이고 재발급해도 고른 값은 남는다.
- 점심당번은 부서 점심 시각이 있을 때만 일정 하나("점심당번", UID `날짜-lunch-pk`). 사유가 있는 날의 근무조 일정은 빠진다.
```

14. `docs/ARCHITECTURE.md` — 찾을 글:

```markdown
- `manage.py run_worker`: 1분마다 **백업**(하루 한 번 `DUTY_BACKUP_HOUR` 이후)
```

   바꿀 글:

```markdown
- `manage.py run_worker`: 1분마다 **휴장일 채우기**(`holidays.sync`, 없는 날짜만 넣어 가볍다) → **백업**(하루 한 번 `DUTY_BACKUP_HOUR` 이후)
```

15. `docs/OVERVIEW.md` — 찾을 글:

```markdown
IT 부서는 매일 출근조(새벽·정상·석식교대·야간)와 장중관제 당번(08:30~18:00, 10칸)을 돌린다. 원래는 구글 시트 + Apps Script 로 관리했다.
```

   바꿀 글:

```markdown
IT 부서는 매일 출근조(새벽·정상·석식교대·야간)와 장중관제 당번(08:30~18:00, 10칸), 점심당번을 돌린다. 원래는 구글 시트 + Apps Script 로 관리했다. 시장관리본부 시장운영실(근무조 3개, 엑셀로 관리)도 같은 앱에서 근무표 하나로 운영할 예정이다(근무표마다 회차·배포·알림이 따로 돈다).
```

16. `docs/OVERVIEW.md` — 찾을 글:

```markdown
| 멤버 | 근무표에 들어가는 모든 사람(약 40명) | 근무표·내 근무 보기, 오늘·미래 근무 바꾸기, 알림·캘린더 설정 |
```

   바꿀 글:

```markdown
| 멤버 | 근무표에 들어가는 모든 사람(약 40명) | 모든 근무표 보기(남의 근무표는 보기 전용), 내 근무표의 오늘·미래 근무 바꾸기·사유 붙이기, 알림·캘린더 설정 |
```

17. `docs/OVERVIEW.md` — 찾을 글:

```markdown
| 관리자(근무표 관리 그룹) | IT 운영 담당 | 회차 만들기·취합·생성·배포·배포 취소, 지난 날짜 수정, 통계·이력 |
```

   바꿀 글:

```markdown
| 관리자(근무표 관리 그룹) | IT 운영 담당 | 회차 만들기·취합·생성·배포·배포 취소, 지난 날짜 수정, 메모(근무 없음 포함), 통계·이력 |
```

18. `docs/OVERVIEW.md` — 찾을 글:

```markdown
| 슈퍼유저 | 관리자 중 1~2명 | 관리 화면: 계정 발급·부서·입력 담당자·관리자 지정(사용자의 그룹 칸)·근무표 보기·로그인 잠금 해제·알림 설정 |
```

   바꿀 글:

```markdown
| 슈퍼유저 | 관리자 중 1~2명 | 관리 화면: 계정 발급·부서(점심 시각)·입력 담당자·관리자 지정(사용자의 그룹 칸)·근무표 보기·휴장일·로그인 잠금 해제·알림 설정 |
```

19. `docs/OVERVIEW.md` — 찾을 글:

```markdown
- 장중관제 자격: 개발자이고 그날 그 시간대의 자격 출근조(08:30 = 정상, 17:00 = 석식교대, 나머지 = 둘 다)에 있어야 한다.
```

   바꿀 글:

```markdown
- 장중관제 자격: 개발자이고 그날 그 시간대의 자격 출근조(08:30 = 정상, 17:00 = 석식교대, 나머지 = 둘 다)에 있어야 한다.
- 점심당번은 생성할 때 그날 새벽 근무자로 채운다. 휴장일과 "근무 없음" 날은 입력 표·생성이 건너뛴다.
```

20. `docs/OVERVIEW.md` — 찾을 글:

```markdown
**하는 것**: 회차·출근표 취합(표·CSV), 장중관제 자동 생성, 배포·배포 취소, 근무 변경·맞교환과 기록, 통계, 텔레그램·웹 푸시 알림, 캘린더(ICS) 구독, 권한별 도움말 영상.
```

   바꿀 글:

```markdown
**하는 것**: 여러 근무표, 회차·출근표 취합(표·CSV), 장중관제·점심당번 자동 생성, 배포·배포 취소, 근무 변경·맞교환과 기록, 사유(휴가·출장·교육), 메모(날·주·달, 근무 없음), 휴장일(공휴일 자동 + 관리 화면), 통계, 텔레그램·웹 푸시 알림, 캘린더(ICS) 구독, 글씨 크기, 권한별 도움말 영상.
```

21. `docs/OVERVIEW.md` — 찾을 글:

```markdown
- 휴장일·공휴일 처리: 대상 날짜는 회차 기간의 월~금 전부다.
```

   바꿀 글:

(빈 글 = 그 줄을 지운다)

22. `docs/OVERVIEW.md` — 찾을 글:

```markdown
| 칸 | 출근조 4개 + 장중관제 10개 = 하루 14칸 |
```

   바꿀 글:

```markdown
| 칸 | 출근조 4개 + 장중관제 10개 + 점심당번 = 하루 15칸 |
| 근무표 | 회차·부서·근무 정의(이름·시각)를 가진 단위. IT 당번표가 첫 근무표 |
| 점심당번 | 그날 점심 자리를 지키는 당번. 가장 이른 근무조를 따라가고 인원 제한이 없다. 점심 시각은 부서마다 |
| 사유 | 이름 뒤 (휴가)·(출장)·(교육). 붙으면 그날 근무로 치지 않는다 |
| 휴장일 | 공휴일·대체공휴일·선거일·임시공휴일·12/31. 모든 근무표 공통 |
| 근무 없음 | 근무표 하나만 쉬는 날. 날 메모로 적고 그날 칸 전체를 글로 덮는다 |
```

23. `docs/OPERATIONS.md` — 찾을 글:

```markdown
- 부서 입력 담당자는 부서 화면의 "입력 담당자"에서 지정한다(
```

   바꿀 글:

```markdown
- 점심 시각은 부서 화면의 "점심 시작"·"점심 끝"(둘 다 넣거나 둘 다 비움). 점심당번 개인 알림·캘린더에 쓰이고, 비우면 점심당번 알림은 날짜 기준 규칙(전날 18시 등)으로만 가고 캘린더 일정은 생기지 않는다.
- 부서 입력 담당자는 부서 화면의 "입력 담당자"에서 지정한다(
```

24. `docs/OPERATIONS.md` — 찾을 글:

```markdown
- nginx 를 켜 둔 서버는 이 묶음을 마친 뒤 아래 "nginx → 평소 운영"의 **업그레이드 뒤 nginx 설정 갱신**을 한다(대부분 "같음"으로 끝난다).
```

   바꿀 글:

```markdown
- **근무표 일반화 2단계로 올릴 때 (한 번, 되돌리기는 업그레이드 전 백업 복원으로만)**: `pip install -r requirements.lock` 이 휴장일 라이브러리 `holidays` 를 새로 깐다. `migrate` 가 사유·메모·휴장일 표, IT 점심당번 정의, IT 부서 점심 시각 11:30~12:30 을 넣고, 업그레이드한 날(포함) 이후의 배포됨·생성됨 회차에서 새벽 근무자를 점심당번으로 채운다(기록·알림 없음). 기존 회차는 휴장일을 건너뛰지 않는다(이름만 보인다). 이후 새로 만드는 회차부터 건너뛴다.
  - 업그레이드 전 확인(읽기 전용): 이름이 (휴가)·(출장)·(교육)으로 끝나는 계정이 있으면 `migrate` 가 멈춘다(0020). 아래가 그런 계정의 아이디를 보여 준다(없으면 아무것도 안 나온다). 있으면 업그레이드 전에 관리 화면에서 이름을 바꾼다. 업그레이드 중에 멈췄으면 위 "롤백"대로 되돌린 뒤 바꾸고 처음부터 다시 한다.
    `sudo -u duty sqlite3 -readonly data/db.sqlite3 "SELECT username FROM duty_user WHERE name LIKE '%(휴가)' OR name LIKE '%(출장)' OR name LIKE '%(교육)';"`
  - `migrate` 를 거꾸로(`migrate duty 0021` 등) 돌려 되돌리지 않는다. 점심당번 행이 하나라도 생기면 0022 가 "백업으로 복원" 오류로 멈춘다. 문제가 생기면 위 "롤백"(코드 되돌리기 + `restore`)만 쓴다.
  - **IT 보고서 알림이 한 번 다시 나간다**: 보고서 끝에 "점심당번 …" 줄이 붙어 내용이 바뀌므로, 업그레이드한 날 이미 받은 보고서 중 발송 창이 아직 열린 것이 한 번 더 간다(예정된 동작). 개인 알림 문구는 그대로다(점심당번 알림은 새로 생긴다).
  - 작업자가 켜지면 첫 바퀴에 휴장일을 채운다. 관리 화면 "휴장일"에 올해·내년 공휴일과 12/31 이 보이면 된다. 아래 "휴장일"대로 임시공휴일을 더한다.
- nginx 를 켜 둔 서버는 이 묶음을 마친 뒤 아래 "nginx → 평소 운영"의 **업그레이드 뒤 nginx 설정 갱신**을 한다(대부분 "같음"으로 끝난다).
```

25. `docs/OPERATIONS.md` — 찾을 글:

```markdown
## 캘린더 구독 (ICS)
```

   바꿀 글:

```markdown
## 휴장일

- 관리 화면 "휴장일"(슈퍼유저): 모든 근무표 공통. 작업자가 매 바퀴 공휴일 라이브러리로 올해·내년(회차가 있는 해까지)의 공휴일과 12/31 "연말 휴장"을 채운다(출처 "자동"). 이미 있는 날짜는 건드리지 않는다.
- 임시공휴일: [휴장일 추가]로 날짜·이름을 넣는다(출처 "직접 추가"). 휴장일이 아닌 날은 목록에서 "휴장"을 끄고 저장한다. 지우기는 없다(지운 자동 휴장일이 다음 바퀴에 다시 생기므로 끈다). 날짜를 잘못 넣었으면 그 행을 끄고 새로 추가한다.
- 바꾼 휴장일은 배포 전 회차의 입력 표(다음에 열 때)와 생성(돌릴 때)에 반영된다. 이미 배정된 근무는 지우지 않는다: 휴장일에 사람이 들어 있으면 근무 변경 "빼기만"으로 뺀다. 이미 배포된 빈 휴장일을 끄면 그날은 빈 날이라 "넣기"로 채운다.
- 영업일 기준 알림은 켜진 휴장일을 영업일에서 뺀다. 휴장일을 바꿔 발송일이 달라져도 이미 보낸 알림은 다시 보내지 않는다.
- 근무표 하나만 쉬는 날은 휴장일이 아니라 그 근무표 관리자가 날짜 칸의 [메모]에서 "근무 없음"으로 적는다(그날 근무가 있으면 확인 뒤 지우고 기록이 남는다).
- 라이브러리가 모르는 새 공휴일은 위처럼 직접 추가하고, 업그레이드 때 `requirements.lock` 의 `holidays` 버전을 올린다(DEVELOPMENT.md "의존성 고정").

## 캘린더 구독 (ICS)
```

26. `docs/OPERATIONS.md` — 찾을 글:

```markdown
- 피드에는 배포된 회차의 본인 출근조·관제 일정만, 오늘 기준 지난 90일부터 나온다.
```

   바꿀 글:

```markdown
- 피드에는 배포된 회차의 본인 출근조·관제·점심당번(부서 점심 시각이 있을 때) 일정만, 오늘 기준 지난 90일부터 나온다. 사유(휴가 등)가 붙은 날의 근무조는 빠진다.
```

27. `docs/PRINCIPLES.md` — 찾을 글:

```markdown
| 2026-11-15 | 로그인 유지 90일(로그인할 때부터, 요청마다 늘리지 않음), 글씨 크기 3단계는 기기마다(localStorage) | 휴대폰으로 가끔 보는 사람이 2주마다 다시 로그인하지 않게. 요청마다 늘리면 화면을 열 때마다 세션 DB 쓰기가 생긴다. 글씨 크기는 같은 사람도 PC·휴대폰에서 다르게 고른다 |
```

   바꿀 글:

```markdown
| 2026-11-15 | 로그인 유지 90일(로그인할 때부터, 요청마다 늘리지 않음), 글씨 크기 3단계는 기기마다(localStorage) | 휴대폰으로 가끔 보는 사람이 2주마다 다시 로그인하지 않게. 요청마다 늘리면 화면을 열 때마다 세션 DB 쓰기가 생긴다. 글씨 크기는 같은 사람도 PC·휴대폰에서 다르게 고른다 |
| 2026-11-16 | 휴장일은 DB 표(라이브러리 `holidays` + 12/31 로 자동 채움, 슈퍼유저가 추가·끔), 새로 만드는 회차부터 건너뜀(`skip_holidays`). 화면 GET 은 채우지 않는다 | 코드 상수는 임시공휴일마다 배포가 필요하다. 마이그레이션이 채우면 라이브러리 버전에 따라 결과가 달라진다. 기존 회차를 바꾸면 이미 받은 근무표가 달라진다 |
| 2026-11-16 | 점심당번은 키 `lunch`(혼자인 당번 칸)로, 생성 때 가장 이른 근무조로 채우고 시각은 부서마다 DB | 근무표마다 점심 시각이 달라도 정의는 하나로 두고, 화면에는 시각 없이 "점심당번"만 보인다 |
| 2026-11-16 | 사유(휴가·출장·교육)는 출근 행의 칸이고, 붙으면 그날 근무로 치지 않는다(알림·캘린더·생성 후보·통계 제외). 사유만 바꾸면 기록만 남고 알림은 없다 | 엑셀 근무표의 "이름(휴가)"를 그대로 옮기되, 휴가 간 사람에게 근무 알림이 가지 않게 |
| 2026-11-16 | 메모는 회차가 아니라 (근무표, 날짜)에. 근무 없음 날 메모는 그날 배정을 지우고 기록을 남기며, 배포 취소로도 되살리지 않는다 | 근무표가 없는 날에도 메모가 보여야 하고, "근무 없는 날은 늘 비어 있다"를 한 곳에서 지킨다 |
| 2026-11-16 | `?board=` 는 보이는 근무표가 내 근무표가 아닐 때만 붙이고, 마지막에 본 근무표는 `/` 에서만 쓴다 | IT 사람의 주소·알림 링크가 1단계 그대로 남고, 링크 없는 변경 POST 가 남의 근무표로 가지 않는다 |
| 2026-11-16 | 2단계 업그레이드는 IT 보고서 알림이 한 번 다시 나가는 것을 받아들이고, 되돌리기는 백업 복원으로만 | 보고서에 점심당번 줄을 붙이면 내용 hash 가 바뀐다. 점심당번 행·기록이 쌓인 뒤의 역마이그레이션은 틀리기 쉽다 |
```

28. `docs/DEVELOPMENT.md` — 찾을 글:

```markdown
- 가짜 데이터는 마이그레이션이 만든 IT 근무표(`boards.it_board()`)에 부서(order 0~3: MEMS·TMCH·MD·UI)·회차를 붙이고, admin 을 "IT 근무표 관리" 그룹에, manager 를 MEMS 입력 그룹에 넣는다(관리자·담당자 판정이 그룹이라서). `tests/test_help_seed.py` 가 seed.py 가 끝까지 도는지 확인한다.
```

   바꿀 글:

```markdown
- 가짜 데이터는 마이그레이션이 만든 IT 근무표(`boards.it_board()`)에 부서(order 0~3: MEMS·TMCH·MD·UI, 점심 11:30~12:30)·회차를 붙이고, admin 을 "IT 근무표 관리" 그룹에, manager 를 MEMS 입력 그룹에 넣는다(관리자·담당자 판정이 그룹이라서). 2단계 화면 예시로 공휴일(`holidays.sync`)과 가짜 임시 휴장일(이번 주 또는 다음 주 금요일), 날·주·달 메모, 다음 회차의 근무 없음 날, 오늘 사유(휴가) 한 명, 생성이 채운 점심당번(MD 새벽 근무자)이 들어간다. 근무표 고르기·보기 전용은 근무표가 하나라 영상에 나오지 않는다(근무표를 더하는 4단계에 다시 녹화). `tests/test_help_seed.py` 가 seed.py 가 끝까지 도는지 확인한다(`lunch` 픽스처로 점심당번 정의를 켠다).
```


고친 뒤 남은 옛 말이 없는지 본다:
```bash
grep -n "휴장일 처리 없음\|휴장일·공휴일 처리\|하루 14칸\|근무표 고르기는 2단계" docs/*.md
```
Expected: 출력 없음

- [ ] **Step 13: 전체 확인과 브라우저 확인(가짜 데이터 DB, 끝나면 지움)**

```bash
.venv/bin/pytest -W error -q                                                       # 모두 PASS, 경고 0개
DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --check --dry-run   # No changes detected
.venv/bin/pytest -W error -q tests/test_alarm_texts_it.py                          # 그대로 통과(IT 문구 불변)
```

화면은 Step 10 과 같은 가짜 데이터로 띄운다(`W=$(mktemp -d)`, `DUTY_ENV_FILE= DUTY_DEBUG=1 DUTY_DATA_DIR=$W/data`, `migrate` → `shell < tools/help_videos/seed.py` → `runserver 127.0.0.1:8795`). 브라우저에서 PC 1400px, 휴대폰 390px(개발자 도구 기기 모드), 다크 모드로 본다.

- **member**(비밀번호 `Demo-pass-123`):
  - 주간과 월간에서 휴장일 이름, 날 메모, 주 메모(표 위·월간은 그 주 아래), 달 메모(표 아래), "(휴가)", 점심당번 줄이 보이는지 본다.
  - [가]로 크게·아주 크게를 본다.
  - 근무 변경 창에 "점심당번도 같이 넘기기"와 [사유 저장]이 보이는지 본다.
  - 다음 회차 기간은 배포 전이라 근무표 없음으로 보인다.
  - [도움말]의 "글로 보기"에 새 줄 다섯 개가 있고 새 영상이 재생되는지 본다.
- **admin**: 날짜 칸·주·달의 [메모] 팝업과 "근무 없음" 확인창을 본다. 회차 "다음 회차"의 입력 표에서 근무 없음 날 행이 잠겨 있는지 본다(manager 로 봐도 된다).
- 모든 화면에서 콘솔에 `document.documentElement.scrollWidth > innerWidth` 가 `false` 다(사본 기준 1385/1400, 390/390).

다 보면 서버를 끄고 `rm -rf $W` 로 가짜 데이터를 지운다.

- [ ] **Step 14: 전체 테스트**

Run: `.venv/bin/pytest -W error -q`
Expected: 모두 PASS(사본 기준 1092 passed), 경고 0개

- [ ] **Step 15: 커밋(문서)**

```bash
git add docs/ARCHITECTURE.md docs/OVERVIEW.md docs/OPERATIONS.md docs/PRINCIPLES.md docs/DEVELOPMENT.md
git commit -m "docs: 2단계 반영(점심당번·사유·메모·휴장일·보일 근무표, 2단계 업그레이드·휴장일 운영, 결정 기록)"
```


---

