# 근무표 통합 1·2단계(단계를 데이터로 · 공통 규칙 켜기) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `Board.input_mode` 갈래를 근무표 단계 설정 데이터(`use_draft`·`use_close`·`step_*`)와 쿼리 없는 단계 규칙으로 바꾸고(1단계, 보이는 변화 없음, 마이그레이션 0023), 이어서 IT 를 포함한 모든 근무표에 같은 회차 규칙(빈 평일 경고만·빈 날이 있을 때만 생성 확인창, 채우기 버튼, 입력 현황, 확인창 하나, 단계 이름 문구, 끈 단계 안내, 글 도움말 하나)을 켠다(2단계, 마이그레이션 없음). 관리 화면 단계 편집은 3단계.

**Architecture:** 단계 규칙은 `Board` 메서드(`step_name`·`steps`·`first_step`·`generate_from`·`editable`·`move_targets`·`step_buttons`)로 DB 를 읽지 않는다. 서비스·뷰·템플릿의 `input_mode` 갈래를 이 메서드와 데이터(켜진 장중관제 정의 유무)로 바꾼다. 1단계에서 지금 문구·확인창·채우기·빈 평일 처리·입력 그룹 자동 생성을 그대로 두려고 임시 기준 하나 `boards.legacy_admin_entry(board)`(= 마감을 안 쓰는 근무표)를 두고, 2단계 PR 이 화면·서비스 자리를 지운다(입력 그룹·부서 폼 자리와 함수는 3단계). 화면이 바뀌지 않았음은 main 코드로 만든 화면 스냅샷(`tests/snapshots/*.html`, `tests/test_snapshots.py`)이 지킨다.

**Tech Stack:** Python 3.12, Django 5.2, SQLite(WAL), pytest + pytest-django, htmx, Pico.css. 새 의존성 없음.

**Spec:** `docs/superpowers/specs/2026-11-17-boards-unify-design.md`(이 브랜치 최신판, Codex 리뷰 반영본. 1단계 장중관제 갈래·고정 생성 방식 글 결정 포함). 이 계획 = 12절 "1. 단계를 데이터로"·"2. 공통 규칙 켜기". 참고: 5.1 Board 칸(1·2단계 관리 화면 읽기 전용), 5.2 단계 규칙, 5.3 Department(1단계 몫), 5.4 버튼 이름·확인창, 6.1 갈래 자리 표("단계" 열 1·2), 10절 마이그레이션·업그레이드·공지, 11절 테스트(스냅샷·`move` 문구 단언), 13절 문서.

## 판단한 것 (설계가 정하지 않았거나 해석이 필요한 곳, 컨트롤러 검토용)

1. **0023 은 한 PR 안에서 두 번 고친다.** Task 2 가 칸·제약·`RunPython(forward)` 를, Task 5 가 `RemoveConstraint`·`RemoveField`·거꾸로 규칙을 더한다. `input_mode` 칸을 지우는 순간 남은 갈래를 모두 고쳐야 하므로, 갈래를 바꾸는 작업(Task 3 서비스, Task 4 화면)을 칸을 지우기 전에 따로 리뷰받으려는 것이다. 운영에는 PR 이 머지된 뒤의 완성된 파일 하나만 간다.
2. **스냅샷(설계 11절)**: `tests/test_snapshots.py` 하나가 `tests/snapshots/<이름>.html` 24개와 비교한다 — IT·운영팀 회차 화면 다섯 상태씩(운영팀은 쓰는 상태 + 남은 작성 중·마감), IT 네 부서가 다 찬 하루짜리 회차의 마감(생성 버튼이 눌리는 상태)과 그것을 생성한 생성됨(배정 횟수 표), 관제 정의를 끈 운영팀에 관제·점심당번 배정이 남은 확정 회차(Codex 리뷰: 관제 이력이 있는 직접 입력 근무표도 1단계에 main 그대로인지), 입력 표 넷, 회차 목록, [출근표 입력] 목록, 관리자 도움말, 근무표 하나 고른 화면 넷(IT 사람의 주간·월간·하루, 남의 근무표 주간 보기 전용). 배포된 회차에는 관제·점심당번 배정이 있어 근무표 칸이 비지 않는다(5단계가 이 기준과 주간·월간·하루를 비교하므로 첫 커밋에서만 만들 수 있다). `<main>` 안에서 메뉴(`<header>`, 3단계에서 바뀐다)를 빼고 공백을 한 칸으로, CSRF 값·회차 번호를 지우고 태그마다 한 줄로 저장한다. 날짜는 `fixed_today` 로, 보기(주간·월간)는 주소로, 화면 아래 저장소 링크는 `settings.REPO_URL = ""` 로 고정한다(개발자 셸의 `DUTY_REPO_URL` 에 흔들리지 않게). `DUTY_SNAPSHOT_WRITE=1` 실행은 기준을 다시 쓴 뒤 **일부러 실패**한다(변수가 남아 기준이 몰래 바뀌는 일을 막는다).
3. **`move` 문구 단언(설계 11절)**은 Task 1 에서 main 코드로 `tests/test_period_lifecycle.py` 에 더한다(배포됨·같은 상태·`MOVABLE` 밖·직접 입력 네 글). Task 2 의 기계적 변경 스크립트가 그 테스트의 직접 입력 근무표도 `OPS_STEPS` 로 바꾼다.
4. **`move` 의 `move_targets` 밖 글(설계 6.1)**: 대상이 `MOVABLE` 밖이면 "옮길 수 없는 상태입니다.", 그 밖은 근무표와 상관없이 "직접 입력 근무표는 입력 중으로만 옮길 수 있습니다."(설계 글 그대로. 1·2단계에서 이 글이 나올 수 있는 근무표는 사실상 옛 직접 입력뿐이다 — 저장된 근무표 단계 칸이 읽기 전용). 2단계에서 뒤의 글만 "'<켠 배포 전 단계 이름들, ·로 이음>'(으)로만 옮길 수 있습니다."로.
5. **테스트의 "직접 입력 근무표"는 `tests/it_defs.OPS_STEPS`**(작성 중·마감 끔, 입력 중·확정 이름). Task 2~4 동안은 `input_mode="direct"` 를 함께 담고(코드가 아직 그 칸을 읽는다) Task 5 에서 그 키만 뺀다. 기존 테스트의 `Board.objects.create(..., input_mode=직접 입력)` 은 Task 2 에서 스크립트로 한 번에 `**OPS_STEPS` 로 바꾼다 — **19개 파일, 24줄**(conftest·Task 1 의 `test_period_lifecycle.py` 포함. 관리 화면 POST 의 `input_mode="direct"` 7곳은 Task 5). 파일마다 있는 `ops` 픽스처를 conftest 하나로 합치는 일은 하지 않는다(범위 밖). conftest 에는 설계 11절의 `ops_board` 하나만 더한다.
6. **1단계 `Department.save` 는 순환 import 를 피해 함수 안에서** `from .services.boards import legacy_admin_entry` 로 부른다(설계 5.3 "조건만 `not legacy_admin_entry(board)`", 임시 기준은 `services/boards.py` 한 함수에만). 3단계에서 이 갈래와 함께 지운다.
7. **관제 이력이 있는 직접 입력 근무표도 1단계는 main 그대로**(Codex 리뷰): 1단계에서 버튼 글자([확정]·[장중관제 생성])·[재생성]·[생성 방식] 버튼과 상자·배정 횟수 표는 켜진 관제 정의가 아니라 **임시 기준**(`legacy_admin_entry`)으로 고른다 — `step_buttons(not legacy)`, 상자·횟수 표는 `not legacy` 일 때만, 상자 글은 main 의 고정 글("10칸(08:30~18:00)에 개발자를"). 그래서 관리 화면에서 관제 정의를 켰거나 관제 배정이 남은 옛 직접 입력 근무표도 1단계 화면이 바이트 단위로 같다(스냅샷 `period-ops-slot-history`, 테스트 `test_legacy_board_with_slot_defs_looks_like_main`). 2단계(Task 8)에서 설계 6.1 의 데이터 기준(켜진 관제 정의, 횟수 표는 `counts` 가 있으면)과 정의에서 만든 생성 방식 글(`shifts.gen_help`, IT 글은 그대로)로 바꾼다. OPERATIONS 1단계 업그레이드 전 확인 ②(직접 입력 근무표마다 켜진 관제 정의 수와 남은 관제 배정 행 수)는 **2단계를 위한 참고**로 남기고, **2단계를 올리기 직전에 같은 확인을 다시 돌려**(작성 중·마감을 둘 다 끈 근무표 기준) 그 결과로 공지와 진행을 정한다(Task 10). 경우가 둘이다: 켜진 관제 정의가 있으면 [장중관제 생성]·[재생성]·[생성 방식]이 생기고, 정의는 없고 배정 행만 남았으면 버튼은 그대로이고 배정 횟수 표와 나가는 확인창 글만 바뀐다. 해당 근무표의 관리자 모두에게 경우에 맞게 공지한다.
8. **버튼 이름(설계 5.4)** 은 `Board.step_buttons(has_slots) -> dict`(`open`·`close`·`generate`·`regenerate`·`undo`). 떼기를 할 수 없는 이름: 취합 중 이름이 " 중"으로 끝나지 않으면 열기·마감은 "'<취합 중 이름>'(으)로"·"'<마감 이름>'(으)로". 생성은 설계의 예("확정" → [확정], "완료됨" → [완료])를 따라 **끝의 "됨"을 떼고, "됨"으로 끝나지 않으면 이름 그대로** 쓴다(설계 본문의 "'<생성됨 이름>'(으)로" 꼴과 예가 어긋나는데, 시장운영실 기본 이름 "확정"이 지금 글자 [확정]·[확정 취소]를 내야 하므로 예를 따랐다. 그래서 취소도 늘 "<생성 버튼> 취소"이고 "'…'(으)로 돌아가기" 꼴은 쓸 일이 없다). 버튼 글자가 비거나 서로(또는 [배포…]·[재생성]과) 겹치는 이름은 `Board.bad_buttons()` 로 찾아 관리 화면 근무표 폼이 칸 오류로 막는다("버튼 이름이 비거나 다른 버튼과 같아집니다: […]", Task 5 — 1·2단계에는 만들 때만 고치므로 만들 때 검사). 미리보기는 [근무표 설정](3단계) 몫이다.
9. **확인창의 이름 글은 `escapejs`, 이름 뒤 조사는 `josa`**(검토 지적): 인라인 JS `confirm('…')` 안에 넣는 동적 글(1단계 [확정]·[확정 취소] 확인창, 배포 취소 확인창의 생성됨 이름, 2단계 `empty_confirm`·`leave_generated_confirm`)은 모두 `|escapejs` 로 넣는다(기본 이름이면 출력이 같다. 따옴표·역슬래시가 든 이름 테스트 `test_step_names_are_escaped_in_confirm`). 순수 함수 `shifts.josa(word, "은/는"|"을/를"|"으로/로")` 가 받침으로 고른다(ㄹ 받침은 '로', 한글로 끝나지 않으면 '은(는)'·'(으)로'). 1단계의 "<생성>은 할 수 있지만", [확정 취소] 확인창 "<생성>을 취소하고 <단계>으로 돌아갈까요?", 배포 취소 글 "<생성됨 이름>으로"를 이것으로 만든다(기본 이름이면 지금 글자 그대로). 2단계 새 글은 조사가 필요 없는 꼴로 쓴다("[<생성>] 버튼은 …", "'<이름>' 상태로", "'<이름>'(으)로").
10. **1단계 관제 생성에서 빼는 날** = 그 회차 출근 행이 하나도 없는 날(설계 6.1 `slot_dates`). 부서 하나인 근무표와 IT(1단계는 빈 날이 있으면 막는다)에서는 지금과 같다.
11. **2단계 빈 평일 글(검토 지적 반영)**: 날짜는 이어진 평일끼리 묶는다(`shifts.day_spans`: "11/16~11/20, 11/24", 금 → 월도 이어진 것으로). 생성 경고(메시지) = "출근표가 비어 있는 날이 있습니다: 운영 1일(11/20), UI 5일(11/16~11/20). 그날 그 부서는 근무자가 없습니다." 회차 화면 ⚠ 줄 = "⚠ 출근표가 비어 있는 날: 운영 2일(11/19~11/20) · UI 5일(11/16~11/20)." — 켠 단계의 취합 중·마감에서만, 그리고 **그 상태에서 생성할 수 있을 때만**(`status == generate_from()`) 뒤에 " [<생성 버튼>] 버튼은 누를 수 있지만 그날 그 부서는 근무자가 없습니다."(컨트롤러 결정: IT 취합 중에는 생성할 수 있다고 말하지 않는다). 생성 확인창 = "출근표가 비어 있는 부서가 있는 날이 N일 있습니다. 그날 그 부서는 근무자가 없고, 아무 부서도 넣지 않은 날은 장중관제도 만들지 않습니다. 계속할까요?"(관제가 없으면 "…근무자가 없습니다. 계속할까요?", N = 어느 부서든 빈 평일 수). 여러 부서 근무표에서 "그날은 근무자가 없습니다"처럼 아무도 없는 것으로 읽히지 않게 늘 "그 부서"라 쓴다. 부서는 이름으로, 순서는 입력 현황과 같은 부서 코드 순. 빈 날이 있으면 생성 버튼은 테두리 버튼(설계 14절), 마감 끈 근무표는 첫 [표 입력]이 진한 버튼.
12. **2단계 생성됨에서 나가는 확인창(설계 5.4)**(없음·관제만·점심당번만·둘 다를 매개변수 테스트로 정확한 글까지 본다): 생성됨 회차는 **그 회차의 `DutyAssignment`**(관제 칸·점심당번 유무)로, 그 밖 상태의 옮기기 상자 설명은 켜진 정의로 이름을 만든다(`views.manage._leave_what`). "생성 결과(장중관제·점심당번 배정)가 지워지고 출근표는 그대로 남습니다. 계속할까요?", 하나만 있으면 그것만, 없으면 "출근표는 그대로 남습니다. 계속할까요?". 옮기기 상자의 `<small>` 설명도 같은 이름("생성됨에서 나가면 <이름> 생성 결과만 지웁니다", 없으면 그 문장을 뺀다).
13. **2단계 문구 모양**: 기간 = "기간은 '<이름>' 단계에서만 고칠 수 있습니다."(켠 단계 ∩ `editable()` 이라 늘 이름 하나), 생성 = "'<generate_from 이름>'인 회차만 <생성 버튼 말>할 수 있습니다.", 배포 = "'<생성됨 이름>'인 회차만 배포할 수 있습니다.", 채우기 상태 = `_require_input` 과 같은 "<취합 중 이름>인 회차가 아닙니다."(같은 함수 `_require_collecting`), 입력 표 닫힘 = "'<취합 중 이름>'인 회차가 아니라 저장할 수 없습니다.", 생성 성공 = "'<생성됨 이름>' 상태로 바꿨습니다. 근무표 화면에는 배포한 뒤에 보입니다.", 입력 표 회차 링크 = "← 회차 화면으로". 끈 단계 안내 = "이 단계는 지금 쓰지 않습니다. 아래 [다른 상태로 옮기기]를 눌러 옮기세요."(검토 지적: 실제 상자 이름을 쓴다) + 그 상자를 펼쳐 둔다.
14. **2단계 입력 현황**: 모든 근무표·모든 상태에서 **부서 이름**으로(검토 지적, 코드 대신), 취합 중일 때만 부서마다 [표 입력] **버튼**(컨트롤러 결정: 누를 자리 44px 이상, 테두리 보조 버튼). 기간 줄이기 확인창은 기간을 고칠 수 있는 모든 회차(IT 작성 중 포함).
15. **관리 화면 단계 칸은 1·2단계 내내 읽기 전용**(설계 5.1·6.1·12: 입력 그룹 기준 `legacy_admin_entry` 가 2단계까지 남아 섞인 상태를 막는다). 그래서 2단계 롤백은 코드만 되돌리면 된다(바뀐 단계 설정이 생길 수 없다).
16. **2단계 글 도움말**: `help.TEXTS` 의 `"direct"` → `"period"`("회차 운영(단계·출근표·생성·배포)", 대상 "근무표 관리자", `perms.is_admin`). 맨 앞에 내가 관리하는 근무표마다 단계 줄. 채우기 설명은 입력 담당자 글(`STEPS["manager"]`)에 한 줄(영상에는 없는 기능이라는 주석).
17. **업그레이드 확인 쿼리**: 설계 10.3 의 1단계 쿼리 `COUNT(*)` 는 회차 없는 근무표를 1로 세므로 `COUNT(p.id)`. 1단계 뒤 대조 쿼리와 확인 ②(관제 켠 직접 입력 근무표)를 더하고, 2단계 올리는 때는 설계 10.3 그대로(IT 의 취합 중·마감·생성됨 회차가 없어야 한다). 모두 0022·0023 상태 임시 DB 에서 돌려 봤다. 1단계 롤백 글은 "거꾸로 `migrate` 는 코드를 되돌리기 **전에**, 아니면 `restore` 만"으로 고쳤다(검토 지적: 옛 코드에는 0023 파일이 없다).
18. **2단계 공지**(검토 지적): 알릴 사람에 시장운영실 근무표 관리자를 더하고([확정]이 빈 날이 없으면 묻지 않음, 입력 현황), 채우기 버튼 글을 실제 조건으로("모든 부서에 [지난주와 같게], 근무조가 셋인 부서는 [2주 전 기준으로 채우기]도"). 설계 10.4 도 같은 글과 경우별 덧붙임으로 맞췄다.
19. **`add_board` 출력** "(코드 mops, 관리자 직접 입력)" → "(코드 mops, 단계 입력 중 → 확정 → 배포됨)". 함수 이름 `create_direct_board` → `create_board`(설계 6.1).

## Global Constraints

- IT 알림 문구·hash 는 바뀌지 않는다. `tests/test_alarm_texts_it.py` 는 고치지 않고 그대로 통과한다(알림 코드를 건드리지 않는다).
- **1단계(Task 1~6)는 보이는 동작이 바뀌지 않는다**: 오류·안내 문구와 확인창은 한 글자도 바꾸지 않고, `tests/snapshots/*.html`(Task 1 에서 main 코드로 만든 기준)을 Task 2~6 에서 고치지 않는다. 지금 문구를 박은 기존 테스트(`test_direct_periods.py`·`test_views_direct.py`·`test_period_lifecycle.py`·`test_publish.py`·`test_collect.py`·`test_fill.py`·`test_views_collect.py`·`test_views_manage.py`)의 문구 단언도 1단계에서 고치지 않는다(바뀌는 것은 근무표를 만드는 줄의 `input_mode` 뿐). 관리 화면 근무표의 단계 칸은 1·2단계에서 만들 때만 고친다(저장된 근무표는 읽기 전용, 3단계에서 연다).
- 2단계 문구의 단계 이름 목록은 **켠 단계**에서만 만든다(끈 단계 이름이 오류 글에 나오지 않게). 상태를 말하는 글은 "'<이름>' 상태로", "'<이름>'(으)로" 꼴(설계 5.4). 바꿀 수 있는 이름 뒤에 조사가 꼭 필요하면 `shifts.josa` 로 고른다.
- 각 작업이 끝난 시점에 `.venv/bin/pytest -W error -q` 전체가 통과한다(경고 0개). 기대 테스트 수는 참고값(지금 main 02c79c5 **1246 passed**).
- TDD(테스트를 먼저 쓰고 실패를 확인한 뒤 구현). DB 를 바꾸는 규칙은 `duty/services/`(뷰·명령에서 모델을 직접 고치지 않는다. 관리 화면의 Django 기본 저장은 그대로). 순수 모듈(`shifts`·`generator`·`csv_io`·`ics`·`alarms/`(senders 제외)·`market_days`)에는 ORM 없음. `Board` 단계 메서드는 DB 를 읽지 않는다.
- "오늘"은 `from . import perms` 후 `perms.today()`. 정해진 값 칸은 `choices` + DB `CheckConstraint`, 기록을 남길 FK는 `PROTECT`. 마이그레이션 파일은 지우지 않는다. 1단계 새 마이그레이션은 `0023_board_steps` 하나, 2단계는 없다. 작업마다 `DUTY_DEBUG=1 DUTY_ENV_FILE= DUTY_DATA_DIR=$(mktemp -d) .venv/bin/python manage.py makemigrations duty --check --dry-run` → "No changes detected in app 'duty'".
- 0023 거꾸로는 0018~0022 처럼 **잃을 데이터가 있을 때만** 거부한다(`input_mode` 로 나타낼 수 있는 근무표면 되돌리고, 아니면 그 근무표 code 를 알려 주며 `RuntimeError`, "백업" 낱말 포함).
- 화면 문구·오류 메시지는 한국어. 커밋 메시지는 `feat:`/`fix:`/`docs:`/`style:` + 한국어 요약, 끝에 아래 두 줄:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
  ```
- 실명 데이터 금지(테스트·가짜 데이터는 "가상가" 같은 가상 이름만). `data/`, DB 파일, `.superpowers/`, `.env` 는 열지 않는다. 로그에는 아이디(멤버 코드)만.
- 운영은 단순하게: 새 deploy 파일·셸 스크립트·타이머를 만들지 않는다. 정적 파일은 CDN 없이.
- 화면을 바꾸는 작업(1단계는 관리 화면 근무표 폼만, 2단계는 회차·입력 표·도움말)은 테스트 통과만으로 끝내지 않고 아래 "브라우저 확인 준비"대로 띄운 가짜 데이터 DB 에서 PC 1400px·휴대폰 390px, 글씨 **아주 크게**(오른쪽 위 [가] 두 번), **다크 모드**(오른쪽 위 ◐)로 본다. 모든 브라우저 단계에서 콘솔 `document.documentElement.scrollWidth > innerWidth` 가 `false`(가로 넘침 없음, 넓은 표는 표 안에서만 스크롤). 보는 사람은 시력이 좋지 않고 변화를 싫어하는 60세 가까운 관리자다: 화면마다 진한 버튼 하나, 큰 누름 영역(44px 이상).
- 각 PR 은 그 단계의 문서(ARCHITECTURE·OPERATIONS·OVERVIEW·DEVELOPMENT·PRINCIPLES 결정 기록)를 같은 PR 에서 고친다. 계획·구현·최종 Codex 리뷰(읽기 전용, DB·`data/`·`.superpowers/` 를 열지 말라고 지시)와 테스트 통과 확인 뒤 머지한다(테스트 결과 확인과 `gh pr merge` 를 한 명령으로 잇지 않는다).

### 브라우저 확인 준비(화면 작업 공통, Task 4 이후)

가짜 데이터만 쓰는 임시 폴더에서 띄우고, 끝나면 서버를 PID 로 끄고 폴더를 지운다. Task 4~9 어느 상태에서도 돈다(운영팀은 단계 칸으로 만든다. Task 4 상태에서는 아직 `input_mode` 칸이 기본값 collect 라 운영 부서에 빈 입력 그룹이 하나 생기는데, 멤버가 없어 화면에는 차이가 없다).

```bash
W=$(mktemp -d)
export DUTY_ENV_FILE= DUTY_DEBUG=1 DUTY_DATA_DIR=$W/data
.venv/bin/python manage.py migrate -v0
.venv/bin/python manage.py shell < tools/help_videos/seed.py > /dev/null     # IT 가짜 데이터(계정 비밀번호 Demo-pass-123)
.venv/bin/python manage.py shell <<'EOF'
# 가짜 '운영팀' 근무표(시장운영실 모양: 작성 중·마감 없음, 실명 없음). seed.py 다음에 같은 임시 DB 에서만 돌린다
from datetime import time, timedelta
from duty import perms
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
periods.save_draft(Period(board=ops, name="이번 2주", start_date=mon, end_date=mon + timedelta(days=11)), by=admin)
print("운영팀 준비 끝")
EOF
.venv/bin/python manage.py runserver 127.0.0.1:8795 > $W/server.log 2>&1 &
echo $! > $W/server.pid
```
(사본에서 Task 4 상태와 Task 9 상태 둘 다 돌려 "운영팀 준비 끝"을 확인했다.)

로그인: `admin` / `Demo-pass-123`(슈퍼유저 + IT·운영팀 관리 그룹), `member` / `Demo-pass-123`(일반), `manager` / `Demo-pass-123`(IT 매칭엔진실 입력 담당). 관리 화면은 `http://127.0.0.1:8795/admin/`.

끝나면:
```bash
kill $(cat $W/server.pid); rm -rf $W; unset DUTY_ENV_FILE DUTY_DEBUG DUTY_DATA_DIR
```

## 작업 순서와 마이그레이션 번호

| PR | Task | 내용 | 마이그레이션 | 테스트 수(참고) |
|---|---|---|---|---|
| 1단계 | 1 | 첫 커밋(main 코드): 화면 스냅샷 기준 24개, `move` 네 문구 단언, conftest `ops_board` | 없음 | 1251 |
| 1단계 | 2 | `Board` 단계 칸·단계 규칙 메서드·`legacy_admin_entry`, 0023(칸·제약·forward), 테스트의 직접 입력 근무표 → `OPS_STEPS` | 0023(1/2) | 1264 |
| 1단계 | 3 | 서비스가 단계 규칙을 따른다(새 회차·기간·생성·`move` 검사 순서·입력·채우기·배포, 관제 빈 날, `status_label`, `add_board` 값) | 없음 | 1281 |
| 1단계 | 4 | 화면이 단계 규칙을 따른다(회차 화면 버튼 한 묶음·`step_buttons`(떼기 못 하는 이름)·`josa`·`escapejs`, 장중관제 갈래는 임시 기준으로 main 그대로, 입력 표, 입력 목록, 도움말 기준) | 없음 | 1290 |
| 1단계 | 5 | `input_mode` 지우기: 0023(제거·거꾸로 규칙), `InputMode`·`DIRECT_STEPS`·`step_label`, 부서 하나 규칙, 입력 그룹·부서 폼 기준을 `legacy_admin_entry` 로, 관리 화면 단계 칸(만들 때만, 버튼 글자 검사 `bad_buttons`), `create_board` | 0023(2/2) | 1303 |
| 1단계 | 6 | 문서(ARCHITECTURE·OVERVIEW·OPERATIONS 업그레이드·확인 쿼리 ①②·롤백 순서·DEVELOPMENT·PRINCIPLES) | 없음 | 1303 |
| 2단계 | 7 | 서비스 공통 규칙(빈 평일 경고만·`day_spans`, 채우기 모든 근무표, 단계 이름 문구) | 없음 | 1301 |
| 2단계 | 8 | 화면 공통 규칙(관제 정의 기준·`gen_help`, ⚠ 줄·빈 날 확인창·입력 현황 이름·[표 입력] 버튼·실제 배정으로 만든 나가는 확인창·끈 단계 안내·입력 표 글, `escapejs`) + 스냅샷 다시 쓰기 | 없음 | 1311 |
| 2단계 | 9 | 글 도움말 하나("회차 운영")·입력 담당 글에 채우기 + 스냅샷 | 없음 | 1312 |
| 2단계 | 10 | 문서(ARCHITECTURE·OVERVIEW·OPERATIONS 2단계 올리는 때·공지·PRINCIPLES) | 없음 | 1312 |

> 검증: Task 1~10 의 코드·문서 편집을 이 브랜치(설계 최신판, 코드는 main 02c79c5 그대로) 사본(`git archive`)에 그대로 넣어 확인했다. 저장소는 고치지 않았다. 결과: 작업마다 위 표의 수로 `.venv/bin/pytest -W error -q` 전체 통과, 경고 0개, `makemigrations duty --check --dry-run` → "No changes detected in app 'duty'", 새 DB 에서 `migrate` → `migrate duty 0022` → `migrate` 왕복. 각 작업의 "실패 확인" 기대 결과도 사본에서 재현했다. 스냅샷은 `DUTY_REPO_URL` 을 준 셸에서도 같았고, 1단계 Task 2~6 내내 기준(관제 이력이 남은 운영팀 회차 포함)을 고치지 않고 통과했다. 업그레이드 확인 쿼리(①·②·뒤 대조·2단계 시점)는 임시 DB 에 `sqlite3 -readonly` 로 돌렸다. 문서 편집의 "찾을 글"은 사본에서 모두 한 번씩만 나왔다. 브라우저 확인은 사본에서 하지 않았다(가짜 데이터 셸 스니펫이 도는 것까지만 확인) — 각 작업의 브라우저 단계에서 사람이 본다.

---

# 1단계 PR: 단계를 데이터로 (마이그레이션 0023, 보이는 변화 없음)

브랜치: `feat/board-steps`(main 에서). PR 제목: `feat: 근무표 입력 방식 갈래를 단계 설정 데이터로(근무표 통합 1단계)`.

### Task 1: 첫 커밋 — 화면 스냅샷 기준과 `move` 문구 단언(main 코드)

> 범위: 테스트만. 앱 코드는 바꾸지 않는다. **이 작업은 앱 코드를 고치기 전에(main 그대로) 한다** — 스냅샷과 문구 단언이 main 의 화면·글자여야 한다(설계 11·12절 "1단계 PR 첫 커밋").

**Files:**
- Modify: `tests/conftest.py` — `from datetime import time` 한 줄, `lunch` 픽스처 앞에 `ops_board`
- Create: `tests/test_snapshots.py`
- Create(생성 파일): `tests/snapshots/*.html` 24개 — 테스트가 `DUTY_SNAPSHOT_WRITE=1` 일 때 쓴다(손으로 쓰지 않는다)
- Modify: `tests/test_period_lifecycle.py` — 맨 끝에 `move` 문구 단언 둘

**Interfaces:**
- Consumes: conftest `it_board`·`depts`·`admin_user`·`fixed_today`, `Board.InputMode.DIRECT`(Task 2 에서 `OPS_STEPS` 로 바뀐다)
- Produces:
  - 픽스처 `ops_board(it_board) -> Board`: code `ops`, 이름 "운영팀", 근무조 이른(07:30)·가운데(09:30)·늦은(11:30) + 점심당번, 부서 `OPS`("운영", 출근조 셋), 장중관제 없음
  - `tests/test_snapshots.py::test_pages_match_snapshots` 와 기준 파일 24개: `period-it|ops-<상태>` 10, `period-it-full-closed`·`period-it-full-generated`(IT 네 부서가 다 찬 하루짜리 회차, 생성 버튼이 눌리는 마감과 배정 횟수 표가 있는 생성됨), `period-ops-slot-history`(관제 정의를 끈 운영팀에 관제·점심당번 배정이 남은 확정 회차 — main 은 [확정 취소]만, 배정 횟수 표 없음), `table-it-collecting`·`table-it-closed`·`table-ops-collecting`·`table-ops-generated`, `periods`, `collect-index`, `help-admin`, IT 사람의 `roster-mine`(`/?view=week`)·`roster-month`(`/?view=month`)·`day`(`/day/2026-11-16/`)·`roster-other`(`/?board=ops&view=week`, 보기 전용). 배포된 회차에는 관제·점심당번 배정이 있다
  - 다시 쓰는 법: `DUTY_SNAPSHOT_WRITE=1 .venv/bin/pytest -q tests/test_snapshots.py` → 기준을 다시 쓰고 **일부러 `1 failed`**("스냅샷을 다시 썼습니다…"). 그다음 변수 없이 다시 돌려 통과를 본다(2단계 Task 8·9 만 쓴다. 지운 기준 파일도 정리한다)

- [ ] **Step 1: 픽스처·스냅샷 테스트·문구 단언을 쓴다**

`tests/conftest.py` 맨 위 import 에 한 줄:
```python
from datetime import time
from itertools import count
```
`lunch` 픽스처 바로 앞에:
```python
@pytest.fixture
def ops_board(it_board):
    """가짜 '운영팀' 근무표(시장운영실과 같은 모양): 작성 중·마감 없음, 근무조 셋 + 점심당번, 부서 하나, 장중관제 없음."""
    board = Board.objects.create(code="ops", name="운영팀", input_mode=Board.InputMode.DIRECT)
    for key, name, h in (("dawn", "이른", 7), ("normal", "가운데", 9), ("dinner", "늦은", 11)):
        BoardShift.objects.create(board=board, key=key, name=name, start=time(h, 30), end=time(h + 9, 30), default_alarm=True)
    BoardShift.objects.create(board=board, key=LUNCH, name="점심당번")
    Department.objects.create(code="OPS", name="운영", shifts="dawn,normal,dinner", board=board)
    return board
```

