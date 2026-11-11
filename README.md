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

## 설치 (사내 서버, 노티파이어와 같은 서버)

```bash
sudo apt install -y sqlite3   # 백업 타이머가 sqlite3 CLI를 쓴다
sudo useradd -r -s /usr/sbin/nologin duty
sudo mkdir -p /opt/duty_generator
sudo install -d -o duty -g duty -m 750 /var/lib/duty_generator /var/backups/duty_generator
sudo install -d -o root -g duty -m 750 /etc/duty_generator
# 코드 배치 후
cd /opt/duty_generator && python3 -m venv .venv && .venv/bin/pip install -e .
sudo install -o root -g duty -m 640 deploy/env.example /etc/duty_generator/env   # 값 채우기 (SECRET_KEY, API 토큰은 python -c "import secrets;print(secrets.token_urlsafe(48))")
# 주의: /etc/duty_generator/env 값에는 따옴표, 공백, $, #, <> 를 넣지 않는다. sh 와 systemd 가 모두 이 파일을 읽는다.
# DUTY_API_TOKEN 은 비우면 안 된다(빈 값이면 API 가 모두 401). 생성: python3 -c "import secrets;print(secrets.token_urlsafe(48))"
sudo sh -c 'set -a; . /etc/duty_generator/env; cd /opt/duty_generator && .venv/bin/python manage.py collectstatic --noinput'   # root: /opt 는 duty 쓰기 권한이 없다
sudo -u duty sh -c 'set -a; . /etc/duty_generator/env; cd /opt/duty_generator && .venv/bin/python manage.py migrate'
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now duty-generator duty-generator-backup.timer
```

`duty-alarms.service` 도 함께 복사되지만 여기서는 켜지 않는다. 아래 "알림 → 전환" 순서대로 켠다.

## 외부 공개 (Tailscale Funnel)

443 포트를 경로로 나눈다. 웹은 `/`, 노티파이어 카카오 웹훅은 기존 경로를 유지한다.

```bash
sudo tailscale funnel --bg --set-path / http://127.0.0.1:8090
sudo tailscale funnel status
```

- `--set-path /` 는 모든 경로를 공개한다. 따라서 `/api/assignments` 도 Funnel 을 통해 외부에서 호출할 수 있다. 이 API 를 막는 것은 `Authorization: Bearer <DUTY_API_TOKEN>` 헤더뿐이다.
- `DUTY_API_TOKEN` 은 `secrets.token_urlsafe(48)` 로 만들고 비워 두지 않는다. 빈 값이면 앱이 모든 요청을 401 로 거부한다.
- 노티파이어는 여전히 Funnel 을 거치지 않고 `http://127.0.0.1:8090/api/assignments` 를 직접 호출한다(같은 서버). 같은 토큰을 `Authorization: Bearer $DUTY_API_TOKEN` 으로 보낸다.

## 처음 한 번: 기존 시트 가져오기

```bash
sudo -u duty sh -c 'set -a; . /etc/duty_generator/env; cd /opt/duty_generator && .venv/bin/python manage.py import_sheets --dry-run'
sudo -u duty sh -c 'set -a; . /etc/duty_generator/env; cd /opt/duty_generator && .venv/bin/python manage.py import_sheets'
```

이후 `/<DUTY_ADMIN_PATH>/` 의 멤버 목록에서 멤버를 선택하고 "계정 발급 / 비밀번호 초기화" 액션으로 임시 비밀번호를 발급한다.
부서 입력 담당자는 부서 화면의 "입력 담당자"에서 지정한다. 어드민은 사용자 화면에서 "스태프 권한"과 "슈퍼유저 권한"을 둘 다 켠다. Django 관리 화면(멤버·부서·입력 담당자, 계정 발급, 잠금 해제)은 슈퍼유저만 쓸 수 있다. 어드민은 1~2명을 가정한다.

## 알림 (텔레그램·웹 푸시)

