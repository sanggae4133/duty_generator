# 근무표 통합 5단계(여러 근무표 한 화면) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 근무표 화면(`/`)에서 큰 드롭다운 하나로 근무표 여러 개를 골라 [보기]를 누르면 날짜 칸 안에 근무표별 구역(이름표 → 날 메모 → 칸)으로 겹쳐 보인다. 고른 목록은 `RosterPref.boards`(code 목록)에 기억한다. 하루 화면(`/day/`)도 같은 순서로 구역을 쌓고, 팝업(근무 변경·메모)은 늘 근무표 하나이며 돌아갈 주소에 고른 근무표·검색·앵커를 싣는다. 근무표 하나면 화면은 지금과 글자 하나 다르지 않다(고르기 자리만 버튼 → 드롭다운). 회차 목록 근무표 열, 알림 규칙의 근무표 순서·`it_board()` 대체, 설계 문서를 본 문서들에 합치고 지운다.

**Architecture:** 고른 목록은 뷰 함수 `_selection(request, remember)` 한 곳(순서 = 내 근무표 먼저, 나머지 id 순)과 서비스 `boards.in_order`·`boards.selection_query`·`prefs.remember_boards` 가 정한다. 근무표 화면은 근무표마다 `part(b)`(쿼리는 근무표마다 몇 번) → 날짜마다 `section(p, d)` 를 부르는 **한 길**이고, 템플릿은 날짜 칸마다 `{% for s in d.sections %}{% include "duty/_section.html" %}` 를 돈다. 이름표·"보기만"·근무 없음 한 줄·앵커 같은 겹친 모양은 `multi`(둘 이상)일 때만 그린다. 하루 화면은 `_day_part`. 새 쓰기 경로는 없다(기억 저장만 `services/prefs`). 마이그레이션 0025 하나.

**Tech Stack:** Python 3.12, Django 5.2, SQLite, pytest + pytest-django, Pico.css v2.0.6(`details.dropdown`, 이미 `duty/static/vendor/`). 새 의존성 없음.

**Spec:** `docs/superpowers/specs/2026-11-17-boards-unify-design.md`(Codex 합의본). 이 계획 = 12절 "5. 여러 근무표 한 화면". 참고: 2절 "남는 IT 가정"(`it_board()`), 3절 "근무표 고르기·겹쳐 보기", 4절 용어, 5.5(RosterPref), 9절 전부, 10.2(0025)·10.4(5단계 메모·공지), 11절(스냅샷·마이그레이션·겹쳐 보기 테스트), 13절(문서 — 이 PR 에서 설계를 합치고 지운다), 14절(겹친 월간이 길다).

## 계획에서 정한 것 (설계가 정하지 않았거나 해석이 필요한 곳, 컨트롤러 검토용)

설계 9절을 다섯 관점(개발자·계획자·디자이너/HCI(시력이 좋지 않은 60세 가까운 부장)·성능(근무표 N개 × 날짜)·보안(다른 근무표 편집 금지))으로 다시 읽고 정한 것. **⚑ 표시는 설계의 글자와 다르게 하는 것**이고 까닭을 함께 적는다(실제 결함일 때만, 동작을 넓히는 것은 없다).

1. ⚑ **"근무표 하나면 글자 하나 다르지 않다"의 범위**: 고르기 자리 자체(`.seg` 버튼 → 드롭다운)와 회차 목록 근무표 열·도움말 글은 설계가 바꾸라고 한 것이라 기준 스냅샷 `roster-mine`·`roster-month`·`roster-other`(고르기 줄)·`periods`(열)·`help-admin`(글)은 바뀐다. 그 밖이 그대로인 것은 **작업 순서로** 지킨다: Task 2·3(구역 한 길·하루 화면·팝업)은 `tests/snapshots/` 를 고치지 않고 통과해야 하고, 다시 쓰기는 Task 4(고르기 줄만)·Task 5(회차 열만)·Task 6(도움말만)에서 하며 매번 `git diff` 가 그 줄뿐인지 본다. 겹친 화면을 리뷰할 수 있게 기준 셋(`roster-both`·`roster-both-month`·`day-both`)을 더한다(Task 4).
2. ⚑ **근무표 고르기 폼은 `view`·필터(`dept`·`type`·`shift`)·`hist` 를 싣지 않는다**(설계 9.1 "지금 검색·필터 값을 함께 보낸다"). `prefs.resolve` 는 `view` 가 있고 `dept` 가 없는 요청을 "필터 모두 해제"로 읽어 저장한다. 내 근무표가 없는 목록(필터 상자가 없어 값을 모름)에서 고르기 폼이 `view` 를 보내 내 근무표로 돌아오면 저장해 둔 내 필터가 지워진다. 보기·필터·변경 내역 표시는 이미 `RosterPref` 에 저장돼 있어(화면을 그릴 때마다 저장값과 같다) 안 보내면 저장값이 그대로 쓰인다. 저장하지 않는 값인 검색 이름(`q1`~`q3`, 빈 칸은 뺌)과 `date` 만 숨은 칸으로 보낸다. 설계가 원한 "근무표를 바꿔도 검색 색칠·필터가 남는다"는 그대로 지킨다(Task 4 테스트).
3. ⚑ **[보기]를 누른 뒤 드롭다운은 닫힌 채 그린다**(설계 9.1 "`pick=1` 일 때 `<details open>`"). [보기]는 "표를 보여 달라"는 버튼인데 PC 에서는 열린 목록이 표 위에 떠서 방금 고른 결과를 가리고, 390px 에서는 목록이 전체 폭으로 표를 밀어 낸다. Pico 드롭다운은 바깥을 누르면 닫히지만 그것을 아는 사용자는 적다. 닫힌 버튼 글이 "근무표: IT 당번표 + 운영팀"으로 고른 것을 그대로 보이고, 고치려면 한 번 누르면 된다. `pick=1` 은 "폼에서 골랐음"(하나도 안 골랐으면 내 근무표만, 기억 비움) 표시로만 쓴다.
4. ⚑ **앵커는 근무표를 둘 이상 골랐을 때만**(설계 9.4 "팝업 `next` 에 그 칸의 앵커"). 날짜 칸 앵커 `id="d-YYYY-MM-DD"`(날짜 링크 `<a>` 에, `<td id="today">` 와 겹치지 않게)와 `next` 끝의 `#d-…`, 하루 화면 칸 id `<code>-<칸 키>`(근무표마다 같은 칸 키가 있어 접두어가 필요하다)는 `multi` 일 때만 그린다. 근무표 하나면 지금 화면(스냅샷)과 같아야 하고 칸 길이도 지금과 같아 돌아온 자리를 잃는 문제가 지금보다 커지지 않는다. 겹친 화면의 "오늘로 스크롤" 스크립트는 주소가 `#d-` 로 오면 건너뛴다(`{% if multi %}` 안의 조건이라 하나일 때 스크립트 글자는 그대로).
5. ⚑ **[내 근무표로] 글자**(설계 9.2 "내 근무표가 목록에 없으면 '보기 전용 · 내 근무표로'"): 남의 근무표만 골랐는데 그 근무표 관리자이면(바꿀 수 있음) "보기 전용"이 거짓말이 된다. 글자 = 내 근무표가 목록에 있으면 "내 근무표만 보기", 없고 모두 보기 전용이면 "보기 전용 · 내 근무표로"(지금 글자, `roster-other` 스냅샷 그대로), 없고 바꿀 수 있는 근무표가 있으면 "내 근무표로". 버튼은 설계대로 고른 목록이 정확히 [내 근무표]가 아니면 늘 보인다(지금은 남의 근무표 관리자에게 버튼이 없었다 — 설계가 정한 변화).
6. **고른 목록 규칙**(`_selection`): `?board=` 여럿은 중복·빈 값을 버리고, 하나라도 없는 code 면 404(지금과 같다). `/` 만 `pick` 과 기억을 본다: `board` 가 있으면 그것(그리고 기억), 없고 `pick=1` 이면 내 근무표만(기억 비움), 둘 다 없으면 기억한 목록(없는 code 는 조용히 버림) → 비면 내 근무표. 순서는 늘 `boards.in_order`(내 근무표 먼저, 나머지 id 순 — 인사이동으로 내 근무표가 바뀌어도 읽을 때 다시 정렬). `RosterPref.boards` 는 그 순서의 code 목록, `[내 근무표]` 면 `[]`, 같으면 쓰지 않는다(없던 사람이 내 근무표만 보면 행을 만들지 않는다 — 지금 `remember_board` 와 같다). `/day/` 는 `?board=` 가 없으면 내 근무표 하나(알림 링크). 팝업(`/cell/`·`/memo/`)은 근무표 하나: `board` 가 둘 이상 오면 404.
7. **주소**: `boards.selection_query(chosen, home)` 은 하나면 지금 `link_query`(내 근무표면 `""`, 아니면 `?board=ops`) 그대로, 둘 이상이면 `?board=it&board=ops`. 날짜 이동·주간/월간·필터 폼 숨은 칸·하루 화면 링크가 모두 이것을 쓴다. 팝업이 돌아올 주소 `page_next` = 지금 주소에서 `pick` 만 뺀 것(`pick` 이 없으면 `request.get_full_path()` 그대로라 하나일 때 글자 그대로). 하루 화면 칸 저장의 `next` 도 `page_next`(+ 둘 이상이면 `#<code>-<칸 키>`) — 지금 `request.path + bq` 와 필터 없는 주소에서는 같은 글자이고, 필터가 붙은 주소면 그대로 돌아온다.
8. **필터는 내 근무표 구역에만**(설계 9.3 규칙 하나): 칸 거르기(`keep`·`shown`)뿐 아니라 칸 링크가 근무 변경 창에 넘기는 부서·유형 꼬리(`filter_qs`, To 후보 거르기)도 내 구역만 붙인다(남의 근무표 팝업 To 후보가 내 근무표 유형 필터로 걸러지지 않게). 필터 상자는 내 근무표가 목록에 있을 때만, 둘 이상이면 상자 맨 위에 "부서·유형·스케줄은 내 근무표에만 적용됩니다" 한 줄. "보기"(변경 내역 표시)와 검색 색칠은 모든 구역.
9. **성능**: `part(b)` 가 근무표마다 정의·배포 날·메모·권한(지난 날/오늘 이후 두 번)·관리자 여부를 한 번씩 읽고, 날짜 루프(`section`)는 쿼리를 하지 않는다. 휴장일은 한 번. `_keeper` 의 사람 표는 필터가 있을 때 한 번. 그래서 쿼리 수는 근무표 수에 비례하고 날짜 수와 무관하다 — 두 근무표 주간과 월간의 쿼리 수가 **같다**는 테스트로 지킨다(허용 오차 없음, 다르면 날짜마다 도는 쿼리를 찾아 고친다). 근무표 수 상한은 두지 않는다(운영 근무표 2~3개).
10. **보안**: 구역의 칸 링크·[메모]는 지금처럼 `perms.can_edit`·`is_board_admin` 결과일 뿐이고 서버는 그대로 `changes`(`assert_can_edit`)·`memos._require_admin` 이 막는다. 새 쓰기 경로는 없고(기억 저장은 `services/prefs`), 팝업 POST 는 늘 `?board=<그 구역>` 하나, 둘 이상 붙인 주소는 404. `next` 는 그대로 `safe_next`(같은 호스트 경로만). 근무표 이름은 자동 이스케이프(뷰에서 `" + ".join` 한 평범한 글자, `mark_safe` 없음).
11. **팝업 근무표 이름**: `boards.edit_boards(user)` = 관리하는 근무표 ∪ 내 부서의 근무표(id 집합). 둘 이상이면 근무 변경 팝업 제목·메모 팝업 제목과 성공 메시지("변경했습니다."·"사유를 저장했습니다."·"메모를 저장했습니다…"·"메모를 지웠습니다.") 앞에 "<근무표 이름> · ". 오류·경고 글에는 붙이지 않는다(설계 9.4 가 제목과 성공 메시지만 말함). 화면이 겹쳤는지와 상관없이 같은 규칙.
12. **메모**: 날 메모는 그 구역 이름표 아래. 주 메모(주간 = 표 위, 월간 = 그 주 아래)·달 메모(표 아래)는 근무표마다 따로, 둘 이상이면 앞에 "<근무표 이름> · ". 월간 주 메모 줄은 어느 구역이든 메모가 있거나 그 근무표를 관리하면 그린다(지금 `week_memo or memo_admin` 을 구역마다 본 것). 겹친 화면의 [메모] 버튼은 날짜 머리 대신 구역 이름표 끝(어느 근무표 메모인지 보이게).
13. **이름표·제목**: 이름표 `<p class="bname">`(하루 화면은 `<h3 class="bname">`) = 굵게 1.05em, 왼쪽 띠 `--pico-muted-border-color`(링크 색 아님). 바꿀 수 없는 구역(내 부서 근무표도 관리 근무표도 아님)은 끝에 작게 "보기만" — **회색으로 흐리게 하지 않는다**(굵기만 보통, 시력이 약한 사용자에게 옅은 회색은 읽히지 않는다). 제목(`cal-title`)은 둘 이상이면 날짜 범위 뒤에 고른 이름들(줄바꿈 허용). "보기 전용" 작은 글은 고른 근무표를 모두 바꿀 수 없고 [내 근무표로] 버튼이 없을 때(지금 규칙). 월간 다른 달 날짜(흐린 칸)는 지금처럼 날짜만(구역 없음).
14. **크기(HCI)**: 드롭다운 단추(`summary role="button"`)·체크박스 줄(줄 전체 `<label>`)·[보기] 둘 다 높이 48px 이상, 글씨 1.05rem(rem 이라 [가] 크게·아주 크게를 따른다), 단추 글은 줄바꿈 허용. 390px 이하에서 단추·목록 모두 한 줄 전체 폭. 목록 안 안내 글("하나도 고르지 않으면 내 근무표만 보입니다")은 .95rem 본문색. 바깥을 누르면 닫히는 것은 Pico 기본(열린 `summary::before` 덮개) — JS 없음. 새 CSS 는 `base.html` `<style>`(roster 템플릿에 넣으면 스냅샷 본문이 바뀐다).
15. **알림 규칙**(설계 2절 표·9.5): `services.alarms.rule_board` 와 `RuleForm` 의 부서 없는 계정 기본 근무표 `it_board()` → `boards.home(user)`. 보고서 규칙 근무표 고르기는 내 근무표 맨 위(`Case/When` 정렬), 아직 고르지 않은 보고서의 스케줄 기준도 내 근무표(목록 첫 줄과 같게). `RuleForm` 을 `user` 없이 만들면(테스트) 지금처럼 첫 근무표. 이 뒤 `it_board()` 를 부르는 곳은 정의와 테스트뿐(`git grep -n "it_board()" -- duty ':!duty/migrations'` 로 확인해 ARCHITECTURE 에 적는다). 테스트 73곳이 쓰므로 함수는 둔다. 관리 화면 근무표 docstring 의 "code(it_board() 가 찾는 열쇠)" 는 "code 는 주소(`?board=`)와 기억한 근무표(`RosterPref.boards`)의 열쇠"로 고친다(Task 1).
16. **0025**: `AddField RosterPref.boards`(기본 `[]`) → `RunPython`: `board` 가 있는 행만 `boards=[board.code]` → `RemoveField board`. 거꾸로: 둘 이상 기억한 행이 하나라도 있으면 `RuntimeError("…업그레이드 전 백업으로 복원하세요…")`(0018~0022 와 같은 꼴), 아니면 하나짜리를 `board` 로(code 로 찾음). 운영 DB(02c79c5 + 통합 1~4단계)의 `RosterPref` 는 `board`(SET_NULL, 내 근무표면 NULL)만 있으니 이것으로 충분하다. OPERATIONS 에 올리기 전·뒤 대조 쿼리(code·건수만, 실명 없음)를 둔다.
17. **설계 문서 합치기**(Task 6): 설계 절마다 남길 사실을 본 문서로 옮기고(표로 대조), 이미 1~4단계 PR 에서 옮긴 것은 그대로 둔다. 시험 규칙(스냅샷 다시 쓰기)은 DEVELOPMENT "테스트"에. 코드·테스트 주석의 "근무표 통합 설계 x.y" 는 고치지 않는다(지운 파일은 git 기록에 남는다) — PRINCIPLES 결정 기록에 지운 커밋과 보는 법을 한 줄로 적는다. `docs/superpowers/specs/2026-11-17-boards-unify-design.md` 를 `git rm`. 옛 설계 `2026-11-15-boards-design.md` 는 이 계획의 범위가 아니다(건드리지 않는다).
18. **테스트 파일**: 새 `tests/test_roster_multi.py`(겹쳐 보기·고르기·하루 화면·팝업, `test_board_pick.two` 픽스처 재사용), 새 `tests/test_migration_rosterpref_boards.py`. 고치는 것: `tests/test_board_pick.py`(기억 값 `board` → `boards`, 옛 `.seg` 버튼 테스트 → 드롭다운, 회차 열·알림 규칙 테스트 추가), `tests/test_snapshots.py`(겹친 화면 기준 셋), `tests/test_help.py`.

