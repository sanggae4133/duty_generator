# duty_generator

IT 당번표 웹. 회차 단위로 부서 출근표를 취합하고, 장중관제 당번을 생성·배포하고, 근무 변경을 기록한다.
설계: `docs/superpowers/specs/2026-11-09-duty-generator-design.md`

## 폴더 구조

개발 PC 와 서버가 같은 모양이다(서버는 `/opt/duty_generator`).

| 위치 | 무엇 | git |
|---|---|---|
| `config/`, `duty/`, `manage.py` | 코드. `config/` 는 Django 프로젝트(설정을 읽는 `settings.py`, URL, WSGI), `duty/` 는 앱 본체(모델·화면·서비스·관리 명령·템플릿·정적 파일). 설치하지 않고 이 폴더에서 바로 돈다. | 올림 |
| `tests/` | pytest 테스트. | 올림 |
| `requirements.in` / `requirements.lock` / `requirements-dev.txt` | 직접 쓰는 라이브러리(범위) / 운영 설치용 고정 버전 / 개발용 테스트 도구. | 올림 |
| `pyproject.toml` | pytest 설정만. | 올림 |
| `deploy/` | 서버용 systemd 유닛 두 개: `duty-web.service`(웹), `duty-worker.service`(작업자). 아래 "서비스 두 개". | 올림 |
| `docs/` | 설계·구현 계획 문서. | 올림 |
| `.env.example` → `.env` | 설정값. 견본을 `.env` 로 복사해 채운다. 개발 PC 와 서버의 차이는 이 파일의 값뿐이다. | `.env` 는 안 올림 |
| `data/` | 실행 중 생기는 파일 전부: `db.sqlite3`(DB), `backups/`(백업), `logs/`(로그), 잠금 파일. `.env` 의 `DUTY_DATA_DIR` 로 옮길 수 있다. | 안 올림 |
| `.venv/`, `staticfiles/` | 파이썬 가상환경, 모은 정적 파일(`collectstatic`). | 안 올림 |

## 개발 PC 와 운영 서버의 차이

차이는 `.env` 값으로만 정한다. 항목마다 설명과 예시 값은 `.env.example` 에 있다.

| 설정 | 개발 PC | 운영 서버 |
|---|---|---|
| `DUTY_DEBUG` | `1`(오류 상세 화면, http 쿠키 허용) | `0` |
| `DUTY_SECRET_KEY` | 비움(개발용 키) | 무작위 값(필수) |
| `DUTY_ALLOWED_HOSTS` | 비움(`127.0.0.1,localhost`) | `duty.example.ts.net,127.0.0.1,localhost` |
| `DUTY_CSRF_ORIGINS` | 비움 | `https://duty.example.ts.net` |
| `DUTY_SITE_URL` | 비움 또는 `http://127.0.0.1:8000` | `https://duty.example.ts.net` |
| `DUTY_ADMIN_PATH` | 비움(`admin`) | 짐작하기 어려운 값 |
| `DUTY_DATA_DIR` | 비움(`data/`) | 비움(`/opt/duty_generator/data`) |
| `DUTY_BACKUP_HOUR` / `DUTY_BACKUP_KEEP_DAYS` / `DUTY_LOG_KEEP_DAYS` | 비움(3시 / 30일 / 14일) | 비움(같음) |

텔레그램 봇 토큰·웹 푸시 키·장애 알림 chat_id 는 `.env` 가 아니라 관리 화면 → 알림 설정(DB)에 둔다(아래 "알림").

실행하는 것도 같다. 개발 PC 는 손으로 켜고, 서버는 systemd 가 켠다.

| 무엇 | 개발 PC | 운영 서버 |
|---|---|---|
| 웹 | `.venv/bin/python manage.py runserver` | `duty-web.service`(gunicorn) |
| 작업자(알림·백업·상태 점검) | 필요할 때 `.venv/bin/python manage.py run_worker` | `duty-worker.service` |

## 개발

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock -r requirements-dev.txt
cp .env.example .env   # 견본 값이 개발 PC 용이라 고칠 것 없다
.venv/bin/pytest -W error   # 테스트는 .env 를 읽지 않는다
.venv/bin/python manage.py migrate   # data/db.sqlite3 를 만든다
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

- `.env` 없이 `DUTY_DEBUG=1 .venv/bin/python manage.py runserver` 처럼 앞에 환경변수를 붙여도 된다(환경변수가 `.env` 보다 이긴다).
- 개발 PC 에서 `run_worker` 를 켜면 실제로 알림을 보낸다(관리 화면에 봇 토큰을 넣었을 때). 상태 점검은 웹을 `127.0.0.1:8090` 에서 찾으므로, runserver(8000)만 켰다면 "웹 응답 없음"이 로그에 남는다(장애 알림 chat_id 를 비워 두면 보내지는 않는다).

## 설치 (사내 서버)

Ubuntu 24.04 (Python 3.12) 기준. 코드는 root 소유(`duty` 는 읽기만), 쓰는 곳은 `data/` 하나(`duty` 소유)다.

