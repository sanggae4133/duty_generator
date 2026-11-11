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

## 설치 (사내 서버)

Ubuntu 24.04 (Python 3.12) 기준. 위치 정리:

| 무엇 | 어디 | 소유·권한 |
|---|---|---|
| 코드·venv | `/opt/duty_generator` | root (duty 는 읽기만) |
| 설정(비밀값) | `/etc/duty_generator/env` | root:duty 640 |
| DB·잠금 파일 | `/var/lib/duty_generator/` | duty 750 |
| 자동 백업 | `/var/backups/duty_generator/` | duty 750 |
| 로그 | `/var/log/duty_generator/*.log` | 폴더 root:adm 750(파일은 systemd 가 root 로 만든다) |

```bash
sudo apt install -y python3-venv sqlite3 git curl   # 백업·업그레이드가 sqlite3 CLI를 쓴다. python3 --version 이 3.12 이상이어야 한다
sudo useradd -r -s /usr/sbin/nologin duty
sudo git clone https://github.com/sanggae4133/duty_generator.git /opt/duty_generator
sudo install -d -o duty -g duty -m 750 /var/lib/duty_generator /var/backups/duty_generator
sudo install -d -o root -g duty -m 750 /etc/duty_generator
sudo install -d -o root -g adm -m 750 /var/log/duty_generator
cd /opt/duty_generator
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.lock && sudo .venv/bin/pip install --no-deps -e .
sudo install -o root -g duty -m 640 deploy/env.example /etc/duty_generator/env
sudoedit /etc/duty_generator/env   # 값 채우기(아래 주의)
# manage.py 를 duty 사용자·운영 설정으로 부르는 함수(이 셸에서만 유효). 아래 절차들이 이걸 쓴다.
dm() { sudo -u duty sh -c 'set -a; . /etc/duty_generator/env; cd /opt/duty_generator && exec .venv/bin/python manage.py "$@"' sh "$@"; }
sudo sh -c 'set -a; . /etc/duty_generator/env; cd /opt/duty_generator && .venv/bin/python manage.py collectstatic --noinput'   # root: /opt 는 duty 쓰기 권한이 없다
dm migrate
dm createsuperuser  # 첫 어드민: 아이디·이름·비밀번호를 묻는다(아래 "처음 한 번: 계정 만들기")
dm check --deploy   # 경고 확인(HTTPS 는 Funnel 이 맡으므로 HSTS·SSL_REDIRECT 경고는 무시)
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/
sudo cp deploy/duty_generator.logrotate /etc/logrotate.d/duty_generator
sudo systemctl daemon-reload
sudo systemctl enable --now duty-generator duty-generator-backup.timer duty-health.timer
sudo systemctl start duty-generator-backup   # 첫 백업(없으면 상태 점검이 "백업 없음"을 알린다)
```

- env 값에는 따옴표, 공백, `$`, `#`, `<>` 를 넣지 않는다. sh 와 systemd 가 모두 이 파일을 읽는다.
- `DUTY_SECRET_KEY` 는 `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` 로 만든다.
- 서버 시계: 알림이 분 단위로 돈다. `timedatectl` 에서 `System clock synchronized: yes`, 시간대와 상관없이 앱은 Asia/Seoul 로 계산한다.
- `duty-alarms.service` 도 함께 복사되지만 여기서는 켜지 않는다. 아래 "알림 → 알림 켜기" 순서대로 켠다.

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

```bash
sudo /opt/duty_generator/deploy/upgrade.sh            # 최신 버전으로
sudo /opt/duty_generator/deploy/upgrade.sh <버전>     # 그 버전으로 되돌리기(롤백)
```

스크립트가 하는 일: 지금 버전 출력 → DB 백업(`before-upgrade-*.sqlite3`) → 웹·알림 중지 → 코드 갱신 → 고정 버전 설치 → 정적 파일·`migrate` → 서비스 파일·logrotate 복사 → 다시 시작 → env 에 빠진 설정 이름 알림. 어느 단계든 실패하면 멈추고(서비스는 꺼진 채) 메시지를 남긴다. 고친 뒤 다시 실행하면 된다.

