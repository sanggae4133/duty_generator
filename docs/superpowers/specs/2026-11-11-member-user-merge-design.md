# 멤버·계정(User) 통합 설계

사용자 요청(2026-11-10 제안, 2026-11-11 진행 결정): 당번표 멤버 칼럼을 실제 서비스 계정(User)에 붙여 한 테이블로 만든다. 멤버 코드는 로그인 아이디로 쓰고 PK는 따로 둔다.
결정 과정: Claude 초안 → 사용자 결정(재직·로그인 한 칸, 방식 A 새 스키마+변환, 코드=아이디, 시트 가져오기·API 삭제) → Codex 토론(개정 1: 마이그레이션 생성·구 DB 차단·WAL 안전 전환·사전 검사·필드 보존·후보/역사 구분·PK 보존, 개정 2→배포 전 확인으로 2단계 배포 생략).

## 범위

1. `Member` 모델을 없애고 커스텀 사용자 모델 `duty.User`(AUTH_USER_MODEL)에 근무표 칸을 붙인다.
2. 기존 마이그레이션 0001~0009를 지우고 **`makemigrations`로 새 `0001_v2`를 생성**한다(손으로 합치지 않음). 이름을 `0001_initial`과 다르게 해서 예전 DB에 실수로 `migrate`하면 확실히 실패하게 한다(테이블 충돌 또는 `InconsistentMigrationHistory`). (배포 전이라 별도 가드는 두지 않는다.)
3. 함께 삭제: `import_sheets` 명령·`duty/importer.py`·관련 테스트, `openpyxl` 의존성(lock 포함), `/api/assignments`·`duty/api.py`·`api_assignments` URL·테스트·`DUTY_API_TOKEN`(settings·test_settings·env.example·README·CLAUDE.md).

## 데이터 모델

`duty.User(AbstractUser)`

| 칸 | 내용 |
|---|---|
| `id` | 자동 PK. **변환 때 예전 멤버 id를 그대로 쓴다**(아래) |
| `username` | 로그인 아이디 = 예전 멤버 코드. Django 기본 규칙(unique, 150자, 기본 validator) |
| `name` | 이름. unique, max 32, `validate_member_name`(`>` `,` 줄바꿈 금지, `+`로 시작 금지) |
| `department` | FK(Department, PROTECT, null 허용, related_name="members"). **null = 근무표 대상 아님**(어드민 전용 계정) |
| `part` | 파트(빈 값 허용) |
| `type` | 스태프/개발자 또는 빈 값. CheckConstraint: (`department` 있음 그리고 `type in (STAFF, DEVELOPER)`) 또는 (`department` 없음 그리고 `type == ""`) |
| `is_active` | **재직**(verbose_name "재직"). 끄면 근무표 후보에서 빠지고 로그인도 막힌다(스태프 예외 없음) |
| `must_change_password` | 첫 로그인 비밀번호 변경 필요 |
| 그 밖 | `password`, `is_staff`, `is_superuser`, `last_login`, `date_joined`, `first_name`·`last_name`·`email`(기본 칸 유지), `groups`·`user_permissions` |

- `__str__` = `name`.
- 근무표 **후보** = `User.objects.roster()` = `department__isnull=False, is_active=True`.
- 계정 발급 전 멤버는 사용할 수 없는 비밀번호(로그인 불가).
- 다른 모델의 연결(필드 이름 유지):
  - `Commute.member`, `ControlDuty.member`, `ChangeLog.before`/`after` → AUTH_USER_MODEL(PROTECT)
  - `Department.managers` → M2M(AUTH_USER_MODEL, related_name="managed_departments")
  - `ChangeLog.by`, `RosterPref`, `CalendarFeed`, `TelegramAlarmProfile`, `PushAlarmSubscription`, `AlarmRule` → AUTH_USER_MODEL(그대로)