```bash
sudo apt install -y python3-venv git curl   # python3 --version 이 3.12 이상이어야 한다
sudo useradd -r -s /usr/sbin/nologin duty
sudo git clone https://github.com/sanggae4133/duty_generator.git /opt/duty_generator
cd /opt/duty_generator
sudo install -d -o duty -g duty -m 750 data data/backups data/logs
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.lock
sudo install -o root -g duty -m 640 .env.example .env
sudoedit .env   # 견본은 개발 PC 값이다. 여섯 줄을 "서버:" 값으로: DUTY_DEBUG=0, DUTY_SECRET_KEY, DUTY_ALLOWED_HOSTS, DUTY_CSRF_ORIGINS, DUTY_SITE_URL, DUTY_ADMIN_PATH
# manage.py 를 duty 사용자로 부르는 함수(이 셸에서만 유효). 아래 절차들이 이걸 쓴다.
dm() { sudo -u duty /opt/duty_generator/.venv/bin/python /opt/duty_generator/manage.py "$@"; }
sudo .venv/bin/python manage.py collectstatic --noinput   # root 로: 코드 폴더는 duty 가 쓸 수 없다
dm migrate
dm createsuperuser  # 첫 어드민: 아이디·이름·비밀번호를 묻는다(아래 "처음 한 번: 계정 만들기")
dm check --deploy   # 경고 확인(HTTPS 는 Funnel 이 맡으므로 HSTS·SSL_REDIRECT 경고는 무시)
sudo cp deploy/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now duty-web duty-worker
```

- `DUTY_SECRET_KEY` 는 `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` 로 만든다.
- `.env` 를 고친 뒤에는 `sudo systemctl restart duty-web duty-worker`.
- `dm` 은 `/opt/duty_generator` 밖에서도 돌므로 파일 인자는 절대 경로로 준다.
- 서버 시계: 알림이 분 단위로 돈다. `timedatectl` 에서 `System clock synchronized: yes`. 시간대와 상관없이 앱은 Asia/Seoul 로 계산한다.
- 작업자는 켜질 때 26시간 안에 만든 백업이 없으면(새 설치·오래 꺼져 있었음) 시각과 상관없이 바로 하나 만든다. 그래서 상태 점검이 "백업 없음"으로 시작하지 않는다.
- `dm check --deploy` 가 `DEBUG`·`SECRET_KEY` 경고를 내면 `.env` 의 여섯 줄을 덜 바꾼 것이다.
- 알림은 관리 화면 → 알림 설정에 봇 토큰을 넣어야 나간다(아래 "알림 켜기").

## 서비스 두 개 (`deploy/`)

서버에서 도는 건 이 둘뿐이다. 둘 다 `/etc/systemd/system/` 에 복사해서 쓰고, 각 줄의 뜻은 파일 안 주석에 있다.

| 유닛 | 하는 일 | 로그 |
|---|---|---|
| `duty-web.service` | 웹. `gunicorn config.wsgi:application --bind 127.0.0.1:8090 --workers 1 --threads 4` | `data/logs/web.log`, `journalctl -u duty-web` |
| `duty-worker.service` | 작업자 `manage.py run_worker`. 1분마다: 알림 발송(매분), DB 백업(하루 한 번 `DUTY_BACKUP_HOUR` 시 이후), 상태 점검(5분마다) | `data/logs/worker.log`, `journalctl -u duty-worker` |

`duty-web.service` 의 줄:
- `User=duty` — `duty` 사용자로 돈다. 코드는 읽기만 하고 `data/` 에만 쓴다.
- `WorkingDirectory=/opt/duty_generator` — 여기서 돌아야 `config`·`duty` 를 찾는다(설치 없이 저장소에서 바로 돈다).
- `ExecStart=... --bind 127.0.0.1:8090` — 서버 안에서만 연다. 바깥 공개는 Tailscale Funnel 이 맡는다. 이 주소를 바꾸면 `duty/services/health.py` 의 `WEB_URL` 도 바꾼다.
- `--workers 1 --threads 4` — 프로세스 하나에 스레드 4개. `web.log` 를 한 프로세스만 써야 자정에 파일을 넘길 때 꼬이지 않는다. 사용자가 수십 명이라 충분하다.
- 접근 로그(`--access-logfile`)는 켜지 않는다 — 캘린더 구독 주소에 비밀 토큰이 들어 있다.
- `Restart=always`, `RestartSec=5` — 죽으면 5초 뒤 다시 띄운다.
- `WantedBy=multi-user.target` — `enable` 해 두면 부팅 때 켜진다.

`duty-worker.service` 의 줄:
- `User`, `WorkingDirectory`, `Restart`, `WantedBy` — 웹과 같다.
- `ExecStart=... manage.py run_worker` — 작업자. `data/.alarms.lock` 잠금으로 한 번에 하나만 돈다(같은 알림이 두 번 가지 않게). 한 작업이 실패해도 로그(`worker job failed: <작업>`)만 남기고 다른 작업은 계속한다.

유닛을 고쳤거나 새 버전에서 바뀌었으면 `sudo cp deploy/*.service /etc/systemd/system/ && sudo systemctl daemon-reload` 후 재시작한다.

