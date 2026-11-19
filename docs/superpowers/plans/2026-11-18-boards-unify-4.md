# 근무표 통합 4단계(근무표 설정: 사람 칸) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 근무표 관리자가 [근무표 설정](`/settings/?board=<code>`) 맨 위 "사람" 칸에서 그 근무표 부서 사람을 더하고, 이름·구분을 고치고, 퇴사(연결 모두 끊음, 남은 근무를 보이고 한 번 더 묻기)·다시 재직시키고, 계정을 발급·초기화(연결은 남김, 여럿 한 번에, 임시 비밀번호는 응답 본문의 결과 상자에만)한다. 관리자 계정(어느 근무표든)·슈퍼유저·나 자신은 대상이 아니다(슈퍼유저가 관리 화면에서). 임시 비밀번호는 헷갈리는 글자 없는 10자로 바뀐다(관리 화면 액션도).

**Architecture:** 계정 규칙은 `duty/accounts.py`(`temp_password`, `issue_account(user, revoke_links=True)`, 새 `deactivate`). DB 쓰기는 `duty/services/board_settings.py` 에 사람 함수 다섯(`add_person`·`set_person`·`set_active`·`issue`, 읽기 `future_cells`)과 대상 규칙 한 곳(`locked_ids`·`_person`)을 더한다(3단계의 `_require_admin`·`_dept`·`_audit`·`NeedsConfirm` 재사용). 화면은 3단계의 `duty/views/board_settings.py`·`board_settings.html` 에 `#people` 칸과 `ACTIONS` 다섯을 더한다. 추가·고치기 오류와 퇴사 확인과 발급 결과는 redirect 없이 그 자리에서 다시 그리고, 나머지는 3단계처럼 칸 메시지 + redirect.

**Tech Stack:** Python 3.12, Django 5.2, SQLite, pytest + pytest-django, Pico.css. 새 의존성 없음. 마이그레이션 없음.

**Spec:** `docs/superpowers/specs/2026-11-17-boards-unify-design.md`(Codex 합의본). 이 계획 = 12절 "4. 근무표 설정(사람)". 참고: 3절 "사람 다루기"·5.7(계정)·6.2(사람 함수 표와 대상 규칙·공통 규칙)·7.1(바로가기 [사람])·7.2 의 1번(사람 칸)·7.3(사람 검사)·8(권한)·10.4(4단계 메모)·11(권한·범위·퇴사 두 번째 확인·계정)·13(문서)·14(임시 비밀번호 노출·실명 아이디).

## 계획에서 정한 것 (설계가 정하지 않았거나 해석이 필요한 곳, 컨트롤러 검토용)

설계의 4단계 몫을 네 관점(개발자·계획자·디자이너/HCI(시력이 좋지 않은 60세 가까운 관리자)·보안)으로 다시 읽고 정한 것. **⚑ 표시는 설계의 글자와 다르게 하는 것**이고 까닭을 함께 적는다(동작을 넓히는 것은 없다).

1. ⚑ **일괄 발급 체크박스는 "발급 전"·"첫 로그인 대기" 줄에만**(설계 7.2 "맨 앞에 선택 체크박스"를 좁힘). "사용 중" 줄을 체크해 [선택한 사람 계정 발급]을 누르면 확인창 없이 그 사람 비밀번호가 바뀌고 모든 기기에서 로그아웃된다(일괄 폼에는 사람마다 확인창이 없다). 쓰는 중인 사람은 [고치기] 안 [비밀번호 초기화](확인창 있음)로만. 서비스 `issue` 는 상태를 가리지 않는다(같은 함수를 초기화 버튼도 쓴다) — 화면 편의이고 막힌 것은 아니다. 같은 까닭으로 줄의 [계정 발급]은 "발급 전" 줄에만, [비밀번호 초기화]는 "발급 전"이 아닌 줄에만 둔다.
2. ⚑ **`set_active` 의 퇴사 뒤 `_keep_active_admin` 검사는 두지 않는다**(설계 6.2 "검사는 한 곳에 둔다"). `_person` 이 관리자 계정(어느 근무표든)을 이미 대상에서 빼므로 그 검사는 닿을 수 없는 코드이고 테스트도 쓸 수 없다. 재직 관리자 한 명 이상 규칙의 한 곳은 그대로 `boards.left_without_admin`(관리자 빼기·관리 화면 사용자 편집·지우기)이다. 대상 규칙을 넓히는 날 함께 더한다.
3. ⚑ **`set_person` 은 구분 칸이 없는 근무표(`prefs.has_types` 거짓)에서 구분을 그대로 둔다**(설계 "구분 칸 규칙도 같다(없으면 '직원')"는 추가 때만). 고치기마다 "직원"을 넣으면 그 근무표에 개발자로 들어온 사람(인사이동 등)의 구분이 알림 없이 바뀐다.
4. ⚑ **`future_cells` 는 칸 키 대신 칸 이름을 돌려준다**: `list[(date, 칸 이름, period, 단계 이름)]`. 쓰는 곳(퇴사 확인·퇴사 뒤 목록)이 모두 이름을 보인다. 그 근무표 회차의 행만(다른 근무표 회차 이름이 이 관리자에게 보이지 않게). "오늘 이후"는 오늘을 넣는다(`date >= perms.today()`). 배포 근무는 그날의 주인 회차(`boards.owners`)의 행만(덮어쓰인 옛 배포 행은 뺀다), 배포 전 회차(작성 중·취합 중·마감·생성됨)는 행 전부. 사유가 붙은 행도 센다(칸에 이름이 있으니 바꿔야 한다).
5. **대상 규칙 한 곳 = `board_settings.locked_ids()`**(슈퍼유저 ∪ 어느 근무표든 관리 그룹 멤버, 한 쿼리) + `_person(by, board, user)`(트랜잭션 안에서 다시 읽고, 부서 없음·다른 근무표 부서·나 자신·`locked_ids` 이면 `PermissionDenied`). 화면도 같은 `locked_ids` 로 줄을 잠근다: 슈퍼유저 줄도 "관리자 계정은 슈퍼유저에게"로 보인다(문구 하나, 슈퍼유저도 관리 화면을 쓰는 계정이라 뜻이 맞는다). 나 자신은 관리자라 늘 잠긴다.
6. **퇴사한 사람의 발급은 막는다**(설계에 없음): `issue` 가 `DutyError("퇴사한 사람은 먼저 [다시 재직]을 누르세요.")`. 로그인할 수 없는 계정에 비밀번호만 만들어 1:1 로 전하는 헛일을 막는다. 같은 상태로 바꾸는 `set_active`(이미 퇴사·이미 재직)도 `DutyError`("이미 퇴사 처리된 사람입니다."/"이미 재직 중인 사람입니다.") — 두 번 눌러 기록이 두 줄 남지 않게.
7. **다음 빈 아이디** `next_username(board)` = `<근무표 code><두 자리 번호>`(`add_board` 와 같은 꼴) 가운데 대소문자 구분 없이 아직 없는 가장 작은 번호. 퇴사자도 계정이 남아 있어 번호가 다시 쓰이지 않는다. code 는 `Board.clean` 이 `[a-z][a-z0-9]{0,15}` 로 지켜 늘 아이디 규칙에 맞는다(따로 막을 것 없음).
8. **추가·고치기 오류는 redirect 없이 다시 그린다**(보낸 값 그대로). 오류 글은 칸 옆이 아니라 그 폼 바로 위 한 줄에 "칸 이름: 글" 꼴로(설계 7.3 "칸 옆"의 해석): 서비스가 설계 6.2 대로 평범한 인자를 받고(폼을 넘기지 않음) 폼이 칸 두세 개라 한 줄로 충분하다. 이름이 겹치면 Django 기본 문구 대신 "이름: 같은 이름이 이미 있습니다(퇴사한 사람·다른 근무표 포함). 동명이인은 이름 뒤에 부서나 숫자를 붙여 구별합니다." — 퇴사자 이름과 겹쳐 막히는 일을 알아듣게.
9. **퇴사 확인은 redirect 없이 그 줄 아래에**(펼친 [고치기] 안 위험 구역). 확인 값(`confirm`)은 화면이 보여 준 목록의 칸 수(뷰가 `future_cells` 를 다시 읽어 그린 줄 수)이고 [그래도 퇴사 처리] 버튼에만 싣는다. 퇴사가 끝나면 redirect + 칸 메시지 둘(성공 글, 남은 근무가 있으면 링크 목록). 링크 목록은 `format_html` 로 만든 안전한 글이라 세션 메시지(`SessionStorage`, Django 가 `SafeData` 표시를 지킨다)에 그대로 실어도 이스케이프된 회차 이름만 들어간다.
10. **결과 상자**: 사람 칸 제목·칸 메시지 바로 아래, 빨간 두꺼운 테두리, 사람마다 `<code class="pw">`(1.6rem, 글자 사이 띄움, 합자 끔), 이름 순. [닫기]는 설정 화면 GET 링크(`?board=<code>#people`). 상자 글에 설계의 문장 + "새로고침하지 마세요(새 비밀번호가 다시 만들어지고 앞 비밀번호는 쓸 수 없게 됩니다)". 응답은 미들웨어가 `Cache-Control: private, no-store` 를 붙여 뒤로 가기로 다시 보이지 않는다(테스트로 본다). 복사 버튼은 두지 않는다(클립보드에 남는 것을 피하고, 받아 적어 1:1 로 전하는 지금 방식 그대로).
11. **누르면 꺼지는 버튼**은 `onsubmit` 에서 `event.submitter` 를 끈다(`if (event.submitter) event.submitter.disabled = true` — 오래된 브라우저에서는 그냥 제출된다). 끄는 버튼에는 `name`/`value` 가 없어 보내는 값이 달라지지 않는다. 일괄 발급 체크박스는 표 안에 있고 줄마다 다른 폼(고치기·발급)이 있어 폼을 겹칠 수 없으므로, 표 밖의 빈 폼 `id="issue-many"` 에 HTML `form` 속성으로 묶는다(JS 없음).
12. ⚑ **줄의 `<summary>` 글은 "고치기 · 비밀번호 · 퇴사"**(설계 "고치기"). 비밀번호 초기화·퇴사 버튼이 그 안에 있는데 "고치기"만 보이면 잊은 비밀번호를 찾는 관리자가 버튼을 찾지 못한다.
13. **`LogEntry`·로그 동작 이름**: "사람 추가"·"이름·구분 고치기"·"퇴사"·"다시 재직"·"계정 발급"·"비밀번호 초기화"(발급마다 사람 한 줄, 그 사람의 발급 전 상태로 고른다). `object_repr` = 아이디. `action_flag` 는 3단계 `_audit` 그대로 `CHANGE`(사람 추가도 — 함수 하나로 같은 꼴). 비밀번호·실명은 넣지 않는다.
14. **퇴사는 그룹을 건드리지 않는다**(설계 5.7 그대로: 재직·비밀번호·캘린더·텔레그램·푸시만). 입력 담당자·관리자 목록에는 "(퇴사)"로 남고 3단계 [빼기]로 뺀다. 관리자 계정은 애초에 대상이 아니다.
15. **사람 표 순서**: 부서 순서(`order`) → 부서 코드 → 이름. 퇴사자는 표 아래 접힌 `<details id="departed">`("퇴사한 사람 N명"). 퇴사한 관리자 계정 줄도 [다시 재직] 대신 "관리자 계정은 슈퍼유저에게".
16. **390px**: `max-width: 40rem` 미디어 쿼리에서 표를 카드로(머리 줄 숨김, `tr`·`td` 를 블록으로, 체크·이름·아이디는 한 줄, 나머지는 `data-label` 을 앞에 붙여 한 줄씩). 체크박스·[고치기]·버튼은 누를 자리 44px 이상. 사람 칸에는 진한 버튼을 두지 않는다(설정 화면의 진한 버튼은 3단계 근무 정의와 부서 칸의 큰 버튼 하나 그대로): [계정 발급]·[선택한 사람 계정 발급]·[사람 추가]·[저장]은 테두리, [비밀번호 초기화]·[퇴사]는 빨간 테두리(`button.danger-btn`, 펼친 [고치기] 안 `section.danger`).
17. **관리 화면 액션은 코드가 그대로**: `issue_account(u)`(기본 `revoke_links=True`)를 지금처럼 부르므로 연결을 끊고, 새 비밀번호 모양만 같이 바뀐다. 세션 메시지로 비밀번호를 보이는 지금 방식도 그대로(설계 7.2 가 받아들임).
18. **첫 발급 판단**(설계 5.7 그대로): `alarms.create_defaults` 가 이미 규칙이 있으면 만들지 않으므로, `last_login` 조건이 실제로 막는 것은 "본인이 기본 규칙을 지운 뒤 퇴사·다시 재직하면 규칙이 되살아나는 일"이다. 그 경우로 테스트한다.
19. **받아들인 위험(PRINCIPLES 에 적는다)**: 근무표 관리자가 사람의 비밀번호를 초기화하면 그 사람으로 로그인할 수 있다. 막지 않고 `LogEntry`·로그 한 줄로 드러내며, 본인은 다음 로그인 때 비밀번호가 바뀐 것을 안다(설계 8 "계정을 만드는 권한을 근무표 관리자에게 준 것은 받아들인 위험").
20. **테스트 파일**: 서비스 `tests/test_board_settings_people.py`, 화면 `tests/test_views_board_settings_people.py`(둘 다 새 파일, 3단계 파일처럼 작은 픽스처를 복사), 계정 `tests/test_auth.py` 맨 끝. 설정 화면은 스냅샷에 넣지 않는다. 바뀌는 스냅샷은 `help-admin` 하나(Task 6).

## Global Constraints