- 이 스크립트가 없던 예전 버전에서 처음 올릴 때만: `cd /opt/duty_generator && sudo git log -1 --format=%h` 로 지금 버전을 적어 두고 `sudo git pull && sudo deploy/upgrade.sh`. 이 스크립트가 들어오기 전 버전으로는 스크립트로 되돌릴 수 없다(스크립트가 거부한다). 그때는 손으로:
  ```bash
  sudo systemctl disable --now duty-health.timer; sudo systemctl stop duty-alarms duty-generator
  cd /opt/duty_generator && sudo git checkout <적어 둔 버전> && sudo .venv/bin/pip install -e .
  sudo sh -c 'set -a; . /etc/duty_generator/env; cd /opt/duty_generator && .venv/bin/python manage.py collectstatic --noinput'
  # DB 구조가 바뀌었으면: sudo -u duty cp <upgrade.sh 가 만든 before-upgrade 백업> /var/lib/duty_generator/db.sqlite3 && sudo -u duty rm -f /var/lib/duty_generator/db.sqlite3-wal /var/lib/duty_generator/db.sqlite3-shm
  sudo cp deploy/*.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl start duty-generator   # 로그는 다시 journalctl 로 간다
  systemctl is-enabled -q duty-alarms && sudo systemctl start duty-alarms
  ``` git 이 "dubious ownership" 을 내면 `sudo chown -R root:root /opt/duty_generator` 후 다시 한다.
- 롤백할 버전은 업그레이드 때 처음 찍힌 `지금 버전` 값이다(`cd /opt/duty_generator && sudo git log --oneline` 에서도 볼 수 있다).
- 업그레이드에서 DB 구조가 바뀌었으면(`migrate` 가 무언가 적용) 롤백 후 DB 도 그때의 `before-upgrade-*` 로 "복원"한다.
- `before-upgrade-*` 백업은 자동으로 지워지지 않는다. 디스크가 작으면 가끔 오래된 것을 지운다.

## 기존 DB 옮기기 (멤버·계정 통합 전 DB, 1회)

멤버·계정 통합 버전은 마이그레이션을 새 `0001_v2` 하나로 새로 만들었다. 그 전 버전(duty 마이그레이션 0001~0009)으로 데이터를 넣은 DB(개발 PC, 시험 설치 서버)는 `migrate` 로 올라가지 않는다(일부러 실패하고 DB 는 그대로다). 그래서 아래처럼 한 번 옮긴다.

### 서버

`upgrade.sh` 를 먼저 돌린다. 백업, 정지(웹·알림·상태 점검 `duty-health.timer`), 체크아웃, 설치, 정적 파일까지 하고 `migrate` 에서 **멈춘다**(예상된 실패). 그다음 아래 명령으로 손으로 이어 간다. `dm` 은 "설치" 절의 함수다. DB 경로는 env 의 `DUTY_DB_PATH`(기본 `/var/lib/duty_generator/db.sqlite3`)다.

```bash
sudo /opt/duty_generator/deploy/upgrade.sh <v2 버전>        # migrate 에서 멈춘다
sudo systemctl stop duty-health.timer duty-alarms duty-generator   # 이미 멈춰 있다(확인용)
cd /var/lib/duty_generator
sudo -u duty sqlite3 db.sqlite3 ".backup db.sqlite3-v1.sqlite3"   # WAL 까지 담긴 일관된 단일 파일
sudo -u duty sqlite3 db.sqlite3-v1.sqlite3 "PRAGMA quick_check"   # ok 가 나와야 한다
sudo -u duty mkdir -p old && sudo -u duty mv db.sqlite3 old/      # 롤백용으로 옮겨 둔다
for f in db.sqlite3-wal db.sqlite3-shm; do if [ -e "$f" ]; then sudo -u duty mv "$f" old/; fi; done   # 있는 것만
dm migrate                                                   # 빈 새 DB
dm convert_v1 /var/lib/duty_generator/db.sqlite3-v1.sqlite3   # 옮기기(dm 은 /opt 에서 돌므로 절대 경로)
cd /opt/duty_generator   # upgrade.sh 가 migrate 뒤에 하려던 일
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/
sudo cp deploy/duty_generator.logrotate /etc/logrotate.d/duty_generator
sudo systemctl daemon-reload
sudo systemctl start duty-generator
systemctl is-enabled -q duty-alarms && sudo systemctl start duty-alarms   # 알림을 켜 둔 서버만
sudo systemctl enable --now duty-health.timer
```

### 개발 PC

저장소 루트에서 실행한다.

```bash
# runserver·run_alarms 를 멈춘다
sqlite3 db.sqlite3 ".backup db.sqlite3-v1.sqlite3"
sqlite3 db.sqlite3-v1.sqlite3 "PRAGMA quick_check"     # ok
mkdir -p old && mv db.sqlite3 old/
for f in db.sqlite3-wal db.sqlite3-shm; do if [ -e "$f" ]; then mv "$f" old/; fi; done
git checkout <v2 버전> && .venv/bin/pip install -e '.[dev]'
DUTY_DEBUG=1 .venv/bin/python manage.py migrate
DUTY_DEBUG=1 .venv/bin/python manage.py convert_v1 db.sqlite3-v1.sqlite3
```

