# 개인별 알림(텔레그램·웹 푸시) 설계

상태: 사용자 확인 대기 · 2026-11-10 · 상위 설계: `2026-11-09-duty-generator-design.md`

## 목표

`duty_notifier`(시트 기반, 설정 파일의 공통 규칙)가 하던 당번 알림을 웹앱으로 옮기고, 사람마다 알림 규칙을 직접 정하게 한다.

- 채널: 텔레그램(각자 chat_id 직접 입력, 선택), 웹 푸시(PWA, 기기별 구독).
- 규칙은 사람마다 여러 개. 규칙마다 종류(개인/보고서형), 기준(시간/일/영업일), 채널(텔레그램·푸시 중복 선택), 대상 조건을 정한다.
- 시간 기준과 영업일 기준은 병행·중복 가능.

범위 밖: 텔레그램 봇의 조회 명령(`/today` 등) — `duty_notifier`에 남긴다. 공휴일 처리(근무표와 같이 평일 = 영업일).

## 결정 사항

| 항목 | 결정 |
|---|---|
| 발송 위치 | 웹앱(Django)으로 통합. `duty_notifier`의 알림 발송은 전환 시 끈다(중복 방지) |
| 시간 단위 | 분. 화면은 "N시간 M분" 입력 → 분으로 저장. 발송 시각도 분 단위(HH:MM) |
| 장중당번 | 개인 알림 대상에 포함. 시작 시각 = 칸 시간대의 시작(예: 10:30~11:30 → 10:30) |
| 기본 규칙 | 모든 계정(신규·기존)에 2개: ① 개인, 1일 전 18:00, 텔레그램, 새벽·석식교대·야간 ② 개인, 시작 120분 전, 텔레그램, 새벽·석식교대·야간 |
| enum | `TextChoices` + DB `CheckConstraint`(CLAUDE.md 규칙) |
| 고아 row | 모든 FK `CASCADE`(사용자 → 프로필·구독·규칙 → 발송기록) |

## 근무 시작 시각 (코드 상수, `duty/shifts.py`)

| 스케줄 | 시간 |
|---|---|
| 새벽 `dawn` | 06:30~15:30 |
| 정상 `normal` | 08:00~17:00 |
| 석식교대 `dinner` | 09:00~18:00 |
| 야간 `night` | 13:30~21:30 |
| 장중당번 `slot0`~`slot9` | `CONTROL_SLOTS` 라벨의 시간대 |

(`duty_notifier` config의 값과 같음: 9시 = 석식교대, 저녁 = 야간)

## 데이터 구조

```
TelegramAlarmProfile         사용자당 1개
├─ user      → User (1:1, CASCADE)
└─ chat_id   CharField, 비우면 텔레그램 발송 안 함

PushAlarmSubscription        기기마다 1개
├─ user      → User (CASCADE)
├─ endpoint  UNIQUE
├─ p256dh, auth
└─ created_at

AlarmRule
├─ user        → User (CASCADE)
├─ enabled     bool
├─ kind        enum personal | report
├─ timing      enum before_start | days | bizdays
├─ offset      int   before_start=분(1~10080) / days=일(0~30) / bizdays=영업일(1~30)
├─ at_minute   int   0~1439 발송 시각. before_start면 0
├─ telegram, push   bool
├─ shifts      JSON [dawn, normal, dinner, night, slots] (고정 순서로 정렬 저장) 빈 값 = 전부
├─ depts       JSON [부서 코드] (코드순) 빈 값 = 전부. personal이면 반드시 []
└─ types       JSON [직원, 개발자] 빈 값 = 전부. personal이면 반드시 []
   CHECK kind/timing ∈ enum, offset·at_minute 범위, before_start → at_minute=0,
         telegram OR push, personal → depts=[] AND types=[]
   UNIQUE (user, kind, timing, offset, at_minute, shifts, depts, types)

AlarmSent                    발송 기록
├─ rule      → AlarmRule (CASCADE)
├─ date
├─ cell      근무 칸 키(dawn, slot3 …). 보고서형은 "report"
├─ channel   enum telegram | push
├─ content_hash   보낸 내용 요약값
└─ sent_at
   CHECK channel ∈ enum, cell ∈ CELLS ∪ {report}
   UNIQUE (rule, date, cell, channel)
```

