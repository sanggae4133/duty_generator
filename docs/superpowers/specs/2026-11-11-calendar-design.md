# 캘린더 구독(ICS) 설계

사용자 요청: Google 캘린더에 "자기 토큰 비슷한 것"을 넣으면 내 근무가 자동으로 연동되고, 따라 할 수 있는 상세 도움말이 있을 것.
결정 과정: Claude 초안 → Codex 토론 2라운드 "최종 합의"(2026-11-11).

## 방식

사용자별 **비밀 ICS 구독 주소**. 사용자는 주소를 한 번 복사해 Google 캘린더(PC 웹 "URL로 추가"), 아이폰 캘린더, Outlook에 등록한다. 이후 그 캘린더 앱이 주기적으로 다시 읽어 자동 갱신된다.

- Google OAuth·Calendar API는 쓰지 않는다(Cloud 프로젝트·앱 검증·refresh token 보관·테스트 사용자 제한 회피). 즉시 반영이 필요하면 텔레그램·푸시 알림을 쓴다.
- 갱신 주기는 캘린더 앱이 정한다(Google은 보장 없음, 경험상 여러 시간). 도움말 첫머리에 알린다.

## 데이터

`CalendarFeed`(마이그레이션 0009)
- `user` OneToOne(User, CASCADE, related_name="calendar_feed")
- `token_hash` CharField(64, unique) — `sha256(token).hexdigest()`
- `created_at` DateTimeField(auto_now_add)

토큰은 `secrets.token_urlsafe(32)`(43자). **원문은 저장하지 않는다.** 발급·재발급 POST 응답에서 한 번만 보여 준다(세션·messages·로그에 원문 금지). 다시 보려면 재발급. 끄기 = 행 삭제. 재발급 = 같은 행의 해시를 교체. unique 충돌 시 2회까지 재생성.

## 피드

`GET|HEAD /calendar/<token>.ics` — 로그인 불필요, `ForcePasswordChangeMiddleware`에서 명시적으로 통과.

- 토큰이 `[A-Za-z0-9_-]{43}`(ASCII)가 아니면 해시 계산 없이 404. 해시로 행이 없으면 404(이전 토큰·끈 경우 포함, 사유 구분 없음).
- 행은 있지만 `User.is_active=False`, 연결된 Member 없음, `Member.is_active=False`(스태프 예외 없음 — 피드는 본인 근무용) → **빈 VCALENDAR 200**(구독 앱이 기존 일정을 지우도록).
- 내용: 본인 배정만. `roster.published_days(perms.today() - 90일, None)`의 `day.members[cell]`에서 이 Member의 이름(전체 고유)이 있는 칸. 출근조와 관제는 각각 별개 이벤트(같은 날 둘 다면 2개).
- 응답 헤더: `Content-Type: text/calendar; charset=utf-8`, `Cache-Control: private, no-cache`, `Referrer-Policy: no-referrer`, `ETag: "<본문 sha256>"`. `If-None-Match` 일치 시 304(Django `get_conditional_response` 사용, 304·HEAD에도 같은 헤더). Last-Modified 없음.
- 로그에 토큰·요청 경로를 남기지 않는다.

### ICS 형식 (직접 작성, `duty/ics.py` 순수 모듈)

- CRLF, 각 줄 75옥텟 이하로 접기(continuation 공백 포함 계산, UTF-8 멀티바이트 경계 보존). TEXT 값만 이스케이프(`\\`, `;`, `,`, 줄바꿈). URI 값은 이스케이프하지 않는다.
- VCALENDAR: `VERSION:2.0`, `PRODID:-//duty_generator//calendar//KO`, `CALSCALE:GREGORIAN`, `NAME`·`X-WR-CALNAME` = "IT 당번(내 일정)", `REFRESH-INTERVAL;VALUE=DURATION:PT6H`, `X-PUBLISHED-TTL:PT6H`. `METHOD` 없음.
- VEVENT: `UID:<YYYYMMDD>-<cell>-<member_pk>@duty-generator`, `DTSTAMP`, `DTSTART`/`DTEND`(UTC `...Z`, `shifts.cell_times`를 Asia/Seoul로 해석 후 변환), `SUMMARY`, `TRANSP:TRANSPARENT`, `STATUS:CONFIRMED`, `SITE_URL`이 있으면 `URL:<SITE_URL>/me/`와 `DESCRIPTION:근무표: <SITE_URL>/me/`. `SEQUENCE`·`VALARM` 없음.
- SUMMARY: 출근조 `"<출근조 라벨> <시작>~<끝>"`(라벨은 `cell_label`), 관제 `"관제 <cell_label>"`.
- DTSTAMP: 피드 공통 revision = max(포함된 회차들의 `published_at`, 포함된 (회차, 날짜)의 `ChangeLog.at`), UTC. `published_at`이 없는 PUBLISHED 회차의 날짜는 경고 로그(회차 id만) 후 제외. 이벤트가 없으면 VEVENT 없음.

## 설정 검증

`DUTY_SITE_URL`이 비어 있지 않으면 시작 시 검증: 스킴 `https`(DEBUG에서는 `http` 허용), host 있음, 제어문자 없음, query·fragment 없음. 어기면 `ImproperlyConfigured`.

## 화면

- `/alarms/`에 "캘린더 구독" 영역: 미발급 → [구독 주소 만들기]; 발급됨 → 발급일, [주소 재발급](확인 문구: 기존 구독 삭제 후 새 주소 등록 필요), [구독 끄기]. 모두 POST.
- 발급·재발급 응답: 같은 화면에 읽기 전용 입력란 + [복사] 버튼으로 주소 1회 표시(링크로 만들지 않음), `Cache-Control: private, no-store`, `Referrer-Policy: no-referrer`. "이 화면을 벗어나면 다시 볼 수 없음, 안 보이면 재발급" 안내.
- Member가 연결되지 않은 계정에는 영역 대신 안내 문구.
- 메뉴 이름 "알림 설정" → "알림·캘린더".

## 도움말 `/help/calendar/`

1. 변경이 즉시 반영되지 않을 수 있음(갱신 시점은 캘린더 앱이 정함) — 즉시 확인은 텔레그램·푸시
2. 주소는 비밀번호처럼: 메신저·메일로 보내지 말 것
3. Google 캘린더 PC 웹: 다른 캘린더 + → URL로 추가 → 붙여넣기 → 캘린더 추가
4. 휴대폰 Google 캘린더 앱에서는 새 구독 추가 불가 — PC에서 추가 후 같은 계정으로 확인(앱 설정에서 해당 캘린더 동기화 켜기)
5. 아이폰: 캘린더 앱 → 캘린더 → 캘린더 추가 → 구독 캘린더 추가
6. Outlook 웹: 캘린더 → 캘린더 추가 → 웹에서 구독("파일 가져오기"는 자동 갱신 안 됨)
7. 일정이 안 보일 때(기다리기, 주소 전체 복사 확인, 배포된 회차만, 지난 90일까지만)
8. 주소 유출·재발급: 기존 구독 캘린더 삭제 → 재발급 → 새 주소 등록
9. 텔레그램·푸시 도움말 링크

## 범위 밖

부서·전체 피드(필요하면 관리자 전용 별도 기능), OAuth 직접 쓰기, 최근 요청 시각 기록, 레이트리밋(256비트 토큰, Funnel 뒤 IP 공유).