`tests/test_snapshots.py`(새 파일):
```python
"""화면 스냅샷(근무표 통합 설계 11절): 회차·입력 표·근무표·도움말 화면 본문(<main> 안, 메뉴 빼고)을 tests/snapshots/ 의
기준 HTML 과 비교한다. 기준은 1단계 PR 첫 커밋에서 main 코드로 만들었다. 1단계는 기준을 고치지 않고 통과해야 하고,
보이는 동작을 일부러 바꾸는 PR 만 DUTY_SNAPSHOT_WRITE=1 로 다시 쓰고 바뀐 줄을 PR diff 로 리뷰한다. 이름은 모두 가상."""
import os
import re
from datetime import date, datetime, time, timezone
from pathlib import Path

import pytest

from duty.models import BoardShift, Commute, Department, DutyAssignment, Period, PeriodEvent, User
from duty.services.generate import run_generation

SNAP = Path(__file__).parent / "snapshots"
S = Period.Status
MON, FRI = date(2026, 11, 16), date(2026, 11, 20)
TUE = date(2026, 11, 17)
AT = datetime(2026, 11, 16, 9, tzinfo=timezone.utc)


def _main(body: str) -> str:
    main = body.index("<main")
    body = body[body.index("</header>", main) + len("</header>"):body.index("</main>")]  # 메뉴는 보지 않는다(3단계에서 바뀐다)
    body = re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', 'name="csrfmiddlewaretoken"', body)
    body = re.sub(r"/(periods|collect)/\d+/", r"/\1/N/", body)  # 회차 번호는 테스트 순서에 따라 다를 수 있다
    body = re.sub(r"\s+", " ", body)  # 템플릿 줄바꿈·들여쓰기 차이는 보지 않는다
    return re.sub(r">\s*<", ">\n<", body).strip() + "\n"  # 태그마다 한 줄(리뷰할 diff 를 읽기 쉽게)


@pytest.fixture
def world(settings, fixed_today, depts, admin_user, ops_board):
    settings.REPO_URL = ""  # 화면 아래 저장소 링크(<main> 안)가 개발자 셸의 DUTY_REPO_URL 에 따라 달라지지 않게
    fixed_today(MON)
    ops_board.admin_group.user_set.add(admin_user)
    it_m = User.objects.create_user("MEMS901", password=None, name="가상일", department=depts["MEMS"], type="개발자")
    ops_m = User.objects.create_user("OPS901", password=None, name="가상이", department=Department.objects.get(code="OPS"),
                                     type="직원")
    out = {}
    for board, member, tag in ((depts["MEMS"].board, it_m, "it"), (ops_board, ops_m, "ops")):
        for status in S.values:
            p = Period.objects.create(board=board, name=f"{tag} {status}", start_date=MON, end_date=FRI, status=status)
            if status == S.PUBLISHED:  # 배포 취소 상자가 보이게
                p.publish_undo, p.published_at, p.overwrite_from = [], AT, MON
                p.save()
                PeriodEvent.objects.create(period=p, from_status=S.GENERATED, to_status=S.PUBLISHED)
            for d in p.dates()[:3]:  # 목·금은 비워 둔다(빈 평일 경고·입력 현황)
                Commute.objects.create(period=p, date=d, member=member, shift="dawn")
            out[(tag, status)] = p
    # 배포된 날의 칸이 비지 않게(근무표 주간·월간·하루 화면): IT 관제 둘, 운영팀 점심당번 하나
    DutyAssignment.objects.create(period=out["it", S.PUBLISHED], date=MON, cell="slot0", member=it_m)
    DutyAssignment.objects.create(period=out["it", S.PUBLISHED], date=TUE, cell="slot1", member=it_m)
    DutyAssignment.objects.create(period=out["ops", S.PUBLISHED], date=MON, cell="lunch", member=ops_m)
    # IT 네 부서가 다 찬 하루짜리 회차: 마감(생성 버튼이 눌리는 상태)과, 그것을 생성한 생성됨(배정 횟수 표)
    devs = [User.objects.create_user(f"{c}8{i}", password=None, name=f"가상{c}{i}", department=depts[c], type="개발자")
            for c in ("MEMS", "TMCH") for i in range(5)]
    staff = [User.objects.create_user(f"{c}80", password=None, name=f"가상{c}", department=depts[c], type="직원")
             for c in ("MD", "UI")]
    for status in (S.CLOSED, S.GENERATED):
        p = Period.objects.create(board=depts["MEMS"].board, name=f"it full {status}", start_date=MON, end_date=MON,
                                  status=S.CLOSED)
        for i, m in enumerate(devs + staff):
            Commute.objects.create(period=p, date=MON, member=m, shift="normal" if i % 2 else "dinner")
        if status == S.GENERATED:
            run_generation(p, seed=1)
        out[("it-full", status)] = p
    # 장중관제 이력이 남은 직접 입력 근무표(설계 리뷰): 꺼진 관제 정의와 그 배정이 남은 확정 회차. 1단계는 main 처럼 [확정]만
    BoardShift.objects.create(board=ops_board, key="slot0", name="점검", start=time(10), end=time(11),
                              eligible_shifts=["dawn"], eligible_types=["직원"], active=False)
    p = Period.objects.create(board=ops_board, name="ops slot history", start_date=MON, end_date=FRI, status=S.GENERATED)
    for d in p.dates()[:3]:
        Commute.objects.create(period=p, date=d, member=ops_m, shift="dawn")
    DutyAssignment.objects.create(period=p, date=MON, cell="slot0", member=ops_m)
    DutyAssignment.objects.create(period=p, date=MON, cell="lunch", member=ops_m)
    out[("ops", "slot-history")] = p
    PeriodEvent.objects.update(at=AT)
    return out, it_m


def _pages(client, admin_user, world):
    p, member = world
    client.force_login(admin_user)
    pages = {f"period-{tag}-{st}": f"/periods/{x.pk}/" for (tag, st), x in p.items()}
    pages |= {
        "table-it-collecting": f"/collect/{p['it', S.COLLECTING].pk}/MEMS/",
        "table-it-closed": f"/collect/{p['it', S.CLOSED].pk}/MEMS/",
        "table-ops-collecting": f"/collect/{p['ops', S.COLLECTING].pk}/OPS/",
        "table-ops-generated": f"/collect/{p['ops', S.GENERATED].pk}/OPS/",
        "periods": "/periods/", "collect-index": "/collect/", "help-admin": "/help/",
    }
    got = {}
    for name, url in pages.items():
        r = client.get(url)
        assert r.status_code == 200, name
        got[name] = _main(r.content.decode())
    client.force_login(member)  # 근무표 하나 고른 화면: 내 근무표 주간·월간·하루, 남의 근무표(보기 전용). 보기는 주소로 고정
    for name, url in (("roster-mine", "/?view=week"), ("roster-month", "/?view=month"), ("day", "/day/2026-11-16/"),
                      ("roster-other", "/?board=ops&view=week")):
        r = client.get(url)
        assert r.status_code == 200, name
        got[name] = _main(r.content.decode())
    return got


def test_pages_match_snapshots(client, admin_user, world):
    got = _pages(client, admin_user, world)
    if os.environ.get("DUTY_SNAPSHOT_WRITE"):
        SNAP.mkdir(exist_ok=True)
        for old in SNAP.glob("*.html"):
            old.unlink()
        for name, body in got.items():
            (SNAP / f"{name}.html").write_text(body, encoding="utf-8")
        pytest.fail("스냅샷을 다시 썼습니다. git diff tests/snapshots/ 로 바뀐 줄을 보고, 변수 없이 다시 돌리세요.")
    assert sorted(f.stem for f in SNAP.glob("*.html")) == sorted(got)
    for name, body in got.items():
        assert body == (SNAP / f"{name}.html").read_text(encoding="utf-8"), name
```

`tests/test_period_lifecycle.py` 맨 끝에(지금은 네 글에 단언이 없다, 설계 11절):
```python
# ── 옮기기 오류 글(근무표 통합 1단계가 순서를 바꿔도 네 글자는 그대로, 설계 6.1) ──

@pytest.mark.parametrize("status,to,msg", [
    (S.PUBLISHED, S.COLLECTING, "배포된 회차는 배포 취소로만 되돌릴 수 있습니다."),
    (S.COLLECTING, S.COLLECTING, "이미 그 상태입니다."),
    (S.DRAFT, S.GENERATED, "옮길 수 없는 상태입니다."),
])
def test_move_messages(it_board, status, to, msg):
    p = Period.objects.create(board=it_board, name="p", start_date=d(11, 9), end_date=d(11, 13), status=status)
    with pytest.raises(DutyError) as e:
        periods.move(p, to)
    assert str(e.value) == msg


def test_move_message_for_board_without_draft_and_close(it_board):
    ops = Board.objects.create(code="ops", name="운영팀", input_mode="direct")
    p = Period.objects.create(board=ops, name="p", start_date=d(11, 9), end_date=d(11, 13), status=S.GENERATED)
    with pytest.raises(DutyError) as e:
        periods.move(p, S.DRAFT)
    assert str(e.value) == "직접 입력 근무표는 입력 중으로만 옮길 수 있습니다."
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_snapshots.py tests/test_period_lifecycle.py`
Expected: `1 failed` — `test_pages_match_snapshots` 의 `AssertionError: assert [] == ['collect-index', …]`(기준 파일이 없다). `move` 문구 단언 4개는 main 코드에서 통과한다(지금 글자를 박는 테스트다).

- [ ] **Step 3: main 코드로 기준을 쓴다(앱 코드는 main 그대로여야 한다)**

Run: `git status --short duty/` → 아무것도 안 나와야 한다. 그다음
`DUTY_SNAPSHOT_WRITE=1 .venv/bin/pytest -W error -q tests/test_snapshots.py; ls tests/snapshots | wc -l`
Expected: `1 failed`("스냅샷을 다시 썼습니다. git diff tests/snapshots/ 로 바뀐 줄을 보고, 변수 없이 다시 돌리세요." — 다시 쓴 실행은 늘 실패한다), `24`. `tests/snapshots/period-it-closed.html` 에 `<button disabled>장중관제 생성</button>` 과 `08:30 칸은 정상, 17:00 칸은 석식교대, 나머지 칸은 정상·석식교대 둘 다 됩니다.`, `period-ops-collecting.html` 에 `⚠ 아직 입력하지 않은 평일: 11/19, 11/20.`, `period-it-full-closed.html` 에 `<button >장중관제 생성</button>`(눌리는 버튼)과 배정 횟수 표, `period-it-full-generated.html` 에 "장중관제 배정 횟수 — 편차", `roster-mine`·`roster-month`·`day` 에 "가상일", `period-ops-slot-history.html` 에 `확정 취소` 가 있고 "배정 횟수"·"생성 방식"·"재생성"이 없는지, `roster-other.html` 에 `보기 전용` 과 "가상이"가 있는지 본다(가상 이름만 들어 있다).

- [ ] **Step 4: 통과와 안정성을 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_snapshots.py && DUTY_REPO_URL=https://example.com/x .venv/bin/pytest -W error -q tests/test_snapshots.py && .venv/bin/pytest -W error -q`
Expected: `1 passed`, `1 passed`(저장소 링크 환경 변수에 흔들리지 않는다), 전체 `1251 passed`(전체 실행에서도 기준이 같아야 한다: 회차 번호·CSRF·시각을 지웠다).

- [ ] **Step 5: 커밋**

```bash
git add tests/conftest.py tests/test_snapshots.py tests/snapshots/ tests/test_period_lifecycle.py
git commit -m "$(cat <<'EOF'
feat: 근무표 통합 전 화면 스냅샷 기준과 회차 옮기기 오류 글 단언(main 코드, 1단계 불변 확인용)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

---

### Task 2: Board 단계 칸·단계 규칙·0023(칸과 forward)

> 범위: 모델 칸과 쿼리 없는 규칙 메서드, 임시 기준 함수, 마이그레이션 0023 의 앞부분. 아직 아무 코드도 이 칸을 읽지 않는다(갈래는 Task 3·4 가 바꾼다). `input_mode` 칸은 Task 5 까지 남는다.

**Files:**
- Modify: `duty/models.py` — `Board` 칸(`input_mode` 다음)·`Meta.constraints`·`admin_group_name()` 뒤 단계 메서드, `class PeriodStatus` 뒤 `MOVABLE`
- Modify: `duty/services/periods.py` — `MOVABLE` 을 models 에서 가져오고 모듈의 `MOVABLE = …` 줄을 지운다
- Modify: `duty/services/boards.py` — `board_of` 앞에 `legacy_admin_entry`
- Create: `duty/migrations/0023_board_steps.py`
- Modify: `tests/it_defs.py` — 맨 끝 `OPS_STEPS`
- Modify(기계적 변경, 단언 그대로): `tests/conftest.py`(`ops_board`) 와 `Board.objects.create(..., input_mode=직접 입력)` 이 있는 테스트 파일 18개(Task 1 의 `test_period_lifecycle.py` 포함) — `**OPS_STEPS` 로(아래 Step 5 스크립트)
- Test: `tests/test_board_steps.py`(새 파일), `tests/test_migration_board_steps.py`(새 파일)

**Interfaces:**
- Consumes: `PeriodStatus`, `_one_of`, `Q`
- Produces:
  - `Board` 칸: `use_draft: bool = True`("작성 중 단계 사용"), `use_close: bool = True`("마감 단계 사용"), `step_draft|step_collecting|step_closed|step_generated|step_published: CharField(16)`(기본 "작성 중"·"취합 중"·"마감"·"생성됨"·"배포됨"), 제약 `board_step_names_set`(다섯 이름 모두 빈 글자 금지)
  - `Board.step_name(status: str) -> str`, `Board.steps() -> list[str]`, `Board.first_step() -> str`, `Board.generate_from() -> str`, `Board.editable() -> set[str]`, `Board.move_targets(status: str) -> list[str]`(DB 를 읽지 않는다, 표는 설계 5.2)
  - `duty.models.MOVABLE = (DRAFT, COLLECTING, CLOSED)`(`periods.MOVABLE` 도 같은 객체로 남는다)
  - `duty.services.boards.legacy_admin_entry(board) -> bool` = `not board.use_close`(1단계 임시 기준. 2단계가 화면·서비스 자리를, 3단계가 입력 그룹·부서 폼 자리와 함수를 지운다)
  - `tests.it_defs.OPS_STEPS: dict` = `input_mode="direct"`(Task 5 에서 뺀다) + `use_draft=False, use_close=False, step_collecting="입력 중", step_generated="확정"`
  - 0023: `input_mode="direct"` 근무표 → 위 OPS 값. 거꾸로는 이 작업에서 `noop`(Task 5 가 규칙을 넣는다)

- [ ] **Step 1: 실패 테스트를 쓴다**

`tests/test_board_steps.py`(새 파일):
```python
"""근무표 단계 설정과 단계 규칙(근무표 통합 설계 5.1·5.2). 쿼리 없는 Board 메서드. 이름은 모두 가상."""
import pytest
from django.db import IntegrityError, transaction

from duty.models import Board, Period
from duty.services import boards
from tests.it_defs import OPS_STEPS

S = Period.Status
D, C, X, G, P = S.DRAFT, S.COLLECTING, S.CLOSED, S.GENERATED, S.PUBLISHED

# (use_draft, use_close) → 켠 단계, 첫 단계, 생성 받는 상태, 기간 수정 상태, {상태: 옮기기 대상}
RULES = [
    ((True, True), [D, C, X, G, P], D, X, {D},
     {D: [C, X], C: [D, X], X: [D, C], G: [D, C, X], P: []}),          # IT
    ((False, False), [C, G, P], C, C, {D, C},
     {D: [C], C: [], X: [C], G: [C], P: []}),                          # 시장운영실(끈 단계에 남은 회차는 취합 중으로만)
    ((False, True), [C, X, G, P], C, X, {D, C},
     {D: [C, X], C: [X], X: [C], G: [C, X], P: []}),                   # 작성 중만 끔
    ((True, False), [D, C, G, P], D, C, {D},
     {D: [C], C: [D], X: [D, C], G: [D, C], P: []}),                   # 마감만 끔
]


@pytest.mark.parametrize("flags,steps,first,gen_from,editable,targets", RULES)
def test_step_rules(flags, steps, first, gen_from, editable, targets):
    b = Board(code="x", name="x", use_draft=flags[0], use_close=flags[1])
    assert b.steps() == steps and b.first_step() == first and b.generate_from() == gen_from
    assert b.editable() == editable
    assert {s: b.move_targets(s) for s in S.values} == targets


def test_default_names_are_status_labels():
    b = Board(code="x", name="x")
    assert [b.step_name(s) for s in S.values] == [label for _, label in S.choices]


def test_ops_names_keep_turned_off_steps():
    b = Board(code="x", name="x", **OPS_STEPS)
    assert [b.step_name(s) for s in S.values] == ["작성 중", "입력 중", "마감", "확정", "배포됨"]


def test_legacy_rule_is_close_off():
    assert boards.legacy_admin_entry(Board(use_close=False)) and not boards.legacy_admin_entry(Board())


@pytest.mark.parametrize("field", ["step_draft", "step_collecting", "step_closed", "step_generated", "step_published"])
def test_step_names_cannot_be_empty(db, field):
    with pytest.raises(IntegrityError), transaction.atomic():
        Board.objects.create(code="x", name="x", **{field: ""})
```

`tests/test_migration_board_steps.py`(새 파일):
```python
"""0023: 입력 방식(input_mode) → 단계 설정(근무표 통합 설계 10.2). 이름은 모두 가상."""
from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0022_lunch_data")]
AFTER = [("duty", "0023_board_steps")]
STEPS = ("use_draft", "use_close", "step_draft", "step_collecting", "step_closed", "step_generated", "step_published")
IT = (True, True, "작성 중", "취합 중", "마감", "생성됨", "배포됨")
OPS = (False, False, "작성 중", "입력 중", "마감", "확정", "배포됨")


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_apps():
    apps = _migrate(BEFORE)  # 마이그레이션이 만든 IT 근무표만 있어 내려갈 수 있다
    yield apps
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())  # 다른 테스트를 위해 최신 스키마로


def _ops(apps):
    group = apps.get_model("auth", "Group").objects.create(name="운영팀 근무표 관리")
    return apps.get_model("duty", "Board").objects.create(code="ops", name="운영팀", input_mode="direct", admin_group=group)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_input_mode_becomes_steps(old_apps):
    ops = _ops(old_apps)
    dept = old_apps.get_model("duty", "Department").objects.create(code="OPS", name="운영", shifts="dawn", board=ops)
    Period = old_apps.get_model("duty", "Period")
    for st in ("draft", "collecting", "closed", "generated", "published"):
        Period.objects.create(board=ops, name=st, start_date=date(2026, 11, 16), end_date=date(2026, 11, 20), status=st)
    apps = _migrate(AFTER)
    Board = apps.get_model("duty", "Board")
    assert Board.objects.filter(code="it").values_list(*STEPS).get() == IT
    assert Board.objects.filter(code="ops").values_list(*STEPS).get() == OPS
    assert sorted(apps.get_model("duty", "Period").objects.filter(board__code="ops").values_list("name", "status")) == sorted(
        (st, st) for st in ("draft", "collecting", "closed", "generated", "published"))  # 회차 상태는 그대로
    assert apps.get_model("duty", "Department").objects.get(pk=dept.pk).input_group_id is None  # 그룹을 만들지 않는다
```

`tests/it_defs.py` 맨 끝:
```python

# 작성 중·마감을 끈 근무표(시장운영실과 같은 단계: 입력 중 → 확정 → 배포됨). 테스트가 Board(**OPS_STEPS) 로 만든다
OPS_STEPS = dict(input_mode="direct", use_draft=False, use_close=False, step_collecting="입력 중", step_generated="확정")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_steps.py tests/test_migration_board_steps.py`
Expected: `13 failed` — `test_board_steps.py` 12개는 `TypeError: Board() got unexpected keyword arguments: 'use_draft', 'use_close'`(이름 칸 테스트는 `'step_draft'` 등), 마이그레이션 테스트는 `NodeNotFoundError: Node ('duty', '0023_board_steps') not a valid node`.

- [ ] **Step 3: 모델·임시 기준·마이그레이션을 쓴다**

`duty/models.py` 의 `Board` — `input_mode = …` 줄 바로 뒤에:
```python
    # 회차 단계(설계 5.1): 작성 중·마감은 끌 수 있고 다섯 단계 모두 화면 이름을 가진다(끈 단계도: 남은 회차·기록이 이름으로 보인다)
    use_draft = models.BooleanField("작성 중 단계 사용", default=True)
    use_close = models.BooleanField("마감 단계 사용", default=True)
    step_draft = models.CharField("작성 중 이름", max_length=16, default="작성 중")
    step_collecting = models.CharField("취합 중 이름", max_length=16, default="취합 중")
    step_closed = models.CharField("마감 이름", max_length=16, default="마감")
    step_generated = models.CharField("생성됨 이름", max_length=16, default="생성됨")
    step_published = models.CharField("배포됨 이름", max_length=16, default="배포됨")
```
`Board.Meta` 의
```python
        constraints = [_one_of("input_mode", InputMode.values, "board_input_mode_valid")]
```
를
```python
        constraints = [
            _one_of("input_mode", InputMode.values, "board_input_mode_valid"),
            models.CheckConstraint(name="board_step_names_set", condition=(
                ~Q(step_draft="") & ~Q(step_collecting="") & ~Q(step_closed="") & ~Q(step_generated="")
                & ~Q(step_published=""))),
        ]
```
로. `admin_group_name()` 바로 뒤(`save` 앞)에:
```python
    # 단계 규칙(설계 5.2). DB 를 읽지 않는다
    def step_name(self, status: str) -> str:
        """그 상태의 화면 이름(끈 단계도)."""
        return getattr(self, f"step_{status}")

    def steps(self) -> list[str]:
        """켠 단계, 순서대로: (작성 중) → 취합 중 → (마감) → 생성됨 → 배포됨."""
        S = PeriodStatus
        return [s for s, on in ((S.DRAFT, self.use_draft), (S.COLLECTING, True), (S.CLOSED, self.use_close),
                                (S.GENERATED, True), (S.PUBLISHED, True)) if on]

    def first_step(self) -> str:
        """새 회차의 상태."""
        return PeriodStatus.DRAFT if self.use_draft else PeriodStatus.COLLECTING

    def generate_from(self) -> str:
        """생성(확정)을 받는 상태(생성됨에서 다시 생성하는 것은 따로)."""
        return PeriodStatus.CLOSED if self.use_close else PeriodStatus.COLLECTING

    def editable(self) -> set[str]:
        """기간을 고칠 수 있는 상태: 작성 중, 그리고 작성 중을 안 쓰면 취합 중에서도."""
        return {PeriodStatus.DRAFT} | (set() if self.use_draft else {PeriodStatus.COLLECTING})

    def move_targets(self, status: str) -> list[str]:
        """'다른 상태로 옮기기'로 갈 수 있는 상태: 켠 배포 전 단계 중 지금 것 빼고. 배포됨에서는 없다(배포 취소로만)."""
        if status == PeriodStatus.PUBLISHED:
            return []
        on = self.steps()
        return [s for s in MOVABLE if s in on and s != status]
```
(`PeriodStatus`·`MOVABLE` 은 아래쪽에 정의되지만 메서드가 불릴 때 찾으므로 괜찮다.) `class PeriodStatus` 정의 바로 뒤, `DIRECT_STEPS` 주석 앞에:
```python
MOVABLE = (PeriodStatus.DRAFT, PeriodStatus.COLLECTING, PeriodStatus.CLOSED)  # 생성됨·배포됨은 생성·배포 버튼으로만 간다

```

`duty/services/periods.py`: import 를
```python
from ..models import MOVABLE, ChangeLog, Commute, Department, DutyAssignment, InputMode, Period, PeriodEvent
```
로 바꾸고, `save_draft` 와 `move` 사이의
```python
MOVABLE = (S.DRAFT, S.COLLECTING, S.CLOSED)  # 생성됨·배포됨은 생성·배포 버튼으로만 간다


```
을 지운다(`@transaction.atomic` 위에 빈 줄 둘이 남게).

`duty/services/boards.py` 의 `def board_of(user)` 바로 앞에:
```python
def legacy_admin_entry(board: Board) -> bool:
    """1단계 임시 기준(설계 6.1): 옛 직접 입력 근무표(마감을 안 쓰는 근무표)의 문구·확인창·채우기·빈 평일 경고·입력 그룹을 지금처럼 고른다.
    ponytail: 2단계에서 화면·서비스 자리를, 3단계에서 Department.save·부서 폼 자리와 이 함수를 지운다."""
    return not board.use_close


```

`duty/migrations/0023_board_steps.py`(새 파일. `makemigrations` 가 만드는 연산과 같은 값이고, 순서만 설계 10.2 대로 손으로 적는다):
```python
"""근무표 단계 설정(근무표 통합 설계 10.2, 1단계). 앱 코드를 import 하지 않고 값을 그대로 적는다.

- 단계 칸을 더한다: 작성 중·마감 단계 사용(기본 켬), 다섯 단계 화면 이름(기본 = 지금 IT 이름) + 이름 빈 글자 금지 제약.
- 직접 입력(input_mode=direct) 근무표: 작성 중·마감을 끄고 취합 중 = '입력 중', 생성됨 = '확정'(지금 화면 이름 그대로).
  부서별 취합(collect) 근무표는 기본값 그대로. 입력 그룹은 만들지 않는다(그룹 없음 = 관리자만 입력, 지금과 같다).
"""
from django.db import migrations, models


