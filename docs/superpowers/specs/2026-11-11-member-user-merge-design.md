# 멤버·계정(User) 통합 설계

사용자 요청(2026-11-10 제안, 2026-11-11 진행 결정): 당번표 멤버 칼럼을 실제 서비스 계정(User)에 붙여 한 테이블로 만든다. 멤버 코드는 로그인 아이디로 쓰고 PK는 따로 둔다.
결정 과정: Claude 초안 → 사용자 결정(재직·로그인 한 칸, 방식 A 새 스키마+변환, 코드=아이디, 시트 가져오기·API 삭제) → Codex 토론.

## 범위

1. `Member` 모델을 없애고 커스텀 사용자 모델 `duty.User`(AUTH_USER_MODEL)에 근무표 칸을 붙인다.
2. 마이그레이션 0001~0009를 새 `0001_initial` 하나로 다시 만든다(기존 DB는 변환 명령으로 옮김).
3. 함께 삭제: `import_sheets` 명령·`duty/importer.py`(1회 이관 끝남), `/api/assignments`·`DUTY_API_TOKEN`(노티파이어 은퇴로 소비자 없음).

## 데이터 모델

`duty.User(AbstractUser)`

| 칸 | 내용 |
|---|---|
| `id` | 자동 PK |
| `username` | 로그인 아이디 = 예전 멤버 코드. Django 기본 규칙(unique, 150자) |
| `name` | 이름. unique, `validate_member_name`(`>` `,` 줄바꿈 금지, `+`로 시작 금지) 그대로 |
| `department` | FK(Department, PROTECT, null 허용, related_name="members"). **null = 근무표 대상 아님**(어드민 전용 계정) |
| `part` | 파트(빈 값 허용) |
| `type` | 스태프/개발자(빈 값 허용). CheckConstraint: `type in (STAFF, DEVELOPER)` 또는 (`department is null` 이고 `type == ""`). 부서가 있으면 `type` 필수 |
| `is_active` | **재직**. 끄면 근무표 후보에서 빠지고 로그인도 막힌다(스태프 예외 없음). verbose_name "재직" |
| `must_change_password` | 첫 로그인 비밀번호 변경 필요 |
| 그 밖 | `password`, `is_staff`, `is_superuser`, `last_login`, `date_joined`, `first_name`·`last_name`·`email`(쓰지 않지만 기본 칸 유지), `groups`·`user_permissions` |

- `__str__` = `name`.
- 근무표 대상 = `department__isnull=False, is_active=True`. 이를 모델 매니저 메서드 하나(`User.objects.roster()`)로 둔다.
- 계정 발급 전 멤버는 `set_unusable_password()` 상태(로그인 불가).
- 다른 모델의 연결:
  - `Commute.member`, `ControlDuty.member`, `ChangeLog.before`/`after` → `settings.AUTH_USER_MODEL`(PROTECT, 필드 이름 유지)
  - `Department.managers` → M2M(AUTH_USER_MODEL, related_name="managed_departments")
  - `ChangeLog.by`, `RosterPref`, `CalendarFeed`, `TelegramAlarmProfile`, `PushAlarmSubscription`, `AlarmRule` → 그대로 AUTH_USER_MODEL
- 기존 제약(choices + CheckConstraint, 출근조 하루 하나 등)은 그대로 다시 만든다.

## 동작 변경

- **재직 하나로**: 지금의 `Member.is_active`(재직)와 `User.is_active`(로그인)가 한 칸이 된다. 퇴사 처리 = 재직 끄기 → 로그인 차단 + 근무표 후보 제외. 퇴사한 스태프가 로그인하던 예외는 없어진다(Django 기본 `is_active` 검사로 로그인 거부). 이미 로그인된 세션도 끊긴다(Django `ModelBackend.get_user`가 비활성 사용자를 돌려주지 않아 다음 요청부터 익명). 그래서 `ForcePasswordChangeMiddleware`의 "퇴사 멤버 로그아웃" 분기는 삭제하고, 이 동작을 테스트로 고정한다.
- **기본 알림 규칙**: 지금은 User 생성(post_save) 때 만든다. 앞으로는 `issue_account()`(계정 발급) 때, 그 계정에 규칙이 하나도 없을 때만 만든다. post_save 신호는 삭제.
- **계정 발급** `issue_account(user)`: 임시 비밀번호 설정, axes 잠금 해제, `must_change_password=True`, 기본 알림 규칙(없을 때만). "이미 다른 계정이 그 아이디를 씀" 오류는 사라진다(아이디가 곧 그 사람).
- `perms.member_of(user)` 삭제. 근무표 관련 판단은 `user.department_id`와 `user.is_active`로 한다. 캘린더 `NO_MEMBER` 오류 문구는 "근무표 대상 계정만 쓸 수 있습니다."로 바꾼다(부서 없는 계정).
- 입력 담당자: `Department.managers`가 User를 직접 가리킨다.
- 근무 변경·생성·통계·취합·캘린더·알림 등 `Member`를 쓰던 모든 곳은 `User.objects.roster()`/User 필드로 바꾼다. 화면 문구는 그대로("멤버" 표기가 화면에 보이면 그대로 둔다).

## 관리 화면

- "멤버"·"사용자" 두 메뉴를 **"사용자"** 하나로(`duty.User`용 `UserAdmin` 상속).
- 목록: 아이디, 이름, 부서, 파트, 구분, 재직, 스태프. 필터: 부서, 구분, 재직, 스태프. 검색: 아이디, 이름.
- 편집 화면에 근무표 칸(이름·부서·파트·구분) 묶음 추가. 추가 화면은 비밀번호 없이 만들 수 있게(발급은 액션으로).
- 액션 [계정 발급 / 비밀번호 초기화] 유지(전체 롤백 동작 그대로).
- 부서 화면의 입력 담당자 선택은 근무표 대상 계정만 보인다.
- `schema.html`(스키마 설명 화면)도 새 구조로 고친다.