- 기존 제약(choices + CheckConstraint, 출근조 하루 하나 등)은 모델에 그대로 두고 `makemigrations`가 새 0001에 담는다. 새 0001에 데이터 생성 작업(예전 0007 기본 알림 규칙)은 넣지 않는다.

## 후보와 역사 구분

- **후보**(새로 배정·교체·추가·맞교환 대상, 생성 풀, 취합 입력 대상 목록, 입력 담당자 선택): `roster()`만.
- **역사·표시**(이미 배정된 사람 표시, 변경기록, 과거 통계, 보고서 알림의 이름·부서, 근무표 조회): 비활성·부서 없는 계정도 그대로 보인다.
- 퇴사자의 기존 배정은 보이고 **제거**할 수 있지만, 퇴사자를 새로 들이거나 **맞교환으로 옮기는 것은 막는다**(지금 `swap`은 활성 검사가 없음 → 양쪽 모두 `is_active` 검사 추가).
- 알림: 규칙 소유자 `user__is_active=True`만(예전 "퇴사 스태프 예외" 제거). 개인 근무 알림은 부서 있는 계정만 대상이 생기고, 보고서형 알림은 부서 없는 어드민도 받는다(지금과 같음).
- 캘린더: 부서 없는 계정은 발급 불가(문구 "근무표 대상 계정만 쓸 수 있습니다."), 비활성 계정 피드는 빈 캘린더(지금과 같음). UID의 `member_pk`는 User id — 멤버 id를 그대로 쓰므로 전환 후에도 같다.

## 동작 변경

- **재직 하나로**: 퇴사 처리 = 재직 끄기 → 로그인 차단 + 후보 제외. 이미 로그인된 세션도 다음 요청부터 익명(Django `ModelBackend.get_user`가 비활성 사용자를 돌려주지 않음). `ForcePasswordChangeMiddleware`의 "퇴사 멤버 로그아웃" 분기는 삭제하고 동작을 테스트로 고정.
- **기본 알림 규칙**: post_save 신호 삭제. `issue_account(user)`에서 **최초 발급일 때만**(호출 전 `has_usable_password()`가 false) 기본 규칙을 만든다. 비밀번호 초기화는 규칙을 건드리지 않는다.
- **계정 발급** `issue_account(user)`: 임시 비밀번호, axes 잠금 해제, `must_change_password=True`, 최초 발급이면 기본 규칙. "다른 계정이 그 아이디를 씀" 오류는 사라진다.
- `perms.member_of()` 삭제. 근무표 판단은 `user.department_id`·`user.is_active`.
- `code` → `username` 전면 교체: 서비스(`member__code` → `member__username`), 템플릿(`m.code` → `m.username`), 폼 값. 완료 조건: `rg '\bMember\b|member__code|user\.member\b|\.code\b'`가 부서 코드(`Department.code`)·의도된 곳 외 0건.
- `django.contrib.auth.models.User` 직접 import는 `get_user_model()` 또는 `duty.models.User`로(코드·테스트 모두).
- 화면 문구는 그대로("멤버" 표기 유지).

## 관리 화면

- "멤버"·"사용자" 두 메뉴를 **"사용자"** 하나로(`django.contrib.auth.admin.UserAdmin` 상속).
- 목록: 아이디, 이름, 부서, 파트, 구분, 재직, 스태프. 필터: 부서, 구분, 재직, 스태프. 검색: 아이디, 이름.
- 편집 화면에 근무표 칸 묶음(이름·부서·파트·구분). **추가 화면은 비밀번호 없이**(아이디·이름·부서·파트·구분) 만들고 사용할 수 없는 비밀번호를 설정한다. 발급은 액션으로.
- 액션 [계정 발급 / 비밀번호 초기화] 유지(전체 롤백).
- 부서 화면의 입력 담당자 선택은 `roster()`만.
- `schema.html`(스키마 설명 화면)을 새 구조로.

## 변환 명령 `manage.py convert_v1 <예전 DB 백업 파일>`

