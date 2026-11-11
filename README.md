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

위치 정리:

| 무엇 | 어디 | 소유·권한 |
|---|---|---|
| 코드·venv | `/opt/duty_generator` | root (duty 는 읽기만) |
| 설정(비밀값) | `/etc/duty_generator/env` | root:duty 640 |
| DB·잠금 파일 | `/var/lib/duty_generator/` | duty 750 |
| 자동 백업 | `/var/backups/duty_generator/` | duty 750 |
| 로그 | `/var/log/duty_generator/*.log` | root:adm 750 |

```bash
sudo apt install -y sqlite3 git curl   # 백업 타이머가 sqlite3 CLI를 쓴다
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
dm check --deploy   # 경고 확인(HTTPS 는 Funnel 이 맡으므로 HSTS·SSL_REDIRECT 경고는 무시)
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/
sudo cp deploy/duty_generator.logrotate /etc/logrotate.d/duty_generator
sudo systemctl daemon-reload
sudo systemctl enable --now duty-generator duty-generator-backup.timer duty-health.timer
sudo systemctl start duty-generator-backup   # 첫 백업(없으면 상태 점검이 "백업 없음"을 알린다)
```

- env 값에는 따옴표, 공백, `$`, `#`, `<>` 를 넣지 않는다. sh 와 systemd 가 모두 이 파일을 읽는다.
- `DUTY_SECRET_KEY`·`DUTY_API_TOKEN` 은 `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` 로 만든다. `DUTY_API_TOKEN` 은 비우면 안 된다(빈 값이면 API 가 모두 401).
- 서버 시계: 알림이 분 단위로 돈다. `timedatectl` 에서 `System clock synchronized: yes`, 시간대와 상관없이 앱은 Asia/Seoul 로 계산한다.
- `duty-alarms.service` 도 함께 복사되지만 여기서는 켜지 않는다. 아래 "알림 → 알림 켜기" 순서대로 켠다.

## 외부 공개 (Tailscale Funnel)


```bash
sudo tailscale funnel --bg --set-path / http://127.0.0.1:8090
sudo tailscale funnel status
```

- `--set-path /` 는 모든 경로를 공개한다. 따라서 `/api/assignments` 도 Funnel 을 통해 외부에서 호출할 수 있다. 이 API 를 막는 것은 `Authorization: Bearer <DUTY_API_TOKEN>` 헤더뿐이다.
- `DUTY_API_TOKEN` 은 `secrets.token_urlsafe(48)` 로 만들고 비워 두지 않는다. 빈 값이면 앱이 모든 요청을 401 로 거부한다.

## 처음 한 번: 기존 시트 가져오기

```bash
dm import_sheets --dry-run
dm import_sheets
```

이후 `/<DUTY_ADMIN_PATH>/` 의 멤버 목록에서 멤버를 선택하고 "계정 발급 / 비밀번호 초기화" 액션으로 임시 비밀번호를 발급한다.
부서 입력 담당자는 부서 화면의 "입력 담당자"에서 지정한다. 어드민은 사용자 화면에서 "스태프 권한"과 "슈퍼유저 권한"을 둘 다 켠다. Django 관리 화면(멤버·부서·입력 담당자, 계정 발급, 잠금 해제)은 슈퍼유저만 쓸 수 있다. 어드민은 1~2명을 가정한다.

## 업그레이드

새 버전을 올릴 때는 항상 이 순서로 한다(`dm` 함수는 "설치" 참고).

```bash
cd /opt/duty_generator
sudo systemctl start duty-generator-backup && ls -1t /var/backups/duty_generator | head -n 1   # 1. 백업 먼저(실패하면 멈춘다)
sudo git log -1 --format=%h               # 2. 지금 버전 기록(롤백 때 씀)
sudo git pull                             # 3. 코드 갱신
sudo .venv/bin/pip install -r requirements.lock && sudo .venv/bin/pip install --no-deps -e .
sudo sh -c 'set -a; . /etc/duty_generator/env; cd /opt/duty_generator && .venv/bin/python manage.py collectstatic --noinput'
dm migrate
diff deploy/env.example /etc/duty_generator/env | grep '^<'   # 4. 새로 생긴 설정 변수가 있으면 sudoedit 로 추가
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/ && sudo cp deploy/duty_generator.logrotate /etc/logrotate.d/duty_generator
sudo systemctl daemon-reload && sudo systemctl restart duty-generator
systemctl is-enabled -q duty-alarms && sudo systemctl restart duty-alarms
sudo tail -n 20 /var/log/duty_generator/web.log   # 5. 오류 없는지
```

(4번의 diff 는 값이 다른 줄도 나온다. 변수 이름이 env 에 아예 없는 줄만 추가하면 된다.)

## 롤백

```bash
cd /opt/duty_generator
sudo systemctl stop duty-alarms duty-generator
sudo git checkout <업그레이드 2번에서 기록한 버전>
sudo .venv/bin/pip install -r requirements.lock && sudo .venv/bin/pip install --no-deps -e .
sudo sh -c 'set -a; . /etc/duty_generator/env; cd /opt/duty_generator && .venv/bin/python manage.py collectstatic --noinput'
# 업그레이드에서 migrate 가 무언가 적용했다면 DB 도 업그레이드 1번 백업으로 되돌린다(아래 "복원")
sudo systemctl start duty-generator
systemctl is-enabled -q duty-alarms && sudo systemctl start duty-alarms
```

롤백 뒤 다시 최신으로 갈 때는 `sudo git checkout main` 후 "업그레이드"를 처음부터 한다.

## 백업·복원