- **스냅샷 규칙은 그대로**: `tests/snapshots/*.html` 은 Task 6 에서 `help-admin.html` 하나만 다시 쓴다(`DUTY_SNAPSHOT_WRITE=1` 실행은 다시 쓴 뒤 일부러 실패하고, 변수 없이 다시 돌려 통과해야 한다. 값은 정확히 `"1"`). Task 1~5 는 기준을 고치지 않고 통과한다. IT 알림 문구·hash(`tests/test_alarm_texts_it.py`)는 고치지 않고 통과한다.
- 각 작업이 끝난 시점에 `.venv/bin/pytest -W error -q` 전체가 통과한다(경고 0개). 기대 테스트 수는 참고값(출발점 `feat/boards-unify-3` 8ec03ad **1380 passed**).
- TDD(테스트를 먼저 쓰고 실패를 확인한 뒤 구현). DB 를 바꾸는 규칙은 `duty/services/`(사람·계정은 `board_settings` → `accounts`). 뷰는 모델을 직접 고치지 않는다. 순수 모듈(`shifts`·`generator`·`csv_io`·`ics`·`alarms/`(senders 제외)·`market_days`)에는 ORM 없음.
- "오늘"은 `from .. import perms` 후 `perms.today()`(테스트는 `fixed_today` 로 monkeypatch). 마이그레이션 없음: 작업마다 `DUTY_DEBUG=1 DUTY_ENV_FILE= DUTY_DATA_DIR=$(mktemp -d) .venv/bin/python manage.py makemigrations duty --check --dry-run` → "No changes detected in app 'duty'"(끝나면 그 임시 폴더를 지운다).
- **비밀값·실명**: 임시 비밀번호는 응답 본문에만(세션·메시지·DB 평문·로그·`LogEntry` 없음). 로그·`LogEntry`·메시지 기록에는 아이디·근무표 code 만. 테스트는 비밀번호 문자열을 적지 않고 발급 결과(응답·반환값)를 그대로 쓴다. 테스트 이름은 가상("가상하나" 등). `data/`, DB 파일, `.superpowers/`, `.env`, 홈의 명단 파일은 열지 않는다. 텔레그램·푸시 실제 호출 없음(이 단계는 보내는 코드를 부르지 않는다).
- 화면 문구·오류 메시지는 한국어. 커밋 메시지는 `feat:`/`fix:`/`docs:`/`style:` + 한국어 요약, 끝에 아래 두 줄:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
  ```
- 새 deploy 파일·셸 스크립트·타이머 없음. 정적 파일은 CDN 없이(새 CSS 는 템플릿 안 `<style>`).
- 화면을 바꾸는 작업(Task 3·4·5·6)은 Task 7 의 준비대로 띄운 가짜 데이터에서 PC 1400px·휴대폰 390px, 글씨 **아주 크게**(오른쪽 위 [가] 두 번), **다크 모드**(오른쪽 위 ◐)로 본다. 모든 브라우저 단계에서 콘솔 `document.documentElement.scrollWidth > innerWidth` 가 `false`. 누름 영역 44px 이상.
- PR 은 4단계 문서(ARCHITECTURE·OPERATIONS·OVERVIEW·PRINCIPLES 결정 기록)를 같은 PR 에서 고친다(Task 6). 계획·구현·최종 Codex 리뷰(`codex exec`, 읽기 전용, DB 파일·`data/`·`.superpowers/` 를 열지 말라고 지시)를 받고, **계정 발급(비밀번호·연결)은 보안 관점 리뷰를 따로 요청한다**(설계 12절 "3·4 를 나눈 까닭"). 테스트 결과 확인과 `gh pr merge` 를 한 명령으로 잇지 않는다.

## 작업 순서

브랜치: `feat/boards-unify-4`(3단계 브랜치 `feat/boards-unify-3` 위, 또는 3단계 머지 뒤 main 에서). PR 제목: `feat: 근무표 설정 사람 칸(추가·고치기·퇴사·다시 재직·계정 발급과 초기화, 근무표 통합 4단계)`.

| Task | 내용 | 테스트 수(참고) |
|---|---|---|
| 1 | `accounts.py`: `temp_password`(헷갈리는 글자 없는 10자), `issue_account(user, revoke_links=True)`, 첫 발급 = 비밀번호 없음 + 로그인한 적 없음, `deactivate` | 1386 |
| 2 | `board_settings.py` 사람 함수: `locked_ids`·`_person`(대상 규칙), `next_username`, `add_person`·`set_person`·`future_cells`·`set_active`(두 번째 확인)·`issue`, 기록 | 1400 |
| 3 | 사람 칸 1: 바로가기 [사람], 읽기 표(계정 상태·관리자 계정 줄), 줄마다 [고치기], 사람 추가(다음 빈 아이디), 390px 카드 | 1404 |
| 4 | 사람 칸 2: 퇴사(그 줄 아래 남은 근무 목록과 [그래도 퇴사 처리], 퇴사 뒤 링크 목록)·퇴사자 목록·[다시 재직] | 1405 |
| 5 | 사람 칸 3: [계정 발급]·[비밀번호 초기화]·[선택한 사람 계정 발급], 결과 상자(응답에만), 누르면 꺼짐, 보안 테스트(IDOR·관리자 계정·로그·세션·`LogEntry`·no-store) | 1409 |
| 6 | 글 도움말 사람 부분 + 스냅샷(`help-admin`) + 문서(ARCHITECTURE·OPERATIONS 4단계 메모·순서·공지·OVERVIEW·PRINCIPLES 두 줄) | 1409 |
| 7 | 브라우저 확인(가짜 데이터 임시 DB, 1400px·390px·다크·아주 크게) | — |

---

### Task 1: `accounts.py` — 임시 비밀번호·초기화의 연결·첫 발급·퇴사

> 범위: 설계 5.7 전부. 관리 화면 액션은 코드가 그대로이고(`issue_account(u)` = 연결 끊음) 비밀번호 모양만 바뀐다.

**Files:**
- Modify: `duty/accounts.py`
- Test: `tests/test_auth.py`(맨 끝에 더함)

**Interfaces:**
- Consumes: `calendar.revoke`, `alarms.clear_telegram`, `alarms.delete_all_subscriptions`, `alarms.create_defaults`, axes `reset`
- Produces:
  - `accounts.ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"`, `accounts.temp_password() -> str`(10자, `secrets.choice`)
  - `accounts.issue_account(user, revoke_links: bool = True) -> str`: 첫 발급 = `not user.has_usable_password() and user.last_login is None` 이면 기본 알림 규칙, 아니면 `revoke_links` 일 때만 연결 끊기
  - `accounts.deactivate(user) -> None`: 재직 끔 + 쓸 수 없는 비밀번호 + 연결 끊기(Task 2 `set_active` 가 쓴다)

- [ ] **Step 1: 실패 테스트를 쓴다** — `tests/test_auth.py` 맨 끝

```python


# ── 근무표 통합 4단계: 임시 비밀번호·초기화의 연결·첫 발급·퇴사(설계 5.7) ──

def _links(u):
    """캘린더 구독·텔레그램·푸시 연결 하나씩(가짜 값)."""
    from django.utils import timezone

    from duty.models import CalendarFeed, PushAlarmSubscription, TelegramAlarmProfile
    CalendarFeed.objects.create(user=u, token_hash="h" * 64, issued_at=timezone.now())
    TelegramAlarmProfile.objects.create(user=u, chat_id="9", verified_at=timezone.now())
    PushAlarmSubscription.objects.create(user=u, endpoint="https://push.example/1", p256dh="p", auth="a")


def _has_links(u) -> tuple[bool, bool, bool]:
    from duty.models import CalendarFeed, PushAlarmSubscription, TelegramAlarmProfile
    return (CalendarFeed.objects.filter(user=u).exists(), TelegramAlarmProfile.objects.get(user=u).chat_id != "",
            PushAlarmSubscription.objects.filter(user=u).exists())


def test_temp_password_shape():
    from duty.accounts import ALPHABET, temp_password
    assert len(ALPHABET) == len(set(ALPHABET)) == 31 and set(ALPHABET).isdisjoint("0o1li")
    got = {temp_password() for _ in range(50)}
    assert len(got) == 50 and all(len(p) == 10 and set(p) <= set(ALPHABET) for p in got)  # 띄어쓰기도 없다


def test_issue_account_uses_temp_password(make_member):
    from duty.accounts import ALPHABET
    pw = issue_account(make_member("가"))
    assert len(pw) == 10 and set(pw) <= set(ALPHABET)


def test_issue_accounts_action_uses_new_password_shape(su_client, make_member):
    """관리 화면 액션도 같은 함수라 모양이 같이 바뀐다."""
    import re

    from duty.accounts import ALPHABET
    a = make_member("가")
    body = su_client.post(reverse("admin:duty_user_changelist"),
                          {"action": "issue_accounts", "_selected_action": [a.pk]}, follow=True).content.decode()
    pw = re.search(rf"<br>가\({a.username}\): ([^<\s]+)", body)[1]
    a.refresh_from_db()
    assert len(pw) == 10 and set(pw) <= set(ALPHABET) and a.check_password(pw)


def test_reset_can_keep_links_but_still_logs_out(client, make_member):
    m = make_member("가")
    issue_account(m)
    _links(m)
    client.force_login(m)
    issue_account(m, revoke_links=False)  # [근무표 설정]의 초기화('비밀번호를 잊었어요')
    assert _has_links(m) == (True, True, True)
    assert client.get("/me/")["Location"].startswith("/login/")  # 비밀번호가 바뀌어 로그인은 끊긴다
    issue_account(m)  # 관리 화면 액션(기본): 지금처럼 끊는다
    assert _has_links(m) == (False, False, False)


def test_first_issue_needs_no_last_login(make_member):
    """퇴사 뒤 다시 재직한 사람(쓸 수 있는 비밀번호 없음 + 로그인한 적 있음)은 첫 발급이 아니다: 지운 기본 규칙이 되살아나지 않는다."""
    from django.utils import timezone
    m = make_member("가")
    issue_account(m)
    AlarmRule.objects.filter(user=m).delete()  # 본인이 지운 기본 규칙
    m.last_login = timezone.now()
    m.set_unusable_password()  # 퇴사(deactivate)가 만드는 상태
    m.save()
    issue_account(m, revoke_links=False)
    assert not AlarmRule.objects.filter(user=m).exists()


def test_deactivate_cuts_login_and_links(client, make_member):
    from duty.accounts import deactivate
    m = make_member("가", user=True)
    _links(m)
    client.force_login(m)
    deactivate(m)
    m.refresh_from_db()
    assert not m.is_active and not m.has_usable_password()
    assert _has_links(m) == (False, False, False)
    assert client.get("/me/")["Location"].startswith("/login/")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_auth.py`
Expected: FAIL 6개 — `ImportError: cannot import name 'ALPHABET'`·`'deactivate'`, `test_issue_account_uses_temp_password`·`..._action_uses_new_password_shape`(12자), `TypeError: issue_account() got an unexpected keyword argument 'revoke_links'`(둘)

- [ ] **Step 3: 구현한다** — `duty/accounts.py` 의 `issue_account` 를 아래로 바꾸고 `deactivate` 를 더한다

```python
ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"  # 헷갈리는 0·o·1·l·i 를 뺐다(근무표 통합 설계 5.7)


def temp_password() -> str:
    """임시 비밀번호 10자(띄어쓰기 없음). 관리 화면 액션과 [근무표 설정]이 함께 쓴다."""
    return "".join(secrets.choice(ALPHABET) for _ in range(10))


def _revoke_links(user: User) -> None:
    """세션과 무관한 연결(캘린더 구독·텔레그램·푸시)을 끊는다. 본인이 다시 연결하면 된다."""
    calendar.revoke(user)
    alarms.clear_telegram(user)
    alarms.delete_all_subscriptions(user)


@transaction.atomic
def issue_account(user: User, revoke_links: bool = True) -> str:
    """임시 비밀번호를 정하고 돌려준다(한 번만 표시). 비밀번호가 바뀌어 모든 기기의 로그인이 끊기고 로그인 잠금이 풀린다.
    첫 발급(쓸 수 있는 비밀번호가 없고 로그인한 적도 없음)이면 기본 알림 규칙을 만든다. 퇴사 뒤 다시 재직한 사람은 첫 발급이 아니다.
    초기화는 revoke_links 일 때 연결도 끊는다: 관리 화면 액션(탈취 의심)은 끊고, [근무표 설정]의 초기화(비밀번호 분실)는 남긴다."""
    first = not user.has_usable_password() and user.last_login is None
    password = temp_password()
    user.set_password(password)
    user.must_change_password = True
    user.save()
    reset(username=user.username)
    if first:
        alarms.create_defaults(user)
    elif revoke_links:
        _revoke_links(user)
    return password


@transaction.atomic
def deactivate(user: User) -> None:
    """퇴사: 재직 끄기 + 쓸 수 없는 비밀번호(모든 기기 로그인이 끊긴다) + 연결 끊기. 다시 재직은 재직만 켜고,
    로그인하려면 [계정 발급]을 다시 한다(계정 열이 '발급 전'으로 보인다)."""
    user.is_active = False
    user.set_unusable_password()
    user.save(update_fields=["is_active", "password"])
    _revoke_links(user)
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_auth.py tests/test_security_stage1.py tests/test_security_stage2.py` → 모두 통과(`test_reissue_revokes_channels`·`test_issue_accounts_action_rolls_back_on_error` 는 고치지 않고 통과: 액션이 `issue_account(u)` 를 그대로 부른다)
Run: `.venv/bin/pytest -W error -q` → `1386 passed`
Run: `makemigrations duty --check --dry-run`(Global Constraints 의 명령) → "No changes detected in app 'duty'"

- [ ] **Step 5: 커밋한다**

```bash
git add duty/accounts.py tests/test_auth.py
git commit -m "feat: 임시 비밀번호를 헷갈리는 글자 없는 10자로, 초기화가 연결을 남길 수 있게(revoke_links), 첫 발급은 로그인한 적 없을 때만, 퇴사 함수 deactivate

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 2: `services/board_settings.py` — 사람 함수·대상 규칙·기록

> 범위: 설계 6.2 사람 함수 표(`add_person`·`set_person`·`set_active`·`future_cells`·`issue`)와 대상 규칙, 공통 규칙(`_require_admin`·근무표 범위·`_audit`). 화면은 Task 3~5.

**Files:**
- Modify: `duty/services/board_settings.py`
- Test: `tests/test_board_settings_people.py`(새 파일)

**Interfaces:**
- Consumes: Task 1 `accounts.issue_account`·`deactivate`, 3단계 `_require_admin`·`_dept`·`_audit`·`NeedsConfirm`·`BEFORE_PUBLISH`, `boards.defs`·`boards.owners`, `prefs.has_types`, `Period.status_label`
- Produces:
  - `USERNAME_RE`, `BAD_USERNAME`, `SAME_NAME`(글)
  - `locked_ids() -> set[int]`: 사람 함수의 대상이 아닌 계정(슈퍼유저 ∪ 어느 근무표든 관리 그룹 멤버)
  - `next_username(board) -> str`: `<code><nn>` 중 빈 가장 작은 번호
  - `add_person(by, board, username, name, dept, type=None) -> User`, `set_person(by, board, user, name, type=None)`, `set_active(by, board, user, active, confirm=None) -> list`(퇴사면 남은 칸 목록, 칸이 있는데 `confirm` 이 칸 수와 다르면 `NeedsConfirm`), `future_cells(board, user) -> list[(date, 칸 이름, Period, 단계 이름)]`, `issue(by, board, users) -> list[(User, password)]`
  - 대상이 아니거나 범위 밖이면 `PermissionDenied`, 검사 오류는 `DutyError`

- [ ] **Step 1: 실패 테스트를 쓴다** — `tests/test_board_settings_people.py`

```python
"""[근무표 설정] 사람 서비스(근무표 통합 설계 5.7·6.2·8): 추가·고치기·퇴사(두 번째 확인)·다시 재직·계정 발급/초기화,
대상 규칙, 기록. 이름은 모두 가상. 비밀번호 문자열은 적지 않고 발급 결과를 그대로 쓴다."""
import logging
from datetime import date

import pytest
from django.contrib.admin.models import LogEntry
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from duty.errors import DutyError
from duty.models import AlarmRule, CalendarFeed, Commute, Department, DutyAssignment, Period, User
from duty.services import board_settings as bs

S = Period.Status
TODAY = date(2026, 12, 2)  # 수요일


@pytest.fixture
def ops_admin(ops_board):
    """운영팀 관리자 가상운영(부서 없는 계정)."""
    u = User.objects.create_user("opsadm", password=None, name="가상운영")
    ops_board.admin_group.user_set.add(u)
    return u


@pytest.fixture
def ops_dept(ops_board):
    return Department.objects.get(code="OPS")


def _ops_member(dept, name, username, active=True):
    return User.objects.create_user(username, password=None, name=name, department=dept, type="직원", is_active=active)


# ── 권한: 그 근무표 관리자만 ──

@pytest.mark.parametrize("who", ["it_admin", "superuser", "anonymous"])
def test_people_functions_only_that_board_admin(who, ops_board, ops_admin, ops_dept, admin_user):
    from django.contrib.auth.models import AnonymousUser
    su = User.objects.create_superuser("root", password=None, name="가상슈퍼")
    by = {"it_admin": admin_user, "superuser": su, "anonymous": AnonymousUser()}[who]
    m = _ops_member(ops_dept, "가상하나", "ops01")
    for call in (lambda: bs.add_person(by, ops_board, "ops02", "가상두리", ops_dept),
                 lambda: bs.set_person(by, ops_board, m, "가상새이름"),
                 lambda: bs.set_active(by, ops_board, m, False),
                 lambda: bs.issue(by, ops_board, [m])):
        with pytest.raises(PermissionDenied):
            call()
    m.refresh_from_db()
    assert (m.name, m.is_active, m.has_usable_password()) == ("가상하나", True, False)
    assert not User.objects.filter(username="ops02").exists()


