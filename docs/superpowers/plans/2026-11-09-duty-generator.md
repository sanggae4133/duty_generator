# duty_generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 구글 시트 + Apps Script 당번표 제작 흐름을 대체하는 Django 웹(회차 관리, 부서 출근표 취합, 장중관제 생성, 배포, 조회, 근무 변경, 노티파이어 API)을 만든다.

**Architecture:** Django 단일 앱 `duty`. 순수 로직(`shifts.py`, `generator.py`, `csv_io.py`)은 ORM에 의존하지 않고, DB를 바꾸는 모든 규칙(권한, 지난 날짜, ChangeLog)은 `duty/services/` 를 거친다. 화면은 서버 렌더링 템플릿 + htmx(근무 변경 팝업) + Pico.css(CDN), 빌드 단계 없음.

**Tech Stack:** Python 3.12, Django 5.2, django-axes, openpyxl, whitenoise, gunicorn, SQLite(WAL), pytest + pytest-django.

**Spec:** `docs/superpowers/specs/2026-11-09-duty-generator-design.md`

## Global Constraints

- Python `>=3.12`, Django `>=5.2,<6`
- 시간대 `Asia/Seoul`, `USE_TZ = True`. "오늘"은 항상 `duty.perms.today()` 로만 구한다(테스트에서 monkeypatch). 다른 모듈은 `from . import perms` 후 `perms.today()` 로 호출한다 — `from .perms import today` 금지.
- 대상 날짜 = 회차 기간의 월~금 (휴장일 처리 없음).
- 지난 날짜(오늘 이전) 수정은 어드민(`User.is_staff`)만. 오늘은 누구나.
- 출근조 키: `dawn`, `normal`, `dinner`, `night`. 관제 칸 키: `slot0` ~ `slot9`. 이 14개 키를 "cell" 이라 부르고 ChangeLog·화면·API 전부 같은 키를 쓴다.
- 장중관제 자격 = `type == "개발자"` 이고 그날 slot 자격 출근조에 있음. 생성 시 카운트 풀은 **기간 중 한 번이라도 자격이 있는 개발자만**(기존 JS는 전체 멤버를 넣어 Phase 2가 동작하지 않던 버그 — 수정).
- 사용자에게 보이는 메시지는 한국어.
- 비밀값은 환경변수: `DUTY_SECRET_KEY`, `DUTY_API_TOKEN`, `DUTY_ADMIN_PATH`, `DUTY_ALLOWED_HOSTS`, `DUTY_CSRF_ORIGINS`, `DUTY_DB_PATH`, `DUTY_DEBUG`.
- 테스트 실행: `.venv/bin/pytest` (설정 `config.test_settings`).
- 커밋 메시지 끝에 아래 두 줄을 붙인다:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0176vw5QvpTHYvSsnWdF4bts
  ```

## File Structure

```
pyproject.toml, manage.py, .gitignore, README.md
config/  settings.py  test_settings.py  urls.py  wsgi.py  __init__.py
duty/
  __init__.py  apps.py
  shifts.py          근무조/관제 상수, weekdays()
  models.py          Department, Member, Period, Commute, ControlDuty, ChangeLog
  errors.py          DutyError
  perms.py           today, is_admin, member_of, managed_departments, can_input_department, assert_can_edit_date
  generator.py       generate_control_duty (순수)
  csv_io.py          CSV 파싱/내보내기 (순수)
  services/
    __init__.py
    periods.py       save_draft, open_collecting, close_collecting, missing_dates
    collect.py       load_table, validate_table, apply_table, apply_csv, export_csv, progress
    generate.py      run_generation
    publish.py       PublishPreview, preview_publish, publish
    roster.py        Cell, Day, chain, published_days, find_day, api_assignments, member_schedule, DEPT_VIEWS, department_table
    changes.py       ChangeResult, change_cell, swap
    stats.py         MemberStat, Summary, member_stats, period_duty_counts
  accounts.py        issue_account
  middleware.py      ForcePasswordChangeMiddleware
  context.py         nav (can_collect)
  admin.py
  api.py             assignments
  urls.py
  views/  __init__.py common.py auth.py roster.py collect.py manage.py
  importer.py        시트 가져오기 로직
  management/__init__.py  management/commands/__init__.py  management/commands/import_sheets.py
  templates/duty/    base, login, password_change, roster, _cell_form, day, dept, me,
                     collect_index, collect_table, periods, period_detail, publish, stats, changes
tests/
  conftest.py  test_shifts.py  test_models.py  test_perms.py  test_generator.py  test_csv_io.py
  test_periods.py  test_collect.py  test_generate.py  test_publish.py  test_roster.py  test_changes.py
  test_stats.py  test_auth_api.py  test_views_roster.py  test_views_collect.py  test_views_manage.py
  test_importer.py  test_baseline.py  fixtures/baseline_commutes.json
deploy/  duty-generator.service  duty-generator-backup.service  duty-generator-backup.timer  env.example
```

---

### Task 1: 프로젝트 골격과 근무조 상수

**Files:**
- Create: `pyproject.toml`, `manage.py`, `.gitignore`, `config/__init__.py`, `config/settings.py`, `config/test_settings.py`, `config/urls.py`, `config/wsgi.py`, `duty/__init__.py`, `duty/apps.py`, `duty/urls.py`, `duty/shifts.py`
- Test: `tests/test_shifts.py`

**Interfaces:**
- Produces: `duty.shifts` — `COMMUTE_SHIFTS: dict[str,str]`, `SHIFT_BY_LABEL`, `CONTROL_SLOTS: list[tuple[str, tuple[str,...]]]`, `CELLS: list[str]`, `CELL_BY_LABEL`, `DAY_LABELS: str`, `DEVELOPER`, `STAFF`, `TARGET_SPREAD`, `MAX_SWAP_ITERATIONS`, `slot_cell(i)->str`, `is_slot_cell(cell)->bool`, `slot_index(cell)->int`, `cell_label(cell)->str`, `weekdays(start, end)->list[date]`

- [ ] **Step 1: 패키지 파일 작성**

`pyproject.toml`
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "duty-generator"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "Django>=5.2,<6",
    "django-axes>=7.0",
    "openpyxl>=3.1",
    "whitenoise>=6.6",
    "gunicorn>=22",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-django>=4.8"]

[tool.setuptools.packages.find]
include = ["config*", "duty*"]

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.test_settings"
testpaths = ["tests"]
```

`.gitignore`
```
.venv/
__pycache__/
*.egg-info/
db.sqlite3*
staticfiles/
.cache/
.pytest_cache/
```

`manage.py`
```python
#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
```

`config/__init__.py`, `duty/__init__.py`: 빈 파일.

`config/settings.py`
```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
env = os.environ.get

DEBUG = env("DUTY_DEBUG", "0") == "1"
SECRET_KEY = env("DUTY_SECRET_KEY") or ("dev-insecure-key" if DEBUG else "")
if not SECRET_KEY:
    raise RuntimeError("DUTY_SECRET_KEY 환경변수가 필요합니다.")

ALLOWED_HOSTS = [h for h in env("DUTY_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in env("DUTY_CSRF_ORIGINS", "").split(",") if o]
API_TOKEN = env("DUTY_API_TOKEN", "")
ADMIN_PATH = env("DUTY_ADMIN_PATH", "admin").strip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "duty",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": env("DUTY_DB_PATH", str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {"init_command": "PRAGMA journal_mode=WAL;", "transaction_mode": "IMMEDIATE"},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
SESSION_COOKIE_AGE = 14 * 24 * 3600
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000  # 출근표 표 저장: 260일 × 4칸
```

`config/test_settings.py`
```python
import os

os.environ.setdefault("DUTY_DEBUG", "1")
os.environ.setdefault("DUTY_SECRET_KEY", "test-secret")
os.environ.setdefault("DUTY_API_TOKEN", "test-token")

from .settings import *  # noqa: E402,F401,F403
```

`config/urls.py`
```python
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path(f"{settings.ADMIN_PATH}/", admin.site.urls),
    path("", include("duty.urls")),
]
```

`config/wsgi.py`
```python
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()
```

`duty/apps.py`
```python
from django.apps import AppConfig


class DutyConfig(AppConfig):
    name = "duty"
    verbose_name = "당번표"
```

`duty/urls.py` (이후 Task에서 채운다)
```python
urlpatterns = []
```

- [ ] **Step 2: 가상환경 설치**

Run: `python3 -m venv .venv && .venv/bin/pip install -q -e '.[dev]'`
Expected: 오류 없이 종료

- [ ] **Step 3: 실패하는 테스트 작성** — `tests/test_shifts.py`

```python
from datetime import date

from duty.shifts import CELL_BY_LABEL, CELLS, cell_label, is_slot_cell, slot_index, weekdays


def test_cells_order_matches_combined_view():
    assert CELLS[:3] == ["dawn", "normal", "dinner"]
    assert CELLS[3:13] == [f"slot{i}" for i in range(10)]
    assert CELLS[-1] == "night"


def test_cell_labels_roundtrip():
    assert cell_label("slot0") == "08:30~09:30"
    assert cell_label("slot9") == "17:00~18:00"
    assert cell_label("night") == "야간"
    assert all(CELL_BY_LABEL[cell_label(c)] == c for c in CELLS)


def test_slot_helpers():
    assert is_slot_cell("slot3") and not is_slot_cell("dawn")
    assert slot_index("slot7") == 7


def test_weekdays_skip_weekend():
    # 2026-11-06 금, 11-09 월
    assert weekdays(date(2026, 11, 6), date(2026, 11, 10)) == [
        date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 10)
    ]
```

- [ ] **Step 4: 실패 확인**

Run: `.venv/bin/pytest tests/test_shifts.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'duty.shifts'`)

- [ ] **Step 5: 구현** — `duty/shifts.py`

```python
"""근무조와 장중관제 시간대 정의. 바뀔 일이 드물어 코드 상수로 둔다."""

from datetime import date, timedelta

COMMUTE_SHIFTS: dict[str, str] = {  # 순서 = 화면 표시 순서
    "dawn": "새벽",
    "normal": "정상",
    "dinner": "석식교대",
    "night": "야간",
}
SHIFT_BY_LABEL = {label: key for key, label in COMMUTE_SHIFTS.items()}

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

DEVELOPER = "개발자"
STAFF = "직원"
TARGET_SPREAD = 2
MAX_SWAP_ITERATIONS = 10000
DAY_LABELS = "월화수목금토일"


def slot_cell(i: int) -> str:
    return f"slot{i}"


def is_slot_cell(cell: str) -> bool:
    return cell.startswith("slot")


def slot_index(cell: str) -> int:
    return int(cell[4:])


CELLS: list[str] = ["dawn", "normal", "dinner", *[slot_cell(i) for i in range(len(CONTROL_SLOTS))], "night"]


def cell_label(cell: str) -> str:
    return CONTROL_SLOTS[slot_index(cell)][0] if is_slot_cell(cell) else COMMUTE_SHIFTS[cell]


CELL_BY_LABEL = {cell_label(c): c for c in CELLS}


def weekdays(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out
```

- [ ] **Step 6: 통과 확인**

Run: `.venv/bin/pytest tests/test_shifts.py -v && DUTY_DEBUG=1 .venv/bin/python manage.py check`
Expected: 4 passed, `System check identified no issues`

- [ ] **Step 7: 커밋**

```bash
git add pyproject.toml manage.py .gitignore config duty tests/test_shifts.py
git commit -m "feat: Django 프로젝트 골격과 근무조 상수"
```

---

### Task 2: 모델, 권한 헬퍼, 테스트 fixture

**Files:**
- Create: `duty/models.py`, `duty/errors.py`, `duty/perms.py`, `duty/migrations/0001_initial.py`(생성 명령으로), `tests/conftest.py`
- Test: `tests/test_models.py`, `tests/test_perms.py`

**Interfaces:**
- Consumes: `duty.shifts.COMMUTE_SHIFTS`, `weekdays`
- Produces:
  - `Department(code PK, name, shifts, managers M2M Member)`, `.shift_keys() -> list[str]`
  - `Member(code, name, department, part, type, is_active, user, must_change_password)`
  - `Period(name, start_date, end_date, status, seed, generated_at, published_at, overwrite_from)`, `Period.Status.{DRAFT,COLLECTING,CLOSED,GENERATED,PUBLISHED}`, `.dates() -> list[date]`
  - `Commute(period, date, member, shift)`, `ControlDuty(period, date, slot, member)`, `ChangeLog(at, by, period, date, cell, before, after)`
  - `duty.errors.DutyError`
  - `duty.perms`: `today()`, `is_admin(user)`, `member_of(user) -> Member|None`, `managed_departments(user) -> QuerySet[Department]`, `can_input_department(user, dept) -> bool`, `assert_can_edit_date(user, d)` (PermissionDenied)
  - fixtures: `depts`, `make_member(name, dept="MEMS", type="개발자", user=False, active=True)`, `admin_user`, `fixed_today(d)`

- [ ] **Step 1: 테스트 fixture 작성** — `tests/conftest.py`

```python
from itertools import count

import pytest
from django.contrib.auth.models import User

from duty.models import Department, Member

DEPTS = [
    ("MEMS", "매칭엔진실", "dawn,normal,dinner,night"),
    ("TMCH", "매매지원실", "dawn,normal,dinner,night"),
    ("MD", "정보분배", "dawn,normal,dinner,night"),
    ("UI", "UI", "normal,dinner,night"),
]


@pytest.fixture
def depts(db):
    return {c: Department.objects.create(code=c, name=n, shifts=s) for c, n, s in DEPTS}


@pytest.fixture
def make_member(depts):
    seq = count(1)

    def make(name, dept="MEMS", type="개발자", user=False, active=True):
        m = Member.objects.create(
            code=f"{dept}{next(seq):03d}", name=name, department=depts[dept],
            part="", type=type, is_active=active,
        )
        if user:
            m.user = User.objects.create_user(username=m.code, password="unused-Pw-123")
            m.save()
        return m

    return make


@pytest.fixture
def admin_user(db):
    return User.objects.create_user("admin", password="unused-Pw-123", is_staff=True)


@pytest.fixture
def fixed_today(monkeypatch):
    def set_today(d):
        monkeypatch.setattr("duty.perms.today", lambda: d)

    return set_today
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_models.py`
```python
from datetime import date

import pytest
from django.db import IntegrityError

from duty.models import Commute, ControlDuty, Period


def test_department_shift_keys(depts):
    assert depts["UI"].shift_keys() == ["normal", "dinner", "night"]


def test_period_dates_are_weekdays():
    p = Period(name="p", start_date=date(2026, 11, 6), end_date=date(2026, 11, 10))
    assert p.dates() == [date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 10)]


def test_period_default_status_is_draft(db):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
    assert p.status == Period.Status.DRAFT


def test_one_commute_per_member_per_day(make_member):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
    m = make_member("가")
    Commute.objects.create(period=p, date=date(2026, 11, 9), member=m, shift="dawn")
    with pytest.raises(IntegrityError):
        Commute.objects.create(period=p, date=date(2026, 11, 9), member=m, shift="night")


def test_one_member_per_duty_slot(make_member):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
    a, b = make_member("가"), make_member("나")
    ControlDuty.objects.create(period=p, date=date(2026, 11, 9), slot=0, member=a)
    with pytest.raises(IntegrityError):
        ControlDuty.objects.create(period=p, date=date(2026, 11, 9), slot=0, member=b)


def test_member_once_per_day_in_duty(make_member):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13))
    a = make_member("가")
    ControlDuty.objects.create(period=p, date=date(2026, 11, 9), slot=0, member=a)
    with pytest.raises(IntegrityError):
        ControlDuty.objects.create(period=p, date=date(2026, 11, 9), slot=1, member=a)
```

`tests/test_perms.py`
```python
from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied

from duty import perms


def test_past_date_is_admin_only(fixed_today, make_member, admin_user):
    fixed_today(date(2026, 11, 10))
    m = make_member("가", user=True)
    perms.assert_can_edit_date(m.user, date(2026, 11, 10))  # 오늘은 누구나
    with pytest.raises(PermissionDenied):
        perms.assert_can_edit_date(m.user, date(2026, 11, 9))
    perms.assert_can_edit_date(admin_user, date(2026, 11, 9))


def test_can_input_department(depts, make_member, admin_user):
    m = make_member("가", user=True)
    depts["MEMS"].managers.add(m)
    assert perms.can_input_department(m.user, depts["MEMS"])
    assert not perms.can_input_department(m.user, depts["MD"])
    assert perms.can_input_department(admin_user, depts["MD"])


def test_managed_departments(depts, make_member, admin_user):
    m = make_member("가", user=True)
    depts["MD"].managers.add(m)
    assert list(perms.managed_departments(m.user)) == [depts["MD"]]
    assert perms.managed_departments(admin_user).count() == 4
    assert perms.managed_departments(AnonymousUser()).count() == 0


def test_member_of(make_member, admin_user):
    m = make_member("가", user=True)
    assert perms.member_of(m.user) == m
    assert perms.member_of(admin_user) is None
```

- [ ] **Step 3: 실패 확인**

Run: `.venv/bin/pytest tests/test_models.py tests/test_perms.py -v`
Expected: FAIL (`ImportError` — models 없음)

- [ ] **Step 4: 구현**

`duty/errors.py`
```python
class DutyError(Exception):
    """업무 규칙 위반. 메시지는 사용자에게 그대로 보여준다."""
```

`duty/models.py`
```python
from django.conf import settings
from django.db import models

from .shifts import COMMUTE_SHIFTS, DEVELOPER, STAFF, weekdays


class Department(models.Model):
    code = models.CharField("코드", max_length=8, primary_key=True)
    name = models.CharField("이름", max_length=32, unique=True)
    shifts = models.CharField("가능한 출근조", max_length=64, help_text="쉼표 구분: dawn,normal,dinner,night")
    managers = models.ManyToManyField("Member", blank=True, related_name="managed_departments", verbose_name="입력 담당자")

    class Meta:
        verbose_name = verbose_name_plural = "부서"
        ordering = ["code"]

    def __str__(self):
        return self.name

    def shift_keys(self) -> list[str]:
        return [s for s in self.shifts.split(",") if s]


class Member(models.Model):
    code = models.CharField("코드", max_length=16, unique=True)
    name = models.CharField("이름", max_length=32, unique=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="members", verbose_name="부서")
    part = models.CharField("파트", max_length=32, blank=True)
    type = models.CharField("구분", max_length=8, choices=[(STAFF, STAFF), (DEVELOPER, DEVELOPER)])
    is_active = models.BooleanField("재직", default=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="member")
    must_change_password = models.BooleanField("첫 로그인 비번 변경 필요", default=False)

    class Meta:
        verbose_name = verbose_name_plural = "멤버"
        ordering = ["code"]

    def __str__(self):
        return self.name


class Period(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "작성 중"
        COLLECTING = "collecting", "취합 중"
        CLOSED = "closed", "마감"
        GENERATED = "generated", "생성됨"
        PUBLISHED = "published", "배포됨"

    name = models.CharField("이름", max_length=64)
    start_date = models.DateField("시작일")
    end_date = models.DateField("종료일")
    status = models.CharField("상태", max_length=16, choices=Status.choices, default=Status.DRAFT)
    seed = models.BigIntegerField(null=True, blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    overwrite_from = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "회차"

    def __str__(self):
        return self.name

    def dates(self):
        return weekdays(self.start_date, self.end_date)


class Commute(models.Model):
    period = models.ForeignKey(Period, on_delete=models.CASCADE)
    date = models.DateField()
    member = models.ForeignKey(Member, on_delete=models.PROTECT)
    shift = models.CharField(max_length=8, choices=list(COMMUTE_SHIFTS.items()))

    class Meta:
        constraints = [models.UniqueConstraint(fields=["period", "date", "member"], name="commute_one_shift_per_day")]
        indexes = [models.Index(fields=["date"])]


class ControlDuty(models.Model):
    period = models.ForeignKey(Period, on_delete=models.CASCADE)
    date = models.DateField()
    slot = models.PositiveSmallIntegerField()
    member = models.ForeignKey(Member, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["period", "date", "slot"], name="duty_one_member_per_slot"),
            models.UniqueConstraint(fields=["period", "date", "member"], name="duty_one_slot_per_member"),
        ]
        indexes = [models.Index(fields=["date"])]


class ChangeLog(models.Model):
    at = models.DateTimeField(auto_now_add=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)  # null = import
    period = models.ForeignKey(Period, on_delete=models.CASCADE)
    date = models.DateField()
    cell = models.CharField(max_length=8)  # dawn|normal|dinner|night|slot0..slot9
    before = models.ForeignKey(Member, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    after = models.ForeignKey(Member, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["at", "id"]
```