## 외부 공개 (Tailscale Funnel)

```bash
sudo tailscale funnel --bg --set-path / http://127.0.0.1:8090
sudo tailscale funnel status
```

## 처음 한 번: 계정 만들기

`/<DUTY_ADMIN_PATH>/` 의 "사용자" 화면이 멤버이자 로그인 계정이다(아이디 = 멤버 코드).
- 첫 어드민은 설치 때 `dm createsuperuser` 로 만든다. 아이디·비밀번호 말고 **이름**도 묻는다. 이 계정은 부서가 없어 근무표 대상이 아닌 어드민 전용 계정이고, "스태프 권한"도 켜져 있다. 기본 알림 규칙은 생기지 않는다(필요하면 알림 화면에서 추가).
- 새 사람: [사용자 추가]에서 아이디·이름·부서·파트·구분을 넣는다(비밀번호 없이 만들어지고 아직 로그인할 수 없다).
- 계정 발급: 목록에서 선택 → "계정 발급 / 비밀번호 초기화" 액션 → 화면에 한 번만 보이는 임시 비밀번호를 전달한다. 첫 발급 때 기본 알림 규칙이 생기고, 첫 로그인에서 비밀번호를 바꾸게 한다.
- 어드민 전용 계정(근무표에 안 들어감)은 부서를 비워 둔다. 어드민은 "스태프 권한"과 "슈퍼유저 권한"을 둘 다 켠다. Django 관리 화면(사용자·부서·입력 담당자, 계정 발급, 잠금 해제)은 슈퍼유저만 쓸 수 있다. 어드민은 1~2명을 가정한다.
- 부서 입력 담당자는 부서 화면의 "입력 담당자"에서 지정한다.
- 비밀번호는 항상 [계정 발급] 액션으로 준다. 사용자 편집 화면의 비밀번호 칸에서 Django 기본 "비밀번호 설정/변경" 화면으로 정하면 발급을 거치지 않는다. 그러면 첫 로그인 비밀번호 변경이 걸리지 않고, 기본 알림 규칙도 생기지 않는다. 그 뒤 [계정 발급]을 해도 최초 발급으로 치지 않는다.

## 업그레이드·롤백

`dm` 은 "설치" 절의 함수다. 지금 버전을 먼저 적어 둔다(롤백할 때 쓴다).

```bash
cd /opt/duty_generator
git log -1 --format=%h                       # 지금 버전(적어 둔다)
sudo systemctl stop duty-web duty-worker
dm backup                                    # data/backups/db-YYYYMMDD-HHMMSS.sqlite3 (경로가 출력된다, 적어 둔다)
sudo git pull --ff-only                      # 특정 버전이면: sudo git fetch && sudo git checkout <버전>
sudo .venv/bin/pip install -r requirements.lock
sudo .venv/bin/python manage.py collectstatic --noinput
dm migrate                                   # 무언가 적용됐으면(DB 구조 변경) 롤백 때 DB 복원이 필요하다
sudo cp deploy/*.service /etc/systemd/system/ && sudo systemctl daemon-reload   # 유닛이 바뀌었을 때만 필요(해도 무해)
sudo systemctl start duty-web duty-worker
systemctl is-active duty-web duty-worker     # 둘 다 active. 아니면 journalctl -u duty-web -n 50
```

- **롤백**: 위와 같은 순서에서 `git pull` 대신 `sudo git checkout <적어 둔 버전>`. 업그레이드 때 `migrate` 가 무언가 적용했으면 `dm migrate` 대신 `dm restore <업그레이드 전에 만든 백업>`(아래 "백업·복원")을 한다 — 복원은 백업의 마이그레이션이 지금 코드와 같아야 받아 주므로, 코드를 먼저 되돌린 뒤에 한다.
- git 이 "dubious ownership" 을 내면 `sudo chown -R root:root /opt/duty_generator/.git` 후 다시 한다.
- 업그레이드 전 백업도 `db-*` 라 `DUTY_BACKUP_KEEP_DAYS` 일 뒤 자동으로 지워진다. 오래 둘 것은 서버 밖으로 내려받는다.

## 백업·복원

