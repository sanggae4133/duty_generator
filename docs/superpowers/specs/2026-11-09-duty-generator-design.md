# duty_generator 설계

- 작성일: 2026-11-09
- 상태: 검토 중

## 1. 목적

구글 시트와 Apps Script로 운영하던 IT 당번표 제작 흐름을 웹 서비스 하나로 대체한다. 지금 쓰는 시트는 취합용 4개, 제작기 1개, 배포용 1개다. 웹 DB가 유일한 원본이 된다.

- 어드민: 회차를 만들고, 취합을 열고 닫고, 장중관제 당번을 생성하고, 배포한다.
- 부서 담당자: 취합이 열려 있는 동안 자기 부서 출근표를 입력한다.
- 멤버: 배포된 근무표를 조회하고, 근무를 변경한다.

## 2. 범위

포함
- 회차(기간) 단위 상태 관리: 취합 → 마감 → 생성(재실행 가능) → 배포
- 부서 출근표 입력: CSV 업로드와 칸 단위 편집
- 장중관제 당번 생성: 기존 Apps Script 알고리즘 이식
- 조회: 통합 근무표, 부서별 뷰, 내 근무, 날짜 상세. 날짜 상세는 모바일에서도 쓴다.
- 근무 변경과 변경 이력
- 당번 통계 (어드민 전용)
- 노티파이어용 읽기 전용 API
- 기존 시트 1회 가져오기
- 외부 공개(Tailscale Funnel)에 필요한 보안 설정

제외 (필요할 때 추가)
- 휴장일 처리. 회차 기간의 월~금은 휴장일이어도 모두 대상 날짜다. 휴장일 근무는 근무 변경으로 처리한다.
  - pykrx는 미래 휴장일을 알 수 없고(시세 데이터 기반, 과거 거래일만 반환) KRX 로그인을 요구해서 쓰지 않는다.
- 근무조와 관제 시간대 설정 화면. 코드 상수로 둔다.
- 순환 패턴 자동 생성. 부서는 엑셀에서 만들어 CSV로 올린다.
- 근무 변경 요청·승인 워크플로
- 생성 알고리즘 개선. 이식할 때는 동작을 바꾸지 않는다.
- 노티파이어 쪽 REST `RosterSource` 구현. duty_notifier repo에서 별도 작업으로 한다.

## 3. 운영 환경

- 노티파이어(`../duty_notifier`)와 같은 사내 서버에서 운영한다.
  - systemd + gunicorn, Python 3.12, Django
  - DB는 SQLite(WAL 모드)
  - 정적 파일은 whitenoise로 서빙
- 외부 공개는 Tailscale Funnel로 한다.
  - 443 포트를 경로로 나눈다. `/`는 이 웹으로, 노티파이어 카카오 웹훅은 기존 경로로 보낸다(`tailscale funnel --set-path`).
- 노티파이어는 Funnel을 거치지 않고 `127.0.0.1`로 직접 API를 호출한다.
- 비밀값(`SECRET_KEY`, API 토큰)은 환경변수로 받는다.
- 백업: systemd timer로 매일 `sqlite3 .backup`을 실행하고 최근 30개를 보관한다.

## 4. 근무조 정의 (코드 상수 `duty/shifts.py`)

출근조

| 키 | 표시 | 시간 |
|---|---|---|
| dawn | 새벽 | 06:30~15:30 |
| normal | 정상 | 08:00~17:00 |
| dinner | 석식교대 | 09:00~18:00 |
| night | 야간 | 13:30~21:30 |

장중관제 시간대 (slot 0~9)

| slot | 라벨 | 자격 출근조 |
|---|---|---|
| 0 | 08:30~09:30 | normal |
| 1~8 | 09:30~10:30 … 16:30~17:00 | normal, dinner |
| 9 | 17:00~18:00 | dinner |

장중관제 자격은 `type=개발자`이면서 그날 자격 출근조에 들어 있는 사람이다.

## 5. 역할과 권한

| 기능 | 어드민 | 부서 담당자 | 멤버 |
|---|---|---|---|
| 회차 생성, 상태 전환, 당번 생성, 배포 | O | | |
| 출근표 입력 (collecting 상태에서만) | 전 부서 | 자기 부서 | |
| 배포된 근무표 조회 (통합 / 부서별 / 내 근무 / 날짜 상세) | O | O | O |
| 근무 변경 (배포된 날짜, 출근조와 당번 모두) | O | O | O |
| 생성 결과 미리보기, 당번 통계, 변경 이력 | O | | |
| 멤버, 계정, 부서 담당자 관리 (Django Admin) | O | | |