### 동작

- `convert_v1` 은 `.backup` 으로 만든 단일 파일만 받는다(옆에 내용 있는 `-wal` 이 있으면 거부한다).
- 예전 백업은 읽기 전용으로 열고, 쓰기 전에 아래를 전부 검사한다.
  - 원본: `quick_check`, `foreign_key_check`, duty 마이그레이션이 0001~0009인지.
  - 지금 DB: `0001_v2` 만 적용된 빈 DB인지.
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
- 롤백: 새 `db.sqlite3`(와 `-wal`·`-shm`)를 지우고 `old/` 의 파일을 제자리로 옮긴 뒤 예전 버전 코드로 되돌린다. 서버는 서비스를 멈추고 `old/` 의 파일을 먼저 제자리로 옮긴 다음 `sudo deploy/upgrade.sh <예전 버전>` 을 실행한다. 예전 DB 라 `migrate` 가 할 일은 없다.

## 백업·복원

- 자동: 매일 03:00 `/var/backups/duty_generator/db-YYYYMMDD.sqlite3`, 최근 30개 보관.
- 수동: 서비스가 도는 중에도 아래 명령으로 뜬다. **DB 파일을 `cp` 로 복사하지 말 것**(WAL 모드라 최근 변경이 빠지거나 깨진 사본이 될 수 있다).
  ```bash
  sudo -u duty sqlite3 /var/lib/duty_generator/db.sqlite3 ".backup /var/backups/duty_generator/manual-$(date +%Y%m%d-%H%M).sqlite3"
  ```
  `manual-*` 은 자동으로 지워지지 않는다. 서버 밖에 보관하려면 이 파일을 내려받는다. 실명이 들어 있으니 공유 폴더에 두지 않는다.
- 복원: `sudo /opt/duty_generator/deploy/restore.sh /var/backups/duty_generator/<백업 파일>`
  - 백업 파일을 먼저 검사하고(`PRAGMA quick_check` 가 `ok` 가 아니면 아무것도 바꾸지 않고 멈춤), 서비스 중지 → 지금 DB 를 `before-restore-*` 로 백업 → 교체 → `migrate`(오래된 백업이면 구조 맞춤) → 다시 시작.

## 로그

| 파일 | 내용 |
|---|---|
| `/var/log/duty_generator/web.log` | 웹(gunicorn 시작·오류, 앱 경고·오류) |
| `/var/log/duty_generator/alarms.log` | 알림 발송(`run_alarms`, 아래 "알림 → 로그 읽기") |
| `/var/log/duty_generator/backup.log` | 백업 실패 메시지(성공 시 비어 있음) |
| `/var/log/duty_generator/health.log` | 상태 점검 결과가 바뀔 때마다 한 줄 |

- 읽기: `sudo tail -f /var/log/duty_generator/alarms.log`, 경고·오류만: `sudo sh -c "grep -E ' (WARNING|ERROR) ' /var/log/duty_generator/*.log"`. 지난 날짜는 `web.log.1`, `web.log.2.gz` … (`sudo zgrep`).
- **보관 기간**: `/etc/logrotate.d/duty_generator` 의 `rotate 7`(일) 숫자를 바꾼다. 하루에 `maxsize 50M` 을 넘은 파일은 그날 회전할 때 넘긴다. 저장소의 `deploy/duty_generator.logrotate` 도 같이 바꿔 두면 업그레이드 때 덮어써도 유지된다.
- 접근 로그(요청마다 한 줄)는 남기지 않는다. 캘린더 구독 주소에 비밀 토큰이 들어 있어서다(gunicorn `--access-logfile` 을 켜지 말 것).

## 장애 알림

`duty-health.timer` 가 5분마다 아래를 보고, **상태가 바뀔 때만** 관리자 텔레그램으로 알린다(문제가 생겼을 때 한 번, 정상으로 돌아왔을 때 한 번).

