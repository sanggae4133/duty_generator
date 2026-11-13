# duty_generator

NXT 당번표 웹앱(Django). 구글 시트 + Apps Script 당번표를 완전히 대체한다. **작업 전에 `docs/ARCHITECTURE.md`를 읽는다**(구조·도메인 규칙의 기준). 기획 `docs/OVERVIEW.md`, 설계 철학·결정 기록 `docs/PRINCIPLES.md`, 운영 `docs/OPERATIONS.md`, 개발 `docs/DEVELOPMENT.md`. 동작을 바꾸면 해당 문서도 같은 PR에서 고치고, 중요한 결정은 PRINCIPLES.md "결정 기록"에 한 줄 더한다.

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
DUTY_DEBUG=1 .venv/bin/python manage.py run_worker   # 작업자(알림·백업·상태 점검), 필요할 때만
```
- 설치(`pip install -e .`) 없이 저장소 루트에서 돈다: `pip install -r requirements.lock -r requirements-dev.txt`. 라이브러리 목록은 `requirements.in`.
- 테스트 설정은 `config.test_settings`. 모든 변경은 테스트를 먼저 쓰고(실패 확인) 구현한다.
- 화면 변경은 테스트 통과만으로 끝내지 말고 브라우저(PC 1400px, 모바일 390px)에서 직접 확인한다.

## 꼭 지킬 것 (자세한 이유는 docs/ARCHITECTURE.md)
- DB를 바꾸는 규칙(권한, 지난 날짜, ChangeLog, 상태 기록)은 전부 `duty/services/`. 뷰·명령에서 모델을 직접 고치지 않는다.
- ORM 없는 순수 모듈: `shifts`·`generator`·`csv_io`·`ics`·`alarms/`(senders 제외). 시각은 인자로 받는다.
- "오늘"은 `from . import perms` 후 `perms.today()`(`from .perms import today` 금지 — 테스트에서 monkeypatch).
- 정해진 값 칸은 `choices` + DB `CheckConstraint`. 기록을 남길 FK는 `PROTECT`.
- 경로는 `settings.DATA_DIR`·`DB_PATH`·`BACKUP_DIR`·`LOG_DIR`에서만. 개발·운영 차이는 `.env` 값으로만. 셸 스크립트·타이머·새 deploy 파일을 만들지 않는다(deploy/ 는 systemd 유닛 2개와 nginx 설정 하나뿐).
- 정적 파일(htmx, Pico.css)은 CDN 말고 `duty/static/vendor/`.
- 테스트에서 텔레그램·푸시 실제 호출 금지(`senders` monkeypatch). 진짜처럼 보이는 비밀값 문자열을 테스트에 쓰지 않는다(런타임에 조립).
- 마이그레이션 파일은 지우지 않는다(운영 DB를 올리는 유일한 길).

## 보안·개인정보
- 실명 데이터를 커밋하지 않는다. 테스트·fixture는 가상의 이름이나 멤버 코드만 쓴다. 보고서·로그에 실명을 옮길 때는 `***`로 가린다.
- 로그·화면·메시지에 남기지 않는다: 봇 토큰·푸시 개인키 원문(관리 화면은 끝 4자리), 캘린더 토큰·피드 경로, 텔레그램 연결 코드, 푸시 endpoint, 메시지 본문, 실명.
- 설정: 서버 기동 값(`DUTY_*`)은 루트 `.env`(견본 `.env.example`, 환경변수가 우선, 테스트는 읽지 않음). 봇 토큰·푸시 키·장애 알림 chat_id는 DB `AlarmSettings`(`services.alarm_settings.current()`).

## 작업 방식
- `main`에서 직접 작업하지 않는다. 브랜치를 따서 작업하고 PR로 합친다. push·PR 생성·머지는 Claude가 직접 해도 된다(2026-11-10 사용자 허용).
- 계획·구현 각 단계와 최종 리뷰는 Codex(`codex exec`, 읽기 전용) 리뷰를 받고 여러 번 토론해 최종 결정한다. Codex 사용량 한도에 걸리면 재설정 시각까지 기다렸다가 이어서 요청한다. Codex에는 DB 파일·`data/`·`.superpowers/`를 열지 말라고 지시한다(실명).