- 어드민은 `User.is_staff`다.
- 부서 담당자는 `Department.managers`에 등록된 멤버다.
- 오늘 이전 날짜는 어드민만 수정할 수 있다. 이 규칙은 출근표 입력, 근무 변경, 배포 덮어쓰기 모두에 적용한다.
  - 검사는 서비스 계층 한 곳(`services.assert_can_edit_date`)에서 한다.
  - 기준 시간대는 Asia/Seoul이다. 오늘 날짜는 누구나 수정할 수 있다.
- 모든 권한은 서버에서 검사한다. 화면에서 버튼을 숨기는 것은 편의 기능일 뿐이다.

## 6. 회차 흐름

```
draft ──오픈──▶ collecting ──마감──▶ closed ──생성──▶ generated ──배포──▶ published
                    ▲                  │                  │
                    └──── 재오픈 ───────┴──────────────────┘ (재오픈하면 그 회차의 당번 삭제)
                                                generated ──재생성──▶ generated
```

| 상태 | 규칙 |
|---|---|
| draft | 이름과 기간을 정한다. 기간은 이 상태에서만 수정할 수 있다. |
| collecting | 출근표를 입력한다. 화면에 부서별 진행률(채워진 날짜 수 / 전체 평일 수)을 보여준다. |
| closed | 입력이 잠긴다. 4개 부서 모두 전체 평일이 채워져야 생성할 수 있다. |
| generated | 당번이 생성된 상태다. 어드민만 결과와 편차를 본다. 재생성하면 이 회차의 당번을 전부 교체한다. |
| published | 멤버와 API에 노출된다. 재생성은 불가능하고 근무 변경만 할 수 있다. |

기간 겹침과 배포 덮어쓰기
- 아직 배포되지 않은 회차끼리는 기간이 겹칠 수 없다.
- 배포된 회차와는 겹쳐도 된다. 예: A(published, 11/01~11/30), B(draft, 11/15~12/30)
- B가 배포되기 전까지는 A가 그대로 노출된다.
- 배포할 때 어드민이 덮어쓰기 시작일 `S`를 고른다. 기본값은 오늘이고, B 기간 안이면 과거 날짜도 고를 수 있다.
  - 다른 배포 회차의 날짜 `>= S` 출근조와 당번 행을 삭제한다. 이 처리는 날짜 단위라서 B가 A 안에 포함되는 경우도 같다.
  - B의 날짜 `< S` 행도 삭제한다.
  - 배포 전 확인창에 덮어쓸 날짜 범위와, 그 범위에 있던 근무 변경 건수를 보여준다.
  - 삭제된 행의 ChangeLog는 남긴다.
- 조회와 API는 "배포된 회차에 남아 있는 행"을 날짜로 읽는다. 한 날짜에는 배포 회차가 최대 하나만 남는다.
- 장중관제 편차는 생성하는 회차 안에서만 맞춘다. 덮어쓰기 이전 날짜의 배정 횟수는 고려하지 않는다. 통계 화면에서 날짜 범위로 합산해 볼 수 있다.

## 7. 데이터 모델

```
Department   code(MEMS/TMCH/MD/UI, PK), name, shifts(쉼표 구분 출근조 키; UI는 새벽 없음)
             managers M2M → Member

Member       code(TME01…, UNIQUE), name(UNIQUE), department FK, part, type(직원/개발자),
             is_active, user 1:1 → auth.User (nullable), must_change_password

Period       name, start_date, end_date, status, seed(nullable), generated_at, published_at,
             overwrite_from(nullable)

Commute      period FK, date, member FK, shift
             UNIQUE(period, date, member)            ← 하루에 출근조 하나

ControlDuty  period FK, date, slot(0~9), member FK
             UNIQUE(period, date, slot), UNIQUE(period, date, member)

ChangeLog    at, by(User, nullable=import), period FK, date,
             kind(commute|duty), shift_or_slot, before(Member, nullable), after(Member, nullable)
```

- 이름은 전체에서 고유하다. CSV와 시트가 이름으로 사람을 찾기 때문이다. 동명이인은 어드민이 구분 표기로 등록한다(예: 김민수A).
- 원본과 변경 표시
  - Commute와 ControlDuty는 항상 현재 상태다.
  - 칸의 `A>B` 표시는 그 칸에 쌓인 ChangeLog를 순서대로 이어 붙여 만든다(`A>B>C`).
  - before만 있으면 제거, after만 있으면 추가다.
