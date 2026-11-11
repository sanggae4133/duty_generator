# 멤버·계정 통합 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** `Member`를 커스텀 사용자 모델 `duty.User`로 합치고, 기존 DB는 `convert_v1`로 옮긴다.

**Architecture:** `duty.User(AbstractUser)` + 근무표 칸. 마이그레이션은 `makemigrations`로 새로 만든 `0001_v2` 하나. 변환은 예전 SQLite 파일을 읽기 전용으로 열어 raw SQL로 읽고 ORM으로 쓴다.

**Tech Stack:** Django 5.2, SQLite. 새 의존성 없음(`openpyxl` 제거).

**Spec:** `docs/superpowers/specs/2026-11-11-member-user-merge-design.md` (구속력 있는 기준)

## Global Constraints

- 화면 문구·오류는 한국어. 커밋 `feat:`/`fix:`/`docs:` + 한국어 요약.
- 테스트 먼저(실패 확인) → 구현. `.venv/bin/pytest -W error` 경고 0.
- DB 변경은 `duty/services/`(와 `duty/accounts.py`)만. "오늘"은 `perms.today()`.
- 실명 금지(테스트·fixture는 가상 이름). `db.sqlite3`는 열지 않는다(리허설은 컨트롤러가 사본으로).
- 화면 변경은 브라우저(1400px, 390px)에서 확인. DB 사본·스크린샷은 확인 후 삭제, 서버는 PID로 종료.

---

### Task 1: 시트 가져오기·API 삭제

**Files:** Delete `duty/management/commands/import_sheets.py`, `duty/importer.py`, `tests/test_importer.py`, `duty/api.py`, `tests/test_auth_api.py`의 API 부분(인증 테스트는 남김 — 파일을 나눠 판단). Modify `duty/urls.py`, `config/settings.py`(`API_TOKEN` 삭제), `config/test_settings.py`, `deploy/env.example`(`DUTY_API_TOKEN` 줄), `pyproject.toml`·`requirements.lock`(`openpyxl`, `et_xmlfile`), `README.md`("처음 한 번: 기존 시트 가져오기" 절, Funnel 절의 API 문단, `DUTY_API_TOKEN` 안내), `CLAUDE.md`(개발 명령의 import_sheets 줄, 연동 절, `replaced` 설명의 API 언급), `duty/shifts.py`·기타 주석의 importer/notifier 참조.

- [ ] `/api/assignments`가 404인 테스트 추가 → 실패 확인 → 삭제 → `rg -n "import_sheets|importer|api_assignments|API_TOKEN|openpyxl"`가 문서 역사(docs/superpowers) 외 0건 → 전체 테스트 → 커밋 `feat: 시트 가져오기·노티파이어 API 삭제`

### Task 2: `duty.User` 모델과 코드 전환

**Files:** `duty/models.py`, `duty/migrations/`(0001~0009 삭제 후 `makemigrations duty -n v2` → `0001_v2.py`), `config/settings.py`(`AUTH_USER_MODEL = "duty.User"`), `duty/apps.py`(post_save 삭제), `duty/accounts.py`, `duty/perms.py`, `duty/middleware.py`, `duty/admin.py`, `duty/services/*`, `duty/views/*`, `duty/templates/duty/*`(특히 `_cell_form.html`, `schema.html`), `tests/*` 전체.

**요구(스펙 "데이터 모델"·"후보와 역사 구분"·"동작 변경"·"관리 화면" 전부):**
- `User` 칸·제약·`objects.roster()`(커스텀 `UserManager` 상속 매니저에 메서드 추가), `__str__`=name.
- FK 대상 전환, `Department.managers` M2M → User.
- `perms.member_of` 삭제, `code`→`username` 전면 교체, `django.contrib.auth.models.User` 직접 import 금지(`get_user_model()`/`duty.models.User`).
- 후보는 `roster()`, 역사·표시는 전체. `changes.swap`에 양쪽 `is_active` 검사(오류 문구는 기존 `change_cell`의 퇴사자 문구와 같은 형식).
- 알림 대상 쿼리 단순화(`user__is_active=True`), 개인 근무 알림은 부서 있는 계정만, 보고서는 부서 없는 계정도.
- 캘린더 `NO_MEMBER` 문구 "근무표 대상 계정만 쓸 수 있습니다."(부서 없음), 비활성 → 빈 캘린더, UID의 member_pk = user.pk.
- 미들웨어의 퇴사 로그아웃 분기 삭제(비활성 세션은 Django가 익명화 — 테스트로 고정).
- `issue_account(user)`: 최초 발급(호출 전 `has_usable_password()` false)일 때만 `alarms.create_defaults`.
- 관리 화면: `UserAdmin` 상속 "사용자"(목록·필터·검색·근무표 칸 묶음, 추가 폼은 비밀번호 없이 unusable password), 발급 액션, 부서 입력 담당자 선택은 `roster()`.
- `schema.html` 새 구조.

