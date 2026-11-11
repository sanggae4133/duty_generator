# 설정 단순화: 루트 `.env` + 알림 설정 DB 설계

사용자 요청(2026-11-11): 설정을 `/etc`가 아니라 프로젝트 루트에, deploy 설명을 자세히, 텔레그램 토큰은 봇이 바뀔 수 있으니 테이블 한 행으로 두고 어드민이 고칠 수 있게. "운용·유지보수가 힘들면 안 된다." 아직 운영 배포 전. Codex 토론은 사용자 요청으로 구현 뒤에.

## 1. 루트 `.env`

- 개발·서버 공통으로 **저장소 루트의 `.env`** 하나. `/etc/duty_generator/env`는 없앤다.
- `config/settings.py`가 시작할 때 `BASE_DIR/.env`를 읽는다(표준 라이브러리만, `KEY=VALUE` 줄, 빈 줄·`#` 주석 무시, 값 앞뒤 공백 제거, 따옴표 없음). 이미 있는 환경변수가 이긴다(`os.environ.setdefault`). 파일이 없어도 동작.
- 테스트는 개발자의 `.env`를 읽지 않는다(`config/test_settings.py`가 읽기를 끄는 방법 — 예: `DUTY_ENV_FILE=""` 를 먼저 설정 — 을 쓰고 테스트로 고정).
- `.env`에 남는 값(서버 시작에 필요한 것만): `DUTY_SECRET_KEY`, `DUTY_DEBUG`, `DUTY_ALLOWED_HOSTS`, `DUTY_CSRF_ORIGINS`, `DUTY_SITE_URL`, `DUTY_DB_PATH`, `DUTY_ADMIN_PATH`, (선택) `DUTY_ALARMS_LOCK`, `DUTY_TELEGRAM_LOCK`.
- `.gitignore`에 `.env`. 루트에 항목마다 설명을 단 **`.env.example`**(개발 예시·서버 예시 값 함께). `deploy/env.example` 삭제.
- 서버: `/opt/duty_generator/.env`, `root:duty 640`. systemd 유닛은 `EnvironmentFile` 대신 settings가 직접 읽으므로 필요 없음 — 단 백업 유닛처럼 셸에서 `$DUTY_DB_PATH`를 쓰는 곳은 `EnvironmentFile=/opt/duty_generator/.env` 유지 또는 경로를 명령으로 얻도록 정리(구현에서 가장 단순한 쪽).
- `dm` 함수: `sudo -u duty /opt/duty_generator/.venv/bin/python /opt/duty_generator/manage.py "$@"`로 단순화. `upgrade.sh`·`restore.sh`·README의 `/etc/duty_generator/env` 참조 전부 교체.
- 시험 서버 1회 이전: `sudo mv /etc/duty_generator/env /opt/duty_generator/.env` + 권한 — README에 한 줄.

## 2. 알림 설정 DB (`AlarmSettings`, 한 행)