- 자동: 작업자가 매일 `DUTY_BACKUP_HOUR` 시(기본 3시) 이후 처음 돌 때 `data/backups/db-YYYYMMDD.sqlite3` 를 만들고, `DUTY_BACKUP_KEEP_DAYS` 일(기본 30)보다 오래된 `db-*` 를 지운다. 작업자가 꺼져 있었으면 다시 켜질 때 그날 것을 만든다(26시간 안 백업이 없으면 그 시각 전이라도 바로).
- 수동: `dm backup` → `data/backups/db-YYYYMMDD-HHMMSS.sqlite3`. 서비스가 도는 중에도 된다. **DB 파일을 `cp` 로 복사하지 말 것**(WAL 모드라 최근 변경이 빠지거나 깨진 사본이 될 수 있다). 백업은 SQLite 백업 기능으로 떠서 일관된 파일 하나가 된다.
- 백업에는 실명과 텔레그램 봇 토큰·푸시 키가 들어 있다. 서버 밖에 보관하려면 내려받되 공유 폴더에 두지 않는다.
- 복원:
  ```bash
  sudo systemctl stop duty-web duty-worker
  dm restore /opt/duty_generator/data/backups/<백업 파일>
  dm migrate
  sudo systemctl start duty-web duty-worker
  ```
  - 작업자가 돌고 있으면(`data/.alarms.lock` 이 잡혀 있으면) 아무것도 바꾸지 않고 멈춘다. 복원하는 동안은 이 잠금을 잡고 있어 작업자가 뜨지 못한다. 웹은 검사하지 않으니 직접 멈춘다.
  - 복원 전에 검사한다. `quick_check` 가 `ok` 가 아니거나 백업의 마이그레이션이 지금 코드와 다르면 아무것도 바꾸지 않고 멈춘다(다르면 그 백업을 만든 버전의 코드로 먼저 바꾼다).
  - 지금 DB 는 `data/backups/before-restore-YYYYMMDD-HHMMSS.sqlite3` 로 남긴다(자동으로 지우지 않는다). 남은 `-wal`·`-shm` 은 지운다.

## 로그

| 파일 | 내용 |
|---|---|
| `data/logs/web.log` | 웹 앱의 경고·오류(`django.request` 404·500 등, 로그인 잠금) |
| `data/logs/worker.log` | 작업자: 매분 `alarms tick:` 한 줄, 발송 실패, `backup: db-…`, `health: …`, `worker job failed: …` |

- 자정마다 새 파일로 넘기고(`web.log.2026-11-10` …) `DUTY_LOG_KEEP_DAYS` 일(기본 14)보다 오래된 파일은 지운다.
- 같은 내용과 gunicorn 자체 메시지는 journald 에도 간다: `journalctl -u duty-web -n 100`, `journalctl -u duty-worker -f`.
- 읽기: `sudo tail -f /opt/duty_generator/data/logs/worker.log`. 경고·오류만: `sudo grep -E ' (WARNING|ERROR) ' /opt/duty_generator/data/logs/*.log`.
- 각 줄은 `<날짜 시각> <레벨> <로거> <메시지>` 형식이다.
- 접근 로그(요청마다 한 줄)는 남기지 않는다. 캘린더 구독 주소에 비밀 토큰이 들어 있어서다.

## 장애 알림

작업자가 5분마다 아래를 보고, **상태가 바뀔 때만** 관리자 텔레그램으로 알린다(문제가 생겼을 때 한 번, 정상으로 돌아왔을 때 한 번).

- 웹이 응답하지 않음(`http://127.0.0.1:8090/login/`) / 26시간 안에 만든 `db-*` 백업이 없음 / `data/` 디스크 사용 90% 이상
- 보내는 봇은 알림용 텔레그램 봇, 받는 사람은 관리 화면 → 알림 설정의 "장애 알림 받을 chat_id"(관리자 개인 chat_id, 아래 "텔레그램 봇" 4단계로 확인). 비우면 `worker.log` 에만 남는다.
- 작업자가 켜진 직후 첫 바퀴는 점검을 건너뛴다(재부팅·업그레이드 때 아직 뜨는 중인 웹을 "응답 없음"으로 알리지 않게). 첫 점검은 다음 5분 단위 시각이다.
- 첫 점검이 정상이면 `health: 정상(점검 시작)` 한 줄만 남기고 알리지 않는다. 마지막 상태는 `data/.health.state` 에 있다.
- 발송에 실패하면 상태를 저장하지 않아 다음 점검(5분 뒤)에 다시 보낸다.
- 웹 점검이 `127.0.0.1` 로 부르므로 `DUTY_ALLOWED_HOSTS` 에 `127.0.0.1` 이 있어야 한다.
- 작업자 자체가 멈추면 이 알림도 멈춘다. `systemctl is-active duty-worker` 와 `worker.log` 의 매분 `alarms tick:` 줄로 확인한다.
- 시험: `sudo systemctl stop duty-web` → 5분 안에 알림 → `sudo systemctl start duty-web` → 복구 알림.

## 예전 배치에서 옮기기 (시험 서버·개발 PC, 1회)

예전 버전은 설정을 `/etc/duty_generator/env`, DB 를 `/var/lib/duty_generator/`, 백업·로그를 `/var/backups/duty_generator/`·`/var/log/duty_generator/` 에 두고, systemd 유닛 7개와 `pip install -e .` 를 썼다. 이 버전은 `.env` + `data/` + 유닛 2개다. 또 멤버·계정 통합 버전부터 마이그레이션을 새 `0001_v2` 하나로 새로 만들어서, 그 전(duty 마이그레이션 0001~0009) DB 는 `migrate` 로 올라가지 않고 `convert_v1` 로 한 번 옮긴다.

### 서버