`duty/perms.py`
```python
"""권한 규칙. 다른 모듈은 `from . import perms` 후 `perms.today()` 형태로 호출한다(테스트 monkeypatch 용)."""

from datetime import date

from django.core.exceptions import PermissionDenied
from django.utils import timezone

from .models import Department, Member


def today() -> date:
    return timezone.localdate()


def is_admin(user) -> bool:
    return bool(user.is_authenticated and user.is_staff)


def member_of(user) -> Member | None:
    if not user.is_authenticated:
        return None
    return getattr(user, "member", None)


def managed_departments(user):
    if is_admin(user):
        return Department.objects.all()
    member = member_of(user)
    if member is None:
        return Department.objects.none()
    return member.managed_departments.all()


def can_input_department(user, dept: Department) -> bool:
    return is_admin(user) or managed_departments(user).filter(pk=dept.pk).exists()


def assert_can_edit_date(user, d: date) -> None:
    if d < today() and not is_admin(user):
        raise PermissionDenied("지난 날짜는 어드민만 수정할 수 있습니다.")
```

- [ ] **Step 5: 마이그레이션 생성**

Run: `DUTY_DEBUG=1 .venv/bin/python manage.py makemigrations duty`
Expected: `duty/migrations/0001_initial.py` 생성

- [ ] **Step 6: 통과 확인**

Run: `.venv/bin/pytest -v`
Expected: 전부 PASS

- [ ] **Step 7: 커밋**

```bash
git add duty tests
git commit -m "feat: 데이터 모델과 권한 헬퍼"
```

---

### Task 3: 장중관제 생성 알고리즘 (순수 함수)

**Files:**
- Create: `duty/generator.py`
- Test: `tests/test_generator.py`

**Interfaces:**
- Consumes: `duty.shifts.CONTROL_SLOTS`, `TARGET_SPREAD`, `MAX_SWAP_ITERATIONS`
- Produces:
  - `SlotFailure(date, slot:int, candidates:int)` (frozen dataclass)
  - `GenerationError(failures: list[SlotFailure])`
  - `GenerationOutput(assignments: dict[date, list[str]], counts: dict[str,int], spread: int, reached: bool)`
  - `generate_control_duty(dates: list[date], commutes: dict[date, dict[str, set[str]]], developers: set[str], seed: int) -> GenerationOutput`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_generator.py`

```python
from datetime import date

import pytest

from duty.generator import GenerationError, SlotFailure, generate_control_duty
from duty.shifts import CONTROL_SLOTS, weekdays

DATES = weekdays(date(2026, 11, 9), date(2026, 11, 27))  # 15일
NORMAL = [f"N{i}" for i in range(7)]
DINNER = [f"D{i}" for i in range(7)]
DEVS = set(NORMAL) | set(DINNER) | {"X"}


def commutes():
    return {d: {"normal": set(NORMAL), "dinner": set(DINNER), "dawn": {"X"}} for d in DATES}


def test_every_slot_is_eligible_and_unique_per_day():
    c = commutes()
    out = generate_control_duty(DATES, c, DEVS, seed=1)
    assert list(out.assignments) == DATES
    for d, picked in out.assignments.items():
        assert len(picked) == 10 and len(set(picked)) == 10
        for i, m in enumerate(picked):
            allowed = set().union(*(c[d][s] for s in CONTROL_SLOTS[i][1]))
            assert m in allowed


def test_never_eligible_developer_is_not_in_pool():
    out = generate_control_duty(DATES, commutes(), DEVS, seed=1)
    assert "X" not in out.counts  # 새벽 출근 개발자는 풀에서 제외 (기존 JS 버그 수정)


def test_non_developers_are_excluded():
    out = generate_control_duty(DATES, commutes(), DEVS - {"N0"}, seed=1)
    assert "N0" not in out.counts
    assert all("N0" not in p for p in out.assignments.values())


def test_same_seed_same_result():
    a = generate_control_duty(DATES, commutes(), DEVS, seed=7)
    b = generate_control_duty(DATES, commutes(), DEVS, seed=7)
    assert a.assignments == b.assignments


def test_spread_reaches_target():
    out = generate_control_duty(DATES, commutes(), DEVS, seed=3)
    assert out.reached and out.spread <= 2
    assert sum(out.counts.values()) == len(DATES) * 10


def test_failure_lists_slots_without_candidates():
    c = commutes()
    c[DATES[0]]["normal"] = set()
    with pytest.raises(GenerationError) as e:
        generate_control_duty(DATES, c, DEVS, seed=1)
    assert SlotFailure(DATES[0], 0, 0) in e.value.failures
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_generator.py -v`
Expected: FAIL (`ModuleNotFoundError: duty.generator`)

- [ ] **Step 3: 구현** — `duty/generator.py`

```python
"""장중관제 당번 생성. 기존 Apps Script(InMarketControlDutyGenerator.gs) 이식.

Phase 1 Greedy: 자격자가 적은 slot부터, 그날 미배정 자격자 중 누적 배정이 가장 적은 사람.
Phase 2 Swap:   최다 배정자의 slot을 최소 배정자(그 slot 자격 있고 그날 미배정)에게 넘김.
차이점: 카운트 풀을 '기간 중 한 번이라도 자격이 있는 개발자'로 한정한다.
기존 JS는 전체 멤버(직원 포함)를 넣어 최소값이 항상 0인 직원이 되어 Phase 2가 즉시 종료되었다.
"""

import random
from dataclasses import dataclass
from datetime import date

from .shifts import CONTROL_SLOTS, MAX_SWAP_ITERATIONS, TARGET_SPREAD


@dataclass(frozen=True)
class SlotFailure:
    date: date
    slot: int
    candidates: int


class GenerationError(Exception):
    def __init__(self, failures: list[SlotFailure]):
        super().__init__(f"배정할 수 없는 칸 {len(failures)}개")
        self.failures = failures


@dataclass
class GenerationOutput:
    assignments: dict[date, list[str]]
    counts: dict[str, int]
    spread: int
    reached: bool


def _eligible(day: dict[str, set[str]], developers: set[str]) -> list[set[str]]:
    return [{m for s in shifts for m in day.get(s, ()) if m in developers} for _, shifts in CONTROL_SLOTS]


def generate_control_duty(
    dates: list[date],
    commutes: dict[date, dict[str, set[str]]],
    developers: set[str],
    seed: int,
) -> GenerationOutput:
    rng = random.Random(seed)
    eligible = {d: _eligible(commutes.get(d, {}), developers) for d in dates}
    counts = {m: 0 for m in sorted({m for d in dates for slot in eligible[d] for m in slot})}
    assignments: dict[date, list[str]] = {}
    failures: list[SlotFailure] = []

    for d in dates:
        slots = eligible[d]
        picked: list[str | None] = [None] * len(slots)
        used: set[str] = set()
        for i in sorted(range(len(slots)), key=lambda i: len(slots[i])):
            candidates = sorted(m for m in slots[i] if m not in used)  # set 순서는 해시에 따라 바뀌므로 정렬 후 섞는다
            if not candidates:
                failures.append(SlotFailure(d, i, len(slots[i])))
                continue
            rng.shuffle(candidates)
            pick = min(candidates, key=lambda m: counts[m])  # 동점이면 섞인 순서의 첫 번째
            picked[i] = pick
            used.add(pick)
            counts[pick] += 1
        assignments[d] = picked

    if failures:
        raise GenerationError(failures)

    _balance(assignments, eligible, counts)
    spread = max(counts.values()) - min(counts.values()) if counts else 0
    return GenerationOutput(assignments, counts, spread, spread <= TARGET_SPREAD)


def _balance(assignments, eligible, counts) -> None:
    for _ in range(MAX_SWAP_ITERATIONS):
        hi, lo = max(counts.values()), min(counts.values())
        if hi - lo <= TARGET_SPREAD:
            return
        maxs = sorted(m for m, c in counts.items() if c == hi)
        mins = sorted(m for m, c in counts.items() if c == lo)
        if not _swap_once(assignments, eligible, counts, maxs, mins):
            return


def _swap_once(assignments, eligible, counts, maxs, mins) -> bool:
    for hi_m in maxs:
        for lo_m in mins:
            for d, picked in assignments.items():
                if hi_m not in picked or lo_m in picked:
                    continue
                i = picked.index(hi_m)
                if lo_m not in eligible[d][i]:
                    continue
                picked[i] = lo_m
                counts[hi_m] -= 1
                counts[lo_m] += 1
                return True
    return False
```

Phase 2(swap)가 실제로 편차를 줄이는지는 Task 14의 실데이터 기준선 테스트가 검증한다(greedy만으로는 편차 6, swap 후 2).

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_generator.py -v`
Expected: 6 passed

- [ ] **Step 5: 커밋**

```bash
git add duty/generator.py tests/test_generator.py
git commit -m "feat: 장중관제 생성 알고리즘 이식 (swap 풀 버그 수정)"
```

---

### Task 4: CSV 입출력 (순수)

**Files:**
- Create: `duty/csv_io.py`
- Test: `tests/test_csv_io.py`

**Interfaces:**
- Consumes: `duty.shifts.COMMUTE_SHIFTS`, `DAY_LABELS`
- Produces:
  - `CsvError(row:int, column:str, reason:str)` (frozen; row 0 = 행 번호 없음)
  - `CsvInvalid(errors: list[CsvError])`
  - `CommuteTable = dict[date, dict[str, list[str]]]` (날짜 → 출근조 키 → 이름 목록)
  - `decode(raw: bytes) -> str`, `split_names(cell: str) -> list[str]`, `header_key(h: str) -> str`, `parse_date(s: str) -> date|None`
  - `parse_commute_csv(raw: bytes, shift_keys: list[str]) -> CommuteTable`
  - `export_commute_csv(dates: list[date], shift_keys: list[str], table: CommuteTable) -> bytes`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_csv_io.py`

```python
from datetime import date

import pytest

from duty.csv_io import CsvInvalid, export_commute_csv, parse_commute_csv, parse_date, split_names

KEYS = ["dawn", "normal", "dinner", "night"]
SAMPLE = (
    'date,day,"새벽\n(06:30~15:30)",정상,석식교대,야간\n'
    '2026-11-09,월,"가, 나",다,라,마\n'
    "2026/11/10,화,가,,,\n"
    ",,,,,\n"
)


def test_parse_basic():
    t = parse_commute_csv(SAMPLE.encode("utf-8-sig"), KEYS)
    assert t[date(2026, 11, 9)]["dawn"] == ["가", "나"]
    assert t[date(2026, 11, 9)]["night"] == ["마"]
    assert t[date(2026, 11, 10)]["normal"] == []
    assert len(t) == 2  # 빈 행 무시


def test_parse_cp949():
    t = parse_commute_csv(SAMPLE.encode("cp949"), KEYS)
    assert t[date(2026, 11, 9)]["normal"] == ["다"]


def test_date_formats():
    assert parse_date("2026-11-09") == date(2026, 11, 9)
    assert parse_date("2026/11/9") == date(2026, 11, 9)
    assert parse_date("2026. 11. 9.") == date(2026, 11, 9)
    assert parse_date("2026-02-30") is None
    assert parse_date("abc") is None


def test_split_names():
    assert split_names("가,\n나 , ") == ["가", "나"]
    assert split_names("") == []


def test_missing_column():
    raw = "date,정상,석식교대,야간\n2026-11-09,가,,\n".encode()
    with pytest.raises(CsvInvalid) as e:
        parse_commute_csv(raw, KEYS)
    assert [(x.row, x.column) for x in e.value.errors] == [(1, "새벽")]


def test_ui_without_dawn_column_is_fine():
    raw = "date,정상,석식교대,야간\n2026-11-09,가,,\n".encode()
    t = parse_commute_csv(raw, ["normal", "dinner", "night"])
    assert t[date(2026, 11, 9)]["normal"] == ["가"]


def test_bad_and_duplicate_dates():
    raw = "date,새벽,정상,석식교대,야간\nabc,,,,\n2026-11-09,,,,\n2026-11-09,,,,\n".encode()
    with pytest.raises(CsvInvalid) as e:
        parse_commute_csv(raw, KEYS)
    assert [x.row for x in e.value.errors] == [2, 4]


def test_export_roundtrip():
    table = {date(2026, 11, 9): {"dawn": ["가", "나"], "normal": ["다"]}}
    raw = export_commute_csv([date(2026, 11, 9), date(2026, 11, 10)], KEYS, table)
    assert raw.startswith("﻿".encode())
    back = parse_commute_csv(raw, KEYS)
    assert back[date(2026, 11, 9)] == {"dawn": ["가", "나"], "normal": ["다"], "dinner": [], "night": []}
    assert back[date(2026, 11, 10)] == {"dawn": [], "normal": [], "dinner": [], "night": []}
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_csv_io.py -v`
Expected: FAIL (`ModuleNotFoundError: duty.csv_io`)

- [ ] **Step 3: 구현** — `duty/csv_io.py`

```python
"""부서 출근표 CSV. 형식은 기존 취합 문서와 같다: date, (day), 새벽, 정상, 석식교대, 야간 / 이름 쉼표 구분."""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date

from .shifts import COMMUTE_SHIFTS, DAY_LABELS

CommuteTable = dict[date, dict[str, list[str]]]


@dataclass(frozen=True)
class CsvError:
    row: int  # 0 = 특정 행이 아님
    column: str
    reason: str


class CsvInvalid(Exception):
    def __init__(self, errors: list[CsvError]):
        super().__init__(f"CSV 오류 {len(errors)}건")
        self.errors = errors


def decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp949")  # 한국어 Windows 엑셀 기본 저장 형식


_NAME_SPLIT = re.compile(r"[,\n]")


def split_names(cell: str) -> list[str]:
    return [n.strip() for n in _NAME_SPLIT.split(cell or "") if n.strip()]


def header_key(h: str) -> str:
    return re.split(r"[\n(]", h, maxsplit=1)[0].strip()


_DATE_PATTERNS = [
    re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$"),
    re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$"),
    re.compile(r"^(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?$"),
]


def parse_date(s: str) -> date | None:
    s = (s or "").strip()
    for p in _DATE_PATTERNS:
        m = p.match(s)
        if m:
            try:
                return date(*map(int, m.groups()))
            except ValueError:
                return None
    return None


def parse_commute_csv(raw: bytes, shift_keys: list[str]) -> CommuteTable:
    rows = list(csv.reader(io.StringIO(decode(raw))))
    if not rows:
        raise CsvInvalid([CsvError(1, "", "빈 파일입니다.")])
    header = [header_key(h) for h in rows[0]]
    errors: list[CsvError] = []
    if "date" not in header:
        errors.append(CsvError(1, "date", "date 열이 없습니다."))
    cols: dict[str, int] = {}
    for key in shift_keys:
        label = COMMUTE_SHIFTS[key]
        if label in header:
            cols[key] = header.index(label)
        else:
            errors.append(CsvError(1, label, f"{label} 열이 없습니다."))
    if errors:
        raise CsvInvalid(errors)

    date_col = header.index("date")
    table: CommuteTable = {}
    for n, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue
        value = row[date_col] if date_col < len(row) else ""
        d = parse_date(value)
        if d is None:
            errors.append(CsvError(n, "date", f"날짜 형식이 아닙니다: {value!r}"))
            continue
        if d in table:
            errors.append(CsvError(n, "date", f"중복된 날짜입니다: {d}"))
            continue
        table[d] = {key: split_names(row[i] if i < len(row) else "") for key, i in cols.items()}
    if errors:
        raise CsvInvalid(errors)
    return table


def export_commute_csv(dates: list[date], shift_keys: list[str], table: CommuteTable) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "day", *[COMMUTE_SHIFTS[k] for k in shift_keys]])
    for d in dates:
        day = table.get(d, {})
        w.writerow([d.isoformat(), DAY_LABELS[d.weekday()], *[", ".join(day.get(k, [])) for k in shift_keys]])
    return buf.getvalue().encode("utf-8-sig")
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_csv_io.py -v`
Expected: 8 passed

- [ ] **Step 5: 커밋**

```bash
git add duty/csv_io.py tests/test_csv_io.py
git commit -m "feat: 부서 출근표 CSV 파싱과 내보내기"
```

---

### Task 5: 회차 상태와 출근표 반영 서비스

**Files:**
- Create: `duty/services/__init__.py` (빈 파일), `duty/services/periods.py`, `duty/services/collect.py`
- Test: `tests/test_periods.py`, `tests/test_collect.py`

**Interfaces:**
- Consumes: models, `perms`, `DutyError`, `csv_io.*`
- Produces:
  - `periods.save_draft(period: Period) -> Period` (DutyError: draft 아님 / 시작>종료 / 미배포 회차와 겹침)
  - `periods.open_collecting(period)` (draft|closed|generated → collecting, 그 회차 ControlDuty 삭제)
  - `periods.close_collecting(period)` (collecting → closed)
  - `periods.missing_dates(period) -> dict[str, list[date]]` (부서 코드 → 비어 있는 날짜, 빈 부서는 키 없음)
  - `collect.load_table(period, dept) -> CommuteTable`
  - `collect.validate_table(user, period, dept, table, full: bool) -> list[CsvError]`
  - `collect.apply_table(user, period, dept, table) -> int` (부서 전체 교체, 반영 인원수 반환; CsvInvalid/DutyError/PermissionDenied)
  - `collect.apply_csv(user, period, dept, raw: bytes) -> int`
  - `collect.export_csv(period, dept) -> bytes`
  - `collect.progress(period) -> dict[str, tuple[int, int]]` (부서 코드 → (채운 날짜 수, 전체 평일 수))

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_periods.py`
```python
from datetime import date

import pytest

from duty.errors import DutyError
from duty.models import Commute, ControlDuty, Period
from duty.services import periods

S = Period.Status


def d(m, day):
    return date(2026, m, day)


def test_unpublished_periods_cannot_overlap(db):
    periods.save_draft(Period(name="a", start_date=d(11, 9), end_date=d(11, 30)))
    with pytest.raises(DutyError):
        periods.save_draft(Period(name="b", start_date=d(11, 20), end_date=d(12, 31)))


def test_overlap_with_published_is_allowed(db):
    Period.objects.create(name="a", start_date=d(11, 2), end_date=d(11, 30), status=S.PUBLISHED)
    p = periods.save_draft(Period(name="b", start_date=d(11, 16), end_date=d(12, 31)))
    assert p.pk


def test_start_after_end_rejected(db):
    with pytest.raises(DutyError):
        periods.save_draft(Period(name="a", start_date=d(11, 30), end_date=d(11, 9)))


def test_dates_editable_only_in_draft(db):
    p = Period.objects.create(name="a", start_date=d(11, 9), end_date=d(11, 30), status=S.COLLECTING)
    p.end_date = d(12, 4)
    with pytest.raises(DutyError):
        periods.save_draft(p)


def test_open_close_and_reopen_deletes_duties(make_member):
    p = Period.objects.create(name="a", start_date=d(11, 9), end_date=d(11, 13))
    periods.open_collecting(p)
    assert p.status == S.COLLECTING
    periods.close_collecting(p)
    assert p.status == S.CLOSED
    p.status, p.seed = S.GENERATED, 1
    p.save()
    ControlDuty.objects.create(period=p, date=d(11, 9), slot=0, member=make_member("가"))
    periods.open_collecting(p)
    assert p.status == S.COLLECTING and p.seed is None
    assert not ControlDuty.objects.filter(period=p).exists()


def test_close_requires_collecting(db):
    p = Period.objects.create(name="a", start_date=d(11, 9), end_date=d(11, 13))
    with pytest.raises(DutyError):
        periods.close_collecting(p)


def test_open_rejected_when_published(db):
    p = Period.objects.create(name="a", start_date=d(11, 9), end_date=d(11, 13), status=S.PUBLISHED)
    with pytest.raises(DutyError):
        periods.open_collecting(p)


def test_missing_dates(make_member):
    p = Period.objects.create(name="a", start_date=d(11, 9), end_date=d(11, 10))
    Commute.objects.create(period=p, date=d(11, 9), member=make_member("가", dept="MEMS"), shift="normal")
    missing = periods.missing_dates(p)
    assert missing["MEMS"] == [d(11, 10)]
    assert missing["UI"] == [d(11, 9), d(11, 10)]
```