- 웹이 응답하지 않음 / 알림 서비스(`duty-alarms`, 켜 둔 경우만)가 멈춤 / 26시간 안에 만든 자동 백업이 없음 / DB 디스크 사용 90% 이상
- 보내는 봇은 알림용 `DUTY_TELEGRAM_BOT_TOKEN`, 받는 사람은 env 의 `DUTY_OPS_CHAT_ID`(관리자 개인 chat_id, 아래 "텔레그램 봇" 4단계로 확인). 비우면 `health.log` 에만 남는다.
- 처음 실행이 정상이면 `health.log` 에 "정상" 한 줄만 남기고 알리지 않는다.
- 웹 점검은 `http://127.0.0.1:8090/login/` 을 부르므로 `DUTY_ALLOWED_HOSTS` 에 `127.0.0.1` 이 있어야 한다.
- 시험: `sudo systemctl stop duty-generator` → 5분 안에 알림 → `sudo systemctl start duty-generator` → 복구 알림.

## 의존성 고정

운영 설치는 `requirements.lock` 의 버전만 쓴다(`pyproject.toml` 은 범위만 적는다). 라이브러리를 올릴 때만 개발 PC 에서 다시 만든다.

```bash
python3 -m venv /tmp/lockvenv && /tmp/lockvenv/bin/pip install -U .
{ echo '# 운영 설치용 고정 버전. 갱신: README "의존성 고정" 참고'; /tmp/lockvenv/bin/pip freeze --exclude-editable | grep -v '^duty-generator'; } > requirements.lock
rm -rf /tmp/lockvenv
.venv/bin/pip install -r requirements.lock && .venv/bin/pytest -W error   # 통과하면 커밋
```

## 알림 (텔레그램·웹 푸시)

사용자가 `/alarms/` 에서 규칙을 만들면 `duty-alarms` 서비스(`manage.py run_alarms`, 1분마다)가 보낸다. 웹(gunicorn)과 별도 프로세스다.

### 설정값 (`/etc/duty_generator/env`)

| 변수 | 내용 |
|---|---|
| `DUTY_TELEGRAM_BOT_TOKEN` | 웹앱 전용 봇 토큰. 비우면 텔레그램 채널이 꺼진다. |
| `DUTY_TELEGRAM_BOT_USERNAME` | 그 봇의 사용자명(`@` 없이). 비우면 [텔레그램 연결] 자동 연결을 못 쓰고 chat_id 직접 입력만 된다. |
| `DUTY_VAPID_PUBLIC_KEY` / `DUTY_VAPID_PRIVATE_KEY` | 웹 푸시 키. 둘 중 하나라도 비면 푸시가 꺼진다. |
| `DUTY_VAPID_SUBJECT` | `mailto:admin@example.com` 형식. 푸시 서비스가 문제 시 연락하는 주소. |
| `DUTY_SITE_URL` | `https://duty.example.ts.net`(경로 없이 호스트만). 텔레그램 알림 링크·캘린더 구독 주소용(비면 링크 생략, 캘린더 구독 주소 발급 불가). |
| `DUTY_ALARMS_LOCK` | 선택. 기본은 DB 와 같은 폴더의 `.alarms.lock`. `run_alarms` 중복 실행 방지 잠금. |
| `DUTY_TELEGRAM_LOCK` | 선택. 기본은 DB 와 같은 폴더의 `.telegram-updates.lock`. [연결 확인]이 `getUpdates` 를 한 번에 하나만 부르게 하는 잠금. |

잠금 경로를 직접 정할 때는 `duty` 사용자가 쓸 수 있는 곳이어야 한다(`/opt/duty_generator` 는 안 된다). 쓸 수 없으면 `run_alarms` 가 시작하지 못하고 [연결 확인]이 500 오류가 난다. 기본값(DB 폴더)은 SQLite 가 쓰는 곳이라 항상 쓸 수 있다.

**기존 서버에 알림 기능을 처음 올릴 때**: 위 "업그레이드·롤백"으로 올리고, 스크립트가 알려 주는 빠진 설정(`# --- 개인 알림` 아래 변수들)을 env 에 추가한 뒤, 아래 "알림 켜기" 1번부터 진행한다.

### VAPID 키 만들기

키는 반드시 아래 명령으로 만든다(형식이 다르거나 깨진 개인키는 설정 단계에서 걸러지지 않고, 발송할 때마다 실패 로그 `status=Temporary:None` 로만 드러난다). 출력 두 줄을 env 파일에 붙이고, 화면 기록 외에 파일로 남기지 않는다. 키를 바꾸면 기존 기기 구독은 모두 다시 해야 한다.

```bash
cd /opt/duty_generator && .venv/bin/python -c "
from py_vapid import Vapid01, b64urlencode
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
v = Vapid01(); v.generate_keys()
print('DUTY_VAPID_PUBLIC_KEY=' + b64urlencode(v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)))
print('DUTY_VAPID_PRIVATE_KEY=' + b64urlencode(v.private_key.private_numbers().private_value.to_bytes(32, 'big')))
"
```