```bash
cd /opt/duty_generator
git log -1 --format=%h          # 지금(예전) 버전 — 롤백용으로 적어 둔다
dm() { sudo -u duty /opt/duty_generator/.venv/bin/python /opt/duty_generator/manage.py "$@"; }   # 이 셸에서 쓸 manage.py 단축
# 예전 DB 위치는 예전 기본값 /var/lib/duty_generator/db.sqlite3 기준이다. 예전 env 에 DUTY_DB_PATH 를 따로 정했다면 아래 경로를 그 값으로 바꾼다:
#   sudo grep DUTY_DB_PATH /etc/duty_generator/env
# 1. 예전 서비스를 끄고 유닛을 지운다
sudo systemctl disable --now duty-health.timer duty-generator-backup.timer duty-alarms duty-generator
sudo rm -f /etc/systemd/system/duty-generator.service /etc/systemd/system/duty-alarms.service \
  /etc/systemd/system/duty-generator-backup.service /etc/systemd/system/duty-generator-backup.timer \
  /etc/systemd/system/duty-health.service /etc/systemd/system/duty-health.timer /etc/logrotate.d/duty_generator
sudo systemctl daemon-reload
# 2. 설정 파일을 복사하고 data/ 를 만든 뒤, 예전 DB 를 일관된 파일 하나로 떠 둔다
sudo install -o root -g duty -m 640 /etc/duty_generator/env .env
sudo install -d -o duty -g duty -m 750 data data/backups data/logs
sudo -u duty sqlite3 /var/lib/duty_generator/db.sqlite3 ".backup /opt/duty_generator/data/backups/old.sqlite3"
# 3. 새 코드(설치 없이 돈다: 예전 editable 설치는 지운다)
sudo git fetch && sudo git checkout <새 버전>
sudo .venv/bin/pip uninstall -y duty-generator; sudo rm -rf duty_generator.egg-info
sudo .venv/bin/pip install -r requirements.lock
sudo .venv/bin/python manage.py collectstatic --noinput
dm migrate                      # 새 빈 data/db.sqlite3. .env 에 남은 예전 알림 값은 이때 알림 설정(DB)으로 옮겨진다
# 4-a. 예전 DB 가 멤버·계정 통합 전(0001~0009)이면
dm convert_v1 /opt/duty_generator/data/backups/old.sqlite3
# 4-b. 이미 0001_v2 DB 면 (convert_v1 대신)
#   sudo -u duty rm data/db.sqlite3 data/db.sqlite3-wal data/db.sqlite3-shm 2>/dev/null
#   sudo -u duty cp data/backups/old.sqlite3 data/db.sqlite3 && dm migrate
# 5. 새 서비스
sudo cp deploy/*.service /etc/systemd/system/ && sudo systemctl daemon-reload
sudo systemctl enable --now duty-web duty-worker
```

- `.env` 에서 이제 안 쓰는 이름(`DUTY_DB_PATH`, `DUTY_ALARMS_LOCK`, `DUTY_TELEGRAM_LOCK`, `DUTY_TELEGRAM_BOT_*`, `DUTY_VAPID_*`, `DUTY_OPS_CHAT_ID`)을 `sudoedit .env` 로 지운다(남아 있어도 무시되지만 토큰이 파일에 남는다). 알림 값이 옮겨졌는지는 관리 화면 → 알림 설정의 "지금 토큰" 끝 4자리와 "푸시 키: 있음"으로 확인한다(키가 같으니 기존 기기 구독도 그대로다).
- 잘 도는 걸 확인한 뒤 예전 폴더를 지운다: `sudo rm -r /etc/duty_generator /var/lib/duty_generator /var/backups/duty_generator /var/log/duty_generator`.
- 롤백(예전 폴더를 지우기 전까지): 예전 DB 는 `/var/lib/duty_generator` 에 그대로 있다.
  ```bash
  sudo systemctl disable --now duty-web duty-worker
  sudo rm -f /etc/systemd/system/duty-web.service /etc/systemd/system/duty-worker.service
  sudo git checkout <적어 둔 예전 버전> && sudo .venv/bin/pip install -r requirements.lock && sudo .venv/bin/pip install --no-deps -e .
  sudo sh -c 'set -a; . /etc/duty_generator/env; .venv/bin/python manage.py collectstatic --noinput'
  # 그 버전 README 의 "설치" 절대로 유닛을 복사하고 켠다
  ```

### 개발 PC

저장소 루트에서, runserver 를 멈추고 실행한다.

```bash
.venv/bin/pip uninstall -y duty-generator; rm -rf duty_generator.egg-info   # 예전 editable 설치
.venv/bin/pip install -r requirements.lock -r requirements-dev.txt
mkdir -p data/backups
sqlite3 db.sqlite3 ".backup data/backups/old.sqlite3"      # 예전 위치의 DB 를 일관된 파일 하나로
# 이미 0001_v2 DB 면:
cp data/backups/old.sqlite3 data/db.sqlite3 && DUTY_DEBUG=1 .venv/bin/python manage.py migrate
# 통합 전(0001~0009) DB 면 (위 대신):
#   DUTY_DEBUG=1 .venv/bin/python manage.py migrate && DUTY_DEBUG=1 .venv/bin/python manage.py convert_v1 data/backups/old.sqlite3
```

잘 되면 예전 `db.sqlite3*` 는 지워도 된다.

### 동작(`convert_v1`)