## Global Constraints

- **스냅샷 규칙**: Task 1~3 은 `tests/snapshots/*.html` 을 고치지 않고 통과한다(근무표 하나면 같은 화면 — 이 PR 의 핵심 불변). 다시 쓰기는 Task 4(roster-* 고르기 줄 + 겹친 화면 기준 셋), Task 5(`periods` 근무표 열), Task 6(`help-admin`)에서만. `DUTY_SNAPSHOT_WRITE=1` 실행은 다시 쓴 뒤 일부러 실패하고, 변수 없이 다시 돌려 통과해야 한다(값은 정확히 `"1"`). 다시 쓸 때마다 `git diff tests/snapshots/` 가 계획이 말한 줄뿐인지 보고, 아니면 멈추고 원인을 찾는다. IT 알림 문구·hash(`tests/test_alarm_texts_it.py`)는 고치지 않고 통과한다.
- 각 작업이 끝난 시점에 `.venv/bin/pytest -W error -q` 전체가 통과한다(경고 0개). 기대 테스트 수는 참고값(출발점 `feat/boards-unify-4` a6ad510 **1418 passed**).
- TDD(테스트를 먼저 쓰고 실패를 확인한 뒤 구현). DB 를 바꾸는 규칙은 `duty/services/`(기억 저장은 `prefs.remember_boards`). 뷰는 모델을 직접 고치지 않는다. 순수 모듈(`shifts`·`generator`·`csv_io`·`ics`·`alarms/`(senders 제외)·`market_days`)에는 ORM 없음(`alarms/forms.py` 는 지금도 폼이라 ORM 을 쓴다 — 그대로).
- "오늘"은 `from .. import perms` 후 `perms.today()`(테스트는 `fixed_today`). 마이그레이션은 Task 1 의 0025 하나: 그 뒤 작업마다 `DUTY_DEBUG=1 DUTY_ENV_FILE= DUTY_DATA_DIR=$(mktemp -d -p /home/dustbox/.claude/jobs/88ab5e02/tmp) .venv/bin/python manage.py makemigrations duty --check --dry-run` → "No changes detected in app 'duty'"(끝나면 그 임시 폴더만 지운다).
- **실명·비밀**: 테스트 이름은 가상("가상가" 등). `data/`, DB 파일, `.superpowers/`, `.env`, 홈의 명단 파일은 열지 않는다. 텔레그램·푸시 실제 호출 없음(이 단계는 보내는 코드를 바꾸지 않는다). OPERATIONS 쿼리는 code·건수만.
- 화면 문구·오류 메시지는 한국어. 커밋 메시지는 `feat:`/`fix:`/`docs:`/`style:` + 한국어 요약, 끝에 빈 줄 하나 뒤 아래 두 줄:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
  ```
- 새 deploy 파일·셸 스크립트·타이머 없음. 정적 파일은 CDN 없이(Pico 드롭다운은 이미 실은 `pico.min.css`). 새 CSS 는 `base.html` `<style>`.
- 화면을 바꾸는 작업(Task 2·3·4·5)은 Task 7 의 준비대로 띄운 가짜 데이터에서 PC 1400px·휴대폰 390px, 글씨 **아주 크게**(오른쪽 위 [가] 두 번), **다크 모드**(◐)로 본다. 모든 브라우저 단계에서 콘솔 `document.documentElement.scrollWidth > innerWidth` 가 `false`. 누름 영역 48px 이상(드롭다운·[내 근무표만 보기]).
- PR 은 5단계 문서와 설계 합치기·지우기를 같은 PR 에서(Task 6). 계획·구현(작업마다)·최종 Codex 리뷰(`codex exec`, 읽기 전용, DB 파일·`data/`·`.superpowers/` 를 열지 말라고 지시)를 받고 토론해 정한다. 테스트 결과 확인과 `gh pr merge` 를 한 명령으로 잇지 않는다.

## 작업 순서

브랜치: `feat/boards-unify-5`(4단계 브랜치 `feat/boards-unify-4` 위, 또는 4단계 머지 뒤 main 에서). PR 제목: `feat: 여러 근무표 한 화면(근무표 고르기 드롭다운·겹쳐 보기·기억 목록, 근무표 통합 5단계)`.

| Task | 내용 | 테스트 수(참고) |
|---|---|---|
| 1 | `RosterPref.boards` + 0025(데이터 옮김·거꾸로 규칙), `prefs.remember_boards`, `boards.in_order`·`selection_query`, `_board` 의 기억 읽기 | 1422 |
| 2 | 근무표 화면 한 길: `_selection`, `part`/`section`, `_daycell`·`_section`·`_memo` 템플릿, 겹친 주간·월간(이름표·보기만·근무 없음 한 줄·메모 이름·필터는 내 구역·앵커·[내 근무표만 보기]), 쿼리 수 테스트. 스냅샷 그대로 | 1429 |
| 3 | 하루 화면 구역(`_day_part`)과 팝업(근무표 하나, `next` 왕복·앵커, 근무표 이름 앞붙이기). 스냅샷 그대로 | 1434 |
| 4 | 근무표 고르기 드롭다운(`pick=1`, 숨은 칸, 보낸 뒤 닫힘) + 스냅샷(roster-* 고르기 줄, 겹친 화면 기준 셋) | 1438 |
| 5 | 회차 목록 근무표 열, 알림 규칙 근무표 순서·`it_board()` → `home`, 통계 `ponytail:` 주석 + 스냅샷(`periods`) | 1441 |
| 6 | 글 도움말 + 스냅샷(`help-admin`) + 문서(ARCHITECTURE·OVERVIEW·OPERATIONS·DEVELOPMENT·PRINCIPLES)에 설계 합치기 + 설계 파일 지우기 | 1441 |
| 7 | 브라우저 확인(가짜 데이터 임시 DB, 1400px·390px·다크·아주 크게) | — |

---

### Task 1: `RosterPref.boards` 와 0025 — 기억을 목록으로

> 범위: 설계 5.5·10.2 의 0025·11 의 0025 테스트. 화면은 아직 근무표 하나(기억 목록의 첫 근무표)만 그린다 — Task 2 가 목록 전체로 바꾼다.

**Files:**
- Modify: `duty/models.py`(RosterPref), `duty/services/prefs.py`, `duty/services/boards.py`, `duty/views/roster.py`(`_board`), `duty/admin.py`(근무표 docstring 한 줄)
- Create: `duty/migrations/0025_rosterpref_boards.py`
- Test: `tests/test_migration_rosterpref_boards.py`(새 파일), `tests/test_roster_multi.py`(새 파일), `tests/test_board_pick.py`(기억 값 세 줄)

**Interfaces:**
- Produces:
  - `RosterPref.boards: JSONField(default=list)` — 고른 근무표 code 목록(내 근무표 먼저, 나머지 id 순). `[]` = 내 근무표만. `RosterPref.board` 는 없어진다.
  - `prefs.remember_boards(user, chosen: list[Board], home: Board | None) -> None`
  - `boards.in_order(chosen: list[Board], home: Board | None) -> list[Board]`
  - `boards.selection_query(chosen: list[Board], home: Board | None) -> str`(하나면 `link_query` 그대로, 둘 이상이면 `?board=a&board=b`)

- [ ] **Step 1: 실패 테스트를 쓴다** — `tests/test_migration_rosterpref_boards.py`(새 파일)

```python
"""0025: 기억한 근무표 RosterPref.board → boards 목록(근무표 통합 설계 10.2, 5단계). 이름은 모두 가상."""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0024_delete_groupkeeper")]
AFTER = [("duty", "0025_rosterpref_boards")]


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_apps():
    yield _migrate(BEFORE)
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())  # 다른 테스트를 위해 최신 스키마로


def _ops(apps):
    group = apps.get_model("auth", "Group").objects.create(name="운영팀 근무표 관리")
    return apps.get_model("duty", "Board").objects.create(code="ops", name="운영팀", admin_group=group, use_draft=False,
                                                          use_close=False, step_collecting="입력 중", step_generated="확정")


def _user(apps, username):
    return apps.get_model("duty", "User").objects.create(username=username, name=f"가상{username}")


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_board_becomes_list_and_back(old_apps):
    ops = _ops(old_apps)
    Old = old_apps.get_model("duty", "RosterPref")
    a = Old.objects.create(user=_user(old_apps, "u1"), board=ops, depts=["OPS"], view="month")  # 남의 근무표를 기억
    b = Old.objects.create(user=_user(old_apps, "u2"))  # 내 근무표(기억 없음 = NULL)
    apps = _migrate(AFTER)
    New = apps.get_model("duty", "RosterPref")
    assert New.objects.get(pk=a.pk).boards == ["ops"] and New.objects.get(pk=b.pk).boards == []
    assert (New.objects.get(pk=a.pk).depts, New.objects.get(pk=a.pk).view) == (["OPS"], "month")  # 다른 값은 그대로
    assert "board" not in {f.name for f in New._meta.fields}
    back = _migrate(BEFORE)  # 하나짜리만 있으면 거꾸로 돈다
    Back = back.get_model("duty", "RosterPref")
    assert Back.objects.get(pk=a.pk).board_id == ops.pk and Back.objects.get(pk=b.pk).board_id is None


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_no_reverse_when_two_boards_remembered(old_apps):
    _ops(old_apps)
    apps = _migrate(AFTER)
    row = apps.get_model("duty", "RosterPref").objects.create(user=_user(apps, "u3"), boards=["it", "ops"])
    with pytest.raises(RuntimeError, match="백업"):
        _migrate(BEFORE)
    row.delete()  # 다른 테스트의 픽스처가 최신으로 다시 올라갈 수 있게
```

`tests/test_roster_multi.py`(새 파일, Task 2~4 가 이어서 더한다):

```python
"""여러 근무표 한 화면(근무표 통합 설계 9절, 5단계): 기억 목록·겹친 주간·월간·하루 화면·팝업·근무표 고르기.
이름은 모두 가상. two 픽스처: IT(가상다 새벽)·운영팀(가상나 새벽)이 D 에 배포, 로그인은 IT 의 가상가, 오늘 = D 앞 금요일."""
import re
from datetime import timedelta
from urllib.parse import quote

import pytest
from django.contrib.messages import get_messages
from django.utils.encoding import iri_to_uri
from django.utils.html import escape

from duty.models import Holiday, Memo, RosterPref
from duty.services import boards, prefs
from tests.test_alarm_boards import D, ops  # noqa: F401 (ops 는 픽스처)
from tests.test_board_pick import WEEK, member, two  # noqa: F401 (two 는 픽스처)

BOTH = WEEK + "&board=it&board=ops"


def test_in_order_and_selection_query(two, it_board):
    board, _, _ = two
    assert boards.in_order([board, it_board], it_board) == [it_board, board]  # 내 근무표 먼저
    assert boards.in_order([it_board, board], board) == [board, it_board]  # 운영팀 사람에게는 운영팀이 먼저
    assert boards.selection_query([it_board], it_board) == ""
    assert boards.selection_query([board], it_board) == "?board=ops"  # 하나면 지금 주소 그대로
    assert boards.selection_query([it_board, board], it_board) == "?board=it&board=ops"


def test_remember_boards_list_and_clear(two, it_board):
    board, ga, _ = two
    prefs.remember_boards(ga, [it_board], it_board)
    assert not RosterPref.objects.filter(user=ga).exists()  # 내 근무표만이면 행을 만들지 않는다
    prefs.remember_boards(ga, [it_board, board], it_board)
    assert RosterPref.objects.get(user=ga).boards == ["it", "ops"]
    prefs.remember_boards(ga, [board], it_board)
    assert RosterPref.objects.get(user=ga).boards == ["ops"]
    prefs.remember_boards(ga, [it_board], it_board)
    assert RosterPref.objects.get(user=ga).boards == []
