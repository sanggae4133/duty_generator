# duty_generator

IT 당번표 웹. 회차 단위로 부서 출근표를 취합하고, 장중관제 당번을 생성·배포하고, 근무 변경을 기록한다.
구조·도메인 규칙: `docs/ARCHITECTURE.md`

## 폴더 구조

개발 PC 와 서버가 같은 모양이다(서버는 `/opt/duty_generator`).

| 위치 | 무엇 | git |
|---|---|---|
| `config/`, `duty/`, `manage.py` | 코드. `config/` 는 Django 프로젝트(설정을 읽는 `settings.py`, URL, WSGI), `duty/` 는 앱 본체(모델·화면·서비스·관리 명령·템플릿·정적 파일). 설치하지 않고 이 폴더에서 바로 돈다. | 올림 |
| `tests/` | pytest 테스트. | 올림 |
| `requirements.in` / `requirements.lock` / `requirements-dev.txt` | 직접 쓰는 라이브러리(범위) / 운영 설치용 고정 버전 / 개발용 테스트 도구. | 올림 |
| `pyproject.toml` | pytest 설정만. | 올림 |
| `deploy/` | 서버용 systemd 유닛 두 개: `duty-web.service`(웹), `duty-worker.service`(작업자). 아래 "서비스 두 개". | 올림 |
| `docs/ARCHITECTURE.md` | 구조와 도메인 규칙. 코드를 고치기 전에 읽는다. | 올림 |
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

RHEL 9.4 이상 기준(Python 3.12 패키지는 9.4 부터, 시스템 SQLite 3.34 — Django 5.2 는 SQLite 3.31 이상이 필요해서 **RHEL 8 은 안 된다**). 코드는 root 소유(`duty` 는 읽기만), 쓰는 곳은 `data/` 하나(`duty` 소유)다.

```bash
sudo dnf install -y python3.12 python3.12-pip git curl     # 기본 python3(3.9)가 아니라 python3.12 를 쓴다
sudo useradd -r -s /sbin/nologin duty
sudo git clone https://github.com/sanggae4133/duty_generator.git /opt/duty_generator
cd /opt/duty_generator
sudo install -d -o duty -g duty -m 750 data data/backups data/logs
sudo python3.12 -m venv .venv
sudo .venv/bin/pip install -r requirements.lock
sudo install -o root -g duty -m 640 .env.example .env
sudoedit .env   # 견본은 개발 PC 값이다. 여섯 줄을 "서버:" 값으로: DUTY_DEBUG=0, DUTY_SECRET_KEY, DUTY_ALLOWED_HOSTS, DUTY_CSRF_ORIGINS, DUTY_SITE_URL, DUTY_ADMIN_PATH
sudo .venv/bin/python manage.py collectstatic --noinput   # root 로: 코드 폴더는 duty 가 쓸 수 없다
sudo -u duty .venv/bin/python manage.py migrate   # 개발 PC DB 를 가져가면 여기서 멈추고 아래 "개발 PC DB 를 서버로 옮기기"
sudo -u duty .venv/bin/python manage.py createsuperuser  # 첫 어드민: 아이디·이름·비밀번호를 묻는다(아래 "처음 한 번: 계정 만들기")
sudo -u duty .venv/bin/python manage.py check --deploy   # 경고 확인(HTTPS 는 Funnel 이 맡으므로 HSTS·SSL_REDIRECT 경고는 무시)
sudo cp deploy/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now duty-web duty-worker
```