- 채널은 유니크 키에서 뺐다: 조건이 같고 채널만 다른 규칙은 한 규칙에서 둘 다 켠다.
- `at_minute`은 NULL 대신 0: SQLite 유니크는 NULL끼리 다르다고 본다.
- JSON 목록은 저장 전에 고정 순서로 정렬(폼·서비스 한 곳에서)해 `[night, dawn]` = `[dawn, night]`.

## 발송 시각 계산 (순수 함수, `duty/alarms/schedule.py`)

`start` = 근무 시작 일시(보고서형은 그날 선택 스케줄 중 가장 이른 시작).

- `before_start`: `start - offset분`
- `days`: `(근무일 - offset일)`의 `at_minute`
- `bizdays`: 근무일에서 평일만 세어 `offset`일 앞선 날의 `at_minute`

발송 창: `send_at <= now < start`. 워커가 꺼져 있다가 켜져도 근무 시작 전이면 보낸다. 시작이 지난 알림은 버린다.

## 알림 내용

대상 판단은 배포된 근무표(`published_days`)의 현재 상태로 한다.

- **개인**: 규칙 주인의 멤버가 그날 그 칸(규칙 `shifts`에 든 칸)에 있으면 1건/칸.
  `[당번 알림] 11/16(월) 새벽당번 06:30~15:30` + `***님, 내일 새벽당번입니다.`
- **보고서형**: 그날 1건. 규칙의 부서·유형·스케줄 조건으로 거른 출근표.
  `[출근표] 11/16(월) — 매칭엔진실·개발자` + 스케줄별 `새벽(06:30~) ***, ***` 줄
- **변경**: 이미 보낸 알림(`AlarmSent`)의 내용이 근무 시작 전에 바뀌면 다시 보낸다.
  개인: 그 칸에서 빠지면 `[당번 변경] … 근무가 취소되었습니다(→ 후임)`. 보고서형: `[출근표 변경]` 차이 줄.
  `content_hash`를 갱신한다.

## 구성 요소

- `duty/alarms/schedule.py` — 발송 시각 계산(ORM 없음).
- `duty/alarms/plan.py` — 근무표 + 규칙 → 지금 보낼 알림 목록(ORM 없는 부분 최대화).
- `duty/alarms/messages.py` — 문구.
- `duty/alarms/telegram.py` — Bot API `sendMessage`(표준 라이브러리 `urllib`).
- `duty/alarms/webpush.py` — `pywebpush`(신규 의존성 1개; VAPID 암호화를 직접 구현하지 않는다). 410/404 응답이면 구독 삭제.
- `duty/services/alarms.py` — 규칙 CRUD·기본 규칙 생성·발송 기록(DB 쓰기는 여기만).
- `manage.py run_alarms` — 1분마다 계획 → 발송 → 기록. systemd 서비스 `duty-alarms.service`(gunicorn과 별도 프로세스). 한 번에 하나만 돌도록 DB 잠금(IMMEDIATE 트랜잭션)으로 발송 기록을 먼저 쓰고 보낸다(중복보다 누락 쪽으로 실패).
- 기본 규칙: User `post_save`(생성 시) + 데이터 마이그레이션(기존 계정).

## 화면

상단 메뉴 "알림 설정"(로그인한 누구나, 자기 것만).

1. 텔레그램 chat_id 입력 + [테스트 발송]. chat_id 확인 방법 안내 문구.
2. [이 기기에서 푸시 받기] / [이 기기 해제] — 서비스 워커 등록·구독 → 서버 저장. 등록된 기기 수 표시. 아이폰은 "홈 화면에 추가" 후에만 가능하다는 안내.
3. 규칙 표: 켬, 종류, 기준(예: "1일 전 18:00", "2시간 전", "1영업일 전 17:00"), 채널, 조건 + [추가]/[수정]/[삭제]. 폼은 종류에 따라 부서·유형 칸을 숨기고, 기준에 따라 "N시간 M분" 또는 "N일 + HH:MM"을 보인다. 중복 규칙은 "같은 규칙이 이미 있습니다" 오류.

PWA: `manifest.webmanifest`, 서비스 워커(`/sw.js`, 루트 범위) — `push` 이벤트에서 알림 표시, 클릭하면 해당 날짜 일별 보기 열기.

## 설정·보안