```

`tests/test_board_pick.py` 의 기억 값 단언 세 줄을 고친다:

```diff
-    assert RosterPref.objects.get(user=ga).board == board
+    assert RosterPref.objects.get(user=ga).boards == ["ops"]
@@
-    assert RosterPref.objects.get(user=ga).board is None  # 내 근무표를 고르면 기억을 비운다
+    assert RosterPref.objects.get(user=ga).boards == []  # 내 근무표를 고르면 기억을 비운다
@@
-    assert RosterPref.objects.get(user=ga).board is None  # 그 링크(?board=내 근무표)는 기억한 근무표를 비운다
+    assert RosterPref.objects.get(user=ga).boards == []  # 그 링크(?board=내 근무표)는 기억한 근무표를 비운다
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_migration_rosterpref_boards.py tests/test_roster_multi.py tests/test_board_pick.py`
Expected: FAIL — `NodeNotFoundError`(0025 없음), `AttributeError: ... 'in_order'`, `'RosterPref' object has no attribute 'boards'`

- [ ] **Step 3: 구현한다**

`duty/models.py` — `RosterPref` 의 `board` 줄을 바꾼다:

```diff
-    board = models.ForeignKey(Board, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")  # 마지막으로 본 근무표
+    # 고른 근무표 code 목록(내 근무표 먼저, 나머지 id 순, 근무표 통합 5단계). [] = 내 근무표만.
+    # code 는 만든 뒤 바뀌지 않고 근무표는 지우지 않아 FK 대신 code. 읽을 때 없는 code 는 버린다
+    boards = models.JSONField(default=list)
```

`duty/migrations/0025_rosterpref_boards.py`(새 파일):

```python
"""기억한 근무표 RosterPref.board(FK 하나) → boards(code 목록)(근무표 통합 설계 5.5·10.2, 5단계).

- 앞으로: board 가 있는 행만 boards = [그 code]. NULL(= 내 근무표)은 기본값 [] 그대로.
- 거꾸로: 0018~0022 처럼 잃을 데이터가 있을 때만 거부한다. 근무표를 둘 이상 기억한 행이 있으면 board 하나로 나타낼 수 없어
  멈춘다(되돌리기는 업그레이드 전 백업 복원). 하나짜리는 board 로 옮긴다.
"""
from django.db import migrations, models


def forward(apps, schema_editor):
    RosterPref = apps.get_model("duty", "RosterPref")
    for p in RosterPref.objects.exclude(board=None).select_related("board"):
        p.boards = [p.board.code]
        p.save(update_fields=["boards"])


def backward(apps, schema_editor):
    RosterPref, Board = apps.get_model("duty", "RosterPref"), apps.get_model("duty", "Board")
    prefs = list(RosterPref.objects.all())
    many = sum(len(p.boards) > 1 for p in prefs)
    if many:
        raise RuntimeError(f"근무표를 둘 이상 기억한 사용자가 {many}명 있어 되돌릴 수 없습니다. 업그레이드 전 백업으로 복원하세요"
                           '(docs/OPERATIONS.md "업그레이드·롤백").')
    by_code = dict(Board.objects.values_list("code", "pk"))
    for p in prefs:
        if p.boards:
            p.board_id = by_code.get(p.boards[0])
            p.save(update_fields=["board"])


class Migration(migrations.Migration):

    dependencies = [
        ('duty', '0024_delete_groupkeeper'),
    ]

    operations = [
        migrations.AddField(
            model_name='rosterpref',
            name='boards',
            field=models.JSONField(default=list),
        ),
        migrations.RunPython(forward, backward),
        migrations.RemoveField(
            model_name='rosterpref',
            name='board',
        ),
    ]
```

`duty/services/boards.py` — 맨 위 import 에 `from urllib.parse import urlencode` 를 더하고 `board_query` 아래에 둘을 더한다:

```python
def in_order(chosen, home: Board | None) -> list[Board]:
    """고른 근무표 순서(근무표 통합 설계 9.1): 내 근무표 먼저, 나머지 id 순. 화면·기억·주소가 모두 이 순서."""
    return sorted(chosen, key=lambda b: (home is None or b.pk != home.pk, b.pk))


def selection_query(chosen: list[Board], home: Board | None) -> str:
    """고른 근무표 주소(설계 9.1). 하나면 link_query 그대로("" 또는 "?board=ops") — 근무표 하나인 화면의 링크는 글자 그대로다.
    둘 이상이면 "?board=it&board=ops"(chosen 은 in_order 순서)."""
    if len(chosen) == 1:
        return link_query(home, chosen[0])
    return "?" + urlencode([("board", b.code) for b in chosen])
```

`duty/services/prefs.py` — `remember_board` 를 바꾼다:

```python
def remember_boards(user, chosen, home) -> None:
    """근무표 화면에서 고른 목록을 기억한다(설계 5.5). chosen 은 boards.in_order 순서. [내 근무표] 하나면 비운다([]).
    기억이 이미 같으면 쓰지 않는다(없던 사용자가 내 근무표만 봐도 행을 만들지 않는다)."""
    keep = [] if home is not None and [b.pk for b in chosen] == [home.pk] else [b.code for b in chosen]
    pref = RosterPref.objects.filter(user=user).first()
    if (pref.boards if pref else []) != keep:
        RosterPref.objects.update_or_create(user=user, defaults={"boards": keep})
```

`duty/views/roster.py` — `_board` 의 기억 읽기·쓰기만 바꾼다(Task 2 가 `_selection` 으로 대신한다):

```diff
         if remember:
-            prefs.remember_board(user, board, home)  # DB 쓰기는 services(뷰는 읽기만)
+            prefs.remember_boards(user, [board], home)  # DB 쓰기는 services(뷰는 읽기만)
         return board
     if remember:
-        pref = RosterPref.objects.filter(user=user).select_related("board").first()
-        if pref and pref.board:
-            return pref.board
+        pref = RosterPref.objects.filter(user=user).first()
+        first = boards.in_order(Board.objects.filter(code__in=pref.boards), home)[:1] if pref else []
+        if first:  # Task 2 가 목록 전체를 그린다
+            return first[0]
     return home
```

`duty/admin.py` 근무표 admin docstring 의 `code(boards.it_board() 가 IT 근무표를 찾는 열쇠)` 를 `code(주소 ?board= 와 기억한 근무표 RosterPref.boards 의 열쇠)` 로 바꾼다.

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_migration_rosterpref_boards.py tests/test_roster_multi.py tests/test_board_pick.py tests/test_migration_groupkeeper.py tests/test_migration_lunch.py` → 모두 통과
Run: `makemigrations duty --check --dry-run`(Global Constraints 의 명령) → "No changes detected in app 'duty'"
Run: `.venv/bin/pytest -W error -q` → `1422 passed`(스냅샷 그대로)

- [ ] **Step 5: 커밋한다**

```bash
git add duty/models.py duty/migrations/0025_rosterpref_boards.py duty/services/prefs.py duty/services/boards.py \
        duty/views/roster.py duty/admin.py tests/test_migration_rosterpref_boards.py tests/test_roster_multi.py tests/test_board_pick.py
git commit -m "feat: 기억한 근무표를 code 목록(RosterPref.boards)으로, 마이그레이션 0025(하나짜리는 그대로 옮기고 둘 이상 기억하면 거꾸로 거부)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 2: 근무표 화면 한 길 — 겹친 주간·월간

> 범위: 설계 9.1 의 서버 읽기·기억(`getlist`·`pick`), 9.2 전부(구역·이름표·보기만·근무 없음 한 줄·칸 링크·주/달 메모 이름·제목·보기 전용·[내 근무표만 보기]·월간·모바일), 9.3(필터는 내 구역), 9.4 의 근무표 화면 쪽 `next`(앵커). 고르기 드롭다운은 Task 4(이 작업에서는 옛 `.seg` 버튼이 남고 `current` 만 목록 기준). **스냅샷을 고치지 않고 통과해야 한다.**

**Files:**
- Modify: `duty/views/roster.py`, `duty/templates/duty/roster.html`, `duty/templates/duty/_daycell.html`, `duty/templates/duty/_memo.html`, `duty/templates/duty/_filters.html`, `duty/templates/duty/base.html`(CSS)
- Create: `duty/templates/duty/_section.html`
- Test: `tests/test_roster_multi.py`

**Interfaces:**
- Consumes: Task 1 `in_order`·`selection_query`·`remember_boards`
- Produces:
  - 뷰 `_selection(request, remember=False) -> (list[Board], Board | None)`, `_page_next(request) -> str`, `_to_mine(chosen, home, view_only) -> str`
  - 템플릿 값: `multi`, `bq`(= `selection_query`), `sel_codes`(필터 폼 숨은 칸, 하나이고 내 근무표면 `[]`), `sel_names`, `page_nq`(인용한 `page_next`), `to_mine`(버튼 글자 또는 ""), `home_code`, `can_click`, 날짜 `d.sections`·`d.nq`·`d.wm_row`, 구역 `s.name`(하나면 "")·`s.bq`·`s.bqa`·`s.memo_admin`·`s.view_only`·`s.filter_qs`·`s.edit`·`s.memo`·`s.no_work`·`s.empty`·`s.week_memo`·`s.commute`·`s.duty`
  - `_filters.html` 은 `sel_codes` 로 숨은 칸을 그리고 `multi and filterable` 이면 안내 한 줄(Task 3 의 하루 화면도 같은 값을 준다)

- [ ] **Step 1: 실패 테스트를 쓴다** — `tests/test_roster_multi.py` 끝에 더한다

```python


# ── 겹친 근무표 화면(설계 9.2·9.3) ──

def _names(body):
    """구역 이름표 글(순서대로)."""
    return [x.strip() for x in re.findall(r'<p class="bname">([^<]+)', body)]


def test_list_memory_shows_both(client, two):
    _, ga, _ = two
    client.force_login(ga)
    client.get(WEEK + "&board=ops&board=it&board=ops")  # 주소 순서·중복과 상관없이
    assert RosterPref.objects.get(user=ga).boards == ["it", "ops"]  # 내 근무표 먼저 저장
    body = client.get(WEEK).content.decode()  # ?board= 가 없으면 기억한 목록
    assert "가상다" in body and "가상나" in body
    assert client.get(WEEK + "&board=it&board=nope").status_code == 404
    RosterPref.objects.filter(user=ga).update(boards=["ops", "gone"])  # 기억의 없는 code 는 버린다
    body = client.get(WEEK).content.decode()
    assert "가상나" in body and "가상다" not in body


def test_sections_in_order_with_labels(client, two):
    _, ga, _ = two
    client.force_login(ga)
    body = client.get(WEEK + "&board=ops&board=it").content.decode()
    assert _names(body) == ["IT 당번표", "운영팀"] * 5  # 날짜마다 내 근무표 먼저(주간 5일)
    assert body.count("<small>보기만</small>") == 5  # 바꿀 수 없는 운영팀 구역만
    assert '<span class="bnames">IT 당번표 + 운영팀</span>' in body  # 제목 옆 고른 이름들
    assert "보기 전용</small>" not in body  # 바꿀 수 있는 근무표(IT)가 있다
    assert '<a class="to-mine" role="button" href="/?board=it">내 근무표만 보기</a>' in body
    month = client.get(BOTH.replace("view=week", "view=month")).content.decode()
    assert len(_names(month)) == 2 * 21  # 2026년 11월 평일 21일 × 2, 다른 달 날짜에는 구역이 없다


def test_holiday_once_memos_named_and_nowork_line(client, two):
    board, ga, _ = two
    Holiday.objects.create(date=D + timedelta(days=1), name="가상 휴장")
    Memo.objects.create(board=board, scope="day", date=D, text="운영 날 메모")
    Memo.objects.create(board=board, scope="day", date=D + timedelta(days=2), text="운영 쉬는 날", no_work=True)
    Memo.objects.create(board=board, scope="week", date=D, text="운영 주 메모")
    Memo.objects.create(board=board, scope="month", date=D.replace(day=1), text="운영 달 메모")
    client.force_login(ga)
    body = client.get(BOTH).content.decode()
    assert body.count("가상 휴장") == 1  # 휴장일은 날짜 칸에 한 번(모든 근무표 공통)
    ops_label = body.index('<p class="bname">운영팀')
    assert ops_label < body.index("운영 날 메모")  # 날 메모는 그 구역 이름표 아래
    assert '<p class="nowork-line">운영 쉬는 날</p>' in body and 'class="nowork"' not in body  # 그 구역 안 한 줄
    assert "운영팀 · 주 메모</small>" in body and "운영팀 · 11월 메모</small>" in body


def test_only_editable_sections_link_with_their_board(client, two):
    board, ga, _ = two
    client.force_login(ga)
    body = client.get(BOTH).content.decode()
    nq = quote(BOTH + f"#d-{D}")  # 돌아올 주소 = 지금 화면 그대로 + 그 날짜 칸
    assert f'hx-get="/cell/{D}/dawn/?next={nq}"' in body  # IT 구역(내 근무표라 ?board= 없음)
    assert f"/day/{D}/?board=ops#dawn" not in body  # 운영팀 구역은 보기만
    assert f'id="d-{D}"' in body
    ga.groups.add(board.admin_group)  # 운영팀 관리자가 되면 그 구역도
    body = client.get(BOTH).content.decode()
    assert f'href="/day/{D}/?board=ops#dawn"' in body and f'hx-get="/cell/{D}/dawn/?next={nq}&amp;board=ops"' in body
    assert "보기만" not in body
    assert f'href="/memo/day/{D}/?board=ops"' in body  # [메모]는 그 구역 이름표 끝
    assert f'href="/day/{D}/?board=it&amp;board=ops"' in body  # 날짜 링크는 고른 목록 그대로


def test_filters_apply_to_my_section_only(client, two):
    _, ga, _ = two
    client.force_login(ga)
    client.get(WEEK + "&f=1&dept=TMCH")  # 내 근무표 필터: 가상다(MEMS)가 숨는다
    body = client.get(BOTH).content.decode()
    assert "가상다" not in body and "가상나" in body  # 운영팀 구역은 늘 전체
    assert "부서·유형·스케줄은 내 근무표에만 적용됩니다" in body
    assert '<input type="hidden" name="board" value="it"><input type="hidden" name="board" value="ops">' in body  # 필터 폼이 고른 목록 그대로
    assert "부서·유형·스케줄은 내 근무표에만" not in client.get(WEEK).content.decode()  # 하나면 지금 그대로


def test_to_mine_label_rules(client, two):
    board, ga, _ = two
    client.force_login(ga)
    assert 'class="to-mine"' not in client.get(WEEK + "&board=it").content.decode()  # 정확히 [내 근무표]
    assert ">보기 전용 · 내 근무표로</a>" in client.get(WEEK + "&board=ops").content.decode()  # 지금 글자
    ga.groups.add(board.admin_group)  # 바꿀 수 있는 남의 근무표 하나: '보기 전용'이라 하지 않는다(계획 5번)
    body = client.get(WEEK + "&board=ops").content.decode()
    assert '<a class="to-mine" role="button" href="/?board=it">내 근무표로</a>' in body and "보기 전용" not in body


def test_queries_do_not_grow_with_days(client, two):
    """쿼리는 근무표마다 몇 번이고 날짜마다 묻지 않는다(계획 9번): 두 근무표 주간과 월간의 쿼리 수가 같다."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    _, ga, _ = two
    client.force_login(ga)
    month = BOTH.replace("view=week", "view=month")
    client.get(BOTH)  # 기억·보기 저장 같은 첫 쓰기를 먼저 치운다
    with CaptureQueriesContext(connection) as week_q:
        client.get(BOTH)
    client.get(month)
    with CaptureQueriesContext(connection) as month_q:
        client.get(month)
    assert len(month_q) == len(week_q)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_roster_multi.py`
Expected: FAIL — `test_list_memory_shows_both`(가상다가 없음), `_names(...) == []` 등

- [ ] **Step 3: 구현한다 — 뷰** `duty/views/roster.py`

import 를 고친다: `from urllib.parse import quote, urlencode`, `from django.shortcuts import get_object_or_404, redirect, render`.

`_board`·`_board_ctx` 위에 셋을 더하고 `_board` 는 팝업 전용으로 줄인다(`_board_ctx` 는 Task 3 이 하루 화면을 바꿀 때 지운다 — 그동안 하루 화면이 `_filters.html` 의 `sel_codes` 를 받게 `_board_ctx` 반환값에 `"sel_codes": [board.code] if bq else []` 를 더한다):

```python
def _selection(request, remember: bool = False) -> tuple[list[Board], Board | None]:
    """고른 근무표와 내 근무표(근무표 통합 설계 9.1). 순서 = 내 근무표 먼저, 나머지 id 순(boards.in_order).
    ?board=a&board=b(중복·빈 값은 버리고 없는 code 는 404) → (근무표 화면만) pick=1 이면 내 근무표만, 아니면 기억한 목록
    (없는 code 는 버림) → 내 근무표. remember=True(근무표 화면)는 고른 목록을 기억한다([내 근무표]면 비운다).
    /day/ 는 기억을 읽지 않는다: ?board= 없는 알림 링크는 늘 내 근무표다."""
    user, home = request.user, boards.home(request.user)
    codes = [c for c in dict.fromkeys(request.GET.getlist("board")) if c]
    if codes:
        chosen = list(Board.objects.filter(code__in=codes))
        if len(chosen) != len(codes):
            raise Http404
    elif remember and not request.GET.get("pick"):
        pref = RosterPref.objects.filter(user=user).first()
        chosen = list(Board.objects.filter(code__in=pref.boards)) if pref else []
    else:
        chosen = []
    chosen = boards.in_order(chosen or [home], home)
    if remember:
        prefs.remember_boards(user, chosen, home)  # DB 쓰기는 services(뷰는 읽기만)
    return chosen, home


def _page_next(request) -> str:
    """팝업이 돌아올 주소(설계 9.4): 지금 주소 그대로에서 pick 만 뺀다(돌아온 화면이 '방금 폼에서 골랐음'이 되지 않게).
    pick 이 없으면 get_full_path() 그대로라 근무표 하나인 화면의 링크는 글자 그대로다."""
    if "pick" not in request.GET:
        return request.get_full_path()
    q = request.GET.copy()
    del q["pick"]
    return request.path + ("?" + q.urlencode() if q else "")


def _to_mine(chosen, home, view_only: bool) -> str:
    """[내 근무표만 보기] 버튼 글자(설계 9.2, 계획 5번). 고른 목록이 정확히 [내 근무표]면 ""(버튼 없음)."""
    if home is None or chosen == [home]:
        return ""
    if home in chosen:
        return "내 근무표만 보기"
    return "보기 전용 · 내 근무표로" if view_only else "내 근무표로"


def _board(request) -> Board:
    """팝업(/cell/·/memo/)의 근무표: 늘 하나(설계 9.4). ?board= 가 없으면 내 근무표, 둘 이상이면 404, 없는 code 는 404."""
    codes = [c for c in request.GET.getlist("board") if c]
    if len(codes) > 1:
        raise Http404
    return get_object_or_404(Board, code=codes[0]) if codes else boards.home(request.user)
```

`roster` 를 바꾼다(이름 읽기·`link`·주/달 계산은 그대로 두고 근무표 쪽만). 전체 모습:

```python
@login_required
def roster(request):
    names = split_names(request.GET.get("q", ""))[:3]  # 구버전 ?q=a,b,c
    names = [request.GET.get(f"q{i}", "").strip() or (names[i - 1] if i <= len(names) else "") for i in (1, 2, 3)]
    today = perms.today()
    chosen, home = _selection(request, remember=True)
    multi, sq = len(chosen) > 1, boards.selection_query(chosen, home)
    mine = home in chosen  # 부서·유형·스케줄 필터는 내 근무표 구역에만(설계 9.3). 목록에 없으면 필터 상자도 없다
    fboard = home if mine else chosen[0]  # 필터 상자를 그릴 근무표(mine 이 아니면 '보기' 칸만 그린다)
    pref = prefs.resolve(request.user, request.GET, fboard, mine=mine)
    view, depts, types, shifts, history = pref["view"], pref["depts"], pref["types"], pref["shifts"], pref["history"]
    anchor = date_param(request, "date") or today
    if not LOW <= anchor <= HIGH:  # 극단 날짜의 overflow 방지
        anchor = today
    keep, shown = _keeper(depts, types), _shown(shifts)

    def link(v: str, d: date) -> str | None:
        if not LOW <= d <= HIGH:
            return None  # 범위 밖으로 가는 링크는 만들지 않는다
        params = {"view": v, "date": d.isoformat(), **{f"q{i}": n for i, n in enumerate(names, 1) if n}, "dept": depts, "type": types, "shift": shifts}
        return (sq + "&" if sq else "?") + urlencode(params, doseq=True)

    if view == "week":
        ...  # 지금 그대로(weeks·prev_d·next_d·title)
    else:
        ...  # 지금 그대로
    first_day, last_day = weeks[0][0], weeks[-1][-1]
    closed = holidays.closed(first_day, last_day)  # 휴장일은 모든 근무표 공통이라 날짜 칸에 한 번
    page_next = _page_next(request)
    dept_qs = "".join("&" + urlencode({k: v}) for k, vs in (("dept", depts), ("type", types)) for v in vs)

    def part(b: Board) -> dict:
        """근무표 하나의 구역 재료(설계 9.2 '한 길'). 쿼리는 근무표마다 몇 번뿐이고 날짜마다 묻지 않는다(계획 9번)."""
        is_home, bq = b == home, boards.link_query(home, b)
        bqa = "&" + bq[1:] if bq else ""
        admin = perms.is_board_admin(request.user, b)
        return {
            "defs": boards.defs(b),
            "keep": keep if is_home else _keeper([], []), "shown": shown if is_home else _shown([]),
            # 칸 링크 권한: 날짜마다 묻지 않고 지난 날·오늘 이후 두 번만 묻는다
            "edit_past": perms.can_edit(request.user, b, today - timedelta(days=1)),
            "edit_now": perms.can_edit(request.user, b, today),
            "by_date": {x.date: x for x in published_days(b, first_day, last_day)},
            "notes": memos.for_range(b, first_day, last_day),  # 메모는 회차가 아니라 (근무표, 날짜)에 붙는다
            "meta": {"name": b.name if multi else "", "code": b.code, "bq": bq, "bqa": bqa, "memo_admin": admin,
                     "view_only": b != boards.board_of(request.user) and not admin,
                     # 근무 변경 창 To 후보를 거를 부서·유형 꼬리도 내 근무표 구역만(계획 8번)
                     "filter_qs": (dept_qs if is_home else "") + bqa},
        }

    parts = [part(b) for b in chosen]

    def section(p: dict, d: date, other: bool) -> dict:
        found, keep_, shown_, defs = p["by_date"].get(d), p["keep"], p["shown"], p["defs"]
        cells = {
            x.key: {
                "key": x.key, "slot": is_slot_cell(x.key), "label": x.name,
                "lines": _lines(_visible([lb for lb in found.cells[x.key].labels if keep_(lb)], _why(found, x.key), history),
                                names, reasons=_why(found, x.key)) if found else [],
                "removed": _lines([lb for lb in found.cells[x.key].removed if keep_(lb)], names, True) if found and history else [],
            }
            for x in display_order(defs) if shown_(x.key)
        }
        note = p["notes"]["day"].get(d)
        no_work = bool(note and note.no_work)
        return {
            **p["meta"], "memo": note.text if note else "", "no_work": no_work, "empty": found is None,
            "week_memo": p["notes"]["week"].get(d),  # 월요일 칸에만 붙는다(week.0 = 그 주 월요일)
            # 배포된 근무표가 있는 날만, 근무 없음 날은 못 바꾼다
            "edit": (p["edit_past"] if d < today else p["edit_now"]) and not other and found is not None and not no_work,
            "commute": [cells[x.key] for x in shift_defs(defs) + lunch_defs(defs) if x.key in cells],  # 근무조 → 점심당번
            "duty": [{"time": cells[x.key]["label"][:5], **cells[x.key]} for x in slot_defs(defs) if x.key in cells],
        }

    def day_info(d: date) -> dict:
        other = view == "month" and d.month != anchor.month
        secs = [section(p, d, other) for p in parts]
        return {
            "date": d, "is_today": d == today, "other": other, "holiday": closed.get(d, ""), "sections": secs,
            # 팝업이 돌아올 주소. 둘 이상이면 그 날짜 칸으로(계획 4번)
            "nq": quote(page_next + (f"#d-{d.isoformat()}" if multi else "")),
            "wm_row": any(s["week_memo"] or s["memo_admin"] for s in secs),  # 월간: 그 주 메모 줄
        }

    days = [[day_info(d) for d in w] for w in weeks]
    months = sorted({d.replace(day=1) for w in weeks for d in w if view == "week" or d.month == anchor.month})
    all_boards = list(Board.objects.order_by("id"))
    view_only = all(p["meta"]["view_only"] for p in parts)
    ctx = {
        "view": view, "title": title, "names": names, "date": anchor, "today_link": (link(view, today) or f"?view={view}&date={today.isoformat()}") + "#today",
        "prev": link(view, prev_d), "next": link(view, next_d),
        "week_link": link("week", anchor), "month_link": link("month", anchor),
        # 근무표 고르기(Task 4 에서 드롭다운으로 바꾼다)
        "board_links": [{"name": b.name, "current": b in chosen,
                         "href": "?" + urlencode({"board": b.code, "view": view, "date": anchor.isoformat()})}
                        for b in all_boards] if len(all_boards) > 1 else [],
        "multi": multi, "bq": sq, "sel_codes": [b.code for b in chosen] if sq else [],
        "sel_names": " + ".join(b.name for b in chosen), "page_nq": quote(page_next),
        "view_only": view_only, "to_mine": _to_mine(chosen, home, view_only), "home_code": home.code if home else "",
        "can_click": any(s["edit"] for d in (days[0][0], days[0][4]) for s in d["sections"]),  # 범례 '칸을 누르면…'
        "weeks": days,
        "month_memos": [{"date": m, "memo": p["notes"]["month"].get(m), "p": p["meta"]} for m in months for p in parts],
    }
    ctx.update(_filter_ctx(fboard, parts[chosen.index(fboard)]["defs"], depts, types, shifts, history, mine))
    return render(request, "duty/roster.html", ctx)
```

`_filter_ctx` 는 그대로 쓴다(`filterable` = `mine`). 구 `day_cells`·`day_info`·`edit_past`/`edit_now`·`by_date`·`notes`·`filter_qs`·`memo_admin`·`bc` 지역 값은 위로 대신하고 지운다.

- [ ] **Step 4: 구현한다 — 템플릿**

`duty/templates/duty/_daycell.html`(전체):

```django
<a{% if multi %} id="d-{{ d.date|date:'Y-m-d' }}"{% endif %} href="{% url 'day' d.date %}{{ bq }}"><strong>{% if view == "week" %}{{ d.date.month }}/{{ d.date.day }} ({{ d.date|date:"D"|slice:":1" }}){% else %}{{ d.date.day }}{% endif %}</strong></a>{% if not multi and not d.other %}{% with s=d.sections.0 %}{% if s.memo_admin %} <a class="memo-btn" href="{% url 'memo' 'day' d.date %}{{ s.bq }}" hx-get="{% url 'memo' 'day' d.date %}?next={{ d.nq }}{{ s.bqa }}" hx-target="#dlg-body" aria-label="{{ d.date|date:'n/j' }} 메모">[메모]</a>{% endif %}{% endwith %}{% endif %}
{% if d.holiday and not d.other %}<p class="hol">{{ d.holiday }}</p>{% endif %}
{% if not d.other %}{% for s in d.sections %}{% include "duty/_section.html" %}{% endfor %}{% endif %}
```

`duty/templates/duty/_section.html`(새 파일 — 지금 `_daycell.html` 의 날 메모·근무 없음·칸 부분을 구역 값 `s` 로 옮긴 것. 겹친 모양은 `multi` 일 때만):

```django
{% if multi %}<div class="bsec"><p class="bname">{{ s.name }}{% if s.view_only %} <small>보기만</small>{% endif %}{% if s.memo_admin %} <a class="memo-btn" href="{% url 'memo' 'day' d.date %}{{ s.bq }}" hx-get="{% url 'memo' 'day' d.date %}?next={{ d.nq }}{{ s.bqa }}" hx-target="#dlg-body" aria-label="{{ s.name }} {{ d.date|date:'n/j' }} 메모">[메모]</a>{% endif %}</p>{% endif %}
{% if s.memo and not s.no_work %}<p class="memo">{{ s.memo|linebreaksbr }}</p>{% endif %}
{% if s.no_work %}<p class="{% if multi %}nowork-line{% else %}nowork{% endif %}">{{ s.memo|default:"근무 없음"|linebreaksbr }}</p>{% elif s.empty %}<p class="none">근무표 없음</p>{% else %}
{% for c in s.commute %}<div class="sec"><b class="sh">{{ c.label }}</b>
  {% if s.edit %}<a class="cell" href="{% url 'day' d.date %}{{ s.bq }}#{{ c.key }}" hx-get="{% url 'cell' d.date c.key %}?next={{ d.nq }}{{ s.filter_qs }}" hx-target="#dlg-body" aria-label="{% if multi %}{{ s.name }} {% endif %}{{ d.date|date:'n/j' }} {{ c.label }} 바꾸기">{% include "duty/_cellbody.html" %}</a>{% else %}{% for line in c.lines %}{% include "duty/_line.html" %}{% endfor %}{% endif %}
  {% for line in c.removed %}<div>{% include "duty/_labels.html" %}</div>{% endfor %}</div>{% endfor %}
{% if s.duty %}<div class="sec slot"><b class="sh">관제</b>
  {% for c in s.duty %}{% if c.lines or c.removed or s.edit %}<div>{% if s.edit %}<a class="cell" href="{% url 'day' d.date %}{{ s.bq }}#{{ c.key }}" hx-get="{% url 'cell' d.date c.key %}?next={{ d.nq }}{{ s.filter_qs }}" hx-target="#dlg-body" aria-label="{% if multi %}{{ s.name }} {% endif %}{{ d.date|date:'n/j' }} 관제 {{ c.label }} 바꾸기">{% endif %}{{ c.time }} {% for line in c.lines %}{% include "duty/_labels.html" %}{% if not forloop.last %}, {% endif %}{% empty %}{% if s.edit %}<span class="add">+</span>{% endif %}{% endfor %}{% if s.edit %}</a>{% endif %}{% for line in c.removed %} {% include "duty/_labels.html" %}{% endfor %}</div>{% endif %}{% endfor %}</div>{% endif %}
{% endif %}{% if multi %}</div>{% endif %}
```

`duty/templates/duty/_memo.html`(전체 — 구역 값 `p` 를 받는다. `p.name` 은 하나일 때 ""):

```django
{% if m or p.memo_admin %}<div class="memo-note{% if m %} filled{% endif %}"><small>{% if p.name %}{{ p.name }} · {% endif %}{% if scope == "week" %}{% if dated %}{{ md|date:"n/j" }} 주 메모:{% else %}주 메모{% endif %}{% else %}{{ md.month }}월 메모{% endif %}</small>{% if m %} <span>{{ m.text|linebreaksbr }}</span>{% endif %}{% if p.memo_admin %} <a class="memo-btn" href="{% url 'memo' scope md %}{{ p.bq }}" hx-get="{% url 'memo' scope md %}?next={{ page_nq }}{{ p.bqa }}" hx-target="#dlg-body">[메모]</a>{% endif %}</div>{% endif %}
```

`duty/templates/duty/roster.html` 에서 바꾸는 줄:

```diff
-  <h3 class="cal-title">{{ title }}{% if view_only and not home_code %} <small>보기 전용</small>{% endif %}</h3>
-  {% if home_code %}<a class="to-mine" role="button" href="/?board={{ home_code }}">보기 전용 · 내 근무표로</a>{% endif %}
+  <h3 class="cal-title">{{ title }}{% if multi %} <span class="bnames">{{ sel_names }}</span>{% endif %}{% if view_only and not to_mine %} <small>보기 전용</small>{% endif %}</h3>
+  {% if to_mine %}<a class="to-mine" role="button" href="/?board={{ home_code }}">{{ to_mine }}</a>{% endif %}
@@
-{% if view == 'week' %}{% include "duty/_memo.html" with scope="week" md=weeks.0.0.date m=weeks.0.0.week_memo %}{% endif %}
+{% if view == 'week' %}{% for s in weeks.0.0.sections %}{% include "duty/_memo.html" with scope="week" md=weeks.0.0.date m=s.week_memo p=s %}{% endfor %}{% endif %}
@@
-    {% if view == 'month' %}{% if week.0.week_memo or memo_admin %}<tr class="wmemo"><td colspan="5">{% include "duty/_memo.html" with scope="week" md=week.0.date m=week.0.week_memo dated=True %}</td></tr>{% endif %}{% endif %}
+    {% if view == 'month' %}{% if week.0.wm_row %}<tr class="wmemo"><td colspan="5">{% for s in week.0.sections %}{% include "duty/_memo.html" with scope="week" md=week.0.date m=s.week_memo dated=True p=s %}{% endfor %}</td></tr>{% endif %}{% endif %}
@@
-{% for mm in month_memos %}{% include "duty/_memo.html" with scope="month" md=mm.date m=mm.memo %}{% endfor %}
-{% if history %}<p class="legend">…{% if weeks.0.0.edit or weeks.0.4.edit %} · 칸을 누르면 바꿀 수 있습니다{% endif %}</small></p>{% endif %}
+{% for mm in month_memos %}{% include "duty/_memo.html" with scope="month" md=mm.date m=mm.memo p=mm.p %}{% endfor %}
+{% if history %}<p class="legend">…{% if can_click %} · 칸을 누르면 바꿀 수 있습니다{% endif %}</small></p>{% endif %}
@@
-  if (today) {
+  if (today{% if multi %} && !location.hash.startsWith("#d-"){% endif %}) {  // 겹친 화면: 팝업에서 돌아온 날짜 칸을 그대로 둔다
```

(범례 `…` 는 지금 글 그대로.)

`duty/templates/duty/_filters.html` 첫 줄과 필터 칸 앞:

```diff
-<input type="hidden" name="f" value="1">{% if bq %}<input type="hidden" name="board" value="{{ board_code }}">{% endif %}
+<input type="hidden" name="f" value="1">{% for c in sel_codes %}<input type="hidden" name="board" value="{{ c }}">{% endfor %}
 {% if not nested %}<details class="filters"><summary>필터{% if filter_on %} <span class="on">적용 중</span>{% endif %}</summary><div class="filters-body">{% endif %}
+  {% if multi and filterable %}<p class="hint mine-only">부서·유형·스케줄은 내 근무표에만 적용됩니다</p>{% endif %}
```

`duty/templates/duty/base.html` `<style>` 의 `.memo-btn` 줄 아래에 더한다:

```css
    /* 여러 근무표 겹쳐 보기(둘 이상 골랐을 때만 그린다, 근무표 통합 5단계): 구역 = 이름표 → 날 메모 → 칸.
       이름표 띠는 중립색(링크 색이면 눌리는 것처럼 보인다), '보기만'은 흐리게 하지 않는다(시력이 약한 사용자) */
    .bname { margin: .35rem 0 .1rem; padding-left: .4rem; border-left: 4px solid var(--pico-muted-border-color); font-size: 1.05em; font-weight: 700; color: var(--pico-color); }
    .bname small { font-size: .9em; font-weight: 400; }
    .bsec + .bsec { margin-top: .4rem; padding-top: .2rem; border-top: 1px solid var(--duty-line); }
    .nowork-line { margin: .2rem 0 0; font-weight: 700; }
    .cal-title .bnames { white-space: normal; font-size: 1rem; font-weight: 400; }
    a[id^="d-"] { scroll-margin-top: 2.6rem; }
    form.search .mine-only { margin: 0; font-size: .95rem; opacity: 1; }
```

- [ ] **Step 5: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_roster_multi.py tests/test_board_pick.py tests/test_roster.py tests/test_views_roster.py tests/test_roster_prefs.py tests/test_snapshots.py` → 모두 통과(**스냅샷을 고치지 않고**. 실패하면 하나일 때 글자가 바뀐 것이니 템플릿을 고친다 — 기준을 다시 쓰지 않는다)
Run: `.venv/bin/pytest -W error -q` → `1429 passed`

- [ ] **Step 6: 브라우저로 본다**(Task 7 의 준비, `member` 와 `admin`)

`/?board=it&board=ops`(주소로 고른다 — 드롭다운은 Task 4): 날짜 칸마다 "IT 당번표" → "운영팀" 이름표(왼쪽 회색 띠), 운영팀 구역 끝 "보기만", 휴장일 한 번, 운영팀 날 메모가 그 구역 안, 근무 없음 날은 운영팀 구역 안 굵은 한 줄(회색 큰 상자 아님), 표 위 "운영팀 · 주 메모", 제목 옆 "IT 당번표 + 운영팀", 큰 [내 근무표만 보기]. IT 칸을 눌러 바꾸고 저장 → 같은 두 근무표 화면의 그 날짜 칸으로 돌아온다. 월간: 모든 구역이 이름표로 시작, 다른 달 날짜는 날짜만. 390px 주간: 하루 카드 안에 구역이 쌓이고 가로 넘침 없음. 다크·아주 크게: 이름표 띠가 보이고 "보기만"이 본문색. `/?board=it` 화면이 Task 1 전과 똑같아 보인다.

- [ ] **Step 7: 커밋한다**

```bash
git add duty/views/roster.py duty/templates/duty/roster.html duty/templates/duty/_daycell.html duty/templates/duty/_section.html \
        duty/templates/duty/_memo.html duty/templates/duty/_filters.html duty/templates/duty/base.html tests/test_roster_multi.py
git commit -m "feat: 근무표 화면에서 근무표 여러 개를 날짜 칸 안 구역으로 겹쳐 보기(이름표·보기만·근무 없음 한 줄·메모 이름, 필터는 내 근무표 구역만, 근무표 하나면 지금 화면 그대로)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 3: 하루 화면 구역과 팝업

> 범위: 설계 9.4 전부(하루 화면 구역, 팝업은 근무표 하나, `next` 왕복과 앵커, 팝업 근무표 이름). **스냅샷을 고치지 않고 통과해야 한다**(`day` 기준은 근무표 하나).

**Files:**
- Modify: `duty/views/roster.py`(`day`·`cell`·`memo`, `_board_ctx` 지움), `duty/templates/duty/day.html`, `duty/templates/duty/_cell_form.html`, `duty/templates/duty/base.html`(하루 화면 이름표 한 줄), `duty/services/boards.py`(`edit_boards`)
- Test: `tests/test_roster_multi.py`

**Interfaces:**
- Consumes: Task 2 `_selection`·`_page_next`·`_to_mine`·`_board`
- Produces: `boards.edit_boards(user) -> set[int]`, 뷰 `_day_part(...)`·`_prefix(user, board) -> str`, 하루 화면 값 `parts`(근무표마다 `name`·`code`·`defs`·`bq`·`bqa`·`memo_admin`·`view_only`·`found`·`note`·`editable`·`sections`), 팝업 값 `prefix`

- [ ] **Step 1: 실패 테스트를 쓴다** — `tests/test_roster_multi.py` 끝에 더한다

```python


# ── 하루 화면과 팝업(설계 9.4) ──

def test_day_two_boards(client, two):
    _, ga, _ = two
    client.force_login(ga)
    client.get(WEEK + "&f=1&dept=TMCH")  # 내 근무표 필터는 내 구역에만
    body = client.get(f"/day/{D}/?board=ops&board=it").content.decode()
    it_at, ops_at = body.index('<h3 class="bname">IT 당번표'), body.index('<h3 class="bname">운영팀')
    assert it_at < ops_at  # 내 근무표 먼저
    it_part, ops_part = body[it_at:ops_at], body[ops_at:]
    assert 'id="ops-dawn"' in ops_part and "가상나" in ops_part and "보기만" in ops_part
    assert "바꾸기</summary>" not in ops_part  # 바꿀 수 없는 구역
    assert "가상다" not in it_part  # TMCH 필터
    assert f'href="/day/2026-11-13/?board=it&amp;board=ops&amp;f=1' in body  # 앞 날짜도 고른 목록 그대로
    assert '<input type="hidden" name="board" value="it"><input type="hidden" name="board" value="ops">' in body


def test_day_cell_next_has_selection_and_anchor(client, two):
    board, ga, na = two
    ga.groups.add(board.admin_group)
    client.force_login(ga)
    body = client.get(f"/day/{D}/?board=it&board=ops").content.decode()
    assert f'value="/day/{D}/?board=it&amp;board=ops#ops-dawn"' in body  # 저장 뒤 이 화면의 그 칸으로
    assert f'action="/cell/{D}/dawn/?board=ops"' in body  # POST 는 그 구역 근무표 하나


def test_popup_next_round_trip_and_safe(client, two):
    _, ga, _ = two
    nb = member("it03", "가상라", ga.department)
    client.force_login(ga)
    back = BOTH + f"&q1=가상다#d-{D}"
    form = client.get(f"/cell/{D}/dawn/?next={quote(back)}").content.decode()
    assert f'name="next" value="{escape(back)}"' in form
    r = client.post(f"/cell/{D}/dawn/", {"before": "it02", "after": nb.username, "next": back})
    assert r.status_code == 302 and r.url == iri_to_uri(back)  # 고른 근무표·검색·앵커가 그대로(Location 은 한글을 %인코딩)
    r = client.post(f"/cell/{D}/dawn/", {"before": nb.username, "after": "it02", "next": "https://evil.example/"})
    assert r.url == f"/day/{D}/"  # 밖 주소는 safe_next 가 버린다


def test_popup_is_one_board(client, two):
    _, ga, _ = two
    client.force_login(ga)
    assert client.get(f"/cell/{D}/dawn/?board=it&board=ops").status_code == 404
    assert client.get(f"/memo/day/{D}/?board=it&board=ops").status_code == 404


def test_popup_board_name_when_two_editable(client, two):
    board, ga, na = two
    client.force_login(ga)
    assert "IT 당번표 · " not in client.get(f"/cell/{D}/dawn/").content.decode()  # 바꿀 수 있는 근무표가 하나
    ga.groups.add(board.admin_group)
    assert "운영팀 · 2026-11-16" in client.get(f"/cell/{D}/dawn/?board=ops").content.decode()
    assert "운영팀 · 11/16 주 메모" in client.get(f"/memo/week/{D}/?board=ops").content.decode()
    nb = member("op02", "가상마", na.department)
    r = client.post(f"/cell/{D}/dawn/?board=ops", {"before": na.username, "after": nb.username})
    assert "운영팀 · 변경했습니다." in [str(m) for m in get_messages(r.wsgi_request)]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_roster_multi.py -k "day_ or popup"`
Expected: FAIL — 하루 화면에 `bname` 없음, 둘 붙인 팝업이 200, 제목에 근무표 이름 없음

- [ ] **Step 3: 구현한다**

`duty/services/boards.py` — `board_query` 아래:

```python
def edit_boards(user) -> set[int]:
    """내가 바꿀 수 있는 근무표 id(근무표 통합 설계 9.4): 관리하는 근무표 ∪ 내 부서의 근무표. 둘 이상이면 팝업에 근무표 이름."""
    mine = board_of(user)
    return set(perms.admin_boards(user).values_list("pk", flat=True)) | ({mine.pk} if mine else set())
```

`duty/views/roster.py` — `_board_ctx` 를 지우고 `day` 를 바꾼다:

```python
def _day_part(request, board: Board, d: date, home, multi: bool, page_next: str, history: bool, flt) -> dict:
    """하루 화면의 근무표 하나(설계 9.4). flt = (부서, 유형, 스케줄): 내 근무표 구역만 받고 나머지는 빈 목록(= 전체)."""
    depts, types, shifts = flt
    defs = boards.defs(board)
    found = find_day(board, d)
    note = memos.for_range(board, d, d)["day"].get(d)
    no_work = bool(note and note.no_work)  # 근무 없음 날은 칸 대신 메모 글만, 바꾸기 없음
    admin = perms.is_board_admin(request.user, board)
    members = _active_members(board, depts, types)
    keep, shown = _keeper(depts, types), _shown(shifts)
    bq = boards.link_query(home, board)
    sections = []
    if found and not no_work:
        for k in filter(shown, [x.key for x in display_order(defs)]):  # 출근조 먼저, 관제는 뒤에 묶어서
            ctx = _cell_context(defs, found, k, d, depts, types, members)
            ctx.update(
                next=page_next + (f"#{board.code}-{k}" if multi else ""),  # 저장 뒤 이 화면 그대로(둘 이상이면 그 칸으로)
                items=_items(_visible([x for x in found.cells[k].labels if keep(x)], _why(found, k), history), [],
                             reasons=_why(found, k)),
                removed_items=_items([x for x in found.cells[k].removed if keep(x)], [], True) if history else [],
            )
            sections.append(ctx)
    return {"name": board.name, "code": board.code, "defs": defs, "bq": bq, "bqa": "&" + bq[1:] if bq else "",
            "memo_admin": admin, "view_only": board != boards.board_of(request.user) and not admin,
            "found": found, "note": note, "editable": perms.can_edit(request.user, board, d) and not no_work,
            "sections": sections}


@login_required
def day(request, d):
    chosen, home = _selection(request)  # 기억은 읽지 않는다(?board= 없는 알림 링크는 내 근무표)
    multi, sq = len(chosen) > 1, boards.selection_query(chosen, home)
    mine = home in chosen
    fboard = home if mine else chosen[0]
    pref = prefs.resolve(request.user, request.GET, fboard, with_view=False, mine=mine)
    depts, types, shifts, history = pref["depts"], pref["types"], pref["shifts"], pref["history"]
    page_next = _page_next(request)
    parts = [_day_part(request, b, d, home, multi, page_next, history,
                       (depts, types, shifts) if b == home else ([], [], [])) for b in chosen]
    view_only = all(p["view_only"] for p in parts)
    qs = "?" + urlencode([("board", b.code) for b in chosen if sq] + [("f", 1)] + [("dept", x) for x in depts]
                         + [("type", x) for x in types] + [("shift", x) for x in shifts])
    return render(request, "duty/day.html", {
        "d": d, "weekday": DAY_LABELS[d.weekday()], "parts": parts, "multi": multi,
        "holiday": holidays.closed(d, d).get(d, ""), "prev": _neighbor(d, -1), "next_day": _neighbor(d, 1), "qs": qs,
        "bq": sq, "sel_codes": [b.code for b in chosen] if sq else [], "page_nq": quote(page_next),
        "view_only": view_only, "to_mine": _to_mine(chosen, home, view_only), "home_code": home.code if home else "",
        **_filter_ctx(fboard, parts[chosen.index(fboard)]["defs"], depts, types, shifts, history, mine),
    })
```

`cell`·`memo` — 근무표 이름 앞붙이기(`_board` 는 Task 2 에서 팝업 전용이 됐다):

```python
def _prefix(user, board) -> str:
    """팝업 제목·성공 글 앞의 '<근무표 이름> · '(설계 9.4): 내가 바꿀 수 있는 근무표가 둘 이상일 때만."""
    return f"{board.name} · " if len(boards.edit_boards(user)) > 1 else ""
```

`cell` 에서: `prefix = _prefix(request.user, board)` 를 `defs` 아래에 두고, `messages.success(request, prefix + ("사유를 저장했습니다." if reason_form else "변경했습니다."))`, `ctx.update(next=..., bq=bq, prefix=prefix)`.
`memo` 에서: `prefix = _prefix(request.user, board)`, 성공 글 `messages.success(request, prefix + msg)`, 렌더 값 `"title": prefix + {...}[scope]`.

`duty/templates/duty/_cell_form.html` 첫 제목 줄:

```diff
-  {% if not inline %}<p><strong>{{ d|date:"Y-m-d" }} {% if slot %}장중관제 {% endif %}{{ label }}</strong></p>{% endif %}
+  {% if not inline %}<p><strong>{{ prefix }}{{ d|date:"Y-m-d" }} {% if slot %}장중관제 {% endif %}{{ label }}</strong></p>{% endif %}
```

(`_memo_form.html` 은 `{{ title }}` 을 그대로 쓰므로 바꿀 것 없음.)

`duty/templates/duty/day.html`(전체 — 하나일 때는 지금과 같은 순서·글자):

```django
{% extends "duty/base.html" %}
{% block content %}
<nav aria-label="날짜 이동">
  <ul><li><a href="{% url 'day' prev %}{{ qs }}">◀</a></li></ul>
  <ul><li><strong>{{ d|date:"Y-m-d" }} ({{ weekday }})</strong>{% if view_only and not to_mine %} <small>보기 전용</small>{% endif %}</li></ul>
  <ul><li><a href="{% url 'day' next_day %}{{ qs }}">▶</a></li></ul>
</nav>
{% if to_mine %}<p><a class="to-mine" role="button" href="/?board={{ home_code }}&amp;date={{ d|date:'Y-m-d' }}">{{ to_mine }}</a></p>{% endif %}
{% if holiday %}<p class="hol">{{ holiday }}</p>{% endif %}
{% if not multi %}{% with p=parts.0 %}
{% if p.note and not p.note.no_work %}<p class="memo">{{ p.note.text|linebreaksbr }}</p>{% endif %}
{% if p.memo_admin %}<p><a class="memo-btn" href="{% url 'memo' 'day' d %}{{ p.bq }}" hx-get="{% url 'memo' 'day' d %}?next={{ page_nq }}{{ p.bqa }}" hx-target="#dlg-body">[메모]</a></p>{% endif %}
{% endwith %}{% endif %}
<form method="get" class="search">
  {% include "duty/_filters.html" %}
</form>
{% for p in parts %}
{% if multi %}<section class="bsec"><h3 class="bname">{{ p.name }}{% if p.view_only %} <small>보기만</small>{% endif %}{% if p.memo_admin %} <a class="memo-btn" href="{% url 'memo' 'day' d %}{{ p.bq }}" hx-get="{% url 'memo' 'day' d %}?next={{ page_nq }}{{ p.bqa }}" hx-target="#dlg-body" aria-label="{{ p.name }} 메모">[메모]</a>{% endif %}</h3>
{% if p.note and not p.note.no_work %}<p class="memo">{{ p.note.text|linebreaksbr }}</p>{% endif %}{% endif %}
{% if p.note.no_work %}<p class="{% if multi %}nowork-line{% else %}nowork{% endif %}">{{ p.note.text|default:"근무 없음"|linebreaksbr }}</p>{% elif not p.found %}<p>배포된 근무표에 없는 날짜입니다.</p>{% endif %}
{% for s in p.sections %}
{% ifchanged s.slot s.lunch %}<h4 class="grp">{% if s.slot %}장중관제{% elif s.lunch %}당번{% else %}출근조{% endif %}</h4>{% endifchanged %}
<article id="{% if multi %}{{ p.code }}-{% endif %}{{ s.cell }}" class="dcell">
  <strong>{{ s.label }}</strong>
  <p>{% with line=s.items %}{% include "duty/_labels.html" %}{% endwith %}{% if not s.items %}-{% endif %}{% if s.removed_items %} {% with line=s.removed_items %}{% include "duty/_labels.html" %}{% endwith %}{% endif %}</p>
  {% if p.editable %}
  <details><summary role="button" class="outline secondary">바꾸기</summary>
    {% include "duty/_cell_form.html" with cell=s.cell label=s.label slot=s.slot lunch=s.lunch carry=s.carry current_members=s.current_members reason_choices=s.reason_choices to_options=s.to_options next=s.next bq=p.bq inline=True %}
  </details>
  {% endif %}
</article>
{% endfor %}
{% if multi %}</section>{% endif %}
{% endfor %}

<style>
  h4.grp { margin: 1.5rem 0 .5rem; }
  article.dcell { margin: 0 0 .6rem; padding: .7rem 1rem; }
  article.dcell p { margin: .2rem 0 .4rem; }
  article.dcell details { margin: 0; }
  article.dcell summary[role=button] { width: auto; display: inline-block; padding: .3rem .9rem; font-size: .85rem; }
</style>
{% endblock %}
```

`<style>` 은 지금 글자 그대로 둔다(하루 화면 이름표 크기는 `base.html` 에 한 줄: `section.bsec h3.bname { margin: 1.6rem 0 .4rem; font-size: 1.3rem; }`). `day` 스냅샷이 바뀌면 순서·공백이 아니라 글자가 달라진 곳을 찾아 템플릿을 고친다.

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_roster_multi.py tests/test_board_pick.py tests/test_snapshots.py tests/test_reasons.py tests/test_views_roster.py tests/test_views_memos.py tests/test_memo*.py` → 모두 통과(**스냅샷 그대로**)
Run: `.venv/bin/pytest -W error -q` → `1434 passed`

- [ ] **Step 5: 브라우저로 본다**(Task 7 의 준비, `admin` = 두 근무표 관리자)

근무표 화면 `/?board=it&board=ops` 에서 날짜를 눌러 하루 화면: "IT 당번표" 큰 이름표 아래 출근조·관제·당번, 그 아래 "운영팀"(관리자라 [바꾸기]·[메모]). 운영팀 칸 [바꾸기]로 저장 → 같은 하루 화면의 그 운영팀 칸으로 돌아온다. 근무표 화면 운영팀 칸 팝업 제목이 "운영팀 · 2026-…", 저장 뒤 맨 위 "운영팀 · 변경했습니다.". `member` 로는 팝업 제목에 근무표 이름이 없다. 390px·아주 크게에서 이름표·[메모]가 한 줄을 넘으면 줄바꿈, 가로 넘침 없음.

- [ ] **Step 6: 커밋한다**

```bash
git add duty/views/roster.py duty/services/boards.py duty/templates/duty/day.html duty/templates/duty/_cell_form.html \
        duty/templates/duty/base.html tests/test_roster_multi.py
git commit -m "feat: 하루 화면도 근무표 구역을 쌓고, 팝업은 늘 근무표 하나(둘 붙이면 404)로 돌아갈 주소에 고른 근무표·검색·앵커를 싣고, 바꿀 수 있는 근무표가 둘 이상이면 제목·성공 글에 근무표 이름

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 4: 근무표 고르기 드롭다운

> 범위: 설계 9.1 의 화면(드롭다운·체크박스·[보기] 둘·안내 글·`pick=1`·숨은 칸·크기) — 계획 2·3·14번. 옛 `.seg` 근무표 버튼을 지운다. 스냅샷: roster-* 의 고르기 줄만 바뀌고 겹친 화면 기준 셋을 더한다.

**Files:**
- Modify: `duty/views/roster.py`(`board_links` → `pick_boards`), `duty/templates/duty/roster.html`, `duty/templates/duty/base.html`(CSS), `tests/test_snapshots.py`, `tests/snapshots/`(다시 쓰기로)
- Test: `tests/test_roster_multi.py`, `tests/test_board_pick.py`(`test_board_buttons_only_with_two_boards` 고침)

**Interfaces:**
- Consumes: Task 2 `_selection`(`pick` 읽기는 이미 있다)
- Produces: 템플릿 값 `pick_boards`(`code`·`name`·`home`·`on`, 내 근무표 먼저 id 순, 근무표가 하나면 `[]`), 폼 `form.board-pick`(GET: `pick=1`·`date`·비지 않은 `q1`~`q3`·체크한 `board`)

- [ ] **Step 1: 실패 테스트를 쓴다** — `tests/test_roster_multi.py` 끝에 더한다

```python


# ── 근무표 고르기(설계 9.1, 계획 2·3번) ──

def _picker(body):
    return re.search(r'<form method="get" class="board-pick">.*?</form>', body, re.S)[0]


def test_picker_dropdown(client, two):
    _, ga, _ = two
    client.force_login(ga)
    body = client.get(WEEK + "&q1=가상다").content.decode()
    f = _picker(body)
    assert "근무표: IT 당번표</summary>" in f
    assert re.findall(r'name="board" value="(\w+)"( checked)?', f) == [("it", " checked"), ("ops", "")]
    assert f.index("IT 당번표 (내 근무표)") < f.index("운영팀")
    assert f.count("<button>보기</button>") == 2 and "하나도 고르지 않으면 내 근무표만 보입니다" in f
    assert 'name="pick" value="1"' in f and f'name="date" value="{D}"' in f and 'name="q1" value="가상다"' in f
    assert 'name="q2"' not in f  # 빈 검색 칸은 보내지 않는다
    for name in ("view", "dept", "type", "shift", "hist"):  # 저장값으로 남는다(계획 2번)
        assert f'name="{name}"' not in f, name
    assert 'aria-label="근무표"' not in body  # 옛 근무표 버튼 없음
    assert body.index('class="board-pick"') < body.index(">주간</a>")  # [주간]·[월간] 앞
    two_names = _picker(client.get(BOTH).content.decode())
    assert "근무표: IT 당번표 + 운영팀</summary>" in two_names


def test_pick_semantics_and_memory(client, two):
    _, ga, _ = two
    client.force_login(ga)
    client.get(f"/?pick=1&board=ops&board=it&date={D}")
    assert RosterPref.objects.get(user=ga).boards == ["it", "ops"]
    assert "가상나" in client.get(WEEK).content.decode()  # pick 도 board 도 없으면 기억한 목록
    body = client.get(f"/?pick=1&date={D}").content.decode()  # 하나도 안 고르고 [보기]
    assert "가상다" in body and "가상나" not in body and RosterPref.objects.get(user=ga).boards == []


def test_links_after_pick_have_no_pick_and_dropdown_closed(client, two):
    _, ga, _ = two
    client.force_login(ga)
    body = client.get(f"/?pick=1&board=it&board=ops&view=week&date={D}").content.decode()
    assert "?board=it&amp;board=ops&amp;view=week&amp;date=2026-11-09" in body  # ◀ 도 같은 꼴, view·date 를 지킨다
    assert "pick=" not in body and "pick%3D" not in body  # 다른 링크·팝업 next 에 pick 없음
    assert '<details class="dropdown" open' not in body  # 보낸 뒤 닫힌 채(계획 3번)


def test_picker_keeps_search_and_saved_filter(client, two):
    _, ga, _ = two
    client.force_login(ga)
    client.get(WEEK + "&f=1&dept=TMCH")  # 내 근무표 필터: 가상다(MEMS) 숨김
    client.get(WEEK + "&board=ops")  # 남의 근무표만(필터 상자 없음)
    body = client.get(f"/?pick=1&board=it&board=ops&date={D}&q1=가상나").content.decode()
    assert RosterPref.objects.get(user=ga).depts == ["TMCH"]  # 고르기 폼이 저장된 필터를 지우지 않는다(계획 2번)
    assert "가상다" not in body and '<span class="hl1">가상나</span>' in body  # 필터·검색 색칠이 남는다
```

`tests/test_board_pick.py` — 드롭다운 체크박스도 `name="board"` 라 `test_other_board_admin_gets_board_links` 의 마지막 단언을 숨은 칸으로 좁힌다:

```diff
-    assert f'href="/day/{D}/#dawn"' in mine and 'name="board"' not in mine  # 내 근무표는 ?board= 없이 그대로
+    assert f'href="/day/{D}/#dawn"' in mine and 'type="hidden" name="board"' not in mine  # 내 근무표는 ?board= 없이 그대로
```

그리고 `test_board_buttons_only_with_two_boards` 를 바꾼다:

```python
def test_board_picker_only_with_two_boards(client, depts, request):
    client.force_login(member("it01", "가상가", depts["MEMS"]))
    assert 'class="board-pick"' not in client.get("/").content.decode()  # 근무표가 하나면 그리지 않는다
    request.getfixturevalue("ops")
    body = client.get("/").content.decode()
    assert 'class="board-pick"' in body and body.index('class="board-pick"') < body.index(">주간</a>")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_roster_multi.py -k pick tests/test_board_pick.py -k picker`
Expected: FAIL — `TypeError: 'NoneType' object is not subscriptable`(고르기 폼 없음)

- [ ] **Step 3: 구현한다**

`duty/views/roster.py` `roster` 의 `board_links` 를 바꾼다:

```python
        # 근무표 고르기(설계 9.1): 근무표가 둘 이상일 때만, 내 근무표 먼저 id 순. 체크박스를 바꿔도 보내지 않고 [보기]로
        "pick_boards": [{"code": b.code, "name": b.name, "home": b == home, "on": b in chosen}
                        for b in boards.in_order(all_boards, home)] if len(all_boards) > 1 else [],
```

`duty/templates/duty/roster.html` — `{% if board_links %}…{% endif %}` 줄을 바꾼다:

```django
  {% if pick_boards %}<form method="get" class="board-pick">
    <input type="hidden" name="pick" value="1"><input type="hidden" name="date" value="{{ date|date:'Y-m-d' }}">
    {% for n in names %}{% if n %}<input type="hidden" name="q{{ forloop.counter }}" value="{{ n }}">{% endif %}{% endfor %}
    <details class="dropdown"><summary role="button" class="outline">근무표: {{ sel_names }}</summary>
      <ul>
        <li><button>보기</button></li>
        <li><small>하나도 고르지 않으면 내 근무표만 보입니다</small></li>
        {% for b in pick_boards %}<li><label><input type="checkbox" name="board" value="{{ b.code }}"{% if b.on %} checked{% endif %}> {{ b.name }}{% if b.home %} (내 근무표){% endif %}</label></li>
        {% endfor %}<li><button>보기</button></li>
      </ul>
    </details>
  </form>{% endif %}
```

(보기·필터·`hist` 는 싣지 않는다 — 계획 2번. `pick=1` 이어도 `<details>` 는 닫힌 채 — 계획 3번.)

`duty/templates/duty/base.html` `<style>` 의 `a.to-mine` 줄 아래에 더한다:

```css
    /* 근무표 고르기(근무표 통합 5단계): Pico details.dropdown. 바깥을 누르면 닫힌다(Pico 의 summary::before 덮개, JS 없음).
       단추·체크 줄·[보기] 모두 48px 이상, 글씨 rem(글씨 크기 설정을 따른다), 이름이 길면 줄바꿈 */
    form.board-pick { margin: 0; }
    form.board-pick details.dropdown { display: block; margin: 0; }
    form.board-pick summary[role=button] { display: flex; align-items: center; gap: .3rem; min-height: 48px; width: auto; margin: 0; padding: .4rem 1rem; font-size: 1.05rem; font-weight: 700; white-space: normal; text-align: left; }
    form.board-pick details.dropdown summary + ul { min-width: min(20rem, calc(100vw - 2rem)); white-space: normal; }
    form.board-pick ul li { padding: .3rem .9rem; }
    form.board-pick ul label { display: flex; align-items: center; gap: .6rem; min-height: 48px; margin: 0; font-size: 1.05rem; cursor: pointer; }
    form.board-pick ul button { width: 100%; min-height: 48px; margin: 0; font-size: 1.05rem; }
    form.board-pick ul small { font-size: .95rem; }
    @media (max-width: 600px) {
      form.board-pick { flex-basis: 100%; }
      form.board-pick summary[role=button] { width: 100%; }
    }
```

`tests/test_snapshots.py` `_pages` 의 사람 쪽 목록 끝(`("roster-other", …)` 뒤)에 셋을 더한다(기억을 쓰므로 맨 뒤에):

```python
                      ("roster-other", "/?board=ops&view=week"),
                      # 겹친 화면(5단계): 두 근무표를 주소로 고른 주간·월간·하루. 운영팀 구역은 보기만
                      ("roster-both", "/?board=it&board=ops&view=week"), ("roster-both-month", "/?board=it&board=ops&view=month"),
                      ("day-both", "/day/2026-11-16/?board=it&board=ops")):
```

- [ ] **Step 4: 통과를 확인하고 스냅샷을 다시 쓴다**

Run: `.venv/bin/pytest -W error -q tests/test_roster_multi.py tests/test_board_pick.py` → 통과
Run: `DUTY_SNAPSHOT_WRITE=1 .venv/bin/pytest -W error -q tests/test_snapshots.py` → 일부러 FAIL("스냅샷을 다시 썼습니다")
Run: `git status --short tests/snapshots/` → 바뀜 `roster-mine.html`·`roster-month.html`·`roster-other.html`, 새 파일 `roster-both.html`·`roster-both-month.html`·`day-both.html` 만
Run: `git diff -U0 tests/snapshots/roster-mine.html tests/snapshots/roster-month.html tests/snapshots/roster-other.html` → 빠진 줄은 `<span class="seg" role="group" aria-label="근무표">` 부터 그 `</span>` 까지뿐, 더한 줄은 `<form method="get" class="board-pick">` 부터 `</form>` 까지뿐(다른 줄이 있으면 멈추고 원인을 찾는다)
Run: 새 기준 셋을 열어 읽는다 — 구역 순서(IT 먼저), 운영팀 "보기만", 링크의 `?board=`, `d-` 앵커, 이름 가상
Run: `.venv/bin/pytest -W error -q tests/test_snapshots.py` → 통과
Run: `.venv/bin/pytest -W error -q` → `1438 passed`

- [ ] **Step 5: 브라우저로 본다**(Task 7 의 준비, `member`)

1400px: [주간]·[월간] 앞 큰 단추 "근무표: IT 당번표 ▾"(Pico 꺾쇠). 누르면 표 위에 목록이 뜬다: 맨 위 [보기], 안내 글, "IT 당번표 (내 근무표)"(체크)·"운영팀", 맨 아래 [보기]. 글자를 눌러도 체크가 바뀌고 바로 보내지 않는다. 운영팀을 체크하고 [보기] → 겹친 화면, 단추 글 "근무표: IT 당번표 + 운영팀", 목록은 닫혀 있다. 바깥을 누르면 목록이 닫힌다. 둘 다 끄고 [보기] → 내 근무표만. 검색에 이름을 넣고 근무표를 바꿔도 색칠이 남는다. 390px: 단추·목록이 한 줄 전체 폭, 줄마다 48px 이상. 아주 크게 + 390px: 단추 글이 줄바꿈되고 가로 넘침 없음. 다크: 목록 배경·글 대비가 보인다.

- [ ] **Step 6: 커밋한다**

```bash
git add duty/views/roster.py duty/templates/duty/roster.html duty/templates/duty/base.html tests/test_roster_multi.py \
        tests/test_board_pick.py tests/test_snapshots.py tests/snapshots/
git commit -m "feat: 근무표 이름 버튼을 큰 드롭다운 하나로(체크박스 여럿·위아래 [보기]·자동 제출 없음, 하나도 안 고르면 내 근무표, 검색·저장된 필터 유지), 겹친 화면 스냅샷

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 5: 회차 목록 근무표 열·알림 규칙 근무표·통계 주석

> 범위: 설계 9.5 표(통계 그대로 + `ponytail:` 주석, 알림 규칙 내 근무표 맨 위·`it_board()` → `home`, 회차 목록 근무표 열), 2절 "남는 IT 가정"의 5단계 몫 — 계획 15번.

**Files:**
- Modify: `duty/templates/duty/periods.html`, `duty/alarms/forms.py`, `duty/services/alarms.py`, `duty/views/manage.py`(주석 한 줄), `tests/snapshots/periods.html`(다시 쓰기로)
- Test: `tests/test_board_pick.py`

**Interfaces:**
- Consumes: `boards.home`, `boards.in_order`
- Produces: `alarms.rule_board(user, "personal", None) == boards.home(user)`, `RuleForm(user=...).fields["board"].queryset` 순서 = 내 근무표 먼저 id 순

- [ ] **Step 1: 실패 테스트를 쓴다** — `tests/test_board_pick.py`

import 에 `alarms` 를 더한다: `from duty.services import alarm_runner, alarms, boards, change_notice`. `test_change_log_board_column_and_filter` 아래와 "알림 규칙 화면" 묶음 끝에 더한다:

```python
def test_period_list_board_column_for_two_boards(admin_client_ok, admin_user, two):
    board, _, _ = two
    assert "<th>근무표</th>" not in admin_client_ok.get("/periods/").content.decode()  # IT 만 관리
    admin_user.groups.add(board.admin_group)
    body = admin_client_ok.get("/periods/").content.decode()
    assert "<th>근무표</th>" in body and "<td>운영팀</td>" in body and "<td>IT 당번표</td>" in body
```

```python
def test_rule_board_for_deptless_admin_is_home(two):
    """부서 없는 운영팀 관리자의 개인 규칙 근무표는 IT 가 아니라 내 근무표(설계 2절 표)."""
    board, _, _ = two
    keeper = User.objects.create_user("opadm", password=None, name="가상관리")
    keeper.groups.add(board.admin_group)
    assert alarms.rule_board(keeper, "personal", None) == board
    assert [c for c, _ in RuleForm(user=keeper).fields["shifts"].choices] == ["dawn", "normal", "dinner"]
    rule = AlarmRule.objects.create(user=keeper, kind="personal", timing="before_start", offset=120, telegram=True,
                                    shifts=[], depts=[], types=[])
    assert RuleForm.initial_from(rule)["board"] == board.pk


def test_rule_form_board_select_home_first(two):
    board, ga, na = two
    assert [b.code for b in RuleForm(user=na).fields["board"].queryset] == ["ops", "it"]
    assert [b.code for b in RuleForm(user=ga).fields["board"].queryset] == ["it", "ops"]
    f = RuleForm.redraw({**FORM, "kind": "report"}, user=na)  # 아직 근무표를 안 골랐으면 목록 첫 줄(내 근무표) 기준
    assert [c for c, _ in f.fields["shifts"].choices] == ["dawn", "normal", "dinner"]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_pick.py -k "period_list or rule_board_for or home_first"`
Expected: FAIL — 근무표 열 없음, `rule_board` 가 IT, 순서 `["it", "ops"]`

- [ ] **Step 3: 구현한다**

`duty/templates/duty/periods.html` 표 머리와 줄:

```diff
-  <thead><tr><th>이름</th><th>기간</th><th>상태</th></tr></thead>
+  <thead><tr>{% if boards|length > 1 %}<th>근무표</th>{% endif %}<th>이름</th><th>기간</th><th>상태</th></tr></thead>
   <tbody>{% for p in periods %}
-    <tr><td><a href="{% url 'period_detail' p.pk %}">{{ p.name }}</a></td>
+    <tr>{% if boards|length > 1 %}<td>{{ p.board.name }}</td>{% endif %}<td><a href="{% url 'period_detail' p.pk %}">{{ p.name }}</a></td>
```

`duty/services/alarms.py` `rule_board`:

```diff
-    """규칙 값을 검사할 근무표. 보고서 = 규칙의 근무표, 개인 = 주인 부서의 근무표(부서 없는 계정은 IT)."""
+    """규칙 값을 검사할 근무표. 보고서 = 규칙의 근무표, 개인 = 주인의 내 근무표(boards.home: 부서 없는 관리자는 관리하는 근무표)."""
     if kind != "report":
-        return boards.board_of(user) or boards.it_board()
+        return boards.home(user)
```

`duty/alarms/forms.py` — import 에 `from django.db.models import Case, Value, When` 를 더하고:

```diff
     def __init__(self, *args, user=None, **kwargs):
         super().__init__(*args, **kwargs)
-        all_boards = list(Board.objects.order_by("id"))
+        first = Board.objects.order_by("id").first()
+        self.home = boards.home(user) if user else first  # 내 근무표(user 없이 만든 폼은 첫 근무표)
+        all_boards = boards.in_order(list(Board.objects.order_by("id")), self.home)  # 내 근무표 맨 위(설계 9.5)
         # 근무표가 하나면 칸을 숨기고 그 근무표로 고정(1단계 화면 그대로)
         self.fixed_board = all_boards[0] if len(all_boards) == 1 else None
         if self.fixed_board is None:
             self.fields["board"].label_from_instance = lambda b: b.name
+            if self.home is not None:
+                self.fields["board"].queryset = Board.objects.order_by(
+                    Case(When(pk=self.home.pk, then=Value(0)), default=Value(1)), "id")
         else:
@@
         if src.get("kind") == "report":
             picked = str(src.get("board") or "")
-            return next((b for b in all_boards if str(b.pk) == picked), all_boards[0] if all_boards else boards.it_board())
+            return next((b for b in all_boards if str(b.pk) == picked), all_boards[0])  # 안 골랐으면 목록 첫 줄 = 내 근무표
         # 화면에서 종류·근무표를 바꾸면 redraw 로 다시 그린다(alarm_rule_form.html)
-        return (boards.board_of(user) if user else None) or boards.it_board()
+        return self.home
@@
-        # '전부'를 체크로 그릴 근무표: 보고서 = 규칙의 근무표, 개인 = 주인의 근무표(부서 없는 계정은 IT)
-        board = rule.board if rule.board_id else (boards.board_of(rule.user) or boards.it_board())
+        # '전부'를 체크로 그릴 근무표: 보고서 = 규칙의 근무표, 개인 = 주인의 내 근무표
+        board = rule.board if rule.board_id else boards.home(rule.user)
```

(`_shift_board` 는 `self.home` 을 쓰도록 `__init__` 에서 `self.home` 을 먼저 정한 뒤 부른다 — 위 순서 그대로. `all_boards` 가 빈 DB 는 마이그레이션이 IT 를 늘 만들어 생기지 않는다.)

`duty/views/manage.py` `stats_view`:

```diff
-    board = perms.stats_boards(request.user).order_by("id").first()  # 관제가 있는 내 근무표 중 첫 것(고르기는 2단계)
+    # ponytail: 관제가 있는 내 근무표 중 id 가 가장 작은 것 하나. 관제 있는 근무표가 둘째로 생기면 근무표 select
+    board = perms.stats_boards(request.user).order_by("id").first()
```

확인: `git grep -n "it_board()" -- duty ':!duty/migrations'` → `duty/services/boards.py` 의 정의 한 줄만(Task 6 이 ARCHITECTURE 에 적는다).

- [ ] **Step 4: 통과를 확인하고 스냅샷을 다시 쓴다**

Run: `.venv/bin/pytest -W error -q tests/test_board_pick.py tests/test_alarm_boards.py tests/test_alarm*.py` → 통과
Run: `DUTY_SNAPSHOT_WRITE=1 .venv/bin/pytest -W error -q tests/test_snapshots.py` → 일부러 FAIL
Run: `git diff --stat tests/snapshots/` → `periods.html` 하나만(스냅샷의 `admin_user` 는 두 근무표 관리자), `git diff tests/snapshots/periods.html` 은 `<th>근무표</th>` 와 줄마다 `<td>…</td>` 한 칸뿐
Run: `.venv/bin/pytest -W error -q tests/test_snapshots.py` → 통과
Run: `.venv/bin/pytest -W error -q` → `1441 passed`

- [ ] **Step 5: 브라우저로 본다**(Task 7 의 준비, `admin`)

[회차]: 맨 앞 "근무표" 열(IT 당번표·운영팀), 390px 에서 표가 화면 안(넘치면 지금처럼 표 안에서만). [알림] → 규칙 추가 → 종류 "보고서형": 근무표 고르기 첫 줄이 내 근무표.

- [ ] **Step 6: 커밋한다**

```bash
git add duty/templates/duty/periods.html duty/alarms/forms.py duty/services/alarms.py duty/views/manage.py \
        tests/test_board_pick.py tests/snapshots/periods.html
git commit -m "feat: 회차 목록에 근무표 열(관리 근무표가 둘 이상일 때), 알림 규칙 근무표는 내 근무표가 맨 위이고 부서 없는 관리자의 기본 근무표는 IT 대신 내 근무표

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 6: 글 도움말·스냅샷·문서에 설계 합치기·설계 파일 지우기

> 범위: 설계 13절(5단계 몫과 "구현이 끝나면 합치고 지운다")·10.4 5단계 메모·공지 — 계획 17번.

**Files:**
- Modify: `duty/help.py`, `tests/test_help.py`, `tests/snapshots/help-admin.html`(다시 쓰기로)
- Modify: `docs/ARCHITECTURE.md`, `docs/OVERVIEW.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT.md`, `docs/PRINCIPLES.md`
- Delete: `docs/superpowers/specs/2026-11-17-boards-unify-design.md`

- [ ] **Step 1: 실패 테스트를 쓴다** — `tests/test_help.py` `test_steps_cover_phase2_member_features`

```diff
-    for word in ("근무표 이름", "보기 전용", "[가]", "점심당번", "(휴가)", "사유", "메모", "근무 없음", "휴장일"):
+    for word in ("[근무표: ", "[보기]", "[내 근무표만 보기]", "보기만", "보기 전용", "[가]", "점심당번", "(휴가)", "사유",
+                 "메모", "근무 없음", "휴장일"):
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_help.py` → FAIL(`[근무표: `)

- [ ] **Step 3: 구현한다** — `duty/help.py` `STEPS["member"]` 넷째 줄을 바꾼다

```python
        "근무표가 둘 이상이면 [주간]·[월간] 앞에 [근무표: 내 근무표 이름] 단추가 보입니다. 누르면 근무표 목록이 펼쳐지고, 함께 볼 근무표에 체크한 뒤 [보기]를 누르면 날짜 칸 안에 근무표마다 이름표를 달고 한 화면에 보입니다(내 근무표가 맨 위). 고른 것은 다음에 들어와도 그대로이고, 큰 [내 근무표만 보기]를 누르면 내 근무표로 돌아갑니다. 바꿀 수 없는 근무표에는 '보기만'이 붙고, 부서·유형·스케줄 필터는 내 근무표에만 적용됩니다. 남의 근무표 하나만 보고 있으면 제목 옆에 [보기 전용 · 내 근무표로]가 보입니다.",
```

- [ ] **Step 4: 스냅샷을 다시 쓴다**

Run: `DUTY_SNAPSHOT_WRITE=1 .venv/bin/pytest -W error -q tests/test_snapshots.py` → 일부러 FAIL
Run: `git diff --stat tests/snapshots/` → `help-admin.html` 하나만, diff 는 위 한 줄
Run: `.venv/bin/pytest -W error -q tests/test_snapshots.py tests/test_help.py` → 통과

- [ ] **Step 5: 설계를 본 문서로 옮긴다** — 아래 대조표대로. "이미 있음"은 `grep` 으로 확인만 하고 그대로 둔다(1~4단계 PR 이 옮긴 것). 옮기는 글에 실명·비밀값 없음.

| 설계 절 | 옮길 곳 | 할 일 |
|---|---|---|
| 1·2 배경·목표·범위 밖(근무표 만들기·휴장일·알림 설정·잠금 해제·부서 만들기는 슈퍼유저, 인사이동은 관리 화면 사용자 → 부서, 지원 근무 없음 = 날 메모, 사람 지우기 없음) | OVERVIEW "범위" | 없는 줄만 더한다 |
| 2 "남는 IT 가정" 표 | ARCHITECTURE "근무표와 칸" 끝 | 짧은 목록으로: `shifts.KEYS`(근무조 4·관제 10칸 고정), 사용법 영상은 IT 화면, 통계는 관제 있는 근무표 하나(`ponytail:`), `boards.it_board()` 는 정의만 남고 앱 코드가 부르지 않는다(테스트·확인용) |
| 3 결정 요약, 8 권한 | PRINCIPLES 결정 기록·ARCHITECTURE "역할" | 이미 있음(1~4단계). 5단계 줄만 아래 |
| 4 용어(단계·켠 단계·근무표 관리자·관리자 계정·입력 담당자·내 근무표·고른 근무표·구역) | OVERVIEW "용어" | 없는 것만 더한다(내 근무표·고른 근무표·구역은 새로) |
| 5 데이터·단계 규칙·버튼 이름·계정 | ARCHITECTURE "데이터"·"회차"·"보안" | 이미 있음. 데이터 그림의 `RosterPref` 에 "(boards: 고른 근무표 code 목록)" |
| 6·7 서비스·[근무표 설정] | ARCHITECTURE "역할"의 [근무표 설정] 문단 | 이미 있음 |
| 9 여러 근무표 | ARCHITECTURE "보일 근무표" | 아래 글로 바꾼다 |
| 10.1~10.4 업그레이드 | OPERATIONS "업그레이드·롤백" | 1~4단계 이미 있음. 5단계 아래 글을 더한다 |
| 11 테스트 전략(스냅샷 규칙) | DEVELOPMENT "테스트" | 아래 문단을 더한다 |
| 12 진행 단계 | (옮기지 않음 — 다 끝났다) | 없음 |
| 14 위험 | PRINCIPLES "받아들인 위험" 성격의 줄 | 1~4단계 몫은 이미 있음. 겹친 월간 칸이 길다 → 5단계 결정 줄에 함께 |
| 15·16 사용자 확인·자체 점검 | (옮기지 않음 — 결정은 결정 기록에 있다) | 없음 |

ARCHITECTURE "보일 근무표" 절의 첫 세 줄(근무표 고르기·`board_query` 링크·보기 전용)을 아래로 바꾼다(이력 줄은 그대로):

```markdown
- 근무표 화면(`/`)은 근무표 여러 개를 골라 한 표에 겹쳐 본다. 고른 목록 = `?board=a&board=b`(중복·빈 값은 버리고 없는 code 는 404) → `pick=1`(폼에서 골랐음)이고 `board` 가 없으면 내 근무표만 → 기억한 목록(`RosterPref.boards`, code 목록, 없는 code 는 버림) → 내 근무표(`boards.home(user)`: 내 부서의 근무표 → 내가 관리하는 첫 근무표 → 첫 근무표). 순서는 늘 `boards.in_order`(내 근무표 먼저, 나머지 id 순), 기억도 그 순서이고 `[내 근무표]` 면 `[]`(`prefs.remember_boards`). 기억은 `/` 에서만 읽고 쓴다: `/day/` 는 `?board=` 가 없으면 내 근무표 하나라 `?board=` 없는 알림 링크가 기억한 남의 근무표로 가지 않는다. 팝업(`/cell/`·`/memo/`)은 늘 근무표 하나(`board` 가 둘 이상이면 404).
- 근무표 고르기: 근무표가 둘 이상일 때만 [주간]·[월간] 앞에 Pico `details.dropdown` 단추 "근무표: <고른 이름들>"(48px 이상, 줄바꿈 허용). 목록 = [보기] · 안내 글 · 체크박스(내 근무표 맨 위 "(내 근무표)") · [보기]. 체크를 바꿔도 보내지 않고, 보낸 뒤에도 닫힌 채다. GET 폼은 `pick=1`·`date`·검색 이름(`q1`~`q3`)만 싣는다 — 보기·필터·변경 내역 표시는 `RosterPref` 저장값이 그대로 쓰인다(폼이 `view` 를 보내면 `prefs.resolve` 가 필터 해제로 읽어 저장된 내 필터를 지운다).
- 한 길: `views/roster.py` 의 `part(b)`(근무표마다 정의·배포 날·메모·권한을 한 번씩) → 날짜마다 `section(p, d)`, 템플릿은 날짜 칸마다 `_section.html` 을 구역 수만큼. 쿼리 수는 근무표 수에 비례하고 날짜 수와 무관하다(테스트가 주간 = 월간을 본다). 겹친 모양(구역 이름표 `.bname`·"보기만"·근무 없음 한 줄 `.nowork-line`·날짜 앵커 `#d-YYYY-MM-DD`·제목 옆 이름들)은 **둘 이상일 때만** 그려서 근무표 하나면 화면이 겹쳐 보기 전과 같다(`tests/snapshots/`). 휴장일은 날짜 칸에 한 번, 날 메모는 구역 안, 주·달 메모는 근무표마다 "<근무표> · " 를 붙인다. 하루 화면(`/day/?board=a&board=b`)도 같은 순서로 구역(`_day_part`, 칸 id `<code>-<칸 키>`).
- 링크는 `boards.selection_query(chosen, home)`: 하나면 `link_query`(내 근무표면 `""`, 아니면 `?board=<code>` — IT 사람의 주소·알림 링크(`Due.url`, hash 와 무관)는 그대로), 둘 이상이면 `?board=it&board=ops`. 칸 링크·[메모]는 그 구역 근무표의 `link_query` 를 붙여 팝업·POST 가 그 근무표 하나로 간다. 팝업의 돌아갈 주소 `next` = 지금 주소에서 `pick` 만 뺀 것(+ 둘 이상이면 그 날짜 칸·하루 화면 칸 앵커), POST 는 `safe_next`. 내가 바꿀 수 있는 근무표(관리 ∪ 내 부서, `boards.edit_boards`)가 둘 이상이면 팝업 제목·성공 글 앞에 "<근무표> · ".
- **바꿀 수 있는 구역만 칸 링크**: 구역마다 `perms.can_edit`(지난 날·오늘 이후 두 번)·`is_board_admin`, 서버는 그대로 `assert_can_edit`·`memos._require_admin`. 바꿀 수 없는 구역(내 부서 근무표도 관리 근무표도 아님)은 이름표 끝 "보기만". 고른 근무표를 모두 바꿀 수 없으면 제목 옆 "보기 전용". [내 근무표만 보기](`a.to-mine`, 48px 이상, `/?board=<내 근무표>` 라 기억을 비운다)는 고른 목록이 정확히 [내 근무표]가 아니면 보이고, 글자는 내 근무표가 목록에 있으면 "내 근무표만 보기", 없으면 모두 보기 전용일 때 "보기 전용 · 내 근무표로", 바꿀 수 있는 근무표가 있으면 "내 근무표로".
- **필터는 내 근무표 구역에만**(근무표마다 부서·근무조·유형의 뜻이 달라서): 필터 상자는 내 근무표가 목록에 있을 때만, 둘 이상이면 "부서·유형·스케줄은 내 근무표에만 적용됩니다". 다른 구역은 늘 전체이고 근무 변경 창 To 후보에도 내 필터를 넘기지 않는다. 검색 색칠과 변경 내역 표시는 모든 구역.
```

ARCHITECTURE 코드 지도 `duty/services/` 줄: "근무표·근무 정의 읽기와 그날의 주인, 고른 근무표 순서·주소는 `boards.py`". 화면 디자인 절의 `RosterPref` 문장에 "고른 근무표 목록"을 더한다. "바꿀 때" 절에 한 줄: "코드·테스트 주석의 '근무표 통합 설계 x.y' 는 지운 설계 문서(아래 PRINCIPLES 2026-11-18 줄의 커밋)의 절 번호다."

OVERVIEW "사용자와 역할" 멤버 줄: "모든 근무표 보기(남의 근무표는 보기 전용)" → "모든 근무표 보기(여러 근무표를 골라 한 화면에 겹쳐 보기, 바꿀 수 없는 근무표는 보기만)". "용어"에 줄 셋:

```markdown
| 내 근무표 | 내 부서의 근무표(부서가 없으면 내가 관리하는 첫 근무표, 그것도 없으면 첫 근무표). 근무표 화면의 기본 |
| 고른 근무표 | 근무표 화면에서 겹쳐 볼 근무표 목록(드롭다운에서 고르고 [보기], 다음에도 그대로). 내 근무표가 맨 위 |
| 구역 | 겹쳐 본 화면의 날짜 칸 안에서 근무표 하나가 차지하는 부분(이름표 → 날 메모 → 칸) |
```

OPERATIONS "업그레이드·롤백"의 4단계 줄 아래에 더한다:

```markdown
- **근무표 통합 5단계로 올릴 때 (한 번)**: `migrate` 가 0025 를 적용한다(기억한 근무표 `RosterPref.board` → 목록 `boards`). 업그레이드 절차 그대로.
  - 올리기 전(읽기 전용, 대조용으로 적어 둔다. code·건수만): `sudo -u duty sqlite3 -readonly data/db.sqlite3 "SELECT b.code, COUNT(*) FROM duty_rosterpref r JOIN duty_board b ON b.id = r.board_id GROUP BY 1;"`
  - 올린 뒤: `sudo -u duty sqlite3 -readonly data/db.sqlite3 "SELECT boards, COUNT(*) FROM duty_rosterpref WHERE boards != '[]' GROUP BY 1;"` → 위와 같은 건수가 `["ops"]` 꼴로 나온다(기억한 근무표가 그대로 보인다).
  - 보이는 변화(근무표가 둘 이상일 때 모든 사용자): 근무표 이름 버튼이 [근무표: ○○ ▾] 단추 하나로 바뀌고 여러 근무표를 겹쳐 볼 수 있다. 관리 근무표가 둘 이상인 관리자의 [회차]에 근무표 열, 알림 규칙의 근무표 고르기에서 내 근무표가 맨 위, 부서 없는 관리자의 개인 알림 스케줄 선택지가 IT 대신 관리하는 근무표 기준.
  - 공지(모든 사용자, 지금 쓰는 메신저): "근무표 이름 버튼이 [근무표: ○○ ▾] 하나로 바뀌었습니다. 눌러서 여러 근무표에 체크하고 [보기]를 누르면 한 화면에 함께 보입니다. 큰 [내 근무표만 보기]를 누르면 내 근무표로 돌아갑니다."
  - 되돌리기는 위 "롤백"(코드 되돌리기 + 업그레이드 전 백업 `restore`)이 기본이다. `migrate duty 0024` 거꾸로는 근무표를 둘 이상 기억한 사용자가 없을 때만 돈다(있으면 백업 복원을 안내하며 멈춘다).
```

DEVELOPMENT "테스트" 절에 더한다:

```markdown
- 화면 스냅샷: `tests/test_snapshots.py` 가 회차·입력 표·근무표(하나·겹친 화면)·하루·도움말 화면 본문(메뉴 빼고, CSRF 토큰·pk 는 이름표로)을 `tests/snapshots/*.html` 과 비교한다. 보이는 동작을 일부러 바꾸는 PR 만 `DUTY_SNAPSHOT_WRITE=1 .venv/bin/pytest tests/test_snapshots.py`(다시 쓴 뒤 일부러 실패한다)로 다시 쓰고, 변수 없이 다시 돌려 통과시킨 뒤 `git diff tests/snapshots/` 의 바뀐 줄이 의도한 것뿐인지 PR 에서 리뷰한다. 의도하지 않은 줄이 바뀌었으면 기준을 다시 쓰지 말고 코드를 고친다.
```

PRINCIPLES "결정 기록" 끝에 두 줄(`<커밋>` = 설계 파일을 마지막으로 고친 커밋, Step 6 첫 명령의 출력. 지운 뒤에도 `git show <커밋>:경로` 로 열린다):

```markdown
| 2026-11-18 | 근무표 화면은 근무표 여러 개를 골라 한 표에 겹쳐 본다: 큰 드롭다운 하나(체크박스 + 위아래 [보기], 자동 제출 없음, 보낸 뒤 닫힘, `pick=1` = 폼에서 골랐음), 기억은 `RosterPref.boards`(code 목록, `[내 근무표]` 면 비움, 0025). 구역을 만드는 한 길이고 겹친 모양은 둘 이상일 때만 그려 근무표 하나면 화면이 그대로다(스냅샷). 필터는 내 근무표 구역에만, 칸 링크는 바꿀 수 있는 구역만, 팝업은 늘 근무표 하나이고 돌아갈 주소에 고른 근무표·검색·앵커. 고르기 폼은 보기·필터를 싣지 않는다(저장값, 실으면 저장된 필터가 지워진다). 겹친 월간 칸이 길어지는 것은 받아들인다 | 사용자 목표: 근무표 N개를 한 화면에. 근무표가 늘수록 이름 버튼이 늘던 것을 단추 하나로. 60세 가까운 부장들: 기본은 내 근무표 하나(기억이 비어 있음), 큰 [내 근무표만 보기]로 바로 돌아가고 하루 화면으로 크게 본다. [보기]를 눌렀는데 목록이 표를 가리면 결과가 안 보인다 |
| 2026-11-18 | 근무표 통합 설계 문서(`docs/superpowers/specs/2026-11-17-boards-unify-design.md`)를 ARCHITECTURE·OVERVIEW·OPERATIONS·DEVELOPMENT·PRINCIPLES 에 합치고 지웠다(`git show <커밋>:docs/superpowers/specs/2026-11-17-boards-unify-design.md` 로 본다). 코드 주석의 "근무표 통합 설계 x.y" 는 그 파일의 절 번호 | 문서는 지금 코드를 설명하고, 지난 설계·토론은 git 기록에 둔다 |
```

- [ ] **Step 6: 설계 파일을 지운다**

```bash
git log -1 --format=%h -- docs/superpowers/specs/2026-11-17-boards-unify-design.md   # PRINCIPLES 줄의 <커밋>에 적는다
git rm docs/superpowers/specs/2026-11-17-boards-unify-design.md
git grep -n "2026-11-17-boards-unify-design" -- ':!docs/superpowers/plans'   # PRINCIPLES 한 줄만 나와야 한다
```

- [ ] **Step 7: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q` → `1441 passed`
Run: `makemigrations duty --check --dry-run` → "No changes detected in app 'duty'"
Run: 문서의 링크·절 이름이 실제로 있는지 `grep -n "보일 근무표\|업그레이드·롤백\|## 테스트" docs/*.md`

- [ ] **Step 8: 커밋한다**

```bash
git add duty/help.py tests/test_help.py tests/snapshots/help-admin.html docs/
git commit -m "docs: 여러 근무표 한 화면(보일 근무표·5단계 업그레이드와 공지·용어·스냅샷 규칙·결정 기록), 근무표 통합 설계를 본 문서에 합치고 지움

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 7: 브라우저 확인(가짜 데이터, 끝나면 지움)

> Task 2~5 의 "브라우저로 본다"를 이 준비에서 한다. 마지막에 한 번 더 모두 훑는다. 실제 DB·`.env` 는 쓰지 않는다(`DUTY_ENV_FILE=` 로 `.env` 를 읽지 않고 `DUTY_DATA_DIR` 을 임시 폴더로).

- [ ] **Step 1: 띄운다**

```bash
W=$(mktemp -d -p /home/dustbox/.claude/jobs/88ab5e02/tmp)
export DUTY_ENV_FILE= DUTY_DEBUG=1 DUTY_DATA_DIR=$W/data
.venv/bin/python manage.py migrate -v0
.venv/bin/python manage.py shell < tools/help_videos/seed.py > /dev/null     # IT 가짜 데이터(계정 비밀번호 Demo-pass-123)
.venv/bin/python manage.py shell <<'EOF'
# 가짜 '운영팀' 근무표(시장운영실 모양): 이번 주가 배포돼 있고 날 메모·근무 없음·주 메모·휴장일이 하나씩. 실명 없음
from datetime import time, timedelta
from duty import perms
from duty.models import Board, BoardShift, Commute, Department, Holiday, Period, User
from duty.services import memos, periods, publish
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
p = periods.save_draft(Period(board=ops, name="4주", start_date=mon - timedelta(days=7), end_date=mon + timedelta(days=18)), by=admin)
for x in p.dates():
    for i, m in enumerate(team):
        Commute.objects.create(period=p, date=x, member=m, shift=("dawn", "normal", "dinner")[i % 3])
run_generation(p, by=admin)
publish.publish(p, p.start_date, by=admin)
memos.save(admin, ops, "day", mon + timedelta(days=1), "운영 점검")
off = mon + timedelta(days=3)
memos.save(admin, ops, "day", off, "운영 쉬는 날", no_work=True, confirm=memos.affected(ops, off))
memos.save(admin, ops, "week", mon, "운영팀 이번 주 메모")
Holiday.objects.get_or_create(date=mon + timedelta(days=2), defaults={"name": "가상 휴장"})
print("운영팀 준비 끝")
EOF
.venv/bin/python manage.py runserver 127.0.0.1:8795 > $W/server.log 2>&1 &
echo $! > $W/server.pid
```

로그인: `admin` / `Demo-pass-123`(슈퍼유저 + IT·운영팀 관리 그룹, 부서 없음 → 내 근무표 = IT), `member` / `Demo-pass-123`(IT 사람), `OPS0`(가상하나) / `Demo-pass-123`(운영팀 사람). 주소 `http://127.0.0.1:8795/`.

- [ ] **Step 2: 본다** — PC 1400px, 휴대폰 390px, 각각 다크 모드와 글씨 아주 크게. 모든 화면에서 콘솔 `document.documentElement.scrollWidth > innerWidth` → `false`.
  - `member`: 단추 "근무표: IT 당번표"(근무표 하나 화면은 단추 말고 지금과 같다). 드롭다운으로 운영팀을 더해 [보기] → Task 2 Step 6·Task 4 Step 5 의 모든 것. IT 칸을 바꿔 저장하면 같은 두 근무표 화면의 그 날짜 칸으로 돌아오고(오늘로 튀지 않음), 단추는 닫혀 있다. [내 근무표만 보기] → 내 근무표, 다시 들어와도 내 근무표. 다시 두 개를 골라 두고 로그아웃·로그인 → 두 개 그대로.
  - 필터: IT 에 부서 필터를 걸고 겹쳐 보면 운영팀 구역은 전체, 상자 맨 위 "부서·유형·스케줄은 내 근무표에만 적용됩니다".
  - `admin`: 운영팀 구역에도 칸 링크·[메모](이름표 끝), "보기만" 없음. 팝업 제목·성공 글에 "운영팀 · ". 하루 화면(Task 3 Step 5). [회차] 근무표 열, 알림 규칙 근무표 순서(Task 5 Step 5).
  - `OPS0`: 드롭다운 첫 줄 "운영팀 (내 근무표)", 겹치면 운영팀 구역이 먼저, IT 구역에 "보기만".
  - 월간 1400px: 칸이 길어져도 이름표로 구역이 갈리고, 다른 달 날짜는 날짜만. 390px 월간은 표 안에서만 옆으로 민다.
  - 서버 로그: `grep -c 가상 $W/server.log` 가 0(이름이 로그에 없다).

- [ ] **Step 3: 끈다**(이 폴더만 지운다)

```bash
kill "$(cat "$W/server.pid")"; rm -rf -- "$W"; unset DUTY_ENV_FILE DUTY_DEBUG DUTY_DATA_DIR W
```

- [ ] **Step 4: 마무리 확인**

Run: `.venv/bin/pytest -W error -q` → `1441 passed`(경고 0개)
Run: `makemigrations duty --check --dry-run` → "No changes detected in app 'duty'"
Run: `git status --short` → 깨끗함(임시 파일 없음)

---

## 자체 점검(설계 12절 5단계 대조표)

| 설계 | 작업 |
|---|---|
| 5.5 `RosterPref.boards`(code 목록, 내 근무표 먼저, `[]` = 내 근무표, 없는 code 버림, `[내 근무표]` 면 `[]`) | Task 1(모델·`remember_boards`), Task 2(`_selection` 읽기) |
| 10.2 0025(`board` → `[code]`, null → `[]`, 둘 이상이면 거꾸로 거부, 하나짜리는 `board` 로) | Task 1 |
| 9.1 둘 이상일 때만·자리([주간] 앞)·`details.dropdown`·"근무표: 이름 + 이름"·[보기] 둘·안내 글·내 근무표 맨 위·자동 제출 없음·`pick=1`·크기·390px·`getlist`·링크 꼴·없는 code 404·기억은 `/` 에서만·`/day/` 는 내 근무표 | Task 4(화면), Task 2(서버). 숨은 칸은 계획 2번 ⚑, 보낸 뒤 닫힘은 계획 3번 ⚑ |
| 9.2 한 길·하나면 같은 화면·구역 순서·이름표(중립 띠)·보기만·근무 없음 한 줄·칸 링크와 `board_query`·주/달 메모 이름·제목·보기 전용·[내 근무표만 보기]·월간·모바일 | Task 2(글자는 계획 5번 ⚑) |
| 9.3 검색 모든 구역·필터는 내 구역·상자는 내 근무표가 있을 때·"(내 근무표에만 적용)"·유형 칸 규칙·변경 내역 모든 구역 | Task 2(To 후보 꼬리는 계획 8번) |
| 9.4 하루 화면 구역·날짜 링크가 목록을 넘김·팝업은 근무표 하나·`next`(고른 근무표·view·date·검색·필터·앵커)·`safe_next`·근무표 이름은 바꿀 수 있는 근무표가 둘 이상일 때 | Task 2(근무표 화면 `next`), Task 3(앵커는 계획 4번 ⚑) |
| 9.5 통계 그대로 + `ponytail:`, 알림 규칙 내 근무표 맨 위·`it_board()` → `home`, 이력 그대로, 회차 목록 근무표 열, 출근표 입력 목록 그대로 | Task 5 |
| 2절 "남는 IT 가정"(5단계: `home` 대체, 남은 `it_board()` 다시 grep 해 적기) | Task 5(grep), Task 6(ARCHITECTURE) |
| 10.4 5단계 메모·공지 | Task 6(OPERATIONS, 대조 쿼리는 계획 16번) |
| 11 스냅샷(하나 고른 주간·월간·하루가 1단계와 같음)·0025 테스트·겹쳐 보기 테스트 전부 | Task 1~4(스냅샷 범위는 계획 1번 ⚑), 쿼리 수 테스트(계획 9번) |
| 13 문서(보일 근무표·데이터 그림·OPERATIONS·OVERVIEW·PRINCIPLES·도움말 멤버 글), 설계 합치고 지우기 | Task 6 |
| 14 겹친 월간이 길다 | 기본 내 근무표 하나·[내 근무표만 보기]·하루 화면, PRINCIPLES 줄(Task 6) |