- `convert_v1` 은 `.backup` 으로 만든 단일 파일만 받는다(옆에 내용 있는 `-wal` 이 있으면 거부한다).
- 예전 백업은 읽기 전용으로 열고, 쓰기 전에 아래를 전부 검사한다.
  - 원본: `quick_check`, `foreign_key_check`, duty 마이그레이션이 0001~0009인지.
  - 지금 DB: `migrate` 만 한 빈 DB인지(이 버전의 duty 마이그레이션 전부 적용, 업무 표가 비어 있음. `migrate` 가 예전 환경변수로 채운 알림 설정 행은 있어도 된다).
  - 아이디·이름 규칙과 중복.
  - 그룹·직접 권한 행이 없는지.
- 하나라도 걸리면 아무것도 쓰지 않고 이유를 출력한다. 옮기기는 한 트랜잭션이라 중간에 실패해도 지금 DB 는 빈 채로 남는다.
- 멤버마다 사용자 1명을 만든다(id = 예전 멤버 id, 아이디 = 멤버 코드). 연결된 계정의 비밀번호·권한·로그인 시각을 옮긴다.
- 재직 = 멤버 재직 AND 계정 활성.
- 멤버와 연결되지 않은 계정(어드민 전용 등)은 부서 없는 사용자가 되고, 이름은 아이디와 같다.
- 나머지 표는 id 그대로 옮긴다.
- 세션·로그인 실패 기록·관리 화면 기록은 버린다(다시 로그인해야 한다). 텔레그램 연결 대기 코드는 비운다.
- 출력에는 건수만 나온다(이름·비밀값 없음). 표별 건수와 함께 재직 AND 로 상태가 바뀐 연결 계정 수도 출력한다.
  - "재직이었지만 계정 비활성이라 재직 끔 N": 이 사람들은 근무표 후보에서 빠진다.
  - "퇴사였지만 계정 활성이라 로그인 차단 N (그중 스태프 M)": 예전엔 퇴사 스태프도 로그인됐지만 이제는 막힌다.
  - 바로잡을 사람은 관리 화면에서 "재직"을 고친다.
- 변환 뒤 활성 슈퍼유저가 없으면 경고를 출력한다. 그때는 어드민이 관리 화면에 들어갈 수 없으니, 둘 중 하나로 복구한다.
  - `dm createsuperuser` 로 새로 만든다.
  - `dm shell` 에서 기존 계정의 `is_active` 를 켠 뒤 `dm changepassword <아이디>` 로 비밀번호를 정한다.

## 의존성 고정

설치하지 않는 프로젝트다(`pip install -e .` 없음). 직접 쓰는 라이브러리와 허용 범위는 `requirements.in`, 운영 설치는 `requirements.lock` 의 고정 버전만 쓴다. 테스트 도구는 `requirements-dev.txt`(고정). 라이브러리를 올릴 때만 개발 PC 에서 lock 을 다시 만든다.

```bash
python3 -m venv /tmp/lockvenv && /tmp/lockvenv/bin/pip install -U -r requirements.in
{ echo '# 운영 설치용 고정 버전. 갱신: README "의존성 고정" 참고'; /tmp/lockvenv/bin/pip freeze; } > requirements.lock
rm -rf /tmp/lockvenv
.venv/bin/pip install -r requirements.lock -r requirements-dev.txt && .venv/bin/pytest -W error   # 통과하면 커밋
```

## 알림 (텔레그램·웹 푸시)

사용자가 `/alarms/` 에서 규칙을 만들면 작업자(`run_worker`, 1분마다)가 보낸다. 웹과 별도 프로세스다.

### 설정: 관리 화면 → 알림 설정

봇 토큰·푸시 키는 `.env` 가 아니라 DB 에 한 행으로 두고, 슈퍼유저가 `/<DUTY_ADMIN_PATH>/` → "알림 설정"에서 고친다. 저장하면 웹·작업자가 바로 새 값을 쓴다(재시작 불필요).

| 칸 | 내용 |
|---|---|
| 텔레그램 봇 토큰 | 웹앱 전용 봇 토큰. 비우면 텔레그램 채널이 꺼진다. 화면에는 끝 4자리만 보인다. **칸을 비워 두고 저장하면 지금 값 그대로**, 새 값을 넣으면 교체, "토큰 지우기"를 체크하면 비운다. |
| 텔레그램 봇 사용자명 | 그 봇의 사용자명(`@` 는 떼고 저장). 비우면 [텔레그램 연결] 자동 연결을 못 쓰고 chat_id 직접 입력만 된다. |
| 장애 알림 받을 chat_id | 관리자 개인 chat_id(숫자). 아래 "장애 알림" 참고. |
| 웹 푸시 연락처 | `mailto:admin@example.com` 형식. 푸시 서비스가 문제 시 연락하는 주소. |
| 푸시 키 | 처음 필요할 때(누군가 `/alarms/` 를 열 때) 자동으로 만든다. 손으로 만들 필요 없다. |
| 푸시 키 다시 만들기 | 키가 유출됐을 때만. 체크하고 저장하면 모든 기기의 푸시 구독이 지워지고, 사용자마다 [이 기기에서 푸시 받기]를 다시 눌러야 한다. |