def forward(apps, schema_editor):
    apps.get_model("duty", "Board").objects.filter(input_mode="direct").update(
        use_draft=False, use_close=False, step_collecting="입력 중", step_generated="확정")


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('duty', '0022_lunch_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='board',
            name='use_draft',
            field=models.BooleanField(default=True, verbose_name='작성 중 단계 사용'),
        ),
        migrations.AddField(
            model_name='board',
            name='use_close',
            field=models.BooleanField(default=True, verbose_name='마감 단계 사용'),
        ),
        migrations.AddField(
            model_name='board',
            name='step_draft',
            field=models.CharField(default='작성 중', max_length=16, verbose_name='작성 중 이름'),
        ),
        migrations.AddField(
            model_name='board',
            name='step_collecting',
            field=models.CharField(default='취합 중', max_length=16, verbose_name='취합 중 이름'),
        ),
        migrations.AddField(
            model_name='board',
            name='step_closed',
            field=models.CharField(default='마감', max_length=16, verbose_name='마감 이름'),
        ),
        migrations.AddField(
            model_name='board',
            name='step_generated',
            field=models.CharField(default='생성됨', max_length=16, verbose_name='생성됨 이름'),
        ),
        migrations.AddField(
            model_name='board',
            name='step_published',
            field=models.CharField(default='배포됨', max_length=16, verbose_name='배포됨 이름'),
        ),
        migrations.AddConstraint(
            model_name='board',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('step_draft', ''), _negated=True), models.Q(('step_collecting', ''), _negated=True), models.Q(('step_closed', ''), _negated=True), models.Q(('step_generated', ''), _negated=True), models.Q(('step_published', ''), _negated=True)), name='board_step_names_set'),
        ),
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_steps.py tests/test_migration_board_steps.py && DUTY_DEBUG=1 DUTY_ENV_FILE= DUTY_DATA_DIR=$(mktemp -d) .venv/bin/python manage.py makemigrations duty --check --dry-run`
Expected: `13 passed`, "No changes detected in app 'duty'"

- [ ] **Step 5: 테스트의 직접 입력 근무표를 `OPS_STEPS` 로 바꾼다(기계적 변경)**

Task 3 부터 서비스가 `input_mode` 대신 단계 칸을 읽으므로, 테스트가 만드는 직접 입력 근무표에 단계 값을 같이 넣는다. 아래 스크립트는 `objects.create(` 가 있는 줄의 `input_mode=Board.InputMode.DIRECT`·`input_mode="direct"` 만 `**OPS_STEPS` 로 바꾸고 import 를 더한다(마이그레이션 테스트·`it_defs.py`·관리 화면 POST 는 건드리지 않는다).

```bash
.venv/bin/python - $(git grep -l -E 'input_mode=(Board\.InputMode\.DIRECT|"direct")' -- tests ':!tests/test_migration_*' ':!tests/it_defs.py') <<'EOF'
"""테스트의 Board.objects.create(..., input_mode=직접 입력) → **OPS_STEPS (근무표 통합 1단계 기계적 변경)."""
import re
import sys
from pathlib import Path

for f in sys.argv[1:]:
    p = Path(f)
    s = p.read_text(encoding="utf-8")
    new = "\n".join(re.sub(r'input_mode=(Board\.InputMode\.DIRECT|"direct")', "**OPS_STEPS", line)
                    if "objects.create(" in line else line for line in s.split("\n"))
    if new == s:
        continue
    if "from tests.it_defs import " in new:
        new = re.sub(r"from tests\.it_defs import ([^\n]+)", r"from tests.it_defs import \1, OPS_STEPS", new, count=1)
    else:
        lines = new.split("\n")
        last = max(i for i, line in enumerate(lines) if line.startswith(("import ", "from ")))
        lines.insert(last + 1, "from tests.it_defs import OPS_STEPS")
        new = "\n".join(lines)
    p.write_text(new, encoding="utf-8")
EOF
git diff --stat tests/
git grep -n -E 'input_mode=' -- tests ':!tests/test_migration_*'
```
Expected: 19개 파일(conftest·`test_period_lifecycle.py` 포함, 24줄)이 바뀐다(관리 화면 POST 의 `input_mode="direct"` 7곳은 `objects.create(` 줄이 아니라 그대로 — 정규식을 넓히지 않는다). 마지막 grep 에는 `tests/it_defs.py` 의 `OPS_STEPS`, `tests/test_admin_boards.py` 의 `su_client.post(ADD, form(..., input_mode="direct"))` 7줄, `tests/test_boards_models.py:59` 의 `input_mode="bogus"` 만 남는다(Task 5 에서 고친다). `git diff tests/` 를 훑어 바뀐 줄이 근무표를 만드는 줄과 import 뿐인지 본다.

- [ ] **Step 6: 전체 테스트**

Run: `.venv/bin/pytest -W error -q`
Expected: `1264 passed`(스냅샷 `test_snapshots.py` 포함, `tests/snapshots/` 는 그대로)

- [ ] **Step 7: 커밋**

```bash
git add duty/models.py duty/services/periods.py duty/services/boards.py duty/migrations/0023_board_steps.py tests/
git commit -m "$(cat <<'EOF'
feat: 근무표 단계 칸(작성 중·마감 사용, 단계 이름)과 쿼리 없는 단계 규칙, 마이그레이션 0023(직접 입력 근무표 → 입력 중·확정)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

---

### Task 3: 서비스가 단계 규칙을 따른다

> 범위: 서비스와 `Period.status_label`, `add_board` 가 만드는 근무표 값. 문구는 1단계 규칙대로 지금 글자를 `legacy_admin_entry` 로 고른다. 화면은 Task 4.

**Files:**
- Modify: `duty/services/periods.py` — import, `save_draft`(기간 수정 상태·새 회차 상태), `move`(검사 순서·`move_targets`), `empty_days` docstring
- Modify: `duty/services/generate.py` — import, `run_generation` 의 상태 검사·빈 평일 처리·`slot_dates`
- Modify: `duty/services/collect.py` — import, `_require_input` 문구, `fill_week` 검사
- Modify: `duty/services/publish.py` — import, `_validate` 문구
- Modify: `duty/models.py` — `Period.status_label`
- Modify: `duty/services/board_setup.py` — `create_direct_board` 가 만드는 `Board(...)` 에 단계 값
- Test: `tests/test_board_steps.py`(서비스 절 더하기)

**Interfaces:**
- Consumes: Task 2 의 `Board.step_name/steps/first_step/generate_from/editable`, `boards.legacy_admin_entry`
- Produces(동작):
  - `periods.save_draft`: 기간 수정 = `row.status in board.editable()`, 새 회차 상태 = `board.first_step()`. 오류 글은 지금 둘 그대로(`legacy` 면 "기간은 입력 중에만 수정할 수 있습니다.", 아니면 "기간은 작성 중(draft) 상태에서만 수정할 수 있습니다.")
  - `periods.move`: 검사 순서 **배포됨 → 같은 상태 → `move_targets`**(설계 6.1). 글은 지금 그대로: "배포된 회차는 배포 취소로만 되돌릴 수 있습니다.", "이미 그 상태입니다.", `move_targets` 밖이면 대상이 `MOVABLE` 밖일 때 "옮길 수 없는 상태입니다.", 그 밖 "직접 입력 근무표는 입력 중으로만 옮길 수 있습니다."(순서가 바뀌어 화면에서 만들 수 없는 "배포된 회차 + 잘못된 대상"만 글이 달라진다)
  - `generate.run_generation`: 상태 = `{board.generate_from(), GENERATED}`(오류 글: `legacy` 면 "입력 중인 회차만 확정할 수 있습니다.", 아니면 "마감된 회차만 생성할 수 있습니다."). 빈 평일: `legacy` 면 경고(지금 글), 아니면 막음(지금 글). 관제 생성일 = 그 회차 출근 행이 하나라도 있는 날
  - `collect._require_input`: "{board.step_name(COLLECTING)}인 회차가 아닙니다."; `collect.fill_week`: `legacy` 가 아니면 지금 오류("채우기는 직접 입력 근무표에서만 씁니다.")
  - `publish._validate`: `legacy` 면 "확정한 회차만 배포할 수 있습니다.", 아니면 "생성이 끝난 회차만 배포할 수 있습니다."
  - `Period.status_label` = `self.board.step_name(self.status)`
  - `board_setup.create_direct_board` 가 만드는 근무표: `use_draft=False, use_close=False, step_collecting="입력 중", step_generated="확정"`(Task 5 까지는 `input_mode=DIRECT` 도 함께)

- [ ] **Step 1: 실패 테스트를 쓴다**

`tests/test_board_steps.py` 의 import 를 아래로 바꾼다(맨 위 docstring 도):
```python
"""근무표 단계 설정과 단계 규칙(근무표 통합 설계 5.1·5.2): 쿼리 없는 Board 메서드와, 서비스가 입력 방식 대신 그 규칙을 따르는지. 이름은 모두 가상."""
from datetime import date, time

import pytest
from django.db import IntegrityError, transaction

from duty.errors import DutyError
from duty.models import Board, BoardShift, Commute, Department, DutyAssignment, Period, User
from duty.services import boards, collect, periods, publish
from duty.services.generate import run_generation
from tests.it_defs import OPS_STEPS
```
파일 맨 끝에:
```python


# ── 서비스가 단계 설정을 따른다(입력 방식이 아니라) ──

MON, FRI = date(2026, 11, 16), date(2026, 11, 20)


def board_with(use_draft, use_close, slot=True, **names):
    """입력 방식은 기본값(부서별 취합) 그대로 두고 단계만 고른 근무표. 근무조 하나 + 관제 하나(직원, slot=False 면 없음), 부서 둘."""
    b = Board.objects.create(code="stp", name="단계팀", use_draft=use_draft, use_close=use_close, **names)
    BoardShift.objects.create(board=b, key="dawn", name="이른", start=time(7), end=time(16))
    if slot:
        BoardShift.objects.create(board=b, key="slot0", name="점검", start=time(10), end=time(11),
                                  eligible_shifts=["dawn"], eligible_types=["직원"])
    for code in ("STA", "STB"):
        Department.objects.create(code=code, name=f"단계{code}", shifts="dawn", board=b)
    return b


def person(code):
    return User.objects.create_user(f"{code}{User.objects.count():03d}", password=None, name=f"가상{code}{User.objects.count()}",
                                    department=Department.objects.get(code=code), type="직원")


@pytest.mark.parametrize("flags,first", [((True, True), D), ((False, False), C), ((False, True), C), ((True, False), D)])
def test_new_period_starts_at_first_step(it_board, flags, first):
    p = periods.save_draft(Period(board=board_with(*flags), name="p", start_date=MON, end_date=FRI))
    assert p.status == first


def test_dates_editable_while_collecting_without_draft(it_board):
    p = Period.objects.create(board=board_with(False, True), name="p", start_date=MON, end_date=FRI, status=C)
    p.end_date = date(2026, 11, 18)
    periods.save_draft(p)
    assert Period.objects.get(pk=p.pk).end_date == date(2026, 11, 18)


@pytest.mark.parametrize("flags,ok,refused,msg", [
    ((False, True), X, C, "마감된 회차만 생성할 수 있습니다"),
    ((True, False), C, X, "입력 중인 회차만 확정할 수 있습니다"),  # 1단계: 마감을 안 쓰면 옛 직접 입력 문구
])
def test_generate_from_rule(it_board, flags, ok, refused, msg):
    b = board_with(*flags)
    bad = Period.objects.create(board=b, name="bad", start_date=MON, end_date=FRI, status=refused)
    with pytest.raises(DutyError, match=msg):
        run_generation(bad)
    good = Period.objects.create(board=b, name="good", start_date=date(2026, 11, 23), end_date=date(2026, 11, 23),
                                 status=ok)
    for code in ("STA", "STB"):
        Commute.objects.create(period=good, date=good.start_date, member=person(code), shift="dawn")
    run_generation(good, seed=1)
    assert Period.objects.get(pk=good.pk).status == G


@pytest.mark.parametrize("flags,status,to,msg", [  # 검사 순서: 배포됨 → 같은 상태 → move_targets(설계 6.1)
    ((False, True), G, D, "직접 입력 근무표는 입력 중으로만 옮길 수 있습니다."),  # 끈 단계로(1단계 글)
    ((True, True), D, G, "옮길 수 없는 상태입니다."),                            # MOVABLE 밖
    ((True, True), P, G, "배포된 회차는 배포 취소로만 되돌릴 수 있습니다."),     # 배포됨이 먼저(main 은 '옮길 수 없는')
])
def test_move_checks_in_order(it_board, flags, status, to, msg):
    p = Period.objects.create(board=board_with(*flags), name="p", start_date=MON, end_date=FRI, status=status)
    with pytest.raises(DutyError) as e:
        periods.move(p, to)
    assert str(e.value) == msg


def test_slots_skip_only_days_without_any_rows(it_board):
    """1단계: 관제는 출근 행이 하나도 없는 날만 뺀다. 한 부서만 빈 날(목·금)은 다른 부서 사람으로 채운다(경고는 그대로)."""
    b = board_with(False, False)
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    a, z = person("STA"), person("STB")
    for x in p.dates():
        Commute.objects.create(period=p, date=x, member=a, shift="dawn")
    for x in p.dates()[:3]:
        Commute.objects.create(period=p, date=x, member=z, shift="dawn")
    out = run_generation(p, seed=1)
    assert out.warnings[0] == "입력하지 않은 평일이 있습니다(그날은 근무자가 없습니다): 11/19, 11/20"
    assert sorted(DutyAssignment.objects.filter(period=p).values_list("date", flat=True)) == p.dates()


def test_names_come_from_board(it_board, admin_user):
    b = board_with(True, True, step_collecting="모으는 중")
    b.admin_group.user_set.add(admin_user)
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    assert p.status_label == "모으는 중"
    p.status = G
    p.save()
    with pytest.raises(DutyError, match="모으는 중인 회차가 아닙니다"):
        collect.apply_table(admin_user, p, Department.objects.get(code="STA"), {})


@pytest.mark.parametrize("flags,allowed", [((False, False), True), ((True, False), True), ((True, True), False)])
def test_fill_follows_legacy_rule(it_board, flags, allowed):
    """1단계: 채우기는 마감을 안 쓰는 근무표에서만(2단계에서 모든 근무표)."""
    b = board_with(*flags)
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    dept = Department.objects.get(code="STA")
    if allowed:
        assert collect.fill_week(p, dept, {}, MON, collect.FILL_1W) == {}
    else:
        with pytest.raises(DutyError, match="채우기는 직접 입력 근무표에서만 씁니다"):
            collect.fill_week(p, dept, {}, MON, collect.FILL_1W)


@pytest.mark.parametrize("flags,msg", [((False, False), "확정한 회차만"), ((True, True), "생성이 끝난 회차만")])
def test_publish_message_follows_legacy_rule(it_board, flags, msg):
    p = Period.objects.create(board=board_with(*flags), name="p", start_date=MON, end_date=FRI, status=C)
    with pytest.raises(DutyError, match=msg):
        publish.publish(p, MON)
```
(`board_with` 는 `input_mode` 를 기본값(collect)으로 둔다. 그래서 이 테스트들은 서비스가 `input_mode` 가 아니라 단계 칸을 읽을 때만 통과한다.)

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_steps.py`
Expected: `11 failed, 18 passed` — 첫 단계(`[flags1-collecting]`·`[flags2-collecting]`), 취합 중 기간 수정, 생성(`[flags1-…]`), 옮기기 둘(끈 단계로 옮기기가 그냥 옮겨짐, 배포됨+`G` 가 main 순서로 "옮길 수 없는 상태입니다."), 관제 빈 날, 이름(`status_label` 이 "취합 중"), 채우기 둘(`[flags0-True]`·`[flags1-True]`), 배포 문구(`[flags0-확정한 회차만]`).

- [ ] **Step 3: 서비스를 고친다**

`duty/services/periods.py` — import 에서 `InputMode` 를 뺀다:
```python
from ..models import MOVABLE, ChangeLog, Commute, Department, DutyAssignment, Period, PeriodEvent
```
`save_draft` 맨 앞의
```python
    direct = period.board.input_mode == InputMode.DIRECT
    editable = {S.DRAFT, S.COLLECTING} if direct else {S.DRAFT}  # 직접 입력은 입력 중(= 취합 중)에도 기간을 고친다(설계 6.1)
    row = Period.objects.select_for_update().get(pk=period.pk) if period.pk else None  # 상태는 DB 에서(낡은 객체 대비)
    if row and row.status not in editable:
        raise DutyError("기간은 입력 중에만 수정할 수 있습니다." if direct
                        else "기간은 작성 중(draft) 상태에서만 수정할 수 있습니다.")
```
를
```python
    board = period.board
    row = Period.objects.select_for_update().get(pk=period.pk) if period.pk else None  # 상태는 DB 에서(낡은 객체 대비)
    if row and row.status not in board.editable():  # 작성 중, 작성 중을 안 쓰면 취합 중에서도(설계 5.2)
        raise DutyError("기간은 입력 중에만 수정할 수 있습니다." if boards.legacy_admin_entry(board)
                        else "기간은 작성 중(draft) 상태에서만 수정할 수 있습니다.")
```
로, 같은 함수의
```python
    if new and direct:
        period.status = S.COLLECTING  # 직접 입력: 만들자마자 입력 중
    if new:
        period.save()
```
를
```python
    if new:
        period.status = board.first_step()  # 작성 중을 안 쓰면 만들자마자 취합 중(입력 중)
        period.save()
```
로. `move` 의 `period.refresh_from_db()` 다음 네 검사(`if to not in MOVABLE:` 부터 `raise DutyError("이미 그 상태입니다.")` 까지)를
```python
    if period.status == S.PUBLISHED:
        raise DutyError("배포된 회차는 배포 취소로만 되돌릴 수 있습니다.")
    if period.status == to:
        raise DutyError("이미 그 상태입니다.")
    if to not in period.board.move_targets(period.status):  # 켠 배포 전 단계로만(설계 5.2)
        raise DutyError("옮길 수 없는 상태입니다." if to not in MOVABLE
                        else "직접 입력 근무표는 입력 중으로만 옮길 수 있습니다.")
```
로. `empty_days` docstring 의 "직접 입력 회차의 확정 경고." 를 "빈 평일 경고." 로.

`duty/services/generate.py` — import 에서 `InputMode` 를 뺀다:
```python
from ..models import Commute, DutyAssignment, Period, User
```
`run_generation` 의
```python
    direct = period.board.input_mode == InputMode.DIRECT  # 직접 입력의 [확정](설계 6.1·6.3)
    if direct and period.status not in {S.COLLECTING, S.GENERATED}:
        raise DutyError("입력 중인 회차만 확정할 수 있습니다.")
    if not direct and period.status not in {S.CLOSED, S.GENERATED}:
        raise DutyError("마감된 회차만 생성할 수 있습니다.")
    holidays.sync(perms.today())  # 작업자가 꺼져 있어도 휴장일 표가 비어 있지 않게
    warnings = []
    empty = []
    if direct:  # 직접 입력은 빈 평일을 막지 않고 경고로만 알린다
        empty = empty_days(period)
```
를
```python
    legacy = boards.legacy_admin_entry(period.board)  # 1단계 임시 기준(문구·빈 평일), 2단계에서 지운다
    if period.status not in {period.board.generate_from(), S.GENERATED}:  # 마감을 쓰면 마감에서, 아니면 취합 중에서
        raise DutyError("입력 중인 회차만 확정할 수 있습니다." if legacy else "마감된 회차만 생성할 수 있습니다.")
    holidays.sync(perms.today())  # 작업자가 꺼져 있어도 휴장일 표가 비어 있지 않게
    warnings = []
    if legacy:  # 빈 평일을 막지 않고 경고로만 알린다
        empty = empty_days(period)
```
로(그 아래 `if empty: warnings.append(…)` 와 `else:` 갈래는 그대로). 그리고
```python
    slot_dates = [d for d in dates if d not in empty]  # 직접 입력의 빈 평일은 후보가 없으니 관제를 만들지 않는다
```
를
```python
    worked = set(Commute.objects.filter(period=period).values_list("date", flat=True))
    slot_dates = [d for d in dates if d in worked]  # 출근 행이 하나도 없는 날은 후보가 없으니 관제를 만들지 않는다
```
로.

`duty/services/collect.py` — import 를
```python
from ..models import Commute, Department, Period, User
```
로(`Board`·`step_label` 을 뺀다). `_require_input` 의 상태 오류를
```python
        raise DutyError(f"{period.board.step_name(Period.Status.COLLECTING)}인 회차가 아닙니다.")  # 취합 중 / 입력 중
```
로. `fill_week` 의 `if period.board.input_mode != Board.InputMode.DIRECT:` 를
```python
    if not boards.legacy_admin_entry(period.board):  # 1단계 임시 기준, 2단계에서 모든 근무표
```
로(다음 줄 `raise DutyError("채우기는 직접 입력 근무표에서만 씁니다.")` 는 그대로).

`duty/services/publish.py` — import 를
```python
from ..models import ChangeLog, Commute, DutyAssignment, Period, PeriodEvent, User
```
로, `_validate` 의 `if period.board.input_mode == InputMode.DIRECT` 를 `if boards.legacy_admin_entry(period.board)` 로(두 문구는 그대로).

`duty/models.py` 의 `Period.status_label` 본문을
```python
        return self.board.step_name(self.status)
```
로.

`duty/services/board_setup.py` 의 `board = Board(code=code, name=name, input_mode=InputMode.DIRECT)` 를
```python
    board = Board(code=code, name=name, input_mode=InputMode.DIRECT,  # 단계: 입력 중 → 확정 → 배포됨(설계 10.2 와 같은 값)
                  use_draft=False, use_close=False, step_collecting="입력 중", step_generated="확정")
```
로(없으면 `add_board` 로 만든 근무표의 새 회차가 작성 중으로 생긴다 — `tests/test_add_board.py::test_works_with_existing_flows` 가 잡는다).

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_steps.py tests/test_direct_periods.py tests/test_views_direct.py tests/test_fill.py tests/test_add_board.py tests/test_period_lifecycle.py tests/test_publish.py tests/test_generate.py tests/test_snapshots.py`
Expected: 모두 통과(기존 문구 단언·Task 1 의 `move` 네 문구·스냅샷 그대로)

- [ ] **Step 5: 전체 테스트**

Run: `.venv/bin/pytest -W error -q && DUTY_DEBUG=1 DUTY_ENV_FILE= DUTY_DATA_DIR=$(mktemp -d) .venv/bin/python manage.py makemigrations duty --check --dry-run`
Expected: `1281 passed`, "No changes detected in app 'duty'"

- [ ] **Step 6: 커밋**

```bash
git add duty/services/periods.py duty/services/generate.py duty/services/collect.py duty/services/publish.py duty/services/board_setup.py duty/models.py tests/test_board_steps.py
git commit -m "$(cat <<'EOF'
feat: 회차 서비스가 입력 방식 대신 단계 규칙을 따른다(새 회차·기간·생성·옮기기 검사 순서·입력·배포, 문구는 그대로)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

---

### Task 4: 화면이 단계 규칙을 따른다(회차 화면 한 묶음·버튼 이름·조사·이스케이프)

> 범위: 회차 화면·입력 표·[출근표 입력] 목록·도움말 기준. IT·운영팀 화면은 글자 하나 바뀌지 않는다(스냅샷 `tests/test_snapshots.py` 가 그대로 통과 — 관제 이력이 남은 운영팀 회차 `period-ops-slot-history` 포함). 1단계에서 버튼 글자·[재생성]·[생성 방식]·배정 횟수 표는 **임시 기준**(`legacy_admin_entry`)으로 고른다: 마감을 쓰는 근무표 = main 의 부서별 취합 화면, 마감을 안 쓰는 근무표 = main 의 직접 입력 화면(관제 정의·배정이 있어도). 관제 정의라는 데이터 기준과 정의에서 만든 생성 방식 문장은 2단계(Task 8). 관리 화면은 Task 5.

**Files:**
- Modify: `duty/models.py` — `Board.editable()` 뒤에 `step_buttons`
- Modify: `duty/shifts.py` — `lunch_defs` 앞에 `josa`
- Modify: `duty/views/manage.py` — import, `_movable` 지우기, `_render_detail`, `period_action` 성공 문구 기준
- Modify: `duty/templates/duty/period_detail.html` — 기간 폼 조건, 버튼 묶음(확인창은 `escapejs`), 경고 두 줄, 옮기기 상자 조건, 배포 취소 글, 입력 현황·배정 횟수·생성 방식 조건(생성 방식 글은 main 그대로)
- Modify: `duty/views/collect.py` — import, `index` 의 `waiting`, `_render_table` 의 `direct` → `legacy`
- Modify: `duty/templates/duty/collect_table.html` — `direct` → `legacy`(세 곳)
- Modify: `duty/help.py` — import, `allowed("direct")` 기준
- Test: `tests/test_board_steps.py`(화면 절 더하기)

**Interfaces:**
- Consumes: Task 2 의 단계 메서드, `boards.legacy_admin_entry`, `boards.active_defs`, `shifts.slot_defs`
- Produces:
  - `Board.step_buttons(has_slots: bool) -> dict[str, str]`: 키 `open`("<취합 중 이름에서 ' 중' 뗀 말> 열기"), `close`("<같은 말> <마감 이름>"), `generate`(`has_slots` 면 "장중관제 생성", 아니면 생성됨 이름 끝의 '됨'을 뗀 말 — '됨'으로 끝나지 않으면 이름 그대로), `regenerate`(`has_slots` 면 "재생성", 아니면 ""), `undo`(생성됨에서 옮길 곳이 하나면 "<generate> 취소", 아니면 ""). 취합 중 이름이 " 중"으로 끝나지 않으면 `open`·`close` 는 "'<취합 중 이름>'(으)로"·"'<마감 이름>'(으)로"
  - `shifts.josa(word: str, pair: str) -> str`: `pair` = "은/는"·"을/를"·"으로/로", 받침으로 고른다(ㄹ 받침 + 으로/로 → "로", 한글로 끝나지 않으면 "은(는)"·"(으)로")
  - `period_detail.html` 컨텍스트: `board`, `legacy`, `steps=[(상태, 이름)…켠 단계]`, `editable`, `buttons`(1단계는 `board.step_buttons(not legacy)`), `movable`, `undo_to`, `generate_topic`(예 "확정은")·`undo_confirm`(예 "확정을 취소하고 입력 중으로 돌아갈까요? 출근표는 그대로 남습니다.")·`generated_ro`(생성됨 이름 뒤 "으로/로"), 그 밖 기존 키(`input_depts`·`empty_days` 는 `legacy` 일 때만)
  - 템플릿 규칙: 인라인 JS `confirm('…')` 안에 넣는 이름에서 나온 글은 모두 `|escapejs`(따옴표·역슬래시가 든 이름도 스크립트를 깨지 않게, 기본 이름이면 출력이 같다)
  - `collect_table.html` 컨텍스트: `direct` 대신 `legacy`
  - `help.allowed(user, "direct")` = 관리하는 근무표 중 `legacy_admin_entry` 인 것이 있다

- [ ] **Step 1: 실패 테스트를 쓴다**

`tests/test_board_steps.py` 의 import 를 아래로 바꾼다(`from django.utils import timezone`·`PeriodEvent`·`josa` 를 더한다):
```python
from datetime import date, time

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from duty.errors import DutyError
from duty.models import Board, BoardShift, Commute, Department, DutyAssignment, Period, PeriodEvent, User
from duty.services import boards, collect, periods, publish
from duty.services.generate import run_generation
from duty.shifts import josa
from tests.it_defs import OPS_STEPS
```
파일 맨 끝에:
```python


# ── 화면: 버튼 글자·생성 방식 문장·갈래가 단계 설정에서 나온다 ──

def test_buttons_from_step_names():
    assert Board(code="x", name="x").step_buttons(True) == {
        "open": "취합 열기", "close": "취합 마감", "generate": "장중관제 생성", "regenerate": "재생성", "undo": ""}
    assert Board(code="x", name="x", **OPS_STEPS).step_buttons(False) == {
        "open": "입력 열기", "close": "입력 마감", "generate": "확정", "regenerate": "", "undo": "확정 취소"}
    assert Board(code="x", name="x", step_collecting="접수 중", step_closed="종료").step_buttons(False)["close"] == "접수 종료"


def test_buttons_use_whole_name_when_it_cannot_be_cut():
    """취합 중 이름이 ' 중'으로 끝나지 않으면 열기·마감은 이름 전체 꼴, 생성은 끝의 '됨'만 뗀다(설계 5.4)."""
    b = Board(code="x", name="x", step_collecting="작성", step_generated="완료됨")
    assert {k: b.step_buttons(False)[k] for k in ("open", "close", "generate")} == {
        "open": "'작성'(으)로", "close": "'마감'(으)로", "generate": "완료"}


def test_josa():
    assert [josa("확정", "은/는"), josa("배포", "은/는"), josa("개발자", "을/를"), josa("직원", "을/를")] == ["은", "는", "를", "을"]
    assert [josa("입력 중", "으로/로"), josa("배포", "으로/로"), josa("마감 날", "으로/로"), josa("A", "으로/로")] == [
        "으로", "로", "로", "(으)로"]


@pytest.fixture
def stp(it_board, admin_user, client):
    """입력 방식은 부서별 취합 그대로, 작성 중·마감을 끄고 이름만 입력 중·확정으로 바꾼 근무표(관제 없음: 시장운영실 모양)."""
    b = board_with(False, False, slot=False, step_collecting="입력 중", step_generated="확정")
    b.admin_group.user_set.add(admin_user)
    client.force_login(admin_user)
    return b, client


def test_period_page_follows_steps(stp):
    b, client = stp
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    Commute.objects.create(period=p, date=MON, member=person("STA"), shift="dawn")
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert body.index(">입력 중<") < body.index(">확정<") < body.index(">배포됨<") and ">마감<" not in body
    assert f'href="/collect/{p.pk}/STA/">표 입력 · 단계STA</a>' in body and ">확정</button>" in body
    assert "확정할까요? 확정하면 배포할 수 있고, 표를 고치려면 [확정 취소]를 누릅니다." in body
    assert "⚠ 아직 입력하지 않은 평일: 11/16, 11/17, 11/18, 11/19, 11/20. 확정은 할 수 있지만" in body  # 단계STB 가 다 비었다
    assert "부서별 입력 현황" not in body and 'name="start_date"' in body and "생성 방식" not in body
    p.status = G
    p.save()
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert ">확정 취소</button>" in body and "다른 상태로 옮기기" not in body and "재생성" not in body
    assert "확정을 취소하고 입력 중으로 돌아갈까요? 출근표는 그대로 남습니다." in body


def test_period_page_with_draft_off_and_close_on(it_board, admin_user, client):
    b = board_with(False, True)
    b.admin_group.user_set.add(admin_user)
    client.force_login(admin_user)
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=D)  # 끈 단계에 남은 회차
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert "취합 열기" not in body and '<option value="collecting">' in body and '<option value="closed">' in body
    assert '<option value="draft">' not in body
    p.status = C
    p.save()
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert ">취합 마감</button>" in body and 'name="start_date"' in body and "부서별 입력 현황" in body
    p.status = X
    p.save()
    assert ">장중관제 생성</button>" in client.get(f"/periods/{p.pk}/").content.decode()


def test_renamed_steps_rename_buttons(it_board, admin_user, client):
    b = board_with(True, True, step_collecting="접수 중", step_closed="종료")
    b.admin_group.user_set.add(admin_user)
    client.force_login(admin_user)
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=D)
    assert ">접수 열기</button>" in client.get(f"/periods/{p.pk}/").content.decode()
    p.status = C
    p.save()
    assert ">접수 종료</button>" in client.get(f"/periods/{p.pk}/").content.decode()


def test_input_table_and_help_follow_legacy_rule(stp):
    b, client = stp
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    body = client.get(f"/collect/{p.pk}/STA/").content.decode()
    assert "지난주와 같게" in body and "CSV 올리기 (표 전체 교체)" in body and f'href="/periods/{p.pk}/"' in body
    assert "직접 입력 근무표 운영" in client.get("/help/").content.decode()


def test_legacy_board_with_slot_defs_looks_like_main(stp):
    """1단계: 마감을 안 쓰는 근무표는 관제 정의가 켜져 있어도 main 처럼 [확정]·[확정 취소], 생성 방식·재생성·배정 횟수 표 없음
    (임시 기준으로 고른다. 2단계에서 관제 정의라는 데이터 기준으로 바꾼다)."""
    b, client = stp
    BoardShift.objects.create(board=b, key="slot0", name="점검", start=time(10), end=time(11),
                              eligible_shifts=["dawn"], eligible_types=["직원"])
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert ">확정</button>" in body and "생성 방식" not in body
    p.status = G
    p.save()
    a = person("STA")
    Commute.objects.create(period=p, date=MON, member=a, shift="dawn")
    DutyAssignment.objects.create(period=p, date=MON, cell="slot0", member=a)
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert ">확정 취소</button>" in body and "재생성" not in body and "장중관제 배정 횟수" not in body


def test_step_names_are_escaped_in_confirm(stp):
    """확인창(인라인 JS) 안의 단계 이름 글은 escapejs 로 넣는다: 따옴표·역슬래시가 든 이름도 스크립트를 깨지 않는다."""
    b, client = stp
    Board.objects.filter(pk=b.pk).update(step_generated="확'정\\됨")
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert ("confirm('확\\u0027정\\u005C할까요? 확\\u0027정\\u005C하면 배포할 수 있고, "
            "표를 고치려면 [확\\u0027정\\u005C 취소]를 누릅니다.')") in body
    p.status = G
    p.save()
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert "confirm('확\\u0027정\\u005C을(를) 취소하고 입력 중으로 돌아갈까요? 출근표는 그대로 남습니다.')" in body
    p.status, p.publish_undo, p.published_at = P, [], timezone.now()
    p.save()
    PeriodEvent.objects.create(period=p, from_status=G, to_status=P)
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert "confirm('배포를 취소하고 이 회차를 확\\u0027정\\u005C됨으로 되돌릴까요?')" in body
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_steps.py`
Expected: FAIL — 모음 오류 `ImportError: cannot import name 'josa' from 'duty.shifts'`

- [ ] **Step 3: 버튼 이름·조사를 쓴다**

`duty/models.py` 의 `Board.editable()` 바로 뒤(`move_targets` 앞)에:
```python
    def step_buttons(self, has_slots: bool) -> dict[str, str]:
        """회차 화면 버튼 글자(설계 5.4): 단계 이름에서 나온다. has_slots = 켜진 장중관제 정의가 있다.
        취합 중 이름이 ' 중'으로 끝나지 않으면 열기·마감은 "'<이름>'(으)로" 꼴. 생성은 생성됨 이름 끝의 '됨'을 뗀 말(없으면 이름 그대로).
        undo = 생성됨에서 옮길 곳이 하나뿐일 때의 [… 취소](둘 이상이면 '다른 상태로 옮기기' 상자라 빈 글자)."""
        c = self.step_collecting
        stem = c.removesuffix(" 중") if c.endswith(" 중") else ""
        generate = "장중관제 생성" if has_slots else self.step_generated.removesuffix("됨")
        return {"open": f"{stem} 열기" if stem else f"'{c}'(으)로",
                "close": f"{stem} {self.step_closed}" if stem else f"'{self.step_closed}'(으)로",
                "generate": generate, "regenerate": "재생성" if has_slots else "",
                "undo": f"{generate} 취소" if len(self.move_targets(PeriodStatus.GENERATED)) == 1 else ""}


```

`duty/shifts.py` 의 `lunch_defs` 바로 앞에:
```python
def josa(word: str, pair: str) -> str:
    """word 뒤 조사(pair = "은/는"·"을/를"·"으로/로")를 받침으로 고른다(바꿀 수 있는 이름 뒤 글, 설계 5.4).
    한글로 끝나지 않으면 '은(는)'·'(으)로' 꼴."""
    a, b = pair.split("/")
    c = word[-1:]
    if not "가" <= c <= "힣":
        return f"({a[0]}){b}" if a == "으로" else f"{a}({b})"
    jong = (ord(c) - ord("가")) % 28
    if a == "으로":
        return b if jong in (0, 8) else a  # 받침 없음·ㄹ 받침은 '로'
    return a if jong else b


