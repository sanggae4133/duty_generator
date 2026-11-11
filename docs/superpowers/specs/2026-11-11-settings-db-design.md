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

## 개정 1 (사용자 요청, 2026-11-11)

사용자: "프로젝트 구조가 지저분하다. 개발·운영 차이는 괜찮지만 낯선 deploy 파일 여러 개가 아니라 설정값으로 다뤄야 한다. 새로 온 사람이 하루 만에 이해할 수 있어야 한다." 위 1·3·4 절의 운영 부분을 아래로 바꾼다(`.env`, `AlarmSettings` DB 는 그대로).

### 실행 데이터 폴더 하나: `data/`
- 설정 하나 `DUTY_DATA_DIR`(기본 저장소 루트 `data/`, 상대 경로는 저장소 루트 기준, 없으면 만든다). 여기서 경로를 모두 얻는다: `db.sqlite3`, `backups/`, `logs/`, `.alarms.lock`, `.telegram-updates.lock`, `.health.state`.
- `DUTY_DB_PATH`, `DUTY_ALARMS_LOCK`, `DUTY_TELEGRAM_LOCK` 는 없앤다. `/etc/duty_generator`, `/var/lib|backups|log/duty_generator` 도 쓰지 않는다. 서버는 `/opt/duty_generator/data`(duty 소유 750)이고, 코드는 root 소유다. `.gitignore` 에 `data/`, `.env`.

### 설치 없이 실행
- `pip install -e .` 를 쓰지 않는다. `pyproject.toml` 에는 `[tool.pytest.ini_options]`(+`pythonpath=["."]`)만 남긴다.
- 의존성은 `requirements.in`(직접 쓰는 것, 범위) → `requirements.lock`(고정), 개발용은 `requirements-dev.txt`(pytest·pytest-django 고정). 서버는 `pip install -r requirements.lock`, 개발은 `-r requirements-dev.txt` 를 더 붙인다.

### 서비스 두 개 + 관리 명령
- `deploy/` 에는 주석을 자세히 단 `duty-web.service`(gunicorn `--workers 1 --threads 4`)와 `duty-worker.service`(`manage.py run_worker`)만 둔다. 나머지 유닛·타이머·logrotate·`upgrade.sh`·`restore.sh`·`duty-health.sh` 는 삭제한다. 유닛에는 `EnvironmentFile` 이 없다.
- `manage.py run_worker`: 1분마다 한 바퀴.
  - 알림 발송: 매분.
  - DB 백업: `DUTY_BACKUP_HOUR`(기본 3) 시 이후 그날 백업이 없으면 `data/backups/db-YYYYMMDD.sqlite3` 를 SQLite 백업 API 로 만든다(임시 파일 → 이름 바꾸기). 그 뒤 `DUTY_BACKUP_KEEP_DAYS`(기본 30)일보다 오래된 `db-*` 를 지운다.
  - 상태 점검: 5분마다. 웹 `/login/` 응답, 26시간 안에 만든 백업, 디스크 90%를 본다. 상태가 바뀔 때만 `ops_chat_id` 로 보내고, 첫 정상은 기록만 하고, 발송에 실패하면 상태를 저장하지 않는다.
  - 작업마다 예외를 따로 잡는다.
  - `data/.alarms.lock` 으로 한 프로세스만 돈다. `--once` 는 모든 작업을 한 번 돌리고, `--dry-run` 은 잠금 없이 알림 건수만 출력한다. `run_alarms` 와 `health` 명령은 없앤다(별도 알림 서비스가 없으므로).
- `manage.py backup`: `data/backups/db-YYYYMMDD-HHMMSS.sqlite3` 를 만든다.
- `manage.py restore <파일>` 은 아래를 검사하고 하나라도 걸리면 아무것도 바꾸지 않는다.
  - `quick_check` 가 `ok` 인지.
  - 백업의 `django_migrations` 가 지금 코드로 migrate 한 결과와 같은지.
  - 지금 DB 파일 자체가 아닌지.
  - 통과하면 지금 DB 를 `before-restore-*.sqlite3` 로 남기고, `-wal`·`-shm` 을 지운 뒤 교체한다. 서비스 중지와 `migrate` 는 README 절차로 한다.
- 로그:
  - 웹(`config/wsgi.py`)과 작업자가 시작할 때 루트 로거에 `data/logs/web.log`·`worker.log` 핸들러를 붙인다(`TimedRotatingFileHandler`, 자정, `DUTY_LOG_KEEP_DAYS` 기본 14). 형식과 캘린더 토큰 지우기는 그대로다.
  - stdout/stderr 는 journald 로 간다. gunicorn 은 프로세스 하나라 한 파일을 한 프로세스만 쓴다.
- 업그레이드·롤백·옛 배치에서 옮기기는 README 의 짧은 명령 목록으로 한다(정지 → `backup` → `git pull`/`checkout` → `pip install -r requirements.lock` → `collectstatic` → `migrate`, 롤백 땐 필요하면 `restore` → 시작).
- 위 2절의 `upgrade.sh` "빠진 설정/안 쓰는 설정" 안내와 3절의 `manage.py health`·`duty-health.service` 는 이 개정으로 대체된다.

### 문서
- README:
  - 폴더 구조 표(코드 / deploy·docs / `.env` / `data/`).
  - "개발 vs 운영 차이는 `.env` 값으로만" 표.
  - 유닛 두 개를 줄마다 설명.
  - 업그레이드·롤백, 백업·복원, 로그, 장애 알림, 옛 배치에서 옮기기(+`convert_v1`).
- `.env.example` 은 모든 설정을 개발·서버 예시 값과 함께 적는다. CLAUDE.md 는 알림 구조와 운영 줄을 고친다.