- 대상 날짜는 `start_date~end_date`의 월~금이다.

## 8. 근무 변경

- 출근조 칸: 교체(A→B), 추가(→B), 제거(A→)
- 관제 칸: 교체만 한다. 관제 칸은 항상 1명이다.
- 맞교환: 같은 날짜의 두 칸에서 두 사람을 서로 바꾼다. 출근조끼리, 관제끼리, 출근조와 관제 사이 모두 된다.
  - 하루에 출근조 하나 제약 때문에 교체를 두 번 하면 중간에 제약에 걸린다. 그래서 맞교환은 한 트랜잭션으로 처리하고 ChangeLog를 2건 남긴다.
- 차단하는 경우
  - 없는 사람이거나 재직 중이 아닌 사람
  - 그날 이미 다른 출근조나 관제 칸에 있는 사람 (맞교환은 예외)
  - 지난 날짜를 어드민이 아닌 사람이 수정하는 경우
- 경고만 띄우고 저장은 허용하는 경우
  - 관제 자격 불일치 (개발자가 아니거나, 그날 자격 출근조가 아님)
- 동시 수정은 마지막에 저장한 쪽이 반영된다. ChangeLog에는 모두 남는다.

## 9. 장중관제 생성 알고리즘 (`duty/generator.py`, 순수 함수)

```python
def generate_control_duty(
    dates: list[date],
    commutes: dict[date, dict[str, set[str]]],   # 날짜 → 출근조 키 → member code
    developers: set[str],
    seed: int,
) -> dict[date, list[str]]:                       # 날짜 → slot 0~9 의 member code
```

기존 `InMarketControlDutyGenerator.gs`의 동작을 그대로 옮긴다.

- Phase 1 (Greedy)
  - 날짜마다 slot별 자격자 집합을 계산한다.
  - 자격자가 적은 slot부터 채운다.
  - 그날 아직 배정되지 않은 자격자 중 지금까지 배정 횟수가 가장 적은 사람을 고른다.
  - 동점이면 `random.Random(seed)`로 섞은 순서를 따른다. 기존 `Math.random() - 0.5` 정렬은 편향이 있어서 바꾼다.
- Phase 2 (Swap)
  - 최다 배정자의 slot 하나를 최소 배정자에게 넘긴다. 받는 사람은 그 slot 자격이 있고 그날 미배정이어야 한다.
  - 최대와 최소 차이가 `TARGET_SPREAD = 2` 이하가 되거나, 더 넘길 수 없거나, 10000회를 넘으면 멈춘다.
- 실패 처리
  - 자격자가 없는 slot이 있으면 `GenerationError`를 던진다. 실패한 `(날짜, slot, 후보 수)` 목록을 담는다.
  - 화면은 이 목록을 그대로 보여준다.
- 결과
  - seed와 사람별 횟수, 최대 편차, 목표 도달 여부를 기록한다.
  - 참고로 기존 1년치 결과는 133~139회, 편차 6이었다.

## 10. CSV 입력

- 인코딩: UTF-8(BOM 허용)을 먼저 시도하고, 실패하면 CP949로 읽는다. 한국어 Windows 엑셀의 기본 저장 형식이 CP949다.
- 헤더: `date`와 그 부서의 출근조 열. 열 이름은 줄바꿈이나 `(` 앞부분으로 매칭한다(`새벽\n(06:30~15:30)` → 새벽). `day` 열은 무시한다.
- 날짜: `YYYY-MM-DD`, `YYYY/M/D`, `YYYY. M. D.`
- 셀: 이름을 쉼표나 줄바꿈으로 구분하고, 앞뒤 공백은 무시한다.
- 검증 항목. 하나라도 실패하면 아무것도 반영하지 않고 `(행, 열, 사유)` 목록을 보여준다.
  - 회차 기간 안의 평일인지
  - 날짜가 중복되지 않는지
  - 그 부서 소속이고 재직 중인 멤버인지
  - 하루에 한 사람이 두 출근조에 들어가 있지 않은지
  - 어드민이 아니면 지난 날짜의 내용이 바뀌지 않았는지
- 반영: 그 부서의 해당 회차 출근조 전체를 파일 내용으로 교체한다.
- 내보내기: 현재 값이 채워진 같은 형식의 CSV를 내려받을 수 있다. UTF-8 BOM을 붙여서 엑셀에서 바로 열리게 한다.