```

- [ ] **Step 4: 회차 화면 뷰를 고친다**

`duty/views/manage.py` — import 두 줄:
```python
from ..models import Board, ChangeLog, Department, Period, User
```
```python
from ..shifts import cell_label, josa, slot_defs
```
`def _movable(period, direct):` 함수 전체(빈 줄 둘 포함)를 지운다. `_render_detail` 의 `slot_names = …` 줄부터 `"empty_days": …` 줄까지를 아래로 바꾼다(뒤의 `undo`·`progress`·`missing`·`counts`·`failures` 줄은 그대로):
```python
    board = period.board
    active = boards.active_defs(board)
    slot_names = [x.name for x in slot_defs(active)]  # generator 의 칸 번호 = 켜진 관제 정의 순서
    legacy = boards.legacy_admin_entry(board)  # 1단계 임시 기준: 옛 직접 입력의 [표 입력]·빈 평일 경고·확인창(2단계에서 지운다)
    S = Period.Status
    targets = board.move_targets(period.status)
    # 1단계: 버튼 글자·[재생성]은 main 처럼 임시 기준으로(옛 직접 입력 = [확정], 그 밖 = [장중관제 생성]·[재생성]).
    # 관제 정의가 켜진 옛 직접 입력 근무표도 지금 화면 그대로다. 2단계에서 관제 정의(데이터) 기준으로 바꾼다
    buttons = board.step_buttons(not legacy)
    gen, undo_label = buttons["generate"], targets and board.step_name(targets[0])
    return render(request, "duty/period_detail.html", {
        "period": period, "board": board, "S": S, "legacy": legacy, "generated_label": board.step_name(S.GENERATED),
        "steps": [(s, board.step_name(s)) for s in board.steps()], "editable": board.editable(),
        "buttons": buttons, "generate_topic": gen + josa(gen, "은/는"),
        "generated_ro": josa(board.step_name(S.GENERATED), "으로/로"),
        "movable": [(s, board.step_name(s)) for s in targets],
        "undo_to": targets[0] if len(targets) == 1 else "",
        "undo_confirm": (f"{gen}{josa(gen, '을/를')} 취소하고 {undo_label}{josa(undo_label, '으로/로')} 돌아갈까요? "
                         "출근표는 그대로 남습니다.") if len(targets) == 1 else "",
        "events": [(e, e.from_status and board.step_name(e.from_status), board.step_name(e.to_status))
                   for e in period.events.select_related("by")],
        "input_depts": Department.objects.filter(board=board).order_by("order", "code") if legacy else [],
        "empty_days": periods.empty_days(period) if legacy and period.status == S.COLLECTING else [],
```
`period_action` 의
```python
        done = f"'{step_label(period.board, period.status)}' 상태로 바꿨습니다."
        if action == "generate" and period.board.input_mode == Board.InputMode.DIRECT:
```
를
```python
        done = f"'{period.board.step_name(period.status)}' 상태로 바꿨습니다."
        if action == "generate" and boards.legacy_admin_entry(period.board):
```
로(다음 줄 문구는 그대로).

- [ ] **Step 5: 회차 화면 템플릿을 고친다**

`duty/templates/duty/period_detail.html` 에서 `<ol class="lifecycle">…` 다음 줄 `{% if period.status == S.DRAFT or direct and period.status == S.COLLECTING %}` 부터 `{% if movable %}` 줄까지를 아래로 바꾼다:
```django
{% if period.status in editable %}
<form method="post" class="search labeled"{% if legacy %} data-start="{{ period.start_date|date:'Y-m-d' }}" data-end="{{ period.end_date|date:'Y-m-d' }}"
      onsubmit="return !(this.start_date.value &gt; this.dataset.start || this.end_date.value &lt; this.dataset.end) || confirm('기간을 줄이면 바깥 날짜의 출근표가 지워집니다. 저장할까요?')"{% endif %}>{% csrf_token %}
  <label>이름 <input name="name" value="{{ period.name }}" required></label>
  <label>시작일 <input type="date" name="start_date" value="{{ period.start_date|date:'Y-m-d' }}" required></label>
  <label>종료일 <input type="date" name="end_date" value="{{ period.end_date|date:'Y-m-d' }}" required></label>
  <button class="outline">기간 저장</button>
</form>
{% else %}
<p>{{ period.start_date|date:"Y-m-d" }} ~ {{ period.end_date|date:"Y-m-d" }}</p>
{% endif %}

<div class="actions">{# 지금 상태에서 다음 단계 버튼(설계 5.4). 버튼 글자는 단계 이름에서 나온다 #}
  {% if period.status == S.DRAFT and board.use_draft %}
  <form method="post" action="{% url 'period_action' period.pk 'open' %}">{% csrf_token %}<button>{{ buttons.open }}</button></form>
  {% elif period.status == S.COLLECTING and board.use_close %}
  <form method="post" action="{% url 'period_action' period.pk 'close' %}">{% csrf_token %}<button>{{ buttons.close }}</button></form>
  {% elif period.status == S.COLLECTING %}
  {% for d in input_depts %}<a role="button"{% if not empty_days or not forloop.first %} class="outline"{% endif %} href="{% url 'collect_table' period.pk d.code %}">표 입력{% if input_depts|length > 1 %} · {{ d.name }}{% endif %}</a>{% endfor %}
  <form method="post" action="{% url 'period_action' period.pk 'generate' %}" onsubmit="return confirm('{{ buttons.generate|escapejs }}할까요? {{ buttons.generate|escapejs }}하면 배포할 수 있{% if buttons.undo %}고, 표를 고치려면 [{{ buttons.undo|escapejs }}]를 누릅니다{% else %}습니다{% endif %}.')">{% csrf_token %}<button{% if empty_days %} class="outline"{% endif %}>{{ buttons.generate }}</button></form>
  {% elif period.status == S.CLOSED and board.use_close %}
  <form method="post" action="{% url 'period_action' period.pk 'generate' %}">{% csrf_token %}<button {% if missing %}disabled{% endif %}>{{ buttons.generate }}</button></form>
  {% elif period.status == S.GENERATED %}
  <a role="button" href="{% url 'period_publish' period.pk %}">배포…</a>
  {% if buttons.regenerate %}<form method="post" action="{% url 'period_action' period.pk 'generate' %}" onsubmit="return confirm('지금 생성 결과를 버리고 다시 생성할까요?')">{% csrf_token %}<button class="outline secondary" {% if missing and board.use_close %}disabled{% endif %}>{{ buttons.regenerate }}</button></form>{% endif %}
  {% if buttons.undo %}<form method="post" action="{% url 'period_move' period.pk %}" onsubmit="return confirm('{{ undo_confirm|escapejs }}')">{% csrf_token %}<input type="hidden" name="to" value="{{ undo_to }}"><button class="outline secondary">{{ buttons.undo }}</button></form>{% endif %}
  {% endif %}
  {% if not legacy and period.status == S.CLOSED or not legacy and period.status == S.GENERATED %}
  <button type="button" class="outline secondary" onclick="document.getElementById('gen-help').showModal()">생성 방식</button>
  {% endif %}
</div>
{% if empty_days %}<p class="note warn">⚠ 아직 입력하지 않은 평일: {% for d in empty_days %}{{ d|date:"n/j" }}{% if not forloop.last %}, {% endif %}{% endfor %}. {{ generate_topic }} 할 수 있지만 그날은 근무자가 없습니다.</p>{% endif %}
{% if missing and board.use_close and period.status != S.DRAFT and period.status != S.PUBLISHED %}<p class="note">출근표가 비어 있는 부서가 있어 아직 생성할 수 없습니다(아래 입력 현황).</p>{% endif %}

{% if movable and not buttons.undo or movable and period.status != S.GENERATED %}
```
(생성됨에서 [… 취소] 버튼이 보이면 '다른 상태로 옮기기' 상자는 숨긴다. [생성 방식] 버튼 조건은 main 과 같은 꼴로 `direct` → `legacy`.) 같은 파일 아래쪽에서:
- 배포 취소 폼의 `confirm('배포를 취소하고 이 회차를 {{ generated_label }}으로 되돌릴까요?')` → `confirm('배포를 취소하고 이 회차를 {{ generated_label|escapejs }}{{ generated_ro }} 되돌릴까요?')`, 그 아래 `<small>` 의 `이 회차는 {{ generated_label }}으로 돌아갑니다` → `이 회차는 {{ generated_label }}{{ generated_ro }} 돌아갑니다`
- `{% if not direct %}` + `<h4>부서별 입력 현황</h4>` 의 `{% if not direct %}` → `{% if not legacy %}`
- `{% if counts and not direct %}` → `{% if counts and not legacy %}`
- `<dialog id="gen-help">` 바로 위 `{% if not direct %}` → `{% if not legacy %}`(상자 글은 main 그대로: "장중관제 10칸(08:30~18:00)에 개발자를…" — 관제 정의에서 만드는 글은 2단계)

- [ ] **Step 6: 입력 표·입력 목록·도움말 기준을 고친다**

`duty/views/collect.py` — import 를 `from ..models import Department, Period, User` 로. `index` 의 `waiting` 을
```python
    waiting = "·".join(dict.fromkeys(d.board.step_name(Period.Status.COLLECTING) for d in depts))
```
로. `_render_table` 의 `direct = period.board.input_mode == Board.InputMode.DIRECT` 를
```python
    legacy = boards.legacy_admin_entry(period.board)  # 1단계 임시 기준(2단계에서 지운다)
```
로, 컨텍스트 두 줄을
```python
        "is_open": is_open, "legacy": legacy, "ncols": len(keys) + 2,
        "show_fill": is_open and legacy, "can_rotate": collect.can_rotate(dept),  # 채우기 버튼(설계 6.2): 1단계는 마감을 안 쓰는 근무표만
```
로.

`duty/templates/duty/collect_table.html`: `{% if direct %}` 세 곳을 모두 `{% if legacy %}` 로(4·5·9번째 줄, 글자는 그대로).

`duty/help.py` — `from .models import InputMode` 를 `from .services import boards` 로, `allowed` 의 `direct` 갈래를
```python
    if name == "direct":
        return any(boards.legacy_admin_entry(b) for b in perms.admin_boards(user))  # 1단계 임시 기준(2단계에서 글 하나로)
```
로.

- [ ] **Step 7: 통과와 화면 불변을 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_steps.py tests/test_snapshots.py tests/test_views_direct.py tests/test_views_manage.py tests/test_help.py tests/test_fill.py tests/test_views_collect.py`
Expected: 모두 통과. `tests/test_snapshots.py` 가 고치지 않은 기준 그대로 통과한다(IT [생성 방식] 글·버튼, 운영팀 [확정]·[확정 취소] 확인창, 관제 이력이 남은 운영팀 회차, 입력 표 글자 그대로). `git status --short tests/snapshots/` → 아무것도 안 나온다.

- [ ] **Step 8: 전체 테스트**

Run: `.venv/bin/pytest -W error -q && DUTY_DEBUG=1 DUTY_ENV_FILE= DUTY_DATA_DIR=$(mktemp -d) .venv/bin/python manage.py makemigrations duty --check --dry-run`
Expected: `1290 passed`, "No changes detected in app 'duty'"

- [ ] **Step 9: 브라우저로 본다(보이는 변화가 없어야 한다)**

위 "브라우저 확인 준비"대로 띄운다. `admin` 으로:
1. PC 1400px, 보통 글씨, 밝게: [회차] → IT 작성 중 회차가 있으면 [취합 열기], 운영팀 "이번 2주" → 단계 띠 "입력 중 → 확정 → 배포됨", [표 입력]·[확정] 버튼, "⚠ 아직 입력하지 않은 평일"(다 비어 있다). [표 입력]에 주마다 [2주 전 기준으로 채우기]·[지난주와 같게]. "지난 2주"(배포됨) → [배포 취소] 설명 "확정으로 돌아갑니다".
2. IT 회차 하나를 마감 상태로 옮겨(다른 상태로 옮기기) [장중관제 생성](비어 있으면 회색)과 [생성 방식] → 상자의 "장중관제 10칸(08:30~18:00)에 개발자를 한 명씩", "08:30 칸은 정상, 17:00 칸은 석식교대, 나머지 칸은 정상·석식교대 둘 다 됩니다."가 main 과 같은지.
3. 390px·아주 크게·다크 모드에서 운영팀 회차 화면과 입력 표: 버튼 줄이 줄바꿈되고 가로 넘침 `false`.

- [ ] **Step 10: 커밋**

```bash
git add duty/models.py duty/shifts.py duty/views/manage.py duty/views/collect.py duty/help.py duty/templates/duty/period_detail.html duty/templates/duty/collect_table.html tests/test_board_steps.py
git commit -m "$(cat <<'EOF'
feat: 회차 화면 버튼을 단계 이름에서 만들고(한 묶음, 조사·escapejs), 1단계 화면 갈래는 임시 기준으로 main 그대로

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

---

### Task 5: `input_mode` 지우기(0023 마무리, 입력 그룹·부서 폼은 임시 기준으로, 관리 화면 단계 칸·버튼 글자 검사)

> 범위: 이제 아무도 읽지 않는 `input_mode` 칸·`InputMode`·`DIRECT_STEPS`·`step_label`, "직접 입력 근무표는 부서 하나" 규칙을 지운다. 부서 저장의 입력 그룹 자동 생성과 관리 화면 부서 폼의 입력 담당자 금지는 **같은 결과로 기준만** `legacy_admin_entry` 로 바꾼다(설계 5.3 1단계, 늦은 입력 그룹은 3단계). 0023 에 칸 제거와 거꾸로 규칙(설계 10.2)을 더한다. 관리 화면 근무표 폼에 단계 칸(만들 때만, 저장된 근무표는 읽기 전용 — 설계 5.1). `add_board` 정리. 보이는 변화는 관리 화면 근무표(입력 방식 → 회차 단계)뿐이다.

**Files:**
- Modify: `duty/models.py` — `InputMode` 클래스·`Board.InputMode`·`input_mode` 칸·`board_input_mode_valid` 지우기, `Department.clean` 지우기, `Department.save` 의 그룹 만들기 조건, `DIRECT_STEPS`·`step_label` 지우기, `Board.bad_buttons` 더하기
- Modify: `duty/migrations/0023_board_steps.py` — docstring, `FIELDS`·`MODES`·`backward`, `RunPython(forward, backward)`, `RemoveConstraint`·`RemoveField`
- Modify: `duty/admin.py` — `DepartmentForm.clean` 기준, `STEP_FIELDS`·`BoardForm`(이름·버튼 글자 검사), `BoardAdmin`(docstring·`list_display`·`get_fieldsets`·`get_readonly_fields`·`step_line`)
- Modify: `duty/services/board_setup.py` — docstring, import, `create_direct_board` → `create_board`, `Board(...)`
- Modify: `duty/management/commands/add_board.py` — `help`, 부르는 함수, 요약 첫 줄
- Modify: `tests/it_defs.py`(`OPS_STEPS` 에서 `input_mode` 빼기), `tests/conftest.py`(`it_board` 기본값)
- Modify(테스트): `tests/test_boards_models.py`, `tests/test_admin_boards.py`, `tests/test_add_board.py`, `tests/test_migration_board_steps.py`

**Interfaces:**
- Consumes: Task 2~4 결과(이제 `input_mode` 를 읽는 앱 코드는 admin·models·board_setup 뿐), `boards.legacy_admin_entry`
- Produces:
  - `Department.save`: 그룹이 없고 근무표가 `not legacy_admin_entry(board)`(마감을 쓰는 근무표)면 "<부서> 출근표 입력" 그룹을 만든다(지금과 같은 결과). `Department.clean` 은 없어진다(부서 수 제한 없음)
  - `DepartmentForm.clean`: 그룹 유무 = 저장된 그룹 또는 `not legacy_admin_entry(board)`, 마감 끈 근무표 부서에 담당자를 고르면 지금 칸 오류("직접 입력 근무표의 부서는 입력 담당자가 없습니다. 근무표 관리자가 입력합니다." — 1단계 문구 규칙)
  - `duty.admin.STEP_FIELDS = ["step_draft", "step_collecting", "step_closed", "step_generated", "step_published"]`, `BoardForm.Meta.fields = ["code", "name", "use_draft", "use_close", *STEP_FIELDS]`, 저장된 근무표는 `get_readonly_fields` 가 `code`·`use_draft`·`use_close`·`STEP_FIELDS`·`group_link`(3단계가 단계 칸을 연다 — 이 계획에는 없다)
  - `Board.bad_buttons() -> list[str]`: 켠 단계에서 나오는 버튼 글자(관제가 있을 때·없을 때 둘 다, [배포…]·[재생성]·[… 취소] 포함) 중 비거나 서로 겹치는 것. `BoardForm.clean` 이 이름 칸 오류 "버튼 이름이 비거나 다른 버튼과 같아집니다: [<글자>]"로 막는다(생성·취소 글자는 `step_generated`, 열기·마감은 `step_collecting` 칸에, 설계 5.4)
  - `board_setup.create_board(code, name, shifts, lunch, people, admin_username=None) -> Board`(이름만 바뀜)
  - 0023 거꾸로: 근무표마다 `(use_draft, use_close, 다섯 이름)` 이 IT 기본값이면 `collect`, 직접 입력 기본값(`False, False, 작성 중, 입력 중, 마감, 확정, 배포됨`)이면 `direct`. 하나라도 그 밖이면 `RuntimeError("단계를 고친 근무표가 있어 입력 방식으로 되돌릴 수 없습니다: <code들>. 업그레이드 전 백업으로 복원하세요(…)")`, 아무것도 바꾸지 않는다

- [ ] **Step 1: 실패 테스트를 쓴다**

`tests/test_migration_board_steps.py` 맨 끝에:
```python


@pytest.fixture
def new_apps():
    yield _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())


def _board(apps, code, **steps):
    group = apps.get_model("auth", "Group").objects.create(name=f"{code} 근무표 관리")
    return apps.get_model("duty", "Board").objects.create(code=code, name=code, admin_group=group, **steps)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_input_mode_column_is_gone(new_apps):
    assert "input_mode" not in {f.name for f in new_apps.get_model("duty", "Board")._meta.fields}


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_reverse_restores_input_mode_for_default_steps(new_apps):
    """IT 기본값·직접 입력 기본값 근무표만 있으면 거꾸로 돌아 input_mode 를 되살린다."""
    _board(new_apps, "ops", **dict(zip(STEPS, OPS)))
    apps = _migrate(BEFORE)
    Board = apps.get_model("duty", "Board")
    assert dict(Board.objects.values_list("code", "input_mode")) == {"it": "collect", "ops": "direct"}
    assert "use_draft" not in {f.name for f in Board._meta.fields}


@pytest.mark.parametrize("steps", [
    {"use_close": False},                                           # 하나만 끔
    {"use_draft": False, "use_close": False},                       # 둘 다 껐지만 이름은 IT 그대로
    {"step_published": "공개됨"},                                    # 이름을 고침
])
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_reverse_refused_when_steps_cannot_be_input_mode(new_apps, steps):
    _board(new_apps, "odd", **steps)
    with pytest.raises(RuntimeError, match="odd.*백업"):
        _migrate(BEFORE)
    Board = new_apps.get_model("duty", "Board")
    assert Board.objects.filter(code="odd").exists()  # 아무것도 바꾸지 않는다
```

`tests/test_boards_models.py`:
- `test_it_board_fixture_has_14_defs_and_admin_group` 첫 줄을
```python
    assert it_board.code == "it" and it_board.steps() == ["draft", "collecting", "closed", "generated", "published"]
```
로.
- `test_depts_fixture_on_it_board_with_input_groups` 바로 앞에:
```python
def test_board_without_close_can_have_many_departments(it_board):
    """'직접 입력 근무표는 부서 하나' 규칙은 없다(근무표 통합 설계 5.3)."""
    ops = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
    for code in ("OPS", "OP2"):
        Department(code=code, name=f"운영{code}", shifts="normal", board=ops).full_clean()
        Department.objects.create(code=code, name=f"운영{code}", shifts="normal", board=ops)


```
- `test_board_constraints` 의 `_bad(lambda: Board.objects.create(code="x", name="x", input_mode="bogus"))` 를
```python
    _bad(lambda: Board.objects.create(code="x", name="x", step_closed=""))
```
로. (입력 그룹 테스트 `test_department_save_creates_input_group_for_collect_board`·`test_department_without_collect_board_has_no_input_group` 은 그대로 통과해야 한다 — 같은 결과.)

`tests/test_admin_boards.py`:
- import 를 `from duty.admin import STEP_FIELDS, DepartmentForm` 로.
- `def form(rows, initial=0, **board):` 바로 앞에:
```python
def steps_form(board=None, **names):
    """근무표 폼의 단계 칸(체크박스는 켤 때만 보낸다). board 가 없으면 작성 중·마감을 끈 시장운영실 모양."""
    b = board or Board(**OPS_STEPS)
    data = {f: getattr(b, f) for f in STEP_FIELDS} | {f: "on" for f in ("use_draft", "use_close") if getattr(b, f)}
    return data | names


```
- `change()` 의 마지막 줄을 `    return form(rows, initial=len(shifts), name=board.name, **steps_form(board))` 로.
- `form(…, input_mode="direct")` 일곱 곳: `sed -i 's/input_mode="direct"/**steps_form()/' tests/test_admin_boards.py`
- `test_change_page_locks_code_mode_keys_and_has_no_delete` 의 이름과 첫 단언을:
```python
def test_change_page_locks_code_steps_keys_and_has_no_delete(su_client, ops):
    board, *_ = ops
    body = su_client.get(reverse("admin:duty_board_change", args=[board.pk])).content.decode()
    assert 'name="name"' in body and 'name="code"' not in body and 'name="input_mode"' not in body
    assert "회차 단계" in body and 'name="use_close"' not in body and 'name="step_collecting"' not in body  # 1단계: 읽기 전용
```
로(나머지 세 줄 그대로).
- `test_direct_board_has_one_department` 를 아래로 바꾼다:
```python
def test_board_without_close_takes_second_department(ops, it_board):
    """부서 수 제한은 없다(근무표 통합 설계 5.3)."""
    board, *_ = ops
    Department.objects.create(code="OPS", name="운영", shifts="dawn", board=board)
    f = DepartmentForm({"code": "OPS2", "name": "운영2", "board": board.pk, "order": 1, "shifts": ["dawn"], "managers": []})
    assert f.is_valid(), f.errors


# ── 회차 단계 칸(근무표 통합 설계 5.1) ──

def test_add_board_saves_steps(su_client, it_board):
    r = su_client.post(ADD, form(three(), code="ops", name="운영팀", **steps_form()))
    assert r.status_code == 302, errors(r)
    b = Board.objects.get(code="ops")
    assert (b.use_draft, b.use_close, b.step_collecting, b.step_generated) == (False, False, "입력 중", "확정")
    assert "입력 중 → 확정 → 배포됨" in su_client.get(reverse("admin:duty_board_changelist")).content.decode()


@pytest.mark.parametrize("names,msg", [
    ({"step_generated": "입력 중"}, "단계 이름이 겹칩니다: 입력 중"),
    ({"step_closed": "마\n감"}, "단계 이름에 줄바꿈을 쓸 수 없습니다."),
    ({"step_draft": ""}, "필수 항목입니다."),
    ({"step_generated": "됨"}, "버튼 이름이 비거나 다른 버튼과 같아집니다: []"),            # 생성 버튼 글자가 빈다
    ({"use_close": "on", "step_generated": "입력 마감됨"}, "버튼 이름이 비거나 다른 버튼과 같아집니다: [입력 마감]"),
])
def test_step_names_checked(su_client, it_board, names, msg):
    r = su_client.post(ADD, form(three(), code="ops", name="운영팀", **steps_form(**names)))
    assert r.status_code == 200 and msg in r.content.decode()
    assert not Board.objects.filter(code="ops").exists()


def test_saved_board_steps_are_read_only(su_client, ops):
    """1단계: 저장된 근무표의 단계는 관리 화면에서 바꾸지 않는다(보낸 값은 무시, 설계 5.1). 3단계에서 연다."""
    board, a, b = ops
    data = change(board, [a, b]) | steps_form(board, use_draft="on", step_collecting="모으는 중")
    r = su_client.post(reverse("admin:duty_board_change", args=[board.pk]), data)
    assert r.status_code == 302, errors(r)
    board.refresh_from_db()
    assert (board.use_draft, board.step_collecting) == (False, "입력 중")
```
(`tests/test_admin_department.py` 는 고치지 않는다: 입력 그룹 이름 겹침·마감 끈 근무표 부서의 담당자 금지 테스트가 같은 결과로 통과해야 한다.)

`tests/test_add_board.py::test_happy_path`:
- `assert board.name == "시장운영실" and board.input_mode == Board.InputMode.DIRECT` 를
```python
    assert board.name == "시장운영실" and [board.step_name(s) for s in board.steps()] == ["입력 중", "확정", "배포됨"]
```
로, `assert "mops01~mops03" in out …` 다음 줄에
```python
    assert "(코드 mops, 단계 입력 중 → 확정 → 배포됨)" in out
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_migration_board_steps.py tests/test_boards_models.py tests/test_admin_boards.py tests/test_add_board.py`
Expected: FAIL — `test_admin_boards.py` 는 모음 오류 `ImportError: cannot import name 'STEP_FIELDS' from 'duty.admin'`. 그 파일을 빼고 돌리면 `7 failed`: 마이그레이션 5개(`test_input_mode_column_is_gone`, `test_reverse_restores…`(ops 가 collect 로 돌아옴), `test_reverse_refused…[steps0~2]`(`DID NOT RAISE`)), `test_board_without_close_can_have_many_departments`(`ValidationError: 직접 입력 근무표에는 부서를 하나만…`), `test_happy_path`(단계 요약 없음).

- [ ] **Step 3: 모델에서 입력 방식을 지운다**

`duty/models.py`:
- `class InputMode(models.TextChoices): …`(세 줄 + 빈 줄 둘), `Board` 의 `InputMode = InputMode`(+ 빈 줄), `input_mode = …` 줄을 지운다.
- `Board.Meta.constraints` 를
```python
        constraints = [models.CheckConstraint(name="board_step_names_set", condition=(
            ~Q(step_draft="") & ~Q(step_collecting="") & ~Q(step_closed="") & ~Q(step_generated="") & ~Q(step_published="")))]
```
로.
- `Department` 의 `def clean(self): …`(직접 입력 부서 하나 검사, 뒤 빈 줄 포함)을 지운다.
- `Department.save` 의
```python
        # 부서별 취합 근무표의 부서는 입력 그룹이 있어야 한다(픽스처·관리 화면·서비스 어느 길로 만들어도)
        if self.input_group_id is None and self.board_id is not None and self.board.input_mode == InputMode.COLLECT:
```
를
```python
        from .services.boards import legacy_admin_entry  # 순환 import 를 피해 여기서(3단계에서 이 갈래와 함께 지운다)
        # 마감을 쓰는 근무표의 부서는 입력 그룹이 있어야 한다(픽스처·관리 화면·서비스 어느 길로 만들어도, 1단계 임시 기준)
        if self.input_group_id is None and self.board_id is not None and not legacy_admin_entry(self.board):
```
로(그 아래 줄들 그대로).
- `# 직접 입력 근무표의 화면 단계…` 주석, `DIRECT_STEPS`, `def step_label(…)` 전체(빈 줄 포함)를 지운다.
- `Board.step_buttons` 바로 뒤(`move_targets` 앞)에 버튼 글자 검사(설계 5.4):
```python
    def bad_buttons(self) -> list[str]:
        """켠 단계에서 나오는 버튼 글자 중 비거나 다른 버튼과 같아지는 것(설계 5.4). 관제가 있을 때·없을 때 둘 다 본다."""
        bad = []
        for has_slots in (False, True):
            b = self.step_buttons(has_slots)
            labels = ([b["generate"], "배포…"] + [b["open"]] * self.use_draft + [b["close"]] * self.use_close
                      + [x for x in (b["undo"], b["regenerate"]) if x])
            bad += [x for x in labels if (not x.strip() or labels.count(x) > 1) and x not in bad]
        return bad

```

- [ ] **Step 4: 0023 에 칸 제거와 거꾸로 규칙을 더한다**

`duty/migrations/0023_board_steps.py` 의 docstring 끝(`… 지금과 같다).` 줄 다음)에 두 항목을 더하고 `forward` 뒤에 `backward` 를 쓴다. 파일 앞부분이 아래가 되게:
```python
"""근무표 단계 설정(근무표 통합 설계 10.2, 1단계). 앱 코드를 import 하지 않고 값을 그대로 적는다.

- 단계 칸을 더한다: 작성 중·마감 단계 사용(기본 켬), 다섯 단계 화면 이름(기본 = 지금 IT 이름) + 이름 빈 글자 금지 제약.
- 직접 입력(input_mode=direct) 근무표: 작성 중·마감을 끄고 취합 중 = '입력 중', 생성됨 = '확정'(지금 화면 이름 그대로).
  부서별 취합(collect) 근무표는 기본값 그대로. 입력 그룹은 만들지 않는다(그룹 없음 = 관리자만 입력, 지금과 같다).
- 입력 방식 칸(input_mode)과 그 제약을 지운다.
- 거꾸로(0018~0022 처럼 잃을 데이터가 있을 때만 거부): input_mode 를 되살려 근무표마다 채운다. 둘 다 켬 + IT 기본 이름이면
  collect, 둘 다 끔 + 직접 입력 기본 이름이면 direct. 그 밖(하나만 끔, 이름을 고침)은 input_mode 로 나타낼 수 없어
  그 근무표 코드를 알려 주며 멈춘다(되돌리기는 업그레이드 전 백업 복원으로).
"""
from django.db import migrations, models

FIELDS = ("use_draft", "use_close", "step_draft", "step_collecting", "step_closed", "step_generated", "step_published")
MODES = {
    (True, True, "작성 중", "취합 중", "마감", "생성됨", "배포됨"): "collect",
    (False, False, "작성 중", "입력 중", "마감", "확정", "배포됨"): "direct",
}


def forward(apps, schema_editor):
    apps.get_model("duty", "Board").objects.filter(input_mode="direct").update(
        use_draft=False, use_close=False, step_collecting="입력 중", step_generated="확정")


def backward(apps, schema_editor):
    """RemoveField 가 먼저 되돌려져 input_mode 칸(기본 collect)이 있는 상태에서 돈다."""
    Board = apps.get_model("duty", "Board")
    rows = list(Board.objects.order_by("id").values_list("pk", "code", *FIELDS))
    odd = [code for _, code, *steps in rows if tuple(steps) not in MODES]
    if odd:
        raise RuntimeError(f"단계를 고친 근무표가 있어 입력 방식으로 되돌릴 수 없습니다: {', '.join(odd)}. "
                           '업그레이드 전 백업으로 복원하세요(docs/OPERATIONS.md "업그레이드·롤백").')
    for pk, _, *steps in rows:
        Board.objects.filter(pk=pk).update(input_mode=MODES[tuple(steps)])
```
`operations` 의 마지막 `migrations.RunPython(forward, migrations.RunPython.noop),` 를
```python
        migrations.RunPython(forward, backward),
        migrations.RemoveConstraint(
            model_name='board',
            name='board_input_mode_valid',
        ),
        migrations.RemoveField(
            model_name='board',
            name='input_mode',
        ),
```
로.

- [ ] **Step 5: 관리 화면을 고친다**

`duty/admin.py`:
- `DepartmentForm.clean` 의
```python
        has_group = self.instance.input_group_id or (board and board.input_mode == board.InputMode.COLLECT)
        if c.get("managers") and board and board.input_mode == board.InputMode.DIRECT:
```
를
```python
        has_group = self.instance.input_group_id or (board and not boards.legacy_admin_entry(board))  # 1단계 임시 기준
        if c.get("managers") and board and boards.legacy_admin_entry(board):
```
로(아래 칸 오류 글·이름 겹침 검사는 그대로, `boards` 는 이미 import 돼 있다).
- `class BoardForm` 을:
```python
STEP_FIELDS = ["step_draft", "step_collecting", "step_closed", "step_generated", "step_published"]


class BoardForm(forms.ModelForm):
    class Meta:
        model = Board
        fields = ["code", "name", "use_draft", "use_close", *STEP_FIELDS]

    def clean(self):
        c = super().clean()
        names = [c.get(f) for f in STEP_FIELDS]
        for f, v in zip(STEP_FIELDS, names):  # 단계 이름(설계 5.1): 줄바꿈 금지, 서로 다름
            if v and ("\n" in v or "\r" in v):
                self.add_error(f, "단계 이름에 줄바꿈을 쓸 수 없습니다.")
            elif v and names.count(v) > 1:
                self.add_error(f, f"단계 이름이 겹칩니다: {v}")
        if not self.errors and all(names):  # 버튼 글자 검사(설계 5.4): 저장된 근무표는 단계 칸이 읽기 전용이라 만들 때만
            steps = Board(use_draft=c.get("use_draft"), use_close=c.get("use_close"), **dict(zip(STEP_FIELDS, names)))
            gen = steps.step_buttons(False)
            for x in steps.bad_buttons():  # 생성·취소 글자는 생성됨 이름에서, 열기·마감은 취합 중 이름에서 나온다
                field = "step_generated" if x in (gen["generate"], gen["undo"]) else "step_collecting"
                self.add_error(field, f"버튼 이름이 비거나 다른 버튼과 같아집니다: [{x}]")
        name = c.get("name")
```
로 시작하게 바꾼다(그 아래 관리 그룹 이름 검사는 그대로. 읽기 전용 칸은 `cleaned_data` 에 없어 검사하지 않는다).
- `BoardAdmin` docstring 첫 줄을 `"""근무표(설계 4.2·4.3). code(boards.it_board() 가 IT 근무표를 찾는 열쇠)는 만든 뒤 바꾸지 않는다. 단계 칸은 1·2단계에서 만들 때만 정한다.` 로, `list_display = ["name", "code", "step_line", "admin_group"]`, `get_fieldsets`·`get_readonly_fields` 를:
```python
    def get_fieldsets(self, request, obj=None):
        fields = ["code", "name"] + ([] if obj is None else ["group_link"])
        return [(None, {"fields": fields, "description": (
            "근무 정의의 이름·시각을 운영 중에 바꾸면 발송 창이 열린 알림이 한 번 다시 나가고, 예전에 내려받은 CSV 의 "
            "열 이름이 맞지 않습니다. 저장한 정의는 지우거나 키를 바꿀 수 없으니 '사용'을 끄고 새 줄을 더합니다. "
            "근무조 1~4 는 이름일 뿐이고 이른·늦은 조는 시작 시각으로 정합니다.")}),
                ("회차 단계", {"fields": ["use_draft", "use_close", *STEP_FIELDS], "description": (
                    "작성 중·마감을 끄면 그 단계를 건너뜁니다. 이름은 화면에 보이는 단계 이름이고, 버튼 이름은 단계 이름에서 "
                    "나옵니다(예: '취합 중' → [취합 열기]). IT = 둘 다 켬, 작성 중·취합 중·마감·생성됨·배포됨. "
                    "시장운영실 = 둘 다 끔, 취합 중 '입력 중'·생성됨 '확정'. 저장한 근무표의 단계는 지금은 바꾸지 않습니다.")})]

    def get_readonly_fields(self, request, obj=None):
        # 1단계: 저장된 근무표의 단계 칸은 읽기 전용(임시 기준 legacy_admin_entry 와 섞인 상태를 막는다, 설계 5.1). 3단계에서 연다
        return [] if obj is None else ["code", "use_draft", "use_close", *STEP_FIELDS, "group_link"]

    @admin.display(description="단계")
    def step_line(self, obj):
        return " → ".join(obj.step_name(s) for s in obj.steps())
```
로.

- [ ] **Step 6: `add_board`·테스트 값을 고친다**

`duty/services/board_setup.py`: docstring 을
```python
"""관리자가 출근표를 직접 넣는 근무표(단계: 입력 중 → 확정 → 배포됨)를 한 번에 만든다(manage.py add_board). 관리 화면 절차
(OPERATIONS '근무표 추가하기' 1~4단계)를 한 트랜잭션으로: 근무표·근무 정의·부서 하나·사람(사용할 수 없는 비밀번호)·근무표 관리자.
검사는 관리 화면과 같은 모델 검사를 쓴다."""
```
로, import 를 `from ..models import Board, BoardShift, Department, User` 로, `def create_direct_board(` 를
```python
def create_board(code: str, name: str, shifts: list[Span], lunch: Span | None,
                 people: list[tuple[int, str]], admin_username: str | None = None) -> Board:
```
로, `Board(...)` 를
```python
    board = Board(code=code, name=name,  # 단계: 입력 중 → 확정 → 배포됨(마이그레이션 0023 이 옛 직접 입력 근무표에 넣은 값과 같다)
                  use_draft=False, use_close=False, step_collecting="입력 중", step_generated="확정")
```
로.

`duty/management/commands/add_board.py`: `help` 를
```python
    help = ("근무표 관리자가 출근표를 넣는 근무표(예: 시장운영실, 단계 입력 중 → 확정 → 배포됨)를 한 번에 만든다: "
            "근무표·근무 정의·부서·사람 계정(비밀번호 없이)·근무표 관리자. 하나라도 문제가 있으면 아무것도 만들지 않는다.")
```
로, 부르는 곳을
```python
            board = board_setup.create_board(o["code"], o["name"], shifts, lunch,
                                             board_setup.read_people(text), o["admin"])
```
로, 요약 첫 줄을
```python
            f"근무표를 만들었습니다: {board.name} (코드 {board.code}, 단계 {' → '.join(board.step_name(s) for s in board.steps())})",
```
로.

`tests/it_defs.py` 의 `OPS_STEPS` 에서 `input_mode="direct", ` 를 지운다:
```python
OPS_STEPS = dict(use_draft=False, use_close=False, step_collecting="입력 중", step_generated="확정")
```
`tests/conftest.py` `it_board` 의 `get_or_create` 를
```python
    board, _ = Board.objects.get_or_create(code="it", defaults={"name": "IT 당번표"})
```
로.

- [ ] **Step 7: 통과를 확인한다**

Run: `git grep -n -E "InputMode|input_mode|DIRECT_STEPS|step_label|create_direct_board" -- duty tools ':!duty/migrations' ':!duty/help_videos'`
Expected: 아무것도 안 나온다.

Run: `.venv/bin/pytest -W error -q tests/test_migration_board_steps.py tests/test_boards_models.py tests/test_admin_boards.py tests/test_admin_department.py tests/test_add_board.py tests/test_help_seed.py tests/test_snapshots.py`
Expected: 모두 통과(스냅샷 그대로)

- [ ] **Step 8: 전체 테스트와 마이그레이션 왕복**

Run: `.venv/bin/pytest -W error -q && DUTY_DEBUG=1 DUTY_ENV_FILE= DUTY_DATA_DIR=$(mktemp -d) .venv/bin/python manage.py makemigrations duty --check --dry-run`
Expected: `1303 passed`(옛 마이그레이션 테스트들이 0023 을 거꾸로 지나 0014~0022 로 내려갔다 오는 것도 포함), "No changes detected in app 'duty'"

Run(새 DB 에서 왕복):
```bash
W=$(mktemp -d); export DUTY_ENV_FILE= DUTY_DEBUG=1 DUTY_DATA_DIR=$W/data
.venv/bin/python manage.py migrate -v0 && .venv/bin/python manage.py migrate -v0 duty 0022 && .venv/bin/python manage.py migrate -v0 && echo 왕복됨
rm -rf $W; unset DUTY_ENV_FILE DUTY_DEBUG DUTY_DATA_DIR
```
Expected: `왕복됨`

- [ ] **Step 9: 브라우저로 관리 화면을 본다**

"브라우저 확인 준비"대로 띄워 `admin` 으로 `http://127.0.0.1:8795/admin/`:
1. PC 1400px, 밝게: 근무표 목록의 "단계" 열이 IT "작성 중 → 취합 중 → 마감 → 생성됨 → 배포됨", 운영팀 "입력 중 → 확정 → 배포됨". 운영팀 편집 화면의 "회차 단계" 묶음은 글자로만 보이고(체크·칸 없음) 설명 글 끝이 "저장한 근무표의 단계는 지금은 바꾸지 않습니다."
2. [근무표 추가]: "회차 단계" 묶음에 체크 둘·이름 칸 다섯(기본 IT 이름). 마감 이름을 "생성됨"으로 바꿔 저장 → "단계 이름이 겹칩니다: 생성됨" 칸 오류, 생성됨 이름을 "됨"으로 → "버튼 이름이 비거나 다른 버튼과 같아집니다: []" 칸 오류(저장하지 않고 돌아간다).
3. 부서 → 운영 → 입력 담당자에 아무나 고르고 저장 → "직접 입력 근무표의 부서는 입력 담당자가 없습니다…" 칸 오류(지금과 같다).
4. 다크 모드: 관리 화면은 Django 기본 화면이라 사이트 글씨 설정을 따르지 않는다. "회차 단계" 설명 글이 읽히는지만 본다. 390px 은 관리 화면 대상이 아니다(OPERATIONS "PC 브라우저에서").

- [ ] **Step 10: 커밋**

```bash
git add duty/models.py duty/migrations/0023_board_steps.py duty/admin.py duty/services/board_setup.py duty/management/commands/add_board.py tests/
git commit -m "$(cat <<'EOF'
feat: 입력 방식 칸 지우기(0023 칸 제거·거꾸로 규칙), 부서 하나 규칙 삭제, 관리 화면 근무표에 회차 단계 칸(만들 때만), add_board 정리

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

---

### Task 6: 1단계 문서

> 범위: 문서만. 코드·테스트 변화 없음(설계 13절의 1단계 몫: ARCHITECTURE "근무표와 칸"·"회차"·"출근표 입력"·"생성"·"도움말", OPERATIONS 업그레이드 메모(10.4 1단계)와 확인 쿼리(10.3), "근무표 추가하기"·"운영 중에 바꾸면", OVERVIEW 용어, DEVELOPMENT 스냅샷, PRINCIPLES 결정 기록). 설계 문서(`docs/superpowers/specs/2026-11-17-boards-unify-design.md`)는 5단계에서 합치고 지우므로 그대로 둔다.

**Files:**
- Modify: `docs/ARCHITECTURE.md`, `docs/OVERVIEW.md`, `docs/OPERATIONS.md`, `docs/DEVELOPMENT.md`, `docs/PRINCIPLES.md`

**Interfaces:**
- Consumes: Task 1~5 의 이름(`Board.use_draft`·`use_close`·`step_*`·`first_step`·`editable`·`generate_from`·`move_targets`·`step_buttons`, `shifts.gen_help`, `boards.legacy_admin_entry`, 0023, `tests/test_snapshots.py`)
- Produces: 문서만

- [ ] **Step 1: 아래 찾을 글을 바꿀 글로 바꾼다(파일마다 한 번씩만 나오는 글이다)**

1. `docs/ARCHITECTURE.md`

   찾을 글:
   ```text
   `add_board`(직접 입력 근무표 한 번에 만들기, 규칙은 `services/board_setup.py`)
   ```
   바꿀 글:
   ```text
   `add_board`(작성 중·마감을 끈 근무표(입력 중 → 확정 → 배포됨) 한 번에 만들기, 규칙은 `services/board_setup.py`)
   ```

2. `docs/ARCHITECTURE.md`

   찾을 글:
   ```text
   근무표를 만들면 관리 그룹 "<이름> 근무표 관리"가, 부서별 취합(`input_mode=collect`) 근무표에 부서를 만들면 입력 그룹 "<부서> 출근표 입력"이 저절로 생긴다.
   ```
   바꿀 글:
   ```text
   근무표마다 회차 단계 설정(`use_draft`·`use_close`, 다섯 단계 화면 이름 `step_*`, 아래 "회차")이 있다. 근무표를 만들면 관리 그룹 "<이름> 근무표 관리"가, 마감 단계를 쓰는 근무표에 부서를 만들면 입력 그룹 "<부서> 출근표 입력"이 저절로 생긴다(1단계 임시 기준 `boards.legacy_admin_entry`, 근무표 통합 3단계에서 첫 입력 담당자를 넣을 때 만들기로 바뀐다).
   ```

3. `docs/ARCHITECTURE.md`

   찾을 글:
   ```text
   code(`boards.it_board()` 가 IT 근무표를 찾는 열쇠)와 입력 방식은 만든 뒤 바꾸지 않으며, 근무표는 지우지 않는다. 직접 입력 근무표에는 부서를 하나만 두고(`Department.clean`), 그 부서는 입력 담당자를 고를 수 없다(관리자가 입력, `DepartmentForm`).
   ```
   바꿀 글:
   ```text
   code(`boards.it_board()` 가 IT 근무표를 찾는 열쇠)는 만든 뒤 바꾸지 않으며, 근무표는 지우지 않는다. 회차 단계 칸은 만들 때 정하고 저장된 근무표에서는 읽기 전용이다(1·2단계: 입력 그룹 기준 `legacy_admin_entry` 와 섞인 상태를 막는다. 3단계에서 기준 함수를 지우며 연다). 단계 이름은 비울 수 없고 줄바꿈 금지·서로 다름, 켠 단계에서 나오는 버튼 글자가 비거나 서로 겹치는 이름도 막는다(`BoardForm`·`Board.bad_buttons`·제약 `board_step_names_set`). 부서 수 제한은 없다. 마감을 안 쓰는 근무표의 부서는 입력 담당자를 고를 수 없다(관리자가 입력, `DepartmentForm`, 1단계 임시 기준).
   ```

4. `docs/ARCHITECTURE.md`

   찾을 글:
   ```text
   - **직접 입력 근무표**(`input_mode=direct`)는 같은 DB 상태를 쓰고 화면 이름만 **입력 중(취합 중) → 확정(생성됨) → 배포됨**이다(`models.DIRECT_STEPS`·`step_label`·`Period.status_label`). 새 회차는 만들자마자 입력 중이고(`periods.save_draft`), 입력 중에도 기간을 고친다(기간을 줄일 때만 [기간 저장]이 바깥 날짜 출근표가 지워진다는 확인 창을 띄운다). 관리자가 회차 화면의 [표 입력]으로 출근표를 넣고 [확정](`generate.run_generation`: 입력 중·확정에서, 빈 평일은 막지 않고 경고 — `periods.empty_days`)하면 배포할 수 있다. 빈 평일은 장중관제 생성에서 빼고(후보가 없다), 평일이 모두 비어도 확정된다(관제 칸 없이). [확정 취소]는 입력 중으로만 옮긴다(`periods.move`, 당번 배정을 지우고 출근표는 남긴다). 작성 중·마감은 쓰지 않는다(그 상태에 남은 회차는 "다른 상태로 옮기기"로 입력 중으로만 옮긴다). 빈 평일이 있으면 첫 [표 입력]이, 없으면 [확정]이 진한 버튼이다. 입력 현황·편차 표·생성 방식은 보이지 않는다.
   ```
   바꿀 글:
   ```text
   - **회차 단계는 근무표 설정이다**(`Board.use_draft`·`use_close`·`step_*`). DB 상태 다섯 개는 그대로이고 작성 중·마감은 끌 수 있으며, 화면 이름(`Period.status_label`, 상태 기록, 단계 띠)은 근무표의 단계 이름이다(끈 단계도 이름이 있어 남은 회차·기록이 이름으로 보인다). IT = 둘 다 켬(작성 중·취합 중·마감·생성됨·배포됨), 시장운영실 = 둘 다 끔(입력 중·확정·배포됨. 마이그레이션 0023 이 옛 `input_mode=direct` 근무표에 넣은 값). 규칙은 쿼리 없는 `Board` 메서드다: 새 회차는 `first_step()`(작성 중을 쓰면 작성 중, 아니면 취합 중, `periods.save_draft`), 기간은 `editable()`(작성 중, 그리고 작성 중을 안 쓰면 취합 중에서도), 생성은 `generate_from()`(마감을 쓰면 마감, 아니면 취합 중) 또는 생성됨에서, "다른 상태로 옮기기"는 `move_targets()`(켠 배포 전 단계끼리, 끈 단계에 남은 회차도 켠 단계로. `periods.move` 는 배포됨 → 같은 상태 → `move_targets` 순으로 검사한다). 회차 화면 버튼 글자는 단계 이름에서 나온다(`step_buttons`: "취합 중" → [취합 열기]·[취합 마감], 장중관제가 있으면 [장중관제 생성]·[재생성], 없으면 생성됨 이름 끝의 "됨"을 뗀 말("됨"으로 끝나지 않으면 이름 그대로, 예: [확정]), 취합 중 이름이 " 중"으로 끝나지 않으면 열기·마감은 "'<이름>'(으)로" 꼴, 생성됨에서 옮길 곳이 하나뿐이면 상자 대신 [확정 취소] 같은 버튼). 바꿀 수 있는 이름 뒤 조사는 `shifts.josa` 로 고르고, 확인창(인라인 JS) 안의 이름 글은 `escapejs` 로 넣는다. 마감을 안 쓰는 근무표는 취합 중 회차 화면에 부서마다 [표 입력] 버튼과 생성 버튼이 나란히 있다. 1단계에서 "장중관제가 있다"는 임시 기준으로 정한다: 마감을 쓰는 근무표는 [장중관제 생성]·[재생성]·[생성 방식](지금 글 그대로)·배정 횟수 표, 마감을 안 쓰는 근무표는 관제 정의·배정이 남아 있어도 [확정]·[확정 취소]만(main 과 같은 화면).
     - **1단계 임시 기준** `boards.legacy_admin_entry(board)`(= 마감을 안 쓰는 근무표): 옛 직접 입력 근무표의 문구·확인창(기간 줄이기·[확정]·[확정 취소])·채우기 버튼·빈 평일 경고(막지 않음, 빈 평일이 있으면 첫 [표 입력]이 진한 버튼)·입력 현황 숨김·글 도움말, 입력 그룹 자동 생성과 부서 폼의 입력 담당자 금지를 지금처럼 고른다. 마감을 쓰는 근무표는 빈 평일이 있으면 생성을 막는다. 버튼 글자·[생성 방식]·[재생성]·배정 횟수 표도 이 기준으로 고른다. 2단계에서 화면·서비스 자리를(그때부터 켜진 장중관제 정의라는 데이터 기준), 3단계에서 입력 그룹 자리와 함수를 지운다.
   ```

5. `docs/ARCHITECTURE.md`

   찾을 글:
   ```text
   직접 입력 근무표의 입력 중 회차에는 주마다 **[2주 전 기준으로 채우기]**
   ```
   바꿀 글:
   ```text
   마감을 안 쓰는 근무표(1단계 임시 기준)의 취합 중 회차에는 주마다 **[2주 전 기준으로 채우기]**
   ```

6. `docs/ARCHITECTURE.md`

   찾을 글:
   ```text
   - **생성**(`generator.py`, `services/generate.py`): 그 근무표 부서마다 평일이 다 차야 한다(IT = 4개 부서). 생성은 두 가지를 한다.
   ```
   바꿀 글:
   ```text
   - **생성**(`generator.py`, `services/generate.py`): 마감을 쓰는 근무표는 그 근무표 부서마다 평일이 다 차야 한다(IT = 4개 부서. 마감을 안 쓰는 근무표는 빈 평일을 경고만 한다, 1단계 임시 기준). 장중관제는 그 회차 출근 행이 하나도 없는 날을 빼고 만든다. 생성은 두 가지를 한다.
   ```

7. `docs/ARCHITECTURE.md`

   찾을 글:
   ```text
   직접 입력 근무표 관리자에게는 영상 없이 글 도움말(`help.TEXTS`·`STEPS["direct"]`)이 하나 더 보인다.
   ```
   바꿀 글:
   ```text
   마감을 안 쓰는 근무표의 관리자에게는 영상 없이 글 도움말(`help.TEXTS`·`STEPS["direct"]`, 1단계 임시 기준)이 하나 더 보인다.
   ```

8. `docs/OVERVIEW.md`

   찾을 글:
   ```text
   - 직접 입력 근무표(시장운영실처럼 관리자가 출근표를 직접 넣는 팀)는 **입력 중 → 확정 → 배포됨**:
   ```
   바꿀 글:
   ```text
   - 작성 중·마감 단계를 끈 근무표(시장운영실처럼 관리자가 출근표를 직접 넣는 팀)는 **입력 중 → 확정 → 배포됨**(단계를 켜고 끄는 것과 단계 이름은 근무표 설정):
   ```

9. `docs/OVERVIEW.md`

   찾을 글:
   ```text
   (직접 입력 근무표는 입력 중 → 확정 → 배포됨)
   ```
   바꿀 글:
   ```text
   (근무표마다 작성 중·마감을 끌 수 있고 단계 이름을 정한다. 시장운영실은 입력 중 → 확정 → 배포됨)
   ```

10. `docs/DEVELOPMENT.md`

   찾을 글:
   ```text
   - 설정은 `config.test_settings`(pytest 가 알아서 쓴다). 테스트는 `.env` 를 읽지 않고 임시 `data/` 를 쓴다.
   ```
   바꿀 글:
   ```text
   - 설정은 `config.test_settings`(pytest 가 알아서 쓴다). 테스트는 `.env` 를 읽지 않고 임시 `data/` 를 쓴다.
   - `tests/test_snapshots.py` 는 회차·입력 표·근무표·도움말 화면의 본문을 `tests/snapshots/*.html` 기준과 비교한다(메뉴·공백·CSRF·회차 번호는 빼고). 화면을 일부러 바꾼 PR 만 `DUTY_SNAPSHOT_WRITE=1 .venv/bin/pytest -q tests/test_snapshots.py` 로 다시 쓴다(다시 쓴 실행은 일부러 실패한다. 변수 없이 다시 돌려 통과를 본다). `git diff tests/snapshots/` 의 바뀐 줄을 PR 에서 리뷰한다.
   ```

11. `docs/OPERATIONS.md`

   찾을 글:
   ```text
   - 만드는 것: 근무표(관리자 직접 입력)와 관리 그룹,
   ```
   바꿀 글:
   ```text
   - 만드는 것: 근무표(작성 중·마감 끔, 단계 입력 중 → 확정 → 배포됨)와 관리 그룹,
   ```

12. `docs/OPERATIONS.md`

   찾을 글:
   ```text
   - **근무표는 지울 수 없고 코드·입력 방식은 저장한 뒤 바꿀 수 없다.**
   ```
   바꿀 글:
   ```text
   - **근무표는 지울 수 없고 코드·회차 단계는 저장한 뒤 바꿀 수 없다**(회차 단계는 다음 업데이트에서 열린다).
   ```

13. `docs/OPERATIONS.md`

   찾을 글:
   ```text
   | 입력 방식 | 관리자 직접 입력 | 근무표 관리자가 출근표를 직접 넣는다(입력 중 → 확정 → 배포됨). "부서별 취합"은 IT 처럼 부서 담당자가 넣는 방식. 저장 뒤 못 바꾼다 |
   ```
   바꿀 글:
   ```text
   | 작성 중 단계 사용 / 마감 단계 사용 | 둘 다 끈다 | "회차 단계" 묶음. 끄면 그 단계를 건너뛰고 근무표 관리자가 출근표를 직접 넣는다(IT 는 둘 다 켬, 부서 담당자가 넣는다). 저장 뒤 못 바꾼다 |
   | 단계 이름 | 취합 중 이름 "입력 중", 생성됨 이름 "확정"(나머지 그대로) | 회차 화면 단계·버튼 이름이 된다("입력 중"·[확정]·[확정 취소]). 다섯 이름은 서로 달라야 한다. 저장 뒤 못 바꾼다 |
   ```

14. `docs/OPERATIONS.md`

   찾을 글:
   ```text
   직접 입력 근무표에는 부서를 **하나만** 둔다(둘째를 만들면 "직접 입력 근무표에는 부서를 하나만 둘 수 있습니다.").
   ```
   바꿀 글:
   ```text
   (지운다: 이 줄과 뒤의 빈 줄)
   ```

15. `docs/OPERATIONS.md`

   찾을 글:
   ```text
   | 입력 담당자 | 비워 둔다 | 직접 입력 근무표는 근무표 관리자가 입력한다(고르면 오류) |
   ```
   바꿀 글:
   ```text
   | 입력 담당자 | 비워 둔다 | 마감을 끈 근무표는 근무표 관리자가 입력한다(고르면 오류) |
   ```

16. `docs/OPERATIONS.md`

   찾을 글:
   ```text
   | 부서 이름 | 부서 화면 "이름" | 부서 이름만 바뀐다(직접 입력 근무표의 부서는 입력 그룹이 없다) |
   ```
   바꿀 글:
   ```text
   | 부서 이름 | 부서 화면 "이름" | 부서 이름만 바뀐다(마감을 끈 근무표의 부서는 입력 그룹이 없다) |
   ```

17. `docs/OPERATIONS.md`

   찾을 글:
   ```text
   | 코드·입력 방식, 부서의 근무표·코드 | — |
   ```
   바꿀 글:
   ```text
   | 코드·회차 단계, 부서의 근무표·코드 | — |
   ```

18. `docs/OPERATIONS.md`

   찾을 글:
   ```text
   - nginx 를 켜 둔 서버는 이 묶음을 마친 뒤
   ```
   바꿀 글:
   ```text
   - **근무표 통합 1단계로 올릴 때 (한 번, 공지 없음)**: `migrate` 가 0023 을 적용한다. 보이는 변화는 없다(IT·시장운영실 회차 화면·버튼·문구·알림 그대로). 관리 화면 "근무표"의 "입력 방식" 칸이 "회차 단계"(작성 중 단계 사용·마감 단계 사용·단계 이름 다섯)로 바뀐다(저장된 근무표에서는 읽기 전용): 옛 직접 입력 근무표는 둘 다 끔·취합 중 "입력 중"·생성됨 "확정", IT 는 둘 다 켬·지금 이름 그대로. 입력 그룹은 새로 생기지 않는다. "직접 입력 근무표는 부서 하나" 제한이 없어진다.
     - 업그레이드 전 확인(읽기 전용, 멈출 일은 없다): 근무표별 입력 방식과 상태별 회차 수를 적어 둔다(업그레이드 뒤 대조용).
       `sudo -u duty sqlite3 -readonly data/db.sqlite3 "SELECT b.code, b.input_mode, p.status, COUNT(p.id) FROM duty_board b LEFT JOIN duty_period p ON p.board_id = b.id GROUP BY 1, 2, 3;"`
     - 업그레이드 뒤 대조(읽기 전용): 근무표·상태·회차 수가 위와 같고, `direct` 였던 근무표는 `0|0|입력 중|확정`, `collect` 였던 근무표는 `1|1|취합 중|생성됨` 이어야 한다.
       `sudo -u duty sqlite3 -readonly data/db.sqlite3 "SELECT b.code, b.use_draft, b.use_close, b.step_collecting, b.step_generated, p.status, COUNT(p.id) FROM duty_board b LEFT JOIN duty_period p ON p.board_id = b.id GROUP BY 1, 2, 3, 4, 5, 6;"`
     - 업그레이드 전 확인 ②(읽기 전용, 참고용): 장중관제 정의를 켜 두었거나 관제 배정이 남은 직접 입력 근무표. 1단계에서는 이런 근무표도 지금 화면 그대로다([확정]·[확정 취소]만). 2단계(데이터 기준)부터 경우에 따라 달라진다 — 켜진 관제 정의 수가 0이 아니면 [장중관제 생성]·[재생성]·[생성 방식]·배정 횟수 표가 생기고, 정의는 0이고 관제 배정 행만 남았으면 버튼은 그대로이고 배정 횟수 표와 [확정 취소] 확인창 글만 바뀐다. 여기서는 결과를 참고로 적어 두기만 하고, 2단계를 올리기 직전에 같은 확인을 다시 돌려(작성 중·마감을 둘 다 끈 근무표 기준) 그때 값으로 공지와 진행을 정한다(아래 "근무표 통합 2단계로 올릴 때"). 근무표마다 `코드|켜진 관제 정의 수|관제 배정 행 수`, 모두 0 이면 해당 없음.
       `sudo -u duty sqlite3 -readonly data/db.sqlite3 "SELECT b.code, (SELECT COUNT(*) FROM duty_boardshift s WHERE s.board_id = b.id AND s.active = 1 AND s.key LIKE 'slot%'), (SELECT COUNT(*) FROM duty_dutyassignment a JOIN duty_period p ON p.id = a.period_id WHERE p.board_id = b.id AND a.cell LIKE 'slot%') FROM duty_board b WHERE b.input_mode = 'direct';"`
     - 되돌리기는 기본이 위 "롤백"(코드 되돌리기 + 업그레이드 전 백업 `restore`)이다. `migrate` 거꾸로를 쓰려면 **코드를 되돌리기 전에**(새 코드 그대로) `sudo -u duty .venv/bin/python manage.py migrate duty 0022` 를 먼저 하고, 그다음 롤백 순서대로 `git checkout <적어 둔 버전>` 을 한다(이때 `restore` 는 하지 않는다). 옛 코드에는 0023 파일이 없어 코드를 먼저 되돌리면 거꾸로 돌지 않는다. 0023 은 입력 방식으로 나타낼 수 없는 근무표(단계 하나만 끔, 이름을 고침)가 있으면 그 코드를 알려 주며 거꾸로 돌기를 거부한다. 헷갈리면 `restore` 만 쓴다.
   - nginx 를 켜 둔 서버는 이 묶음을 마친 뒤
   ```

19. `docs/PRINCIPLES.md` "결정 기록" 표 맨 끝에 한 줄:

   ```text
   | 2026-11-17 | 근무표의 입력 방식 갈래(`input_mode` collect/direct)를 지우고 회차 단계를 근무표 설정 데이터로 둔다(작성 중·마감 단계 사용, 다섯 단계 화면 이름, 규칙은 쿼리 없는 `Board` 메서드, 버튼 이름은 단계 이름에서). 1단계는 임시 기준 하나(`legacy_admin_entry` = 마감을 안 쓰는 근무표)로 보이는 동작을 그대로 두고 main 기준 화면 스냅샷(`tests/snapshots/`)으로 지킨다. 관리 화면의 단계 칸은 1·2단계에서 만들 때만 고친다(입력 그룹 기준이 3단계까지 남아서, 3단계에서 연다). 버튼 글자는 단계 이름에서 만들고 비거나 겹치는 이름은 막는다. 1단계의 버튼 글자·[생성 방식]·[재생성]·배정 횟수 표는 임시 기준으로 고른다(관제 이력이 남은 직접 입력 근무표도 main 과 같은 화면). "직접 입력 근무표는 부서 하나" 규칙은 없앤다 | 사용자 지적: 부서마다 따로 구현된 느낌이라 다른 부서가 늘면 갈래가 늘어 유지보수가 어렵다. 업그레이드한 날은 아무것도 달라 보이지 않아야 한다(변화를 싫어하는 사용자). 공통 규칙(2단계)과 늦은 입력 그룹(3단계)은 따로 켠다 |
   ```

- [ ] **Step 2: 바뀐 곳을 확인한다**

Run: `git grep -n -E "input_mode|직접 입력" -- docs/ARCHITECTURE.md docs/OVERVIEW.md docs/DEVELOPMENT.md`
Expected: `ARCHITECTURE.md` "회차" 절 두 줄(0023 이 옛 `input_mode=direct` 근무표에 넣은 값, "1단계 임시 기준"의 "옛 직접 입력 근무표")과 "보안" 절의 "chat_id 직접 입력 없음"(다른 뜻)만. `git grep -n "직접 입력" -- docs/OPERATIONS.md` 는 "근무표 추가하기" 4·5단계의 도움말 제목 "직접 입력 근무표 운영"(2단계에서 바뀐다)과 지난·이번 업그레이드 메모에만 나온다.

Run: `.venv/bin/pytest -W error -q`
Expected: `1303 passed`(문서만 바꿨다)

- [ ] **Step 3: 업그레이드 확인 쿼리를 임시 DB 에서 돌려 본다(실DB 는 열지 않는다)**

```bash
W=$(mktemp -d); export DUTY_ENV_FILE= DUTY_DEBUG=1 DUTY_DATA_DIR=$W/data
.venv/bin/python manage.py migrate -v0 duty 0022
sqlite3 -readonly $W/data/db.sqlite3 "SELECT b.code, b.input_mode, p.status, COUNT(p.id) FROM duty_board b LEFT JOIN duty_period p ON p.board_id = b.id GROUP BY 1, 2, 3;"
sqlite3 -readonly $W/data/db.sqlite3 "SELECT b.code, (SELECT COUNT(*) FROM duty_boardshift s WHERE s.board_id = b.id AND s.active = 1 AND s.key LIKE 'slot%'), (SELECT COUNT(*) FROM duty_dutyassignment a JOIN duty_period p ON p.id = a.period_id WHERE p.board_id = b.id AND a.cell LIKE 'slot%') FROM duty_board b WHERE b.input_mode = 'direct';"
.venv/bin/python manage.py migrate -v0
sqlite3 -readonly $W/data/db.sqlite3 "SELECT b.code, b.use_draft, b.use_close, b.step_collecting, b.step_generated, p.status, COUNT(p.id) FROM duty_board b LEFT JOIN duty_period p ON p.board_id = b.id GROUP BY 1, 2, 3, 4, 5, 6;"
rm -rf $W; unset DUTY_ENV_FILE DUTY_DEBUG DUTY_DATA_DIR
```
Expected: `it|collect||0`, (확인 ② 는 직접 입력 근무표가 없어 아무것도 안 나옴), `it|1|1|취합 중|생성됨||0`

- [ ] **Step 4: 커밋**

```bash
git add docs/
git commit -m "$(cat <<'EOF'
docs: 근무표 통합 1단계(단계 설정 데이터, 0023 업그레이드 메모와 확인 쿼리, 화면 스냅샷)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

- [ ] **Step 5: 1단계 PR**

전체 테스트 결과(`1303 passed`, 경고 0)와 `makemigrations --check` 결과를 확인한 **뒤에** 따로 push·PR 을 만든다(결과 확인과 머지를 한 명령으로 잇지 않는다). PR 본문: 보이는 변화 없음(첫 커밋의 main 기준 스냅샷 `tests/snapshots/` 가 마지막 커밋까지 그대로 통과), 관리 화면 근무표 "입력 방식" → "회차 단계"(저장된 근무표는 1·2단계 내내 읽기 전용, 만들 때 버튼 글자 검사), "부서 하나" 제한 삭제, 마이그레이션 0023 과 업그레이드 전 확인 ①②·뒤 대조 쿼리, 롤백 순서(OPERATIONS), 거꾸로 규칙, 공지 없음. Codex 최종 리뷰를 받은 뒤 머지한다.

---

# 2단계 PR: 공통 규칙 켜기 (마이그레이션 없음, IT 에 보이는 변화)

브랜치: `feat/board-common-rules`(1단계가 머지된 main 에서). PR 제목: `feat: 모든 근무표에 같은 회차 규칙(빈 평일 경고만·채우기·입력 현황·단계 이름 문구, 근무표 통합 2단계)`. **운영 반영은 IT 근무표에 취합 중·마감·생성됨 회차가 없을 때**(설계 10.3·10.4, OPERATIONS 확인 쿼리).

### Task 7: 서비스 공통 규칙(빈 평일 경고만·채우기 모든 근무표·단계 이름 문구)

> 범위: 서비스. 설계 6.1 "단계" 열 2 의 서비스 자리(`periods.py:21-26`·`63-70`, `generate.py:21-24`·`29-43`, `collect.py:184`, `publish.py:9,26`)에서 `legacy_admin_entry` 를 지운다. 화면은 Task 8(아직 `legacy` 기준이 남은 화면은 Task 8 까지 그대로 보인다).

**Files:**
- Modify: `duty/services/periods.py` — `_names` 더하기, `save_draft` 기간 오류, `move` 검사
- Modify: `duty/services/generate.py` — import, `run_generation` 앞부분(상태 오류·빈 평일 경고), `slots` 계산을 위로
- Modify: `duty/services/collect.py` — `_require_collecting` 로 나누고 `fill_week` 가 부른다
- Modify: `duty/services/publish.py` — `_validate` 오류
- Modify: `duty/shifts.py` — `lunch_defs` 앞에 `day_spans`(이어진 평일 묶기)
- Modify(테스트, 옛 문구 → 새 문구): `tests/test_board_steps.py`, `tests/test_direct_periods.py`, `tests/test_generate.py`, `tests/test_fill.py`, `tests/test_views_direct.py`, `tests/test_period_lifecycle.py`

**Interfaces:**
- Consumes: `Board.step_name/steps/editable/generate_from/step_buttons`, `periods.missing_dates(period) -> dict[code, list[date]]`, `generate._days(days) -> "11/19, 11/20"`
- Produces(동작·문구):
  - `periods._names(board, statuses) -> str`: 켠 단계 중 `statuses` 에 든 것의 이름을 단계 순으로 "·" 로 이음
  - `save_draft`: `DutyError(f"기간은 '{_names(board, board.editable())}' 단계에서만 고칠 수 있습니다.")`(IT "'작성 중'", 운영팀 "'입력 중'")
  - `move`: 검사 순서는 그대로(배포됨 → 같은 상태 → `move_targets`). `move_targets` 밖 글 중 대상이 `MOVABLE` 안인 경우만 `f"'{_names(board, MOVABLE)}'(으)로만 옮길 수 있습니다."`(IT "'작성 중·취합 중·마감'", 운영팀 "'입력 중'"), `MOVABLE` 밖은 "옮길 수 없는 상태입니다." 그대로
  - `shifts.day_spans(days) -> str`: "11/16~11/20, 11/24"(이어진 평일끼리, 금 → 월도 이어진 것으로, 빈 목록은 "")
  - `run_generation`: 상태 오류 `f"'{generate_from 이름}'인 회차만 {step_buttons(관제 있음)['generate']}할 수 있습니다."`(IT "'마감'인 회차만 장중관제 생성할 수 있습니다.", 운영팀 "'입력 중'인 회차만 확정할 수 있습니다."). 빈 평일은 막지 않고 `out.warnings[0] = "출근표가 비어 있는 날이 있습니다: <부서 이름> <n>일(<day_spans>), …. 그날 그 부서는 근무자가 없습니다."`(부서 코드 순, 점심당번 경고보다 앞)
  - `collect._require_collecting(period)`: 취합 중이 아니면 `DutyError("<취합 중 이름>인 회차가 아닙니다.")`. `_require_input` 과 `fill_week` 가 부른다(채우기는 모든 근무표)
  - `publish._validate`: `f"'{생성됨 이름}'인 회차만 배포할 수 있습니다."`

- [ ] **Step 1: 테스트를 새 규칙·문구로 고친다(실패 테스트)**

`tests/test_generate.py` — `test_missing_department_dates_block_generation`·`test_wrong_status` 를:
```python
def test_missing_department_dates_only_warn(closed_period):
    """빈 평일은 IT 도 막지 않고 경고만(근무표 통합 2단계). 다른 부서 사람이 있는 날은 관제도 채운다."""
    Commute.objects.filter(period=closed_period, member__department="UI", date=date(2026, 11, 13)).delete()
    out = run_generation(closed_period, seed=5)
    assert out.warnings[0] == "출근표가 비어 있는 날이 있습니다: UI 1일(11/13). 그날 그 부서는 근무자가 없습니다."
    assert DutyAssignment.objects.filter(period=closed_period, date=date(2026, 11, 13)).count() == 10


def test_wrong_status(closed_period):
    closed_period.status = S.COLLECTING
    closed_period.save()
    with pytest.raises(DutyError, match="'마감'인 회차만 장중관제 생성할 수 있습니다"):
        run_generation(closed_period)
```

`tests/test_direct_periods.py` — 문구 단언만 바꾼다:
- `match="기간은 입력 중에만 수정할 수 있습니다"` → `match="기간은 '입력 중' 단계에서만 고칠 수 있습니다"`
- `test_collect_dates_still_draft_only` 의 `match="작성 중"` → `match="기간은 '작성 중' 단계에서만 고칠 수 있습니다"`
- `assert out.warnings[0] == "입력하지 않은 평일이 있습니다(그날은 근무자가 없습니다): 11/20"` → `assert out.warnings[0] == "출근표가 비어 있는 날이 있습니다: 운영 1일(11/20). 그날 그 부서는 근무자가 없습니다."`
- `test_confirm_only_from_input_or_confirmed` 의 `match="입력 중인 회차만 확정할 수 있습니다"` → `match="'입력 중'인 회차만 확정할 수 있습니다"`
- `match="마감된 회차만 생성할 수 있습니다"` → `match="'마감'인 회차만 장중관제 생성할 수 있습니다"`
- `match="입력 중으로만"` → `match=r"'입력 중'\(으\)로만 옮길 수 있습니다"`
- `test_confirm_with_slot_def_and_empty_weekday` 의 `out.warnings[0].endswith("11/20")` → `"운영 1일(11/20)" in out.warnings[0]`

`tests/test_period_lifecycle.py::test_move_message_for_board_without_draft_and_close` 의 마지막 단언을
```python
    assert str(e.value) == "'입력 중'(으)로만 옮길 수 있습니다."  # 근무표 통합 2단계: 켠 단계 이름으로
```
로(Task 1 의 나머지 세 글은 그대로).

`tests/test_fill.py::test_fill_errors` 의 마지막 네 줄(`it = Period.objects.create(…)` 부터 `collect.fill_week(it, mems, …)` 까지)을:
```python
    p.status = S.GENERATED  # 채우기는 입력을 받는 동안만(모든 근무표, 근무표 통합 2단계)
    with pytest.raises(DutyError, match="입력 중인 회차가 아닙니다"):
        collect.fill_week(p, dept, {}, d(11, 16), collect.FILL_1W)


def test_fill_works_on_it_board(it_board):
    """IT(마감을 쓰는 근무표)도 취합 중이면 채운다(근무표 통합 2단계)."""
    it = Period.objects.create(board=it_board, name="it", start_date=d(11, 16), end_date=d(11, 20), status=S.COLLECTING)
    mems = Department.objects.create(code="MEMS", name="매칭엔진실", shifts="dawn,normal,dinner", board=it_board)
    assert collect.fill_week(it, mems, {}, d(11, 16), collect.FILL_1W) == {}
```
로.

`tests/test_views_direct.py`:
- `test_confirm_shows_empty_day_warning` 의 `"입력하지 않은 평일이 있습니다(그날은 근무자가 없습니다): 11/20"` → `"출근표가 비어 있는 날이 있습니다: 운영 1일(11/20). 그날 그 부서는 근무자가 없습니다."`
- `test_publish_error_names_confirm` 의 `match="확정한 회차만 배포할 수 있습니다"` → `match="'확정'인 회차만 배포할 수 있습니다"`

`tests/test_board_steps.py`:
- `test_generate_from_rule` 의 매개변수를:
```python
@pytest.mark.parametrize("flags,ok,refused,msg", [
    ((False, True), X, C, "'마감'인 회차만 장중관제 생성할 수 있습니다"),
    ((True, False), C, X, "'취합 중'인 회차만 장중관제 생성할 수 있습니다"),
])
```
- `test_move_checks_in_order` 의 첫 매개변수 줄을
```python
    ((False, True), G, D, "'취합 중·마감'(으)로만 옮길 수 있습니다."),  # 끈 단계로: 켠 단계 이름만
```
로(나머지 두 줄 그대로).
- import 줄 `from duty.shifts import josa` 를 `from duty.shifts import day_spans, josa` 로.
- `test_slots_skip_only_days_without_any_rows` 의 docstring 을 `"""관제는 출근 행이 하나도 없는 날만 뺀다. 한 부서만 빈 날(목·금)은 다른 부서 사람으로 채운다(경고는 부서별)."""` 로, 경고 단언을
```python
    assert out.warnings[0] == "출근표가 비어 있는 날이 있습니다: 단계STB 2일(11/19~11/20). 그날 그 부서는 근무자가 없습니다."
```
로.
- `test_fill_follows_legacy_rule` 와 `test_publish_message_follows_legacy_rule` 두 함수(매개변수 데코레이터 포함)를 아래 하나로 바꾼다:
```python
def test_messages_use_step_names(it_board):
    """오류 글은 그 근무표의 단계 이름을 쓴다(근무표 통합 2단계)."""
    b = board_with(True, True, step_draft="준비", step_generated="만듦")
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    with pytest.raises(DutyError, match="'만듦'인 회차만 배포할 수 있습니다"):
        publish.publish(p, MON)
    with pytest.raises(DutyError, match="기간은 '준비' 단계에서만 고칠 수 있습니다"):
        periods.save_draft(p)


def test_day_spans():
    """긴 날짜 목록은 이어진 평일끼리 묶는다(금 → 월도 이어진 것으로)."""
    days = [date(2026, 11, d) for d in (16, 17, 18, 19, 20, 23, 25)]
    assert day_spans(days) == "11/16~11/23, 11/25" and day_spans([MON]) == "11/16" and day_spans([]) == ""
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_steps.py tests/test_direct_periods.py tests/test_generate.py tests/test_fill.py tests/test_views_direct.py tests/test_period_lifecycle.py`
Expected: FAIL — `test_board_steps.py` 는 모음 오류 `ImportError: cannot import name 'day_spans'`, 나머지 파일은 새 문구·규칙 테스트가 실패(옛 문구가 나오거나 `DutyError: 출근표가 비어 있는 날짜가 있습니다: UI 1일`, `채우기는 직접 입력 근무표에서만 씁니다`)

- [ ] **Step 3: 서비스를 고친다**

`duty/services/periods.py` — `@transaction.atomic` + `def save_draft(` 바로 앞에:
```python
def _names(board, statuses) -> str:
    """켠 단계 중 statuses 에 든 것의 이름(단계 순). 끈 단계 이름은 오류 글에 나오지 않는다(설계 6.1)."""
    return "·".join(board.step_name(s) for s in board.steps() if s in statuses)


```
`save_draft` 의 기간 오류 두 줄(`raise DutyError("기간은 입력 중에만 …" if boards.legacy_admin_entry(board)` / `else …`)을
```python
        raise DutyError(f"기간은 '{_names(board, board.editable())}' 단계에서만 고칠 수 있습니다.")
```
로. `move` 의 `move_targets` 검사 글을
```python
        raise DutyError("옮길 수 없는 상태입니다." if to not in MOVABLE
                        else f"'{_names(period.board, MOVABLE)}'(으)로만 옮길 수 있습니다.")
```
로.

`duty/shifts.py` 의 `lunch_defs` 바로 앞에(긴 빈 날 목록을 줄인다, 검토 지적):
```python
def day_spans(days) -> str:
    """날짜들을 이어진 평일끼리 묶어 '11/16~11/20, 11/24' 꼴로(금 → 월도 이어진 것으로). 긴 빈 날 목록을 줄인다."""
    runs: list[list[date]] = []
    for d in sorted(days):
        if runs and d == runs[-1][1] + timedelta(days=3 if runs[-1][1].weekday() == 4 else 1):
            runs[-1][1] = d
        else:
            runs.append([d, d])
    return ", ".join(f"{a.month}/{a.day}" + (f"~{b.month}/{b.day}" if b != a else "") for a, b in runs)


```

`duty/services/generate.py` — import 세 줄(`from ..shifts import LUNCH, by_key, shift_defs, slot_defs` 에 `day_spans` 를 더한다):
```python
from ..models import Commute, Department, DutyAssignment, Period, User
```
```python
from .periods import missing_dates, record
```
```python
from ..shifts import LUNCH, by_key, day_spans, shift_defs, slot_defs
```
`run_generation` 의 `period.refresh_from_db()` 다음부터 `if seed is None:` 앞까지를:
```python
    board = period.board
    active = boards.active_defs(board)
    slots = slot_defs(active)  # 인덱스 i ↔ 칸 키 slots[i].key. 꺼진 관제는 생성하지 않는다
    if period.status not in {board.generate_from(), S.GENERATED}:  # 마감을 쓰면 마감에서, 아니면 취합 중에서
        raise DutyError(f"'{board.step_name(board.generate_from())}'인 회차만 "
                        f"{board.step_buttons(bool(slots))['generate']}할 수 있습니다.")
    holidays.sync(perms.today())  # 작업자가 꺼져 있어도 휴장일 표가 비어 있지 않게
    warnings = []
    missing = missing_dates(period)  # 빈 평일은 모든 근무표에서 막지 않고 경고로만 알린다(설계 6.1)
    if missing:
        names = dict(Department.objects.filter(board=board).values_list("code", "name"))
        detail = ", ".join(f"{names[code]} {len(ds)}일({day_spans(ds)})" for code, ds in missing.items())
        warnings.append(f"출근표가 비어 있는 날이 있습니다: {detail}. 그날 그 부서는 근무자가 없습니다.")
```
로 바꾸고, 아래쪽의
```python
    active = boards.active_defs(period.board)
    slots = slot_defs(active)  # 인덱스 i ↔ 칸 키 slots[i].key. 꺼진 관제는 생성하지 않는다
```
두 줄을 지운다(`if slots:` 가 바로 `slot_dates` 다음에 오게).

`duty/services/collect.py` — `_require_input` 의 마지막 두 줄(`if period.status != … COLLECTING:` / `raise …`)을 `    _require_collecting(period)` 로 바꾸고 그 아래에:
```python


def _require_collecting(period: Period) -> None:
    if period.status != Period.Status.COLLECTING:
        raise DutyError(f"{period.board.step_name(Period.Status.COLLECTING)}인 회차가 아닙니다.")  # 취합 중 / 입력 중
```
`fill_week` 의
```python
    if not boards.legacy_admin_entry(period.board):  # 1단계 임시 기준, 2단계에서 모든 근무표
        raise DutyError("채우기는 직접 입력 근무표에서만 씁니다.")
```
를 `    _require_collecting(period)  # 모든 근무표, 입력을 받는 동안만(설계 6.1)` 로.

`duty/services/publish.py` — `_validate` 의 두 줄 오류를
```python
        raise DutyError(f"'{period.board.step_name(S.GENERATED)}'인 회차만 배포할 수 있습니다.")
```
로.

- [ ] **Step 4: 통과를 확인한다**

Run: `git grep -n legacy_admin_entry -- duty/services/periods.py duty/services/generate.py duty/services/collect.py duty/services/publish.py`
Expected: 아무것도 안 나온다.
Run: `.venv/bin/pytest -W error -q && DUTY_DEBUG=1 DUTY_ENV_FILE= DUTY_DATA_DIR=$(mktemp -d) .venv/bin/python manage.py makemigrations duty --check --dry-run`
Expected: `1301 passed`(채우기 기준 테스트 3개·배포 문구 2개 → 문구 1개, IT 채우기 1개, `day_spans` 1개), "No changes detected in app 'duty'". 스냅샷은 아직 그대로 통과한다(화면은 Task 8).

- [ ] **Step 5: 커밋**

```bash
git add duty/services/periods.py duty/services/generate.py duty/services/collect.py duty/services/publish.py tests/
git commit -m "$(cat <<'EOF'
feat: 빈 평일은 모든 근무표에서 경고만, 채우기는 모든 근무표, 회차 오류 글은 켠 단계 이름으로(근무표 통합 2단계)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

---

### Task 8: 화면 공통 규칙(데이터 기준 장중관제·⚠ 줄·빈 날 확인창·입력 현황·나가는 확인창·끈 단계 안내·입력 표 글)

> 범위: 회차 화면·입력 표. 설계 6.1 "단계" 열 2 의 화면 자리(`views/collect.py:66-72`, `views/manage.py:84-93`·`137-139`, `period_detail.html:5-7`·`18-35`·`36-38,113-131`·`40-41`·`63-67`·`76`, `collect_table.html:4,5,9`)와 5.4 `leave_generated_confirm`(그 회차에 실제로 있는 배정으로). 1단계의 임시 기준 갈래(버튼 글자·[재생성]·[생성 방식]·배정 횟수 표)를 **켜진 장중관제 정의라는 데이터 기준**으로 바꾸고, 생성 방식 글을 관제 정의에서 만든다(`shifts.gen_help`, IT 글은 그대로). 확인창 글은 모두 `escapejs`. 스냅샷을 다시 쓰고 바뀐 줄을 리뷰한다. 도움말은 Task 9. 관리 화면 단계 칸은 그대로 읽기 전용(3단계).

**Files:**
- Modify: `duty/shifts.py` — `josa` 뒤에 `gen_help`
- Modify: `duty/views/manage.py` — import, `_empty_confirm`·`_leave_what`, `_render_detail` 전체, `period_action` 성공 문구
- Modify: `duty/templates/duty/period_detail.html` — 기간 폼 확인창, 생성 버튼 세 곳, [생성 방식] 버튼 조건, ⚠ 줄·끈 단계 안내, 옮기기 상자(펼침·확인창·설명), 입력 현황, 배정 횟수 표 조건, 생성 방식 상자(조건·글), 스타일 두 줄
- Modify: `duty/views/collect.py` — `_render_table` 컨텍스트
- Modify: `duty/templates/duty/collect_table.html` — 4·5·9번째 줄
- Modify: `duty/services/periods.py` — 쓰지 않게 된 `empty_days` 지우기
- Modify(테스트): `tests/test_board_steps.py`, `tests/test_fill.py`, `tests/test_views_direct.py`
- Modify(생성 파일): `tests/snapshots/*.html`(다시 쓴다, 17개가 바뀐다)

**Interfaces:**
- Consumes: Task 7 서비스와 `shifts.day_spans`·`josa`, `periods.missing_dates`, `Board.step_buttons`·`steps`·`generate_from`, `shifts.is_slot_cell`·`LUNCH`·`by_key`·`slot_defs`·`shift_defs`
- Produces:
  - `shifts.gen_help(defs: list[Def]) -> dict | None`: 키 `count`·`start`·`end`(time)·`types`(자격 구분 "·"로 이음, 없으면 "")·`who`(`types` 또는 "사람")·`whom`(`who` + 을/를)·`rule`(자격 문장: 가장 많은 칸의 자격 근무조는 "나머지 칸", 다른 칸은 시작 시각으로). 관제 정의가 없으면 `None`. IT 정의에서 지금 글 그대로("10칸(08:30~18:00)에 개발자를", "08:30 칸은 정상, 17:00 칸은 석식교대, 나머지 칸은 정상·석식교대 둘 다 됩니다.")
  - 화면 갈래(2단계): `buttons = board.step_buttons(bool(켜진 관제 정의))`, `gen_help = gen_help(켜진 정의)`, 배정 횟수 표는 `counts` 가 있으면(관제 배정이 남은 회차도)
  - `views.manage._empty_confirm(missing, has_slots) -> str`: "출근표가 비어 있는 부서가 있는 날이 {N}일 있습니다. 그날 그 부서는 근무자가 없고, 아무 부서도 넣지 않은 날은 장중관제도 만들지 않습니다. 계속할까요?"(관제가 없으면 "…근무자가 없습니다. 계속할까요?"), N = 어느 부서든 빈 평일 수. 템플릿 변수 `empty_confirm`(빈 날이 없으면 "" → 생성 버튼에 확인창 없음)
  - `views.manage._leave_what(period, active) -> str`: 생성됨 회차는 그 회차의 `DutyAssignment`(관제 칸·점심당번 유무), 그 밖은 켜진 정의로 "장중관제·점심당번"·"장중관제"·"점심당번"·"". 템플릿 변수 `leave_what`·`leave_generated_confirm`("생성 결과(<leave_what> 배정)가 지워지고 출근표는 그대로 남습니다. 계속할까요?", 비면 "출근표는 그대로 남습니다. 계속할까요?")
  - `period_detail.html` 컨텍스트: `legacy`·`empty_days`·`generate_topic`·`undo_confirm` 이 없어지고 `gen_help`, `empty=[(부서 이름, 날 수, day_spans)…]`(켠 단계의 취합 중·마감, 부서 코드 순), `can_generate_now`(지금 상태가 `generate_from()`), `unused_step`, `progress=[(code, 부서 이름, n, m)…]`, `input_depts` 는 늘 채운다. `generated_ro` 는 그대로
  - `collect_table.html` 컨텍스트: `legacy` 대신 `back_link`(그 근무표 관리자)·`collecting`(취합 중 이름), `show_fill = is_open`
  - 생성 성공 문구 "'<생성됨 이름>' 상태로 바꿨습니다. 근무표 화면에는 배포한 뒤에 보입니다."(모든 근무표)

- [ ] **Step 1: 테스트를 새 화면으로 고친다(실패 테스트)**

`tests/test_board_steps.py`:
- import 끝 두 줄(`from duty.shifts import day_spans, josa`, `from tests.it_defs import OPS_STEPS`)을
```python
from duty.shifts import Def, day_spans, gen_help, josa
from tests.it_defs import IT_DEFS, OPS_STEPS
```
로.
- `test_josa` 바로 앞에 생성 방식 문장 단위 테스트 둘(IT 글은 지금 상자 글과 같아야 한다):
```python
def test_gen_help_for_it_defs_matches_old_text():
    assert gen_help(IT_DEFS) == {
        "count": 10, "start": time(8, 30), "end": time(18), "types": "개발자", "who": "개발자", "whom": "개발자를",
        "rule": "08:30 칸은 정상, 17:00 칸은 석식교대, 나머지 칸은 정상·석식교대 둘 다 됩니다."}
    assert gen_help([d for d in IT_DEFS if not d.key.startswith("slot")]) is None


def test_gen_help_for_other_slots():
    defs = [Def("dawn", "이른", time(7), time(16)), Def("slot3", "점검", time(10), time(11), ("dawn",), ("직원",))]
    assert gen_help(defs) == {"count": 1, "start": time(10), "end": time(11), "types": "직원", "who": "직원", "whom": "직원을",
                              "rule": "모든 칸은 이른만 됩니다."}
```
- `test_period_page_follows_steps` 를 아래로 바꾼다(빈 날 확인창·⚠ 줄·입력 현황·나가는 확인창):
```python
def test_period_page_follows_steps(stp):
    b, client = stp
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    Commute.objects.create(period=p, date=MON, member=person("STA"), shift="dawn")
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert body.index(">입력 중<") < body.index(">확정<") < body.index(">배포됨<") and ">마감<" not in body
    assert f'href="/collect/{p.pk}/STA/">표 입력 · 단계STA</a>' in body and ">확정</button>" in body
    # 빈 날이 있을 때만 생성 확인창(날 수 = 어느 부서든 빈 평일), 관제가 없으면 장중관제 문장을 뺀다
    assert "confirm('출근표가 비어 있는 부서가 있는 날이 5일 있습니다. 그날 그 부서는 근무자가 없습니다. 계속할까요?')" in body
    assert ("⚠ 출근표가 비어 있는 날: 단계STA 4일(11/17~11/20) · 단계STB 5일(11/16~11/20). "
            "[확정] 버튼은 누를 수 있지만 그날 그 부서는 근무자가 없습니다.") in body
    assert "단계STB: 0 / 5일" in body and f'<a role="button" class="outline secondary" href="/collect/{p.pk}/STB/">표 입력</a>' in body
    assert 'name="start_date"' in body and "생성 방식" not in body
    p.status = G
    p.save()
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert ">확정 취소</button>" in body and "다른 상태로 옮기기" not in body and "재생성" not in body
    assert "confirm('출근표는 그대로 남습니다. 계속할까요?')" in body  # 이 회차에는 지울 배정이 없다(설계 5.4)
```
- `test_period_page_with_draft_off_and_close_on` 의 끝 세 줄(`p.status = X` … `assert ">장중관제 생성</button>" in client.get(…)`)을 아래로(2단계: 생성 방식 글이 이 근무표의 관제 정의에서 나온다):
```python
    p.status = X
    p.save()
    body = client.get(f"/periods/{p.pk}/").content.decode()  # 2단계: 생성 방식 문장은 이 근무표의 관제 정의에서
    assert ">장중관제 생성</button>" in body and "장중관제 1칸(10:00~11:00)에 직원을 한 명씩" in body
    assert "직원이고 그날 그 칸의 출근조에 있어야 합니다." in body and "모든 칸은 이른만 됩니다." in body
```
- `test_input_table_and_help_follow_legacy_rule` 를 아래 다섯으로 바꾼다(도움말 확인은 Task 9 로):
```python
def test_no_generate_confirm_without_empty_days(stp):
    b, client = stp
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=MON, status=C)
    for code in ("STA", "STB"):
        Commute.objects.create(period=p, date=MON, member=person(code), shift="dawn")
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert f'<form method="post" action="/periods/{p.pk}/action/generate/"><input' in body and "출근표가 비어 있는 날" not in body
    assert "확정할까요" not in body


def test_unused_step_notice(it_board, admin_user, client):
    """끈 단계에 남은 회차는 한 줄로 알리고 옮기기 상자를 펼쳐 둔다(근무표 통합 2단계)."""
    b = board_with(False, True)
    b.admin_group.user_set.add(admin_user)
    client.force_login(admin_user)
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=D)
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert "이 단계는 지금 쓰지 않습니다. 아래 [다른 상태로 옮기기]를 눌러 옮기세요." in body
    assert '<details class="move-box" open>' in body
    p.status = C
    p.save()
    assert "이 단계는 지금 쓰지 않습니다" not in client.get(f"/periods/{p.pk}/").content.decode()


def test_leave_confirm_names_actual_assignments(it_board, admin_user, client):
    """나가는 확인창은 그 회차에 실제로 있는 배정으로 만든다: 관제 정의를 꺼도 남은 관제 배정이 글에 남는다(설계 5.4)."""
    b = board_with(True, True)
    b.admin_group.user_set.add(admin_user)
    client.force_login(admin_user)
    BoardShift.objects.filter(board=b, key="slot0").update(active=False)
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=G)
    DutyAssignment.objects.create(period=p, date=MON, cell="slot0", member=person("STA"))
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert "confirm('생성 결과(장중관제 배정)가 지워지고 출근표는 그대로 남습니다. 계속할까요?')" in body
    assert "생성됨에서 나가면 장중관제 생성 결과만 지웁니다." in body


@pytest.mark.parametrize("cells,text", [
    ([], "출근표는 그대로 남습니다. 계속할까요?"),
    (["slot0"], "생성 결과(장중관제 배정)가 지워지고 출근표는 그대로 남습니다. 계속할까요?"),
    (["lunch"], "생성 결과(점심당번 배정)가 지워지고 출근표는 그대로 남습니다. 계속할까요?"),
    (["slot0", "lunch"], "생성 결과(장중관제·점심당번 배정)가 지워지고 출근표는 그대로 남습니다. 계속할까요?"),
])
def test_leave_confirm_text_by_assignments(it_board, admin_user, client, cells, text):
    """생성됨에서 나가는 확인창 글은 그 회차의 배정(없음·관제만·점심당번만·둘 다)으로 정해진다(설계 5.4)."""
    b = board_with(True, True)
    b.admin_group.user_set.add(admin_user)
    client.force_login(admin_user)
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=G)
    a = person("STA")
    for cell in cells:
        DutyAssignment.objects.create(period=p, date=MON, cell=cell, member=a)
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert body.count(f"confirm('{text}')") == 1  # 옮길 곳이 셋이라 '다른 상태로 옮기기' 상자 하나


def test_input_table_same_for_every_board(stp, depts, make_member, client):
    """입력 표: 채우기·CSV 글·닫힘 글은 모든 근무표가 같고, 회차 화면 링크는 그 근무표 관리자에게만(근무표 통합 2단계)."""
    b, admin = stp
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    body = admin.get(f"/collect/{p.pk}/STA/").content.decode()
    assert "지난주와 같게" in body and "CSV 올리기(이 표 전체 교체)" in body and f'href="/periods/{p.pk}/"' in body
    p.status = G
    p.save()
    assert "'입력 중'인 회차가 아니라 저장할 수 없습니다." in admin.get(f"/collect/{p.pk}/STA/").content.decode()
    it = Period.objects.create(board=depts["MEMS"].board, name="it", start_date=MON, end_date=FRI, status=C)
    clerk = make_member("가상담당", user=True)
    depts["MEMS"].input_group.user_set.add(clerk)
    client.force_login(clerk)
    body = client.get(f"/collect/{it.pk}/MEMS/").content.decode()
    assert "지난주와 같게" in body and "2주 전 기준으로 채우기" not in body  # 입력 근무조 4개(2주 전 기준은 3개일 때만)
    assert f'href="/periods/{it.pk}/"' not in body  # 입력 담당자는 회차 화면에 못 들어간다
```
(`stp` 픽스처와 `test_input_table_same_for_every_board` 의 `client` 는 같은 객체다: `admin` 으로 본 뒤 `clerk` 로 다시 로그인한다.)
- `test_legacy_board_with_slot_defs_looks_like_main` 을 데이터 기준 테스트로 바꾼다:
```python
def test_board_without_close_follows_slot_defs(stp):
    """2단계: 버튼 글자·생성 방식·재생성·배정 횟수 표는 켜진 관제 정의(데이터)로 정한다. 마감을 안 쓰는 근무표도 관제가 있으면
    [장중관제 생성]·[재생성]·생성 방식·횟수 표가 보인다."""
    b, client = stp
    BoardShift.objects.create(board=b, key="slot0", name="점검", start=time(10), end=time(11),
                              eligible_shifts=["dawn"], eligible_types=["직원"])
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=C)
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert ">장중관제 생성</button>" in body and "생성 방식" in body
    p.status = G
    p.save()
    a = person("STA")
    Commute.objects.create(period=p, date=MON, member=a, shift="dawn")
    DutyAssignment.objects.create(period=p, date=MON, cell="slot0", member=a)
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert ">장중관제 생성 취소</button>" in body and ">재생성</button>" in body and "장중관제 배정 횟수" in body
```
- `test_step_names_are_escaped_in_confirm` 을 아래로 바꾼다(2단계의 생성·나가는 확인창에는 이름이 들어가지 않는다. 이름이 남는 배포 취소 확인창을 본다):
```python
def test_step_names_are_escaped_in_confirm(stp):
    """확인창(인라인 JS) 안의 단계 이름 글은 escapejs 로 넣는다: 따옴표·역슬래시가 든 이름도 스크립트를 깨지 않는다.
    2단계의 생성·나가는 확인창에는 이름이 들어가지 않고, 배포 취소 확인창에 남는다."""
    b, client = stp
    Board.objects.filter(pk=b.pk).update(step_generated="확'정\\됨")
    p = Period.objects.create(board=b, name="p", start_date=MON, end_date=FRI, status=P, publish_undo=[],
                              published_at=timezone.now())
    PeriodEvent.objects.create(period=p, from_status=G, to_status=P)
    body = client.get(f"/periods/{p.pk}/").content.decode()
    assert "confirm('배포를 취소하고 이 회차를 확\\u0027정\\u005C됨으로 되돌릴까요?')" in body
```
- 파일 맨 끝에(IT: 취합 중에는 빈 날만 알리고 생성할 수 있다고 말하지 않는다 — 컨트롤러 결정):
```python


def test_it_empty_days_warn_and_generate_from_closed_only(admin_client_ok, depts, it_board):
    """IT 도 빈 평일은 경고만(근무표 통합 2단계). 취합 중에는 빈 날만 알리고(아직 생성할 수 없다), 마감에서 [장중관제 생성]은
    막히지 않고 테두리 버튼·확인창. 경고는 부서 이름·날 수·이어진 날짜."""
    p = Period.objects.create(board=it_board, name="p", start_date=MON, end_date=FRI, status=C)
    devs = {}
    for d in depts.values():
        if d.code != "UI":
            devs[d.code] = User.objects.create_user(f"{d.code}9", password=None, name=f"가상{d.code}", department=d, type="개발자")
            Commute.objects.create(period=p, date=MON, member=devs[d.code], shift="normal")
    warn = ("⚠ 출근표가 비어 있는 날: 정보분배 4일(11/17~11/20) · 매칭엔진실 4일(11/17~11/20) · "
            "매매지원실 4일(11/17~11/20) · UI 5일(11/16~11/20).")  # 부서 코드 순(입력 현황과 같다)
    body = admin_client_ok.get(f"/periods/{p.pk}/").content.decode()
    assert warn + "</p>" in body and "누를 수 있지만" not in body
    p.status = X
    p.save()
    body = admin_client_ok.get(f"/periods/{p.pk}/").content.decode()
    assert '<button class="outline">장중관제 생성</button>' in body and "아직 생성할 수 없습니다" not in body
    assert ("confirm('출근표가 비어 있는 부서가 있는 날이 5일 있습니다. 그날 그 부서는 근무자가 없고, "
            "아무 부서도 넣지 않은 날은 장중관제도 만들지 않습니다. 계속할까요?')") in body
    assert warn + " [장중관제 생성] 버튼은 누를 수 있지만 그날 그 부서는 근무자가 없습니다." in body
    p.status = G
    p.save()
    DutyAssignment.objects.create(period=p, date=MON, cell="slot0", member=devs["MEMS"])
    body = admin_client_ok.get(f"/periods/{p.pk}/").content.decode()
    assert '<button class="outline secondary">재생성</button>' in body and "다른 상태로 옮기기" in body
    assert "confirm('생성 결과(장중관제 배정)가 지워지고 출근표는 그대로 남습니다. 계속할까요?')" in body
```

`tests/test_fill.py`:
- `test_no_fill_buttons_on_collect_board_or_closed_period` 를:
```python
def test_fill_buttons_on_every_board_only_while_open(client, admin_user, it_board, ops):
    """채우기 버튼은 근무표와 상관없이 입력을 받는 동안만(근무표 통합 2단계): IT 취합 중에도 보이고, 확정한 회차에는 없다."""
    p, _ = ops
    p.status = S.GENERATED
    p.save()
    ops[1].board.admin_group.user_set.add(admin_user)
    Department.objects.create(code="MEMS", name="매칭엔진실", shifts="dawn,normal,dinner", board=it_board)
    it = Period.objects.create(board=it_board, name="it", start_date=d(11, 16), end_date=d(11, 20), status=S.COLLECTING)
    client.force_login(admin_user)
    body = client.get(f"/collect/{it.pk}/MEMS/").content.decode()
    assert 'value="2w:2026-11-16"' in body and 'value="1w:2026-11-16"' in body
    assert 'name="fill"' not in client.get(f"/collect/{p.pk}/OPS/").content.decode()
```
- `test_table_cells_wrap_and_messages_are_plain` 의 `"CSV 올리기 (표 전체 교체)"` → `"CSV 올리기(이 표 전체 교체)"`

`tests/test_views_direct.py`:
- `test_input_page_shows_direct_steps_and_buttons` 의
```python
    assert "⚠ 아직 입력하지 않은 평일: 11/19, 11/20." in body
    assert "부서별 입력 현황" not in body and "생성 방식" not in body and "다른 상태로 옮기기" not in body
```
를
```python
    assert "⚠ 출근표가 비어 있는 날: 운영 2일(11/19~11/20). [확정] 버튼은 누를 수 있지만 그날 그 부서는 근무자가 없습니다." in body
    assert "부서별 입력 현황" in body and "운영: 3 / 5일" in body  # 입력 현황은 모든 근무표, 부서 이름으로(근무표 통합 2단계)
    assert "생성 방식" not in body and "다른 상태로 옮기기" not in body
```
로.
- `test_input_table_links_back_and_names_closed_state` 의 `"입력 중인 회차가 아니라 저장할 수 없습니다"` → `"'입력 중'인 회차가 아니라 저장할 수 없습니다"`
- `test_period_save_confirms_only_when_shrinking` 의 docstring 을 `"""기간 저장: 지금 기간(data-start/end)보다 좁힐 때만 확인 창(바깥 날짜 행이 지워진다). 모든 근무표(근무표 통합 2단계)."""` 로, 마지막 줄을
```python
    assert SHRINK in admin_client_ok.get(f"/periods/{draft.pk}/").content.decode()  # 되돌아온 작성 중 회차는 행이 있을 수 있다
```
로.
- `test_confirm_message_says_what_happened` 의 마지막 단언을(메시지 안 작은따옴표는 HTML 에서 `&#x27;` 로 나온다)
```python
    assert "&#x27;확정&#x27; 상태로 바꿨습니다. 근무표 화면에는 배포한 뒤에 보입니다." in body and "완료했습니다" not in body
```
로.

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_steps.py tests/test_fill.py tests/test_views_direct.py`
Expected: FAIL — `test_board_steps.py` 는 모음 오류 `ImportError: cannot import name 'gen_help' from 'duty.shifts'`, `test_fill.py` 2개·`test_views_direct.py` 4개 실패

- [ ] **Step 3: 생성 방식 문장과 회차 화면 뷰**

`duty/shifts.py` 의 `josa` 바로 뒤에:
```python
def gen_help(defs: list[Def]) -> dict | None:
    """회차 화면 [생성 방식] 상자의 숫자·자격 문장(설계 6.1): 켜진 관제 정의에서 만든다. 관제가 없으면 None.
    가장 많은 칸이 쓰는 자격 근무조는 '나머지 칸', 다른 칸은 시작 시각으로 적는다."""
    slots = slot_defs(defs)
    if not slots:
        return None
    order = [x.key for x in shift_defs(defs)]
    names = {x.key: x.name for x in defs}

    def joined(keys):
        return "·".join(names[k] for k in order if k in keys)

    sets = [frozenset(x.eligible_shifts) for x in slots]
    common = max(sets, key=sets.count)  # 같은 수면 먼저 나온 것
    rest = joined(common) + (" 둘 다" if len(common) == 2 else " 모두" if len(common) > 2 else "만")
    rule = [f"{x.start:%H:%M} 칸은 {joined(s)}" for x, s in zip(slots, sets) if s != common]
    rule.append(f"{'나머지 칸' if rule else '모든 칸'}은 {rest} 됩니다.")
    types = "·".join(dict.fromkeys(t for x in slots for t in x.eligible_types))  # 비면 구분 없이 누구나
    who = types or "사람"
    return {"count": len(slots), "start": slots[0].start, "end": max(x.end for x in slots), "types": types,
            "who": who, "whom": who + josa(who, "을/를"), "rule": ", ".join(rule)}


```

`duty/views/manage.py` — import 두 줄:
```python
from ..models import Board, ChangeLog, Department, DutyAssignment, Period, User
```
```python
from ..shifts import LUNCH, by_key, cell_label, day_spans, gen_help, is_slot_cell, josa, slot_defs
```
`def _render_detail(` 부터 다음 `@admin_required` 앞까지를 아래로 바꾼다(앞에 두 도우미):
```python
def _empty_confirm(missing, has_slots) -> str:
    """빈 평일이 있을 때만 띄우는 생성 확인창(설계 6.1). 날 수 = 어느 부서든 출근표가 빈 평일."""
    n = len({d for ds in missing.values() for d in ds})
    tail = "고, 아무 부서도 넣지 않은 날은 장중관제도 만들지 않습니다." if has_slots else "습니다."
    return f"출근표가 비어 있는 부서가 있는 날이 {n}일 있습니다. 그날 그 부서는 근무자가 없{tail} 계속할까요?"


def _leave_what(period, active) -> str:
    """생성됨에서 나갈 때 지워지는 배정 이름(설계 5.4). 생성됨 회차는 그 회차에 실제로 있는 배정으로(정의를 꺼도 남은 배정이
    숨지 않게), 그 밖은 켜진 정의로(옮기기 상자 설명)."""
    if period.status == Period.Status.GENERATED:
        cells = set(DutyAssignment.objects.filter(period=period).values_list("cell", flat=True))
        slot, lunch = any(is_slot_cell(c) for c in cells), LUNCH in cells
    else:
        slot, lunch = bool(slot_defs(active)), LUNCH in by_key(active)
    return "·".join(name for name, on in (("장중관제", slot), ("점심당번", lunch)) if on)


def _render_detail(request, period, failures):
    counts, spread, reached = stats.period_duty_counts(period)
    board = period.board
    active = boards.active_defs(board)
    slot_names = [x.name for x in slot_defs(active)]  # generator 의 칸 번호 = 켜진 관제 정의 순서
    S = Period.Status
    targets = board.move_targets(period.status)
    missing = periods.missing_dates(period)
    names = dict(Department.objects.filter(board=board).values_list("code", "name"))
    leave = _leave_what(period, active)
    on = board.steps()
    return render(request, "duty/period_detail.html", {
        "period": period, "board": board, "S": S, "generated_label": board.step_name(S.GENERATED),
        "steps": [(s, board.step_name(s)) for s in on], "editable": board.editable(),
        # 2단계: 버튼 글자·[재생성]·생성 방식·배정 횟수 표는 켜진 관제 정의(데이터)로 정한다(1단계는 임시 기준)
        "buttons": board.step_buttons(bool(slot_names)), "gen_help": gen_help(active),
        "generated_ro": josa(board.step_name(S.GENERATED), "으로/로"),
        "movable": [(s, board.step_name(s)) for s in targets],
        "undo_to": targets[0] if len(targets) == 1 else "",
        "unused_step": period.status not in on,  # 끈 단계에 남은 회차(설계 6.1)
        # 생성됨에서 나가는 확인창은 하나([… 취소] 버튼과 '다른 상태로 옮기기' 상자, 설계 5.4)
        "leave_what": leave,
        "leave_generated_confirm": (f"생성 결과({leave} 배정)가 지워지고 출근표는 그대로 남습니다. 계속할까요?"
                                    if leave else "출근표는 그대로 남습니다. 계속할까요?"),
        "empty_confirm": _empty_confirm(missing, bool(slot_names)) if missing else "",
        "events": [(e, e.from_status and board.step_name(e.from_status), board.step_name(e.to_status))
                   for e in period.events.select_related("by")],
        "input_depts": Department.objects.filter(board=board).order_by("order", "code"),
        # 빈 평일 경고(설계 6.1): 켠 단계의 취합 중·마감에서 부서마다 빈 날 수와 날짜(이어진 평일은 묶어서).
        # '버튼은 누를 수 있지만'은 그 상태에서 생성할 수 있을 때만
        "empty": ([(names[c], len(ds), day_spans(ds)) for c, ds in missing.items()]
                  if period.status in {S.COLLECTING, S.CLOSED} and period.status in on else []),
        "can_generate_now": period.status == board.generate_from(),
        "undo": publishing.unpublish_info(period) if period.status == Period.Status.PUBLISHED else None,
        "progress": [(code, names[code], n, m) for code, (n, m) in collect.progress(period).items()], "missing": missing,
        "counts": counts, "spread": spread, "reached": reached,
        "failures": [{"date": f.date, "slot": slot_names[f.slot], "candidates": f.candidates} for f in failures],
    })
```
`period_action` 의
```python
        if action == "generate" and boards.legacy_admin_entry(period.board):
            done = "확정했습니다. 근무표 화면에는 배포한 뒤에 보입니다. 아래 경고를 확인하고 [배포…]를 누르세요."
```
를
```python
        if action == "generate":
            done += " 근무표 화면에는 배포한 뒤에 보입니다."
```
로.

`duty/services/periods.py` 의 `def empty_days(period: Period) -> list[date]:` 함수 전체(docstring·return·빈 줄 둘)를 지운다(이제 부르는 곳이 없다: `git grep -n empty_days -- duty` → 없음).

- [ ] **Step 4: 회차 화면 템플릿을 고친다**

`duty/templates/duty/period_detail.html`:
- 기간 폼 두 줄을(확인창이 모든 근무표에):
```django
<form method="post" class="search labeled" data-start="{{ period.start_date|date:'Y-m-d' }}" data-end="{{ period.end_date|date:'Y-m-d' }}"
      onsubmit="return !(this.start_date.value &gt; this.dataset.start || this.end_date.value &lt; this.dataset.end) || confirm('기간을 줄이면 바깥 날짜의 출근표가 지워집니다. 저장할까요?')">{% csrf_token %}
```
- `{% elif period.status == S.COLLECTING %}` 갈래의 두 줄과 그 아래 두 갈래(마감·생성됨)를:
```django
  {% for d in input_depts %}<a role="button"{% if not missing or not forloop.first %} class="outline"{% endif %} href="{% url 'collect_table' period.pk d.code %}">표 입력{% if input_depts|length > 1 %} · {{ d.name }}{% endif %}</a>{% endfor %}
  <form method="post" action="{% url 'period_action' period.pk 'generate' %}"{% if empty_confirm %} onsubmit="return confirm('{{ empty_confirm|escapejs }}')"{% endif %}>{% csrf_token %}<button{% if missing %} class="outline"{% endif %}>{{ buttons.generate }}</button></form>
  {% elif period.status == S.CLOSED and board.use_close %}
  <form method="post" action="{% url 'period_action' period.pk 'generate' %}"{% if empty_confirm %} onsubmit="return confirm('{{ empty_confirm|escapejs }}')"{% endif %}>{% csrf_token %}<button{% if missing %} class="outline"{% endif %}>{{ buttons.generate }}</button></form>
  {% elif period.status == S.GENERATED %}
  <a role="button" href="{% url 'period_publish' period.pk %}">배포…</a>
  {% if buttons.regenerate %}<form method="post" action="{% url 'period_action' period.pk 'generate' %}" onsubmit="return confirm('지금 생성 결과를 버리고 다시 생성할까요?')">{% csrf_token %}<button class="outline secondary">{{ buttons.regenerate }}</button></form>{% endif %}
  {% if buttons.undo %}<form method="post" action="{% url 'period_move' period.pk %}" onsubmit="return confirm('{{ leave_generated_confirm|escapejs }}')">{% csrf_token %}<input type="hidden" name="to" value="{{ undo_to }}"><button class="outline secondary">{{ buttons.undo }}</button></form>{% endif %}
```
로(빈 날이 있으면 생성 버튼은 막지 않고 테두리 버튼 + 날 수 확인창, 마감 끈 근무표는 첫 [표 입력]이 진한 버튼. 확인창 글은 `escapejs`. [재생성] 확인창은 그대로).
- [생성 방식] 버튼 조건 `{% if not legacy and period.status == S.CLOSED or not legacy and period.status == S.GENERATED %}` 을
```django
  {% if gen_help and period.status == board.generate_from or gen_help and period.status == S.GENERATED %}
```
로(켜진 관제 정의가 있을 때, 생성할 수 있는 상태와 생성됨에서).
- `</div>` 아래 경고 두 줄(`{% if empty_days %}…` 와 `{% if missing and board.use_close …%}<p class="note">출근표가 비어 있는 부서가 있어 아직 생성할 수 없습니다…`)을:
```django
{% if empty %}<p class="note warn">⚠ 출근표가 비어 있는 날: {% for name, n, spans in empty %}{{ name }} {{ n }}일({{ spans }}){% if not forloop.last %} · {% endif %}{% endfor %}.{% if can_generate_now %} [{{ buttons.generate }}] 버튼은 누를 수 있지만 그날 그 부서는 근무자가 없습니다.{% endif %}</p>{% endif %}
{% if unused_step %}<p class="note warn">이 단계는 지금 쓰지 않습니다. 아래 [다른 상태로 옮기기]를 눌러 옮기세요.</p>{% endif %}
```
로.
- 옮기기 상자: `<details class="move-box"><summary>` → `<details class="move-box"{% if unused_step %} open{% endif %}><summary>다른 상태로 옮기기</summary>`, 폼 확인창 `confirm('장중관제·점심당번 생성 결과가 삭제됩니다. 계속할까요?')` → `confirm('{{ leave_generated_confirm|escapejs }}')`, 설명 줄을
```django
  <small>출근표는 그대로 남습니다.{% if leave_what %} 생성됨에서 나가면 {{ leave_what }} 생성 결과만 지웁니다.{% endif %}</small>
```
로.
- 입력 현황 블록(`{% if not legacy %}` … `{% endif %}`)을:
```django
<h4>부서별 입력 현황</h4>
<ul class="progress">{% for code, name, n, m in progress %}<li>{{ name }}: {{ n }} / {{ m }}일
  {% if code in missing %}<small>(비어 있는 날짜 있음)</small>{% endif %}
  {% if period.status == S.COLLECTING %}<a role="button" class="outline secondary" href="{% url 'collect_table' period.pk code %}">표 입력</a>{% endif %}</li>{% endfor %}</ul>
```
로.
- `{% if counts and not legacy %}` → `{% if counts %}`
- `<dialog id="gen-help">` 바로 위 `{% if not legacy %}` → `{% if gen_help %}`, 상자 안 세 곳(지금 "장중관제 10칸(08:30~18:00)에 개발자를 한 명씩", "개발자이고 … 08:30 칸은 정상, 17:00 칸은 석식교대, 나머지 칸은 정상·석식교대 둘 다 됩니다.", "개발자끼리만" 줄)을:
```django
  <p>취합된 출근조를 보고 날짜마다 장중관제 {{ gen_help.count }}칸({{ gen_help.start|time:"H:i" }}~{{ gen_help.end|time:"H:i" }})에 {{ gen_help.whom }} 한 명씩 배정합니다.</p>
```
```django
    <li><strong>자격</strong> — {% if gen_help.types %}{{ gen_help.types }}이고 {% endif %}그날 그 칸의 출근조에 있어야 합니다.
      {{ gen_help.rule }}</li>
```
```django
  <p><small>횟수는 기간 중 한 번이라도 자격이 있었던 {{ gen_help.who }}끼리만 비교합니다.
```
- `<style>` 의 `p.note.warn {` 줄 바로 앞에 두 줄:
```css
  ul.progress li { display: flex; flex-wrap: wrap; align-items: center; gap: .3rem .6rem; margin-bottom: .4rem; }
  ul.progress a[role=button] { width: auto; margin: 0; min-height: 44px; padding: .45rem 1rem; }  /* 누를 자리 44px 이상 */
```

- [ ] **Step 5: 입력 표를 고친다**

`duty/views/collect.py` `_render_table` 의 `legacy = boards.legacy_admin_entry(period.board)  …` 줄을 지우고 컨텍스트 두 줄을:
```python
        "is_open": is_open, "back_link": admin, "ncols": len(keys) + 2,  # 회차 화면 링크는 그 근무표 관리자에게만
        "collecting": period.board.step_name(Period.Status.COLLECTING),
        "show_fill": is_open, "can_rotate": collect.can_rotate(dept),  # 채우기 버튼(설계 6.1): 모든 근무표, 입력을 받는 동안
```
로(`admin` 은 함수 앞에서 이미 `perms.is_board_admin(request.user, period.board)` 로 구해 둔 값).

`duty/templates/duty/collect_table.html` 4·5번째 줄을:
```django
{% if back_link %}<p><a href="{% url 'period_detail' period.pk %}">← 회차 화면으로</a></p>{% endif %}
{% if not is_open %}<p>'{{ collecting }}'인 회차가 아니라 저장할 수 없습니다.</p>{% endif %}
```
로, 9번째 줄 버튼을 `    <button class="secondary">CSV 올리기(이 표 전체 교체)</button>` 로.

- [ ] **Step 6: 통과를 확인하고 스냅샷을 다시 쓴다**

Run: `git grep -n -E "legacy|empty_days" -- duty/views duty/templates duty/services/periods.py`
Expected: 아무것도 안 나온다.
Run: `.venv/bin/pytest -W error -q tests/test_board_steps.py tests/test_fill.py tests/test_views_direct.py tests/test_views_manage.py tests/test_views_collect.py`
Expected: 모두 통과
Run: `DUTY_SNAPSHOT_WRITE=1 .venv/bin/pytest -W error -q tests/test_snapshots.py; .venv/bin/pytest -W error -q tests/test_snapshots.py && git status --short tests/snapshots/`
Expected: 첫 실행 `1 failed`(다시 씀), 둘째 `1 passed`, 바뀐 파일은 회차 화면 13개(`period-*` 전부 — 스타일 두 줄이 늘었다)와 입력 표 4개, 모두 17개. `collect-index`·`day`·`help-admin`·`periods`·`roster-mine`·`roster-month`·`roster-other` 7개는 그대로여야 한다. `git diff tests/snapshots/` 로 파일마다 아래만 바뀌었는지 본다(모든 `period-*` 에는 `<style>` 의 `ul.progress` 두 줄과 입력 현황이 부서 이름으로 바뀐 것이 공통. IT 생성 방식 상자 글은 바뀌지 않는다 — `gen_help` 가 같은 글을 만든다):
- `period-it-closed`: 생성 폼에 `onsubmit="return confirm('출근표가 비어 있는 부서가 있는 날이 5일 있습니다. 그날 그 부서는 근무자가 없고, 아무 부서도 넣지 않은 날은 장중관제도 만들지 않습니다. 계속할까요?')"`, `<button disabled>장중관제 생성` → `<button class="outline">장중관제 생성`, "출근표가 비어 있는 부서가 있어 아직 생성할 수 없습니다(아래 입력 현황)." → "⚠ 출근표가 비어 있는 날: 정보분배 5일(11/16~11/20) · 매칭엔진실 2일(11/19~11/20) · 매매지원실 5일(11/16~11/20) · UI 5일(11/16~11/20). [장중관제 생성] 버튼은 누를 수 있지만 그날 그 부서는 근무자가 없습니다.", 옮기기 상자 설명 "생성됨에서 나가면 장중관제 생성 결과만 지웁니다."(테스트 IT 에는 점심당번 정의가 없다)
- `period-it-collecting`: "아직 생성할 수 없습니다" 줄 → ⚠ 줄(날 수·날짜만, "누를 수 있지만" 없음), 입력 현황 부서마다 `<a role="button" class="outline secondary" href="/collect/N/<코드>/">표 입력</a>`
- `period-it-draft`: 기간 폼에 `data-start`·`data-end`·줄이기 확인창
- `period-it-generated`: `재생성` 버튼의 `disabled` 가 빠지고 "아직 생성할 수 없습니다" 줄이 빠지고, 옮기기 상자 확인창이 "출근표는 그대로 남습니다. 계속할까요?"(그 회차에 배정이 없다)
- `period-it-full-closed`: 생성 버튼은 그대로 진한 버튼·확인창 없음(빈 날 없음) / `period-it-full-generated`: 옮기기 확인창 "생성 결과(장중관제 배정)가 지워지고 출근표는 그대로 남습니다. 계속할까요?"
- `period-ops-collecting`: [확정] 확인창 "확정할까요? …[확정 취소]를 누릅니다." → "출근표가 비어 있는 부서가 있는 날이 2일 있습니다. 그날 그 부서는 근무자가 없습니다. 계속할까요?", "⚠ 아직 입력하지 않은 평일: 11/19, 11/20. 확정은…" → "⚠ 출근표가 비어 있는 날: 운영 2일(11/19~11/20). [확정] 버튼은 누를 수 있지만 그날 그 부서는 근무자가 없습니다.", 입력 현황(`운영: 3 / 5일 (비어 있는 날짜 있음) [표 입력]`)
- `period-ops-draft`·`period-ops-closed`(끈 단계에 남은 회차): "이 단계는 지금 쓰지 않습니다. 아래 [다른 상태로 옮기기]를 눌러 옮기세요." 줄, 펼친 상자(`open`), 입력 현황(⚠ 줄은 없다)
- `period-ops-generated`: [확정 취소] 확인창 "출근표는 그대로 남습니다. 계속할까요?"(그 회차에 배정이 없다), 입력 현황 / `period-ops-published`·`period-it-published`: 입력 현황·스타일
- `period-ops-slot-history`(관제 정의는 꺼졌고 관제·점심당번 배정이 남은 확정 회차): [확정 취소] 확인창 "생성 결과(장중관제·점심당번 배정)가 지워지고 출근표는 그대로 남습니다. 계속할까요?", 입력 현황, **배정 횟수 표가 새로 보인다**(데이터 기준: 남은 관제 배정이 있다. 버튼은 켜진 관제 정의가 없어 그대로 [확정 취소]). OPERATIONS 1단계 확인 ②가 이런 근무표를 찾는다
- `table-it-collecting`: `← 회차 화면으로` 링크, `CSV 올리기(이 표 전체 교체)`, 화면 밖 `표 저장` 버튼과 주마다 `지난주와 같게`(입력 근무조 4개라 2주 전 기준은 없음)
- `table-it-closed`: `← 회차 화면으로` 링크, "취합이 열려 있지 않아 저장할 수 없습니다." → "'취합 중'인 회차가 아니라 저장할 수 없습니다."
- `table-ops-collecting`: `← 회차 화면으로(확정·배포)` → `← 회차 화면으로`, `CSV 올리기 (표 전체 교체)` → `CSV 올리기(이 표 전체 교체)`
- `table-ops-generated`: 링크 글, "입력 중인 회차가 아니라…" → "'입력 중'인 회차가 아니라…"

- [ ] **Step 7: 전체 테스트**

Run: `.venv/bin/pytest -W error -q && DUTY_DEBUG=1 DUTY_ENV_FILE= DUTY_DATA_DIR=$(mktemp -d) .venv/bin/python manage.py makemigrations duty --check --dry-run`
Expected: `1311 passed`, "No changes detected in app 'duty'"

- [ ] **Step 8: 브라우저로 본다**

"브라우저 확인 준비"대로 띄운다.
1. PC 1400px, 보통 글씨, 밝게, `admin`: IT 회차 하나를 취합 중으로 두고 ⚠ 줄이 부서 이름·날 수·이어진 날짜로 한두 줄인지, "누를 수 있지만"이 없는지. 마감으로 옮겨 → [장중관제 생성]이 테두리 버튼, ⚠ 줄 끝에 "[장중관제 생성] 버튼은 누를 수 있지만…". 누르면 "출근표가 비어 있는 부서가 있는 날이 N일 있습니다. …계속할까요?" → [확인] 뒤 "'생성됨' 상태로 바꿨습니다. 근무표 화면에는 배포한 뒤에 보입니다."와 노란 경고 "출근표가 비어 있는 날이 있습니다: …". "다른 상태로 옮기기" → [옮기기] 확인창이 그 회차의 배정 이름. 운영팀 "이번 2주" → 입력 현황(운영 n/10일, [표 입력] 버튼), ⚠ 줄, 첫 [표 입력]이 진한 버튼, [확정]을 누르면 빈 날 수 확인창.
2. 끈 단계 안내는 테스트와 스냅샷(`period-ops-draft`)으로 본다(관리 화면 단계 칸이 2단계까지 읽기 전용이라 화면으로 만들 수 없다). IT 취합 중 회차의 매칭엔진실 입력 표(`manager` 로 로그인): 주 머리마다 [지난주와 같게]만(입력 근무조 4개), [← 회차 화면으로] 링크 없음. `admin` 으로 보면 링크가 있다.
3. 390px·아주 크게: 회차 화면 ⚠ 줄이 줄바꿈되고 가로 넘침이 없는지, 입력 현황 [표 입력] 버튼이 부서 이름 옆(좁으면 아래 줄)에 손가락으로 누를 만큼 큰지(개발자 도구로 높이 44px 이상). 입력 표의 주 머리 [지난주와 같게]가 한 줄에 다 보인다. 확인창 글이 휴대폰 창에서 잘리지 않는다. 가로 넘침 `false`.
4. 다크 모드: ⚠ 줄·끈 단계 안내(주황 띠·옅은 배경) 글자 대비, 테두리 [장중관제 생성]·[표 입력] 버튼이 보이는지.

- [ ] **Step 9: 커밋**

```bash
git add duty/shifts.py duty/views/manage.py duty/views/collect.py duty/services/periods.py duty/templates/duty/period_detail.html duty/templates/duty/collect_table.html tests/
git commit -m "$(cat <<'EOF'
feat: 회차 화면을 관제 정의 기준으로(생성 방식 글은 정의에서), 빈 평일 경고·빈 날 확인창·입력 현황([표 입력] 버튼)·실제 배정으로 만든 나가는 확인창·끈 단계 안내, 입력 표 채우기·글을 모든 근무표에 같게(근무표 통합 2단계)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

---

### Task 9: 글 도움말 하나("회차 운영")·입력 담당 글에 채우기

> 범위: `duty/help.py`(설계 6.1 `help.py:3,12,53,72-73` 의 2단계). 이 작업으로 `legacy_admin_entry` 의 화면·서비스 자리가 모두 없어진다. 함수와 `Department.save`·부서 폼 자리, 관리 화면 단계 칸 편집 열기는 3단계 몫이다(설계 5.1·5.3) — 이 작업에서 관리 화면은 건드리지 않는다.

**Files:**
- Modify: `duty/help.py` — import, `TEXTS`, `STEPS["manager"]` 한 줄, `STEPS["direct"]` → `STEPS["period"]`, `allowed`, `_board_steps`·`texts_for`
- Modify(테스트): `tests/test_help.py`(직접 입력 글 테스트 → 새 테스트 둘)
- Modify(생성 파일): `tests/snapshots/help-admin.html`

**Interfaces:**
- Consumes: `perms.admin_boards(user)`, `perms.is_admin(user)`, `Board.step_name/steps`
- Produces:
  - `help.TEXTS = [("period", "회차 운영(단계·출근표·생성·배포)", "근무표 관리자")]`, `help.allowed(user, "period") = perms.is_admin(user)`
  - `help.texts_for(user)`: `steps` = 내가 관리하는 근무표마다 `"<이름>: <켠 단계 이름 → …>"`(id 순) + `STEPS["period"]`
  - `STEPS["manager"]` 에 채우기 한 줄(영상 뒤에 생긴 기능)

- [ ] **Step 1: 실패 테스트를 쓴다**

`tests/test_help.py` 의 `test_direct_board_admin_text_help` 함수 전체를 아래 둘로 바꾼다:
```python
def test_period_text_help_for_every_board_admin(client, people, videos):
    """근무표 관리자 모두에게 글 도움말 하나(근무표 통합 2단계). 단계 줄은 내가 관리하는 근무표마다 그 근무표의 단계 이름으로."""
    from duty.models import Board
    client.force_login(people["member"])
    assert "<h4>글 도움말</h4>" not in client.get("/help/").content.decode()
    client.force_login(people["admin"])
    body = client.get("/help/").content.decode()
    assert body.index("<h4>사용법 영상</h4>") < body.index("<h4>글 도움말</h4>") < body.index("회차 운영(단계·출근표·생성·배포)")
    assert "<li>IT 당번표: 작성 중 → 취합 중 → 마감 → 생성됨 → 배포됨</li>" in body and "운영팀" not in body
    Board.objects.create(code="ops", name="운영팀", **OPS_STEPS).admin_group.user_set.add(people["admin"])
    body = client.get("/help/").content.decode()
    assert body.index("<li>IT 당번표: 작성 중") < body.index("<li>운영팀: 입력 중 → 확정 → 배포됨</li>")
    for word in ("[2주 전 기준으로 채우기]", "[지난주와 같게]", "[표 저장]", "[확정 취소]", "[배포…]", "[생성 방식]"):
        assert word in body, word
    assert "직접 입력" not in body
    assert body.count("글로 보기") == 3  # 영상 글은 그대로, 글 도움말은 영상이 없다
    assert client.get("/help/video/period.mp4").status_code == 404


def test_manager_text_explains_fill(client, people, videos):
    """채우기 버튼은 입력 담당자에게도 보이므로(2단계) 출근표 입력 글에 설명이 있다."""
    client.force_login(people["manager"])
    body = client.get("/help/").content.decode()
    assert "[지난주와 같게]" in body and "[2주 전 기준으로 채우기]" in body and "<h4>글 도움말</h4>" not in body
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_help.py`
Expected: `2 failed` — `test_period_text_help_for_every_board_admin`(`ValueError: substring not found`: 글 도움말이 없다), `test_manager_text_explains_fill`

- [ ] **Step 3: 도움말을 고친다**

`duty/help.py`:
- 맨 위 import 를 `from . import perms` 한 줄만 남긴다(`from .services import boards` 를 지운다).
- `TEXTS` 를:
```python
TEXTS = [  # 영상 없이 글로만 보는 사용법 (이름, 제목, 누구를 위한)
    ("period", "회차 운영(단계·출근표·생성·배포)", "근무표 관리자"),
]
```
- `STEPS["manager"]` 의 `"엑셀로 하려면 … 부서 전체를 한 번에 바꿉니다.",` 다음 줄에:
```python
        # 영상 뒤에 생긴 기능(근무표 통합 2단계): 영상에는 없다
        "표에는 주마다 [지난주와 같게](지난주 같은 요일을 옮기고 사유는 옮기지 않음)와, 입력 근무조가 3개인 부서는 [2주 전 기준으로 채우기](2주 전 그 주를 보고 이른 조와 늦은 조를 맞바꿈, 가운데 조였던 사람과 새로 온 사람은 가운데 조)가 있습니다. 채우기는 그 주 표를 그려 보여 주기만 하니(바뀐 칸 색칠) 확인하고 [표 저장]을 누릅니다.",
```
- `"direct": [ … ],` 항목 전체를:
```python
    "period": [  # 앞에 내가 관리하는 근무표마다 단계 줄이 붙는다(texts_for)
        "[회차]에서 [+ 새 회차]로 이름과 기간을 정해 만듭니다. 첫 단계에서는 기간을 고칠 수 있습니다(줄이면 기간 밖 출근표는 지워집니다).",
        "입력 단계(취합 중·입력 중)에는 부서 입력 담당자와 근무표 관리자가 출근표를 넣습니다. 회차 화면 '부서별 입력 현황'의 [표 입력]으로 들어갑니다. 입력 담당자가 없는 부서는 근무표 관리자만 넣습니다.",
        "입력 표에는 주마다 [지난주와 같게]와(입력 근무조가 3개인 부서는) [2주 전 기준으로 채우기]가 있습니다. 그 주 표를 그려 보여 주기만 하니 확인하고 [표 저장]을 누릅니다(자세한 것은 '출근표 입력' 글).",
        "마감 단계를 쓰는 근무표는 [… 마감] 뒤에, 쓰지 않는 근무표는 입력 단계에서 바로 생성 버튼([장중관제 생성]·[확정] 등)을 누릅니다. 출근표가 비어 있는 날이 있으면 누르기 전에 날 수를 묻고, 경고만 보인 채 생성됩니다(그날 그 부서는 근무자가 없습니다).",
        "장중관제가 있으면 자격자에게 편차 2 이하로 자동 배정하고(규칙은 [생성 방식]), 점심당번이 있으면 가장 이른 근무조 사람으로 채웁니다.",
        "생성한 뒤 [배포…]로 근무표에 내보냅니다. 배포 전에 고칠 것이 있으면 [… 취소]나 '다른 상태로 옮기기'로 입력 단계로 돌아갑니다(출근표는 그대로, 생성 결과만 지워집니다).",
        "배포한 뒤에는 근무표 화면에서 칸을 눌러 바꿉니다. 잘못 배포했으면 회차 화면의 [배포 취소]로 되돌립니다(가장 최근 배포만).",
        "버튼 이름은 단계 이름에서 나옵니다(예: '취합 중' → [취합 열기]·[취합 마감], 장중관제가 없는 근무표의 '확정' → [확정]·[확정 취소]).",
    ],
```
로.
- `allowed` 의 끝 세 줄(`if name == "direct":` … `return name == "admin" and perms.is_admin(user)`)을
```python
    return name in ("admin", "period") and perms.is_admin(user)
```
로.
- `texts_for` 를:
```python
def _board_steps(user) -> list[str]:
    """내가 관리하는 근무표마다 단계 줄(설계 6.1): 'IT 당번표: 작성 중 → 취합 중 → 마감 → 생성됨 → 배포됨'."""
    return [f"{b.name}: " + " → ".join(b.step_name(s) for s in b.steps()) for b in perms.admin_boards(user).order_by("id")]


def texts_for(user) -> list[dict]:
    return [{"name": n, "title": t, "who": w, "steps": _board_steps(user) + STEPS[n]}
            for n, t, w in TEXTS if allowed(user, n)]
```
로.

- [ ] **Step 4: 통과·흔적·스냅샷**

Run: `git grep -n legacy_admin_entry -- duty`
Expected: `duty/admin.py` 의 `DepartmentForm.clean` 두 줄과 `BoardAdmin.get_readonly_fields` 주석 한 줄, `duty/models.py` 의 `Department.save` 두 줄, `duty/services/boards.py` 의 정의만(3단계 몫).
Run: `git grep -n -E "\bdirect\b" -- duty tests ':!duty/migrations' ':!duty/help_videos' ':!tests/test_migration_*'`
Expected: `tests/test_admin_department.py:70-71` 의 지역 변수 이름 `direct` 두 줄만(갈래가 아니라 이름).
Run: `.venv/bin/pytest -W error -q tests/test_help.py tests/test_board_steps.py tests/test_help_seed.py tests/test_admin_boards.py`
Expected: 모두 통과
Run: `DUTY_SNAPSHOT_WRITE=1 .venv/bin/pytest -W error -q tests/test_snapshots.py; .venv/bin/pytest -W error -q tests/test_snapshots.py && git status --short tests/snapshots/`
Expected: 첫 실행 `1 failed`(다시 씀), 둘째 `1 passed`, `help-admin.html` 하나만 바뀐다(글 도움말 제목·대상·단계 줄 "IT 당번표: …"·"운영팀: 입력 중 → 확정 → 배포됨"·본문, 출근표 입력 글에 채우기 한 줄).

- [ ] **Step 5: 전체 테스트**

Run: `.venv/bin/pytest -W error -q && DUTY_DEBUG=1 DUTY_ENV_FILE= DUTY_DATA_DIR=$(mktemp -d) .venv/bin/python manage.py makemigrations duty --check --dry-run`
Expected: `1312 passed`, "No changes detected in app 'duty'"

- [ ] **Step 6: 브라우저로 본다**

"브라우저 확인 준비"대로 띄운다.
1. `admin`(IT·운영팀 관리): [도움말] → "사용법 영상" 아래 "글 도움말"에 "회차 운영(단계·출근표·생성·배포) · 근무표 관리자", 첫 두 줄 "IT 당번표: 작성 중 → … → 배포됨"·"운영팀: 입력 중 → 확정 → 배포됨". `manager`: 출근표 입력 영상의 "글로 보기"에 채우기 줄, 글 도움말 없음. `member`: 글 도움말 없음. PC 1400px·390px·아주 크게·다크 모드에서 글 목록이 줄바꿈되고 가로 넘침 `false`.
2. 관리 화면 → 근무표 → 운영팀: "회차 단계" 칸이 그대로 글자로만(읽기 전용) 보인다(3단계에서 열린다).

- [ ] **Step 7: 커밋**

```bash
git add duty/help.py tests/
git commit -m "$(cat <<'EOF'
feat: 글 도움말을 근무표 관리자 모두의 '회차 운영' 하나로(근무표마다 단계 줄), 입력 담당 글에 채우기

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

---

### Task 10: 2단계 문서

> 범위: 문서만(설계 13절의 2단계 몫, 10.3 2단계 확인 쿼리, 10.4 "2단계" 올리는 때·공지). Task 6 이 바꾼 글 위에서 바꾼다.

**Files:**
- Modify: `docs/ARCHITECTURE.md`, `docs/OVERVIEW.md`, `docs/OPERATIONS.md`, `docs/PRINCIPLES.md`

**Interfaces:**
- Consumes: Task 7~9 의 동작·문구(`_leave_what`·`leave_generated_confirm`, `_empty_confirm`, `day_spans`, 끈 단계 안내, 빈 평일 경고 글, `help` 의 `"period"`)
- Produces: 문서만

- [ ] **Step 1: 아래 찾을 글을 바꿀 글로 바꾼다(파일마다 한 번씩만 나오는 글이다)**

1. `docs/ARCHITECTURE.md`

   찾을 글:
   ```text
   마감을 안 쓰는 근무표는 취합 중 회차 화면에 부서마다 [표 입력] 버튼과 생성 버튼이 나란히 있다.
   ```
   바꿀 글:
   ```text
   마감을 안 쓰는 근무표는 취합 중 회차 화면에 부서마다 [표 입력] 버튼과 생성 버튼이 나란히 있다(빈 평일이 있으면 첫 [표 입력]이, 없으면 생성 버튼이 진한 버튼).
   ```

2. `docs/ARCHITECTURE.md`

   찾을 글:
   ```text
     - **1단계 임시 기준** `boards.legacy_admin_entry(board)`(= 마감을 안 쓰는 근무표): 옛 직접 입력 근무표의 문구·확인창(기간 줄이기·[확정]·[확정 취소])·채우기 버튼·빈 평일 경고(막지 않음, 빈 평일이 있으면 첫 [표 입력]이 진한 버튼)·입력 현황 숨김·글 도움말, 입력 그룹 자동 생성과 부서 폼의 입력 담당자 금지를 지금처럼 고른다. 마감을 쓰는 근무표는 빈 평일이 있으면 생성을 막는다. 버튼 글자·[생성 방식]·[재생성]·배정 횟수 표도 이 기준으로 고른다. 2단계에서 화면·서비스 자리를(그때부터 켜진 장중관제 정의라는 데이터 기준), 3단계에서 입력 그룹 자리와 함수를 지운다.
   ```
   바꿀 글:
   ```text
     - **모든 근무표에 같은 규칙**(근무표 통합 2단계): 버튼 글자·[재생성]·[생성 방식](숫자·자격 문장은 관제 정의에서 만든다, `shifts.gen_help`)·배정 횟수 표는 켜진 장중관제 정의라는 데이터로 정한다. 빈 평일은 생성을 막지 않고 경고만 한다. 회차 화면 켠 취합 중·마감에 "⚠ 출근표가 비어 있는 날: <부서 이름> n일(11/16~11/20) · …"(이어진 평일은 묶는다, `shifts.day_spans`), 그 상태에서 생성할 수 있을 때만 "[<생성 버튼>] 버튼은 누를 수 있지만 그날 그 부서는 근무자가 없습니다."를 붙인다(IT 취합 중에는 붙이지 않는다). 빈 날이 있으면 생성 버튼은 테두리 버튼이고 누르면 "출근표가 비어 있는 부서가 있는 날이 N일 있습니다. …계속할까요?" 확인창(빈 날이 없으면 확인창 없음), 생성 뒤 메시지에 부서별 빈 날. 부서별 입력 현황은 모든 근무표에 부서 이름으로 보이고 취합 중이면 부서마다 [표 입력] 버튼(누를 자리 44px 이상)이 붙는다. [기간 저장]은 기간을 줄일 때만 확인창을 띄운다. 생성됨에서 나가는 확인창은 하나이고 그 회차에 **실제로 있는 배정**으로 만든다(`leave_generated_confirm`: "생성 결과(장중관제·점심당번 배정)가 지워지고 출근표는 그대로 남습니다. 계속할까요?", 하나만 있으면 그것만, 없으면 "출근표는 그대로 남습니다. 계속할까요?"), 옮기기 상자 설명도 같은 말. 확인창 글은 `escapejs` 로 넣는다. 끈 단계에 남은 회차는 "이 단계는 지금 쓰지 않습니다. 아래 [다른 상태로 옮기기]를 눌러 옮기세요." 한 줄과 펼쳐진 상자. 오류·안내 글은 그 근무표의 **켠** 단계 이름을 쓴다("기간은 '작성 중' 단계에서만…", "'입력 중'(으)로만 옮길 수…", "'마감'인 회차만 장중관제 생성할 수…", "'확정'인 회차만 배포할 수…", "'생성됨' 상태로 바꿨습니다. 근무표 화면에는 배포한 뒤에 보입니다."). 입력 표의 [← 회차 화면으로] 링크는 그 근무표 관리자에게만.
     - 1단계 임시 기준 `boards.legacy_admin_entry(board)`(= 마감을 안 쓰는 근무표)는 입력 그룹 자동 생성(`Department.save`)과 부서 폼의 입력 담당자 금지에만 남는다. 그래서 관리 화면 단계 칸도 2단계까지 읽기 전용이다(3단계에서 첫 입력 담당자를 넣을 때 그룹을 만들기로 바꾸며 함수를 지우고 단계 편집을 연다).
   ```

3. `docs/ARCHITECTURE.md`

   찾을 글:
   ```text
   마감을 안 쓰는 근무표(1단계 임시 기준)의 취합 중 회차에는 주마다 **[2주 전 기준으로 채우기]**
   ```
   바꿀 글:
   ```text
   취합 중 회차의 입력 표에는 근무표와 상관없이 주마다 **[2주 전 기준으로 채우기]**
   ```

4. `docs/ARCHITECTURE.md`

   찾을 글:
   ```text
   마감을 쓰는 근무표는 그 근무표 부서마다 평일이 다 차야 한다(IT = 4개 부서. 마감을 안 쓰는 근무표는 빈 평일을 경고만 한다, 1단계 임시 기준). 장중관제는 그 회차 출근 행이 하나도 없는 날을 빼고 만든다.
   ```
   바꿀 글:
   ```text
   빈 평일(그 근무표 부서 중 출근표가 없는 평일)은 모든 근무표에서 막지 않고 부서별 빈 날을 경고 한 줄로 알린다. 장중관제는 그 회차 출근 행이 하나도 없는 날을 빼고 만든다(일부 부서만 빈 날은 다른 부서 사람으로 채우고, 후보가 모자라면 지금처럼 못 채운 칸 표).
   ```

5. `docs/ARCHITECTURE.md`

   찾을 글:
   ```text
   마감을 안 쓰는 근무표의 관리자에게는 영상 없이 글 도움말(`help.TEXTS`·`STEPS["direct"]`, 1단계 임시 기준)이 하나 더 보인다.
   ```
   바꿀 글:
   ```text
   근무표 관리자에게는 영상 없이 글 도움말 "회차 운영"(`help.TEXTS`·`STEPS["period"]`)이 하나 더 보이고, 맨 앞에 내가 관리하는 근무표마다 단계 줄("IT 당번표: 작성 중 → 취합 중 → 마감 → 생성됨 → 배포됨")이 붙는다(`help.texts_for`). 출근표 입력 글(`STEPS["manager"]`)에는 영상 뒤에 생긴 채우기 버튼 설명이 한 줄 있다.
   ```

6. `docs/OVERVIEW.md`

   찾을 글:
   ```text
   [확정]하면 배포할 수 있다. 확정을 되돌리려면 [확정 취소].
   ```
   바꿀 글:
   ```text
   [확정]하면 배포할 수 있다. 확정을 되돌리려면 [확정 취소]. 주마다 채우기 버튼과 "빈 평일은 경고만(생성은 막지 않고, 누를 때 빈 날 수를 묻는다)"은 IT 를 포함한 모든 근무표에 같다.
   ```

7. `docs/OPERATIONS.md`

   찾을 글:
   ```text
   도움말 "직접 입력 근무표 운영(입력 중·확정·배포)"이 보인다.
   ```
   바꿀 글:
   ```text
   도움말 "회차 운영(단계·출근표·생성·배포)"이 보인다.
   ```

8. `docs/OPERATIONS.md`

   찾을 글:
   ```text
   화면마다 할 일은 사이트 [도움말]의 "직접 입력 근무표 운영"에 있다.
   ```
   바꿀 글:
   ```text
   화면마다 할 일은 사이트 [도움말]의 "회차 운영"에 있다.
   ```

9. `docs/OPERATIONS.md`

   찾을 글:
   ```text
   - [확정]을 누르면 "확정했습니다…"가 나온다. 아직 근무표 화면에는 보이지 않는다. 회차 화면의 경고(입력하지 않은 평일)를 보고 [배포…]로 간다.
   ```
   바꿀 글:
   ```text
   - [확정]을 누르면(출근표가 빈 날이 있으면 그 날 수를 먼저 묻는다) "'확정' 상태로 바꿨습니다. 근무표 화면에는 배포한 뒤에 보입니다."가 나온다. 출근표가 비어 있는 날이 있으면 바로 아래 경고("출근표가 비어 있는 날이 있습니다: …")를 보고 [배포…]로 간다.
   ```

10. `docs/OPERATIONS.md`

   찾을 글:
   ```text
   회차 화면의 "아직 입력하지 않은 평일" 경고로도 확인한다.
   ```
   바꿀 글:
   ```text
   회차 화면의 "⚠ 출근표가 비어 있는 날" 경고로도 확인한다.
   ```

11. `docs/OPERATIONS.md`

   찾을 글:
   ```text
   - nginx 를 켜 둔 서버는 이 묶음을 마친 뒤
   ```
   바꿀 글:
   ```text
   - **근무표 통합 2단계로 올릴 때**: 마이그레이션이 없다(`migrate` 는 "No migrations to apply"). **IT 근무표에 취합 중·마감·생성됨 회차가 하나도 없을 때(작성 중·배포됨만, 보통 배포 직후 ~ 다음 [취합 열기] 전) 올린다**. 아래가 아무것도 안 나오면 올려도 된다.
       `sudo -u duty sqlite3 -readonly data/db.sqlite3 "SELECT p.id, p.status FROM duty_period p JOIN duty_board b ON b.id = p.board_id WHERE b.code = 'it' AND p.status IN ('collecting', 'closed', 'generated');"`
     - **올리기 직전에 확인 ②를 다시 돌린다**(1단계 전에 적어 둔 값이 아니라 지금 값으로 공지와 진행을 정한다). 작성 중·마감을 둘 다 끈 근무표마다 `코드|켜진 관제 정의 수|관제 배정 행 수`:
       `sudo -u duty sqlite3 -readonly data/db.sqlite3 "SELECT b.code, (SELECT COUNT(*) FROM duty_boardshift s WHERE s.board_id = b.id AND s.active = 1 AND s.key LIKE 'slot%'), (SELECT COUNT(*) FROM duty_dutyassignment a JOIN duty_period p ON p.id = a.period_id WHERE p.board_id = b.id AND a.cell LIKE 'slot%') FROM duty_board b WHERE b.use_draft = 0 AND b.use_close = 0;"`
       - 켜진 관제 정의가 1 이상인 근무표: 2단계부터 [확정] 대신 [장중관제 생성]이, 생성됨에서 [재생성]이, [생성 방식] 버튼·상자가 보이고 생성하면 관제를 배정한다. 그 근무표가 관제를 쓰지 않으면 올리기 전에 관리 화면 근무표에서 그 관제 줄의 "사용"을 끈다(그러면 아래 경우가 된다). 쓰면 그 근무표 관리자에게 공지한다.
       - 켜진 관제 정의는 0 이고 관제 배정 행만 남은 근무표: 버튼은 그대로다([확정]·[확정 취소] 등). 그 행이 남은 회차 화면에 장중관제 배정 횟수 표가 새로 보이고, 생성됨에서 나가는 확인창이 "생성 결과(장중관제… 배정)가 지워지고 출근표는 그대로 남습니다."로 바뀐다(남은 관제 배정도 지운다는 뜻). 그 근무표 관리자에게 공지한다.
       - 모두 0 이면 해당 없음. 1 이상인 근무표가 있는데 그 관리자에게 미리 알릴 수 없으면 올리지 않는다.
     - IT 에 보이는 변화: 마감 회차에 출근표가 빈 부서·날이 있어도 [장중관제 생성]이 막히지 않는다(테두리 버튼, 누르면 빈 날 수를 묻는 확인창, 생성 뒤 "출근표가 비어 있는 날이 있습니다: UI 1일(11/13). …" 경고). 회차 화면 빈 날 경고가 부서 이름·날 수로 바뀐다. 모든 부서의 입력 표에 주마다 [지난주와 같게], 입력 근무조가 3개인 부서는 [2주 전 기준으로 채우기]도. 회차 화면 "부서별 입력 현황"이 부서 이름으로 보이고 취합 중이면 부서마다 [표 입력] 버튼, 기간을 줄일 때 확인창. 일부 오류·안내 글이 단계 이름을 쓰는 꼴로(예: "'마감'인 회차만 장중관제 생성할 수 있습니다.", "'생성됨' 상태로 바꿨습니다. 근무표 화면에는 배포한 뒤에 보입니다."). 입력 표 CSV 버튼 글 "CSV 올리기(이 표 전체 교체)", 글 도움말은 "회차 운영" 하나로(모든 근무표 관리자에게). 작성 중·마감을 끈 근무표의 장중관제 쪽 변화는 위 확인 ② 결과에 따른다. 시장운영실: 회차 화면에 입력 현황이 생기고, 빈 평일 경고 글 모양이 바뀌고, 출근표가 다 차 있으면 [확정]을 누를 때 묻지 않는다. 관리 화면 근무표 단계 칸은 그대로 읽기 전용이다. 알림 문구는 그대로다.
     - 되돌리기는 위 "롤백"에서 코드만 되돌리면 된다(마이그레이션이 없고 DB 는 그대로. 단계 칸도 2단계에서 고칠 수 없어 바뀐 설정이 없다).
     - 공지(지금 쓰는 메신저로). 알릴 사람: IT 근무표 관리자·입력 담당자, 시장운영실 근무표 관리자, 확인 ②에 나온 모든 근무표의 관리자. "회차 화면이 조금 바뀌었습니다. 출근표가 빈 날이 있어도 [장중관제 생성]을 누를 수 있고, 누르기 전에 빈 날을 알려 줍니다. 입력 표에 주마다 [지난주와 같게] 버튼이 생겼고, 근무조가 셋인 부서는 [2주 전 기준으로 채우기]도 있습니다(눌러도 저장은 [표 저장]으로만 됩니다). 시장운영실: 출근표가 다 차 있으면 [확정]을 누를 때 묻지 않고 바로 확정됩니다(고칠 것이 있으면 [확정 취소]). 회차 화면에 부서별 입력 현황이 생겼습니다." 확인 ②에 나온 근무표의 관리자에게는 경우에 맞는 한 줄을 덧붙인다 — 켜진 관제 정의가 있으면 "회차 화면의 [확정] 버튼이 [장중관제 생성]으로 바뀌고 [재생성]·[생성 방식]이 생겼습니다(생성하면 장중관제를 배정합니다).", 관제 배정만 남았으면 "버튼은 그대로입니다. 예전 장중관제 배정이 남은 회차 화면에 배정 횟수 표가 보이고, [확정 취소] 때 그 배정도 지운다고 묻습니다."
   - nginx 를 켜 둔 서버는 이 묶음을 마친 뒤
   ```

12. `docs/PRINCIPLES.md` "결정 기록" 표 맨 끝에 한 줄:

   ```text
   | 2026-11-17 | 빈 평일은 IT 를 포함한 모든 근무표에서 경고만 한다(생성은 막지 않고 빈 날이 있을 때만 날 수를 묻는 확인창, 관제는 출근 행이 하나도 없는 날만 뺀다). 채우기 버튼·부서별 입력 현황·기간 줄이기 확인창·생성됨에서 나가는 확인창·단계 이름 문구·글 도움말을 모든 근무표에 같게 한다(관리 화면 단계 칸은 3단계까지 읽기 전용). 2단계는 IT 회차가 취합 중·마감·생성됨이 아닐 때 올린다 | 사용자 결정: 근무표마다 다른 규칙을 두지 않는다(다른 부서가 늘어도 같은 화면). 빈 날째 생성해도 배포 미리보기·배포 취소로 되돌릴 수 있고, 경고와 확인창에 날짜·날 수가 나온다. 회차 중간에 규칙이 바뀌지 않게 올리는 때를 정한다 |
   ```

- [ ] **Step 2: 바뀐 곳을 확인한다**

Run: `git grep -n -E "legacy_admin_entry|1단계 임시 기준" -- docs/ARCHITECTURE.md docs/OVERVIEW.md docs/OPERATIONS.md`
Expected: `ARCHITECTURE.md` 의 세 곳만 — "Board" 항목(입력 그룹 자동 생성), "근무표와 근무 정의" 항목(부서 폼 입력 담당자 금지), "회차" 절의 "1단계 임시 기준 … 입력 그룹 자동 생성과 부서 폼에만 남는다"(3단계에서 지운다). `STEPS["direct"]` 는 나오지 않는다.
Run(올리기 직전 확인 ② 쿼리가 1단계 뒤 스키마에서 도는지, 실DB 는 열지 않는다):
```bash
W=$(mktemp -d); export DUTY_ENV_FILE= DUTY_DEBUG=1 DUTY_DATA_DIR=$W/data
.venv/bin/python manage.py migrate -v0
sqlite3 -readonly $W/data/db.sqlite3 "SELECT b.code, (SELECT COUNT(*) FROM duty_boardshift s WHERE s.board_id = b.id AND s.active = 1 AND s.key LIKE 'slot%'), (SELECT COUNT(*) FROM duty_dutyassignment a JOIN duty_period p ON p.id = a.period_id WHERE p.board_id = b.id AND a.cell LIKE 'slot%') FROM duty_board b WHERE b.use_draft = 0 AND b.use_close = 0;"
Q="SELECT b.code, (SELECT COUNT(*) FROM duty_boardshift s WHERE s.board_id = b.id AND s.active = 1 AND s.key LIKE 'slot%'), (SELECT COUNT(*) FROM duty_dutyassignment a JOIN duty_period p ON p.id = a.period_id WHERE p.board_id = b.id AND a.cell LIKE 'slot%') FROM duty_board b WHERE b.use_draft = 0 AND b.use_close = 0;"
.venv/bin/python manage.py shell -c "
from datetime import date, time
from duty.models import Board, BoardShift, Department, Period, DutyAssignment, User
b = Board.objects.create(code='ops', name='가상운영', use_draft=False, use_close=False, step_collecting='입력 중', step_generated='확정')
BoardShift.objects.create(board=b, key='dawn', name='07:30', start=time(7, 30), end=time(16, 30))
BoardShift.objects.create(board=b, key='slot0', name='점검', start=time(10), end=time(11), eligible_shifts=['dawn'])
d = Department.objects.create(code='OPS', name='가상운영', shifts='dawn', board=b)
u = User.objects.create_user('ops01', password=None, name='가상가', department=d, type='직원')
p = Period.objects.create(board=b, name='가상', start_date=date(2026, 11, 16), end_date=date(2026, 11, 20), status='generated')
DutyAssignment.objects.create(period=p, date=date(2026, 11, 16), member=u, cell='slot0')"
sqlite3 -readonly $W/data/db.sqlite3 "$Q"
.venv/bin/python manage.py shell -c "from duty.models import BoardShift; BoardShift.objects.filter(key='slot0').update(active=False)"
sqlite3 -readonly $W/data/db.sqlite3 "$Q"
rm -rf $W; unset DUTY_ENV_FILE DUTY_DEBUG DUTY_DATA_DIR
```
Expected: 첫 쿼리는 오류 없이 아무것도 안 나온다(새 DB 에는 IT 근무표뿐이다). 가짜 근무표를 넣은 뒤 `ops|1|1`, 관제 정의를 끈 뒤 `ops|0|1`(두 서브쿼리와 공지의 두 경우가 맞게 갈린다). 가짜 데이터는 임시 DB 에만 있고 바로 지운다. 모델 칸 이름이 다르면(이 계획 Task 2·5 기준) 그에 맞춘다.
Run: `.venv/bin/pytest -W error -q`
Expected: `1312 passed`

- [ ] **Step 3: 커밋**

```bash
git add docs/
git commit -m "$(cat <<'EOF'
docs: 근무표 통합 2단계(모든 근무표에 같은 회차 규칙, IT 회차 사이에 올리기와 공지·롤백)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
EOF
)"
```

- [ ] **Step 4: 2단계 PR**

전체 테스트(`1312 passed`, 경고 0)와 `makemigrations --check` 결과를 확인한 **뒤에** 따로 push·PR. PR 본문: IT 에 보이는 변화 목록과 공지 글(OPERATIONS "근무표 통합 2단계로 올릴 때"와 같은 글), 올리는 때(IT 근무표에 취합 중·마감·생성됨 회차가 없을 때)와 확인 쿼리, 올리기 직전 확인 ② 다시 돌리기와 경우별 공지(켜진 관제 정의 / 관제 배정만), `tests/snapshots/` 의 바뀐 파일(Task 8 의 17개 + Task 9 의 `help-admin`)과 그대로인 파일(`periods`·`collect-index`·`roster-mine`·`roster-month`·`day`·`roster-other`), `tests/test_alarm_texts_it.py` 그대로 통과. Codex 최종 리뷰를 받은 뒤 머지한다.

---

## 자체 점검(최종 대조표)

| 확인할 것 | 어디서 |
|---|---|
| 설계 12절 1단계: 첫 커밋 스냅샷·`move` 문구 단언 | Task 1(기준 24개, 다시 쓰기는 일부러 실패) |
| 5.1 단계 칸·제약, 1·2단계 관리 화면 읽기 전용 | Task 2(칸·제약), Task 5(폼·읽기 전용) |
| 5.2 단계 규칙(4조합 매개변수) | Task 2 |
| 5.3 1단계(부서 하나 삭제, 입력 그룹·부서 폼은 임시 기준) | Task 5 |
| 5.4 버튼 이름·떼기 못 하는 이름·버튼 글자 검사 | Task 4(`step_buttons`), Task 5(`bad_buttons`) |
| 6.1 "1" 자리 전부, 문구 그대로 | Task 2~5(문구는 `legacy_admin_entry` 로 고름) |
| 1단계 장중관제 갈래(버튼 글자·재생성·생성 방식·횟수 표)는 임시 기준, 생성 방식 글은 main 고정 글 | Task 4(관제 이력 테스트·스냅샷) |
| 확인창 동적 글 `escapejs`, 이름 뒤 조사 `josa` | Task 4, Task 8 |
| 0023 forward·거꾸로 규칙·왕복 | Task 2·5 |
| 10.3 확인 ①·② (②는 2단계 참고용, 관제 정의·관제 배정 수), 뒤 대조, 롤백 순서 | Task 6 |
| 6.1 "2" 자리: 문구·빈 평일 경고·채우기 | Task 7 |
| 6.1 "2" 자리: 관제 정의 기준·`gen_help`, ⚠ 줄·빈 날 확인창·입력 현황·끈 단계 안내·입력 표 | Task 8 |
| 5.4 `leave_generated_confirm`(실제 배정, 없음·관제·점심당번·둘 다 매개변수 테스트) | Task 8 |
| 글 도움말 하나·입력 담당 글 채우기 | Task 9 |
| 10.3 2단계 시점 쿼리·10.4 공지(시장운영실 관리자 포함)·롤백 | Task 10 |
| IT 알림 글자·hash 그대로(`test_alarm_texts_it.py` 수정 없음) | 모든 작업 |
| 이 계획 밖(3~5단계): 늦은 입력 그룹·함수 삭제·단계 편집 열기·[근무표 설정]·0024, 사람 칸, 겹쳐 보기·0025 | — |