`tests/test_collect.py`
```python
from datetime import date

import pytest
from django.core.exceptions import PermissionDenied

from duty.csv_io import CsvInvalid
from duty.errors import DutyError
from duty.models import Period
from duty.services import collect

S = Period.Status
CSV = 'date,새벽,정상,석식교대,야간\n2026-11-09,가,"나,다",,\n'


@pytest.fixture
def setup(depts, make_member, fixed_today):
    fixed_today(date(2026, 11, 1))
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13), status=S.COLLECTING)
    mgr = make_member("담당", user=True)
    depts["MEMS"].managers.add(mgr)
    for n in ["가", "나", "다"]:
        make_member(n)
    make_member("타부서", dept="MD")
    return p, depts["MEMS"], mgr.user


def reasons(exc):
    return " / ".join(e.reason for e in exc.value.errors)


def test_apply_csv_writes_rows(setup):
    p, dept, user = setup
    assert collect.apply_csv(user, p, dept, CSV.encode()) == 3
    t = collect.load_table(p, dept)
    assert t[date(2026, 11, 9)] == {"dawn": ["가"], "normal": ["나", "다"]}


def test_apply_replaces_whole_department(setup):
    p, dept, user = setup
    collect.apply_csv(user, p, dept, CSV.encode())
    collect.apply_csv(user, p, dept, "date,새벽,정상,석식교대,야간\n2026-11-10,,가,,\n".encode())
    assert collect.load_table(p, dept) == {date(2026, 11, 10): {"normal": ["가"]}}


def test_rejects_other_department_member(setup):
    p, dept, user = setup
    with pytest.raises(CsvInvalid) as e:
        collect.apply_csv(user, p, dept, "date,새벽,정상,석식교대,야간\n2026-11-09,타부서,,,\n".encode())
    assert "재직 멤버가 아닙니다" in reasons(e)


def test_rejects_double_shift(setup):
    p, dept, user = setup
    with pytest.raises(CsvInvalid) as e:
        collect.apply_csv(user, p, dept, "date,새벽,정상,석식교대,야간\n2026-11-09,가,,,가\n".encode())
    assert "중복" in reasons(e)


def test_rejects_weekend_and_out_of_period(setup):
    p, dept, user = setup
    with pytest.raises(CsvInvalid) as e:
        collect.apply_csv(user, p, dept, "date,새벽,정상,석식교대,야간\n2026-11-14,가,,,\n2026-11-16,나,,,\n".encode())
    assert len(e.value.errors) == 2


def test_rejects_shift_department_does_not_have(setup, depts, make_member):
    p, _, user = setup
    make_member("유아이", dept="UI")
    table = {date(2026, 11, 9): {"dawn": ["유아이"]}}
    with pytest.raises(CsvInvalid) as e:
        collect.apply_table(user, p, depts["UI"], table)
    assert "출근조가 없습니다" in reasons(e)


def test_errors_mean_nothing_is_written(setup):
    p, dept, user = setup
    collect.apply_csv(user, p, dept, CSV.encode())
    with pytest.raises(CsvInvalid):
        collect.apply_csv(user, p, dept, "date,새벽,정상,석식교대,야간\n2026-11-10,없는사람,,,\n".encode())
    assert date(2026, 11, 9) in collect.load_table(p, dept)


def test_non_manager_forbidden(setup, make_member):
    p, dept, _ = setup
    other = make_member("남", user=True)
    with pytest.raises(PermissionDenied):
        collect.apply_csv(other.user, p, dept, CSV.encode())


def test_requires_collecting(setup):
    p, dept, user = setup
    p.status = S.CLOSED
    p.save()
    with pytest.raises(DutyError):
        collect.apply_csv(user, p, dept, CSV.encode())


def test_past_dates_locked_for_manager_not_admin(setup, fixed_today, admin_user):
    p, dept, user = setup
    collect.apply_csv(user, p, dept, CSV.encode())
    fixed_today(date(2026, 11, 11))
    changed = "date,새벽,정상,석식교대,야간\n2026-11-09,나,가,,\n".encode()
    with pytest.raises(CsvInvalid) as e:
        collect.apply_csv(user, p, dept, changed)
    assert "지난 날짜" in reasons(e)
    removed_past = "date,새벽,정상,석식교대,야간\n2026-11-12,가,,,\n".encode()
    with pytest.raises(CsvInvalid):
        collect.apply_csv(user, p, dept, removed_past)  # 11/9 를 지우는 것도 수정
    assert collect.apply_csv(admin_user, p, dept, changed) == 2


def test_export_has_current_values(setup):
    p, dept, user = setup
    collect.apply_csv(user, p, dept, CSV.encode())
    text = collect.export_csv(p, dept).decode("utf-8-sig")
    assert "2026-11-09,월,가,\"나, 다\",," in text
    assert text.count("\n") == 6  # 헤더 + 평일 5일


def test_progress(setup):
    p, dept, user = setup
    collect.apply_csv(user, p, dept, CSV.encode())
    pr = collect.progress(p)
    assert pr["MEMS"] == (1, 5) and pr["UI"] == (0, 5)
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_periods.py tests/test_collect.py -v`
Expected: FAIL (`ImportError: cannot import name 'periods'`)

- [ ] **Step 3: 구현**

`duty/services/__init__.py`: 빈 파일.

`duty/services/periods.py`
```python
from collections import defaultdict
from datetime import date

from django.db import transaction

from ..errors import DutyError
from ..models import Commute, ControlDuty, Department, Period

S = Period.Status


def save_draft(period: Period) -> Period:
    if period.pk and Period.objects.get(pk=period.pk).status != S.DRAFT:
        raise DutyError("기간은 작성 중(draft) 상태에서만 수정할 수 있습니다.")
    if period.start_date > period.end_date:
        raise DutyError("시작일이 종료일보다 늦습니다.")
    clash = (
        Period.objects.exclude(pk=period.pk)
        .exclude(status=S.PUBLISHED)
        .filter(start_date__lte=period.end_date, end_date__gte=period.start_date)
        .first()
    )
    if clash:
        raise DutyError(f"배포 전 회차와 기간이 겹칩니다: {clash.name}")
    period.save()
    return period


@transaction.atomic
def open_collecting(period: Period) -> None:
    if period.status not in {S.DRAFT, S.CLOSED, S.GENERATED}:
        raise DutyError("이 상태에서는 취합을 열 수 없습니다.")
    ControlDuty.objects.filter(period=period).delete()
    period.status, period.seed, period.generated_at = S.COLLECTING, None, None
    period.save()


def close_collecting(period: Period) -> None:
    if period.status != S.COLLECTING:
        raise DutyError("취합 중인 회차만 마감할 수 있습니다.")
    period.status = S.CLOSED
    period.save()


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

`duty/services/collect.py`
```python
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count

from .. import perms
from ..csv_io import CommuteTable, CsvError, CsvInvalid, export_commute_csv, parse_commute_csv
from ..errors import DutyError
from ..models import Commute, Department, Member, Period
from ..shifts import COMMUTE_SHIFTS


def _require_input(user, period: Period, dept: Department) -> None:
    if not perms.can_input_department(user, dept):
        raise PermissionDenied("이 부서의 출근표를 입력할 권한이 없습니다.")
    if period.status != Period.Status.COLLECTING:
        raise DutyError("취합 중인 회차가 아닙니다.")


def load_table(period: Period, dept: Department) -> CommuteTable:
    table: CommuteTable = {}
    rows = (
        Commute.objects.filter(period=period, member__department=dept)
        .select_related("member")
        .order_by("date", "member__code")
    )
    for c in rows:
        table.setdefault(c.date, {}).setdefault(c.shift, []).append(c.member.name)
    return table


def _norm(day: dict[str, list[str]]) -> dict[str, list[str]]:
    return {k: sorted(v) for k, v in day.items() if v}


def validate_table(user, period: Period, dept: Department, table: CommuteTable, full: bool) -> list[CsvError]:
    errors: list[CsvError] = []
    valid_dates = set(period.dates())
    shift_keys = dept.shift_keys()
    members = set(Member.objects.filter(department=dept, is_active=True).values_list("name", flat=True))
    for d in sorted(table):
        col = d.isoformat()
        if d not in valid_dates:
            errors.append(CsvError(0, col, "회차 기간의 평일이 아닙니다."))
            continue
        seen: dict[str, str] = {}
        for key, names in table[d].items():
            if names and key not in shift_keys:
                errors.append(CsvError(0, col, f"{dept.name}에는 {COMMUTE_SHIFTS[key]} 출근조가 없습니다."))
                continue
            for name in names:
                if name not in members:
                    errors.append(CsvError(0, col, f"{dept.name}의 재직 멤버가 아닙니다: {name}"))
                elif name in seen:
                    errors.append(CsvError(0, col, f"{name}: {COMMUTE_SHIFTS[seen[name]]}와 {COMMUTE_SHIFTS[key]}에 중복"))
                else:
                    seen[name] = key
    if not perms.is_admin(user):
        existing = load_table(period, dept)
        today = perms.today()
        candidates = set(table) | (set(existing) if full else set())
        for d in sorted(x for x in candidates if x < today):
            if _norm(table.get(d, {})) != _norm(existing.get(d, {})):
                errors.append(CsvError(0, d.isoformat(), "지난 날짜는 어드민만 수정할 수 있습니다."))
    return errors


@transaction.atomic
def apply_table(user, period: Period, dept: Department, table: CommuteTable) -> int:
    _require_input(user, period, dept)
    errors = validate_table(user, period, dept, table, full=True)
    if errors:
        raise CsvInvalid(errors)
    by_name = {m.name: m for m in Member.objects.filter(department=dept)}
    Commute.objects.filter(period=period, member__department=dept).delete()
    rows = [
        Commute(period=period, date=d, member=by_name[n], shift=key)
        for d, day in table.items()
        for key, names in day.items()
        for n in names
    ]
    Commute.objects.bulk_create(rows)
    return len(rows)


def apply_csv(user, period: Period, dept: Department, raw: bytes) -> int:
    _require_input(user, period, dept)
    return apply_table(user, period, dept, parse_commute_csv(raw, dept.shift_keys()))


def export_csv(period: Period, dept: Department) -> bytes:
    return export_commute_csv(period.dates(), dept.shift_keys(), load_table(period, dept))


def progress(period: Period) -> dict[str, tuple[int, int]]:
    total = len(period.dates())
    filled = dict(
        Commute.objects.filter(period=period)
        .values("member__department")
        .annotate(n=Count("date", distinct=True))
        .values_list("member__department", "n")
    )
    return {d.code: (filled.get(d.code, 0), total) for d in Department.objects.order_by("code")}
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_periods.py tests/test_collect.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add duty/services tests/test_periods.py tests/test_collect.py
git commit -m "feat: 회차 상태 전환과 부서 출근표 반영"
```

---

### Task 6: 생성 실행과 배포 덮어쓰기

**Files:**
- Create: `duty/services/generate.py`, `duty/services/publish.py`
- Test: `tests/test_generate.py`, `tests/test_publish.py`

**Interfaces:**
- Consumes: `generator.generate_control_duty`, `GenerationError`, `periods.missing_dates`
- Produces:
  - `generate.run_generation(period, seed: int | None = None) -> GenerationOutput` (DutyError: 상태/빈 날짜; GenerationError 그대로 전파)
  - `publish.PublishPreview(overwrite_from: date, overwrite_to: date, periods: list[str], discarded_changes: int)`
  - `publish.preview_publish(period, overwrite_from: date) -> PublishPreview`
  - `publish.publish(period, overwrite_from: date) -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_generate.py`
```python
from datetime import date

import pytest

from duty.errors import DutyError
from duty.generator import GenerationError
from duty.models import Commute, ControlDuty, Period
from duty.services.generate import run_generation

S = Period.Status


@pytest.fixture
def closed_period(make_member):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 13), status=S.CLOSED)
    normal = [make_member(f"N{i}", dept="MEMS") for i in range(7)]
    dinner = [make_member(f"D{i}", dept="TMCH") for i in range(7)]
    md = make_member("엠", dept="MD", type="직원")
    ui = make_member("유", dept="UI", type="직원")
    for d in p.dates():
        for m in normal + [md, ui]:
            Commute.objects.create(period=p, date=d, member=m, shift="normal")
        for m in dinner:
            Commute.objects.create(period=p, date=d, member=m, shift="dinner")
    return p


def test_generation_writes_duties(closed_period):
    out = run_generation(closed_period, seed=5)
    closed_period.refresh_from_db()
    assert closed_period.status == S.GENERATED and closed_period.seed == 5
    assert ControlDuty.objects.filter(period=closed_period).count() == 5 * 10
    assert not ControlDuty.objects.filter(period=closed_period, member__type="직원").exists()
    assert out.reached


def test_regenerate_replaces(closed_period):
    run_generation(closed_period, seed=1)
    run_generation(closed_period, seed=2)
    assert ControlDuty.objects.filter(period=closed_period).count() == 50


def test_missing_department_dates_block_generation(closed_period):
    Commute.objects.filter(period=closed_period, member__department="UI", date=date(2026, 11, 13)).delete()
    with pytest.raises(DutyError) as e:
        run_generation(closed_period)
    assert "UI" in str(e.value)


def test_wrong_status(closed_period):
    closed_period.status = S.COLLECTING
    closed_period.save()
    with pytest.raises(DutyError):
        run_generation(closed_period)


def test_no_candidates_raises_generation_error(closed_period):
    Commute.objects.filter(period=closed_period, date=date(2026, 11, 9), shift="dinner").update(shift="night")
    with pytest.raises(GenerationError):
        run_generation(closed_period, seed=1)
    closed_period.refresh_from_db()
    assert closed_period.status == S.CLOSED
```

`tests/test_publish.py`
```python
from datetime import date

import pytest

from duty.errors import DutyError
from duty.models import ChangeLog, Commute, ControlDuty, Period
from duty.services.publish import preview_publish, publish
from duty.shifts import weekdays

S = Period.Status


def d(m, day):
    return date(2026, m, day)


def make_period(name, start, end, status, member):
    p = Period.objects.create(name=name, start_date=start, end_date=end, status=status)
    for x in weekdays(start, end):
        Commute.objects.create(period=p, date=x, member=member, shift="normal")
        ControlDuty.objects.create(period=p, date=x, slot=0, member=member)
    return p


def dates_of(p):
    return sorted(set(Commute.objects.filter(period=p).values_list("date", flat=True)))


@pytest.fixture
def ab(make_member):
    a = make_period("A", d(11, 2), d(11, 27), S.PUBLISHED, make_member("가"))
    b = make_period("B", d(11, 16), d(12, 11), S.GENERATED, make_member("나"))
    return a, b


def test_publish_overwrites_from_selected_date(ab):
    a, b = ab
    publish(b, d(11, 18))
    b.refresh_from_db()
    assert b.status == S.PUBLISHED and b.overwrite_from == d(11, 18)
    assert dates_of(a)[-1] == d(11, 17)
    assert dates_of(b)[0] == d(11, 18)
    assert not ControlDuty.objects.filter(period=a, date__gte=d(11, 18)).exists()


def test_publish_inside_keeps_tail_of_old(make_member):
    a = make_period("A", d(11, 2), d(11, 27), S.PUBLISHED, make_member("가"))
    b = make_period("B", d(11, 16), d(11, 20), S.GENERATED, make_member("나"))
    publish(b, d(11, 16))
    assert d(11, 23) in dates_of(a) and d(11, 16) not in dates_of(a)


def test_preview_counts_discarded_changes(ab):
    a, b = ab
    m = Commute.objects.filter(period=a).first().member
    ChangeLog.objects.create(period=a, date=d(11, 19), cell="normal", before=m, after=None)
    ChangeLog.objects.create(period=a, date=d(11, 10), cell="normal", before=m, after=None)
    pv = preview_publish(b, d(11, 18))
    assert pv.discarded_changes == 1
    assert pv.periods == ["A"]
    assert (pv.overwrite_from, pv.overwrite_to) == (d(11, 18), d(12, 11))


def test_requires_generated(ab):
    _, b = ab
    b.status = S.CLOSED
    b.save()
    with pytest.raises(DutyError):
        publish(b, d(11, 16))


def test_overwrite_from_must_be_in_period(ab):
    _, b = ab
    with pytest.raises(DutyError):
        publish(b, d(11, 13))
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_generate.py tests/test_publish.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`duty/services/generate.py`
```python
import random
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from ..errors import DutyError
from ..generator import GenerationOutput, generate_control_duty
from ..models import Commute, ControlDuty, Member, Period
from ..shifts import DEVELOPER
from .periods import missing_dates

S = Period.Status


def run_generation(period: Period, seed: int | None = None) -> GenerationOutput:
    if period.status not in {S.CLOSED, S.GENERATED}:
        raise DutyError("마감된 회차만 생성할 수 있습니다.")
    missing = missing_dates(period)
    if missing:
        detail = ", ".join(f"{code} {len(ds)}일" for code, ds in missing.items())
        raise DutyError(f"출근표가 비어 있는 날짜가 있습니다: {detail}")
    if seed is None:
        seed = random.SystemRandom().randrange(2**31)

    commutes: dict = defaultdict(lambda: defaultdict(set))
    for d, shift, code in Commute.objects.filter(period=period).values_list("date", "shift", "member__code"):
        commutes[d][shift].add(code)
    developers = set(Member.objects.filter(type=DEVELOPER, is_active=True).values_list("code", flat=True))
    out = generate_control_duty(period.dates(), commutes, developers, seed)  # GenerationError 전파

    by_code = {m.code: m for m in Member.objects.filter(code__in=out.counts)}
    with transaction.atomic():
        ControlDuty.objects.filter(period=period).delete()
        ControlDuty.objects.bulk_create(
            ControlDuty(period=period, date=d, slot=i, member=by_code[code])
            for d, picked in out.assignments.items()
            for i, code in enumerate(picked)
        )
        period.status, period.seed, period.generated_at = S.GENERATED, seed, timezone.now()
        period.save()
    return out
```

`duty/services/publish.py`
```python
from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.utils import timezone

from ..errors import DutyError
from ..models import ChangeLog, Commute, ControlDuty, Period

S = Period.Status


@dataclass(frozen=True)
class PublishPreview:
    overwrite_from: date
    overwrite_to: date
    periods: list[str]
    discarded_changes: int


def _validate(period: Period, overwrite_from: date) -> None:
    if period.status != S.GENERATED:
        raise DutyError("생성이 끝난 회차만 배포할 수 있습니다.")
    if not period.start_date <= overwrite_from <= period.end_date:
        raise DutyError("덮어쓰기 시작일은 회차 기간 안이어야 합니다.")


def _others(period: Period):
    return Period.objects.filter(status=S.PUBLISHED).exclude(pk=period.pk)


def preview_publish(period: Period, overwrite_from: date) -> PublishPreview:
    _validate(period, overwrite_from)
    rng = {"date__gte": overwrite_from, "date__lte": period.end_date}
    names = set(Commute.objects.filter(period__in=_others(period), **rng).values_list("period__name", flat=True))
    names |= set(ControlDuty.objects.filter(period__in=_others(period), **rng).values_list("period__name", flat=True))
    discarded = ChangeLog.objects.filter(period__in=_others(period), **rng).count()
    return PublishPreview(overwrite_from, period.end_date, sorted(names), discarded)


@transaction.atomic
def publish(period: Period, overwrite_from: date) -> None:
    _validate(period, overwrite_from)
    for model in (Commute, ControlDuty):
        model.objects.filter(period__in=_others(period), date__gte=overwrite_from, date__lte=period.end_date).delete()
        model.objects.filter(period=period, date__lt=overwrite_from).delete()
    period.status, period.overwrite_from, period.published_at = S.PUBLISHED, overwrite_from, timezone.now()
    period.save()
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_generate.py tests/test_publish.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add duty/services/generate.py duty/services/publish.py tests/test_generate.py tests/test_publish.py
git commit -m "feat: 당번 생성 실행과 배포 덮어쓰기"
```