- 환경변수: `DUTY_TELEGRAM_BOT_TOKEN`, `DUTY_VAPID_PUBLIC_KEY`, `DUTY_VAPID_PRIVATE_KEY`, `DUTY_VAPID_SUBJECT`(mailto:). 없으면 해당 채널만 끄고 화면에 "설정 안 됨" 표시.
- 구독·규칙 API는 로그인 + CSRF. 남의 규칙·구독은 404.
- 웹 푸시는 HTTPS 필요(Tailscale Funnel = HTTPS). 로컬 개발은 `localhost` 예외로 동작.
- 알림 문구에 실명이 들어간다 — 로그에는 남기지 않는다(발송 실패 로그는 규칙 id·채널·상태 코드만).

## 전환 순서

1. 웹앱 배포 → 각자 chat_id·푸시 등록(기본 규칙이 이미 있음).
2. `duty_notifier`의 알림 규칙(`rules`)을 비워 발송 중지, 봇 조회 기능만 유지.
3. `run_alarms` 서비스 시작.

## 테스트

- 시각 계산: 각 기준·경계(주말 건너뛰기, 0일 전, 월요일 근무의 1영업일 전 = 금요일, 장중 칸 시작 시각).
- 계획: 개인/보고서형 대상 판단, 필터 조건, 발송 창, 중복 방지, 변경 재발송·취소.
- 제약: 각 CHECK·UNIQUE가 IntegrityError, CASCADE로 고아 없음.
- 화면: 남의 규칙 접근 404, 중복 규칙 오류, 기본 규칙 생성(신규·기존).
- 발송기: 텔레그램·푸시 클라이언트는 가짜로 바꿔 끼워 검증(외부 호출 없음). 410이면 구독 삭제.
- 브라우저: 설정 화면 1400/390px, 실제 푸시 수신은 수동 확인.

## 개정 1 — Codex 계획 리뷰 반영 (2026-11-10)

아래가 위 본문보다 우선한다.

1. **발송 기록 = 목적지별 시도 기록.** `AlarmSent` → `AlarmDelivery(rule, date, cell, channel, destination, status[sent|failed], attempts, next_attempt_at, content_hash, updated_at)`, UNIQUE `(rule, date, cell, channel, destination)`. destination = 텔레그램 chat_id 또는 `sub:<구독 id>`. **보낸 뒤에 기록**한다: 성공 → `sent`, 실패 → `failed` + 재시도 시각(1·2·4·8…분, 최대 30분, 429/503은 `Retry-After`). 발송 창(근무 시작 전) 안에서만 재시도. 404/410은 구독 삭제, 그 밖의 4xx는 재시도 안 함. 워커는 하나만: systemd `ExecStart`를 `flock -n`으로 감싼다. 발송 직후·기록 직전에 프로세스가 죽으면 드물게 중복될 수 있음을 감수한다.
2. **푸시 endpoint 검증(SSRF 방지).** `https`, 포트·userinfo 없음, IP 리터럴 금지, 호스트가 허용 목록 접미사(`fcm.googleapis.com`, `updates.push.services.mozilla.com`, `push.apple.com`, `notify.windows.com`) 중 하나. `p256dh`·`auth`는 base64url·길이 검사. 다른 사용자의 endpoint를 옮길 때는 키가 같아야 하고 다르면 409.
3. **시간.** `tick(now)`는 aware datetime만 받는다. 순수 계층에는 Asia/Seoul naive로 바꿔 넘기고, DB에는 aware로 저장. 조회 기준 날짜는 `perms.today()`.
4. **사라진 날짜.** 계획 대상 날짜 = 배포 근무표 날짜 ∪ 오늘 이후 발송 기록 날짜. 기록만 남은 날짜는 빈 근무로 보고 개인 취소·보고서 변경을 계산한다.
5. **보고서 마감.** 보고서형 발송 창 끝 = 선택 칸 중 **가장 늦은** 시작(첫 발송 시각 계산은 그대로 가장 이른 시작 기준). 개인은 칸별 그대로. 발송 시각이 이미 칸 시작 이후인 칸은 그 규칙으로는 알림이 없다(화면에 안내).
6. **푸시 옵션.** `timeout=10`, `ttl` = 근무 시작까지 남은 초(최소 60).
7. **길이.** 푸시 본문은 요약 한 줄(보고서형: 날짜·조건·인원수) + 링크, 1000바이트 이내. 텔레그램 본문은 4000자에서 자르고 "…(이하 생략, 웹에서 확인)".
8. **변경 문구.** 개인 취소에 후임이 있으면 표시(`Day.replaced` 역참조). 보고서 변경은 차이 대신 `[출근표 변경]` + 전체 표 재전송.
9. **텔레그램.** chat_id는 양수(개인 채팅)만. [테스트 발송] 응답의 `chat.type == "private"` 확인. 웹앱 전용 봇을 새로 만들기를 권장(기존 `duty_notifier` 봇은 polling 중이라 `getUpdates` 안내와 충돌) — README에 명시.
10. **규칙 수정.** 기준·간격·시각·스케줄·부서·유형이 바뀌면 그 규칙의 오늘 이후 발송 기록을 지운다(새 조건으로 다시 발송). 켬/끔·채널만 바뀌면 유지.
11. **필터 값 검증.** 서비스에서 알 수 없는 스케줄·부서·유형 값이 있으면 `DutyError`. "전체"는 빈 목록(또는 전부 체크)으로만.
12. **서비스 워커.** `push`·`notificationclick` 모두 `event.waitUntil(...)`, 클릭 시 `notification.close()`. 권한 요청은 버튼 클릭 핸들러 안에서. 실제 수신(Chrome, iOS 홈 화면 앱)은 전환 전에 사람이 확인.
13. **기기 관리.** 구독에 `label`(User-Agent 요약)·`created_at` 표시, 기기별 삭제와 [모든 기기 해제]. 등록 시 "로그아웃해도 알림은 계속 오고 잠금 화면에 이름이 보일 수 있음" 안내.
14. **전환 runbook.** `run_alarms --dry-run`(보낼 건수만, 이름 없이), 두 채널 실제 테스트, 매 tick 요약 로그(건수·실패 수), 롤백 = `duty-alarms` 중지 + `duty_notifier` `rules` 복구.
15. **로그.** `rule`, `channel`, 기록 id(`delivery`), HTTP status, attempt만(이름·본문·토큰·endpoint 금지).
16. 발송기는 `duty/alarms/senders.py` 하나.
17. **정리.** tick마다 7일 지난 발송 기록 삭제.