## 11. 화면

| 화면 | 대상 | 내용 |
|---|---|---|
| 통합 근무표 (첫 화면) | 전체 | 날짜, 요일, 새벽, 정상, 석식교대, 관제 10칸, 야간. 오늘 행 강조와 자동 스크롤, 이름 검색(최대 3명) 강조, 변경된 칸 `A>B` 강조, 날짜 범위 필터. 칸을 클릭하면 근무 변경 팝업, 날짜를 클릭하면 날짜 상세로 이동한다. |
| 날짜 상세 | 전체, 모바일 대응 | 한 날짜의 출근조 4개와 관제 10칸을 세로로 나열. 이전/다음 날짜 이동, 칸마다 [변경] 버튼. 변경 폼은 기본 `<select>`를 쓰고 PC 팝업과 같은 폼을 재사용한다. |
| 부서별 뷰 | 전체 | IT운영(매칭엔진실/매매지원실 × 직원/개발자), 정보분배, UI를 탭으로 보여준다. |
| 내 근무 | 전체, 모바일 대응 | 본인의 출근조와 관제 시간대를 다가오는 순서로 보여준다. 일정을 탭하면 날짜 상세로 간다. |
| 출근표 입력 | 담당자, 어드민 | collecting 회차의 부서 표. CSV 업로드와 내려받기, 칸 편집. |
| 회차 관리 | 어드민 | 목록과 상태 전환, 부서별 진행률, 생성과 결과 미리보기(사람별 횟수, 편차), 배포(덮어쓰기 시작일, 확인창). |
| 당번 통계 | 어드민 | 날짜 범위별로 사람별 관제/새벽/야간 횟수, 평균, 표준편차, 최대 편차를 보여준다. |
| 변경 이력 | 어드민 | ChangeLog를 날짜, 사람, 수정자로 필터해서 보여준다. |
| 멤버, 계정 관리 | 어드민 | Django Admin. "계정 발급" 액션이 아이디(멤버 코드)와 임시 비번을 한 번만 표시한다. 사용자는 첫 로그인 때 비번을 바꿔야 한다. |

- 서버 렌더링 Django 템플릿과 htmx를 쓴다. 칸 변경과 저장은 부분 갱신한다.
- CSS는 CDN 프레임워크 하나(Pico.css)만 쓰고 빌드 단계는 없다.
- 통합 근무표는 모바일에서 가로 스크롤하고 날짜와 요일 열을 고정한다.
- 입력, 회차 관리, 통계 화면은 PC 기준이다.

## 12. 노티파이어 API

`GET /api/assignments?from=YYYY-MM-DD&to=YYYY-MM-DD` (from/to를 생략하면 배포된 날짜 전체)

```json
[
  {"date": "2026-11-10", "shift": "새벽",         "name": "홍성남", "replaced": null},
  {"date": "2026-11-10", "shift": "08:30~09:30", "name": "김경필", "replaced": "하원숙"}
]
```

- 배포된 데이터만 반환한다.
- `shift`는 출근조 표시명이나 관제 라벨을 그대로 쓴다. 근무조 이름 변환은 노티파이어 `source.columns`가 맡는다.
- `replaced`는 그 칸에서 이 사람이 들어오게 만든 마지막 ChangeLog의 before다. 노티파이어 `Assignment.replaced`와 의미가 같다.
- 인증은 `Authorization: Bearer <DUTY_API_TOKEN>`이다. 토큰이 없거나 틀리면 401을 반환한다.
- 비교는 `hmac.compare_digest`로 한다.

## 13. 기존 시트 가져오기 (`manage.py import_sheets [--dry-run]`)

공개된 시트를 xlsx export URL로 받는다.

| 원본 | 대상 |
|---|---|
| 제작기 `tb_member` | Department 4개, Member |
| 배포용 `view_all_combine` | Period "시트 이관"(2026-08-10~2027-09-03, published). Commute와 ControlDuty를 생성 당시 원본으로 저장한다. |
| 배포용 `근무표` | 칸마다 `A>B`(`A->B`) 체인을 파싱해서 원본과 비교한다. 차이를 ChangeLog(by=import)로 기록하고 현재 상태에 반영한다. |

- 배포용 파일을 기준으로 한다. 제작기 데이터는 09-07부터라 08-10~09-04 구간이 없다.
- 없는 이름이나 하루 중복이 있으면 중단하고 목록을 출력한다. 시트를 고친 뒤 다시 실행한다.
- 출근조 행의 부서는 멤버의 소속 부서로 정한다.
- 실행이 끝나면 건수를 리포트한다(멤버, 날짜, 출근조, 관제, 변경). 최종 상태는 배포용 `근무표`의 최종 근무자와 같아야 한다.