예전(0009까지) SQLite 백업 파일을 **URI `mode=ro`로** 열어 현재 DB(새 0001_v2만 적용된 빈 DB)에 옮긴다. 원본 경로가 현재 DB 경로와 같으면 거부.

### 사전 검사 (하나라도 걸리면 아무것도 쓰지 않음, 이유를 한국어로 출력, 이름·비밀값 출력 금지)

- 원본: `PRAGMA quick_check` = ok, `PRAGMA foreign_key_check` 결과 없음, `django_migrations`의 duty 행이 정확히 0001~0009(이름 집합 일치), 필요한 테이블·칼럼 존재.
- 대상: `django_migrations`의 duty 행이 `0001_v2` 하나, 업무 테이블(부서·사용자·회차·배정·변경기록·설정·캘린더·텔레그램·푸시·규칙·발송) 모두 비어 있음.
- 최종 사용자 집합(만들 User 각각): `username`·`name` 필드의 길이·validator 전부 실행(SQLite는 길이를 강제하지 않으므로 기존 멤버 이름도 검사), username 중복 없음, name 중복 없음.
- `auth_user_groups`·`auth_user_user_permissions`·`auth_group`에 행이 있으면 거부(쓰지 않는 기능, 있으면 사람이 판단).

### 사용자 만들기 (전체가 한 트랜잭션)

- 멤버마다 User 1개, **`id = 예전 멤버 id`**, `username=code`, name·department·part·type 복사.
  - 연결된 계정이 있으면 그 계정의 `password`·`is_staff`·`is_superuser`·`last_login`·`date_joined`·`first_name`·`last_name`·`email` 복사, `is_active = member.is_active and user.is_active`, `must_change_password` 복사. 계정 username이 코드와 달랐으면 코드를 쓰고 건수만 출력.
  - 없으면 사용할 수 없는 비밀번호, `is_active=member.is_active`, `date_joined=변환 시각`.
- 멤버와 연결되지 않은 계정마다 User 1개, `auth_user.id` 순서대로 `id = (멤버 id 최댓값 또는 0) + 1, +2, …`, username·비밀번호·권한·활성·시각·이름 칸 그대로, `name=username`, 부서 없음.
- 대응표: 예전 멤버 id → 같은 id(항등), 예전 `auth_user.id` → 새 id.

### 복사

- Department(+managers), Period, Commute, ControlDuty, ChangeLog(by·before·after), RosterPref, CalendarFeed, TelegramAlarmProfile(연결 대기 코드 칸은 비움), PushAlarmSubscription, AlarmRule, AlarmDelivery. **PK는 모두 예전 값 유지**(그래서 `AlarmDelivery.destination="sub:<id>"`도 맞음).
- `auto_now_add`/`auto_now` 칸(`ChangeLog.at`, `PushAlarmSubscription.created_at`, `AlarmDelivery.updated_at` 등 모델 전체에서 확인)은 생성 후 `update()`로 원래 값을 되돌린다. JSON·null·해시 값은 그대로.
- `auth_permission`·`django_content_type`은 복사하지 않는다(새 DB의 migrate가 만든 것 사용).
- 버림(건수만 출력): 세션, axes 기록, 관리 화면 LogEntry.
- 끝에 테이블별 예전/새 건수 출력. 기본 알림 규칙은 만들지 않는다(예전 규칙만 복사).
- PK를 지정해 넣어도 SQLite `AUTOINCREMENT`의 `sqlite_sequence`가 따라오므로 이후 새 행 id가 겹치지 않는다(모든 복사 테이블에서 테스트).

## 기존 DB 옮기기 (배포 전이라 1회 수동)

2026-11-11 사용자 확인: 아직 운영 배포 전이다. 그래서 2단계 배포·운영 가드·전환 스크립트(개정 2)는 **하지 않는다**. 이미 가져온 데이터가 있는 DB(개발 PC, 시험 설치 서버)만 README의 수동 절차로 옮긴다.