- SELinux(기본 enforcing)에서도 기본 정책으로 돈다(서비스는 `/opt` 의 가상환경을 실행하고 `data/` 에만 쓴다). 서비스가 `Permission denied` 로 안 뜨면 `sudo ausearch -m avc -ts recent` 로 거부 기록을 보고, 파일을 다른 곳에서 옮겨 왔다면 `sudo restorecon -R /opt/duty_generator` 로 라벨을 되돌린다.
- 웹은 `127.0.0.1:8090` 에만 열고 바깥 공개는 Tailscale Funnel 이 맡으므로 firewalld 는 열 것이 없다.
- `DUTY_SECRET_KEY` 는 `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` 로 만든다.
- `.env` 를 고친 뒤에는 `sudo systemctl restart duty-web duty-worker`.
- 서버 명령은 모두 `cd /opt/duty_generator` 에서 실행한다. `manage.py` 는 항상 `sudo -u duty .venv/bin/python manage.py ...` 로 부른다(DB·로그 파일 주인이 `duty` 라서).
- 서버 시계: 알림이 분 단위로 돈다. `timedatectl` 에서 `System clock synchronized: yes`. 시간대와 상관없이 앱은 Asia/Seoul 로 계산한다.
- 작업자는 켜질 때 26시간 안에 만든 백업이 없으면(새 설치·오래 꺼져 있었음) 시각과 상관없이 바로 하나 만든다. 그래서 상태 점검이 "백업 없음"으로 시작하지 않는다.
- `sudo -u duty .venv/bin/python manage.py check --deploy` 가 `DEBUG`·`SECRET_KEY` 경고를 내면 `.env` 의 여섯 줄을 덜 바꾼 것이다.
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
- 첫 어드민은 설치 때 `sudo -u duty .venv/bin/python manage.py createsuperuser` 로 만든다. 아이디·비밀번호 말고 **이름**도 묻는다. 이 계정은 부서가 없어 근무표 대상이 아닌 어드민 전용 계정이고, "스태프 권한"도 켜져 있다. 기본 알림 규칙은 생기지 않는다(필요하면 알림 화면에서 추가).
- 새 사람: [사용자 추가]에서 아이디·이름·부서·파트·구분을 넣는다(비밀번호 없이 만들어지고 아직 로그인할 수 없다).
- 계정 발급: 목록에서 선택 → "계정 발급 / 비밀번호 초기화" 액션 → 화면에 한 번만 보이는 임시 비밀번호를 전달한다. 첫 발급 때 기본 알림 규칙이 생기고, 첫 로그인에서 비밀번호를 바꾸게 한다.
- 어드민 전용 계정(근무표에 안 들어감)은 부서를 비워 둔다. 어드민은 "스태프 권한"과 "슈퍼유저 권한"을 둘 다 켠다. Django 관리 화면(사용자·부서·입력 담당자, 계정 발급, 잠금 해제)은 슈퍼유저만 쓸 수 있다. 어드민은 1~2명을 가정한다.
- 부서 입력 담당자는 부서 화면의 "입력 담당자"에서 지정한다.
- 비밀번호는 항상 [계정 발급] 액션으로 준다. 사용자 편집 화면의 비밀번호 칸에서 Django 기본 "비밀번호 설정/변경" 화면으로 정하면 발급을 거치지 않는다. 그러면 첫 로그인 비밀번호 변경이 걸리지 않고, 기본 알림 규칙도 생기지 않는다. 그 뒤 [계정 발급]을 해도 최초 발급으로 치지 않는다.

## 업그레이드·롤백

지금 버전을 먼저 적어 둔다(롤백할 때 쓴다).

```bash
cd /opt/duty_generator
git log -1 --format=%h                       # 지금 버전(적어 둔다)
sudo systemctl stop duty-web duty-worker
sudo -u duty .venv/bin/python manage.py backup   # data/backups/db-YYYYMMDD-HHMMSS.sqlite3 (경로가 출력된다, 적어 둔다)
sudo git pull --ff-only                      # 특정 버전이면: sudo git fetch && sudo git checkout <버전>
sudo .venv/bin/pip install -r requirements.lock
sudo .venv/bin/python manage.py collectstatic --noinput
sudo -u duty .venv/bin/python manage.py migrate   # 무언가 적용됐으면(DB 구조 변경) 롤백 때 DB 복원이 필요하다
sudo cp deploy/*.service /etc/systemd/system/ && sudo systemctl daemon-reload   # 유닛이 바뀌었을 때만 필요(해도 무해)
sudo systemctl start duty-web duty-worker
systemctl is-active duty-web duty-worker     # 둘 다 active. 아니면 journalctl -u duty-web -n 50
```

- **롤백**: 위와 같은 순서에서 `git pull` 대신 `sudo git checkout <적어 둔 버전>`. 업그레이드 때 `migrate` 가 무언가 적용했으면 `sudo -u duty .venv/bin/python manage.py migrate` 대신 `sudo -u duty .venv/bin/python manage.py restore <업그레이드 전에 만든 백업>`(아래 "백업·복원")을 한다 — 복원은 백업의 마이그레이션이 지금 코드와 같아야 받아 주므로, 코드를 먼저 되돌린 뒤에 한다.
- git 이 "dubious ownership" 을 내면 `sudo chown -R root:root /opt/duty_generator/.git` 후 다시 한다.
- 업그레이드 전 백업도 `db-*` 라 `DUTY_BACKUP_KEEP_DAYS` 일 뒤 자동으로 지워진다. 오래 둘 것은 서버 밖으로 내려받는다.