# ── 대상: 그 근무표 부서 사람 중 슈퍼유저·나 자신·관리자 계정(어느 근무표든)이 아닌 사람 ──

def test_people_targets(it_board, ops_board, ops_dept, make_member):
    me = _ops_member(ops_dept, "가상나관리", "ops08")  # 부서가 있는 이 근무표 관리자(나 자신)
    ops_board.admin_group.user_set.add(me)
    other_admin = _ops_member(ops_dept, "가상겸직", "ops09")  # 이 근무표 사람이지만 IT 관리자(관리자 계정)
    it_board.admin_group.user_set.add(other_admin)
    su = User.objects.create_superuser("root", password=None, name="가상슈퍼", department=ops_dept, type="직원")
    it_person = make_member("가상아이티")  # 다른 근무표 사람
    nodept = User.objects.create_user("free1", password=None, name="가상무소속")  # 부서 없는 계정
    targets = [me, other_admin, su, it_person, nodept]
    for t in targets:
        for call in (lambda: bs.set_person(me, ops_board, t, "가상새이름"),
                     lambda: bs.set_active(me, ops_board, t, False),
                     lambda: bs.issue(me, ops_board, [t])):
            with pytest.raises(PermissionDenied):
                call()
    assert not User.objects.filter(name="가상새이름").exists()
    assert all(u.is_active for u in User.objects.filter(pk__in=[t.pk for t in targets]))
    assert bs.locked_ids() >= {me.pk, other_admin.pk, su.pk} and it_person.pk not in bs.locked_ids()


# ── 추가·고치기 ──

def test_add_person_checks(ops_board, ops_admin, ops_dept, depts):
    for bad in ("Ops01", "가상01", "1ops", "o", "ops-01", "ops 01"):  # 실명·대문자 아이디가 로그·기록에 남지 않게
        with pytest.raises(DutyError, match="아이디는 영문 소문자로 시작하고"):
            bs.add_person(ops_admin, ops_board, bad, "가상하나", ops_dept)
    _ops_member(ops_dept, "가상하나", "OPS01")
    with pytest.raises(DutyError, match="같은 아이디가 이미 있습니다"):
        bs.add_person(ops_admin, ops_board, "ops01", "가상두리", ops_dept)  # 대소문자만 다른 아이디
    with pytest.raises(DutyError, match="^이름: 같은 이름이 이미 있습니다"):
        bs.add_person(ops_admin, ops_board, "ops02", "가상하나", ops_dept)
    for name in ("=가상", "가상(휴가)", " "):  # 이름 규칙(validate_member_name)·빈 이름
        with pytest.raises(DutyError, match="^이름: "):
            bs.add_person(ops_admin, ops_board, "ops02", name, ops_dept)
    with pytest.raises(PermissionDenied):
        bs.add_person(ops_admin, ops_board, "ops02", "가상두리", depts["MEMS"])  # 다른 근무표 부서
    u = bs.add_person(ops_admin, ops_board, "ops02", " 가상두리 ", ops_dept, "개발자")
    u.refresh_from_db()
    # 장중관제가 없는 근무표: 구분은 늘 직원(보낸 구분은 무시), 비밀번호는 쓸 수 없는 값(발급 전)
    assert (u.name, u.department_id, u.type, u.is_active, u.has_usable_password()) == ("가상두리", "OPS", "직원", True, False)


def test_type_only_on_boards_with_slots(it_board, admin_user, depts):
    with pytest.raises(DutyError, match="구분"):
        bs.add_person(admin_user, it_board, "it01", "가상하나", depts["MEMS"])
    u = bs.add_person(admin_user, it_board, "it01", "가상하나", depts["MEMS"], "개발자")
    assert u.type == "개발자"
    bs.set_person(admin_user, it_board, u, "가상하나", "직원")
    assert User.objects.get(pk=u.pk).type == "직원"


def test_set_person_keeps_type_where_no_types(ops_board, ops_admin, ops_dept):
    m = User.objects.create_user("ops01", password=None, name="가상하나", department=ops_dept, type="개발자")
    _ops_member(ops_dept, "가상두리", "ops02")
    with pytest.raises(DutyError, match="^이름: 같은 이름이 이미 있습니다"):
        bs.set_person(ops_admin, ops_board, m, "가상두리")
    bs.set_person(ops_admin, ops_board, m, " 가상새이름 ", "직원")
    m.refresh_from_db()
    assert (m.name, m.type) == ("가상새이름", "개발자")  # 구분 칸이 없는 근무표: 구분은 그대로


def test_next_username(ops_board, ops_dept):
    assert bs.next_username(ops_board) == "ops01"
    _ops_member(ops_dept, "가상하나", "ops01")
    _ops_member(ops_dept, "가상두리", "OPS02")  # 대소문자만 달라도 쓴 번호
    _ops_member(ops_dept, "가상세찬", "ops04", active=False)
    assert bs.next_username(ops_board) == "ops03"
    _ops_member(ops_dept, "가상네모", "ops03")
    assert bs.next_username(ops_board) == "ops05"  # 퇴사자 번호(ops04)도 다시 쓰지 않는다


# ── 남은 근무·퇴사(두 번째 확인)·다시 재직 ──

@pytest.fixture
def busy(ops_board, ops_dept, fixed_today):
    """오늘(12/2) 이후 칸이 셋인 가상하나: 배포 근무 12/3(근무조·점심당번), 입력 중 회차 1/5."""
    fixed_today(TODAY)
    m = _ops_member(ops_dept, "가상하나", "ops01")
    old = Period.objects.create(board=ops_board, name="옛 회차", start_date=date(2026, 11, 30), end_date=date(2026, 12, 4),
                                status=S.PUBLISHED)
    Commute.objects.create(period=old, date=date(2026, 12, 3), member=m, shift="dinner")  # 뒤 배포에 덮였다: 빠진다
    done = Period.objects.create(board=ops_board, name="12월 회차", start_date=date(2026, 11, 30), end_date=date(2026, 12, 4),
                                 status=S.PUBLISHED)
    Commute.objects.create(period=done, date=date(2026, 12, 1), member=m, shift="normal")  # 어제: 빠진다
    Commute.objects.create(period=done, date=date(2026, 12, 3), member=m, shift="normal")
    DutyAssignment.objects.create(period=done, date=date(2026, 12, 3), member=m, cell="lunch")
    nxt = Period.objects.create(board=ops_board, name="1월 회차", start_date=date(2027, 1, 4), end_date=date(2027, 1, 15),
                                status=S.COLLECTING)
    Commute.objects.create(period=nxt, date=date(2027, 1, 5), member=m, shift="dawn")
    return m


def test_future_cells(busy, ops_board):
    assert [(d, cell, p.name, step) for d, cell, p, step in bs.future_cells(ops_board, busy)] == [
        (date(2026, 12, 3), "가운데", "12월 회차", "배포됨"), (date(2026, 12, 3), "점심당번", "12월 회차", "배포됨"),
        (date(2027, 1, 5), "이른", "1월 회차", "입력 중")]


def test_leave_asks_with_count_then_cuts(busy, ops_board, ops_admin):
    with pytest.raises(bs.NeedsConfirm) as e:
        bs.set_active(ops_admin, ops_board, busy, False)
    assert e.value.rows == 3 and str(e.value) == "이 근무 3칸은 그대로 남습니다. 근무표·입력 표에서 다른 사람으로 바꾸세요."
    with pytest.raises(bs.NeedsConfirm):
        bs.set_active(ops_admin, ops_board, busy, False, confirm=2)  # 본 칸 수와 다르면(그사이 바뀜) 다시 묻는다
    assert User.objects.get(pk=busy.pk).is_active
    assert len(bs.set_active(ops_admin, ops_board, busy, False, confirm=3)) == 3  # 퇴사 뒤 목록을 돌려준다
    busy.refresh_from_db()
    assert not busy.is_active and not busy.has_usable_password()
    with pytest.raises(DutyError, match="이미 퇴사"):
        bs.set_active(ops_admin, ops_board, busy, False, confirm=3)
    assert bs.set_active(ops_admin, ops_board, busy, True) == []
    busy.refresh_from_db()
    assert busy.is_active and not busy.has_usable_password()  # 다시 재직: 계정은 '발급 전'(다시 발급해야 로그인)


def test_leave_without_future_cells_is_one_step(ops_board, ops_admin, ops_dept):
    m = _ops_member(ops_dept, "가상하나", "ops01")
    assert bs.set_active(ops_admin, ops_board, m, False) == []
    assert not User.objects.get(pk=m.pk).is_active


# ── 계정 발급·초기화 ──

def test_issue_many_all_or_nothing_and_keeps_links(ops_board, ops_admin, ops_dept, make_member):
    a, b = _ops_member(ops_dept, "가상하나", "ops01"), _ops_member(ops_dept, "가상두리", "ops02")
    gone = _ops_member(ops_dept, "가상퇴사", "ops05", active=False)
    with pytest.raises(PermissionDenied):
        bs.issue(ops_admin, ops_board, [a, make_member("가상아이티")])  # 하나라도 대상이 아니면 아무것도 안 한다
    with pytest.raises(DutyError, match="퇴사한 사람은 먼저 \\[다시 재직\\]"):
        bs.issue(ops_admin, ops_board, [a, gone])
    with pytest.raises(DutyError, match="고르세요"):
        bs.issue(ops_admin, ops_board, [])
    assert not User.objects.get(pk=a.pk).has_usable_password()
    out = bs.issue(ops_admin, ops_board, [a, b])
    assert [u.username for u, _ in out] == ["ops01", "ops02"]
    for u, pw in out:
        u = User.objects.get(pk=u.pk)
        assert u.check_password(pw) and u.must_change_password
    assert AlarmRule.objects.filter(user=a).count() == 2  # 첫 발급: 기본 알림 규칙
    CalendarFeed.objects.create(user=a, token_hash="h" * 64, issued_at=timezone.now())
    [(_, pw)] = bs.issue(ops_admin, ops_board, [a])  # 초기화: 연결은 남긴다(비밀번호 분실 길)
    assert User.objects.get(pk=a.pk).check_password(pw) and CalendarFeed.objects.filter(user=a).exists()


# ── 기록: 로그 한 줄 + LogEntry 한 줄, 실명·비밀번호 없음 ──

def test_people_writes_log_without_names_or_passwords(ops_board, ops_admin, ops_dept, caplog):
    caplog.set_level(logging.DEBUG)  # 모든 로거
    u = bs.add_person(ops_admin, ops_board, "ops01", "가상하나", ops_dept)
    bs.set_person(ops_admin, ops_board, u, "가상하나둘")
    [(_, pw1)] = bs.issue(ops_admin, ops_board, [u])
    [(_, pw2)] = bs.issue(ops_admin, ops_board, [u])
    bs.set_active(ops_admin, ops_board, u, False)
    bs.set_active(ops_admin, ops_board, u, True)
    actions = ["사람 추가", "이름·구분 고치기", "계정 발급", "비밀번호 초기화", "퇴사", "다시 재직"]
    assert [r.getMessage() for r in caplog.records if r.name == "duty.services.board_settings"] == [
        f"board ops: {a} ops01 by opsadm" for a in actions]
    rows = list(LogEntry.objects.order_by("id").values_list("user__username", "object_id", "object_repr", "change_message"))
    assert rows == [("opsadm", str(u.pk), "ops01", f"근무표 ops: {a}") for a in actions]
    traces = caplog.text + str(rows)
    assert "가상" not in traces and pw1 not in traces and pw2 not in traces
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_settings_people.py`
Expected: FAIL — `AttributeError: module 'duty.services.board_settings' has no attribute 'add_person'`(`locked_ids`·`next_username`·`future_cells`·`set_active`·`issue` 도)

- [ ] **Step 3: 구현한다** — `duty/services/board_settings.py`

import 를 바꾼다(맨 위 docstring 첫 줄의 "관리자·입력 담당자·…" 앞에 "사람·" 을 더한다):

```diff
 import logging
+import re
+from datetime import date
 
 from django.contrib.admin.models import CHANGE, LogEntry
 from django.contrib.contenttypes.models import ContentType
-from django.core.exceptions import PermissionDenied
+from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
 from django.db import transaction
 from django.db.models import Count, Q
 
-from .. import perms
+from .. import accounts, perms
 from ..errors import DutyError
 from ..models import Board, BoardShift, Commute, Department, DutyAssignment, Period, User
-from ..shifts import SHIFT_KEYS, is_slot_cell, josa, shift_defs
-from . import boards
+from ..shifts import DEVELOPER, SHIFT_KEYS, STAFF, is_slot_cell, josa, shift_defs
+from . import boards, prefs
```

파일 맨 끝에 더한다:

```python
# ── 사람(근무표 통합 4단계, 설계 5.7·6.2) ──

USERNAME_RE = re.compile(r"[a-z][a-z0-9_]{1,29}")
BAD_USERNAME = "아이디는 영문 소문자로 시작하고 영문 소문자·숫자·_ 로만 씁니다(예: ops07)."
SAME_NAME = "이름: 같은 이름이 이미 있습니다(퇴사한 사람·다른 근무표 포함). 동명이인은 이름 뒤에 부서나 숫자를 붙여 구별합니다."


def locked_ids() -> set[int]:
    """사람 함수(set_person·set_active·issue)의 대상이 아닌 계정: 슈퍼유저와 관리자 계정(어느 근무표든 관리 그룹 멤버).
    관리자 계정의 발급·초기화·퇴사·이름 고치기는 슈퍼유저가 관리 화면에서 한다(관리자끼리 계정을 가로채지 못하게).
    나 자신은 관리자라 늘 든다. 화면도 이 목록으로 줄을 잠근다."""
    return set(User.objects.filter(Q(is_superuser=True) | Q(groups__admin_board__isnull=False)).values_list("pk", flat=True))


def _person(by, board, user) -> User:
    """트랜잭션 안에서 다시 읽고 대상인지 본다: 그 근무표 부서 사람이고, 나 자신·슈퍼유저·관리자 계정이 아님(아니면 PermissionDenied, 뷰는 404)."""
    user = User.objects.select_related("department").get(pk=user.pk)
    if (user.department_id is None or user.department.board_id != board.pk or user.pk == by.pk
            or user.pk in locked_ids()):
        raise PermissionDenied("이 근무표 설정에서 다룰 수 없는 사람입니다.")
    return user


def next_username(board) -> str:
    """사람 추가 아이디 칸에 미리 넣을 값: '<근무표 code><두 자리 번호>'(add_board 와 같은 꼴) 가운데 대소문자 구분 없이
    아직 없는 가장 작은 번호. code 는 Board.clean 이 영문 소문자로 지켜 늘 아이디 규칙에 맞는다."""
    taken = {u.lower() for u in User.objects.filter(username__istartswith=board.code).values_list("username", flat=True)}
    n = 1
    while f"{board.code}{n:02d}" in taken:
        n += 1
    return f"{board.code}{n:02d}"


def _type(board, type, current=STAFF) -> str:
    """구분: 켜진 장중관제 정의가 있는 근무표(관제 후보를 고르는 구분이라)에서만 고른다. 없으면 current(새 사람은 직원, 고치기는 그대로)."""
    if not prefs.has_types(boards.defs(board)):
        return current
    if type not in (STAFF, DEVELOPER):
        raise DutyError("구분(직원·개발자)을 고르세요.")
    return type


def _clean(user) -> None:
    """이름 규칙·이름 전체 고유·구분 제약(User.full_clean). 오류는 '칸 이름: 글' 한 줄."""
    if User.objects.filter(name=user.name).exclude(pk=user.pk).exists():
        raise DutyError(SAME_NAME)
    try:
        user.full_clean()
    except ValidationError as e:
        raise DutyError(" ".join(("" if f == NON_FIELD_ERRORS else f"{User._meta.get_field(f).verbose_name}: ") + m
                                 for f, ms in e.message_dict.items() for m in ms)) from None