## 개정 2 — Codex 토론 반영 (2026-11-10)

개정 1보다 우선. 계획의 Task 5~8 "최종" 절이 이 내용을 구현한다.

1. 계획·기록을 **목적지 단위**로: `plan()`이 목적지 목록을 받고 `Due.destination`을 낸다. 판정은 목적지별 마지막 **성공** 내용(`AlarmDelivery.last_sent_hash`) 기준. `content_hash`는 마지막 시도 내용. 첫 알림이 실패한 채 배정이 빠지면 취소를 보내지 않는다.
2. backoff는 같은 내용 재시도에만. 내용이 바뀌면 즉시 시도. `Retry-After`는 그대로 따르되 근무 시작을 넘으면 포기. 푸시 401/403은 설정 오류로 보고 일시 실패로 재시도.
3. 개인 hash = `in:`/`out:` + 렌더링된 본문 hash(후임·이름 변화 반영).
4. 푸시 ttl = `max(1, ceil(남은 초))`(`total_seconds`).
5. 기록 정리는 **근무일** 기준 7일.
6. 단일 워커: 명령 내부 `fcntl.flock`(systemd `flock` 대신; 수동 `--once`도 보호).
7. 허용 호스트 비교는 `host == s or host.endswith("." + s)`, 소문자화, 잘못된 포트는 400. Windows WNS는 실제 검증 전까지 제외.
8. 텔레그램은 **[저장 및 테스트]** 하나: private 확인된 chat_id만 저장(`verified_at`), 범위 `1..2^63-1`, 사용자별 30초 쿨다운. 발송은 검증된 chat_id에만.
9. 잘린 텔레그램 본문엔 `DUTY_SITE_URL` 절대 링크.
10. 규칙 수정 시 기록 삭제 조건에 `kind` 포함, 정규화 값 비교, 같은 트랜잭션.
11. 당일 규칙에서 제외되는 칸은 저장 후 구체 안내(일부/전부).

## 개정 3 — 사용자 결정 (2026-11-10)

1. 텔레그램 **자동 연결**: [텔레그램 연결] → `t.me/<봇>?start=<일회용 코드>`(10분) → 봇에서 [시작] → 웹 [연결 확인] → 서버가 getUpdates에서 그 코드의 private 채팅을 찾아 chat_id 저장(검증됨). 웹앱 전용 봇 필수. 직접 입력도 유지.
2. **도움말 페이지**: `/help/telegram/`, `/help/push/` — 화면에서 바로 따라 할 수 있는 단계별 안내. 이후 기능(캘린더 연동)도 같은 형식의 도움말을 둔다.