- 자동: 매일 03:00 `/var/backups/duty_generator/db-YYYYMMDD.sqlite3`, 최근 30개 보관.
- 수동: 서비스가 도는 중에도 아래 명령으로 뜬다. **DB 파일을 `cp` 로 복사하지 말 것**(WAL 모드라 최근 변경이 빠지거나 깨진 사본이 될 수 있다).
  ```bash
  sudo -u duty sqlite3 /var/lib/duty_generator/db.sqlite3 ".backup /var/backups/duty_generator/manual-$(date +%Y%m%d-%H%M).sqlite3"
  ```
  `manual-*` 은 자동으로 지워지지 않는다. 서버 밖에 보관하려면 이 파일을 내려받는다. 실명이 들어 있으니 공유 폴더에 두지 않는다.
- 복원:
  ```bash
  sudo systemctl stop duty-alarms duty-generator
  sudo -u duty cp /var/backups/duty_generator/<백업 파일> /var/lib/duty_generator/db.sqlite3
  sudo -u duty rm -f /var/lib/duty_generator/db.sqlite3-wal /var/lib/duty_generator/db.sqlite3-shm
  sudo systemctl start duty-generator
  systemctl is-enabled -q duty-alarms && sudo systemctl start duty-alarms
  ```

## 로그

| 파일 | 내용 |
|---|---|
| `/var/log/duty_generator/web.log` | 웹(gunicorn 시작·오류, 앱 경고·오류) |
| `/var/log/duty_generator/alarms.log` | 알림 발송(`run_alarms`, 아래 "알림 → 로그 읽기") |
| `/var/log/duty_generator/backup.log` | 백업 실패 메시지(성공 시 비어 있음) |
| `/var/log/duty_generator/health.log` | 상태 점검 결과가 바뀔 때마다 한 줄 |

- 읽기: `sudo tail -f /var/log/duty_generator/alarms.log`, 경고·오류만: `sudo grep -E ' (WARNING|ERROR) ' /var/log/duty_generator/*.log`. 지난 날짜는 `web.log.1`, `web.log.2.gz` … (`sudo zgrep`).
- **보관 기간**: `/etc/logrotate.d/duty_generator` 의 `rotate 7`(일) 숫자를 바꾼다. 하루에 `maxsize 50M` 을 넘은 파일은 그날 회전할 때 넘긴다. 저장소의 `deploy/duty_generator.logrotate` 도 같이 바꿔 두면 업그레이드 때 덮어써도 유지된다.
- 접근 로그(요청마다 한 줄)는 남기지 않는다. 캘린더 구독 주소에 비밀 토큰이 들어 있어서다(gunicorn `--access-logfile` 을 켜지 말 것).

## 장애 알림

`duty-health.timer` 가 5분마다 아래를 보고, **상태가 바뀔 때만** 관리자 텔레그램으로 알린다(문제가 생겼을 때 한 번, 정상으로 돌아왔을 때 한 번).

- 웹이 응답하지 않음 / 알림 서비스(`duty-alarms`, 켜 둔 경우만)가 멈춤 / 26시간 안에 만든 자동 백업이 없음 / DB 디스크 사용 90% 이상
- 보내는 봇은 알림용 `DUTY_TELEGRAM_BOT_TOKEN`, 받는 사람은 env 의 `DUTY_OPS_CHAT_ID`(관리자 개인 chat_id, 아래 "텔레그램 봇" 4단계로 확인). 비우면 `health.log` 에만 남는다.
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

**기존 서버에 알림 기능을 처음 올릴 때**: 위 "업그레이드"를 하고(4번에서 `# --- 개인 알림` 아래 변수들을 env 에 추가), 아래 "전환" ①부터 진행한다. `duty-alarms` 는 전환 ④에서 켠다.

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
- 피드에는 배포된 회차의 본인 출근조·관제 일정만, 오늘 기준 지난 90일부터 나온다. 퇴사(재직 끔)·계정 비활성·멤버 연결 해제면 빈 캘린더가 된다.
- 갱신 시점은 캘린더 앱이 정한다(Google은 몇 시간 이상 걸리기도 함). 즉시 알아야 하는 변경은 텔레그램·푸시 알림이 맡는다.
- DB에는 토큰의 SHA-256 해시만 남고 주소는 발급 화면에 한 번만 보인다. 주소가 유출되면 본인이 [주소 재발급](기존 주소 즉시 무효) 또는 [구독 끄기]를 누른다. 피드 경로는 앱 로그(`django.request`·`django.server`)에서 `calendar feed <상태코드>`로 바뀌어 남는다.
- `DUTY_SITE_URL`이 비어 있으면 주소를 발급할 수 없다. 값은 경로 없이 `https://호스트[:포트]` 형식만 허용(DEBUG에서만 `http`), 경로·공백·제어문자·`?`·`#`·`user@`·잘못된 포트가 있으면 서버가 시작하지 않는다.
- 피드 오류 로그에 지역 변수를 담는 도구(HTML 오류 메일 `include_html`, 지역 변수 수집 APM)를 켜지 말 것 — 토큰이 포함될 수 있음.

## 운영 메모

- 로그인 5회 실패 시 그 계정은 15분 잠긴다. 슈퍼유저가 Admin의 Axes 메뉴에서 해제할 수 있다.
  잠금은 아이디 기준이라 멤버 코드를 아는 사람은 그 계정을 15분씩 계속 잠글 수 있다. 이때도 슈퍼유저가 Axes 관리 화면에서 풀면 된다.
- 퇴사자는 멤버의 "재직"을 끈다. 이제 로그인도 차단된다(스태프 제외).