### 텔레그램 봇

봇은 이 웹앱만 써야 한다. 다른 프로그램(예: 예전 `duty_notifier`)이 같은 봇으로 polling 중이면 서로의 업데이트를 가로챈다(409 충돌). 예전 봇을 다시 쓰려면 그 프로그램을 먼저 끈다.

1. 텔레그램 `@BotFather` 에서 `/newbot` → 토큰과 사용자명을 `DUTY_TELEGRAM_BOT_TOKEN`, `DUTY_TELEGRAM_BOT_USERNAME` 에 넣는다.
2. 토큰을 셸 기록에 남기지 않도록 env 파일에서 읽어 부르는 함수를 만든다(이 셸에서만 유효).
   ```bash
   tg() { sudo sh -c '. /etc/duty_generator/env; curl --fail-with-body --silent --show-error "https://api.telegram.org/bot$DUTY_TELEGRAM_BOT_TOKEN/$1"; echo' sh "$1"; }
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

### 로그 읽기 (`/var/log/duty_generator/alarms.log`)

- 각 줄은 `<날짜 시각> <레벨> <로거> <메시지>` 형식이다(예: `2026-11-11 09:00:00 INFO duty.services.alarm_runner alarms tick: ...`, 실패는 `WARNING`). 실패만 보려면 `sudo grep -E ' (WARNING|ERROR) ' /var/log/duty_generator/alarms.log`.
- 매분 `alarms tick: due=<보낼 건수> sent=<성공> failed=<실패>`.
- 실패마다 `alarm send failed rule=<규칙 id> channel=<telegram|push> delivery=<기록 id> status=<종류>:<HTTP 코드> attempt=<시도 횟수>`. `status` 는 결과 상태가 아니라 실패 종류와 응답 코드를 붙인 것이다(코드가 없으면 `None`).
  - `Temporary:None` — 네트워크 오류·응답 이상·깨진 VAPID 키. 1, 2, 4 … 최대 30분 간격으로 재시도.
  - `Temporary:<5xx>` — 상대 서버 오류. 위와 같이 재시도(텔레그램 503 도 여기).
  - 푸시만 `Temporary:401`/`403` — VAPID 키·subject 설정 오류일 가능성. 재시도하므로 키를 고치면 다시 나간다.
  - `RetryLater:429`(텔레그램·푸시), `RetryLater:503`(푸시만) — 상대가 알려 준 시간(`retry_after`/`Retry-After`) 뒤 재시도. 시간을 안 알려 주면 위의 일반 간격.
  - `Permanent:<4xx>` — 그 알림은 만료 시각까지 다시 보내지 않는다. 텔레그램 `Permanent:401` 은 봇 토큰 오류, `Permanent:403` 은 사용자가 봇을 차단, `Permanent:400` 은 chat_id 오류. 푸시는 401·403·404·410·429 를 뺀 4xx(구독 데이터 이상 등).
  - 그 밖의 이름(예: `OperationalError:None`)은 예기치 않은 예외 — 일시 실패로 재시도된다. 계속 나오면 확인한다.
- 만료된 푸시 구독(404/410)은 로그 없이 지워진다. 기기에서 다시 [이 기기에서 푸시 받기]를 누르면 된다.

### 알림 켜기

1. env 값을 채우고 `sudo systemctl restart duty-generator` 후 `dm run_alarms --dry-run` — 발송·기록 없이 `telegram=<n> push=<n>`(지금 보낼 건수)만 출력한다. 오류 없이 끝나야 한다.
2. `/alarms/` 에서 텔레그램 연결 또는 chat_id [저장 및 테스트], 푸시 [이 기기에서 푸시 받기] → [테스트 푸시]로 실제 수신을 확인한다.
3. PC Chrome 과 아이폰 홈 화면 앱에서 테스트 푸시가 오는지, 알림을 누르면 해당 화면이 열리는지 확인한다.
4. 예전 `duty_notifier` 가 이 서버에서 아직 돌고 있으면 먼저 끈다(같은 알림이 두 번 가지 않게): `sudo systemctl disable --now duty-notifier`
5. `sudo systemctl enable --now duty-alarms` 후 `sudo tail -f /var/log/duty_generator/alarms.log` 에서 매분 `alarms tick:` 줄이 찍히는지 확인한다.
6. 끄기: `sudo systemctl disable --now duty-alarms`

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