---

### Task 7: 조회 모델과 근무 변경

**Files:**
- Create: `duty/services/roster.py`, `duty/services/changes.py`
- Test: `tests/test_roster.py`, `tests/test_changes.py`

**Interfaces:**
- Consumes: models, `perms`, `shifts.*`, `DutyError`
- Produces:
  - `roster.chain(current: list[str], logs: list[tuple[str|None, str|None]]) -> tuple[list[str], list[str], dict[str, str]]` (표시 라벨, 제거된 사람 라벨, 이름→직전 근무자)
  - `roster.Cell(labels: list[str], removed: list[str], changed: bool)`
  - `roster.Day(date, period_id, cells: dict[str, Cell], members: dict[str, list[str]], replaced: dict[tuple[str,str], str])`
  - `roster.published_days(start: date|None = None, end: date|None = None) -> list[Day]`
  - `roster.find_day(d) -> Day|None`
  - `roster.api_assignments(start, end) -> list[dict]` (`date`, `shift`, `name`, `replaced`)
  - `roster.member_schedule(member, start: date) -> list[tuple[date, list[str]]]`
  - `roster.DEPT_VIEWS: dict[str, tuple[str, list[str]]]`, `roster.department_table(key, start=None, end=None) -> tuple[str, list[str], list[list[str]]]`
  - `changes.ChangeResult(warnings: list[str])`
  - `changes.change_cell(user, d, cell, before: Member|None, after: Member|None) -> ChangeResult`
  - `changes.swap(user, d, cell_a, a: Member, cell_b, b: Member) -> ChangeResult`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_roster.py`
```python
from datetime import date

from duty.models import ChangeLog, Commute, ControlDuty, Period
from duty.services.roster import api_assignments, chain, department_table, member_schedule, published_days

S = Period.Status
D = date(2026, 11, 10)


def test_chain_replace_twice():
    labels, removed, replaced = chain(["C"], [("A", "B"), ("B", "C")])
    assert labels == ["A>B>C"] and removed == [] and replaced["C"] == "B"


def test_chain_add_and_remove():
    labels, removed, _ = chain(["B", "X"], [(None, "B"), ("A", None)])
    assert labels == ["+B", "X"] and removed == ["A"]


def make_published(make_member):
    p = Period.objects.create(name="p", start_date=D, end_date=D, status=S.PUBLISHED)
    staff = make_member("직원1", type="직원")
    a, b, c = make_member("가"), make_member("나", dept="TMCH"), make_member("다")
    Commute.objects.create(period=p, date=D, member=staff, shift="normal")
    Commute.objects.create(period=p, date=D, member=b, shift="normal")
    Commute.objects.create(period=p, date=D, member=c, shift="dawn")
    ControlDuty.objects.create(period=p, date=D, slot=0, member=b)
    ChangeLog.objects.create(period=p, date=D, cell="normal", before=a, after=b)
    return p


def test_published_days_builds_cells(make_member):
    make_published(make_member)
    [day] = published_days()
    assert day.members["normal"] == ["직원1", "나"]
    assert day.cells["normal"].labels == ["직원1", "가>나"] and day.cells["normal"].changed
    assert day.cells["slot0"].labels == ["나"] and not day.cells["slot0"].changed


def test_unpublished_is_hidden(make_member):
    p = make_published(make_member)
    p.status = S.GENERATED
    p.save()
    assert published_days() == []


def test_api_assignments(make_member):
    make_published(make_member)
    rows = api_assignments(None, None)
    assert {"date": "2026-11-10", "shift": "정상", "name": "나", "replaced": "가"} in rows
    assert {"date": "2026-11-10", "shift": "08:30~09:30", "name": "나", "replaced": None} in rows
    assert {"date": "2026-11-10", "shift": "새벽", "name": "다", "replaced": None} in rows


def test_member_schedule(make_member):
    make_published(make_member)
    from duty.models import Member

    assert member_schedule(Member.objects.get(name="나"), D) == [(D, ["정상", "08:30~09:30"])]


def test_department_table_it_splits_type(make_member):
    make_published(make_member)
    title, header, rows = department_table("it")
    assert title == "IT운영본부"
    assert header[:3] == ["날짜", "요일", "구분"] and header[3] == "새벽 매칭엔진실"
    staff_row, dev_row = rows
    assert staff_row[2] == "직원" and dev_row[2] == "개발자"
    normal_tmch = header.index("정상 매매지원실")
    assert dev_row[normal_tmch] == "나"
    assert staff_row[header.index("정상 매칭엔진실")] == "직원1"
```

`tests/test_changes.py`
```python
from datetime import date

import pytest
from django.core.exceptions import PermissionDenied

from duty.errors import DutyError
from duty.models import ChangeLog, Commute, ControlDuty, Period
from duty.services import changes
from duty.services.roster import find_day

S = Period.Status
D = date(2026, 11, 10)


@pytest.fixture
def world(make_member, fixed_today):
    fixed_today(D)
    p = Period.objects.create(name="p", start_date=D, end_date=D, status=S.PUBLISHED)
    m = {n: make_member(n, user=True) for n in ["가", "나", "다", "라"]}
    m["직원"] = make_member("직원", type="직원", user=True)
    Commute.objects.create(period=p, date=D, member=m["가"], shift="normal")
    Commute.objects.create(period=p, date=D, member=m["나"], shift="night")
    Commute.objects.create(period=p, date=D, member=m["라"], shift="dinner")
    ControlDuty.objects.create(period=p, date=D, slot=0, member=m["가"])
    ControlDuty.objects.create(period=p, date=D, slot=1, member=m["라"])
    return p, m


def test_replace_commute(world):
    p, m = world
    changes.change_cell(m["다"].user, D, "normal", m["가"], m["다"])
    assert Commute.objects.get(period=p, date=D, member=m["다"]).shift == "normal"
    assert find_day(D).cells["normal"].labels == ["가>다"]
    assert ChangeLog.objects.get().by == m["다"].user


def test_removing_commute_warns_when_member_has_duty(world):
    _, m = world
    r = changes.change_cell(m["가"].user, D, "normal", m["가"], None)
    assert any("관제" in w for w in r.warnings)
    assert find_day(D).cells["normal"].removed == ["가"]


def test_add_commute(world):
    _, m = world
    changes.change_cell(m["다"].user, D, "dawn", None, m["다"])
    assert find_day(D).cells["dawn"].labels == ["+다"]


def test_after_already_in_other_shift_rejected(world):
    _, m = world
    with pytest.raises(DutyError):
        changes.change_cell(m["가"].user, D, "normal", m["가"], m["나"])


def test_before_not_in_cell_rejected(world):
    _, m = world
    with pytest.raises(DutyError):
        changes.change_cell(m["가"].user, D, "dawn", m["가"], m["다"])


def test_duty_replace_warns_on_ineligible(world):
    p, m = world
    r = changes.change_cell(m["가"].user, D, "slot0", m["가"], m["직원"])
    assert ControlDuty.objects.get(period=p, date=D, slot=0).member == m["직원"]
    assert len(r.warnings) == 2  # 개발자 아님 + 출근조 없음


def test_duty_only_replace(world):
    _, m = world
    with pytest.raises(DutyError):
        changes.change_cell(m["가"].user, D, "slot0", m["가"], None)


def test_duty_after_in_other_slot_rejected(world):
    _, m = world
    with pytest.raises(DutyError):
        changes.change_cell(m["가"].user, D, "slot0", m["가"], m["라"])


def test_swap_commute(world):
    p, m = world
    changes.swap(m["가"].user, D, "normal", m["가"], "night", m["나"])
    assert Commute.objects.get(period=p, date=D, member=m["가"]).shift == "night"
    day = find_day(D)
    assert day.cells["normal"].labels == ["가>나"] and day.cells["night"].labels == ["나>가"]
    assert ChangeLog.objects.count() == 2


def test_swap_duty(world):
    p, m = world
    changes.swap(m["가"].user, D, "slot0", m["가"], "slot1", m["라"])
    assert ControlDuty.objects.get(period=p, date=D, slot=0).member == m["라"]
    assert ControlDuty.objects.get(period=p, date=D, slot=1).member == m["가"]


def test_swap_across_kinds_rejected(world):
    _, m = world
    with pytest.raises(DutyError):
        changes.swap(m["가"].user, D, "normal", m["가"], "slot1", m["라"])


def test_past_date_admin_only(world, fixed_today, admin_user):
    _, m = world
    fixed_today(date(2026, 11, 11))
    with pytest.raises(PermissionDenied):
        changes.change_cell(m["다"].user, D, "normal", m["가"], m["다"])
    changes.change_cell(admin_user, D, "normal", m["가"], m["다"])


def test_unpublished_date_rejected(world):
    _, m = world
    with pytest.raises(DutyError):
        changes.change_cell(m["가"].user, date(2026, 11, 11), "normal", None, m["다"])


def test_inactive_after_rejected(world):
    _, m = world
    m["다"].is_active = False
    m["다"].save()
    with pytest.raises(DutyError):
        changes.change_cell(m["가"].user, D, "dawn", None, m["다"])
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_roster.py tests/test_changes.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`duty/services/roster.py`
```python
"""배포된 근무표 읽기 모델. 화면·API·통계가 공통으로 쓴다."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from ..models import ChangeLog, Commute, ControlDuty, Department, Member, Period
from ..shifts import CELLS, COMMUTE_SHIFTS, DAY_LABELS, DEVELOPER, STAFF, cell_label, slot_cell

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
            if before:
                replaced[after] = before
        elif prev:
            removed.append(prev)
    return [label.get(n, n) for n in current], removed, replaced


def published_days(start: date | None = None, end: date | None = None) -> list[Day]:
    def scoped(qs):
        qs = qs.filter(period__status=Period.Status.PUBLISHED)
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        return qs

    raw: dict[date, dict] = {}

    def slot(d, pid):
        return raw.setdefault(d, {"period": pid, "cells": defaultdict(list)})

    commutes = scoped(Commute.objects).order_by("date", "member__code")
    for d, pid, shift, name in commutes.values_list("date", "period_id", "shift", "member__name"):
        slot(d, pid)["cells"][shift].append(name)
    for d, pid, i, name in scoped(ControlDuty.objects).values_list("date", "period_id", "slot", "member__name"):
        slot(d, pid)["cells"][slot_cell(i)].append(name)

    logs: dict[tuple[date, str], list[Log]] = defaultdict(list)
    rows = scoped(ChangeLog.objects).order_by("at", "id").values_list("date", "period_id", "cell", "before__name", "after__name")
    for d, pid, cell, before, after in rows:
        if d in raw and raw[d]["period"] == pid:  # 덮어쓰인 회차의 이력은 숨긴다
            logs[(d, cell)].append((before, after))

    days = []
    for d in sorted(raw):
        cells, members, replaced = {}, {}, {}
        for cell in CELLS:
            current = raw[d]["cells"].get(cell, [])
            cell_logs = logs.get((d, cell), [])
            labels, removed, rep = chain(current, cell_logs)
            cells[cell] = Cell(labels, removed, bool(cell_logs))
            members[cell] = current
            replaced.update({(cell, name): prev for name, prev in rep.items()})
        days.append(Day(d, raw[d]["period"], cells, members, replaced))
    return days


def find_day(d: date) -> Day | None:
    days = published_days(d, d)
    return days[0] if days else None


def api_assignments(start: date | None, end: date | None) -> list[dict]:
    return [
        {"date": day.date.isoformat(), "shift": cell_label(cell), "name": name, "replaced": day.replaced.get((cell, name))}
        for day in published_days(start, end)
        for cell in CELLS
        for name in day.members[cell]
    ]


def member_schedule(member: Member, start: date) -> list[tuple[date, list[str]]]:
    out = []
    for day in published_days(start, None):
        labels = [cell_label(c) for c in CELLS if member.name in day.members[c]]
        if labels:
            out.append((day.date, labels))
    return out


DEPT_VIEWS: dict[str, tuple[str, list[str]]] = {
    "it": ("IT운영본부", ["MEMS", "TMCH"]),
    "md": ("정보분배", ["MD"]),
    "ui": ("UI", ["UI"]),
}


def department_table(key: str, start: date | None = None, end: date | None = None):
    title, codes = DEPT_VIEWS[key]
    depts = [Department.objects.get(code=c) for c in codes]
    info = {m.name: (m.department_id, m.type) for m in Member.objects.all()}
    shifts = [s for s in COMMUTE_SHIFTS if any(s in d.shift_keys() for d in depts)]
    split = len(depts) > 1
    header = ["날짜", "요일", *(["구분"] if split else [])]
    header += [f"{COMMUTE_SHIFTS[s]} {d.name}" if split else COMMUTE_SHIFTS[s] for s in shifts for d in depts]
    rows = []
    for day in published_days(start, end):
        for i, t in enumerate([STAFF, DEVELOPER] if split else [None]):
            row = [day.date.isoformat() if i == 0 else "", DAY_LABELS[day.date.weekday()] if i == 0 else ""]
            if split:
                row.append(t)
            for s in shifts:
                for d in depts:
                    row.append(", ".join(
                        n for n in day.members[s]
                        if info.get(n, (None, None))[0] == d.code and (t is None or info[n][1] == t)
                    ))
            rows.append(row)
    return title, header, rows
```

`duty/services/changes.py`
```python
from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.db.models import Q

from .. import perms
from ..errors import DutyError
from ..models import ChangeLog, Commute, ControlDuty, Member, Period
from ..shifts import COMMUTE_SHIFTS, CONTROL_SLOTS, DEVELOPER, cell_label, is_slot_cell, slot_index


@dataclass
class ChangeResult:
    warnings: list[str]


def _owner(d: date) -> Period:
    p = (
        Period.objects.filter(status=Period.Status.PUBLISHED)
        .filter(Q(commute__date=d) | Q(controlduty__date=d))
        .distinct()
        .first()
    )
    if p is None:
        raise DutyError("배포된 근무표에 없는 날짜입니다.")
    return p


def _eligibility_warnings(period: Period, d: date, slot: int, m: Member) -> list[str]:
    label, allowed = CONTROL_SLOTS[slot]
    out = []
    if m.type != DEVELOPER:
        out.append(f"{m.name}은(는) 개발자가 아닙니다.")
    shift = Commute.objects.filter(period=period, date=d, member=m).values_list("shift", flat=True).first()
    if shift not in allowed:
        out.append(f"{m.name}의 그날 출근조({COMMUTE_SHIFTS.get(shift, '없음')})는 {label} 관제 자격이 아닙니다.")
    return out


def _check_active(m: Member | None) -> None:
    if m is not None and not m.is_active:
        raise DutyError(f"{m.name}은(는) 재직 중이 아닙니다.")


@transaction.atomic
def change_cell(user, d: date, cell: str, before: Member | None, after: Member | None) -> ChangeResult:
    perms.assert_can_edit_date(user, d)
    period = _owner(d)
    if (before is None and after is None) or before == after:
        raise DutyError("변경할 내용이 없습니다.")
    _check_active(after)
    warnings: list[str] = []
    if is_slot_cell(cell):
        slot = slot_index(cell)
        if before is None or after is None:
            raise DutyError("관제 칸은 교체만 할 수 있습니다.")
        row = ControlDuty.objects.filter(period=period, date=d, slot=slot).first()
        if row is None or row.member_id != before.pk:
            raise DutyError(f"{before.name}은(는) 이 칸에 없습니다.")
        if ControlDuty.objects.filter(period=period, date=d, member=after).exists():
            raise DutyError(f"{after.name}은(는) 그날 이미 다른 관제 칸에 있습니다. 맞교환을 사용하세요.")
        row.member = after
        row.save()
        warnings = _eligibility_warnings(period, d, slot, after)
    else:
        if cell not in COMMUTE_SHIFTS:
            raise DutyError("알 수 없는 칸입니다.")
        row = None
        if before is not None:
            row = Commute.objects.filter(period=period, date=d, member=before, shift=cell).first()
            if row is None:
                raise DutyError(f"{before.name}은(는) 이 칸에 없습니다.")
        if after is not None and Commute.objects.filter(period=period, date=d, member=after).exists():
            raise DutyError(f"{after.name}은(는) 그날 이미 다른 출근조에 있습니다. 맞교환을 사용하세요.")
        if row is not None:
            row.delete()
            duty = ControlDuty.objects.filter(period=period, date=d, member=before).first()
            if duty is not None:
                warnings.append(f"{before.name}은(는) {CONTROL_SLOTS[duty.slot][0]} 관제 칸에 남아 있습니다.")
        if after is not None:
            Commute.objects.create(period=period, date=d, member=after, shift=cell)
    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell, before=before, after=after)
    return ChangeResult(warnings)


@transaction.atomic
def swap(user, d: date, cell_a: str, a: Member, cell_b: str, b: Member) -> ChangeResult:
    perms.assert_can_edit_date(user, d)
    period = _owner(d)
    if a == b or cell_a == cell_b:
        raise DutyError("서로 다른 두 칸의 서로 다른 사람을 골라 주세요.")
    if is_slot_cell(cell_a) != is_slot_cell(cell_b):
        raise DutyError("출근조끼리 또는 관제 칸끼리만 맞교환할 수 있습니다.")
    warnings: list[str] = []
    if is_slot_cell(cell_a):
        sa, sb = slot_index(cell_a), slot_index(cell_b)
        ra = ControlDuty.objects.filter(period=period, date=d, slot=sa, member=a).first()
        rb = ControlDuty.objects.filter(period=period, date=d, slot=sb, member=b).first()
        if ra is None or rb is None:
            raise DutyError("선택한 사람이 해당 칸에 없습니다.")
        ra.delete()
        rb.delete()
        ControlDuty.objects.create(period=period, date=d, slot=sa, member=b)
        ControlDuty.objects.create(period=period, date=d, slot=sb, member=a)
        warnings = _eligibility_warnings(period, d, sa, b) + _eligibility_warnings(period, d, sb, a)
    else:
        ra = Commute.objects.filter(period=period, date=d, member=a, shift=cell_a).first()
        rb = Commute.objects.filter(period=period, date=d, member=b, shift=cell_b).first()
        if ra is None or rb is None:
            raise DutyError("선택한 사람이 해당 칸에 없습니다.")
        ra.shift, rb.shift = cell_b, cell_a
        ra.save()
        rb.save()
    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell_a, before=a, after=b)
    ChangeLog.objects.create(by=user, period=period, date=d, cell=cell_b, before=b, after=a)
    return ChangeResult(warnings)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_roster.py tests/test_changes.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add duty/services/roster.py duty/services/changes.py tests/test_roster.py tests/test_changes.py
git commit -m "feat: 배포 근무표 조회 모델과 근무 변경(교체·추가·제거·맞교환)"
```

---

### Task 8: 당번 통계

**Files:**
- Create: `duty/services/stats.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: `roster.published_days`
- Produces:
  - `MemberStat(name, duty, dawn, night)` + `.total` property
  - `Summary(mean: float, stdev: float, spread: int)`
  - `member_stats(start, end) -> tuple[list[MemberStat], Summary|None, Summary|None]` (관제 요약, 합계 요약). 대상 = 재직 개발자 + 기간 중 관제 배정된 사람
  - `period_duty_counts(period) -> tuple[list[tuple[str,int]], int, bool]` (이름별 횟수 오름차순, 편차, 목표 도달)

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_stats.py`