## 변환 명령 `manage.py convert_v1 <예전 DB 경로>`

예전(0009까지) SQLite 파일을 **읽기 전용**으로 열어 현재 DB(새 스키마, `migrate` 직후 비어 있어야 함)에 옮긴다.

1. 사전 검사(하나라도 걸리면 아무것도 쓰지 않고 오류):
   - 예전 DB의 `django_migrations`에서 duty 마지막 마이그레이션이 `0009_calendarfeed`인지
   - 대상 DB의 `duty_user`·`duty_department`가 비어 있는지
   - 멤버와 연결되지 않은 계정의 username이 어떤 멤버 코드와 같지 않은지
2. 계정 만들기(한 트랜잭션):
   - 멤버마다 User 1개: `username=code`, name·department·part·type 복사.
     - 연결된 계정이 있으면 그 계정의 `password`·`is_staff`·`is_superuser`·`last_login`·`date_joined` 복사, `is_active = member.is_active and user.is_active`, `must_change_password` 복사. 계정 username이 코드와 다르면 코드를 쓰고 건수만 출력.
     - 없으면 사용할 수 없는 비밀번호, `is_active=member.is_active`, `date_joined=변환 시각`.
   - 멤버와 연결되지 않은 계정마다 User 1개: username·비밀번호·권한·활성 그대로, `name=username`, 부서 없음.
   - 이름 충돌(어드민 username이 어떤 멤버 이름과 같음)은 사전 검사에서 오류.
   - 예전 `auth_user.id` → 새 id, 예전 `duty_member.id` → 새 id 대응표를 메모리에 둔다.
3. 복사: Department(+managers 대응표로), Period, Commute, ControlDuty, ChangeLog(by·before·after), RosterPref, CalendarFeed, TelegramAlarmProfile(연결 대기 코드 칸은 비움), PushAlarmSubscription, AlarmRule, AlarmDelivery. PK는 User 외에는 예전 값 유지.
4. 버림: 세션, axes 기록, 관리 화면 LogEntry, 권한 그룹(쓰지 않음 — 있으면 건수 출력 후 버림).
5. 끝에 테이블별 예전/새 건수를 출력(이름 출력 금지). 계정 행에 대한 기본 알림 규칙은 만들지 않는다(예전 규칙만 복사).
6. PK를 지정해 넣어도 SQLite `AUTOINCREMENT`의 `sqlite_sequence`가 자동으로 따라오므로 이후 새 행 id가 겹치지 않는다(테스트로 확인: 변환 후 새 행 생성).

## 운영 전환 (1회, README)

```bash
sudo systemctl stop duty-alarms duty-generator
sudo -u duty sqlite3 /var/lib/duty_generator/db.sqlite3 ".backup /var/backups/duty_generator/before-v2.sqlite3"
sudo -u duty mv /var/lib/duty_generator/db.sqlite3 /var/lib/duty_generator/db-v1.sqlite3   # -wal/-shm 도 함께
(코드 갱신·설치는 upgrade.sh 의 해당 단계 — 단, migrate 는 빈 새 DB 에)
dm migrate
dm convert_v1 /var/lib/duty_generator/db-v1.sqlite3
sudo systemctl start duty-generator (+ duty-alarms)
```

- 모두 다시 로그인한다. 문제가 생기면 서비스 중지 → `db-v1.sqlite3`를 원래 이름으로 → 예전 버전 코드로 되돌린다.
- 이 전환에는 `upgrade.sh`를 그대로 쓸 수 없다(빈 DB 준비가 필요). README에 전환 절차를 따로 쓴다. 정확한 명령은 구현 계획에서 확정하고 개발 DB로 리허설한다.
- `convert_v1`은 전환이 끝난 뒤 다음 정리 때 삭제해도 된다(1회용).

## 테스트

- 예전 스키마 fixture: 현재 main(0009)으로 migrate한 빈 DB의 스키마를 `tests/fixtures/v1_schema.sql`로 저장(데이터 없음, 실명 없음).
- 변환 테스트: fixture로 임시 DB 생성 → 가상 데이터(연결된 멤버, 계정 없는 멤버, 퇴사 멤버, 어드민 전용 계정, 배정·변경기록·알림·캘린더) 삽입 → 변환 → 대응 관계·is_active 규칙·비밀번호 해시 보존·건수 확인. 사전 검사 실패 3종(마이그레이션 버전, 대상 비어 있지 않음, 아이디 충돌·이름 충돌) 각각.
- 기존 테스트 전체를 새 모델로 옮겨 통과(`-W error`). `Member` 팩토리는 User 팩토리로.
- 동작 변경 테스트: 퇴사(재직 끔) 계정 로그인 거부(스태프 포함), 부서 없는 계정은 근무표 후보·캘린더 발급 제외, 계정 발급 때 기본 알림 규칙 생성(이미 있으면 안 만듦), 관리 화면 사용자 목록·발급 액션.
- 화면 확인(1400px·390px): 관리 화면 사용자 목록·편집, 근무표·근무 변경 팝업 후보, 알림·캘린더 화면.

## 범위 밖

- 이름(first/last)·이메일 칸 제거, 사용자 목록 화면 별도 제작, 노티파이어 저장소 정리.