사용자가 `/alarms/` 에서 규칙을 만들면 `duty-alarms` 서비스(`manage.py run_alarms`, 1분마다)가 보낸다. 웹(gunicorn)과 별도 프로세스다.

### 설정값 (`/etc/duty_generator/env`)

| 변수 | 내용 |
|---|---|
| `DUTY_TELEGRAM_BOT_TOKEN` | 웹앱 전용 봇 토큰. 비우면 텔레그램 채널이 꺼진다. |
| `DUTY_TELEGRAM_BOT_USERNAME` | 그 봇의 사용자명(`@` 없이). 비우면 [텔레그램 연결] 자동 연결을 못 쓰고 chat_id 직접 입력만 된다. |
| `DUTY_VAPID_PUBLIC_KEY` / `DUTY_VAPID_PRIVATE_KEY` | 웹 푸시 키. 둘 중 하나라도 비면 푸시가 꺼진다. |
| `DUTY_VAPID_SUBJECT` | `mailto:admin@example.com` 형식. 푸시 서비스가 문제 시 연락하는 주소. |
| `DUTY_SITE_URL` | `https://duty.example.ts.net`. 텔레그램 알림 마지막 줄의 링크용(비면 링크 생략). |
| `DUTY_ALARMS_LOCK` | **필수.** `/var/lib/duty_generator/alarms.lock`. `run_alarms` 중복 실행 방지 잠금. |
| `DUTY_TELEGRAM_LOCK` | **필수.** `/var/lib/duty_generator/telegram-updates.lock`. [연결 확인]이 `getUpdates` 를 한 번에 하나만 부르게 하는 잠금. |

두 잠금 경로는 `duty` 사용자가 쓸 수 있어야 한다. 기본값은 코드 폴더(`/opt/duty_generator`, `duty` 쓰기 불가)라서 비워 두면 `run_alarms` 가 시작하지 못하고 [연결 확인]이 500 오류가 난다.

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

### 텔레그램 봇 (웹앱 전용으로 새로 만든다)

기존 `duty_notifier` 봇은 polling(`getUpdates`) 중이라 같은 봇을 쓰면 서로의 업데이트를 가로챈다(409 충돌). 반드시 새 봇을 쓴다.

1. 텔레그램 `@BotFather` 에서 `/newbot` → 토큰과 사용자명을 `DUTY_TELEGRAM_BOT_TOKEN`, `DUTY_TELEGRAM_BOT_USERNAME` 에 넣는다.
2. webhook 이 걸려 있지 않은지 확인한다. 응답의 `url` 이 `""` 이어야 한다.
   ```bash
   curl -s "https://api.telegram.org/bot<토큰>/getWebhookInfo"
   # url 이 비어 있지 않으면 한 번만:
   curl -s "https://api.telegram.org/bot<토큰>/deleteWebhook?drop_pending_updates=false"
   ```
3. (직접 입력용) chat_id 확인: 그 사람이 새 봇에게 `/start` 를 보낸 뒤 `curl -s "https://api.telegram.org/bot<토큰>/getUpdates"` 의 `message.chat.id`. `offset` 은 붙이지 않는다(붙이면 대기 중인 연결 요청이 확인 처리돼 사라진다).
   보통은 사용자가 `/alarms/` 의 [텔레그램 연결] → 봇에서 [시작] → [연결 확인]으로 직접 연결하므로 이 단계는 필요 없다.

위 명령의 토큰은 셸 기록에 남는다. 공용 계정에서 실행했다면 기록에서 지운다.

### 웹 푸시 지원 범위