```bash
# 서비스(또는 runserver) 중지 후
sqlite3 <예전 DB> ".backup <예전 DB>-v1.sqlite3"        # WAL 까지 담긴 일관된 단일 파일
sqlite3 <예전 DB>-v1.sqlite3 "PRAGMA quick_check"      # ok
mv <예전 DB> <예전 DB>-wal <예전 DB>-shm 를 다른 폴더로(있는 것만, 롤백용)
git checkout <v2 버전> && 설치
manage.py migrate                                       # 빈 새 DB
manage.py convert_v1 <예전 DB>-v1.sqlite3
```

- 롤백: 새 DB 지우고 옮겨 둔 파일을 제자리로, 예전 버전 코드로.
- 실수로 예전 DB에 새 코드의 `migrate`를 돌리면 실패한다(이름이 다른 `0001_v2`). DB를 바꾸지 않고 멈추는지 개발 DB 사본으로 확인한다.
- `convert_v1`은 시험 서버까지 옮긴 뒤 다음 정리 때 지운다.

## 테스트

- **마이그레이션 그래프**: 빈 DB에 `migrate` → `duty_user` 있음, `auth_user` 없음, admin·auth·contenttypes·axes·sessions 정상, admin LogEntry FK가 `duty_user`. `makemigrations --check` 변경 없음.
- **예전 스키마 fixture**: 현재 main(0009)으로 migrate한 빈 DB의 전체 `.dump`(스키마 + `django_migrations`·contenttypes·permission 행, 업무 데이터 없음)를 `tests/fixtures/v1_empty.sql`로. 테스트가 fixture의 업무 테이블이 비어 있는지 검사.
- **변환**: fixture로 임시 DB → 가상 데이터 삽입(연결된 멤버 is_active 4조합·스태프, 계정 없는 멤버, 퇴사 멤버, 어드민 전용 계정, 입력 담당자, 배정·변경기록·알림 규칙·발송 기록·푸시·텔레그램·캘린더·화면 설정) → 변환 →
  - 모든 테이블의 PK·FK·시각·JSON·null·해시를 원본과 정확히 비교, 멤버 id = User id, `sub:<id>` 정합성, 캘린더 UID·토큰 해시 보존
  - 비밀번호 해시 보존(연결 계정으로 실제 로그인 성공), 계정 없는 멤버 로그인 불가
  - 변환 후 각 테이블 새 행 id > 기존 최댓값
  - 사전 검사 실패 각각(원본 버전·quick_check, 대상 비어 있지 않음, username·name 충돌, validator 위반, 그룹/권한 행, 원본=대상 경로) → 대상에 아무것도 없음
  - 중간 고의 실패(monkeypatch) → 대상 전체 롤백
- **동작**: 퇴사(재직 끔) 계정 로그인 거부(스태프 포함)·기존 세션 익명화, 퇴사자 기존 배정 표시·제거 가능, 퇴사자 신규 교체·추가·맞교환 불가, 부서 없는 계정 후보·캘린더 제외·보고서 알림 수신, 최초 발급 때만 기본 규칙(초기화 때 안 만듦, 규칙 지운 계정 초기화 후에도 0개), 관리 화면 추가 폼이 비밀번호 없이 unusable password 설정, 발급 액션.
- **리허설**: 개발 DB 사본으로 README 절차를 실제로 실행(WAL·SHM이 없는 경우 포함), 예전 DB에 새 `migrate`가 실패하고 DB가 그대로인지 확인. 결과를 PR에 적는다.
- 기존 테스트 전체를 새 모델로 옮겨 통과(`-W error`).
- 화면 확인(1400px·390px): 관리 화면 사용자 목록·추가·편집, 근무표·근무 변경 팝업 후보, 알림·캘린더 화면.

## 범위 밖

- first/last/email 칸 제거, 사용자 목록 화면 별도 제작, 노티파이어 저장소 정리.
