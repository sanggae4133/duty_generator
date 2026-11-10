# duty_generator

IT 당번표 웹앱(Django). 구글 시트 + Apps Script 당번표를 완전히 대체한다. 설계: `docs/superpowers/specs/2026-11-09-duty-generator-design.md`(구속력 있는 기준), 구현 계획: `docs/superpowers/plans/2026-11-09-duty-generator.md`.

## 소통 규칙
- 사용자와의 대화, 진행 보고, 질문, 최종 보고는 **한국어**로 한다.
- 화면에 보이는 모든 문구와 오류 메시지는 한국어로 쓴다(사용자가 정한 영문 라벨은 그대로 둔다. 예: 근무 변경 팝업의 From/To).
- 커밋 메시지는 `feat:`/`fix:`/`docs:`/`style:` 접두어 + 한국어 요약.
- 작업 중 작업 트리에 생긴 사용자의 수정은 의도된 것으로 보고 그대로 살려서 이어간다(따로 빼두거나 되돌리지 않는다).

## 개발 명령
```bash
.venv/bin/pytest -W error                      # 전체 테스트, 경고 0개 유지
DUTY_DEBUG=1 .venv/bin/python manage.py migrate
DUTY_DEBUG=1 .venv/bin/python manage.py runserver
DUTY_DEBUG=1 .venv/bin/python manage.py import_sheets --dry-run   # 시트 이관 확인(실제 가져오기는 1회만)
```
- 테스트 설정은 `config.test_settings`. 모든 변경은 테스트를 먼저 쓰고(실패 확인) 구현한다.
- 화면 변경은 테스트 통과만으로 끝내지 말고 브라우저(PC 1400px, 모바일 390px)에서 직접 확인한다.

## 구조 원칙
- 순수 로직은 ORM 없이: `duty/shifts.py`(근무조·관제 상수), `duty/generator.py`(장중관제 생성), `duty/csv_io.py`.
- DB를 바꾸는 규칙(권한, 지난 날짜, ChangeLog)은 전부 `duty/services/`를 거친다. 뷰에서 모델을 직접 고치지 않는다.
- "오늘"은 항상 `duty.perms.today()`로 구한다(`from . import perms` 후 `perms.today()`; `from .perms import today` 금지 — 테스트에서 monkeypatch).
- 시간대 `Asia/Seoul`, `USE_TZ=True`. DB는 SQLite(WAL, `transaction_mode=IMMEDIATE`).
- 정해진 값만 받는 칸은 `choices`(TextChoices) + DB `CheckConstraint`를 같이 건다(SQLite엔 enum 타입이 없음). 기록을 남겨야 하는 FK는 `PROTECT`.
- 정적 파일(htmx, Pico.css)은 CDN이 아니라 `duty/static/vendor/`에서 직접 서빙한다.

## 도메인 기준
- 칸(cell) 키 14개: 출근조 `dawn`/`normal`/`dinner`/`night`, 관제 `slot0`~`slot9`. ChangeLog·화면·API가 같은 키를 쓴다.
- 대상 날짜는 회차 기간의 월~금(휴장일 처리 없음).
- 출근조는 한 사람이 하루 하나만(DB 제약). 관제는 한 사람이 하루 여러 칸 가능(대신 서기, 경고만). 자동 생성은 한 사람에게 하루 한 칸만 배정한다.
- 관제 자격: `type == "개발자"`이고 그날 그 칸의 자격 출근조에 있음. 생성 카운트 풀은 기간 중 한 번이라도 자격 있는 개발자만. 목표 편차 2 이하.
- 지난 날짜(오늘 이전) 수정은 어드민(`is_staff`)만. 오늘·미래는 로그인한 누구나.
- 근무 변경: 출근조 칸은 교체·추가·제거, 관제 칸은 교체만, 맞교환은 같은 종류끼리. 동시 수정은 먼저 저장한 쪽이 반영되고 늦은 쪽은 오류.
- ChangeLog `before`/`after`: 교체 `A>B`, 추가 `+B`, 제거(취소선). `replaced`는 그 칸에 그 사람을 들인 마지막 기록의 before(노티파이어 `Assignment.replaced`와 같은 의미 — 바꾸면 노티파이어가 깨진다).
- 배포 덮어쓰기: 다른 배포 회차의 `[S, B 종료일]` 행을 지우고 B의 `S` 이전 행을 지운다. ChangeLog는 남긴다.
- 멤버 이름은 전체에서 고유하고 `>`, `,`, 줄바꿈을 쓸 수 없으며 `+`로 시작할 수 없다(체인·CSV 문법 문자).
- 어드민: 웹 화면 어드민 기능은 `is_staff`, Django 관리 화면(멤버·계정 발급·잠금 해제)은 슈퍼유저(어드민 1~2명 가정).

## 보안·개인정보
- Tailscale Funnel로 공개되는 앱이다. 로그인 잠금은 사용자명 기준, API는 `Authorization: Bearer <DUTY_API_TOKEN>`(빈 토큰 거부, `hmac.compare_digest`).
- 실명 데이터를 커밋하지 않는다. 테스트·fixture는 가상의 이름이나 멤버 코드만 쓴다. 보고서·로그에 실명을 옮길 때는 `***`로 가린다.
- 비밀값은 환경변수(`DUTY_*`)로만 받는다.

## 연동
- `../duty_notifier`(FastAPI 알림봇)가 `/api/assignments`를 읽는다. 응답 형식(`date`, `shift`, `name`, `replaced`)을 바꾸면 노티파이어도 같이 바꿔야 한다.

## 작업 방식
- `main`에서 직접 작업하지 않는다. 브랜치를 따서 작업하고 PR로 합친다. push·PR 생성·머지는 Claude가 직접 해도 된다(2026-11-10 사용자 허용).
- 계획·구현 각 단계와 최종 리뷰는 Codex(`codex exec`, 읽기 전용) 리뷰를 받고 여러 번 토론해 최종 결정한다. Codex 사용량 한도에 걸리면 재설정 시각까지 기다렸다가 이어서 요청한다. Codex에는 DB 파일·`.superpowers/`를 열지 말라고 지시한다(실명).