@transaction.atomic
def add_person(by, board, username, name, dept, type=None) -> User:
    """그 근무표 부서에 사람을 만든다. 비밀번호는 쓸 수 없는 값(관리 화면 UserAddForm 과 같다, 로그인은 [계정 발급] 뒤).
    아이디는 영문 소문자·숫자·_ 만(실명 아이디가 로그·LogEntry·로그인 잠금 기록에 남지 않게)."""
    _require_admin(by, board)
    dept = _dept(board, dept)
    if not USERNAME_RE.fullmatch(username):
        raise DutyError(BAD_USERNAME)
    if User.objects.filter(username__iexact=username).exists():  # 대소문자만 다른 아이디는 로그인·잠금에서 헷갈린다
        raise DutyError("같은 아이디가 이미 있습니다(대소문자 구분 없음).")
    user = User(username=username, name=name.strip(), department=dept, type=_type(board, type))
    user.set_unusable_password()
    _clean(user)
    user.save()
    _audit(by, board, user, username, "사람 추가")
    return user


@transaction.atomic
def set_person(by, board, user, name, type=None) -> None:
    """이름·구분을 고친다(검사는 add_person 과 같다). 부서를 바꾸는 길은 없다(인사이동은 슈퍼유저)."""
    _require_admin(by, board)
    user = _person(by, board, user)
    user.name, user.type = name.strip(), _type(board, type, user.type)
    _clean(user)
    user.save(update_fields=["name", "type"])
    _audit(by, board, user, user.username, "이름·구분 고치기")


def future_cells(board, user) -> list[tuple[date, str, Period, str]]:
    """읽기만: 그 사람의 오늘 이후 칸 전부 — 배포 근무(그날의 주인 회차의 행)와 배포 전 회차의 출근표·당번 행.
    (날짜, 칸 이름, 회차, 단계 이름), 날짜 순. 그 근무표 회차만. 퇴사 확인과 퇴사 뒤 목록에 쓴다."""
    today = perms.today()
    names = {x.key: x.name for x in boards.defs(board)}
    owner = {d: p.pk for d, p in boards.owners(board, today, None).items()}
    out = []
    for model, col in ((Commute, "shift"), (DutyAssignment, "cell")):
        for row in model.objects.filter(period__board=board, member=user, date__gte=today).select_related("period__board"):
            p, key = row.period, getattr(row, col)
            if p.status in BEFORE_PUBLISH or owner.get(row.date) == p.pk:
                out.append((row.date, names.get(key, key), p, p.status_label))
    return sorted(out, key=lambda c: (c[0], c[2].pk))


@transaction.atomic
def set_active(by, board, user, active: bool, confirm: int | None = None) -> list:
    """퇴사(accounts.deactivate: 로그인·연결 모두 끊음)·다시 재직(재직만 켬, 로그인하려면 [계정 발급]).
    오늘 이후 칸이 있으면 confirm(화면이 보여 준 칸 수)이 같을 때만 퇴사한다(아니면 NeedsConfirm, 막지는 않는다).
    퇴사면 남은 칸 목록을 돌려준다. 관리자 계정은 _person 이 막으므로 재직 관리자 검사는 여기 없다(boards.left_without_admin 한 곳)."""
    _require_admin(by, board)
    user = _person(by, board, user)
    if user.is_active == active:
        raise DutyError("이미 재직 중인 사람입니다." if active else "이미 퇴사 처리된 사람입니다.")
    if active:
        User.objects.filter(pk=user.pk).update(is_active=True)
        _audit(by, board, user, user.username, "다시 재직")
        return []
    cells = future_cells(board, user)
    if cells and confirm != len(cells):
        raise NeedsConfirm(f"이 근무 {len(cells)}칸은 그대로 남습니다. 근무표·입력 표에서 다른 사람으로 바꾸세요.", len(cells))
    accounts.deactivate(user)
    _audit(by, board, user, user.username, "퇴사")
    return cells


@transaction.atomic
def issue(by, board, users) -> list[tuple[User, str]]:
    """계정 발급 / 비밀번호 초기화(연결은 남긴다: '비밀번호를 잊었어요' 길). 여러 사람을 한 트랜잭션으로 — 하나라도 대상이
    아니면 아무것도 하지 않는다. 임시 비밀번호를 돌려준다(화면이 응답 본문에만 그린다. 여기서도 로그·기록에 넣지 않는다)."""
    _require_admin(by, board)
    people = [_person(by, board, u) for u in users]
    if not people:
        raise DutyError("계정을 발급할 사람을 고르세요.")
    if not all(u.is_active for u in people):
        raise DutyError("퇴사한 사람은 먼저 [다시 재직]을 누르세요.")
    out = []
    for u in people:
        action = "비밀번호 초기화" if u.has_usable_password() else "계정 발급"
        out.append((u, accounts.issue_account(u, revoke_links=False)))
        _audit(by, board, u, u.username, action)
    return out
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_settings_people.py` → `14 passed`
Run: `.venv/bin/pytest -W error -q` → `1400 passed`
Run: `makemigrations duty --check --dry-run` → "No changes detected in app 'duty'"

- [ ] **Step 5: 커밋한다**

```bash
git add duty/services/board_settings.py tests/test_board_settings_people.py
git commit -m "feat: 근무표 설정 사람 서비스(추가·이름·구분 고치기·퇴사 두 번째 확인·다시 재직·계정 발급과 초기화, 관리자 계정·슈퍼유저·나 자신은 대상 아님, 로그와 LogEntry)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 3: 사람 칸 1 — 바로가기·읽기 표·고치기·사람 추가

> 범위: 설계 7.1 바로가기 [사람], 7.2 의 1번 중 읽기 표(이름·아이디·부서·구분·계정·동작, 관리자 계정 줄), 줄마다 `<details>` 고치기(`set_person`), "사람 추가" 폼(다음 빈 아이디, 부서가 하나면 숨김, 구분은 장중관제가 있는 근무표만), 390px 카드. 퇴사는 Task 4, 발급은 Task 5.

**Files:**
- Modify: `duty/views/board_settings.py`, `duty/templates/duty/board_settings.html`
- Test: `tests/test_views_board_settings_people.py`(새 파일)

**Interfaces:**
- Consumes: Task 2 `add_person`·`set_person`·`locked_ids`·`next_username`, `prefs.has_types`
- Produces: POST `do=add_person`(name·username·dept·type), `do=set_person`(user·name·type). 칸 id `people`. 뷰 함수 `_state(u)`·`_people(board, edit=None)`. 템플릿 줄 `<tr id="p-<pk>">`(Task 4·5 가 같은 줄에 더한다)

- [ ] **Step 1: 실패 테스트를 쓴다** — `tests/test_views_board_settings_people.py`

```python
"""[근무표 설정] 사람 칸(근무표 통합 설계 7.2 의 1번·8절): 읽기 표·고치기·사람 추가·퇴사·다시 재직·계정 발급과 결과 상자.
이름은 모두 가상. 임시 비밀번호는 응답에서 읽어 쓰고 테스트에 적지 않는다."""
import logging
import re
from datetime import date

import pytest
from django.contrib.admin.models import LogEntry

from duty.accounts import issue_account
from duty.models import Commute, Department, Period, User

URL = "/settings/"
OPS = URL + "?board=ops"


@pytest.fixture
def ops_admin(ops_board):
    u = User.objects.create_user("opsadm", password=None, name="가상운영")
    ops_board.admin_group.user_set.add(u)
    return u


@pytest.fixture
def ops_client(client, ops_admin):
    client.force_login(ops_admin)
    return client


def _ops_member(name, username, active=True):
    return User.objects.create_user(username, password=None, name=name, department=Department.objects.get(code="OPS"),
                                    type="직원", is_active=active)


def _in_use(name, username):
    """계정 '사용 중'(발급 뒤 첫 로그인 비밀번호 변경까지 마친 사람)."""
    u = _ops_member(name, username)
    issue_account(u)
    User.objects.filter(pk=u.pk).update(must_change_password=False)
    return u


def _row(body, user) -> str:
    """표에서 그 사람 줄(<tr id="p-…"> … </tr>)."""
    i = body.index(f'<tr id="p-{user.pk}">')
    return body[i:body.index("</tr>", i)]


# ── 읽기 표 ──

def test_people_section_first_with_states(ops_client, ops_board, it_board):
    a = _ops_member("가상하나", "ops01")
    b = _ops_member("가상두리", "ops02")
    issue_account(b)
    c = _in_use("가상세찬", "ops03")
    e = _ops_member("가상겸직", "ops09")
    it_board.admin_group.user_set.add(e)  # 다른 근무표 관리자 = 관리자 계정
    body = ops_client.get(OPS).content.decode()
    assert body.index('<a href="#people">사람</a>') < body.index('<a href="#admins">관리자</a>')
    assert body.index('<section id="people"') < body.index('<section id="admins"')
    assert "발급 전" in _row(body, a) and "첫 로그인 대기" in _row(body, b) and "사용 중" in _row(body, c)
    assert "<details>" in _row(body, a) and '<input name="name" value="가상하나"' in _row(body, a)
    assert "관리자 계정은 슈퍼유저에게" in _row(body, e) and "<details" not in _row(body, e)
    assert "<th>구분</th>" not in body  # 장중관제가 없는 근무표
    assert '<input name="username" value="ops04"' in body  # 다음 빈 번호
    assert '<input type="hidden" name="dept" value="OPS">' in body  # 부서가 하나면 숨김
    assert "아이디에는 실명을 쓰지 않습니다" in body and "인사이동은 슈퍼유저에게 부탁하세요" in body


def test_it_board_people_have_type_and_dept_choice(admin_client_ok, depts):
    body = admin_client_ok.get(URL).content.decode()
    assert "<th>구분</th>" in body and '<select name="dept" required>' in body
    r = admin_client_ok.post(URL, {"do": "add_person", "name": "가상하나", "username": "it01", "dept": "MEMS"})
    assert r.status_code == 200 and "구분(직원·개발자)을 고르세요." in r.content.decode()
    r = admin_client_ok.post(URL, {"do": "add_person", "name": "가상하나", "username": "it01", "dept": "MEMS", "type": "개발자"})
    assert r.status_code == 302 and User.objects.get(username="it01").type == "개발자"


# ── 사람 추가·고치기 ──

def test_add_person(ops_client, ops_board):
    r = ops_client.post(OPS, {"do": "add_person", "name": "가상하나", "username": "Ops01", "dept": "OPS"})
    body = r.content.decode()
    assert r.status_code == 200 and "아이디는 영문 소문자로 시작하고" in body  # redirect 없이 다시 그린다
    assert '<input name="name" value="가상하나"' in body and '<input name="username" value="Ops01"' in body  # 보낸 값 그대로
    assert not User.objects.filter(name="가상하나").exists()
    r = ops_client.post(OPS, {"do": "add_person", "name": "가상하나", "username": "ops01", "dept": "OPS"})
    assert r.status_code == 302 and r.url == OPS + "#people"
    u = User.objects.get(username="ops01")
    assert (u.name, u.type, u.has_usable_password()) == ("가상하나", "직원", False)
    body = ops_client.get(r.url).content.decode()
    assert "가상하나를 추가했습니다(아이디 ops01). 표에서 [계정 발급]을 눌러 임시 비밀번호를 주세요." in body
    assert "발급 전" in _row(body, u) and '<input name="username" value="ops02"' in body


def test_edit_person_row(ops_client, ops_board):
    a = _ops_member("가상하나", "ops01")
    _ops_member("가상두리", "ops02")
    r = ops_client.post(OPS, {"do": "set_person", "user": a.pk, "name": "가상두리"})
    row = _row(r.content.decode(), a)
    assert r.status_code == 200 and "<details open>" in row and "이름: 같은 이름이 이미 있습니다" in row  # 오류는 그 줄 안에
    assert '<input name="name" value="가상두리"' in row  # 보낸 값 그대로
    r = ops_client.post(OPS, {"do": "set_person", "user": a.pk, "name": "가상새이름"})
    assert r.status_code == 302 and User.objects.get(pk=a.pk).name == "가상새이름"
    assert "가상새이름을 저장했습니다." in ops_client.get(r.url).content.decode()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_views_board_settings_people.py`
Expected: FAIL 4개 — `ValueError: substring not found`(`#people` 없음), `add_person`·`set_person` 은 `do` 가 `ACTIONS` 에 없어 404

- [ ] **Step 3: 뷰를 구현한다** — `duty/views/board_settings.py`

docstring 첫 줄 "관리자·입력 담당자·…" 앞에 "사람·" 을 더하고 import 를 바꾼다:

```diff
-from ..services import board_settings, boards
-from ..shifts import josa, shift_defs, slot_defs
+from ..services import board_settings, boards, prefs
+from ..shifts import DEVELOPER, STAFF, josa, shift_defs, slot_defs
```

`_remove_assignee` 아래에 더한다:

```python
def _add_person(request, board):
    p, dept = request.POST, _dept(request)
    try:
        user = board_settings.add_person(request.user, board, p.get("username", "").strip(), p.get("name", ""), dept,
                                         p.get("type"))
    except DutyError as e:  # 보낸 값 그대로 다시 그리고 오류는 폼 바로 위에(설계 7.3)
        return _render(request, board, add={k: p.get(k, "") for k in ("name", "username", "dept", "type")} | {"error": str(e)})
    return (f"{user.name}{josa(user.name, '을/를')} 추가했습니다(아이디 {user.username}). "
            "표에서 [계정 발급]을 눌러 임시 비밀번호를 주세요.")


def _set_person(request, board):
    user, p = _user(request), request.POST
    try:
        board_settings.set_person(request.user, board, user, p.get("name", ""), p.get("type"))
    except DutyError as e:  # 그 줄을 펼친 채 보낸 값과 오류를 그 줄 안에
        return _render(request, board, edit={"pk": user.pk, "name": p.get("name", ""), "type": p.get("type", ""),
                                             "error": str(e)})
    name = p.get("name", "").strip()
    return f"{name}{josa(name, '을/를')} 저장했습니다."
```

`ACTIONS` 에 더한다:

```diff
 ACTIONS = {  # POST do → (칸 id, 처리). 처리는 결과 글(성공 메시지)이나 응답(다시 그리기·다른 곳으로)을 돌려준다
+    "add_person": ("people", _add_person), "set_person": ("people", _set_person),
     "add_admin": ("admins", _add_admin), "remove_admin": ("admins", _remove_admin),
```

`_unassigned` 위에 더한다:

```python
def _state(u) -> str:
    """계정 열(설계 7.2): 쓸 수 있는 비밀번호가 없으면 발급 전, 첫 로그인 비밀번호 변경 전이면 첫 로그인 대기."""
    if not u.has_usable_password():
        return "발급 전"
    return "첫 로그인 대기" if u.must_change_password else "사용 중"


def _people(board, edit=None) -> list[dict]:
    """사람 칸 줄: 그 근무표 부서 사람(퇴사자 포함), 부서 순 → 이름 순. locked = 사람 함수의 대상이 아닌 계정
    (관리자 계정·슈퍼유저, board_settings.locked_ids): 체크박스·[고치기]·동작 없이 '관리자 계정은 슈퍼유저에게'.
    edit = 고치기 오류로 다시 그릴 때 그 줄의 보낸 값과 오류."""
    locked = board_settings.locked_ids()
    rows = []
    for u in (User.objects.filter(department__board=board).select_related("department")
              .order_by("department__order", "department__code", "name")):
        e = edit if edit and edit["pk"] == u.pk else {}
        rows.append({"u": u, "locked": u.pk in locked, "state": _state(u), "name": e.get("name", u.name),
                     "type": e.get("type", u.type), "error": e.get("error"), "open": bool(e)})
    return rows
```

`_render` 를 바꾼다:

```diff
-def _render(request, board, shifts=None, steps=None, ask=None):
+def _render(request, board, shifts=None, steps=None, ask=None, add=None, edit=None):
     me = request.user
@@
     steps = steps or StepsForm(instance=board)
     on = board.steps()
+    rows = _people(board, edit)
     return render(request, "duty/board_settings.html", {
         "board": board, "boards": _mine(request), "here": _here(board),
+        "people": [r for r in rows if r["u"].is_active], "has_types": prefs.has_types(active), "types": [STAFF, DEVELOPER],
+        "people_depts": list(board.departments.order_by("order", "code")),
+        "add": add or {"username": board_settings.next_username(board)},
         "admin_rows": admin_rows, "admin_candidates": board_settings.admin_candidates(board), "depts": depts,
```

- [ ] **Step 4: 템플릿을 구현한다** — `duty/templates/duty/board_settings.html`

바로가기 줄 맨 앞에 [사람]:

```diff
-<nav class="jump" aria-label="칸 바로가기"><a href="#admins">관리자</a>
+<nav class="jump" aria-label="칸 바로가기"><a href="#people">사람</a><a href="#admins">관리자</a>
```

`<section id="admins" class="cfg">` 바로 위에 사람 칸을 더한다:

```django
<section id="people" class="cfg">
  <h4>사람 <small>이 근무표 부서 사람과 로그인 계정. 줄마다 [고치기]를 펼쳐 이름·구분을 고치고, 비밀번호 초기화·퇴사도 그 안에서 합니다</small></h4>
  {% include "duty/_section_msgs.html" with sec="people" %}
  <table class="people">
    <thead><tr><th>발급</th><th>이름</th><th>아이디</th><th>부서</th>{% if has_types %}<th>구분</th>{% endif %}<th>계정</th><th>동작</th></tr></thead>
    <tbody>{% for r in people %}<tr id="p-{{ r.u.pk }}">
      <td class="pick"></td>
      <td class="who"><strong>{{ r.u.name }}</strong></td>
      <td class="who">{{ r.u.username }}</td>
      <td data-label="부서">{{ r.u.department.name }}</td>
      {% if has_types %}<td data-label="구분">{{ r.u.type }}</td>{% endif %}
      <td data-label="계정">{{ r.state }}</td>
      <td class="act">{% if r.locked %}<small class="note">관리자 계정은 슈퍼유저에게</small>{% else %}
        <details{% if r.open %} open{% endif %}><summary>고치기 · 비밀번호 · 퇴사</summary>
          {% if r.error %}<p class="err">{{ r.error }}</p>{% endif %}
          <form method="post" action="{{ here }}#p-{{ r.u.pk }}" class="add labeled">{% csrf_token %}
            <input type="hidden" name="do" value="set_person"><input type="hidden" name="user" value="{{ r.u.pk }}">
            <label>이름 <input name="name" value="{{ r.name }}" required maxlength="32"></label>
            {% if has_types %}<label>구분 <select name="type" required>{% for t in types %}<option{% if t == r.type %} selected{% endif %}>{{ t }}</option>{% endfor %}</select></label>{% endif %}
            <button class="outline">저장</button>
          </form>
        </details>{% endif %}</td>
    </tr>{% empty %}<tr><td colspan="7">아직 사람이 없습니다. 아래 '사람 추가'에서 넣습니다.</td></tr>{% endfor %}</tbody>
  </table>
  <h5 id="add-person">사람 추가</h5>
  {% if add.error %}<p class="err">{{ add.error }}</p>{% endif %}
  <form method="post" action="{{ here }}#add-person" class="add labeled">{% csrf_token %}<input type="hidden" name="do" value="add_person">
    <label>이름 <input name="name" value="{{ add.name|default:'' }}" required maxlength="32"></label>
    <label>아이디 <input name="username" value="{{ add.username }}" required maxlength="30" autocapitalize="none" autocomplete="off" spellcheck="false" aria-describedby="uid-help"></label>
    {% if people_depts|length == 1 %}<input type="hidden" name="dept" value="{{ people_depts.0.pk }}">
    {% else %}<label>부서 <select name="dept" required><option value="">고르세요</option>{% for d in people_depts %}<option value="{{ d.pk }}"{% if d.pk == add.dept %} selected{% endif %}>{{ d.name }}</option>{% endfor %}</select></label>{% endif %}
    {% if has_types %}<label>구분 <select name="type" required><option value="">고르세요</option>{% for t in types %}<option{% if t == add.type %} selected{% endif %}>{{ t }}</option>{% endfor %}</select></label>{% endif %}
    <button class="outline">사람 추가</button>
  </form>
  <p class="note" id="uid-help">아이디에는 실명을 쓰지 않습니다(영문 소문자·숫자·_). 다음 번호를 미리 넣어 두었고 고칠 수 있습니다.<br>
    부서·근무표를 옮기는 인사이동은 슈퍼유저에게 부탁하세요.</p>
</section>
```

`<style>` 끝(`.btn-name` 줄 아래)에 더한다:

```css
  table.people { max-width: 64rem; }
  table.people td, table.people th { vertical-align: top; }
  table.people td.act form, table.people td.act button { width: auto; margin: 0 0 .4rem; }
  table.people td.act details { margin: 0; }
  table.people td.act summary { min-height: 44px; display: flex; align-items: center; }
  table.people button { min-height: 44px; padding: .4rem 1rem; }
  table.people .note, p.note { color: var(--pico-muted-color); }
  h5#add-person { margin: 1.5rem 0 .6rem; scroll-margin-top: 1rem; }
  /* 휴대폰: 줄을 카드처럼(체크·이름·아이디 한 줄, 나머지는 칸 이름을 앞에 붙여 한 줄씩, 설계 7.2) */
  @media (max-width: 40rem) {
    table.people thead { display: none; }
    table.people, table.people tbody, table.people tr, table.people td { display: block; }
    table.people tr { padding: .6rem 0; border-bottom: 1px solid var(--duty-line); }
    table.people td { border: 0; padding: .2rem 0; }
    table.people td.pick, table.people td.who { display: inline-block; vertical-align: middle; margin-right: .5rem; }
    table.people td[data-label]::before { content: attr(data-label) " · "; color: var(--pico-muted-color); }
  }
```

- [ ] **Step 5: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_views_board_settings_people.py tests/test_views_board_settings.py` → 모두 통과
Run: `.venv/bin/pytest -W error -q` → `1404 passed`(스냅샷 그대로: 설정 화면은 스냅샷에 없다)

- [ ] **Step 6: 브라우저로 본다**(Task 7 의 준비, `admin`)

[근무표 설정] → [운영팀]: 바로가기 맨 앞 [사람], 사람 칸이 맨 위. 표에 가상하나…(사용 중), 가상일곱(발급 전), 가상여덟(첫 로그인 대기), 가상다섯(IT 관리자 = "관리자 계정은 슈퍼유저에게"). [고치기 · 비밀번호 · 퇴사]를 펼쳐 이름을 다른 사람 이름으로 바꿔 [저장] → 그 줄이 펼친 채 "이름: 같은 이름이 이미 있습니다…". 사람 추가: 아이디 칸에 `ops01`(두 자리 번호 중 빈 첫 번호. `OPS0`~`OPS5` 는 꼴이 달라 겹치지 않는다), 이름을 넣고 [사람 추가] → 칸 제목 아래 성공 글. 390px: 표가 카드(이름·아이디 한 줄, "부서 · 운영"·"계정 · 발급 전" 한 줄씩), [고치기]·[저장]·[사람 추가] 44px 이상, 가로 넘침 없음. 1400px·다크·아주 크게에서 글이 잘리지 않는다. 확인 뒤 더한 사람은 그대로 둔다(임시 DB).

- [ ] **Step 7: 커밋한다**

```bash
git add duty/views/board_settings.py duty/templates/duty/board_settings.html tests/test_views_board_settings_people.py
git commit -m "feat: 근무표 설정 사람 칸(계정 상태가 보이는 읽기 표, 줄마다 고치기, 다음 빈 아이디를 넣은 사람 추가, 휴대폰 카드)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 4: 사람 칸 2 — 퇴사(두 번째 확인)·퇴사자 목록·다시 재직

> 범위: 설계 7.2 의 1번 중 [퇴사](확인창, 남은 근무가 있으면 그 줄 아래 목록과 [그래도 퇴사 처리]), 퇴사 뒤 메시지와 링크 목록(배포된 날 = 하루 화면, 배포 전 회차 = 그 회차 입력 표), 접힌 퇴사자 목록과 [다시 재직].

**Files:**
- Modify: `duty/views/board_settings.py`, `duty/templates/duty/board_settings.html`
- Test: `tests/test_views_board_settings_people.py`(맨 끝)

**Interfaces:**
- Consumes: Task 2 `set_active`·`future_cells`·`NeedsConfirm`, `boards.board_query`
- Produces: POST `do=leave`(user, confirm), `do=rejoin`(user). `_people(board, edit=None, leave=None)`, `_cells(request, board, user, cells) -> list[(url, 글)]`

- [ ] **Step 1: 실패 테스트를 쓴다** — `tests/test_views_board_settings_people.py` 맨 끝

```python


# ── 퇴사·다시 재직 ──

def test_leave_confirm_then_list_then_rejoin(ops_client, ops_board, fixed_today):
    fixed_today(date(2026, 12, 2))
    m = _ops_member("가상하나", "ops01")
    done = Period.objects.create(board=ops_board, name="12월 회차", start_date=date(2026, 11, 30), end_date=date(2026, 12, 4),
                                 status="published")
    Commute.objects.create(period=done, date=date(2026, 12, 3), member=m, shift="normal")
    nxt = Period.objects.create(board=ops_board, name="1월 회차", start_date=date(2027, 1, 4), end_date=date(2027, 1, 15),
                                status="collecting")
    Commute.objects.create(period=nxt, date=date(2027, 1, 5), member=m, shift="dawn")
    body = ops_client.get(OPS).content.decode()
    assert "을(를) 퇴사 처리할까요? 로그인할 수 없고 캘린더·텔레그램·푸시 연결이 모두 끊깁니다." in _row(body, m)
    r = ops_client.post(OPS, {"do": "leave", "user": m.pk})  # 남은 근무가 있다: 저장하지 않고 그 줄 아래에서 묻는다
    row = _row(r.content.decode(), m)
    assert r.status_code == 200 and "<details open>" in row and User.objects.get(pk=m.pk).is_active
    assert "12/3 가운데 — 12월 회차(배포됨)" in row and "1/5 이른 — 1월 회차(입력 중)" in row
    assert "이 근무 2칸은 그대로 남습니다. 근무표·입력 표에서 다른 사람으로 바꾸세요." in row
    assert '<button class="danger-btn" name="confirm" value="2">그래도 퇴사 처리</button>' in row
    r = ops_client.post(OPS, {"do": "leave", "user": m.pk, "confirm": "2"})
    assert r.status_code == 302 and r.url == OPS + "#people" and not User.objects.get(pk=m.pk).is_active
    body = ops_client.get(r.url).content.decode()
    assert "가상하나를 퇴사 처리했습니다. [다시 재직]으로 되돌릴 수 있습니다." in body
    assert '<a href="/day/2026-12-03/">12/3 가운데 — 12월 회차(배포됨)</a>' in body  # 운영팀이 이 관리자의 내 근무표
    assert f'<a href="/collect/{nxt.pk}/OPS/">1/5 이른 — 1월 회차(입력 중)</a>' in body
    assert f'<tr id="p-{m.pk}">' not in body  # 표에서 빠지고
    departed = body[body.index('<details id="departed"'):]
    assert "퇴사한 사람 1명" in departed and "가상하나" in departed and ">다시 재직</button>" in departed
    r = ops_client.post(OPS, {"do": "rejoin", "user": m.pk})
    assert r.status_code == 302 and User.objects.get(pk=m.pk).is_active
    body = ops_client.get(r.url).content.decode()
    assert "가상하나를 다시 재직으로 돌렸습니다. 로그인하려면 [계정 발급]을 다시 누르세요." in body
    assert "발급 전" in _row(body, m)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_views_board_settings_people.py`
Expected: FAIL — `test_leave_confirm_then_list_then_rejoin`(`assert ... in` : 퇴사 확인창 글이 없다)

- [ ] **Step 3: 뷰를 구현한다** — `duty/views/board_settings.py`

import 를 더한다:

```diff
 from django.urls import reverse
+from django.utils.html import format_html, format_html_join
```

`_set_person` 아래에 더한다:

```python
def _cells(request, board, user, cells) -> list[tuple[str, str]]:
    """남은 근무 목록 (링크, 글 "12/3 정상 — 12월 회차(배포됨)"): 배포된 날은 하루 화면, 배포 전 회차는 그 사람 부서의 입력 표."""
    q = boards.board_query(request.user, board)
    return [(reverse("day", args=[d]) + q if p.status == Period.Status.PUBLISHED
             else reverse("collect_table", args=[p.pk, user.department_id]),
             f"{d.month}/{d.day} {cell} — {p.name}({step})") for d, cell, p, step in cells]


def _leave(request, board):
    user, confirm = _user(request), request.POST.get("confirm", "")
    try:
        cells = board_settings.set_active(request.user, board, user, False, int(confirm) if confirm.isdigit() else None)
    except board_settings.NeedsConfirm as e:  # 오늘 이후 근무가 남았다: 그 줄 아래에 목록과 [그래도 퇴사 처리](본 칸 수)
        rows = _cells(request, board, user, board_settings.future_cells(board, user))
        return _render(request, board, leave={"pk": user.pk, "cells": rows, "msg": str(e), "n": len(rows)})
    messages.success(request, f"{user.name}{josa(user.name, '을/를')} 퇴사 처리했습니다. [다시 재직]으로 되돌릴 수 있습니다.",
                     extra_tags="people")
    if cells:  # 퇴사 뒤에도 남은 근무를 링크로(설계 7.2). format_html 이라 회차 이름은 이스케이프된다
        messages.warning(request, format_html(
            "남은 근무 {}칸 — 근무표·입력 표에서 다른 사람으로 바꾸세요.<ul>{}</ul>", len(cells),
            format_html_join("", '<li><a href="{}">{}</a></li>', _cells(request, board, user, cells))), extra_tags="people")
    return redirect(f"{_here(board)}#people")


def _rejoin(request, board):
    user = _user(request)
    board_settings.set_active(request.user, board, user, True)
    return f"{user.name}{josa(user.name, '을/를')} 다시 재직으로 돌렸습니다. 로그인하려면 [계정 발급]을 다시 누르세요."
```

`ACTIONS` 의 사람 줄을 바꾼다:

```diff
-    "add_person": ("people", _add_person), "set_person": ("people", _set_person),
+    "add_person": ("people", _add_person), "set_person": ("people", _set_person),
+    "leave": ("people", _leave), "rejoin": ("people", _rejoin),
```

`_people` 이 퇴사 확인을 받는다:

```diff
-def _people(board, edit=None) -> list[dict]:
+def _people(board, edit=None, leave=None) -> list[dict]:
@@
-    edit = 고치기 오류로 다시 그릴 때 그 줄의 보낸 값과 오류."""
+    edit = 고치기 오류로 다시 그릴 때 그 줄의 보낸 값과 오류, leave = 퇴사 확인으로 다시 그릴 때 그 줄의 남은 근무."""
@@
         e = edit if edit and edit["pk"] == u.pk else {}
+        lv = leave if leave and leave["pk"] == u.pk else None
         rows.append({"u": u, "locked": u.pk in locked, "state": _state(u), "name": e.get("name", u.name),
-                     "type": e.get("type", u.type), "error": e.get("error"), "open": bool(e)})
+                     "type": e.get("type", u.type), "error": e.get("error"), "leave": lv, "open": bool(e or lv)})
```

`_render`:

```diff
-def _render(request, board, shifts=None, steps=None, ask=None, add=None, edit=None):
+def _render(request, board, shifts=None, steps=None, ask=None, add=None, edit=None, leave=None):
@@
-    rows = _people(board, edit)
+    rows = _people(board, edit, leave)
@@
-        "people": [r for r in rows if r["u"].is_active], "has_types": prefs.has_types(active), "types": [STAFF, DEVELOPER],
+        "people": [r for r in rows if r["u"].is_active], "departed": [r for r in rows if not r["u"].is_active],
+        "has_types": prefs.has_types(active), "types": [STAFF, DEVELOPER],
```

- [ ] **Step 4: 템플릿을 구현한다** — `duty/templates/duty/board_settings.html`

줄의 고치기 폼 `</form>` 과 `</details>` 사이에 위험 구역을 더한다:

```diff
             <button class="outline">저장</button>
           </form>
+          <section class="danger">
+            {% if r.leave %}<div class="msg warning" role="alert"><ul>{% for url, text in r.leave.cells %}<li>{{ text }}</li>{% endfor %}</ul>{{ r.leave.msg }}</div>{% endif %}
+            <form method="post" action="{{ here }}#p-{{ r.u.pk }}"{% if not r.leave %} onsubmit="return confirm('{{ r.u.name|escapejs }}({{ r.u.username|escapejs }})을(를) 퇴사 처리할까요? 로그인할 수 없고 캘린더·텔레그램·푸시 연결이 모두 끊깁니다.')"{% endif %}>{% csrf_token %}
+              <input type="hidden" name="do" value="leave"><input type="hidden" name="user" value="{{ r.u.pk }}">
+              {% if r.leave %}<button class="danger-btn" name="confirm" value="{{ r.leave.n }}">그래도 퇴사 처리</button>{% else %}<button class="danger-btn">퇴사</button>{% endif %}
+            </form>
+          </section>
         </details>{% endif %}</td>
```

`</table>` 바로 아래(사람 추가 `<h5>` 위)에 퇴사자 목록:

```django
  {% if departed %}<details id="departed" class="departed"><summary>퇴사한 사람 {{ departed|length }}명</summary>
    <ul class="members">{% for r in departed %}<li><span>{{ r.u.name }} <small>· {{ r.u.username }} · {{ r.u.department.name }}</small></span>
      {% if r.locked %}<small class="note">관리자 계정은 슈퍼유저에게</small>
      {% else %}<form method="post" action="{{ here }}#people">{% csrf_token %}<input type="hidden" name="do" value="rejoin"><input type="hidden" name="user" value="{{ r.u.pk }}">
        <button class="outline secondary">다시 재직</button></form>{% endif %}</li>{% endfor %}</ul>
  </details>{% endif %}
```

`<style>` 의 사람 칸 줄 아래에 더한다:

```css
  table.people section.danger { margin-top: .8rem; padding: .6rem; }
  table.people .msg ul { margin: 0 0 .4rem; }
  details.departed { max-width: 40rem; margin: 1rem 0 0; }
  details.departed > summary { min-height: 44px; display: flex; align-items: center; }
```

- [ ] **Step 5: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_views_board_settings_people.py` → 모두 통과
Run: `.venv/bin/pytest -W error -q` → `1405 passed`

- [ ] **Step 6: 브라우저로 본다**(`admin`)

[운영팀] 사람 칸: 가상두리(남은 근무 있음) [고치기 · 비밀번호 · 퇴사] → [퇴사] → 확인창(이름·아이디) → 그 줄이 펼친 채 빨간 구역 안에 "…/… 가운데 — 이번 2주(입력 중)" 목록, "이 근무 1칸은 그대로 남습니다…", [그래도 퇴사 처리] → 칸 제목 아래 성공 글과 "남은 근무 1칸 —" 링크 목록(누르면 입력 표). 표 아래 [퇴사한 사람 2명](가상아홉 포함)을 펼쳐 가상두리 [다시 재직] → 계정 "발급 전". 390px·다크·아주 크게: 빨간 구역과 경고 상자가 카드 폭 안, 버튼 44px 이상, 가로 넘침 없음.

- [ ] **Step 7: 커밋한다**

```bash
git add duty/views/board_settings.py duty/templates/duty/board_settings.html tests/test_views_board_settings_people.py
git commit -m "feat: 근무표 설정 사람 칸 퇴사(남은 근무를 그 줄 아래 보이고 한 번 더 묻기, 퇴사 뒤 링크 목록)와 퇴사자 목록·다시 재직

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 5: 사람 칸 3 — 계정 발급·초기화·결과 상자·보안

> 범위: 설계 7.2 의 1번 중 [계정 발급](발급 전 줄)·[비밀번호 초기화](확인창)·[선택한 사람 계정 발급](체크박스, 계획 1번), 누르면 꺼짐, 임시 비밀번호 결과 상자(redirect 없이, 응답 본문에만). 보안 테스트: 다른 근무표 사람·관리자 계정·나 자신·없는 id 를 섞은 POST → 404·DB 변화 없음, 비밀번호가 로그·세션(메시지 포함)·`LogEntry` 에 없음, `Cache-Control: no-store`.

**Files:**
- Modify: `duty/views/board_settings.py`, `duty/templates/duty/board_settings.html`
- Test: `tests/test_views_board_settings_people.py`(맨 끝)

**Interfaces:**
- Consumes: Task 2 `issue`
- Produces: POST `do=issue`(users 여러 개). `_render(..., issued=[(user, password)])`, 템플릿 `<code class="pw">`, 빈 폼 `id="issue-many"`

- [ ] **Step 1: 실패 테스트를 쓴다** — `tests/test_views_board_settings_people.py` 맨 끝

```python


# ── 계정 발급·초기화·결과 상자 ──

OFF = "if (event.submitter) event.submitter.disabled = true"  # 누르면 바로 꺼진다
PW = re.compile(r'\((ops\d\d)\) <code class="pw">([^<]+)</code>')


def test_issue_controls_per_state(ops_client, ops_board):
    a = _ops_member("가상하나", "ops01")
    b = _ops_member("가상두리", "ops02")
    issue_account(b)
    c = _in_use("가상세찬", "ops03")
    body = ops_client.get(OPS).content.decode()
    pick = 'name="users" value="{}" form="issue-many"'
    # 일괄 발급 체크는 발급 전·첫 로그인 대기만(쓰는 중인 사람을 확인창 없이 한꺼번에 로그아웃시키지 않게)
    assert pick.format(a.pk) in _row(body, a) and pick.format(b.pk) in _row(body, b) and pick.format(c.pk) not in _row(body, c)
    assert ">계정 발급</button>" in _row(body, a) and ">계정 발급</button>" not in _row(body, b)
    assert ">비밀번호 초기화</button>" not in _row(body, a) and ">비밀번호 초기화</button>" in _row(body, c)
    assert "의 비밀번호를 새로 만들까요? 로그인 중인 기기에서 로그아웃되고 로그인 잠금도 풀립니다. 캘린더·텔레그램·푸시 연결은 그대로입니다." in _row(body, c)
    assert body.count(OFF) == 4  # 일괄 폼 + a [계정 발급] + b·c [비밀번호 초기화]
    assert '<button form="issue-many" class="outline">선택한 사람 계정 발급</button>' in body


def test_issue_result_box_only_in_response(ops_client, ops_board, caplog):
    caplog.set_level(logging.INFO)  # 운영 로그 수준, 모든 로거
    a, b = _ops_member("가상하나", "ops01"), _ops_member("가상두리", "ops02")
    r = ops_client.post(OPS, {"do": "issue", "users": [a.pk, b.pk]})
    body = r.content.decode()
    got = dict(PW.findall(body))
    assert r.status_code == 200 and set(got) == {"ops01", "ops02"}  # redirect 없이 그 자리에서
    assert "no-store" in r["Cache-Control"]  # 뒤로 가기로 다시 보이지 않게
    assert "띄어쓰기 없이 입력합니다. 사람마다 1:1로만 전달하세요." in body and "새로고침하지 마세요" in body
    assert f'<a href="{OPS}#people" role="button" class="outline">닫기</a>' in body
    for u in (a, b):
        u.refresh_from_db()
        assert u.check_password(got[u.username]) and u.must_change_password
    assert "첫 로그인 대기" in _row(body, a)
    traces = (caplog.text + str(dict(ops_client.session.items()))  # 세션(메시지 포함)
              + str(list(LogEntry.objects.values_list("object_repr", "change_message"))))
    assert not any(pw in traces for pw in got.values()) and "가상" not in caplog.text
    assert not PW.search(ops_client.get(OPS).content.decode())  # [닫기]·다음 화면에는 없다


def test_issue_needs_pick_and_active(ops_client, ops_board):
    gone = _ops_member("가상퇴사", "ops05", active=False)
    assert "계정을 발급할 사람을 고르세요." in ops_client.post(OPS, {"do": "issue"}, follow=True).content.decode()
    body = ops_client.post(OPS, {"do": "issue", "users": [gone.pk]}, follow=True).content.decode()
    assert "퇴사한 사람은 먼저 [다시 재직]을 누르세요." in body and not User.objects.get(pk=gone.pk).has_usable_password()


def test_people_posts_outside_targets_are_404(ops_client, ops_board, ops_admin, it_board, make_member):
    """다른 근무표 사람·관리자 계정(어느 근무표든)·나 자신·없는 id·다른 근무표 부서 → 404, DB 변화 없음(설계 11)."""
    a = _ops_member("가상하나", "ops01")
    it_person = make_member("가상아이티")
    other_admin = _ops_member("가상겸직", "ops09")
    it_board.admin_group.user_set.add(other_admin)
    for data in ({"do": "issue", "users": [a.pk, it_person.pk]}, {"do": "issue", "users": [other_admin.pk]},
                 {"do": "issue", "users": [ops_admin.pk]}, {"do": "issue", "users": [a.pk, "99999"]},
                 {"do": "set_person", "user": it_person.pk, "name": "가상새이름"},
                 {"do": "set_person", "user": other_admin.pk, "name": "가상새이름"},
                 {"do": "leave", "user": it_person.pk}, {"do": "leave", "user": other_admin.pk},
                 {"do": "rejoin", "user": it_person.pk},
                 {"do": "add_person", "name": "가상새이름", "username": "ops07", "dept": "MEMS"}):
        assert ops_client.post(OPS, data).status_code == 404, data
    people = User.objects.filter(pk__in=[a.pk, it_person.pk, other_admin.pk, ops_admin.pk])
    assert not any(u.has_usable_password() for u in people) and all(u.is_active for u in people)
    assert not User.objects.filter(name="가상새이름").exists() and not LogEntry.objects.exists()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_views_board_settings_people.py`
Expected: FAIL — `test_issue_controls_per_state`·`test_issue_result_box_only_in_response`·`test_issue_needs_pick_and_active`(`do=issue` 가 404 이거나 체크박스가 없다), `test_people_posts_outside_targets_are_404` 의 `issue` 줄(이미 404 라 통과할 수 있음 — 나머지 셋이 실패하면 된다)

- [ ] **Step 3: 뷰를 구현한다** — `duty/views/board_settings.py`

`_rejoin` 아래에 더한다:

```python
def _issue(request, board):
    ids = set(request.POST.getlist("users"))
    users = list(User.objects.filter(pk__in=[i for i in ids if i.isdigit()]))
    if len(users) != len(ids):  # 없는 id 가 섞였다
        raise Http404
    issued = board_settings.issue(request.user, board, users)
    # 임시 비밀번호는 이 응답 본문에만: redirect·messages(세션)·로그에 싣지 않는다(설계 7.2)
    return _render(request, board, issued=sorted(issued, key=lambda x: x[0].name))
```

`ACTIONS`:

```diff
-    "leave": ("people", _leave), "rejoin": ("people", _rejoin),
+    "leave": ("people", _leave), "rejoin": ("people", _rejoin), "issue": ("people", _issue),
```

`_render`:

```diff
-def _render(request, board, shifts=None, steps=None, ask=None, add=None, edit=None, leave=None):
+def _render(request, board, shifts=None, steps=None, ask=None, add=None, edit=None, leave=None, issued=None):
@@
         "add": add or {"username": board_settings.next_username(board)},
+        "issued": issued,
```

- [ ] **Step 4: 템플릿을 구현한다** — `duty/templates/duty/board_settings.html`

사람 칸의 `{% include "duty/_section_msgs.html" with sec="people" %}` 바로 아래에 결과 상자와 일괄 폼:

```django
  {% if issued %}<div class="pwbox" role="alert">
    <p><strong>띄어쓰기 없이 입력합니다. 사람마다 1:1로만 전달하세요. 이 상자를 닫거나 다른 버튼을 누르면 다시 볼 수 없습니다.
      새로고침하지 마세요(새 비밀번호가 다시 만들어지고 앞 비밀번호는 쓸 수 없게 됩니다). 적은 뒤에 다음 사람을 발급하세요(여럿이면 체크해서 한 번에).</strong></p>
    <ul>{% for u, pw in issued %}<li>{{ u.name }}({{ u.username }}) <code class="pw">{{ pw }}</code></li>{% endfor %}</ul>
    <a href="{{ here }}#people" role="button" class="outline">닫기</a>
  </div>{% endif %}
  {# 체크박스는 표 안(줄마다 다른 폼이 있어 겹칠 수 없다)에서 form 속성으로 이 빈 폼에 묶는다 #}
  <form id="issue-many" method="post" action="{{ here }}#people" onsubmit="if (event.submitter) event.submitter.disabled = true">{% csrf_token %}<input type="hidden" name="do" value="issue"></form>
```

체크 칸:

```diff
-      <td class="pick"></td>
+      <td class="pick">{% if not r.locked and r.state != "사용 중" %}<label><input type="checkbox" name="users" value="{{ r.u.pk }}" form="issue-many" aria-label="{{ r.u.name }} 계정 발급 선택"></label>{% endif %}</td>
```

동작 칸의 `<details` 바로 앞(`{% else %}` 다음)에 줄의 [계정 발급]:

```django
        {% if r.state == "발급 전" %}<form method="post" action="{{ here }}#people" onsubmit="if (event.submitter) event.submitter.disabled = true">{% csrf_token %}
          <input type="hidden" name="do" value="issue"><input type="hidden" name="users" value="{{ r.u.pk }}"><button class="outline">계정 발급</button></form>{% endif %}
```

위험 구역 `<section class="danger">` 바로 다음 줄(퇴사 목록·폼 위)에 [비밀번호 초기화]:

```django
            {% if r.state != "발급 전" %}<form method="post" action="{{ here }}#people" onsubmit="if (!confirm('{{ r.u.name|escapejs }}({{ r.u.username|escapejs }})의 비밀번호를 새로 만들까요? 로그인 중인 기기에서 로그아웃되고 로그인 잠금도 풀립니다. 캘린더·텔레그램·푸시 연결은 그대로입니다.')) return false; if (event.submitter) event.submitter.disabled = true">{% csrf_token %}
              <input type="hidden" name="do" value="issue"><input type="hidden" name="users" value="{{ r.u.pk }}"><button class="danger-btn">비밀번호 초기화</button></form>{% endif %}
```

`</table>` 바로 아래(퇴사자 목록 위)에 일괄 버튼:

```django
  {% if people %}<p class="bulk"><button form="issue-many" class="outline">선택한 사람 계정 발급</button> <small class="note">발급 전·첫 로그인 대기인 사람을 체크해 한 번에 받습니다</small></p>{% endif %}
```

`<style>` 의 사람 칸 줄 아래에 더한다:

```css
  table.people td.pick label { display: inline-flex; align-items: center; justify-content: center; min-width: 44px; min-height: 44px; margin: 0; }
  p.bulk button { width: auto; min-height: 44px; margin: 0 .5rem .4rem 0; }
  .pwbox { max-width: 40rem; padding: 1rem; margin: 0 0 1.2rem; border: 3px solid var(--nxt-red); border-radius: .4rem; }
  .pwbox ul { padding-left: 1.2rem; }
  .pwbox li { margin: .6rem 0; font-size: 1.1rem; }
  code.pw { font-size: 1.6rem; letter-spacing: .12em; padding: .2rem .5rem; font-variant-ligatures: none; }  /* 받아 적기 쉬운 고정폭 큰 글씨 */
  .pwbox a[role=button] { min-height: 44px; }
```