```python
from datetime import date

from duty.models import Commute, ControlDuty, Period
from duty.services.stats import member_stats, period_duty_counts

S = Period.Status
D1, D2 = date(2026, 11, 9), date(2026, 11, 10)


def setup_period(make_member, status=S.PUBLISHED):
    p = Period.objects.create(name="p", start_date=D1, end_date=D2, status=status)
    a, b = make_member("가"), make_member("나")
    make_member("직원", type="직원")
    Commute.objects.create(period=p, date=D1, member=a, shift="dawn")
    Commute.objects.create(period=p, date=D2, member=a, shift="night")
    ControlDuty.objects.create(period=p, date=D1, slot=0, member=b)
    ControlDuty.objects.create(period=p, date=D2, slot=0, member=b)
    ControlDuty.objects.create(period=p, date=D2, slot=1, member=a)
    return p


def test_member_stats(make_member):
    setup_period(make_member)
    rows, duty, total = member_stats(None, None)
    by = {r.name: r for r in rows}
    assert set(by) == {"가", "나"}  # 직원 제외
    assert (by["가"].duty, by["가"].dawn, by["가"].night, by["가"].total) == (1, 1, 1, 3)
    assert (by["나"].duty, by["나"].total) == (2, 2)
    assert duty.spread == 1 and duty.mean == 1.5
    assert total.spread == 1


def test_member_stats_date_range(make_member):
    setup_period(make_member)
    rows, _, _ = member_stats(D2, D2)
    assert {r.name: r.duty for r in rows} == {"가": 1, "나": 1}


def test_period_duty_counts(make_member):
    p = setup_period(make_member, status=S.GENERATED)
    counts, spread, reached = period_duty_counts(p)
    assert counts == [("가", 1), ("나", 2)] and spread == 1 and reached
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_stats.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현** — `duty/services/stats.py`

```python
import statistics
from dataclasses import dataclass
from datetime import date

from django.db.models import Count

from ..models import ControlDuty, Member, Period
from ..shifts import DEVELOPER, TARGET_SPREAD, is_slot_cell
from .roster import published_days


@dataclass
class MemberStat:
    name: str
    duty: int = 0
    dawn: int = 0
    night: int = 0

    @property
    def total(self) -> int:
        return self.duty + self.dawn + self.night


@dataclass(frozen=True)
class Summary:
    mean: float
    stdev: float
    spread: int


def _summary(values: list[int]) -> Summary | None:
    if not values:
        return None
    stdev = statistics.stdev(values) if len(values) > 1 else 0.0
    return Summary(statistics.mean(values), stdev, max(values) - min(values))


def member_stats(start: date | None, end: date | None):
    days = published_days(start, end)
    stats = {n: MemberStat(n) for n in Member.objects.filter(type=DEVELOPER, is_active=True).values_list("name", flat=True)}
    for day in days:
        for cell, names in day.members.items():
            if is_slot_cell(cell):
                for n in names:
                    stats.setdefault(n, MemberStat(n)).duty += 1
    for day in days:
        for n in day.members["dawn"]:
            if n in stats:
                stats[n].dawn += 1
        for n in day.members["night"]:
            if n in stats:
                stats[n].night += 1
    rows = sorted(stats.values(), key=lambda s: (s.duty, s.name))
    return rows, _summary([s.duty for s in rows]), _summary([s.total for s in rows])


def period_duty_counts(period: Period) -> tuple[list[tuple[str, int]], int, bool]:
    rows = (
        ControlDuty.objects.filter(period=period)
        .values("member__name")
        .annotate(n=Count("id"))
        .order_by("n", "member__name")
    )
    counts = [(r["member__name"], r["n"]) for r in rows]
    spread = counts[-1][1] - counts[0][1] if counts else 0
    return counts, spread, spread <= TARGET_SPREAD
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_stats.py -v`
Expected: 3 passed

- [ ] **Step 5: 커밋**

```bash
git add duty/services/stats.py tests/test_stats.py
git commit -m "feat: 당번 통계"
```

---

### Task 9: 인증, 보안 설정, 계정 발급, 노티파이어 API

**Files:**
- Create: `duty/accounts.py`, `duty/middleware.py`, `duty/context.py`, `duty/admin.py`, `duty/api.py`, `duty/views/__init__.py`(빈 파일), `duty/views/common.py`, `duty/views/auth.py`, `duty/templates/duty/base.html`, `duty/templates/duty/login.html`, `duty/templates/duty/password_change.html`
- Modify: `config/settings.py` (axes, 미들웨어, 컨텍스트 프로세서), `duty/urls.py`
- Test: `tests/test_auth_api.py`

**Interfaces:**
- Consumes: `roster.api_assignments`, `perms`
- Produces:
  - `accounts.issue_account(member) -> str` (임시 비번 반환, User 생성 또는 비번 초기화, `must_change_password=True`)
  - `views.common.admin_required(view)`, `date_param(request, name) -> date|None`, `safe_next(request, fallback: str) -> str`
  - URL 이름: `login`, `logout`, `password_change`, `api_assignments`; path converter `isodate`
  - `duty/templates/duty/base.html` — 블록 `title`, `content`; `<dialog id="dlg">` 안 `#dlg-body` 가 htmx 팝업 대상

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_auth_api.py`

```python
from datetime import date

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from duty.accounts import issue_account
from duty.models import Commute, Period

D = date(2026, 11, 10)


def test_issue_account_creates_user(make_member):
    m = make_member("가")
    pw = issue_account(m)
    m.refresh_from_db()
    assert m.user.username == m.code and m.user.check_password(pw) and m.must_change_password
    pw2 = issue_account(m)
    m.user.refresh_from_db()
    assert pw2 != pw and m.user.check_password(pw2)


def test_force_password_change(client, make_member):
    m = make_member("가")
    issue_account(m)
    client.force_login(m.user)
    r = client.get("/me/")
    assert r.status_code == 302 and r.url == reverse("password_change")
    assert client.get(reverse("password_change")).status_code == 200


def test_password_change_clears_flag(client, make_member):
    m = make_member("가")
    pw = issue_account(m)
    client.force_login(m.user)
    r = client.post(reverse("password_change"), {
        "old_password": pw, "new_password1": "Tr0ub4dor&3-xyz", "new_password2": "Tr0ub4dor&3-xyz",
    })
    assert r.status_code == 302
    m.refresh_from_db()
    assert not m.must_change_password


def test_login_lockout_after_five_failures(client, db):
    User.objects.create_user("u1", password="Correct-Horse-9")
    for _ in range(5):
        client.post(reverse("login"), {"username": "u1", "password": "wrong"})
    r = client.post(reverse("login"), {"username": "u1", "password": "Correct-Horse-9"})
    assert r.status_code == 429
    assert "_auth_user_id" not in client.session


def test_login_success_redirects_home(client, db):
    User.objects.create_user("u2", password="Correct-Horse-9")
    r = client.post(reverse("login"), {"username": "u2", "password": "Correct-Horse-9"})
    assert r.status_code == 302 and r.url == "/"


@pytest.fixture
def published(make_member):
    p = Period.objects.create(name="p", start_date=D, end_date=D, status=Period.Status.PUBLISHED)
    Commute.objects.create(period=p, date=D, member=make_member("가"), shift="dawn")
    return p


def test_api_requires_token(client, published):
    assert client.get("/api/assignments").status_code == 401
    assert client.get("/api/assignments", HTTP_AUTHORIZATION="Bearer nope").status_code == 401


def test_api_returns_assignments(client, published):
    r = client.get("/api/assignments?from=2026-11-10&to=2026-11-10", HTTP_AUTHORIZATION="Bearer test-token")
    assert r.status_code == 200
    assert r.json() == [{"date": "2026-11-10", "shift": "새벽", "name": "가", "replaced": None}]


def test_api_bad_date(client, published):
    r = client.get("/api/assignments?from=nope", HTTP_AUTHORIZATION="Bearer test-token")
    assert r.status_code == 400
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_auth_api.py -v`
Expected: FAIL (`ModuleNotFoundError: duty.accounts`)

- [ ] **Step 3: settings 수정** — `config/settings.py`

`INSTALLED_APPS` 의 `"duty",` 앞에 `"axes",` 추가:
```python
    "django.contrib.staticfiles",
    "axes",
    "duty",
]
```

`MIDDLEWARE` 끝(`XFrameOptionsMiddleware` 다음)에 두 줄 추가:
```python
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "duty.middleware.ForcePasswordChangeMiddleware",
    "axes.middleware.AxesMiddleware",
]
```

`context_processors` 목록 끝에 추가:
```python
                "django.contrib.messages.context_processors.messages",
                "duty.context.nav",
```

파일 끝에 추가:
```python
from datetime import timedelta  # noqa: E402

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = ["username"]  # Funnel 뒤에서는 모든 요청 IP가 127.0.0.1 이라 IP 잠금은 전원 차단이 된다
AXES_RESET_ON_SUCCESS = True
```

- [ ] **Step 4: 구현**

`duty/accounts.py`
```python
import secrets

from django.contrib.auth.models import User
from django.db import transaction

from .models import Member


@transaction.atomic
def issue_account(member: Member) -> str:
    """로그인 계정을 만들거나 비밀번호를 초기화하고 임시 비밀번호를 돌려준다(한 번만 표시)."""
    password = secrets.token_urlsafe(9)
    if member.user is None:
        member.user = User.objects.create_user(username=member.code, password=password)
    else:
        member.user.set_password(password)
        member.user.save()
    member.must_change_password = True
    member.save()
    return password
```

`duty/middleware.py`
```python
from django.shortcuts import redirect
from django.urls import reverse

from . import perms


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        member = perms.member_of(request.user)
        if member and member.must_change_password and request.path not in {reverse("password_change"), reverse("logout")}:
            return redirect("password_change")
        return self.get_response(request)
```

`duty/context.py`
```python
from . import perms


def nav(request):
    user = request.user
    return {"can_collect": user.is_authenticated and perms.managed_departments(user).exists()}
```

`duty/admin.py`
```python
from django.contrib import admin, messages

from .accounts import issue_account
from .models import Department, Member


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "shifts"]
    filter_horizontal = ["managers"]


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "department", "part", "type", "is_active", "user"]
    list_filter = ["department", "type", "is_active"]
    search_fields = ["code", "name"]
    raw_id_fields = ["user"]
    actions = ["issue_accounts"]

    @admin.action(description="계정 발급 / 비밀번호 초기화")
    def issue_accounts(self, request, queryset):
        lines = [f"{m.name}({m.code}): {issue_account(m)}" for m in queryset]
        self.message_user(request, "임시 비밀번호 — 이 화면에서만 보입니다. " + " / ".join(lines), messages.WARNING)
```

`duty/api.py`
```python
import hmac
from datetime import date

from django.conf import settings
from django.http import JsonResponse

from .services.roster import api_assignments


def assignments(request):
    token = settings.API_TOKEN
    given = request.headers.get("Authorization", "")
    if not token or not hmac.compare_digest(given.encode(), f"Bearer {token}".encode()):
        return JsonResponse({"error": "unauthorized"}, status=401)
    try:
        start = date.fromisoformat(request.GET["from"]) if request.GET.get("from") else None
        end = date.fromisoformat(request.GET["to"]) if request.GET.get("to") else None
    except ValueError:
        return JsonResponse({"error": "from/to 는 YYYY-MM-DD 형식이어야 합니다."}, status=400)
    return JsonResponse(api_assignments(start, end), safe=False, json_dumps_params={"ensure_ascii": False})
```

`duty/views/__init__.py`: 빈 파일.

`duty/views/common.py`
```python
from datetime import date
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.utils.http import url_has_allowed_host_and_scheme

from .. import perms


def admin_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not perms.is_admin(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return login_required(wrapped)


def date_param(request, name: str) -> date | None:
    raw = request.GET.get(name, "")
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def safe_next(request, fallback: str) -> str:
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    return nxt if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}) else fallback
```

`duty/views/auth.py`
```python
from django.contrib.auth import views as auth_views

from .. import perms


class PasswordChange(auth_views.PasswordChangeView):
    template_name = "duty/password_change.html"
    success_url = "/"

    def form_valid(self, form):
        response = super().form_valid(form)
        member = perms.member_of(self.request.user)
        if member and member.must_change_password:
            member.must_change_password = False
            member.save(update_fields=["must_change_password"])
        return response
```

`duty/urls.py`
```python
from datetime import date

from django.contrib.auth import views as auth_views
from django.urls import path, register_converter

from . import api
from .views import auth as auth_views_local


class IsoDateConverter:
    regex = r"\d{4}-\d{2}-\d{2}"

    def to_python(self, value):
        return date.fromisoformat(value)

    def to_url(self, value):
        return value.isoformat()