**테스트(먼저, 스펙 "테스트"의 마이그레이션 그래프·동작 항목):**
- 빈 DB migrate: `duty_user` 있음, `auth_user` 없음, `django_admin_log.user_id`가 `duty_user` 참조. `makemigrations --check` 변경 없음.
- 퇴사 계정 로그인 거부(스태프 포함)·기존 세션 익명화; 퇴사자 기존 배정 표시·제거 가능, 신규 교체·추가·맞교환 불가; 부서 없는 계정 후보·캘린더 제외·보고서 알림 수신; 최초 발급 때만 기본 규칙(초기화 땐 안 만듦, 규칙 지운 계정 초기화 후 0개); 관리 화면 추가 폼(비밀번호 없이 → unusable), 발급 액션, 사용자 목록.
- 기존 테스트 전체를 새 모델로(멤버 팩토리 → User 팩토리; `conftest.py`).
- `rg -n '\bMember\b|member__code|user\.member\b|member_of|from django.contrib.auth.models import User'` → 0건(문서 역사 제외), `\.code\b`는 부서 코드만.

- [ ] 테스트 작성 → 실패 확인 → 구현 → 브라우저 확인(관리 화면 사용자 목록·추가·편집, 근무 변경 팝업 후보, 알림·캘린더) → 전체 테스트 → 커밋 `feat: 멤버를 사용자(User) 모델로 통합`

### Task 3: 변환 명령 `convert_v1`

**Files:** Create `duty/management/commands/convert_v1.py`(로직은 `duty/services/convert_v1.py`), `tests/fixtures/v1_empty.sql`, `tests/test_convert_v1.py`. Modify `README.md`(기존 DB 옮기기 절 — 스펙 "기존 DB 옮기기"의 명령).

**fixture 만들기:** main(`git worktree`로 Task 1 이전 커밋 `cd7d592`)에서 빈 임시 DB에 migrate → `sqlite3 tmp.db .dump > tests/fixtures/v1_empty.sql`. 업무 테이블은 비어 있음(테스트가 검사).

**요구:** 스펙 "변환 명령" 전부 — `mode=ro`, 원본=대상 경로 거부, 사전 검사 전체(원본 quick_check·foreign_key_check·duty 마이그레이션 정확히 0001~0009·필요한 테이블; 대상 duty 마이그레이션 `0001_v2` 하나·업무 테이블 비어 있음; 만들 User 각각 username·name 필드 validator·길이, 중복; 그룹·직접 권한 행 거부), User 생성 규칙(멤버 id 그대로, 연결 계정 칸 복사·is_active AND, 연결 없는 계정은 `auth_user.id` 순으로 `max(member id or 0)+1…`, name=username), 모든 테이블 PK 유지 복사, auto_now(_add) 값 `update()`로 복원(모델 전체에서 `auto_now` 칸 찾아 처리), 텔레그램 연결 대기 칸 비움, 세션·axes·LogEntry 버림(건수 출력), 테이블별 건수 출력(이름·비밀값 출력 금지), 전체 한 트랜잭션.

**테스트(먼저, 스펙 "변환" 항목 전부):** fixture로 임시 DB 생성 → 가상 데이터 삽입(raw SQL) → 변환 → 모든 테이블 PK·FK·시각·JSON·null·해시 원본 일치, 멤버 id = User id, `sub:<id>`, 캘린더 UID·토큰 해시, 연결 계정 실제 로그인 성공·계정 없는 멤버 로그인 불가, 새 행 id > 기존 최댓값(각 테이블), 사전 검사 실패 각각 → 대상 빈 상태, 중간 고의 실패 → 전체 롤백.

- [ ] 테스트 작성 → 실패 확인 → 구현 → 전체 테스트 → 커밋 `feat: 예전 DB 변환 명령(convert_v1)`

### Task 4: 문서·리허설

**Files:** `README.md`(관리 화면 "사용자" 메뉴·계정 발급 설명, 퇴사 처리 = 재직 끔(스태프 예외 없음), 기존 DB 옮기기 절 확인), `CLAUDE.md`(도메인 기준의 멤버·어드민 설명, 구조 원칙에 `duty.User`), `docs/superpowers/specs/2026-11-09-duty-generator-design.md`는 역사 문서라 두지 않고 맨 위에 "멤버는 2026-11-11 User로 통합됨(설계 링크)" 한 줄.

- [ ] 문서 수정 → 컨트롤러가 개발 DB 사본으로 README 절차 리허설(WAL·SHM 없는 경우 포함, 예전 DB에 새 migrate 실패·DB 무변경 확인) → 커밋 `docs: 멤버·계정 통합 문서`