- 받는 쪽 푸시 서비스는 Chrome·Android(FCM), Firefox(Mozilla), Safari·iOS(Apple)만 허용한다. Edge(WNS)는 지원하지 않는다(구독 시 "지원하지 않는 푸시 서비스입니다.").
- 한 사용자당 기기 20대까지.
- 아이폰·아이패드: iOS 16.4 이상에서 Safari 로 사이트를 연 뒤 공유 → "홈 화면에 추가" 한 앱에서만 푸시를 받을 수 있다. 그 홈 화면 앱 안에서 `/alarms/` → [이 기기에서 푸시 받기]를 누른다. 사파리 탭에서는 안 된다. 안내 화면: `/help/push/`.

### 로그 읽기 (`journalctl -u duty-alarms`)

- 매분 `alarms tick: due=<보낼 건수> sent=<성공> failed=<실패>`.
- 실패마다 `alarm send failed rule=<규칙 id> channel=<telegram|push> delivery=<기록 id> status=<종류>:<HTTP 코드> attempt=<시도 횟수>`. `status` 는 결과 상태가 아니라 실패 종류와 응답 코드를 붙인 것이다(코드가 없으면 `None`).
  - `Temporary:None` — 네트워크 오류·응답 이상·깨진 VAPID 키. 1, 2, 4 … 최대 30분 간격으로 재시도.
  - `Temporary:<5xx>`, `Temporary:401`/`403`(푸시: VAPID 키·subject 설정 오류 가능성 — 키를 고치면 다시 나간다) — 재시도.
  - `RetryLater:429`/`503` — 상대가 알려 준 시간 뒤 재시도.
  - `Permanent:<4xx>` — 그 알림은 만료 시각까지 다시 보내지 않는다. 텔레그램 `Permanent:401` 은 봇 토큰 오류, `Permanent:403` 은 사용자가 봇을 차단, `Permanent:400` 은 chat_id 오류, `Permanent:409` 는 그 봇에 webhook 이 걸렸거나 다른 프로그램이 polling 중.
  - 그 밖의 이름(예: `OperationalError:None`)은 예기치 않은 예외 — 일시 실패로 재시도된다. 계속 나오면 확인한다.
- 만료된 푸시 구독(404/410)은 로그 없이 지워진다. 기기에서 다시 [이 기기에서 푸시 받기]를 누르면 된다.

### 전환 (duty_notifier 규칙 → 웹앱 알림)

1. env 값을 채우고 `sudo systemctl restart duty-generator` 후 `sudo -u duty sh -c 'set -a; . /etc/duty_generator/env; cd /opt/duty_generator && .venv/bin/python manage.py run_alarms --dry-run'` — 발송·기록 없이 `telegram=<n> push=<n>`(지금 보낼 건수)만 출력한다. 오류 없이 끝나야 한다.
2. `/alarms/` 에서 텔레그램 연결 또는 chat_id [저장 및 테스트], 푸시 [이 기기에서 푸시 받기] → [테스트 푸시]로 실제 수신을 확인한다.
3. PC Chrome 과 아이폰 홈 화면 앱에서 테스트 푸시가 오는지, 알림을 누르면 해당 화면이 열리는지 확인한다.
4. `duty_notifier` 의 `rules` 를 비우고(같은 알림이 두 번 가지 않게) `sudo systemctl enable --now duty-alarms`.
5. `journalctl -u duty-alarms -f` 에서 매분 `alarms tick:` 줄이 찍히는지 확인한다.
6. 롤백: `sudo systemctl disable --now duty-alarms` 후 `duty_notifier` 의 `rules` 를 되돌린다.

## 운영 메모

- 로그인 5회 실패 시 그 계정은 15분 잠긴다. 슈퍼유저가 Admin의 Axes 메뉴에서 해제할 수 있다.
  잠금은 아이디 기준이라 멤버 코드를 아는 사람은 그 계정을 15분씩 계속 잠글 수 있다. 이때도 슈퍼유저가 Axes 관리 화면에서 풀면 된다.
- 퇴사자는 멤버의 "재직"을 끈다. 이제 로그인도 차단된다(스태프 제외).
- 백업: 매일 03:00 `/var/backups/duty_generator/` 에 최근 30개 보관.