- **봇을 바꾸면**(토큰이나 사용자명 변경) 모든 사용자의 텔레그램 연결 확인이 지워진다. 새 봇에서 [시작]을 다시 눌러야 하기 때문이다. 저장 뒤 화면에 몇 명인지 나온다. 각자 `/alarms/` 에서 [텔레그램 연결] → [시작] → [연결 확인]을 다시 하면 된다.
- 토큰·개인키는 로그와 화면에 나오지 않는다. DB 백업에는 들어 있으니 백업 파일도 비밀로 다룬다.

`.env` 에 남는 알림 관련 값은 하나다:

| 변수 | 내용 |
|---|---|
| `DUTY_SITE_URL` | `https://duty.example.ts.net`(경로 없이 호스트만). 텔레그램 알림 링크·캘린더 구독 주소용(비면 링크 생략, 캘린더 구독 주소 발급 불가). |

### 텔레그램 봇

봇은 이 웹앱만 써야 한다. 다른 프로그램(예: 예전 `duty_notifier`)이 같은 봇으로 polling 중이면 서로의 업데이트를 가로챈다(409 충돌). 예전 봇을 다시 쓰려면 그 프로그램을 먼저 끈다.

1. 텔레그램 `@BotFather` 에서 `/newbot` → 토큰과 사용자명을 관리 화면 → 알림 설정에 넣는다.
2. 텔레그램 API 를 손으로 부르는 함수를 만든다(이 셸에서만 유효, "설치"의 `dm` 이 필요). 토큰은 DB 에서 읽어 curl 에 표준입력으로 넘기므로 셸 기록·프로세스 목록에 남지 않는다.
   ```bash
   tg() { dm shell -v 0 -c "from duty.services.alarm_settings import current; print('url = \"https://api.telegram.org/bot' + current().telegram_bot_token + '/$1\"')" | curl --fail-with-body --silent --show-error -K -; echo; }
   ```
3. webhook 이 걸려 있지 않은지 확인한다. `tg getWebhookInfo` 의 `"ok":true` 이고 `result.url` 이 `""` 이어야 한다.
   `url` 이 비어 있지 않으면 한 번만 `tg 'deleteWebhook?drop_pending_updates=false'` (응답 `"ok":true,"result":true` 확인) 후 `tg getWebhookInfo` 를 다시 실행해 `url` 이 `""` 인지 확인한다.
4. (직접 입력용) chat_id 확인: 그 사람이 새 봇에게 `/start` 를 보낸 뒤 `tg getUpdates` 의 `message.chat.id`. `offset` 은 붙이지 않는다(붙이면 대기 중인 연결 요청이 확인 처리돼 사라진다).
   보통은 사용자가 `/alarms/` 의 [텔레그램 연결] → 봇에서 [시작] → [연결 확인]으로 직접 연결하므로 이 단계는 필요 없다.

[연결 확인]이 "텔레그램 봇 설정 오류입니다."를 띄우면 `getUpdates` 가 4xx 로 거절된 것이다. 대개 409(그 봇에 webhook 이 걸렸거나 다른 프로그램이 같은 봇으로 polling 중) 또는 401(토큰 오류)이다. 3단계로 webhook 을 확인하고, 다른 프로그램이 같은 봇을 쓰고 있지 않은지 본다.

### 웹 푸시 지원 범위

- 받는 쪽 푸시 서비스는 Chrome·Android(FCM), Firefox(Mozilla), Safari·iOS(Apple)만 허용한다. Edge(WNS)는 지원하지 않는다(구독 시 "지원하지 않는 푸시 서비스입니다.").
- 한 사용자당 기기 20대까지.
- 아이폰·아이패드: iOS 16.4 이상에서 Safari 로 사이트를 연 뒤 공유 → "홈 화면에 추가" 한 앱에서만 푸시를 받을 수 있다. 그 홈 화면 앱 안에서 `/alarms/` → [이 기기에서 푸시 받기]를 누른다. 사파리 탭에서는 안 된다. 안내 화면: `/help/push/`.

### 로그 읽기 (`data/logs/worker.log`)