- [ ] **Step 5: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_views_board_settings_people.py tests/test_board_settings_people.py tests/test_auth.py` → 모두 통과
Run: `.venv/bin/pytest -W error -q` → `1409 passed`

- [ ] **Step 6: 브라우저로 본다**(`admin`)

[운영팀] 사람 칸: 가상일곱 줄 [계정 발급] → 누르는 순간 버튼이 꺼지고, 같은 화면 사람 칸 맨 위 빨간 상자에 "가상일곱(ops11) `xxxxxxxxxx`"(고정폭 큰 글씨), 굵은 안내 글, [닫기]. 줄 계정 열 "첫 로그인 대기". 새로고침 → 브라우저가 다시 보낼지 묻는다(취소). [닫기] → 상자 없음. 가상여덟·가상일곱 체크 → [선택한 사람 계정 발급] → 두 사람이 이름 순으로. 사용 중 줄에는 체크박스가 없다. 가상하나 [고치기 · 비밀번호 · 퇴사] → [비밀번호 초기화] → 확인창 글 → 상자. 다른 창에서 그 사람(`OPS0` / `Demo-pass-123`)으로 로그인해 둔 세션이 끊기는지 본다. 390px: 상자가 화면 폭 안(비밀번호가 한 줄), 체크박스 누를 자리 44px, 가로 넘침 없음. 다크·아주 크게에서 빨간 테두리와 글이 읽힌다. 서버 로그(`$W/server.log`)에 비밀번호·실명 없음(`grep -c` 로 상자에 보인 값이 0).

- [ ] **Step 7: 커밋한다**

```bash
git add duty/views/board_settings.py duty/templates/duty/board_settings.html tests/test_views_board_settings_people.py
git commit -m "feat: 근무표 설정 사람 칸 계정 발급·비밀번호 초기화(연결 남김, 여럿 한 번에, 임시 비밀번호는 응답의 결과 상자에만, 누르면 꺼지는 버튼)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 6: 글 도움말 사람 부분·스냅샷·문서

> 범위: 설계 13(4단계 몫)·10.4 의 4단계. `help.py` 의 "근무표 설정" 글에 사람 부분, 스냅샷 `help-admin` 다시 쓰기, ARCHITECTURE·OPERATIONS·OVERVIEW·PRINCIPLES.

**Files:**
- Modify: `duty/help.py`, `tests/test_help.py`, `tests/snapshots/help-admin.html`(다시 쓰기로)
- Modify: `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`, `docs/OVERVIEW.md`, `docs/PRINCIPLES.md`

- [ ] **Step 1: 실패 테스트를 쓴다** — `tests/test_help.py` 의 `test_settings_text_help_for_board_admins` 를 고친다

```diff
-    assert "근무표 설정(관리자·입력 담당자·근무 정의·단계)" not in client.get("/help/").content.decode()
+    assert "근무표 설정(사람·관리자·입력 담당자·근무 정의·단계)" not in client.get("/help/").content.decode()
     client.force_login(people["admin"])
     body = client.get("/help/").content.decode()
-    i = body.index("근무표 설정(관리자·입력 담당자·근무 정의·단계)")
+    i = body.index("근무표 설정(사람·관리자·입력 담당자·근무 정의·단계)")
     assert body.index("회차 운영(단계·출근표·생성·배포)") < i
     part = body[i:]
-    for word in ("[근무표 설정]", "나 자신과 퇴사한 관리자", "[부서 저장]", "[그래도 저장]", "회차 단계", "슈퍼유저"):
+    for word in ("[근무표 설정]", "나 자신과 퇴사한 관리자", "[부서 저장]", "[그래도 저장]", "회차 단계", "슈퍼유저",
+                 "[계정 발급]", "1:1로만", "띄어쓰기 없이", "[비밀번호 초기화]", "[다시 재직]", "관리자 계정"):
         assert word in part, word
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_help.py`
Expected: FAIL — `ValueError: substring not found`

- [ ] **Step 3: 구현한다** — `duty/help.py`

```diff
-    ("settings", "근무표 설정(관리자·입력 담당자·근무 정의·단계)", "근무표 관리자"),
+    ("settings", "근무표 설정(사람·관리자·입력 담당자·근무 정의·단계)", "근무표 관리자"),
```

`STEPS["settings"]` 의 주석을 `# 근무표 통합 3·4단계: [근무표 설정] 화면` 으로 바꾸고, 첫 줄의 "관리자·입력 담당자·근무 정의와 부서·회차 단계를" 을 "사람·관리자·입력 담당자·근무 정의와 부서·회차 단계를" 로 고친 뒤, 첫 줄 바로 다음에 아래 다섯 줄을 넣는다:

```python
        "사람: 이 근무표 부서 사람과 계정 상태(발급 전·첫 로그인 대기·사용 중)가 보입니다. 줄의 [고치기 · 비밀번호 · 퇴사]를 펼쳐 이름·구분을 고치고 [저장]을 누릅니다.",
        "새 사람은 표 아래 '사람 추가'에서 이름과 아이디를 넣습니다. 아이디 칸에는 다음 번호가 미리 들어 있고, 실명 대신 영문 소문자·숫자·_ 로 씁니다. 추가한 뒤 그 줄의 [계정 발급]을 누릅니다.",
        "[계정 발급]·[비밀번호 초기화]를 누르면 사람 칸 맨 위 빨간 상자에 임시 비밀번호가 한 번만 보입니다. 띄어쓰기 없이 입력하도록 사람마다 1:1로만 전달하고, 적기 전에는 새로고침하거나 다른 버튼을 누르지 않습니다. 여럿이면 체크해서 [선택한 사람 계정 발급]으로 한 번에 받습니다.",
        "로그인이 잠겼거나 비밀번호를 잊은 사람은 펼친 줄 안의 [비밀번호 초기화]를 누릅니다. 로그인 중인 기기는 로그아웃되고, 캘린더·텔레그램·푸시 연결은 그대로 남습니다.",
        "퇴사는 펼친 줄 안의 [퇴사]입니다. 로그인과 캘린더·텔레그램·푸시 연결이 모두 끊깁니다. 오늘 이후 근무가 남아 있으면 목록을 보여 주고 한 번 더 묻습니다(근무는 남으니 근무표·입력 표에서 다른 사람으로 바꿉니다). 실수였으면 표 아래 '퇴사한 사람'에서 [다시 재직]을 누르고 [계정 발급]을 다시 합니다.",
```

마지막 줄을 바꾼다:

```diff
-        "사람 추가·계정 발급과 비밀번호 초기화, 관리자 계정, 인사이동(부서 옮기기), 근무표 만들기는 슈퍼유저에게 부탁합니다.",
+        "관리자 계정(어느 근무표든 관리자인 계정)의 계정 발급·비밀번호 초기화·퇴사·이름 고치기, 인사이동(부서 옮기기), 근무표 만들기는 슈퍼유저에게 부탁합니다.",
```

- [ ] **Step 4: 스냅샷을 다시 쓴다**

Run: `DUTY_SNAPSHOT_WRITE=1 .venv/bin/pytest -W error -q tests/test_snapshots.py` → 일부러 FAIL("스냅샷을 다시 썼습니다")
Run: `git diff --stat tests/snapshots/` → `help-admin.html` 하나만 바뀜(다른 파일이 바뀌었으면 멈추고 원인을 찾는다)
Run: `.venv/bin/pytest -W error -q tests/test_snapshots.py tests/test_help.py` → 통과

- [ ] **Step 5: 문서를 고친다**

`docs/ARCHITECTURE.md`
- 코드 지도 `duty/services/` 줄은 그대로. 역할 표 근무표 관리자 줄의 "[근무표 설정](관리자 넣기·…)" 을 "[근무표 설정](사람(관리자 계정 제외: 추가·이름·구분 고치기·퇴사·다시 재직·계정 발급과 비밀번호 초기화), 관리자 넣기·나 자신과 퇴사자 빼기, 입력 담당자, 근무 정의와 부서, 회차 단계)" 로. 슈퍼유저 줄의 "계정 발급" 을 "계정 발급(관리자 계정의 발급·초기화·퇴사·이름 고치기는 여기서만)" 으로.
- [근무표 설정] 문단(`/settings/?board=<code>` 로 시작)의 "칸 바로가기(#admins·…)" 를 "칸 바로가기(#people·#admins·#assignees·#shifts·#steps)" 로 고치고 문단 끝에 덧붙인다: "사람 칸(`#people`, 맨 위): 그 근무표 부서 사람 표(계정 열 = 발급 전(쓸 수 있는 비밀번호 없음)·첫 로그인 대기(`must_change_password`)·사용 중), 줄마다 `<details>` 안에 이름·구분 고치기와 위험 구역([비밀번호 초기화]·[퇴사]), 접힌 퇴사자 목록([다시 재직]), 사람 추가(아이디 `[a-z][a-z0-9_]{1,29}`, 다음 빈 번호 `<code><nn>` 를 미리 넣음 `board_settings.next_username`, 구분은 켜진 장중관제 정의가 있는 근무표만). 사람 함수(`set_person`·`set_active`·`issue`)의 대상은 그 근무표 부서 사람 중 슈퍼유저·나 자신·관리자 계정(어느 근무표든)이 아닌 사람만(`board_settings.locked_ids`·`_person`, 아니면 `PermissionDenied`·뷰 404, 화면은 그 줄을 '관리자 계정은 슈퍼유저에게'로 잠근다). 퇴사는 오늘 이후 칸(`future_cells`: 그날의 주인 회차의 배포 행 + 배포 전 회차 행)이 있으면 그 줄 아래 목록과 [그래도 퇴사 처리](본 칸 수 `confirm`)를 거치고, 퇴사 뒤 칸 메시지에 링크 목록(배포된 날 = 하루 화면, 배포 전 = 입력 표). 계정 발급·초기화(`issue`, 한 트랜잭션, 퇴사자 거부)는 redirect 없이 그 자리에서 다시 그려 사람 칸 맨 위 결과 상자에 임시 비밀번호를 보인다(응답 본문에만, 세션·메시지·로그·`LogEntry` 에 없음). 일괄 발급 체크박스는 발급 전·첫 로그인 대기 줄에만(표 밖 빈 폼 `issue-many` 에 `form` 속성으로 묶음), 발급 버튼은 누르면 꺼진다(`event.submitter`)."
- "보안·개인정보" 절: 첫 줄의 "[계정 발급]으로 초기화하면 모든 로그인이 끊긴다" 는 그대로 두고, "계정 초기화(재발급)는 캘린더 구독·텔레그램·푸시 연결도 끊는다." 줄을 아래로 바꾼다: "관리 화면 액션 '계정 발급 / 비밀번호 초기화'의 초기화는 캘린더 구독·텔레그램·푸시 연결도 끊는다(탈취 의심 길). [근무표 설정]의 [비밀번호 초기화]는 연결을 남긴다(비밀번호 분실 길, `accounts.issue_account(revoke_links=False)` — 비밀번호가 바뀌어 로그인은 끊긴다). 퇴사(`accounts.deactivate`)는 재직을 끄고 쓸 수 없는 비밀번호로 모든 로그인을 끊고 연결을 모두 끊는다. 다시 재직은 재직만 켜서 [계정 발급]을 다시 해야 한다. 첫 발급(기본 알림 규칙)은 쓸 수 있는 비밀번호가 없고 로그인한 적도 없을 때만. 임시 비밀번호는 `accounts.temp_password`(헷갈리는 0·o·1·l·i 를 뺀 31자에서 `secrets.choice` 로 10자). 텔레그램은 `/start <일회용 코드>` 로만 연결한다(chat_id 직접 입력 없음)." 그리고 "[근무표 설정]에서 한 일은…" 줄 끝에 "근무표 관리자는 자기 근무표 사람 계정을 만들고 초기화한다(초기화한 비밀번호로 그 사람으로 들어갈 수 있는 것은 받아들인 위험, PRINCIPLES 2026-11-18). 관리자 계정·슈퍼유저·나 자신은 대상이 아니다." 를 덧붙인다.
- "도움말" 절의 "글 도움말 \"근무표 설정\"(`STEPS[\"settings\"]`, 근무표 관리자)은 [근무표 설정] 칸마다 할 일이다" 는 그대로(사람 칸도 칸이다).
- 데이터 절 알림 문단의 "기본 규칙(계정 첫 발급)" 을 "기본 규칙(계정 첫 발급: 쓸 수 있는 비밀번호가 없고 로그인한 적도 없을 때)" 으로.

`docs/OPERATIONS.md`
- "처음 한 번: 계정 만들기"의 "새 사람:" 줄 끝에 덧붙인다: "근무표 관리자는 사이트 [근무표 설정] → 사람에서 직접 더하고 [계정 발급]한다(아이디는 영문 소문자·숫자·_, 다음 번호가 미리 들어 있다). 관리자 계정(어느 근무표든 관리자인 계정)은 근무표 관리자가 다루지 못하니 여기 관리 화면에서 한다."
- "계정이 털렸다고 의심되면…" 줄 끝에 덧붙인다: "근무표 관리자의 [근무표 설정] [비밀번호 초기화]는 비밀번호를 잊은 사람용이라 연결을 남긴다(로그인만 끊긴다). 털림 의심은 슈퍼유저가 이 관리 화면 액션으로 한다."
- "계정 발급:" 줄의 "화면에 한 번만 보이는 임시 비밀번호를" 을 "화면에 한 번만 보이는 임시 비밀번호(헷갈리는 0·o·1·l·i 없는 영문 소문자·숫자 10자, 띄어쓰기 없음)를" 로, 줄 끝에 "근무표 관리자는 [근무표 설정] → 사람에서 같은 일을 한다(발급 전·첫 로그인 대기인 사람을 체크해 [선택한 사람 계정 발급], 비밀번호는 그 화면의 빨간 상자에만 한 번 보인다)." 를 덧붙인다.
- "한 번에 만들기(명령)"의 "이어서 3단계 끝의 계정 발급(사용자 목록 → 액션 \"계정 발급 / 비밀번호 초기화\")과" 를 "이어서 계정 발급(사용자 목록 → 액션 \"계정 발급 / 비밀번호 초기화\", 또는 근무표 관리자가 [근무표 설정] → 사람에서 체크 → [선택한 사람 계정 발급])과" 로.
- "3. 사람" 절 표 위에 한 줄: "근무표를 만든 뒤에는 근무표 관리자가 [근무표 설정] → 사람 → '사람 추가'에서 넣어도 된다(아래 칸 규칙이 같고, 구분은 장중관제가 없는 근무표면 늘 직원)."
- "운영 중에 바꾸면" 표의 "퇴사·전입" 줄을 바꾸고 두 줄을 더한다:
  ```
  | 퇴사·전입 | [근무표 설정] → 사람 → 그 줄 [고치기 · 비밀번호 · 퇴사] → [퇴사] / '사람 추가'(관리자 계정은 사용자 "재직" 끄기) | 로그인과 캘린더·텔레그램·푸시 연결이 모두 끊긴다. 오늘 이후 이미 배정된 근무는 남으므로(퇴사 때 목록이 나온다) 근무표·입력 표에서 다른 사람으로 바꾼다. 되돌리려면 '퇴사한 사람' → [다시 재직] → [계정 발급]. 전입·인사이동(부서·근무표 옮기기)은 슈퍼유저가 사용자 "부서"에서(그 사람의 개인 알림 발송 기록이 정리된다) |
  | 공동 관리자 들이기 | [근무표 설정] | 사람 추가 → [계정 발급] → 관리자 칸에서 [넣기]. 넣은 뒤에는 관리자 계정이라 사람 칸에서 고칠 수 없다(그 전에 이름을 확인한다) |
  | 관리자 퇴사 | [근무표 설정] → 관리자, 그 뒤 사람 | 그 사람이 스스로 관리자 칸에서 나를 [빼기] → 다른 관리자가 사람 칸에서 [퇴사]. 스스로 뺄 수 없으면 슈퍼유저가 관리 화면 사용자 "그룹"에서 빼고 "재직"을 끈다 |
  ```