## 백업·복원

- 자동: 작업자가 매일 `DUTY_BACKUP_HOUR` 시(기본 3시) 이후 처음 돌 때 `data/backups/db-YYYYMMDD.sqlite3` 를 만들고, `DUTY_BACKUP_KEEP_DAYS` 일(기본 30)보다 오래된 `db-*` 를 지운다. 작업자가 꺼져 있었으면 다시 켜질 때 그날 것을 만든다(26시간 안 백업이 없으면 그 시각 전이라도 바로).
- 수동: `sudo -u duty .venv/bin/python manage.py backup` → `data/backups/db-YYYYMMDD-HHMMSS.sqlite3`. 서비스가 도는 중에도 된다. **DB 파일을 `cp` 로 복사하지 말 것**(WAL 모드라 최근 변경이 빠지거나 깨진 사본이 될 수 있다). 백업은 SQLite 백업 기능으로 떠서 일관된 파일 하나가 된다.
- 백업에는 실명과 텔레그램 봇 토큰·푸시 키가 들어 있다. 서버 밖에 보관하려면 내려받되 공유 폴더에 두지 않는다.
- 복원:
  ```bash
  sudo systemctl stop duty-web duty-worker
  sudo -u duty .venv/bin/python manage.py restore data/backups/<백업 파일>
  sudo -u duty .venv/bin/python manage.py migrate
  sudo systemctl start duty-web duty-worker
  ```
  - 작업자가 돌고 있으면(`data/.alarms.lock` 이 잡혀 있으면) 아무것도 바꾸지 않고 멈춘다. 복원하는 동안은 이 잠금을 잡고 있어 작업자가 뜨지 못한다. 웹은 검사하지 않으니 직접 멈춘다.
  - 복원 전에 검사한다. `quick_check` 가 `ok` 가 아니거나 백업의 마이그레이션이 지금 코드와 다르면 아무것도 바꾸지 않고 멈춘다(다르면 그 백업을 만든 버전의 코드로 먼저 바꾼다).
  - 지금 DB 는 `data/backups/before-restore-YYYYMMDD-HHMMSS.sqlite3` 로 남긴다(자동으로 지우지 않는다). 남은 `-wal`·`-shm` 은 지운다.

## 서버에서 데이터 보기

`duty` 는 로그인할 수 없는 계정이라(`/sbin/nologin`) `su - duty` 로는 안 들어가진다. 계정을 바꾸지 않고 `sudo` 로 본다.

```bash
cd /opt/duty_generator
sudo ls -la data data/backups data/logs
sudo tail -f data/logs/worker.log         # 작업자 로그 (web.log 는 웹)
sudo -u duty bash                         # duty 로 셸이 꼭 필요할 때. 나갈 때 exit
```

DB 안을 볼 때는 읽기 전용으로 연다(서비스가 도는 중에도 안전).

```bash
sudo dnf install -y sqlite                # 처음 한 번
sudo -u duty sqlite3 -readonly data/db.sqlite3
# sqlite> .tables
# sqlite> select id, name, status from duty_period;
# sqlite> .quit
```

- 데이터는 DB 를 직접 고치지 말고 웹 화면·관리 화면에서 고친다(직접 고치면 변경 기록이 남지 않고 규칙 검사도 건너뛴다).
- DB 에는 실명과 봇 토큰이 들어 있다. 화면을 캡처하거나 결과를 밖으로 옮기지 않는다.

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

## 개발 PC DB 를 서버로 옮기기 (처음 한 번)

서버는 개발 PC 에서 쓰던 DB 를 그대로 가져가 시작한다. 계정·비밀번호·근무·기록·알림 설정(봇 토큰·푸시 키)이 전부 같이 간다.