- 모델 `AlarmSettings`(마이그레이션 0002): `telegram_bot_token`, `telegram_bot_username`(앞 `@` 제거 저장), `ops_chat_id`(관리자 장애 알림, 양의 정수 또는 빈 값), `vapid_public_key`, `vapid_private_key`, `vapid_subject`(기본 `mailto:admin@localhost`), `updated_at`. 한 행만: `CheckConstraint(pk=1)` + 가져오기 함수 `get_or_create(pk=1)`.
- 0002는 데이터 이전도 한다: 마이그레이션 시점에 예전 환경변수(`DUTY_TELEGRAM_BOT_TOKEN`, `DUTY_TELEGRAM_BOT_USERNAME`, `DUTY_VAPID_PUBLIC_KEY`, `DUTY_VAPID_PRIVATE_KEY`, `DUTY_VAPID_SUBJECT`, `DUTY_OPS_CHAT_ID`)가 있으면 그 값으로 행을 채운다(시험 서버 이전용).
- `settings.py`에서 위 환경변수 읽기 삭제.
- 읽기: `duty/services/alarm_settings.py`의 `current()`. `duty/alarms/senders.py`는 ORM 없는 순수 계층을 유지한다 — 토큰·VAPID 값을 인자(작은 dataclass)로 받는다. 서비스·뷰·`run_alarms`가 `current()`로 읽어 넘긴다.
- **VAPID 자동 생성**: 푸시가 필요할 때(설정 화면 열기·구독·발송) 키가 비어 있으면 `py_vapid`로 만들어 저장(동시 생성 경합은 한 트랜잭션 + 다시 읽기로 처리). README의 수동 키 생성 절차 삭제.
- **관리 화면 "알림 설정"**(슈퍼유저): 한 행만(추가는 행 없을 때만, 삭제 불가). 토큰은 `PasswordInput(render_value=False)` — 비워 두면 그대로, 값을 넣으면 교체, "토큰 지우기" 체크로 비움. 화면에 토큰은 끝 4자리만 표시. 액션/버튼 [푸시 키 다시 만들기](확인 문구: 기존 기기 구독이 모두 끊김 → 저장 시 모든 `PushAlarmSubscription` 삭제).
- **봇 토큰이나 사용자명이 바뀌면**: 모든 `TelegramAlarmProfile`의 확인 상태(`verified_at`)와 연결 대기 코드를 비운다(새 봇에 [시작]을 다시 눌러야 하므로). 관리 화면 저장 후 메시지로 안내.
- 화면 안내(`/alarms/`): 꺼져 있을 때 "관리자가 관리 화면 → 알림 설정에서 텔레그램 봇 토큰을 넣으면 [텔레그램 연결] 버튼이 나타납니다." 푸시는 자동 생성이라 늘 켜짐(키 생성 실패 시에만 안내).
- 로그·화면에 토큰 원문 금지(기존 규칙 유지).

## 3. 장애 점검 `manage.py health`

- `deploy/duty-health.sh`를 관리 명령으로 대체(같은 점검: 웹 응답 `http://127.0.0.1:8090/login/`, `duty-alarms`가 enabled일 때 active, 26시간 안 백업, DB 디스크 90%; 상태가 바뀔 때만 `ops_chat_id`로 텔레그램; 첫 정상은 기록만; 발송 실패 시 상태 저장 안 함). `systemctl`·`df`는 subprocess/`shutil.disk_usage`. 백업 폴더 경로는 상수(`/var/backups/duty_generator`) 또는 `.env`의 선택 값.
- `duty-health.service`가 `manage.py health` 실행. 테스트는 subprocess·HTTP·발송을 monkeypatch.

## 4. 문서

- README 맨 위 **폴더 구조** 표: `config/`(Django 프로젝트 코드 — 설정값은 `.env`가 정함), `duty/`(앱), `deploy/`(서버 설치 파일), `tests/`, `docs/`, `.env.example`.
- **`deploy/` 파일별 설명**(무엇·언제·어디로 복사): 각 `.service`/`.timer`, logrotate, `upgrade.sh`, `restore.sh`.
- 설치·업그레이드 절차를 `.env` 기준으로. 알림 절의 설정값 표는 "관리 화면 → 알림 설정"으로.
- CLAUDE.md: 비밀값 규칙을 "서버 기동 값은 `.env`, 알림 봇·푸시 키는 DB `AlarmSettings`(관리 화면)"로.

## 테스트

- `.env` 읽기: 주석·빈 줄·환경변수 우선·파일 없음, 테스트가 개발자 `.env`를 읽지 않음.
- `AlarmSettings` 한 행 제약, 0002 데이터 이전(환경변수 있음/없음), VAPID 자동 생성(한 번만, 이후 같은 값), 토큰 변경 시 텔레그램 확인 초기화, 푸시 키 재생성 시 구독 삭제, 관리 화면(슈퍼유저만, 토큰 미노출·비우면 유지), `/alarms/` 안내 문구, 발송·연결 확인이 DB 값을 씀, 로그에 토큰 없음.
- `health` 명령: 상태 변화 때만 발송, 첫 정상 기록만, 발송 실패 시 상태 미저장, df 실패.
- 기존 테스트 전체 `-W error`. 화면 확인 1400·390(관리 화면 알림 설정, `/alarms/`).