- "운영 메모"의 "퇴사자는 사용자의 \"재직\"을 끈다." 를 "퇴사자는 근무표 관리자가 [근무표 설정] → 사람에서 [퇴사]한다(관리자 계정은 슈퍼유저가 사용자 \"재직\"을 끈다. 관리 화면에서 재직만 끄면 비밀번호·캘린더·텔레그램·푸시 연결은 남는다)." 로.
- "업그레이드·롤백"의 "근무표 통합 3단계로 올릴 때" 묶음 뒤에 더한다:
  ```
  - **근무표 통합 4단계로 올릴 때**: 마이그레이션이 없다(`migrate` 는 "No migrations to apply"). [근무표 설정] 맨 위에 사람 칸이 생겨 근무표 관리자가 사람 추가·이름·구분 고치기·퇴사·다시 재직·계정 발급과 비밀번호 초기화를 한다(관리자 계정은 대상이 아니다). 새로 발급하는 임시 비밀번호의 모양이 바뀐다(헷갈리는 글자 없는 영문 소문자·숫자 10자, 관리 화면 액션도 같다). [근무표 설정]의 초기화는 캘린더·텔레그램·푸시 연결을 남기고, 관리 화면 액션은 지금처럼 끊는다. 되돌리기는 위 "롤백"에서 코드만 되돌리면 된다(DB 구조가 같다. 그사이 설정 화면에서 만든 사람·퇴사는 그대로 남는다).
    - [근무표 설정]에서 누가 무엇을 바꿨는지는 3단계와 같이 관리 화면 그 사람 편집 페이지의 [기록](사람 추가·이름·구분 고치기·퇴사·다시 재직·계정 발급·비밀번호 초기화, 비밀번호·실명 없음)과 웹 로그 `board <코드>: <동작> <아이디> by <아이디>` 로 본다.
    - 공지(지금 쓰는 메신저로). 알릴 사람: 근무표 관리자 전원. "[근무표 설정] 맨 위에 '사람' 칸이 생겼습니다. 새 사람 추가, 이름 고치기, 퇴사, 계정 발급과 비밀번호 초기화를 여기서 직접 합니다. 임시 비밀번호는 화면의 빨간 상자에 한 번만 보이니 받아 적어 사람마다 1:1로 전해 주세요(띄어쓰기 없이 10자). 관리자 계정과 인사이동은 지금처럼 슈퍼유저에게 부탁하세요."
  ```

`docs/OVERVIEW.md`
- 역할 표 관리자 줄 "[근무표 설정](관리자·입력 담당자·…)" 을 "[근무표 설정](사람 추가·고치기·퇴사·계정 발급과 비밀번호 초기화, 관리자·입력 담당자·근무 정의와 부서 출근조·점심 시각·회차 단계)" 로. 슈퍼유저 줄 "계정 발급" 을 "관리자 계정 발급·퇴사" 로.

`docs/PRINCIPLES.md` 결정 기록 표 맨 끝에 두 줄:

```
| 2026-11-18 | 근무표 관리자가 [근무표 설정] 사람 칸에서 그 근무표 부서 사람을 더하고(아이디는 영문 소문자·숫자·_), 이름·구분을 고치고, 퇴사·다시 재직시키고, 계정을 발급·초기화한다. 대상은 슈퍼유저·나 자신·관리자 계정(어느 근무표든)이 아닌 사람만이고, 관리자 계정은 슈퍼유저가 관리 화면에서 다룬다. 계정을 만드는 권한을 근무표 관리자에게 준 것은 받아들인 위험이다(초기화한 비밀번호로 그 사람으로 들어갈 수 있다. 모든 쓰기가 로그 한 줄과 `LogEntry`(아이디만)에 남고, 본인은 다음 로그인 때 비밀번호가 바뀐 것을 안다) | 사용자 지적: 사람이 들어오거나 비밀번호를 잊을 때마다 슈퍼유저를 거치는 것이 운영 공수다. 관리자끼리 계정을 가로채지 못하게 관리자 계정을 빼고, 재직 중인 다른 관리자 빼기는 슈퍼유저만이라 "빼고 나서 초기화" 우회도 막힌다 |
| 2026-11-18 | [근무표 설정]의 비밀번호 초기화는 캘린더·텔레그램·푸시 연결을 남기고(비밀번호 분실 길, 로그인은 끊긴다) 관리 화면 액션은 지금처럼 끊는다(탈취 의심 길). 퇴사는 로그인·연결을 모두 끊고, 다시 재직은 재직만 켜서 [계정 발급]을 다시 하게 한다. 임시 비밀번호는 헷갈리는 글자(0·o·1·l·i) 없는 10자이고, 설정 화면에서는 세션 메시지가 아니라 응답 본문의 결과 상자에만 보인다. 일괄 발급 체크박스는 발급 전·첫 로그인 대기 줄에만 둔다 | 잊은 사람마다 연결을 다시 맺게 하면 공수가 늘고, 탈취 의심은 슈퍼유저 길이 남는다. 시력이 좋지 않은 사용자가 받아 적고 치기 쉬워야 한다. 평문 비밀번호를 세션 DB 에 남기지 않는다. 쓰는 중인 사람을 확인창 없이 한꺼번에 로그아웃시키지 않는다 |
```

- [ ] **Step 6: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q` → `1409 passed`
Run: `git diff --check` → 출력 없음(줄 끝 공백 없음)

- [ ] **Step 7: 브라우저로 본다**(`admin`)

[도움말] → "글 도움말"에 "근무표 설정(사람·관리자·입력 담당자·근무 정의·단계)" 열세 줄, 사람 다섯 줄이 둘째 줄부터. `manager` 로는 보이지 않는다. 390px·아주 크게에서 줄이 감기고 가로 넘침 없음.

- [ ] **Step 8: 커밋한다**

```bash
git add duty/help.py tests/test_help.py tests/snapshots/help-admin.html docs/ARCHITECTURE.md docs/OPERATIONS.md docs/OVERVIEW.md docs/PRINCIPLES.md
git commit -m "docs: 근무표 설정 사람 칸 도움말·운영 문서(4단계 올리기·공동 관리자 들이기·관리자 퇴사·퇴사와 전입)·결정 기록

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 7: 브라우저 확인(가짜 데이터, 끝나면 지움)

> Task 3~6 의 "브라우저로 본다"를 이 준비에서 한다. 마지막에 한 번 더 모두 훑는다. 실제 DB·`.env` 는 쓰지 않는다(`DUTY_ENV_FILE=` 로 `.env` 를 읽지 않고 `DUTY_DATA_DIR` 을 임시 폴더로).

- [ ] **Step 1: 띄운다**

```bash
W=$(mktemp -d -p /home/dustbox/.claude/jobs/88ab5e02/tmp)
export DUTY_ENV_FILE= DUTY_DEBUG=1 DUTY_DATA_DIR=$W/data
.venv/bin/python manage.py migrate -v0
.venv/bin/python manage.py shell < tools/help_videos/seed.py > /dev/null     # IT 가짜 데이터(계정 비밀번호 Demo-pass-123)
.venv/bin/python manage.py shell <<'EOF'
# 가짜 '운영팀' 근무표(시장운영실 모양) + 사람 칸 상태 다섯 가지. 실명 없음. seed.py 다음에 같은 임시 DB 에서만 돌린다
from datetime import time, timedelta
from duty import perms
from duty.accounts import issue_account
from duty.models import Board, BoardShift, Commute, Department, Period, User
from duty.services import periods, publish
from duty.services.generate import run_generation
admin = User.objects.get(username="admin")
ops = Board.objects.create(code="ops", name="운영팀", use_draft=False, use_close=False,
                           step_collecting="입력 중", step_generated="확정")
for key, name, h in (("dawn", "이른", 7), ("normal", "가운데", 9), ("dinner", "늦은", 11)):
    BoardShift.objects.create(board=ops, key=key, name=name, start=time(h, 30), end=time(h + 9, 0), default_alarm=True)
BoardShift.objects.create(board=ops, key="lunch", name="점심당번")
dept = Department.objects.create(code="OPS", name="운영", shifts="dawn,normal,dinner", board=ops, order=0,
                                 lunch_start=time(11, 30), lunch_end=time(12, 30))
team = [User.objects.create_user(f"OPS{i}", password="Demo-pass-123", name=n, department=dept, type="직원", help_dismissed=True)
        for i, n in enumerate("가상하나 가상두리 가상세찬 가상네모 가상다섯 가상여섯".split())]
ops.admin_group.user_set.add(admin)
mon = perms.today() - timedelta(days=perms.today().weekday())
old = periods.save_draft(Period(board=ops, name="지난 2주", start_date=mon - timedelta(days=14), end_date=mon - timedelta(days=3)), by=admin)
for x in old.dates():
    for i, m in enumerate(team):
        Commute.objects.create(period=old, date=x, member=m, shift=("dawn", "normal", "dinner")[i % 3])
run_generation(old, by=admin)
publish.publish(old, old.start_date, by=admin)
now = periods.save_draft(Period(board=ops, name="이번 2주", start_date=mon, end_date=mon + timedelta(days=11)), by=admin)
# 사람 칸 상태: 발급 전·첫 로그인 대기·퇴사·관리자 계정(IT 관리자)·남은 근무
User.objects.create_user("ops11", password=None, name="가상일곱", department=dept, type="직원")
issue_account(User.objects.create_user("ops12", password=None, name="가상여덟", department=dept, type="직원"))
User.objects.create_user("ops13", password=None, name="가상아홉", department=dept, type="직원", is_active=False)
Board.objects.get(code="it").admin_group.user_set.add(team[4])
Commute.objects.create(period=now, date=now.end_date, member=team[1], shift="normal")
print("운영팀 준비 끝")
EOF
.venv/bin/python manage.py runserver 127.0.0.1:8795 > $W/server.log 2>&1 &
echo $! > $W/server.pid
```

로그인: `admin` / `Demo-pass-123`(슈퍼유저 + IT·운영팀 관리 그룹). 사람 쪽 확인용 `OPS0`(가상하나) / `Demo-pass-123`. 주소 `http://127.0.0.1:8795/settings/?board=ops`.

- [ ] **Step 2: 본다** — PC 1400px, 휴대폰 390px, 각각 다크 모드와 글씨 아주 크게. 모든 화면에서 콘솔 `document.documentElement.scrollWidth > innerWidth` → `false`.
  - 바로가기 맨 앞 [사람], 사람 칸이 맨 위. 계정 열 "발급 전"(가상일곱)·"첫 로그인 대기"(가상여덟)·"사용 중"(OPS0~5), 가상다섯 줄은 "관리자 계정은 슈퍼유저에게"이고 체크·[고치기]가 없다. `admin`(부서 없음)은 표에 없다.
  - Task 3 Step 6, Task 4 Step 6, Task 5 Step 6, Task 6 Step 7 의 흐름.
  - 390px 카드: 체크·이름·아이디 한 줄, "부서 · 운영"·"계정 · …" 한 줄씩, 펼친 [고치기] 안 입력칸·빨간 구역이 카드 폭 안, 누름 영역 44px 이상.
  - 진한 버튼은 화면 전체에서 근무 정의와 부서 칸 아래 큰 버튼 하나뿐이다(사람 칸은 테두리·빨간 테두리만).
  - 서버 로그: `grep -c "board ops:" $W/server.log` 가 한 일 수만큼, 결과 상자에서 본 비밀번호로 `grep -c` 하면 0, `grep -c 가상 $W/server.log` 가 0.

- [ ] **Step 3: 끈다**(이 폴더만 지운다)

```bash
kill "$(cat "$W/server.pid")"; rm -rf -- "$W"; unset DUTY_ENV_FILE DUTY_DEBUG DUTY_DATA_DIR W
```

- [ ] **Step 4: 마무리 확인**

Run: `.venv/bin/pytest -W error -q` → `1409 passed`(경고 0개)
Run: `makemigrations duty --check --dry-run` → "No changes detected in app 'duty'"
Run: `git status --short` → 깨끗함(임시 파일 없음)

---

## 자체 점검(설계 12절 4단계 대조표)

| 설계 | 작업 |
|---|---|
| 3절 사람 다루기(추가·고치기·퇴사·다시 재직·발급/초기화, 관리자 계정 제외) | Task 2(서비스), Task 3~5(화면) |
| 5.7 `issue_account(user, revoke_links=True)`, 첫 발급 = 비밀번호 없음 + `last_login` 없음, 10자 `ALPHABET`·`secrets.choice`, `deactivate`, 관리 화면 액션은 끊음 | Task 1 |
| 6.2 공통 규칙(`_require_admin` 첫 줄, 트랜잭션 안 다시 읽기, 범위 밖 `PermissionDenied`·뷰 404, 로그 한 줄 + `LogEntry`, 실명·비밀번호 없음) | Task 2(`_person`·`_dept`·`_audit`), Task 5(404 테스트) |
| 6.2 `add_person`(아이디 정규식·대소문자 겹침·이름 `full_clean`·구분) / `set_person` / `set_active`(+`confirm`, `future_cells`) / `future_cells` / `issue`(한 트랜잭션, 하나라도 대상 아니면 없음) | Task 2 |
| 6.2 대상 = 그 근무표 부서 사람 중 슈퍼유저·나 자신·관리자 계정(어느 근무표든) 아님 | Task 2(`locked_ids`·`_person`), Task 3(잠긴 줄), Task 5(404) |
| 6.2 `set_active` 의 `_keep_active_admin` | 계획 2번(닿을 수 없어 두지 않음, ⚑) |
| 7.1 바로가기 [사람] | Task 3 |
| 7.2 1번: 읽기 표·계정 열 셋·체크박스·[고치기]·위험 구역 두 버튼과 확인창·남은 근무 목록과 [그래도 퇴사 처리]·퇴사 뒤 메시지와 링크·관리자 계정 줄·[계정 발급]·[선택한 사람 계정 발급]·누르면 꺼짐·결과 상자·퇴사자 목록·[다시 재직]·사람 추가(다음 빈 아이디·부서 하나면 숨김·구분)·안내 두 줄·390px 카드 | Task 3·4·5(체크박스는 계획 1번 ⚑, summary 글은 계획 12번 ⚑) |
| 7.3 사람 검사 | Task 2 |
| 8 권한(관리자 계정 제외, 계정을 만드는 권한은 받아들인 위험) | Task 2·5, 문서 Task 6 |
| 10.4 4단계 메모(공동 관리자 들이기·관리자 퇴사·퇴사와 전입, 비밀번호 모양) | Task 6(OPERATIONS) |
| 11 권한·범위·퇴사 두 번째 확인·계정(연결 남김/끊음, 다시 재직 뒤 발급 전, 규칙 두 번 없음, 글자 집합·길이, 결과 상자가 응답에만, 로그·`LogEntry` 에 비밀번호·실명 없음, 쓰기마다 한 줄) | Task 1·2·4·5 |
| 13 문서·글 도움말 사람 부분 | Task 6 |
| 14 임시 비밀번호 노출·실명 아이디 | Task 2(아이디 규칙), Task 5(응답에만·no-store), Task 6(PRINCIPLES) |

- 5단계로 넘기는 것: 여러 근무표 한 화면(9절), `RosterPref.boards`(0025), 설계 문서를 ARCHITECTURE·OVERVIEW·OPERATIONS 에 합치고 지우기.