- 각 줄은 `<날짜 시각> <레벨> <로거> <메시지>` 형식이다(예: `2026-11-11 09:00:00 INFO duty.services.alarm_runner alarms tick: ...`, 실패는 `WARNING`). 실패만 보려면 `sudo grep -E ' (WARNING|ERROR) ' /opt/duty_generator/data/logs/worker.log`.
- 매분 `alarms tick: due=<보낼 건수> sent=<성공> failed=<실패>`.
- 실패마다 `alarm send failed rule=<규칙 id> channel=<telegram|push> delivery=<기록 id> status=<종류>:<HTTP 코드> attempt=<시도 횟수>`. `status` 는 결과 상태가 아니라 실패 종류와 응답 코드를 붙인 것이다(코드가 없으면 `None`).
  - `Temporary:None` — 네트워크 오류·응답 이상·깨진 VAPID 키. 1, 2, 4 … 최대 30분 간격으로 재시도.
  - `Temporary:<5xx>` — 상대 서버 오류. 위와 같이 재시도(텔레그램 503 도 여기).
  - 푸시만 `Temporary:401`/`403` — 푸시 키·연락처(subject) 설정 오류일 가능성. 재시도하므로 관리 화면 → 알림 설정에서 연락처를 고치면 다시 나간다.
  - `RetryLater:429`(텔레그램·푸시), `RetryLater:503`(푸시만) — 상대가 알려 준 시간(`retry_after`/`Retry-After`) 뒤 재시도. 시간을 안 알려 주면 위의 일반 간격.
  - `Permanent:<4xx>` — 그 알림은 만료 시각까지 다시 보내지 않는다. 텔레그램 `Permanent:401` 은 봇 토큰 오류, `Permanent:403` 은 사용자가 봇을 차단, `Permanent:400` 은 chat_id 오류. 푸시는 401·403·404·410·429 를 뺀 4xx(구독 데이터 이상 등).
  - 그 밖의 이름(예: `OperationalError:None`)은 예기치 않은 예외 — 일시 실패로 재시도된다. 계속 나오면 확인한다.
- 만료된 푸시 구독(404/410)은 로그 없이 지워진다. 기기에서 다시 [이 기기에서 푸시 받기]를 누르면 된다.

### 알림 켜기

작업자는 늘 돈다(백업·상태 점검). 알림은 보낼 곳이 생기면 그때부터 나간다: 텔레그램은 관리 화면에 봇 토큰이 있고 사용자가 연결했을 때, 푸시는 사용자가 기기를 등록했을 때.

1. 예전 `duty_notifier` 가 이 서버에서 아직 돌고 있으면 먼저 끈다(같은 알림이 두 번 가지 않게): `sudo systemctl disable --now duty-notifier`
2. 관리 화면 → 알림 설정에 봇 토큰·사용자명을 넣는다(위 "텔레그램 봇").
3. `dm run_worker --dry-run` — 발송·기록 없이 `telegram=<n> push=<n>`(지금 보낼 건수)만 출력한다. 작업자가 도는 중에도 된다.
4. `/alarms/` 에서 텔레그램 연결 또는 chat_id [저장 및 테스트], 푸시 [이 기기에서 푸시 받기] → [테스트 푸시]로 실제 수신을 확인한다. PC Chrome 과 아이폰 홈 화면 앱에서 알림을 누르면 해당 화면이 열리는지도 본다.
5. `sudo tail -f /opt/duty_generator/data/logs/worker.log` 에서 매분 `alarms tick:` 줄이 찍히는지 확인한다.
6. 텔레그램 알림을 모두 멈추려면 관리 화면 → 알림 설정에서 "토큰 지우기". (푸시만 따로 끄는 스위치는 없다. 사용자가 기기를 해제하거나 규칙을 끈다.)

## 캘린더 구독 (ICS)

- 각자 [알림·캘린더] 화면에서 [구독 주소 만들기]로 개인 구독 주소(`/calendar/<토큰>.ics`)를 받아 Google 캘린더·아이폰·Outlook에 구독한다. 사용 방법은 `/help/calendar/`.
- 피드에는 배포된 회차의 본인 출근조·관제 일정만, 오늘 기준 지난 90일부터 나온다. 퇴사(재직 끔)면 빈 캘린더가 된다. 부서 없는 계정은 구독 주소를 만들 수 없다.
- 갱신 시점은 캘린더 앱이 정한다(Google은 몇 시간 이상 걸리기도 함). 즉시 알아야 하는 변경은 텔레그램·푸시 알림이 맡는다.
- DB에는 토큰의 SHA-256 해시만 남고 주소는 발급 화면에 한 번만 보인다. 주소가 유출되면 본인이 [주소 재발급](기존 주소 즉시 무효) 또는 [구독 끄기]를 누른다. 피드 경로는 앱 로그(`django.request`·`django.server`)에서 `calendar feed <상태코드>`로 바뀌어 남는다.
- `DUTY_SITE_URL`이 비어 있으면 주소를 발급할 수 없다. 값은 경로 없이 `https://호스트[:포트]` 형식만 허용(DEBUG에서만 `http`), 경로·공백·제어문자·`?`·`#`·`user@`·잘못된 포트가 있으면 서버가 시작하지 않는다.
- 피드 오류 로그에 지역 변수를 담는 도구(HTML 오류 메일 `include_html`, 지역 변수 수집 APM)를 켜지 말 것 — 토큰이 포함될 수 있음.

## 운영 메모

- 로그인 5회 실패 시 그 계정은 15분 잠긴다. 슈퍼유저가 Admin의 Axes 메뉴에서 해제할 수 있다.
  잠금은 아이디 기준이라 멤버 코드를 아는 사람은 그 계정을 15분씩 계속 잠글 수 있다. 이때도 슈퍼유저가 Axes 관리 화면에서 풀면 된다.
- 퇴사자는 사용자의 "재직"을 끈다. 근무표 후보에서 빠지고 로그인도 막힌다(어드민도 예외 없음). 지난 근무·기록·통계에는 그대로 남는다.