register_converter(IsoDateConverter, "isodate")

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="duty/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password/", auth_views_local.PasswordChange.as_view(), name="password_change"),
    path("api/assignments", api.assignments, name="api_assignments"),
]
```

`duty/templates/duty/base.html`
```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}IT 당번표{% endblock %}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2.0.6/css/pico.min.css">
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
  <style>
    .grid-wrap { overflow-x: auto; }
    table.roster { font-size: .8rem; white-space: pre-line; }
    table.roster th:nth-child(-n+2), table.roster td:nth-child(-n+2) {
      position: sticky; background: var(--pico-background-color); z-index: 1; }
    table.roster th:nth-child(1), table.roster td:nth-child(1) { left: 0; min-width: 6.5rem; }
    table.roster th:nth-child(2), table.roster td:nth-child(2) { left: 6.5rem; }
    .changed { background: #fff3cd; }
    .hl { outline: 2px solid #1e88e5; font-weight: bold; }
    tr.today td { border-top: 3px solid #d9534f; }
    .removed { text-decoration: line-through; opacity: .6; }
    @media (prefers-color-scheme: dark) { .changed { background: #4d3f00; } }
  </style>
</head>
<body>
<main class="container-fluid">
  <nav>
    <ul><li><strong>IT 당번표</strong></li></ul>
    {% if user.is_authenticated %}
    <ul>
      <li><a href="/">근무표</a></li>
      <li><a href="/dept/it/">부서별</a></li>
      <li><a href="/me/">내 근무</a></li>
      {% if can_collect %}<li><a href="/collect/">출근표 입력</a></li>{% endif %}
      {% if user.is_staff %}
      <li><a href="/periods/">회차</a></li>
      <li><a href="/stats/">통계</a></li>
      <li><a href="/changes/">이력</a></li>
      {% endif %}
      <li><form method="post" action="{% url 'logout' %}" style="margin:0">{% csrf_token %}<button class="outline secondary">로그아웃</button></form></li>
    </ul>
    {% endif %}
  </nav>
  {% for m in messages %}<article><small>{{ m }}</small></article>{% endfor %}
  {% block content %}{% endblock %}
</main>
<dialog id="dlg"><article><div id="dlg-body"></div><footer><button class="secondary" onclick="document.getElementById('dlg').close()">닫기</button></footer></article></dialog>
<script>
  document.body.addEventListener("htmx:afterSwap", e => {
    if (e.detail.target.id === "dlg-body") document.getElementById("dlg").showModal();
  });
</script>
</body>
</html>
```

`duty/templates/duty/login.html`
```html
{% extends "duty/base.html" %}
{% block content %}
<article style="max-width: 24rem; margin: auto">
  <h3>로그인</h3>
  {% if form.errors %}<p><small>아이디 또는 비밀번호가 맞지 않습니다.</small></p>{% endif %}
  <form method="post">{% csrf_token %}
    <input name="username" placeholder="아이디 (멤버 코드)" autocomplete="username" required>
    <input name="password" type="password" placeholder="비밀번호" autocomplete="current-password" required>
    <button>로그인</button>
  </form>
</article>
{% endblock %}
```

`duty/templates/duty/password_change.html`
```html
{% extends "duty/base.html" %}
{% block content %}
<article style="max-width: 28rem; margin: auto">
  <h3>비밀번호 변경</h3>
  <form method="post">{% csrf_token %}{{ form.as_div }}<button>변경</button></form>
</article>
{% endblock %}
```

- [ ] **Step 5: 마이그레이션 적용 확인 (axes 테이블)**

Run: `DUTY_DEBUG=1 .venv/bin/python manage.py check`
Expected: `System check identified no issues`

- [ ] **Step 6: 통과 확인**

Run: `.venv/bin/pytest tests/test_auth_api.py -v`
Expected: `test_force_password_change` 는 `/me/` 가 아직 없어도 미들웨어가 먼저 302 를 주므로 PASS. 전부 PASS.

- [ ] **Step 7: 전체 테스트**

Run: `.venv/bin/pytest`
Expected: 전부 PASS

- [ ] **Step 8: 커밋**

```bash
git add config duty tests/test_auth_api.py
git commit -m "feat: 로그인 잠금, 첫 로그인 비번 변경, 계정 발급, 노티파이어 API"
```

---

### Task 10: 조회와 근무 변경 화면

**Files:**
- Create: `duty/views/roster.py`, `duty/templates/duty/roster.html`, `duty/templates/duty/_cell_form.html`, `duty/templates/duty/day.html`, `duty/templates/duty/dept.html`, `duty/templates/duty/me.html`
- Modify: `duty/urls.py`
- Test: `tests/test_views_roster.py`

**Interfaces:**
- Consumes: `roster.published_days/find_day/member_schedule/department_table/DEPT_VIEWS`, `changes.change_cell/swap`, `views.common.*`
- Produces: URL 이름 `roster`(`/`), `day`(`/day/<isodate:d>/`), `cell`(`/cell/<isodate:d>/<str:cell>/`), `swap`(`/swap/<isodate:d>/`), `dept`(`/dept/<str:key>/`), `me`(`/me/`)

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_views_roster.py`

```python
from datetime import date

import pytest

from duty.models import Commute, ControlDuty, Period

D = date(2026, 11, 10)


@pytest.fixture
def world(make_member, fixed_today):
    fixed_today(D)
    p = Period.objects.create(name="p", start_date=D, end_date=D, status=Period.Status.PUBLISHED)
    a, b = make_member("가", user=True), make_member("나", user=True)
    Commute.objects.create(period=p, date=D, member=a, shift="normal")
    Commute.objects.create(period=p, date=D, member=b, shift="dinner")
    ControlDuty.objects.create(period=p, date=D, slot=0, member=a)
    return a, b


def test_anonymous_redirected_to_login(client, db):
    r = client.get("/")
    assert r.status_code == 302 and r.url.startswith("/login/")


def test_roster_shows_names_and_highlight(client, world):
    a, _ = world
    client.force_login(a.user)
    r = client.get("/?q=가")
    body = r.content.decode()
    assert r.status_code == 200 and "가" in body and 'class="today"' in body and "hl" in body


def test_cell_form_partial(client, world):
    a, _ = world
    client.force_login(a.user)
    r = client.get(f"/cell/{D}/normal/")
    assert r.status_code == 200 and 'name="before"' in r.content.decode()


def test_change_via_post(client, world, make_member):
    a, _ = world
    c = make_member("다")
    client.force_login(a.user)
    r = client.post(f"/cell/{D}/normal/", {"before": a.code, "after": c.code, "next": "/"})
    assert r.status_code == 302 and r.url == "/"
    assert Commute.objects.filter(date=D, member=c, shift="normal").exists()


def test_past_date_change_forbidden_for_member(client, world, fixed_today, make_member):
    a, _ = world
    c = make_member("다")
    fixed_today(date(2026, 11, 11))
    client.force_login(a.user)
    r = client.post(f"/cell/{D}/normal/", {"before": a.code, "after": c.code})
    assert r.status_code == 403


def test_swap_via_post(client, world):
    a, b = world
    client.force_login(a.user)
    r = client.post(f"/swap/{D}/", {"a": f"normal|{a.code}", "b": f"dinner|{b.code}"})
    assert r.status_code == 302
    assert Commute.objects.get(date=D, member=a).shift == "dinner"


def test_day_page(client, world):
    a, _ = world
    client.force_login(a.user)
    body = client.get(f"/day/{D}/").content.decode()
    assert "08:30~09:30" in body and "맞교환" in body


def test_dept_views(client, world):
    a, _ = world
    client.force_login(a.user)
    for key in ["it", "md", "ui"]:
        assert client.get(f"/dept/{key}/").status_code == 200
    assert client.get("/dept/nope/").status_code == 404


def test_me(client, world):
    a, _ = world
    client.force_login(a.user)
    body = client.get("/me/").content.decode()
    assert "정상" in body and "08:30~09:30" in body
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_views_roster.py -v`
Expected: FAIL (404 — URL 없음)

- [ ] **Step 3: 구현**

`duty/views/roster.py`
```python
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .. import perms
from ..csv_io import split_names
from ..errors import DutyError
from ..models import Member
from ..services import changes
from ..services.roster import DEPT_VIEWS, department_table, find_day, member_schedule, published_days
from ..shifts import CELLS, DAY_LABELS, cell_label, is_slot_cell
from .common import date_param, safe_next


def _wrap(names: list[str], per_line: int = 3) -> str:
    return "\n".join(", ".join(names[i:i + per_line]) for i in range(0, len(names), per_line))


def _member(code: str | None) -> Member | None:
    return Member.objects.filter(code=code).first() if code else None


def _active_members():
    return list(Member.objects.filter(is_active=True).select_related("department").order_by("name"))


def _cell_context(day, cell: str, d):
    current = day.members[cell] if day else []
    return {
        "d": d, "cell": cell, "label": cell_label(cell), "slot": is_slot_cell(cell),
        "current_members": list(Member.objects.filter(name__in=current).order_by("name")),
    }


@login_required
def roster(request):
    start, end = date_param(request, "from"), date_param(request, "to")
    q = request.GET.get("q", "")
    names = split_names(q)[:3]
    today, admin = perms.today(), perms.is_admin(request.user)
    rows, anchored = [], False
    for day in published_days(start, end):
        cells = [
            {
                "key": k, "text": _wrap(day.cells[k].labels), "removed": day.cells[k].removed,
                "changed": day.cells[k].changed, "hl": any(n in day.members[k] for n in names),
            }
            for k in CELLS
        ]
        anchor = not anchored and day.date >= today
        anchored = anchored or anchor
        rows.append({
            "date": day.date, "weekday": DAY_LABELS[day.date.weekday()], "cells": cells,
            "anchor": anchor, "editable": admin or day.date >= today,
        })
    return render(request, "duty/roster.html", {
        "headers": [cell_label(k) for k in CELLS], "rows": rows, "start": start, "end": end, "q": q,
    })


@login_required
def cell(request, d, cell):
    if cell not in CELLS:
        raise Http404
    fallback = reverse("day", args=[d])
    if request.method == "POST":
        try:
            result = changes.change_cell(
                request.user, d, cell, _member(request.POST.get("before")), _member(request.POST.get("after"))
            )
        except DutyError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, "변경했습니다.")
            for w in result.warnings:
                messages.warning(request, w)
        return redirect(safe_next(request, fallback))
    ctx = _cell_context(find_day(d), cell, d)
    ctx.update(members=_active_members(), next=safe_next(request, fallback))
    return render(request, "duty/_cell_form.html", ctx)


def _neighbor(d, step: int):
    d = d + timedelta(days=step)
    while d.weekday() >= 5:
        d += timedelta(days=step)
    return d


@login_required
def day(request, d):
    found = find_day(d)
    editable = perms.is_admin(request.user) or d >= perms.today()
    members = _active_members()
    sections = []
    if found:
        for k in CELLS:
            ctx = _cell_context(found, k, d)
            ctx.update(
                members=members, next=request.path, labels=found.cells[k].labels,
                removed=found.cells[k].removed, changed=found.cells[k].changed,
            )
            sections.append(ctx)
    swap_options = [
        {"value": f"{s['cell']}|{m.code}", "text": f"{s['label']} · {m.name}"}
        for s in sections for m in s["current_members"]
    ]
    return render(request, "duty/day.html", {
        "d": d, "weekday": DAY_LABELS[d.weekday()], "found": found, "sections": sections,
        "editable": editable, "swap_options": swap_options, "prev": _neighbor(d, -1), "next_day": _neighbor(d, 1),
    })


@login_required
@require_POST
def swap(request, d):
    try:
        cell_a, code_a = request.POST["a"].split("|")
        cell_b, code_b = request.POST["b"].split("|")
        result = changes.swap(
            request.user, d, cell_a, Member.objects.get(code=code_a), cell_b, Member.objects.get(code=code_b)
        )
    except (KeyError, ValueError, Member.DoesNotExist):
        messages.error(request, "맞교환할 두 사람을 골라 주세요.")
    except DutyError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "맞교환했습니다.")
        for w in result.warnings:
            messages.warning(request, w)
    return redirect("day", d)


@login_required
def dept(request, key):
    if key not in DEPT_VIEWS:
        raise Http404
    title, header, rows = department_table(key, date_param(request, "from"), date_param(request, "to"))
    return render(request, "duty/dept.html", {
        "key": key, "title": title, "header": header, "rows": rows,
        "tabs": [(k, v[0]) for k, v in DEPT_VIEWS.items()],
    })


@login_required
def me(request):
    member = perms.member_of(request.user)
    items = member_schedule(member, perms.today()) if member else []
    return render(request, "duty/me.html", {
        "member": member,
        "items": [{"date": d, "weekday": DAY_LABELS[d.weekday()], "labels": labels} for d, labels in items],
    })
```

`duty/urls.py` — import 와 urlpatterns 에 추가:
```python
from .views import roster as roster_views
```
```python
    path("", roster_views.roster, name="roster"),
    path("day/<isodate:d>/", roster_views.day, name="day"),
    path("cell/<isodate:d>/<str:cell>/", roster_views.cell, name="cell"),
    path("swap/<isodate:d>/", roster_views.swap, name="swap"),
    path("dept/<str:key>/", roster_views.dept, name="dept"),
    path("me/", roster_views.me, name="me"),
```

`duty/templates/duty/roster.html`
```html
{% extends "duty/base.html" %}
{% block content %}
<form method="get" role="group">
  <input type="date" name="from" value="{{ start|date:'Y-m-d' }}" aria-label="시작일">
  <input type="date" name="to" value="{{ end|date:'Y-m-d' }}" aria-label="종료일">
  <input name="q" value="{{ q }}" placeholder="이름 검색 (쉼표로 최대 3명)">
  <button>보기</button>
</form>
<div class="grid-wrap">
<table class="roster">
  <thead><tr><th>날짜</th><th>요일</th>{% for h in headers %}<th>{{ h }}</th>{% endfor %}</tr></thead>
  <tbody>
  {% for row in rows %}
    <tr {% if row.anchor %}id="today" class="today"{% endif %}>
      <td><a href="{% url 'day' row.date %}">{{ row.date|date:"Y-m-d" }}</a></td>
      <td>{{ row.weekday }}</td>
      {% for c in row.cells %}
      <td class="{% if c.changed %}changed{% endif %} {% if c.hl %}hl{% endif %}">
        {% if row.editable %}<a href="{% url 'day' row.date %}#{{ c.key }}" hx-get="{% url 'cell' row.date c.key %}?next={{ request.get_full_path|urlencode }}" hx-target="#dlg-body">{{ c.text|default:"·" }}</a>{% else %}{{ c.text }}{% endif %}
        {% for r in c.removed %}<div class="removed">{{ r }}</div>{% endfor %}
      </td>
      {% endfor %}
    </tr>
  {% empty %}
    <tr><td colspan="16">배포된 근무표가 없습니다.</td></tr>
  {% endfor %}
  </tbody>
</table>
</div>
<script>document.getElementById("today")?.scrollIntoView({block: "center"});</script>
{% endblock %}
```

`duty/templates/duty/_cell_form.html`
```html
<form method="post" action="{% url 'cell' d cell %}">{% csrf_token %}
  <input type="hidden" name="next" value="{{ next }}">
  <p><strong>{{ d|date:"Y-m-d" }} {{ label }}</strong></p>
  <label>누구를
    <select name="before">
      {% if not slot %}<option value="">(새로 추가)</option>{% endif %}
      {% for m in current_members %}<option value="{{ m.code }}">{{ m.name }}</option>{% endfor %}
    </select>
  </label>
  <label>누구로
    <select name="after">
      {% if not slot %}<option value="">(빼기)</option>{% endif %}
      {% for m in members %}<option value="{{ m.code }}">{{ m.name }} · {{ m.department.name }}</option>{% endfor %}
    </select>
  </label>
  <button>변경</button>
</form>
```

`duty/templates/duty/day.html`
```html
{% extends "duty/base.html" %}
{% block content %}
<nav>
  <ul><li><a href="{% url 'day' prev %}">◀</a></li></ul>
  <ul><li><strong>{{ d|date:"Y-m-d" }} ({{ weekday }})</strong></li></ul>
  <ul><li><a href="{% url 'day' next_day %}">▶</a></li></ul>
</nav>
{% if not found %}<p>배포된 근무표에 없는 날짜입니다.</p>{% endif %}
{% for s in sections %}
<article id="{{ s.cell }}" {% if s.changed %}class="changed"{% endif %}>
  <strong>{{ s.label }}</strong>
  <p>{{ s.labels|join:", "|default:"-" }}{% for r in s.removed %} <span class="removed">{{ r }}</span>{% endfor %}</p>
  {% if editable %}
  <details><summary>변경</summary>
    {% include "duty/_cell_form.html" with cell=s.cell label=s.label slot=s.slot current_members=s.current_members members=s.members next=s.next %}
  </details>
  {% endif %}
</article>
{% endfor %}
{% if found and editable %}
<details><summary>맞교환</summary>
  <form method="post" action="{% url 'swap' d %}">{% csrf_token %}
    <select name="a">{% for o in swap_options %}<option value="{{ o.value }}">{{ o.text }}</option>{% endfor %}</select>
    <select name="b">{% for o in swap_options %}<option value="{{ o.value }}">{{ o.text }}</option>{% endfor %}</select>
    <button>맞교환</button>
  </form>
</details>
{% endif %}
{% endblock %}
```

`duty/templates/duty/dept.html`
```html
{% extends "duty/base.html" %}
{% block content %}
<nav><ul>{% for k, t in tabs %}<li><a href="{% url 'dept' k %}" {% if k == key %}aria-current="page"{% endif %}>{{ t }}</a></li>{% endfor %}</ul></nav>
<div class="grid-wrap">
<table class="roster">
  <thead><tr>{% for h in header %}<th>{{ h }}</th>{% endfor %}</tr></thead>
  <tbody>{% for r in rows %}<tr>{% for v in r %}<td>{{ v }}</td>{% endfor %}</tr>{% endfor %}</tbody>
</table>
</div>
{% endblock %}
```

`duty/templates/duty/me.html`
```html
{% extends "duty/base.html" %}
{% block content %}
<h3>내 근무</h3>
{% if not member %}<p>멤버와 연결된 계정이 아닙니다.</p>{% endif %}
{% for it in items %}
<article><a href="{% url 'day' it.date %}"><strong>{{ it.date|date:"Y-m-d" }} ({{ it.weekday }})</strong></a>
  <p>{{ it.labels|join:", " }}</p></article>
{% empty %}{% if member %}<p>예정된 근무가 없습니다.</p>{% endif %}{% endfor %}
{% endblock %}
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_views_roster.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add duty tests/test_views_roster.py
git commit -m "feat: 통합 근무표, 날짜 상세, 부서별, 내 근무 화면과 근무 변경"
```

---

### Task 11: 출근표 입력 화면

**Files:**
- Create: `duty/views/collect.py`, `duty/templates/duty/collect_index.html`, `duty/templates/duty/collect_table.html`
- Modify: `duty/urls.py`
- Test: `tests/test_views_collect.py`

**Interfaces:**
- Consumes: `collect.load_table/apply_table/apply_csv/export_csv/progress`, `perms`
- Produces: URL 이름 `collect_index`(`/collect/`), `collect_table`(`/collect/<int:pid>/<str:code>/`), `collect_upload`(`.../upload/`), `collect_export`(`.../export.csv`)

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_views_collect.py`

```python
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from duty.models import Commute, Period


@pytest.fixture
def ctx(depts, make_member, fixed_today):
    fixed_today(date(2026, 11, 1))
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 10), status=Period.Status.COLLECTING)
    mgr = make_member("담당", user=True)
    depts["MEMS"].managers.add(mgr)
    make_member("가")
    return p, mgr


def test_index_lists_managed_departments(client, ctx):
    p, mgr = ctx
    client.force_login(mgr.user)
    body = client.get("/collect/").content.decode()
    assert "매칭엔진실" in body and "정보분배" not in body


def test_non_manager_forbidden(client, ctx, make_member):
    p, _ = ctx
    other = make_member("남", user=True)
    client.force_login(other.user)
    assert client.get("/collect/").status_code == 403
    assert client.get(f"/collect/{p.pk}/MEMS/").status_code == 403


def test_upload_csv(client, ctx):
    p, mgr = ctx
    client.force_login(mgr.user)
    f = SimpleUploadedFile("a.csv", "date,새벽,정상,석식교대,야간\n2026-11-09,가,,,\n".encode("utf-8-sig"))
    r = client.post(f"/collect/{p.pk}/MEMS/upload/", {"file": f})
    assert r.status_code == 302
    assert Commute.objects.filter(period=p, shift="dawn").count() == 1


def test_upload_errors_are_listed(client, ctx):
    p, mgr = ctx
    client.force_login(mgr.user)
    f = SimpleUploadedFile("a.csv", "date,새벽,정상,석식교대,야간\n2026-11-09,없는사람,,,\n".encode())
    r = client.post(f"/collect/{p.pk}/MEMS/upload/", {"file": f})
    assert r.status_code == 400 and "없는사람" in r.content.decode()


def test_table_form_save(client, ctx):
    p, mgr = ctx
    client.force_login(mgr.user)
    r = client.post(f"/collect/{p.pk}/MEMS/", {"c_2026-11-10_normal": "가"})
    assert r.status_code == 302
    assert Commute.objects.get(period=p).date == date(2026, 11, 10)


def test_export(client, ctx):
    p, mgr = ctx
    client.force_login(mgr.user)
    r = client.get(f"/collect/{p.pk}/MEMS/export.csv")
    assert r.status_code == 200 and r["Content-Type"].startswith("text/csv")
    assert r.content.decode("utf-8-sig").splitlines()[0] == "date,day,새벽,정상,석식교대,야간"
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_views_collect.py -v`
Expected: FAIL (404)

- [ ] **Step 3: 구현**

`duty/views/collect.py`
```python
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .. import perms
from ..csv_io import CsvInvalid, split_names
from ..errors import DutyError
from ..models import Department, Period
from ..services import collect
from ..shifts import COMMUTE_SHIFTS, DAY_LABELS


@login_required
def index(request):
    depts = list(perms.managed_departments(request.user))
    if not depts:
        raise PermissionDenied
    items = []
    for p in Period.objects.filter(status=Period.Status.COLLECTING).order_by("start_date"):
        prog = collect.progress(p)
        items.append({"period": p, "depts": [(d, prog[d.code]) for d in depts]})
    return render(request, "duty/collect_index.html", {"items": items})


def _load(request, pid, code):
    period = get_object_or_404(Period, pk=pid)
    dept = get_object_or_404(Department, code=code)
    if not perms.can_input_department(request.user, dept):
        raise PermissionDenied
    return period, dept


def _render_table(request, period, dept, table, errors):
    keys = dept.shift_keys()
    today, admin = perms.today(), perms.is_admin(request.user)
    rows = [
        {
            "date": d, "weekday": DAY_LABELS[d.weekday()], "locked": d < today and not admin,
            "cells": [{"name": f"c_{d.isoformat()}_{k}", "value": ", ".join(table.get(d, {}).get(k, []))} for k in keys],
        }
        for d in period.dates()
    ]
    return render(request, "duty/collect_table.html", {
        "period": period, "dept": dept, "rows": rows, "errors": errors,
        "shift_labels": [COMMUTE_SHIFTS[k] for k in keys],
        "is_open": period.status == Period.Status.COLLECTING,
    }, status=400 if errors else 200)


@login_required
def table(request, pid, code):
    period, dept = _load(request, pid, code)
    if request.method == "POST":
        posted = {}
        for d in period.dates():
            day = {k: split_names(request.POST.get(f"c_{d.isoformat()}_{k}", "")) for k in dept.shift_keys()}
            if any(day.values()):
                posted[d] = day
        try:
            n = collect.apply_table(request.user, period, dept, posted)
        except CsvInvalid as e:
            return _render_table(request, period, dept, posted, e.errors)
        except DutyError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, f"{n}명분을 저장했습니다.")
        return redirect("collect_table", pid, code)
    return _render_table(request, period, dept, collect.load_table(period, dept), [])


@login_required
@require_POST
def upload(request, pid, code):
    period, dept = _load(request, pid, code)
    f = request.FILES.get("file")
    if f is None:
        messages.error(request, "CSV 파일을 선택해 주세요.")
        return redirect("collect_table", pid, code)
    try:
        n = collect.apply_csv(request.user, period, dept, f.read())
    except CsvInvalid as e:
        return _render_table(request, period, dept, collect.load_table(period, dept), e.errors)
    except DutyError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f"CSV를 반영했습니다. ({n}명분)")
    return redirect("collect_table", pid, code)


@login_required
def export(request, pid, code):
    period, dept = _load(request, pid, code)
    resp = HttpResponse(collect.export_csv(period, dept), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{dept.code}_{period.start_date:%Y%m%d}.csv"'
    return resp
```

`duty/urls.py` — import 와 urlpatterns 에 추가:
```python
from .views import collect as collect_views
```
```python
    path("collect/", collect_views.index, name="collect_index"),
    path("collect/<int:pid>/<str:code>/", collect_views.table, name="collect_table"),
    path("collect/<int:pid>/<str:code>/upload/", collect_views.upload, name="collect_upload"),
    path("collect/<int:pid>/<str:code>/export.csv", collect_views.export, name="collect_export"),
```

`duty/templates/duty/collect_index.html`
```html
{% extends "duty/base.html" %}
{% block content %}
<h3>출근표 입력</h3>
{% for it in items %}
<article>
  <strong>{{ it.period.name }}</strong> ({{ it.period.start_date|date:"Y-m-d" }} ~ {{ it.period.end_date|date:"Y-m-d" }})
  <ul>{% for d, p in it.depts %}
    <li><a href="{% url 'collect_table' it.period.pk d.code %}">{{ d.name }}</a> — {{ p.0 }} / {{ p.1 }}일</li>
  {% endfor %}</ul>
</article>
{% empty %}<p>취합 중인 회차가 없습니다.</p>{% endfor %}
{% endblock %}
```

`duty/templates/duty/collect_table.html`
```html
{% extends "duty/base.html" %}
{% block content %}
<h3>{{ period.name }} · {{ dept.name }}</h3>
{% if not is_open %}<p>취합이 열려 있지 않아 저장할 수 없습니다.</p>{% endif %}
<div role="group">
  <form method="post" enctype="multipart/form-data" action="{% url 'collect_upload' period.pk dept.code %}" role="group">{% csrf_token %}
    <input type="file" name="file" accept=".csv" required>
    <button>CSV 업로드 (부서 전체 교체)</button>
  </form>
  <a role="button" class="secondary" href="{% url 'collect_export' period.pk dept.code %}">CSV 내려받기</a>
</div>
{% if errors %}
<article>
  <strong>반영하지 않았습니다. 오류 {{ errors|length }}건</strong>
  <ul>{% for e in errors %}<li>{% if e.row %}{{ e.row }}행 {% endif %}{{ e.column }}: {{ e.reason }}</li>{% endfor %}</ul>
</article>
{% endif %}
<form method="post">{% csrf_token %}
<div class="grid-wrap">
<table class="roster">
  <thead><tr><th>날짜</th><th>요일</th>{% for s in shift_labels %}<th>{{ s }}</th>{% endfor %}</tr></thead>
  <tbody>{% for r in rows %}
    <tr><td>{{ r.date|date:"Y-m-d" }}</td><td>{{ r.weekday }}</td>
      {% for c in r.cells %}<td><input name="{{ c.name }}" value="{{ c.value }}" {% if r.locked %}readonly{% endif %}></td>{% endfor %}
    </tr>{% endfor %}</tbody>
</table>
</div>
<button>표 저장</button>
</form>
{% endblock %}
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_views_collect.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add duty tests/test_views_collect.py
git commit -m "feat: 부서 출근표 입력 화면 (CSV 업로드·내려받기, 표 편집)"
```

---

### Task 12: 어드민 화면 (회차 관리, 배포, 통계, 변경 이력)

**Files:**
- Create: `duty/views/manage.py`, `duty/templates/duty/periods.html`, `duty/templates/duty/period_detail.html`, `duty/templates/duty/publish.html`, `duty/templates/duty/stats.html`, `duty/templates/duty/changes.html`
- Modify: `duty/urls.py`
- Test: `tests/test_views_manage.py`

**Interfaces:**
- Consumes: `periods.*`, `collect.progress`, `generate.run_generation`, `GenerationError`, `publish.preview_publish/publish`, `stats.member_stats/period_duty_counts`
- Produces: URL 이름 `periods`, `period_detail`, `period_action`(`/periods/<pid>/action/<name>/`), `period_publish`, `stats`, `changes`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_views_manage.py`

```python
from datetime import date

import pytest

from duty.models import ChangeLog, Commute, Period


@pytest.fixture
def member_client(client, make_member):
    m = make_member("가", user=True)
    client.force_login(m.user)
    return client


@pytest.mark.parametrize("url", ["/periods/", "/stats/", "/changes/"])
def test_admin_pages_forbidden_for_member(member_client, url):
    assert member_client.get(url).status_code == 403


def test_create_period(admin_client_ok):
    r = admin_client_ok.post("/periods/", {"name": "2027", "start_date": "2026-11-09", "end_date": "2026-11-13"})
    p = Period.objects.get(name="2027")
    assert r.status_code == 302 and r.url == f"/periods/{p.pk}/"


def test_full_flow(admin_client_ok, make_member, fixed_today):
    fixed_today(date(2026, 11, 1))
    c = admin_client_ok
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 10))
    c.post(f"/periods/{p.pk}/action/open/")
    devs = [make_member(f"D{i}", dept=["MEMS", "TMCH", "MD", "UI"][i % 4]) for i in range(12)]
    for d in p.dates():
        for m in devs:
            Commute.objects.create(period=p, date=d, member=m, shift="normal" if m.pk % 2 else "dinner")
    c.post(f"/periods/{p.pk}/action/close/")
    r = c.post(f"/periods/{p.pk}/action/generate/")
    p.refresh_from_db()
    assert r.status_code == 302 and p.status == Period.Status.GENERATED
    assert "편차" in c.get(f"/periods/{p.pk}/").content.decode()
    assert "덮어쓰기" in c.get(f"/periods/{p.pk}/publish/?from=2026-11-09").content.decode()
    c.post(f"/periods/{p.pk}/publish/", {"from": "2026-11-09"})
    p.refresh_from_db()
    assert p.status == Period.Status.PUBLISHED


def test_generation_failure_is_shown(admin_client_ok, make_member):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 9), status=Period.Status.CLOSED)
    for code in ["MEMS", "TMCH", "MD", "UI"]:
        Commute.objects.create(period=p, date=date(2026, 11, 9), member=make_member(f"직{code}", dept=code, type="직원"), shift="normal")
    r = admin_client_ok.post(f"/periods/{p.pk}/action/generate/")
    assert r.status_code == 200 and "후보" in r.content.decode()


def test_stats_and_changes_pages(admin_client_ok, make_member):
    p = Period.objects.create(name="p", start_date=date(2026, 11, 9), end_date=date(2026, 11, 9), status=Period.Status.PUBLISHED)
    m = make_member("가")
    Commute.objects.create(period=p, date=date(2026, 11, 9), member=m, shift="dawn")
    ChangeLog.objects.create(period=p, date=date(2026, 11, 9), cell="dawn", before=None, after=m)
    assert "가" in admin_client_ok.get("/stats/").content.decode()
    assert "새벽" in admin_client_ok.get("/changes/?name=가").content.decode()
```

`tests/conftest.py` 끝에 fixture 추가:
```python
@pytest.fixture
def admin_client_ok(client, admin_user):
    client.force_login(admin_user)
    return client
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_views_manage.py -v`
Expected: FAIL (404)

- [ ] **Step 3: 구현**

`duty/views/manage.py`
```python
from datetime import date

from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .. import perms
from ..errors import DutyError
from ..generator import GenerationError
from ..models import ChangeLog, Period
from ..services import collect, generate, periods, stats
from ..services import publish as publishing
from ..shifts import CONTROL_SLOTS, cell_label
from .common import admin_required, date_param


def _form_period(post, period: Period | None = None) -> Period:
    name = post.get("name", "").strip()
    if not name:
        raise ValueError("이름이 비어 있습니다.")
    period = period or Period()
    period.name = name
    period.start_date = date.fromisoformat(post["start_date"])
    period.end_date = date.fromisoformat(post["end_date"])
    return period


@admin_required
def period_list(request):
    if request.method == "POST":
        try:
            p = periods.save_draft(_form_period(request.POST))
        except (KeyError, ValueError):
            messages.error(request, "이름과 기간을 확인해 주세요.")
        except DutyError as e:
            messages.error(request, str(e))
        else:
            return redirect("period_detail", p.pk)
        return redirect("periods")
    return render(request, "duty/periods.html", {"periods": Period.objects.order_by("-start_date")})


def _render_detail(request, period, failures):
    counts, spread, reached = stats.period_duty_counts(period)
    return render(request, "duty/period_detail.html", {
        "period": period, "S": Period.Status,
        "progress": collect.progress(period), "missing": periods.missing_dates(period),
        "counts": counts, "spread": spread, "reached": reached,
        "failures": [{"date": f.date, "slot": CONTROL_SLOTS[f.slot][0], "candidates": f.candidates} for f in failures],
    })


@admin_required
def period_detail(request, pid):
    period = get_object_or_404(Period, pk=pid)
    if request.method == "POST":
        try:
            periods.save_draft(_form_period(request.POST, period))
        except (KeyError, ValueError):
            messages.error(request, "이름과 기간을 확인해 주세요.")
        except DutyError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, "저장했습니다.")
        return redirect("period_detail", pid)
    return _render_detail(request, period, [])


@admin_required
@require_POST
def period_action(request, pid, action):
    period = get_object_or_404(Period, pk=pid)
    actions = {
        "open": periods.open_collecting,
        "close": periods.close_collecting,
        "generate": generate.run_generation,
    }
    if action not in actions:
        raise Http404
    try:
        actions[action](period)
    except GenerationError as e:
        return _render_detail(request, period, e.failures)
    except DutyError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "완료했습니다.")
    return redirect("period_detail", pid)


@admin_required
def period_publish(request, pid):
    period = get_object_or_404(Period, pk=pid)
    raw = request.POST.get("from") or request.GET.get("from")
    default = min(max(perms.today(), period.start_date), period.end_date)
    try:
        start = date.fromisoformat(raw) if raw else default
    except ValueError:
        start = default
    try:
        if request.method == "POST":
            publishing.publish(period, start)
            messages.success(request, "배포했습니다.")
            return redirect("period_detail", pid)
        preview = publishing.preview_publish(period, start)
    except DutyError as e:
        messages.error(request, str(e))
        return redirect("period_detail", pid)
    return render(request, "duty/publish.html", {"period": period, "preview": preview})


@admin_required
def stats_view(request):
    start, end = date_param(request, "from"), date_param(request, "to")
    rows, duty_summary, total_summary = stats.member_stats(start, end)
    return render(request, "duty/stats.html", {
        "rows": rows, "duty": duty_summary, "total": total_summary, "start": start, "end": end,
    })


@admin_required
def change_log(request):
    qs = ChangeLog.objects.select_related("by", "before", "after", "period").order_by("-at", "-id")
    start, end = date_param(request, "from"), date_param(request, "to")
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    name = request.GET.get("name", "").strip()
    if name:
        qs = qs.filter(Q(before__name=name) | Q(after__name=name))
    by = request.GET.get("by", "").strip()
    if by:
        qs = qs.filter(by__username=by)
    logs = [
        {
            "at": log.at, "by": log.by.username if log.by else "import", "date": log.date,
            "cell": cell_label(log.cell), "before": log.before.name if log.before else "",
            "after": log.after.name if log.after else "", "period": log.period.name,
        }
        for log in qs[:500]
    ]
    return render(request, "duty/changes.html", {"logs": logs, "name": name, "by": by, "start": start, "end": end})
```

`duty/urls.py` — import 와 urlpatterns 에 추가:
```python
from .views import manage as manage_views
```
```python
    path("periods/", manage_views.period_list, name="periods"),
    path("periods/<int:pid>/", manage_views.period_detail, name="period_detail"),
    path("periods/<int:pid>/action/<str:action>/", manage_views.period_action, name="period_action"),
    path("periods/<int:pid>/publish/", manage_views.period_publish, name="period_publish"),
    path("stats/", manage_views.stats_view, name="stats"),
    path("changes/", manage_views.change_log, name="changes"),
```

`duty/templates/duty/periods.html`
```html
{% extends "duty/base.html" %}
{% block content %}
<h3>회차</h3>
<form method="post" role="group">{% csrf_token %}
  <input name="name" placeholder="회차 이름" required>
  <input type="date" name="start_date" required aria-label="시작일">
  <input type="date" name="end_date" required aria-label="종료일">
  <button>새 회차</button>
</form>
<table>
  <thead><tr><th>이름</th><th>기간</th><th>상태</th></tr></thead>
  <tbody>{% for p in periods %}
    <tr><td><a href="{% url 'period_detail' p.pk %}">{{ p.name }}</a></td>
      <td>{{ p.start_date|date:"Y-m-d" }} ~ {{ p.end_date|date:"Y-m-d" }}</td>
      <td>{{ p.get_status_display }}</td></tr>
  {% endfor %}</tbody>
</table>
{% endblock %}
```

`duty/templates/duty/period_detail.html`
```html
{% extends "duty/base.html" %}
{% block content %}
<h3>{{ period.name }} <small>({{ period.get_status_display }})</small></h3>
{% if period.status == S.DRAFT %}
<form method="post" role="group">{% csrf_token %}
  <input name="name" value="{{ period.name }}" required>
  <input type="date" name="start_date" value="{{ period.start_date|date:'Y-m-d' }}" required>
  <input type="date" name="end_date" value="{{ period.end_date|date:'Y-m-d' }}" required>
  <button>저장</button>
</form>
{% else %}
<p>{{ period.start_date|date:"Y-m-d" }} ~ {{ period.end_date|date:"Y-m-d" }}</p>
{% endif %}

<div role="group">
  {% if period.status == S.DRAFT or period.status == S.CLOSED or period.status == S.GENERATED %}
  <form method="post" action="{% url 'period_action' period.pk 'open' %}">{% csrf_token %}<button class="secondary">{% if period.status == S.DRAFT %}취합 열기{% else %}재오픈 (생성 결과 삭제){% endif %}</button></form>
  {% endif %}
  {% if period.status == S.COLLECTING %}
  <form method="post" action="{% url 'period_action' period.pk 'close' %}">{% csrf_token %}<button>취합 마감</button></form>
  {% endif %}
  {% if period.status == S.CLOSED or period.status == S.GENERATED %}
  <form method="post" action="{% url 'period_action' period.pk 'generate' %}">{% csrf_token %}<button {% if missing %}disabled{% endif %}>{% if period.status == S.GENERATED %}재생성{% else %}생성{% endif %}</button></form>
  {% endif %}
  {% if period.status == S.GENERATED %}
  <a role="button" href="{% url 'period_publish' period.pk %}">배포…</a>
  {% endif %}
</div>

<h4>부서별 입력 현황</h4>
<ul>{% for code, p in progress.items %}<li>{{ code }}: {{ p.0 }} / {{ p.1 }}일
  {% if code in missing %}<small>(비어 있는 날짜 있음)</small>{% endif %}</li>{% endfor %}</ul>

{% if failures %}
<article><strong>배정할 수 없는 칸이 있습니다.</strong>
  <table><thead><tr><th>날짜</th><th>시간대</th><th>후보 수</th></tr></thead>
  <tbody>{% for f in failures %}<tr><td>{{ f.date|date:"Y-m-d" }}</td><td>{{ f.slot }}</td><td>{{ f.candidates }}</td></tr>{% endfor %}</tbody></table>
</article>
{% endif %}

{% if counts %}
<h4>장중관제 배정 횟수 — 편차 {{ spread }} {% if reached %}(목표 2 이하 도달){% else %}(목표 2 미도달){% endif %}</h4>
<table><tbody>{% for name, n in counts %}<tr><td>{{ name }}</td><td>{{ n }}</td></tr>{% endfor %}</tbody></table>
{% endif %}
{% endblock %}
```

`duty/templates/duty/publish.html`
```html
{% extends "duty/base.html" %}
{% block content %}
<h3>{{ period.name }} 배포</h3>
<form method="get" role="group">
  <label>덮어쓰기 시작일 <input type="date" name="from" value="{{ preview.overwrite_from|date:'Y-m-d' }}" min="{{ period.start_date|date:'Y-m-d' }}" max="{{ period.end_date|date:'Y-m-d' }}"></label>
  <button class="secondary">다시 계산</button>
</form>
<article>
  <p>덮어쓰기 범위: {{ preview.overwrite_from|date:"Y-m-d" }} ~ {{ preview.overwrite_to|date:"Y-m-d" }}</p>
  <p>시작일 이전의 이 회차 데이터는 버립니다.</p>
  {% if preview.periods %}<p>덮어쓰는 회차: {{ preview.periods|join:", " }}</p>{% endif %}
  <p>사라지는 근무 변경: {{ preview.discarded_changes }}건 (이력은 남음)</p>
</article>
<form method="post">{% csrf_token %}
  <input type="hidden" name="from" value="{{ preview.overwrite_from|date:'Y-m-d' }}">
  <button>배포</button>
</form>
{% endblock %}
```

`duty/templates/duty/stats.html`
```html
{% extends "duty/base.html" %}
{% block content %}
<h3>당번 통계</h3>
<form method="get" role="group">
  <input type="date" name="from" value="{{ start|date:'Y-m-d' }}"><input type="date" name="to" value="{{ end|date:'Y-m-d' }}"><button>보기</button>
</form>
{% if duty %}<p>장중관제 — 평균 {{ duty.mean|floatformat:2 }}, 표준편차 {{ duty.stdev|floatformat:2 }}, 최대 편차 {{ duty.spread }}</p>{% endif %}
{% if total %}<p>전체 — 평균 {{ total.mean|floatformat:2 }}, 표준편차 {{ total.stdev|floatformat:2 }}, 최대 편차 {{ total.spread }}</p>{% endif %}
<table>
  <thead><tr><th>이름</th><th>장중관제</th><th>새벽</th><th>야간</th><th>계</th></tr></thead>
  <tbody>{% for r in rows %}<tr><td>{{ r.name }}</td><td>{{ r.duty }}</td><td>{{ r.dawn }}</td><td>{{ r.night }}</td><td>{{ r.total }}</td></tr>{% endfor %}</tbody>
</table>
{% endblock %}
```

`duty/templates/duty/changes.html`
```html
{% extends "duty/base.html" %}
{% block content %}
<h3>변경 이력</h3>
<form method="get" role="group">
  <input type="date" name="from" value="{{ start|date:'Y-m-d' }}"><input type="date" name="to" value="{{ end|date:'Y-m-d' }}">
  <input name="name" value="{{ name }}" placeholder="사람 이름"><input name="by" value="{{ by }}" placeholder="수정자 아이디">
  <button>보기</button>
</form>
<div class="grid-wrap"><table>
  <thead><tr><th>시각</th><th>수정자</th><th>근무일</th><th>칸</th><th>변경</th><th>회차</th></tr></thead>
  <tbody>{% for l in logs %}
    <tr><td>{{ l.at|date:"Y-m-d H:i" }}</td><td>{{ l.by }}</td><td>{{ l.date|date:"Y-m-d" }}</td><td>{{ l.cell }}</td>
      <td>{{ l.before|default:"(없음)" }} → {{ l.after|default:"(없음)" }}</td><td>{{ l.period }}</td></tr>
  {% empty %}<tr><td colspan="6">이력이 없습니다.</td></tr>{% endfor %}</tbody>
</table></div>
{% endblock %}
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_views_manage.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 전체 테스트**

Run: `.venv/bin/pytest`
Expected: 전부 PASS

- [ ] **Step 6: 커밋**

```bash
git add duty tests/test_views_manage.py tests/conftest.py
git commit -m "feat: 회차 관리·배포·통계·변경 이력 화면"
```

---

### Task 13: 기존 시트 가져오기

**Files:**
- Create: `duty/importer.py`, `duty/management/__init__.py`, `duty/management/commands/__init__.py`, `duty/management/commands/import_sheets.py`
- Test: `tests/test_importer.py`

**Interfaces:**
- Consumes: models, `shifts.CELLS/CELL_BY_LABEL/cell_label/is_slot_cell/slot_index`
- Produces:
  - `importer.parse_chains(cell) -> list[list[str]]`
  - `importer.diff_cell(original: list[str], final_cell) -> tuple[list[str], list[tuple[str|None, str|None]]]`
  - `importer.ImportReport(members, dates, commutes, duties, changes, errors)`
  - `importer.run_import(maker: bytes, deploy: bytes, dry_run: bool) -> ImportReport`
  - `importer.download_xlsx(sheet_id) -> bytes`, `MAKER_ID`, `DEPLOY_ID`
  - 명령 `manage.py import_sheets [--maker-xlsx PATH] [--deploy-xlsx PATH] [--dry-run]`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_importer.py`

```python
from datetime import date
from io import BytesIO

import openpyxl
import pytest

from duty.importer import diff_cell, parse_chains, run_import
from duty.models import ChangeLog, Commute, ControlDuty, Member, Period
from duty.services.roster import api_assignments
from duty.shifts import CELLS, cell_label

D = date(2026, 11, 9)
DEVS = [f"d{i}" for i in range(12)]


def _bytes(wb):
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def maker():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "tb_member"
    ws.append(["id", "department", "name", "part", "type", "is_id_dup", "is_active"])
    ws.append(["MEE01", "매칭엔진실", "직원가", "매칭엔진", "직원", False, True])
    for i, n in enumerate(DEVS):
        ws.append([f"MED{i:02d}", "매칭엔진실", n, "매칭엔진", "개발자", False, True])
    return _bytes(wb)


BASE = {"dawn": "직원가", "normal": ",".join(DEVS[:6]) + "\n" + ",".join(DEVS[6:10]), "dinner": "", "night": "",
        **{f"slot{i}": DEVS[i] for i in range(10)}}


def deploy(final_overrides):
    wb = openpyxl.Workbook()
    a = wb.active
    a.title = "view_all_combine"
    a.append(["날짜", "요일", *[cell_label(c) for c in CELLS]])
    a.append([D, "월", *[BASE[c] for c in CELLS]])
    b = wb.create_sheet("근무표")
    b.append(["검색", "."])
    b.append(["날짜", "요일", *[cell_label(c) for c in CELLS]])
    final = {**BASE, **final_overrides}
    b.append([D, "월", *[final[c] for c in CELLS]])
    return _bytes(wb)


def test_parse_chains_handles_arrows_and_newlines():
    assert parse_chains("가,\n나\n> 다, 라->마") == [["가"], ["나", "다"], ["라", "마"]]


def test_diff_cell_pairs_overwrites_as_replacement():
    final, logs = diff_cell(["가", "나"], "가, 다")
    assert final == ["가", "다"] and logs == [("나", "다")]


def test_diff_cell_chain():
    final, logs = diff_cell(["가"], "가>나>다")
    assert final == ["다"] and logs == [("가", "나"), ("나", "다")]


def test_import_applies_changes(db):
    overrides = {"normal": BASE["normal"].replace("d0", "d0>d10"), "slot0": "d0 -> d11"}
    report = run_import(maker(), deploy(overrides), dry_run=False)
    assert report.errors == []
    p = Period.objects.get(name="시트 이관")
    assert p.status == Period.Status.PUBLISHED
    assert Member.objects.count() == 13
    assert Commute.objects.filter(member__name="d10", shift="normal").exists()
    assert not Commute.objects.filter(member__name="d0").exists()
    assert ControlDuty.objects.get(slot=0).member.name == "d11"
    assert ChangeLog.objects.count() == 2
    rows = api_assignments(None, None)
    assert {"date": "2026-11-09", "shift": "정상", "name": "d10", "replaced": "d0"} in rows


def test_unknown_name_aborts(db):
    report = run_import(maker(), deploy({"dawn": "없는사람"}), dry_run=False)
    assert any("없는사람" in e for e in report.errors)
    assert not Period.objects.exists()


def test_double_commute_aborts(db):
    report = run_import(maker(), deploy({"night": "d1"}), dry_run=False)
    assert any("중복" in e for e in report.errors)


def test_dry_run_writes_nothing(db):
    report = run_import(maker(), deploy({}), dry_run=True)
    assert report.errors == [] and report.dates == 1 and report.duties == 10
    assert not Member.objects.exists()


def test_second_import_refused(db):
    run_import(maker(), deploy({}), dry_run=False)
    assert run_import(maker(), deploy({}), dry_run=False).errors
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_importer.py -v`
Expected: FAIL (`ModuleNotFoundError: duty.importer`)

- [ ] **Step 3: 구현**

`duty/importer.py`
```python
"""기존 구글 시트 1회 가져오기.

제작기 tb_member → Department/Member
배포용 view_all_combine → 생성 당시 원본, 배포용 근무표 → 'A>B' 변경을 ChangeLog 로 기록하고 최종 상태 반영.
"""

import re
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO

import openpyxl
from django.db import transaction
from django.utils import timezone

from .models import ChangeLog, Commute, ControlDuty, Department, Member, Period
from .shifts import CELL_BY_LABEL, CELLS, cell_label, is_slot_cell, slot_index

MAKER_ID = "1y-T4gWwGb9p8g4Lkla0so1yY7Ox_QnV0N1unRChfYOI"
DEPLOY_ID = "1RZjmnktNRFNg3KycrNI3No6Sczu8ATnWd1IWAYWxn5w"
IMPORT_PERIOD_NAME = "시트 이관"
DEPARTMENTS = [
    ("MEMS", "매칭엔진실", "dawn,normal,dinner,night"),
    ("TMCH", "매매지원실", "dawn,normal,dinner,night"),
    ("MD", "정보분배", "dawn,normal,dinner,night"),
    ("UI", "UI", "normal,dinner,night"),
]

_ARROW = re.compile(r"\s*-?>\s*")  # duty_notifier cell_parser 와 같은 규칙
_SEP = re.compile(r"[,\n]")

Log = tuple[str | None, str | None]


def download_xlsx(sheet_id: str) -> bytes:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def parse_chains(cell) -> list[list[str]]:
    joined = _ARROW.sub(">", str(cell or ""))
    out = []
    for token in _SEP.split(joined):
        parts = [p.strip() for p in token.split(">") if p.strip()]
        if parts:
            out.append(parts)
    return out


def diff_cell(original: list[str], final_cell) -> tuple[list[str], list[Log]]:
    chains = parse_chains(final_cell)
    heads = [c[0] for c in chains]
    removed = [o for o in original if o not in heads]
    added = [h for h in heads if h not in original]
    logs: list[Log] = list(zip(removed, added))  # 이름을 덮어쓴 칸은 교체로 본다
    logs += [(o, None) for o in removed[len(added):]]
    logs += [(None, h) for h in added[len(removed):]]
    for c in chains:
        logs.extend(zip(c, c[1:]))
    return [c[-1] for c in chains], logs


def _as_date(v):
    if isinstance(v, datetime):
        return v.date()
    return v if isinstance(v, date) else None


def read_grid(ws, header_row: int) -> dict[date, dict[str, str]]:
    rows = list(ws.iter_rows(min_row=header_row, values_only=True))
    cols = {i: CELL_BY_LABEL[str(h).strip()] for i, h in enumerate(rows[0]) if h is not None and str(h).strip() in CELL_BY_LABEL}
    grid = {}
    for r in rows[1:]:
        d = _as_date(r[0]) if r else None
        if d:
            grid[d] = {cell: "" if i >= len(r) or r[i] is None else str(r[i]) for i, cell in cols.items()}
    return grid


def read_members(ws) -> list[dict]:
    rows = list(ws.iter_rows(values_only=True))
    idx = {str(h).strip(): i for i, h in enumerate(rows[0]) if h is not None}
    out = []
    for r in rows[1:]:
        if not r[idx["id"]]:
            continue
        active = r[idx["is_active"]]
        out.append({
            "code": str(r[idx["id"]]).strip(),
            "department": str(r[idx["department"]]).strip(),
            "name": str(r[idx["name"]]).strip(),
            "part": str(r[idx["part"]] or "").strip(),
            "type": str(r[idx["type"]]).strip(),
            "is_active": active is True or str(active).upper() == "TRUE",
        })
    return out


@dataclass
class ImportReport:
    members: int = 0
    dates: int = 0
    commutes: int = 0
    duties: int = 0
    changes: int = 0
    errors: list[str] = field(default_factory=list)


def run_import(maker: bytes, deploy: bytes, dry_run: bool) -> ImportReport:
    report = ImportReport()
    if Period.objects.filter(name=IMPORT_PERIOD_NAME).exists():
        report.errors.append("이미 가져온 회차(시트 이관)가 있습니다.")
        return report
    mk = openpyxl.load_workbook(BytesIO(maker), data_only=True)
    dp = openpyxl.load_workbook(BytesIO(deploy), data_only=True)
    members = read_members(mk["tb_member"])
    dept_codes = {name: code for code, name, _ in DEPARTMENTS}
    errors: list[str] = []
    names: set[str] = set()
    for m in members:
        if m["department"] not in dept_codes:
            errors.append(f"{m['name']}: 알 수 없는 부서 {m['department']}")
        if m["name"] in names:
            errors.append(f"멤버 이름 중복: {m['name']}")
        names.add(m["name"])

    original = read_grid(dp["view_all_combine"], 1)
    final = read_grid(dp["근무표"], 2)
    plan: dict[date, dict[str, tuple[list[str], list[Log]]]] = {}
    for d in sorted(original):
        if d not in final:
            errors.append(f"{d}: 근무표에 없는 날짜")
            continue
        day = {}
        commute_seen: dict[str, str] = {}
        duty_seen: set[str] = set()
        for cell in CELLS:
            orig = [n for c in parse_chains(original[d].get(cell)) for n in c]
            fin, logs = diff_cell(orig, final[d].get(cell))
            for n in sorted({*fin, *(x for pair in logs for x in pair if x)}):
                if n not in names:
                    errors.append(f"{d} {cell_label(cell)}: 멤버에 없는 이름 '{n}'")
            if is_slot_cell(cell):
                if len(fin) != 1:
                    errors.append(f"{d} {cell_label(cell)}: 관제 칸은 1명이어야 합니다 ({', '.join(fin) or '비어 있음'})")
                for n in fin:
                    if n in duty_seen:
                        errors.append(f"{d}: {n}이(가) 관제 칸에 중복")
                    duty_seen.add(n)
            else:
                for n in fin:
                    if n in commute_seen:
                        errors.append(f"{d}: {n}이(가) {cell_label(commute_seen[n])}와 {cell_label(cell)}에 중복")
                    commute_seen[n] = cell
            day[cell] = (fin, logs)
        plan[d] = day

    report.members, report.dates = len(members), len(plan)
    for day in plan.values():
        for cell, (fin, logs) in day.items():
            if is_slot_cell(cell):
                report.duties += len(fin)
            else:
                report.commutes += len(fin)
            report.changes += len(logs)
    report.errors = errors
    if errors or dry_run or not plan:
        return report
    _write(members, plan, dept_codes)
    return report


@transaction.atomic
def _write(members, plan, dept_codes) -> None:
    for code, name, shifts in DEPARTMENTS:
        Department.objects.update_or_create(code=code, defaults={"name": name, "shifts": shifts})
    by_name = {}
    for m in members:
        obj, _ = Member.objects.update_or_create(code=m["code"], defaults={
            "name": m["name"], "department_id": dept_codes[m["department"]],
            "part": m["part"], "type": m["type"], "is_active": m["is_active"],
        })
        by_name[obj.name] = obj
    dates = sorted(plan)
    period = Period.objects.create(
        name=IMPORT_PERIOD_NAME, start_date=dates[0], end_date=dates[-1],
        status=Period.Status.PUBLISHED, published_at=timezone.now(), overwrite_from=dates[0],
    )
    commutes, duties, logs = [], [], []
    for d, day in plan.items():
        for cell, (fin, pairs) in day.items():
            for n in fin:
                if is_slot_cell(cell):
                    duties.append(ControlDuty(period=period, date=d, slot=slot_index(cell), member=by_name[n]))
                else:
                    commutes.append(Commute(period=period, date=d, member=by_name[n], shift=cell))
            for before, after in pairs:
                logs.append(ChangeLog(
                    by=None, period=period, date=d, cell=cell,
                    before=by_name[before] if before else None, after=by_name[after] if after else None,
                ))
    Commute.objects.bulk_create(commutes)
    ControlDuty.objects.bulk_create(duties)
    ChangeLog.objects.bulk_create(logs)
```

`duty/management/__init__.py`, `duty/management/commands/__init__.py`: 빈 파일.

`duty/management/commands/import_sheets.py`
```python
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from duty.importer import DEPLOY_ID, MAKER_ID, download_xlsx, run_import


class Command(BaseCommand):
    help = "구글 시트(제작기 tb_member, 배포용 view_all_combine/근무표)를 1회 가져온다."

    def add_arguments(self, parser):
        parser.add_argument("--maker-xlsx", help="제작기 xlsx 경로 (없으면 공개 URL에서 받음)")
        parser.add_argument("--deploy-xlsx", help="배포용 xlsx 경로 (없으면 공개 URL에서 받음)")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        maker = Path(opts["maker_xlsx"]).read_bytes() if opts["maker_xlsx"] else download_xlsx(MAKER_ID)
        deploy = Path(opts["deploy_xlsx"]).read_bytes() if opts["deploy_xlsx"] else download_xlsx(DEPLOY_ID)
        r = run_import(maker, deploy, opts["dry_run"])
        for e in r.errors:
            self.stderr.write(e)
        self.stdout.write(f"멤버 {r.members}, 날짜 {r.dates}, 출근조 {r.commutes}, 관제 {r.duties}, 변경 {r.changes}")
        if r.errors:
            raise CommandError(f"오류 {len(r.errors)}건 — 반영하지 않았습니다.")
        self.stdout.write("dry-run: 반영하지 않았습니다." if opts["dry_run"] else "가져오기 완료")
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_importer.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 실데이터 dry-run (네트워크 필요)**

Run: `mkdir -p .cache && DUTY_DEBUG=1 DUTY_DB_PATH=.cache/dryrun.sqlite3 sh -c '.venv/bin/python manage.py migrate -v0 && .venv/bin/python manage.py import_sheets --dry-run'`
Expected: `멤버 36, 날짜 280, ...` 와 `dry-run: 반영하지 않았습니다.` 출력. 오류가 나오면 오류 목록을 그대로 사용자에게 보고한다(시트를 고쳐야 하는 데이터 문제일 수 있음 — 코드로 우회하지 않는다).

- [ ] **Step 6: 커밋**

```bash
git add duty/importer.py duty/management tests/test_importer.py
git commit -m "feat: 기존 구글 시트 1회 가져오기 명령"
```

---

### Task 14: 생성 품질 기준선 테스트

**Files:**
- Create: `tests/fixtures/baseline_commutes.json` (스크립트로 생성), `tests/test_baseline.py`

**Interfaces:**
- Consumes: `generator.generate_control_duty`

- [ ] **Step 1: fixture 생성** — 실제 제작기 시트의 1년치 출근표(멤버 코드만, 이름 없음)를 저장한다.

Run:
```bash
mkdir -p .cache tests/fixtures
curl -sL -o .cache/maker.xlsx "https://docs.google.com/spreadsheets/d/1y-T4gWwGb9p8g4Lkla0so1yY7Ox_QnV0N1unRChfYOI/export?format=xlsx"
.venv/bin/python - <<'EOF'
import json, openpyxl
wb = openpyxl.load_workbook(".cache/maker.xlsx", data_only=True)
rows = list(wb["tb_member"].iter_rows(values_only=True)); h = list(rows[0])
devs = sorted(r[0] for r in rows[1:] if r[0] and r[h.index("type")] == "개발자" and r[h.index("is_active")] in (True, "TRUE"))
rows = list(wb["tb_commute_schedule"].iter_rows(values_only=True)); h = list(rows[0])
cols = {k: h.index(f"{k}_commute") for k in ["dawn", "normal", "dinner", "night"]}
days = {}
for r in rows[1:]:
    if r[0] is None:
        continue
    days[r[0].date().isoformat()] = {k: [x for x in str(r[i] or "").split(",") if x] for k, i in cols.items()}
with open("tests/fixtures/baseline_commutes.json", "w") as f:
    json.dump({"developers": devs, "days": days}, f, ensure_ascii=False, indent=1)
print(len(devs), "developers,", len(days), "days")
EOF
```
Expected: `19 developers, 260 days`

- [ ] **Step 2: 테스트 작성** — `tests/test_baseline.py`

```python
"""실제 1년치 출근표(2026-09-07~2027-09-03)로 생성 품질을 고정한다.
기존 Apps Script 결과는 편차 6(Phase 2 미동작). 이식본은 목표 2에 도달해야 한다."""

import json
from datetime import date
from pathlib import Path

from duty.generator import generate_control_duty


def test_baseline_reaches_target_spread():
    data = json.loads((Path(__file__).parent / "fixtures" / "baseline_commutes.json").read_text())
    days = {date.fromisoformat(d): {k: set(v) for k, v in s.items()} for d, s in data["days"].items()}
    out = generate_control_duty(sorted(days), days, set(data["developers"]), seed=20261109)
    assert out.reached, f"spread={out.spread}"
    assert sum(out.counts.values()) == len(days) * 10
```

- [ ] **Step 3: 통과 확인**

Run: `.venv/bin/pytest tests/test_baseline.py -v`
Expected: PASS

- [ ] **Step 4: 커밋**

```bash
git add tests/fixtures/baseline_commutes.json tests/test_baseline.py
git commit -m "test: 실제 1년치 출근표로 생성 품질 기준선 고정"
```

---

### Task 15: 배포 파일과 운영 문서

**Files:**
- Create: `deploy/duty-generator.service`, `deploy/duty-generator-backup.service`, `deploy/duty-generator-backup.timer`, `deploy/env.example`, `README.md`

- [ ] **Step 1: systemd 유닛 작성**

`deploy/env.example`
```
DUTY_SECRET_KEY=change-me-50-random-chars
DUTY_API_TOKEN=change-me-long-random-token
DUTY_ADMIN_PATH=manage-x7k2q
DUTY_ALLOWED_HOSTS=<machine>.<tailnet>.ts.net,127.0.0.1,localhost
DUTY_CSRF_ORIGINS=https://<machine>.<tailnet>.ts.net
DUTY_DB_PATH=/var/lib/duty_generator/db.sqlite3
```

`deploy/duty-generator.service`
```ini
[Unit]
Description=duty_generator (Django)
After=network-online.target

[Service]
User=duty
WorkingDirectory=/opt/duty_generator
EnvironmentFile=/etc/duty_generator/env
ExecStart=/opt/duty_generator/.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8090 --workers 2
Restart=always

[Install]
WantedBy=multi-user.target
```

`deploy/duty-generator-backup.service`
```ini
[Unit]
Description=duty_generator SQLite 백업

[Service]
Type=oneshot
User=duty
EnvironmentFile=/etc/duty_generator/env
ExecStart=/bin/sh -c 'mkdir -p /var/backups/duty_generator && sqlite3 "$DUTY_DB_PATH" ".backup /var/backups/duty_generator/db-$(date +%%Y%%m%%d).sqlite3" && ls -1t /var/backups/duty_generator/db-*.sqlite3 | tail -n +31 | xargs -r rm --'
```

`deploy/duty-generator-backup.timer`
```ini
[Unit]
Description=duty_generator 매일 백업

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 2: README 작성** — `README.md`

````markdown
# duty_generator

IT 당번표 웹. 회차 단위로 부서 출근표를 취합하고, 장중관제 당번을 생성·배포하고, 근무 변경을 기록한다.
설계: `docs/superpowers/specs/2026-11-09-duty-generator-design.md`

## 개발

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
DUTY_DEBUG=1 .venv/bin/python manage.py migrate
DUTY_DEBUG=1 .venv/bin/python manage.py createsuperuser
DUTY_DEBUG=1 .venv/bin/python manage.py runserver
```

## 설치 (사내 서버, 노티파이어와 같은 서버)

```bash
sudo useradd -r -s /usr/sbin/nologin duty
sudo mkdir -p /opt/duty_generator /etc/duty_generator /var/lib/duty_generator
sudo chown duty: /var/lib/duty_generator
# 코드 배치 후
cd /opt/duty_generator && python3 -m venv .venv && .venv/bin/pip install .
sudo cp deploy/env.example /etc/duty_generator/env   # 값 채우기 (SECRET_KEY, API 토큰은 python -c "import secrets;print(secrets.token_urlsafe(48))")
sudo -u duty sh -c 'set -a; . /etc/duty_generator/env; .venv/bin/python manage.py migrate && .venv/bin/python manage.py collectstatic --noinput'
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now duty-generator duty-generator-backup.timer
```

## 외부 공개 (Tailscale Funnel)

443 포트를 경로로 나눈다. 웹은 `/`, 노티파이어 카카오 웹훅은 기존 경로를 유지한다.

```bash
sudo tailscale funnel --bg --set-path / http://127.0.0.1:8090
sudo tailscale funnel status
```

노티파이어는 Funnel을 거치지 않고 `http://127.0.0.1:8090/api/assignments` 를 `Authorization: Bearer $DUTY_API_TOKEN` 으로 호출한다.

## 처음 한 번: 기존 시트 가져오기

```bash
sudo -u duty sh -c 'set -a; . /etc/duty_generator/env; .venv/bin/python manage.py import_sheets --dry-run'
sudo -u duty sh -c 'set -a; . /etc/duty_generator/env; .venv/bin/python manage.py import_sheets'
```

이후 `/<DUTY_ADMIN_PATH>/` 의 멤버 목록에서 멤버를 선택하고 "계정 발급 / 비밀번호 초기화" 액션으로 임시 비밀번호를 발급한다.
부서 입력 담당자는 부서 화면의 "입력 담당자"에서 지정한다. 어드민은 사용자 화면에서 "스태프 권한"을 켠다.

## 운영 메모

- 로그인 5회 실패 시 그 계정은 15분 잠긴다. Admin의 Axes 메뉴에서 해제할 수 있다.
- 백업: 매일 03:00 `/var/backups/duty_generator/` 에 최근 30개 보관.
````

- [ ] **Step 3: 운영 설정 점검**

Run: `DUTY_SECRET_KEY=x DUTY_ALLOWED_HOSTS=example.ts.net DUTY_CSRF_ORIGINS=https://example.ts.net .venv/bin/python manage.py check --deploy 2>&1 | tail -20`
Expected: 경고 목록이 나온다. `SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT`, `SECRET_KEY` 길이 경고만 남아야 한다(HTTPS는 Funnel이 종료하고 ts.net 도메인은 HSTS preload 대상이므로 무시). 다른 경고가 있으면 수정한다.

- [ ] **Step 4: 전체 테스트**

Run: `.venv/bin/pytest`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add deploy README.md
git commit -m "docs: 배포 유닛, 백업 타이머, 운영 README"
```