```bash
# 개발 PC (저장소 루트): runserver·run_worker 를 멈추고, 서버에 올릴 것과 같은 코드(main)에서
git pull --ff-only
DUTY_DEBUG=1 .venv/bin/python manage.py migrate   # 서버 코드와 마이그레이션을 맞춘다(안 맞으면 restore 가 거부한다)
DUTY_DEBUG=1 .venv/bin/python manage.py backup   # data/backups/db-YYYYMMDD-HHMMSS.sqlite3 (경로가 출력된다)
scp data/backups/db-<시각>.sqlite3 <서버>:/tmp/duty.sqlite3

# 서버: "설치"를 migrate 직전까지 한 뒤 (createsuperuser 는 하지 않는다 — 계정은 DB 에 있다)
sudo systemctl stop duty-web duty-worker 2>/dev/null
sudo install -o duty -g duty -m 640 /tmp/duty.sqlite3 data/import.sqlite3 && rm /tmp/duty.sqlite3
sudo -u duty .venv/bin/python manage.py restore data/import.sqlite3 && sudo rm data/import.sqlite3
sudo -u duty .venv/bin/python manage.py migrate
# 이어서 "설치"의 check --deploy 부터
```

- **DB 파일을 `cp` 로 복사하지 말고 `backup` 으로 뜬다**(WAL 모드라 그냥 복사하면 최근 변경이 빠질 수 있다).
- `restore` 는 파일의 마이그레이션이 서버 코드와 같아야 받는다. 개발 PC 와 서버를 같은 커밋으로 맞춘다.
- 옮긴 뒤에는 **개발 PC 에서 그 DB 로 `run_worker` 를 켜지 않는다**. 같은 봇 토큰으로 두 곳이 알림을 보내고 텔레그램 연결 확인이 서로 엉킨다. 개발 PC 에서 알림을 시험하려면 관리 화면 → 알림 설정에서 토큰을 지우거나 다른 시험용 봇을 넣는다.
- 웹 푸시는 주소(127.0.0.1 → 서버 도메인)가 바뀌어서 개발 PC 에서 등록한 기기는 서버에서 받지 못한다. 각자 서버 주소로 들어가 [이 기기에서 푸시 받기]를 다시 누른다. 텔레그램 연결은 그대로 쓰인다. 캘린더 구독은 주소가 바뀌므로 알림·캘린더 화면에서 다시 발급받는다.
- 개발 PC 에 남은 DB 와 백업에는 실명과 봇 토큰이 들어 있다. 공유 폴더에 두지 않는다.

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

봇은 이 웹앱만 써야 한다. 다른 프로그램(개발 PC 의 `run_worker` 포함)이 같은 봇으로 polling 중이면 서로의 업데이트를 가로챈다(409 충돌).

1. 텔레그램 `@BotFather` 에서 `/newbot` → 토큰과 사용자명을 관리 화면 → 알림 설정에 넣는다.
2. 사용자는 `/alarms/` 의 [텔레그램 연결] → 봇에서 [시작] → [연결 확인]으로 직접 연결한다. 서버에서 따로 할 일은 없다.

[연결 확인]이 "텔레그램 봇 설정 오류입니다."를 띄우면 `getUpdates` 가 4xx 로 거절된 것이다. 대개 409(그 봇에 webhook 이 걸렸거나 다른 프로그램이 같은 봇으로 polling 중) 또는 401(토큰 오류)이다. 토큰을 다시 확인하고, 다른 프로그램이 같은 봇을 쓰고 있지 않은지 본다. 원인을 못 찾으면 BotFather 에서 새 봇을 만들어 알림 설정의 토큰·사용자명을 바꾸는 것이 가장 빠르다(사용자는 다시 연결해야 한다).

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

1. 관리 화면 → 알림 설정에 봇 토큰·사용자명을 넣는다(위 "텔레그램 봇").
2. `sudo -u duty .venv/bin/python manage.py run_worker --dry-run` — 발송·기록 없이 `telegram=<n> push=<n>`(지금 보낼 건수)만 출력한다. 작업자가 도는 중에도 된다.
3. `/alarms/` 에서 텔레그램 연결 또는 chat_id [저장 및 테스트], 푸시 [이 기기에서 푸시 받기] → [테스트 푸시]로 실제 수신을 확인한다. PC Chrome 과 아이폰 홈 화면 앱에서 알림을 누르면 해당 화면이 열리는지도 본다.
4. `sudo tail -f /opt/duty_generator/data/logs/worker.log` 에서 매분 `alarms tick:` 줄이 찍히는지 확인한다.
5. 텔레그램 알림을 모두 멈추려면 관리 화면 → 알림 설정에서 "토큰 지우기". (푸시만 따로 끄는 스위치는 없다. 사용자가 기기를 해제하거나 규칙을 끈다.)

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