## 14. 보안 (Funnel 공개 전제)

- 로그인 시도 제한: `django-axes`. 같은 계정이나 IP로 5회 실패하면 15분 동안 잠긴다. 잠금은 Admin에서 조회하고 해제할 수 있다.
- 쿠키와 HTTPS
  - `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS
  - `ALLOWED_HOSTS`와 `CSRF_TRUSTED_ORIGINS`는 Funnel 도메인으로 고정한다.
  - `SECURE_PROXY_SSL_HEADER`를 설정한다.
- 세션은 14일 유지한다. 비번을 바꾸면 다른 세션은 무효가 된다(Django 기본 동작).
- 비밀번호는 Django 기본 검증기를 쓴다.
- Django Admin 경로는 환경변수로 받은 추측하기 어려운 경로로 둔다.
- API는 토큰 인증 필수다. Funnel을 거친 요청은 출발지가 `127.0.0.1`로 보이므로 IP 기반 차단에 의존하지 않는다.

## 15. 프로젝트 구조

```
manage.py
pyproject.toml
config/                  settings.py, urls.py, wsgi.py
duty/
  shifts.py              출근조, 관제 시간대 상수
  models.py              Department, Member, Period, Commute, ControlDuty, ChangeLog
  generator.py           장중관제 생성 (순수 함수)
  csv_io.py              CSV 파싱, 검증, 내보내기
  services.py            상태 전환, 출근표 반영, 근무 변경, 배포 덮어쓰기, 날짜 권한 검사
  views.py, urls.py      화면
  api.py                 노티파이어 API
  admin.py               멤버, 부서, 계정 발급 액션
  management/commands/import_sheets.py
  templates/duty/
tests/
deploy/                  duty-generator.service, duty-generator-backup.{service,timer}
```

- 화면, API, 명령은 `services.py`를 거쳐서만 데이터를 바꾼다. 권한, 날짜 규칙, ChangeLog 기록이 한 곳에 모인다.
- `generator.py`와 `csv_io.py`는 Django ORM에 의존하지 않는다.

## 16. 테스트 (pytest + pytest-django)

| 대상 | 검증 |
|---|---|
| generator | 모든 slot이 자격자인지, 하루 중복이 없는지, 같은 seed면 같은 결과인지, 후보가 없으면 실패 목록을 내는지 |
| 품질 기준선 | 기존 1년치 출근표 fixture로 생성했을 때 최대 편차가 6 이하인지 |
| csv_io | 인코딩 2종, 헤더와 날짜 형식, 각 검증 실패, 오류가 있으면 전체 미반영인지 |
| 권한과 상태 | 상태별 허용 동작, 담당자 부서 범위, 지난 날짜는 어드민만, 통계와 이력은 어드민만. 서버가 403을 반환하는지 확인한다. |
| 근무 변경 | 교체, 추가, 제거, 맞교환, 중복 차단, 자격 경고, ChangeLog 체인 표시 |
| 배포 덮어쓰기 | 시작일 이전은 유지, 이후는 교체, 포함 관계, 미배포 회차끼리의 겹침 거부 |
| API | 응답 형식, `replaced`, 토큰 401, 미배포 제외 |
| import_sheets | 저장해 둔 xlsx fixture로 실행했을 때 변경 393칸이 ChangeLog에 들어가고 최종 상태가 `근무표`와 일치하는지 |

브라우저 E2E 테스트는 만들지 않는다.

## 17. 결정 기록

- Django를 쓴다. 로그인, 권한 그룹, Admin, 템플릿이 기본 제공되고 화면 대부분이 표와 폼이다.
- 노티파이어는 FastAPI로 유지한다. FastAPI 의존은 웹훅 1개 파일뿐이고, 두 서비스는 API 하나로만 연결된다.
- 시트는 완전히 대체한다. 두 원본을 동기화하는 문제를 없애기 위해서다.
- 근무 변경은 로그인한 누구나 즉시 할 수 있다. 지금 시트 운영 방식을 유지하고, 이력과 지난 날짜 제한으로 통제한다.
- 휴장일은 처리하지 않는다. 신뢰할 수 있는 미래 휴장일 출처가 없고, 운영자가 근무 변경으로 대응한다.
