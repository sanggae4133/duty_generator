# 근무표 통합 3단계(근무표 설정: 관리자·입력 담당자·근무 정의와 부서·단계, 그룹 정리) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 근무표 관리자가 앱 안의 [근무표 설정](`/settings/?board=<code>`) 한 화면에서 그 근무표의 관리자·부서 입력 담당자·근무 정의와 부서 출근조·점심 시각·회차 단계를 고치게 하고, 그룹 관리자(`GroupKeeper`)·[그룹] 화면을 지운다(마이그레이션 0024). 입력 그룹은 첫 입력 담당자를 넣을 때 만들고(`Department.ensure_input_group`), 1단계 임시 기준 `legacy_admin_entry` 를 지우며 관리 화면·설정 화면의 단계 칸 편집을 연다. 근무표마다 재직 관리자 한 명 이상을 앱과 관리 화면 모두에서 지킨다.

**Architecture:** DB 쓰기는 새 서비스 `duty/services/board_settings.py` 한 곳(함수마다 `_require_admin` + 근무표 범위 검사 + 로그 한 줄 + `LogEntry`). 검사 폼은 관리 화면과 설정 화면이 함께 쓰도록 `duty/forms.py` 로 옮긴다(근무 정의 한 줄·근무표 전체, 회차 단계, 부서 출근조·점심 시각). 화면은 `duty/views/board_settings.py` 하나와 템플릿 하나: 칸(`<section id>`)마다 따로 저장하고 그 칸 앵커로 돌아오며 결과 메시지는 `messages` 의 `extra_tags`(칸 id)로 그 칸 안에 그린다. 재직 관리자 검사는 `boards.left_without_admin(users)` 하나를 앱과 관리 화면(사용자 편집·지우기)이 쓴다.

**Tech Stack:** Python 3.12, Django 5.2, SQLite(WAL, `IMMEDIATE`), pytest + pytest-django, Pico.css. 새 의존성 없음.

**Spec:** `docs/superpowers/specs/2026-11-17-boards-unify-design.md`(Codex 합의본). 이 계획 = 12절 "3. 근무표 설정(관리) + 그룹 정리". 참고: 5.1(단계 칸 편집 열기)·5.3(3단계 몫: 늦은 입력 그룹, `legacy_admin_entry` 삭제)·5.6(GroupKeeper)·6.1(`perms.kept_groups`·`services/groups.py` 삭제)·6.2(`board_settings` 함수 중 관리자·입력 담당자·근무 정의·단계)·7.1~7.4(화면, 사람 칸 빼고)·8(권한)·10.2(0024)·10.3(3단계 ①②)·10.4(3단계 공지)·11(테스트)·13(문서). **사람 칸(추가·고치기·퇴사·다시 재직·계정 발급/초기화, 5.7 계정 함수, `#people`)은 4단계 계획이다.**

## 판단한 것 (설계가 정하지 않았거나 해석이 필요한 곳, 컨트롤러 검토용)

1. **범위**: 사람 칸·[사람] 바로가기(`#people`)·`accounts.issue_account(revoke_links=)`·`deactivate`·`future_cells` 는 4단계다. 3단계 바로가기는 [관리자] [입력 담당자] [근무 정의와 부서] [회차 단계] 넷이고, 4단계가 맨 앞에 [사람]을 더한다. 글 도움말·공지의 "사람 추가·계정 발급은 슈퍼유저에게"도 4단계에서 바꾼다.
2. **주소는 설계 7.1 그대로 `/settings/?board=<code>`**(pk 없는 주소). 그래서 스냅샷 정규화기(`tests/test_snapshots.py` 의 pk 이름표)는 고칠 것이 없다. 설정 화면은 스냅샷에 넣지 않는다(새 화면이라 기준이 없고, 칸마다 테스트가 본다).
3. **스냅샷이 바뀌는 곳은 `help-admin` 하나(Task 8)**: 글 도움말 "근무표 설정"이 더해진다. 메뉴 [그룹] → [근무표 설정]은 `<header>` 안이라 정규화기가 보지 않는다. `<main>` 안에서 `/settings/`·`/groups/` 링크가 나오는 스냅샷 화면은 없다(도움말 글의 "[근무표 설정]"은 링크가 아닌 글자). 메시지 자리(`base.html`, `<main>` 안)의 조건이 바뀌지만 스냅샷 화면에는 메시지가 없어 글자가 같다. Task 1~7 은 스냅샷을 고치지 않고 통과해야 한다.
4. **늦은 입력 그룹과 테스트**: `Department.save` 가 그룹을 만들지 않으므로 `tests/conftest.py` 의 `depts` 픽스처가 부서마다 `ensure_input_group()` 을 부른다(운영 IT 부서처럼 그룹이 있는 상태). 그래서 `input_group.user_set` 에 기대는 기존 테스트 20곳은 그대로 통과한다. 사용법 영상 가짜 데이터(`tools/help_videos/seed.py`)도 한 줄(`ensure_input_group().user_set.add(manager)`).
5. **관리 화면 부서 폼의 이름 겹침**: 첫 담당자를 골라 그룹을 만들 때와 이름을 바꿀 때 모두 "같은 이름의 그룹이 이미 있습니다: …" 를 **이름 칸**에 붙인다(부서 이름을 바꾸면 풀리므로). 담당자 없이 만드는 새 부서는 그룹을 만들지 않으니 겹침을 보지 않는다. 저장(`save_related`)은 담당자를 골랐을 때만 `ensure_input_group()`.
6. **재직 관리자 검사 = `boards.left_without_admin(users) -> list[Board]`**(설계의 `active_admin_left(board, removing=user)` "같은" 함수): 관리 화면 일괄 지우기가 여러 사람을 한 번에 넘기므로 사람 목록을 받아 "재직 관리자가 남지 않는 근무표" 목록을 돌려준다. users 중 재직 관리자가 있는 근무표만 보므로, 이미 재직 관리자가 없는 근무표에서 퇴사한 관리자를 빼는 일은 막지 않는다(설계 10.3 ① 로 업그레이드 전에 0명 근무표를 없앤다).
7. **관리 화면 지우기 가드는 `UserAdmin.get_deleted_objects`**(설계의 `delete_model`·`delete_queryset` 대신): Django 의 한 명 지우기와 "선택한 사용자 삭제" 둘 다 이 함수가 돌려준 보호 목록이 비어야 지운다. 까닭("○○ 근무표에 재직 중인 관리자가 남지 않습니다. 먼저 다른 관리자를 넣으세요.")이 확인 화면의 보호 목록에 보이고 아무것도 지우지 않는다. `delete_model` 에서 막으면 Django 가 그 뒤 "삭제되었습니다" 성공 메시지를 띄운다.
8. **관리 화면 사용자 편집 검사는 `UserForm.clean`(Django `UserChangeForm` 상속)**: 저장 전 DB 상태로 판단하고, 재직을 끄면 "재직" 칸, 관리 그룹만 빼면 "그룹" 칸에 오류.
9. **`duty/forms.py` 로 옮기는 것**: `SHIFT_KEY_CHOICES`·`BoardShiftForm`·`BoardShiftFormSet`(내용 그대로)·`STEP_FIELDS`, 새 `StepsForm`(관리 화면 `BoardForm.clean` 의 단계 검사를 그대로 옮기고 `BoardForm` 이 물려받는다 — 설계 5.4 "같은 함수"), 새 `DeptShiftsForm`·`ShiftFormSet`(빈 추가 줄 하나, 시각은 `<input type=time>`; 관리 화면 인라인 위젯은 그대로)·`shift_forms(board, data)`. 기존 테스트의 `from duty.admin import STEP_FIELDS, BoardForm, DepartmentForm` 이 그대로 돌도록 admin 이 import 한다.
10. **"부서마다 켜진 입력 근무조 하나 이상"을 같은 저장의 부서 출근조로**: `BoardShiftFormSet.planned_depts`(`{부서 이름: 키들}`)를 설정 화면 서비스만 넣는다. 없으면 지금처럼 저장된 부서를 읽는다(관리 화면). 설정 화면 문구 꼬리는 "아래 부서에서 켜진 근무조를 하나 이상 체크하세요."(관리 화면은 지금 "부서의 출근조를 먼저 바꾸세요.").
11. **부서 덩어리 체크박스 = 그린 때의 켜진 근무조**(이름 + 시각, 시작 시각 순). 꺼진 근무조 키는 부서 저장 때 빠진다(관리 화면 부서 폼과 같은 결과).
12. **부서에서 근무조를 뺄 때 확인**: 설계대로 배포 전 회차(작성 중·취합 중·마감·생성됨)의 그 부서 사람·그 근무조 출근표 행을 센다. 단 **켜진 근무조만** 센다: 같은 저장에서 끄면서 빼면 꺼진 근무조 행은 표 저장 때 남으므로(`collect._kept_keys`) 묻지 않는다. 글: "운영 부서에서 '늦은'을 빼면 배포 전 회차(이번 회차)의 그 근무조 출근표 1행이 다음 표 저장 때 지워집니다. 그래도 저장하려면 [그래도 저장]을 누르세요."(여러 부서면 문장을 잇는다, `confirm` = 행 수 합).
13. **관제 정의를 끌 때 경고**는 설계 글의 "생성됨 회차" 자리에 그 근무표 생성됨 단계 이름을 쓴다(시장운영실이면 "확정 회차(…)"). 회차·정의마다 한 줄.
14. **"아직 부서에 배정되지 않은 근무조" 경고는 그릴 때마다 계산**한다(저장 직후만이 아니라 조건이 남아 있는 동안 늘 보인다). 버튼: 근무 정의 카드 아래 테두리 [저장] + 부서 덩어리 아래 큰 주 버튼(배정 안 된 근무조가 있으면 [부서 저장], 확인 중이면 [그래도 저장], 아니면 [저장]) — 같은 폼이라 어느 것이든 전체를 저장한다.
15. **오류·확인은 다시 그리기, 성공은 redirect**: 근무 정의와 부서·단계 칸이 오류(또는 행 수 확인)면 redirect 하지 않고 보낸 값 그대로 다시 그린다(다른 칸 입력은 건드리지 않는다). 폼 `action` 에 `#shifts`·`#steps` 가 있어 브라우저가 그 칸으로 간다. 관리자·입력 담당자 칸은 늘 redirect(`?board=<code>#admins` 등).
16. **칸 안 메시지**: `messages` 의 `extra_tags` = 칸 id, `_section_msgs.html` 이 그 칸 제목 바로 아래에 그리고 `base.html` 은 `extra_tags` 가 없는 메시지만 그린다. 단계 칸은 접힌 `<details>` 라 그 칸 메시지가 있거나 폼 오류로 다시 그릴 때 펼쳐 그린다.
17. **미리보기는 저장된 단계로**(오류로 다시 그릴 때도): "저장된 단계: 입력 중 → 확정 → 배포됨", "버튼: [확정] [확정 취소] [배포…]" — 회차 화면과 같은 `Board.step_buttons(켜진 관제 정의 유무)` 글자를 진행 순서([열기]·[마감]·생성·[… 취소]·[재생성]·[배포…])로.
18. **나 자신을 빼면** 그 근무표 설정에 더 들어올 수 없으므로 다른 관리 근무표가 있으면 `/settings/`, 없으면 근무표 화면(`/`)으로 보내고 메시지는 맨 위에("… 관리자에서 나를 뺐습니다.").
19. **관리 화면 근무표 저장에도 끈 단계 안내**(`board_settings.stranded`, 설정 화면과 같은 글): 단계를 고치는 곳이 둘이 되므로.
20. **`LogEntry` 대상**: 관리자·입력 담당자는 그 사람(`object_repr` = 아이디), 단계·근무 정의와 부서 저장은 그 근무표(`object_repr` = code). 동작 이름: "관리자 넣기"·"관리자 빼기"·"<부서 코드> 입력 담당자 넣기"·"<부서 코드> 입력 담당자 빼기"·"회차 단계 저장"·"근무 정의·부서 저장". 로그 `board <code>: <동작> <대상> by <아이디>`.
21. **접근**: 어느 근무표의 관리자도 아니면 403(다른 관리 화면과 같은 `admin_required`), 관리자이지만 그 근무표 관리자가 아니면 404(설계 7.1, 회차 화면과 같은 방식). POST 의 근무 정의 id(`shifts-N-id`)·부서 칸(`d-<코드>-…`)·사람·부서가 그 근무표 것이 아니면 404(서비스도 `PermissionDenied`).
22. **0024** 는 `makemigrations` 가 만든 `DeleteModel` 에 설계 10.2 의 뜻을 docstring 으로 단다. 업그레이드 확인 ①②는 0023 상태 임시 DB 에 가짜 그룹 관리자 행을 넣어 `sqlite3 -readonly` 로 돌렸다(열 이름 맞음, 실명 열 없음).
23. 글 도움말 "근무표 설정"(`STEPS["settings"]`)에는 근무표별 단계 줄을 붙이지 않는다(`texts_for` 가 "회차 운영"에만).

## Global Constraints

- **1단계 스냅샷 기준 규칙은 그대로**: `tests/snapshots/*.html` 은 Task 8 에서 `help-admin.html` 하나만 다시 쓴다(`DUTY_SNAPSHOT_WRITE=1` 실행은 다시 쓴 뒤 일부러 실패하고, 변수 없이 다시 돌려 통과해야 한다. 값은 정확히 `"1"`). Task 1~7 은 기준을 고치지 않고 통과한다. IT 알림 문구·hash(`tests/test_alarm_texts_it.py`)는 고치지 않고 통과한다.
- 각 작업이 끝난 시점에 `.venv/bin/pytest -W error -q` 전체가 통과한다(경고 0개). 기대 테스트 수는 참고값(지금 이 브랜치 출발점 5f3a561 **1326 passed**).
- TDD(테스트를 먼저 쓰고 실패를 확인한 뒤 구현). DB 를 바꾸는 규칙은 `duty/services/`(뷰·명령에서 모델을 직접 고치지 않는다. 관리 화면의 Django 기본 저장·`Department.ensure_input_group` 모델 메서드는 예외로 둔다 — 그룹 만들기는 모델 불변식이라 모델에). 순수 모듈(`shifts`·`generator`·`csv_io`·`ics`·`alarms/`(senders 제외)·`market_days`)에는 ORM 없음.
- "오늘"은 `from . import perms` 후 `perms.today()`. 정해진 값 칸은 `choices` + DB `CheckConstraint`, 기록을 남길 FK 는 `PROTECT`. 마이그레이션 파일은 지우지 않는다. 3단계 새 마이그레이션은 `0024_delete_groupkeeper` 하나(Task 7). 작업마다 `DUTY_DEBUG=1 DUTY_ENV_FILE= DUTY_DATA_DIR=$(mktemp -d) .venv/bin/python manage.py makemigrations duty --check --dry-run` → "No changes detected in app 'duty'".
- 0024 거꾸로는 빈 표(거부하지 않는다). 3단계 롤백은 업그레이드 전 백업 복원만 지원한다(OPERATIONS).
- **실명·비밀값**: 로그·`LogEntry`·메시지에 실명을 넣지 않는다(아이디·부서 코드·근무표 code 만). 테스트 이름은 가상("가상하나" 등). `data/`, DB 파일, `.superpowers/`, `.env` 는 열지 않는다.
- 화면 문구·오류 메시지는 한국어. 커밋 메시지는 `feat:`/`fix:`/`docs:`/`style:` + 한국어 요약, 끝에 아래 두 줄:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
  ```
- 운영은 단순하게: 새 deploy 파일·셸 스크립트·타이머를 만들지 않는다. 정적 파일은 CDN 없이(새 CSS 는 템플릿 안 `<style>`).
- 화면을 바꾸는 작업(Task 1 관리 화면, Task 3 관리 화면 사용자, Task 5·6 설정 화면, Task 7 메뉴, Task 8 도움말)은 테스트 통과만으로 끝내지 않고 아래 "브라우저 확인 준비"대로 띄운 가짜 데이터에서 PC 1400px·휴대폰 390px, 글씨 **아주 크게**(오른쪽 위 [가] 두 번), **다크 모드**(오른쪽 위 ◐)로 본다. 모든 브라우저 단계에서 콘솔 `document.documentElement.scrollWidth > innerWidth` 가 `false`(가로 넘침 없음). 보는 사람은 시력이 좋지 않고 변화를 싫어하는 60세 가까운 관리자다: 화면마다 진한 버튼 하나, 누름 영역 44px 이상.
- PR 은 그 단계의 문서(ARCHITECTURE·OPERATIONS·OVERVIEW·DEVELOPMENT·PRINCIPLES 결정 기록)를 같은 PR 에서 고친다(Task 8). 계획·구현·최종 Codex 리뷰(읽기 전용, DB·`data/`·`.superpowers/` 를 열지 말라고 지시)와 테스트 통과 확인 뒤 머지한다(테스트 결과 확인과 `gh pr merge` 를 한 명령으로 잇지 않는다).

### 브라우저 확인 준비(화면 작업 공통)

가짜 데이터만 쓰는 임시 폴더에서 띄우고, 끝나면 서버를 PID 로 끄고 폴더를 지운다(1·2단계 계획과 같은 준비, Task 1~8 어느 상태에서도 돈다).

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
(사본에서 Task 8 상태로 돌려 "운영팀 준비 끝"과 `/settings/`·`/settings/?board=ops` 200 을 확인했다: IT 카드 20개(근무 정의 15 + 빈 줄 1 + 부서 4), 운영팀 6개.)

로그인: `admin` / `Demo-pass-123`(슈퍼유저 + IT·운영팀 관리 그룹), `member` / `Demo-pass-123`(일반), `manager` / `Demo-pass-123`(IT 매칭엔진실 입력 담당). 관리 화면은 `http://127.0.0.1:8795/admin/`.

끝나면:
```bash
kill $(cat $W/server.pid); rm -rf $W; unset DUTY_ENV_FILE DUTY_DEBUG DUTY_DATA_DIR
```

## 작업 순서

브랜치: `feat/boards-unify-3`(2단계 PR 머지 뒤 main 에서, 또는 2단계 브랜치 위에). PR 제목: `feat: 근무표 설정 화면(관리자·입력 담당자·근무 정의와 부서·단계)과 그룹 관리자 정리(근무표 통합 3단계)`.

| Task | 내용 | 마이그레이션 | 테스트 수(참고) |
|---|---|---|---|
| 1 | 늦은 입력 그룹(`ensure_input_group`, 저장은 그룹을 만들지 않음), 관리 화면 부서 폼 금지 검사 지움, `legacy_admin_entry` 삭제, 관리 화면 단계 칸 편집 열기 | 없음 | 1326 |
| 2 | `services/board_settings.py`: 관리자 넣기·빼기, 입력 담당자 넣기·빼기, `_audit`(로그 + `LogEntry`), `boards.left_without_admin` | 없음 | 1341 |
| 3 | 관리 화면 재직 관리자 한 명 이상(사용자 편집 폼·지우기) | 없음 | 1345 |
| 4 | `duty/forms.py`(근무 정의 폼 옮김, `StepsForm`·`DeptShiftsForm`·`ShiftFormSet`·`shift_forms`), `save_steps`·`save_shifts`·`stranded`·`NeedsConfirm`, 관리 화면 끈 단계 안내 | 없음 | 1360 |
| 5 | 설정 화면 1: 주소·메뉴·제목·근무표 링크·칸 바로가기·칸 안 메시지·관리자 칸·입력 담당자 칸 | 없음 | 1370 |
| 6 | 설정 화면 2: 근무 정의와 부서 칸(카드·부서 덩어리·배정 안 된 근무조 경고·[부서 저장]·[그래도 저장])·회차 단계 칸(접힘·미리보기·확인창) | 없음 | 1378 |
| 7 | 그룹 정리: `GroupKeeper`·0024·[그룹] 화면·`services/groups.py`·`perms.kept_groups`·`GroupKeeperInline`, 관리 화면 글 | 0024 | 1370 |
| 8 | 글 도움말 "근무표 설정" + 스냅샷(`help-admin`) + 문서(ARCHITECTURE·OPERATIONS 3단계 확인·롤백·공지·OVERVIEW·DEVELOPMENT·PRINCIPLES) | 없음 | 1371 |

> 검증: Task 1~8 의 코드·문서 편집을 출발점 5f3a561 사본(`git archive`)에 그대로 넣어 확인했다. 저장소는 고치지 않았다. 결과: 작업마다 위 표의 수로 `.venv/bin/pytest -W error -q` 전체 통과, 경고 0개, `makemigrations duty --check --dry-run` → "No changes detected in app 'duty'", 새 DB 에서 `migrate` → `migrate duty 0022` → `migrate` 왕복(0024 포함)과 `migrate duty 0023` → `migrate`. 각 작업의 "실패 확인" 기대 결과도 사본에서 재현했다(앱 코드만 앞 작업 상태로 되돌려 새 테스트를 돌림). 스냅샷은 Task 1~7 내내 기준을 고치지 않고 통과했고 Task 8 에서 `help-admin.html` 만 16줄 늘었다. 문서 편집 스크립트의 "찾을 글"은 모두 한 번씩만 나왔다. 업그레이드 확인 ①②는 0023 상태 임시 DB 에 `sqlite3 -readonly` 로 돌렸다. 브라우저 확인은 사본에서 하지 않았다(가짜 데이터 셸이 돌고 설정 화면이 200 인 것까지만) — 각 작업의 브라우저 단계에서 사람이 본다.

---

### Task 1: 늦은 입력 그룹·`legacy_admin_entry` 삭제·관리 화면 단계 칸 편집 열기

> 범위: 설계 5.3 의 3단계 몫. `Department.save` 는 입력 그룹을 만들지 않고(이름을 바꿀 때 그룹 이름만 따라감), 첫 입력 담당자를 넣을 때 `Department.ensure_input_group()` 이 만든다. 관리 화면 부서 폼의 "직접 입력 근무표 부서는 입력 담당자 없음" 검사를 지우고 담당자를 고르면 그룹을 만든다. 임시 기준 `boards.legacy_admin_entry` 를 지우고, 그 기준 때문에 읽기 전용이던 관리 화면 근무표 단계 칸을 연다(설계 5.1). 보이는 변화: 관리 화면 근무표 편집에서 단계 칸을 고칠 수 있다, 관리 화면 부서에 담당자를 처음 고르면 그룹이 생긴다.

**Files:**
- Modify: `duty/models.py` — `from .errors import DutyError`, `Department.save`(그룹 만들기 지움), `Department.ensure_input_group` 더하기
- Modify: `duty/services/boards.py` — `legacy_admin_entry` 지우기
- Modify: `duty/admin.py` — `_input_users` docstring, `DepartmentForm.clean`, `DepartmentAdmin.save_related`, `BoardForm.clean` 주석, `BoardAdmin`(docstring·단계 묶음 설명·`get_readonly_fields`)
- Modify: `tools/help_videos/seed.py` — 입력 담당 넣는 줄
- Modify(테스트): `tests/conftest.py`(`depts`), `tests/test_boards_models.py`, `tests/test_board_steps.py`, `tests/test_admin_department.py`, `tests/test_admin_boards.py`

**Interfaces:**
- Consumes: `Department.input_group_name()`, `_renamed(obj)`, `boards.active_defs`
- Produces:
  - `Department.ensure_input_group() -> Group`: 입력 그룹이 없으면 "<부서 이름> 출근표 입력" 그룹을 만들어 그 부서에 단다(그 칸만 `update`). 이미 있으면 그대로 돌려준다. 같은 이름의 그룹이 있으면 `DutyError("같은 이름의 그룹이 이미 있습니다: <이름>. 슈퍼유저에게 그 그룹 이름을 바꿔 달라고 하세요.")`
  - `Department.save`: 입력 그룹을 만들지 않는다
  - `DepartmentForm.clean`: 첫 담당자를 고를 때(그룹 없음) 또는 그룹이 있는 부서 이름을 바꿀 때, 만들/바꿀 그룹 이름이 이미 있으면 이름 칸 오류 "같은 이름의 그룹이 이미 있습니다: <그룹 이름>"
  - `BoardAdmin.get_readonly_fields`: 저장된 근무표는 `["code", "group_link"]`(단계 칸을 고친다)
  - `boards.legacy_admin_entry` 없음

- [ ] **Step 1: 실패 테스트를 쓴다**

```diff
diff --git a/tests/conftest.py b/tests/conftest.py
index 84104fa..a9faa97 100644
--- a/tests/conftest.py
+++ b/tests/conftest.py
@@ -47,9 +47,13 @@ def lunch(it_board):
 
 @pytest.fixture
 def depts(it_board):
-    # order = 지금 근무표 부서 필터 순서(views/roster.py DEPT_ORDER: MEMS·TMCH·MD·UI = DEPTS 순서)
-    return {c: Department.objects.create(code=c, name=n, shifts=s, board=it_board, order=i)
-            for i, (c, n, s) in enumerate(DEPTS)}
+    # order = 지금 근무표 부서 필터 순서(views/roster.py DEPT_ORDER: MEMS·TMCH·MD·UI = DEPTS 순서).
+    # 운영 IT 부서처럼 입력 그룹이 있다(근무표 통합 3단계부터 Department.save 는 그룹을 만들지 않는다)
+    out = {c: Department.objects.create(code=c, name=n, shifts=s, board=it_board, order=i)
+           for i, (c, n, s) in enumerate(DEPTS)}
+    for d in out.values():
+        d.ensure_input_group()
+    return out
 
 
 @pytest.fixture
diff --git a/tests/test_admin_boards.py b/tests/test_admin_boards.py
index ddf98d4..6666ba7 100644
--- a/tests/test_admin_boards.py
+++ b/tests/test_admin_boards.py
@@ -164,7 +164,7 @@ def test_change_page_locks_code_steps_keys_and_has_no_delete(su_client, ops):
     board, *_ = ops
     body = su_client.get(reverse("admin:duty_board_change", args=[board.pk])).content.decode()
     assert 'name="name"' in body and 'name="code"' not in body and 'name="input_mode"' not in body
-    assert "회차 단계" in body and 'name="use_close"' not in body and 'name="step_collecting"' not in body  # 1단계: 읽기 전용
+    assert "회차 단계" in body and 'name="use_close"' in body and 'name="step_collecting"' in body  # 3단계: 단계 칸을 고친다
     assert reverse("admin:auth_group_change", args=[board.admin_group_id]) in body  # 관리 그룹 링크(그룹 관리자 지정)
     assert 'name="shifts-0-active"' in body and 'name="shifts-0-DELETE"' not in body
     assert '<select name="shifts-0-key"' in body and "disabled" in body.split('name="shifts-0-key"')[1].split(">")[0]
@@ -271,14 +271,16 @@ def test_bad_button_error_field(it_board, data, field, label):
     assert f.errors[field] == [f"버튼 이름이 비거나 다른 버튼과 같아집니다: [{label}]"]
 
 
-def test_saved_board_steps_are_read_only(su_client, ops):
-    """1단계: 저장된 근무표의 단계는 관리 화면에서 바꾸지 않는다(보낸 값은 무시, 설계 5.1). 3단계에서 연다."""
+def test_saved_board_steps_can_change(su_client, ops):
+    """3단계: 저장된 근무표의 단계도 관리 화면에서 고친다(설계 5.1). 버튼 글자 검사도 만들 때와 같다."""
     board, a, b = ops
-    data = change(board, [a, b]) | steps_form(board, use_draft="on", step_collecting="모으는 중")
-    r = su_client.post(reverse("admin:duty_board_change", args=[board.pk]), data)
+    url = reverse("admin:duty_board_change", args=[board.pk])
+    r = su_client.post(url, change(board, [a, b]) | steps_form(board, use_draft="on", step_collecting="모으는 중"))
     assert r.status_code == 302, errors(r)
     board.refresh_from_db()
-    assert (board.use_draft, board.step_collecting) == (False, "입력 중")
+    assert (board.use_draft, board.step_collecting) == (True, "모으는 중")
+    r = su_client.post(url, change(board, [a, b]) | steps_form(board, step_generated="됨"))
+    assert r.status_code == 200 and "버튼 이름이 비거나 다른 버튼과 같아집니다: []" in r.content.decode()
 
 
 # ── 그룹 관리자 ──
diff --git a/tests/test_admin_department.py b/tests/test_admin_department.py
index 65fe97e..1394b95 100644
--- a/tests/test_admin_department.py
+++ b/tests/test_admin_department.py
@@ -101,13 +101,15 @@ def test_saved_department_board_is_read_only(depts):
     assert form.save().board_id == depts["UI"].board_id  # 보낸 근무표는 무시된다(옮기기는 별도 기능)
 
 
-def test_new_department_input_group_name_clash(it_board):
-    """Department.save 가 만들 입력 그룹 이름이 이미 있으면 500 대신 칸 오류."""
+def test_new_department_input_group_name_clash(it_board, make_member):
+    """첫 담당자를 골라 만들 입력 그룹 이름이 이미 있으면 500 대신 칸 오류. 담당자가 없으면 그룹을 만들지 않아 통과."""
     Group.objects.create(name="품질 출근표 입력")
-    data = {"code": "QA", "name": "품질", "board": it_board.pk, "order": 9, "shifts": ["normal"], "managers": []}
+    data = {"code": "QA", "name": "품질", "board": it_board.pk, "order": 9, "shifts": ["normal"],
+            "managers": [make_member("가").pk]}
     form = DepartmentForm(data)
     assert not form.is_valid()
     assert "같은 이름의 그룹이 이미 있습니다: 품질 출근표 입력" in str(form.errors.get("name", ""))
+    assert DepartmentForm({**data, "managers": []}).is_valid()
 
 
 def test_rename_department_renames_input_group(su_client, depts):
@@ -147,13 +149,16 @@ def test_change_page_code_is_readonly(su_client, depts):
     assert Department.objects.count() == n and not Department.objects.filter(code="ZZ").exists()
 
 
-def test_direct_board_department_refuses_input_managers(it_board, make_member):
-    """직접 입력 근무표의 부서는 입력 그룹이 없다: 입력 담당자를 고르면 조용히 버리지 않고 칸 오류."""
+def test_first_manager_creates_input_group(su_client, it_board, make_member):
+    """마감을 끈 근무표의 부서도 담당자를 처음 고를 때 입력 그룹이 생긴다(근무표 통합 설계 5.3)."""
     ops = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
     BoardShift.objects.create(board=ops, key="normal", name="가운데", start="09:00", end="18:00")
     m = make_member("가", dept="UI")
-    data = {"code": "OPS", "name": "운영", "board": ops.pk, "order": 9, "shifts": ["normal"], "managers": [m.pk]}
-    form = DepartmentForm(data)
-    assert not form.is_valid()
-    assert "직접 입력 근무표의 부서는 입력 담당자가 없습니다" in str(form.errors.get("managers", ""))
-    assert DepartmentForm({**data, "managers": []}).is_valid()
+    data = {"code": "OPS", "name": "운영", "board": ops.pk, "order": 9, "shifts": ["normal"], "managers": []}
+    r = su_client.post(reverse("admin:duty_department_add"), data)
+    assert r.status_code == 302, r.content.decode()[:2000]
+    assert Department.objects.get(code="OPS").input_group_id is None  # 담당자 없이 만들면 그룹도 없다
+    r = su_client.post(reverse("admin:duty_department_change", args=["OPS"]), {**data, "managers": [m.pk]})
+    assert r.status_code == 302, r.content.decode()[:2000]
+    dept = Department.objects.get(code="OPS")
+    assert dept.input_group.name == "운영 출근표 입력" and list(dept.input_group.user_set.all()) == [m]
diff --git a/tests/test_board_steps.py b/tests/test_board_steps.py
index 96e6373..e76b063 100644
--- a/tests/test_board_steps.py
+++ b/tests/test_board_steps.py
@@ -7,7 +7,7 @@ from django.utils import timezone
 
 from duty.errors import DutyError
 from duty.models import Board, BoardShift, Commute, Department, DutyAssignment, Period, PeriodEvent, User
-from duty.services import boards, collect, periods, publish
+from duty.services import collect, periods, publish
 from duty.services.generate import run_generation
 from duty.shifts import Def, day_spans, gen_help, josa
 from tests.it_defs import IT_DEFS, OPS_STEPS
@@ -46,10 +46,6 @@ def test_ops_names_keep_turned_off_steps():
     assert [b.step_name(s) for s in S.values] == ["작성 중", "입력 중", "마감", "확정", "배포됨"]
 
 
-def test_legacy_rule_is_close_off():
-    assert boards.legacy_admin_entry(Board(use_close=False)) and not boards.legacy_admin_entry(Board())
-
-
 @pytest.mark.parametrize("field", ["step_draft", "step_collecting", "step_closed", "step_generated", "step_published"])
 def test_step_names_cannot_be_empty(db, field):
     with pytest.raises(IntegrityError), transaction.atomic():
diff --git a/tests/test_boards_models.py b/tests/test_boards_models.py
index e5bb39b..90a8955 100644
--- a/tests/test_boards_models.py
+++ b/tests/test_boards_models.py
@@ -5,6 +5,7 @@ import pytest
 from django.contrib.auth.models import Group
 from django.db import IntegrityError, transaction
 
+from duty.errors import DutyError
 from duty.models import Board, BoardShift, Department, GroupKeeper
 from duty.shifts import KEYS
 from tests.it_defs import IT_DEFS2, OPS_STEPS
@@ -35,14 +36,24 @@ def test_board_save_creates_admin_group(db):
     assert Group.objects.count() == before and b.admin_group.name == "운영팀2 근무표 관리"
 
 
-def test_department_save_creates_input_group_for_collect_board(it_board):
+def test_department_save_makes_no_input_group(it_board):
+    """입력 그룹은 첫 입력 담당자를 넣을 때 만든다(근무표 통합 설계 5.3). 마감을 쓰는 근무표도 같다."""
+    assert Department.objects.create(code="QA", name="품질", shifts="normal", board=it_board).input_group is None
+
+
+def test_ensure_input_group_makes_it_once(it_board):
     d = Department.objects.create(code="QA", name="품질", shifts="normal", board=it_board)
-    assert d.input_group.name == "품질 출근표 입력"
+    g = d.ensure_input_group()
+    assert g.name == "품질 출근표 입력" and Department.objects.get(pk="QA").input_group_id == g.pk
+    assert d.ensure_input_group() == g and Group.objects.filter(name="품질 출근표 입력").count() == 1
 
 
-def test_department_without_collect_board_has_no_input_group(db):
-    ops = Board.objects.create(code="ops", name="운영팀", **OPS_STEPS)
-    assert Department.objects.create(code="OPS", name="운영", shifts="normal", board=ops).input_group is None
+def test_ensure_input_group_name_clash(it_board):
+    Group.objects.create(name="품질 출근표 입력")
+    d = Department.objects.create(code="QA", name="품질", shifts="normal", board=it_board)
+    with pytest.raises(DutyError, match="같은 이름의 그룹이 이미 있습니다: 품질 출근표 입력. 슈퍼유저에게 그 그룹 이름을"):
+        d.ensure_input_group()
+    assert Department.objects.get(pk="QA").input_group_id is None
 
 
 def test_board_without_close_can_have_many_departments(it_board):
@@ -108,6 +119,7 @@ def test_board_save_without_rename_keeps_admin_group_name(it_board):
 
 def test_department_save_without_rename_keeps_input_group_name(it_board):
     d = Department.objects.create(code="QA", name="품질", shifts="normal", board=it_board)
+    d.ensure_input_group()
     Group.objects.filter(pk=d.input_group_id).update(name="옛 품질 그룹")
     d = Department.objects.get(pk="QA")
     d.order = 5
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_boards_models.py tests/test_admin_department.py tests/test_admin_boards.py tests/test_board_steps.py`
Expected: FAIL — `depts` 픽스처를 쓰는 테스트가 setup 에서 `AttributeError: 'Department' object has no attribute 'ensure_input_group'`(ERROR), `test_department_save_makes_no_input_group`·`test_ensure_input_group_*`·`test_change_page_locks_code_steps_keys_and_has_no_delete`·`test_saved_board_steps_can_change` FAIL.

- [ ] **Step 3: 구현한다**

```diff
diff --git a/duty/admin.py b/duty/admin.py
index 3350490..2ac2f9f 100644
--- a/duty/admin.py
+++ b/duty/admin.py
@@ -21,7 +21,7 @@ SHIFT_KEY_CHOICES = [(k, label) for k, label in BoardShift._meta.get_field("key"
 
 
 def _input_users(dept):
-    """부서 입력 그룹 멤버. 새 부서·직접 입력 근무표 부서(그룹 없음)는 빈 목록."""
+    """부서 입력 그룹 멤버. 입력 그룹이 없는 부서(새 부서, 담당자를 넣은 적 없는 부서)는 빈 목록."""
     return dept.input_group.user_set.all() if dept.input_group_id else User.objects.none()
 
 
@@ -69,14 +69,13 @@ class DepartmentForm(forms.ModelForm):
 
     def clean(self):
         c = super().clean()
-        board, name = c.get("board"), c.get("name")
-        # Department.save 가 만들거나 바꿀 입력 그룹 이름이 이미 있으면 Group.name unique 위반(500) 대신 칸 오류로
+        name = c.get("name")
+        # 입력 그룹은 첫 담당자를 고를 때 생기고(save_related → ensure_input_group), 부서 이름을 바꾸면 따라 바뀐다(설계 5.3).
+        # 그 그룹 이름이 이미 있으면 Group.name unique 위반(500) 대신 이름 칸 오류로
         group = f"{name} 출근표 입력"
-        has_group = self.instance.input_group_id or (board and not boards.legacy_admin_entry(board))  # 1단계 임시 기준
-        if c.get("managers") and board and boards.legacy_admin_entry(board):
-            self.add_error("managers", "직접 입력 근무표의 부서는 입력 담당자가 없습니다. 근무표 관리자가 입력합니다.")
-        if (name and has_group and "name" in self.changed_data  # 이름을 바꿀 때만 그룹 이름이 바뀐다
-                and Group.objects.exclude(pk=self.instance.input_group_id).filter(name=group).exists()):
+        makes = not self.instance.input_group_id and c.get("managers")
+        renames = self.instance.input_group_id and "name" in self.changed_data
+        if name and (makes or renames) and Group.objects.exclude(pk=self.instance.input_group_id).filter(name=group).exists():
             self.add_error("name", f"같은 이름의 그룹이 이미 있습니다: {group}")
         return c
 
@@ -109,8 +108,11 @@ class DepartmentAdmin(admin.ModelAdmin):
 
     def save_related(self, request, form, formsets, change):
         super().save_related(request, form, formsets, change)
-        if form.instance.input_group_id:  # 직접 입력 근무표의 부서는 입력 그룹이 없다
-            form.instance.input_group.user_set.set(form.cleaned_data["managers"])
+        dept, picked = form.instance, form.cleaned_data["managers"]
+        if picked:  # 첫 담당자를 고를 때 입력 그룹을 만든다(이름 겹침은 clean 이 먼저 막았다)
+            dept.ensure_input_group()
+        if dept.input_group_id:
+            dept.input_group.user_set.set(picked)
 
 
 class UserAddForm(forms.ModelForm):
@@ -298,7 +300,7 @@ class BoardForm(forms.ModelForm):
                 self.add_error(f, "단계 이름에 줄바꿈을 쓸 수 없습니다.")
             elif v and names.count(v) > 1:
                 self.add_error(f, f"단계 이름이 겹칩니다: {v}")
-        # 버튼 글자 검사(설계 5.4): 저장된 근무표는 단계 칸이 읽기 전용이라 만들 때만. 단계 칸 자체 오류가 없으면 본다
+        # 버튼 글자 검사(설계 5.4). 단계 칸 자체 오류가 없으면 본다
         if all(names) and not set(STEP_FIELDS) & set(self.errors):
             steps = Board(use_draft=c.get("use_draft"), use_close=c.get("use_close"), **dict(zip(STEP_FIELDS, names)))
             gen, slot = steps.step_buttons(False), steps.step_buttons(True)
@@ -320,7 +322,7 @@ class BoardForm(forms.ModelForm):
 
 @admin.register(Board)
 class BoardAdmin(admin.ModelAdmin):
-    """근무표(설계 4.2·4.3). code(boards.it_board() 가 IT 근무표를 찾는 열쇠)는 만든 뒤 바꾸지 않는다. 단계 칸은 1·2단계에서 만들 때만 정한다.
+    """근무표(설계 4.2·4.3). code(boards.it_board() 가 IT 근무표를 찾는 열쇠)는 만든 뒤 바꾸지 않는다. 단계 칸은 언제든 고친다(근무표 통합 3단계).
     지우기는 막는다. 관리 그룹은 Board.save 가 만들고, 그 그룹의 그룹 관리자는 '관리 그룹' 링크(그룹 화면)에서 정한다."""
     form = BoardForm
     list_display = ["name", "code", "step_line", "admin_group"]
@@ -335,11 +337,11 @@ class BoardAdmin(admin.ModelAdmin):
                 ("회차 단계", {"fields": ["use_draft", "use_close", *STEP_FIELDS], "description": (
                     "작성 중·마감을 끄면 그 단계를 건너뜁니다. 이름은 화면에 보이는 단계 이름이고, 버튼 이름은 단계 이름에서 "
                     "나옵니다(예: '취합 중' → [취합 열기]). IT = 둘 다 켬, 작성 중·취합 중·마감·생성됨·배포됨. "
-                    "시장운영실 = 둘 다 끔, 취합 중 '입력 중'·생성됨 '확정'. 저장한 근무표의 단계는 지금은 바꾸지 않습니다.")})]
+                    "시장운영실 = 둘 다 끔, 취합 중 '입력 중'·생성됨 '확정'. 바꾸면 진행 중인 회차의 단계 이름과 버튼이 바로 바뀌고, "
+                    "끈 단계에 남은 회차는 회차 화면의 '다른 상태로 옮기기'로 옮깁니다.")})]
 
     def get_readonly_fields(self, request, obj=None):
-        # 1단계: 저장된 근무표의 단계 칸은 읽기 전용(임시 기준 legacy_admin_entry 와 섞인 상태를 막는다, 설계 5.1). 3단계에서 연다
-        return [] if obj is None else ["code", "use_draft", "use_close", *STEP_FIELDS, "group_link"]
+        return [] if obj is None else ["code", "group_link"]
 
     @admin.display(description="단계")
     def step_line(self, obj):
diff --git a/duty/models.py b/duty/models.py
index b6fbf7c..846faa4 100644
--- a/duty/models.py
+++ b/duty/models.py
@@ -9,6 +9,7 @@ from django.db.models import F, Func, Q, Value
 from django.db.models.lookups import Exact
 
 from .csv_io import split_reason
+from .errors import DutyError
 from .shifts import (
     DEVELOPER, DUTY_KEYS, KEYS, LUNCH, REASONS, SHIFT_KEYS, STAFF, is_slot_cell, slot_index, weekdays,
 )
@@ -224,15 +225,24 @@ class Department(models.Model):
 
     @transaction.atomic
     def save(self, *args, **kwargs):
-        from .services.boards import legacy_admin_entry  # 순환 import 를 피해 여기서(3단계에서 이 갈래와 함께 지운다)
-        # 마감을 쓰는 근무표의 부서는 입력 그룹이 있어야 한다(픽스처·관리 화면·서비스 어느 길로 만들어도, 1단계 임시 기준)
-        if self.input_group_id is None and self.board_id is not None and not legacy_admin_entry(self.board):
-            self.input_group = Group.objects.create(name=self.input_group_name())
-        elif self.input_group_id and _renamed(self):  # 이름을 바꿀 때만 그룹 이름도
+        # 입력 그룹은 만들지 않는다: 첫 입력 담당자를 넣을 때 ensure_input_group 이 만든다(근무표 통합 설계 5.3)
+        if self.input_group_id and _renamed(self):  # 이름을 바꿀 때만 그룹 이름도
             Group.objects.filter(pk=self.input_group_id).update(name=self.input_group_name())
             self.input_group.name = self.input_group_name()
         super().save(*args, **kwargs)
 
+    @transaction.atomic
+    def ensure_input_group(self) -> Group:
+        """입력 그룹 "<부서> 출근표 입력"(없으면 만든다). 그룹이 없는 부서와 빈 그룹인 부서는 똑같이 '관리자만 입력'이라
+        첫 입력 담당자를 넣을 때만 부른다(board_settings.add_assignee, 관리 화면 부서 폼). 같은 이름의 그룹이 있으면 DutyError."""
+        if self.input_group_id is None:
+            name = self.input_group_name()
+            if Group.objects.filter(name=name).exists():
+                raise DutyError(f"같은 이름의 그룹이 이미 있습니다: {name}. 슈퍼유저에게 그 그룹 이름을 바꿔 달라고 하세요.")
+            self.input_group = Group.objects.create(name=name)
+            Department.objects.filter(pk=self.pk).update(input_group=self.input_group)  # 다른 칸은 건드리지 않는다
+        return self.input_group
+
     def shift_keys(self) -> list[str]:
         return [s for s in self.shifts.split(",") if s]
 
diff --git a/duty/services/boards.py b/duty/services/boards.py
index 40868c6..e17d710 100644
--- a/duty/services/boards.py
+++ b/duty/services/boards.py
@@ -33,12 +33,6 @@ def dept_keys(dept, defs: list[Def]) -> list[str]:
     return [x.key for x in shift_defs(defs) if x.key in mine]
 
 
-def legacy_admin_entry(board: Board) -> bool:
-    """1단계 임시 기준(설계 6.1): 옛 직접 입력 근무표(마감을 안 쓰는 근무표)의 문구·확인창·채우기·빈 평일 경고·입력 그룹을 지금처럼 고른다.
-    ponytail: 2단계에서 화면·서비스 자리를, 3단계에서 Department.save·부서 폼 자리와 이 함수를 지운다."""
-    return not board.use_close
-
-
 def board_of(user) -> Board | None:
     dept = getattr(user, "department", None)  # 익명·부서 없는 계정은 근무표가 없다
     return dept.board if dept else None
diff --git a/tools/help_videos/seed.py b/tools/help_videos/seed.py
index 21cc4dc..e87c639 100644
--- a/tools/help_videos/seed.py
+++ b/tools/help_videos/seed.py
@@ -32,7 +32,7 @@ for i, n in enumerate(NAMES + FREE):
 member = User.objects.create_user("member", password=PW, name="나사용", department=depts["MD"], type="개발자", help_dismissed=True)
 manager = User.objects.create_user("manager", password=PW, name="나담당", department=depts["MEMS"], type="개발자", help_dismissed=True)
 admin = User.objects.create_superuser("admin", password=PW, name="나관리", help_dismissed=True)
-depts["MEMS"].input_group.user_set.add(manager)  # 출근표 입력 담당 = 부서 입력 그룹 멤버
+depts["MEMS"].ensure_input_group().user_set.add(manager)  # 출근표 입력 담당 = 부서 입력 그룹 멤버(첫 담당자라 그룹을 만든다)
 it.admin_group.user_set.add(admin)  # 근무표 관리자 = IT 근무표 관리 그룹 멤버(슈퍼유저라고 자동으로 관리자가 아니다)
 workers = people[:len(NAMES)] + [member, manager]
 
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_boards_models.py tests/test_admin_department.py tests/test_admin_boards.py tests/test_board_steps.py tests/test_help_seed.py`
Expected: PASS
Run: `git grep -n legacy_admin_entry -- duty tests tools` → 아무것도 안 나온다.
Run: `.venv/bin/pytest -W error -q` → `1326 passed`(빠진 `test_legacy_rule_is_close_off`·입력 그룹 자동 생성 테스트 둘 = 늘어난 `ensure_input_group` 테스트 셋), 스냅샷 그대로.
Run: `DUTY_DEBUG=1 DUTY_ENV_FILE= DUTY_DATA_DIR=$(mktemp -d) .venv/bin/python manage.py makemigrations duty --check --dry-run` → "No changes detected in app 'duty'"

- [ ] **Step 5: 브라우저로 본다**(위 "브라우저 확인 준비", `admin` 으로 관리 화면)

관리 화면 → 근무표 → 운영팀: "회차 단계" 묶음의 체크 두 개·이름 다섯 칸이 입력칸이다. "마감 단계 사용"을 켜고 [저장] → 목록의 단계 열이 "입력 중 → 마감 → 확정 → 배포됨". 다시 끄고 저장. 관리 화면 → 부서 → 운영: "입력 담당자"에 가상하나를 오른쪽으로 옮겨 저장 → 그룹 목록에 "운영 출근표 입력"이 생긴다. 1400px·390px·다크·아주 크게에서 단계 묶음 설명이 잘리지 않는다.

- [ ] **Step 6: 커밋한다**

```bash
git add duty/models.py duty/services/boards.py duty/admin.py tools/help_videos/seed.py tests/conftest.py tests/test_boards_models.py tests/test_board_steps.py tests/test_admin_department.py tests/test_admin_boards.py
git commit -m "feat: 입력 그룹은 첫 입력 담당자를 넣을 때 만들고 임시 기준 legacy_admin_entry 를 지워 관리 화면 단계 칸 편집을 연다

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 2: `services/board_settings.py` — 관리자·입력 담당자·기록

> 범위: 설계 6.2 의 공통 규칙(`_require_admin`, 근무표 범위 검사, 로그 한 줄 + `LogEntry`)과 `add_admin`·`remove_admin`·`add_assignee`·`remove_assignee`, 재직 관리자 검사 `boards.left_without_admin`. 화면은 Task 5.

**Files:**
- Create: `duty/services/board_settings.py`
- Modify: `duty/services/boards.py` — `User` import, `left_without_admin`
- Test: `tests/test_board_settings.py`(새 파일)

**Interfaces:**
- Consumes: `perms.is_board_admin`, `Department.ensure_input_group`(Task 1), `User.objects.roster()`
- Produces:
  - `boards.left_without_admin(users) -> list[Board]`: users 를 관리 그룹에서 빼거나 퇴사시키면 재직 관리자가 하나도 남지 않는 근무표(users 중 재직 관리자가 있는 근무표만, id 순)
  - `board_settings.NO_ADMIN_LEFT`(빼기 오류 글), `admin_candidates(board)`(재직 + 그 근무표 부서 사람이거나 부서 없는 계정, 이미 관리자 빼고, 이름 순), `assignee_candidates(board, dept)`(그 근무표 부서 재직자, 이미 담당자 빼고, 이름 순)
  - `add_admin(by, board, user)`, `remove_admin(by, board, user)`(나 자신·퇴사자만, 재직 관리자가 남아야, 아니면 `DutyError(NO_ADMIN_LEFT)`), `add_assignee(by, board, dept, user)`(첫 담당자면 그룹을 만듦, 겹침은 `DutyError`), `remove_assignee(by, board, dept, user)` — 모두 그 근무표 관리자가 아니거나 범위 밖이면 `PermissionDenied`
  - `_require_admin(by, board)`, `_audit(by, board, obj, target, action)`(Task 4 도 쓴다): 로그 `board <code>: <action> <target> by <아이디>` + `LogEntry(user=by, 대상=obj, object_repr=target, action_flag=CHANGE, change_message="근무표 <code>: <action>")`

- [ ] **Step 1: 실패 테스트를 쓴다** — `tests/test_board_settings.py`

```python
"""[근무표 설정] 서비스(근무표 통합 설계 6.2·8): 권한·근무표 범위(IDOR)·재직 관리자 한 명 이상·기록. 이름은 모두 가상."""
import logging

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied

from duty.errors import DutyError
from duty.models import Department, User
from duty.services import board_settings as bs
from duty.services import boards


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


def _admins(board):
    return set(board.admin_group.user_set.values_list("username", flat=True))


# ── 권한: 그 근무표 관리자만 ──

@pytest.mark.parametrize("who", ["it_admin", "it_clerk", "superuser", "anonymous"])
def test_only_that_board_admin(who, ops_board, ops_admin, ops_dept, admin_user, make_member, depts):
    from django.contrib.auth.models import AnonymousUser
    clerk = make_member("가상담당")
    depts["MEMS"].input_group.user_set.add(clerk)
    su = User.objects.create_superuser("root", password=None, name="가상슈퍼")
    by = {"it_admin": admin_user, "it_clerk": clerk, "superuser": su, "anonymous": AnonymousUser()}[who]
    m = _ops_member(ops_dept, "가상하나", "OPS801")
    for call in (lambda: bs.add_admin(by, ops_board, m), lambda: bs.remove_admin(by, ops_board, ops_admin),
                 lambda: bs.add_assignee(by, ops_board, ops_dept, m), lambda: bs.remove_assignee(by, ops_board, ops_dept, m)):
        with pytest.raises(PermissionDenied):
            call()
    assert _admins(ops_board) == {"opsadm"} and Department.objects.get(code="OPS").input_group_id is None


# ── 관리자 넣기 ──

def test_add_admin_candidates(ops_board, ops_admin, ops_dept, make_member):
    m = _ops_member(ops_dept, "가상하나", "OPS801")
    nodept = User.objects.create_user("free1", password=None, name="가상무소속")
    gone = _ops_member(ops_dept, "가상퇴사", "OPS802", active=False)
    it_person = make_member("가상아이티")
    assert list(bs.admin_candidates(ops_board)) == [nodept, m]  # 이름 순, 이미 관리자인 가상운영은 빠진다
    bs.add_admin(ops_admin, ops_board, m)
    bs.add_admin(ops_admin, ops_board, nodept)
    assert _admins(ops_board) == {"opsadm", "OPS801", "free1"}
    for bad in (gone, it_person, m):  # 퇴사자·다른 근무표 사람·이미 관리자
        with pytest.raises(PermissionDenied):
            bs.add_admin(ops_admin, ops_board, bad)


# ── 관리자 빼기: 나 자신이나 퇴사한 관리자만, 재직 관리자 한 명 이상 ──

def test_remove_other_active_admin_is_superuser_job(ops_board, ops_admin, ops_dept):
    m = _ops_member(ops_dept, "가상하나", "OPS801")
    ops_board.admin_group.user_set.add(m)
    with pytest.raises(PermissionDenied):
        bs.remove_admin(ops_admin, ops_board, m)
    bs.remove_admin(ops_admin, ops_board, ops_admin)  # 나 자신은 된다(가상하나가 남는다)
    assert _admins(ops_board) == {"OPS801"}


def test_remove_departed_admin(ops_board, ops_admin, ops_dept):
    gone = _ops_member(ops_dept, "가상퇴사", "OPS802", active=False)
    ops_board.admin_group.user_set.add(gone)
    bs.remove_admin(ops_admin, ops_board, gone)
    assert _admins(ops_board) == {"opsadm"}


@pytest.mark.parametrize("with_departed", [False, True])
def test_last_active_admin_cannot_leave(ops_board, ops_admin, ops_dept, with_departed):
    if with_departed:  # 퇴사한 관리자만 남는 경우도 막는다
        ops_board.admin_group.user_set.add(_ops_member(ops_dept, "가상퇴사", "OPS802", active=False))
    with pytest.raises(DutyError, match="재직 중인 관리자가 아무도 남지 않습니다"):
        bs.remove_admin(ops_admin, ops_board, ops_admin)
    assert "opsadm" in _admins(ops_board)


def test_remove_admin_not_in_group(ops_board, ops_admin, ops_dept):
    with pytest.raises(PermissionDenied):
        bs.remove_admin(ops_admin, ops_board, _ops_member(ops_dept, "가상하나", "OPS801"))


def test_left_without_admin_counts_only_active(it_board, ops_board, ops_admin, admin_user):
    assert boards.left_without_admin([ops_admin]) == [ops_board]
    assert boards.left_without_admin([admin_user, ops_admin]) == [it_board, ops_board]
    ops_admin.is_active = False
    ops_admin.save()
    assert boards.left_without_admin([ops_admin]) == []  # 이미 재직 관리자가 없는 근무표에서 퇴사자 빼기는 막지 않는다


# ── 입력 담당자: 첫 담당자를 넣을 때 그룹이 생긴다 ──

def test_first_assignee_makes_input_group(ops_board, ops_admin, ops_dept):
    a, b = _ops_member(ops_dept, "가상하나", "OPS801"), _ops_member(ops_dept, "가상두리", "OPS802")
    assert list(bs.assignee_candidates(ops_board, ops_dept)) == [b, a]  # 이름 순
    bs.add_assignee(ops_admin, ops_board, ops_dept, a)
    dept = Department.objects.get(code="OPS")
    assert dept.input_group.name == "운영 출근표 입력" and list(dept.input_group.user_set.all()) == [a]
    assert list(bs.assignee_candidates(ops_board, dept)) == [b]  # 이미 든 사람은 빠진다
    with pytest.raises(PermissionDenied):
        bs.add_assignee(ops_admin, ops_board, dept, a)
    bs.remove_assignee(ops_admin, ops_board, dept, a)
    assert not dept.input_group.user_set.exists()  # 빈 그룹 = 관리자만 입력(그룹은 남는다)


def test_assignee_group_name_clash(ops_board, ops_admin, ops_dept):
    Group.objects.create(name="운영 출근표 입력")
    with pytest.raises(DutyError, match="같은 이름의 그룹이 이미 있습니다: 운영 출근표 입력. 슈퍼유저에게"):
        bs.add_assignee(ops_admin, ops_board, ops_dept, _ops_member(ops_dept, "가상하나", "OPS801"))
    assert Department.objects.get(code="OPS").input_group_id is None


def test_assignee_scope(ops_board, ops_admin, ops_dept, depts, make_member):
    """다른 근무표의 부서·사람은 PermissionDenied, 아무것도 바뀌지 않는다. 퇴사자는 넣지 않고 빼기는 된다."""
    it_person = make_member("가상아이티")
    gone = _ops_member(ops_dept, "가상퇴사", "OPS802", active=False)
    with pytest.raises(PermissionDenied):
        bs.add_assignee(ops_admin, ops_board, depts["MEMS"], _ops_member(ops_dept, "가상하나", "OPS801"))
    for bad in (it_person, gone):
        with pytest.raises(PermissionDenied):
            bs.add_assignee(ops_admin, ops_board, ops_dept, bad)
    assert not depts["MEMS"].input_group.user_set.exists() and Department.objects.get(code="OPS").input_group_id is None
    ops_dept.ensure_input_group().user_set.add(gone)
    bs.remove_assignee(ops_admin, ops_board, ops_dept, gone)
    with pytest.raises(PermissionDenied):
        bs.remove_assignee(ops_admin, ops_board, depts["MEMS"], it_person)


# ── 기록: 로그 한 줄 + LogEntry 한 줄, 실명 없음 ──

def test_every_write_logs_once_without_names(ops_board, ops_admin, ops_dept, caplog):
    m = _ops_member(ops_dept, "가상하나", "OPS801")
    caplog.set_level(logging.INFO, logger="duty.services.board_settings")
    bs.add_admin(ops_admin, ops_board, m)
    bs.add_assignee(ops_admin, ops_board, ops_dept, m)
    bs.remove_assignee(ops_admin, ops_board, ops_dept, m)
    bs.remove_admin(m, ops_board, m)  # 재직 중인 다른 관리자는 못 빼니 스스로
    assert [r.getMessage() for r in caplog.records] == [
        "board ops: 관리자 넣기 OPS801 by opsadm", "board ops: OPS 입력 담당자 넣기 OPS801 by opsadm",
        "board ops: OPS 입력 담당자 빼기 OPS801 by opsadm", "board ops: 관리자 빼기 OPS801 by OPS801"]
    rows = list(LogEntry.objects.order_by("id").values_list("user__username", "object_id", "object_repr", "change_message"))
    assert rows == [("opsadm", str(m.pk), "OPS801", "근무표 ops: 관리자 넣기"),
                    ("opsadm", str(m.pk), "OPS801", "근무표 ops: OPS 입력 담당자 넣기"),
                    ("opsadm", str(m.pk), "OPS801", "근무표 ops: OPS 입력 담당자 빼기"),
                    ("OPS801", str(m.pk), "OPS801", "근무표 ops: 관리자 빼기")]
    assert "가상" not in caplog.text and not LogEntry.objects.filter(object_repr__contains="가상").exists()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_settings.py`
Expected: FAIL — `ImportError: cannot import name 'board_settings' from 'duty.services'`

- [ ] **Step 3: 구현한다**

`duty/services/boards.py`:
```diff
diff --git a/duty/services/boards.py b/duty/services/boards.py
index e17d710..e8abcfa 100644
--- a/duty/services/boards.py
+++ b/duty/services/boards.py
@@ -5,7 +5,7 @@ from django.db.models import Exists, F, OuterRef, Subquery
 from django.db.models.functions import Coalesce
 
 from .. import perms
-from ..models import Board, BoardShift, Period, PeriodEvent
+from ..models import Board, BoardShift, Period, PeriodEvent, User
 from ..shifts import Def, ordered, shift_defs, weekdays
 from . import holidays, memos
 
@@ -33,6 +33,14 @@ def dept_keys(dept, defs: list[Def]) -> list[str]:
     return [x.key for x in shift_defs(defs) if x.key in mine]
 
 
+def left_without_admin(users) -> list[Board]:
+    """users 를 관리 그룹에서 빼거나 퇴사시키면 재직 중인 관리자가 하나도 남지 않는 근무표(근무표 통합 설계 6.2·7.4).
+    users 가운데 재직 관리자가 있는 근무표만 본다(이미 재직 관리자가 없는 근무표에서 퇴사자를 빼는 일은 막지 않는다)."""
+    ids = [u.pk for u in users]
+    return [b for b in Board.objects.filter(admin_group__user__in=ids, admin_group__user__is_active=True).distinct()
+            if not User.objects.filter(groups=b.admin_group_id, is_active=True).exclude(pk__in=ids).exists()]
+
+
 def board_of(user) -> Board | None:
     dept = getattr(user, "department", None)  # 익명·부서 없는 계정은 근무표가 없다
     return dept.board if dept else None
```

`duty/services/board_settings.py`(새 파일):
```python
"""[근무표 설정](근무표 통합 설계 6.2): 근무표 관리자가 그 근무표의 관리자·입력 담당자·근무 정의와 부서·회차 단계를 고친다.
모든 함수는 그 근무표 관리자만 부르고(첫 줄 _require_admin), 받은 부서·사람이 그 근무표 것인지 다시 본다(아니면 PermissionDenied,
뷰는 404). 쓰기마다 로그 한 줄과 Django LogEntry 한 줄을 남긴다(아이디·부서 코드·근무표 code 만, 실명·비밀번호 없음)."""
import logging

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q

from .. import perms
from ..errors import DutyError
from ..models import Department, User
from . import boards

log = logging.getLogger(__name__)

NO_ADMIN_LEFT = "재직 중인 관리자가 아무도 남지 않습니다. 회차·배포·설정을 할 사람이 없으니 다른 사람을 먼저 넣으세요."


def _require_admin(by, board) -> None:
    if not perms.is_board_admin(by, board):
        raise PermissionDenied("이 근무표 관리자가 아닙니다.")


def _audit(by, board, obj, target: str, action: str) -> None:
    """로그 한 줄 + LogEntry 한 줄(관리 화면에서 그 사람·부서·근무표 편집 페이지의 [기록]에 보인다).
    Django 의 log_actions 는 object_repr 에 str(obj)(= 사람 실명)를 넣으므로 쓰지 않고 아이디·코드를 직접 넣는다."""
    log.info("board %s: %s %s by %s", board.code, action, target, by.username)
    LogEntry.objects.create(user=by, content_type=ContentType.objects.get_for_model(obj), object_id=str(obj.pk),
                            object_repr=target, action_flag=CHANGE, change_message=f"근무표 {board.code}: {action}")


def admin_candidates(board):
    """관리자 넣기 후보: 재직 중이고 그 근무표 부서 사람이거나 부서 없는 계정, 이미 관리자인 사람은 빼고, 이름 순.
    다른 근무표 사람은 넣지 않는다(필요하면 슈퍼유저가 관리 화면에서)."""
    return (User.objects.filter(is_active=True).filter(Q(department__board=board) | Q(department__isnull=True))
            .exclude(groups=board.admin_group_id).select_related("department").order_by("name"))


def assignee_candidates(board, dept):
    """입력 담당자 넣기 후보: 그 근무표 부서의 재직자, 이미 담당자인 사람은 빼고, 이름 순."""
    qs = User.objects.roster().filter(department__board=board).select_related("department")
    if dept.input_group_id:
        qs = qs.exclude(groups=dept.input_group_id)
    return qs.order_by("name")


def _dept(board, dept) -> Department:
    """트랜잭션 안에서 부서를 다시 읽고 그 근무표 부서인지 본다(IDOR)."""
    dept = Department.objects.select_related("input_group").get(pk=dept.pk)
    if dept.board_id != board.pk:
        raise PermissionDenied("이 근무표의 부서가 아닙니다.")
    return dept


@transaction.atomic
def add_admin(by, board, user) -> None:
    _require_admin(by, board)
    if not admin_candidates(board).filter(pk=user.pk).exists():
        raise PermissionDenied("관리자로 넣을 수 없는 사람입니다.")
    board.admin_group.user_set.add(user)
    _audit(by, board, user, user.username, "관리자 넣기")


@transaction.atomic
def remove_admin(by, board, user) -> None:
    """나 자신이나 퇴사한 관리자만 뺀다. 재직 중인 다른 관리자 빼기는 슈퍼유저(관리 화면): 빼고 나서 그 계정을 다루는 우회를 막는다."""
    _require_admin(by, board)
    user = User.objects.get(pk=user.pk)  # 재직 여부는 DB 에서
    if not board.admin_group.user_set.filter(pk=user.pk).exists():
        raise PermissionDenied("이 근무표 관리자가 아닙니다.")
    if user.pk != by.pk and user.is_active:
        raise PermissionDenied("재직 중인 다른 관리자는 슈퍼유저가 관리 화면에서 뺍니다.")
    if board in boards.left_without_admin([user]):
        raise DutyError(NO_ADMIN_LEFT)
    board.admin_group.user_set.remove(user)
    _audit(by, board, user, user.username, "관리자 빼기")


@transaction.atomic
def add_assignee(by, board, dept, user) -> None:
    """부서 입력 그룹에 넣는다. 첫 담당자면 그룹을 만든다(이름이 겹치면 DutyError)."""
    _require_admin(by, board)
    dept = _dept(board, dept)
    if not assignee_candidates(board, dept).filter(pk=user.pk).exists():
        raise PermissionDenied("입력 담당자로 넣을 수 없는 사람입니다.")
    dept.ensure_input_group().user_set.add(user)
    _audit(by, board, user, user.username, f"{dept.code} 입력 담당자 넣기")


@transaction.atomic
def remove_assignee(by, board, dept, user) -> None:
    """부서 입력 그룹에서 뺀다(퇴사자도). 담당자가 하나도 없으면 그 부서는 근무표 관리자만 입력한다."""
    _require_admin(by, board)
    dept = _dept(board, dept)
    if not (dept.input_group_id and dept.input_group.user_set.filter(pk=user.pk).exists()):
        raise PermissionDenied("이 부서의 입력 담당자가 아닙니다.")
    dept.input_group.user_set.remove(user)
    _audit(by, board, user, user.username, f"{dept.code} 입력 담당자 빼기")
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_settings.py` → `15 passed`
Run: `.venv/bin/pytest -W error -q` → `1341 passed`
Run: `makemigrations duty --check --dry-run`(Global Constraints 의 명령) → "No changes detected in app 'duty'"

- [ ] **Step 5: 커밋한다**

```bash
git add duty/services/board_settings.py duty/services/boards.py tests/test_board_settings.py
git commit -m "feat: 근무표 설정 서비스(관리자·입력 담당자 넣고 빼기, 근무표 범위 검사, 재직 관리자 한 명 이상, 로그와 LogEntry)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 3: 관리 화면 재직 관리자 한 명 이상(사용자 편집·지우기)

> 범위: 설계 7.4 "재직 관리자 한 명 이상 규칙은 관리 화면에서도 같다". 사용자 편집 폼(관리 그룹 빼기·재직 끄기)과 지우기(한 명·일괄)가 `boards.left_without_admin` 을 거친다.

**Files:**
- Modify: `duty/admin.py` — `UserChangeForm` import, `_no_admin_left`, `UserForm`, `UserAdmin.form`·`get_deleted_objects`
- Test: `tests/test_admin_users.py`(맨 끝에 더함)

**Interfaces:**
- Consumes: `boards.left_without_admin`(Task 2)
- Produces: `duty.admin.UserForm`(사용자 편집 폼), 오류 글 "<근무표 이름> 근무표에 재직 중인 관리자가 남지 않습니다. 먼저 다른 관리자를 넣으세요."(편집은 칸 오류, 지우기는 확인 화면 보호 목록)

- [ ] **Step 1: 실패 테스트를 쓴다**

```diff
diff --git a/tests/test_admin_users.py b/tests/test_admin_users.py
index d62e741..e1f811b 100644
--- a/tests/test_admin_users.py
+++ b/tests/test_admin_users.py
@@ -89,3 +89,50 @@ def test_change_page_hides_user_permissions(su_client, make_member):
     m = make_member("가")
     body = su_client.get(reverse("admin:duty_user_change", args=[m.pk])).content.decode()
     assert 'name="groups"' in body and 'name="user_permissions"' not in body
+
+
+# ── 재직 관리자 한 명 이상(근무표 통합 설계 7.4) ──
+
+def _user_data(u, **over):
+    """사용자 편집 폼에 지금 값을 그대로 보낸다(체크박스는 켤 때만)."""
+    data = {"username": u.username, "name": u.name, "department": u.department_id or "", "part": u.part, "type": u.type,
+            "groups": [g.pk for g in u.groups.all()], "date_joined_0": f"{u.date_joined:%Y-%m-%d}",
+            "date_joined_1": f"{u.date_joined:%H:%M:%S}"}
+    data |= {f: "on" for f in ("is_active", "is_staff", "is_superuser", "help_dismissed", "notify_changes",
+                               "must_change_password") if getattr(u, f)}
+    return {k: v for k, v in (data | over).items() if v is not None}
+
+
+@pytest.fixture
+def ops_only_admin(ops_board):
+    u = User.objects.create_user("opsadm", password=None, name="가상운영")
+    ops_board.admin_group.user_set.add(u)
+    return u
+
+
+@pytest.mark.parametrize("change", [{"groups": []}, {"is_active": None}])
+def test_last_active_admin_kept_in_user_form(su_client, ops_only_admin, change):
+    url = reverse("admin:duty_user_change", args=[ops_only_admin.pk])
+    r = su_client.post(url, _user_data(ops_only_admin, **change))
+    assert r.status_code == 200 and "운영팀 근무표에 재직 중인 관리자가 남지 않습니다. 먼저 다른 관리자를 넣으세요." in r.content.decode()
+    ops_only_admin.refresh_from_db()
+    assert ops_only_admin.is_active and ops_only_admin.groups.exists()
+
+
+def test_user_form_allows_when_another_admin_stays(su_client, ops_board, ops_only_admin, make_member):
+    ops_board.admin_group.user_set.add(make_member("가상둘째", user=True))
+    r = su_client.post(reverse("admin:duty_user_change", args=[ops_only_admin.pk]), _user_data(ops_only_admin, groups=[]))
+    assert r.status_code == 302, r.content.decode()[:3000]
+    assert not ops_only_admin.groups.exists()
+
+
+def test_delete_refused_for_last_active_admin(su_client, ops_only_admin, make_member):
+    r = su_client.post(reverse("admin:duty_user_delete", args=[ops_only_admin.pk]), {"post": "yes"})
+    assert r.status_code == 200 and "운영팀 근무표에 재직 중인 관리자가 남지 않습니다" in r.content.decode()
+    r = su_client.post(reverse("admin:duty_user_changelist"),
+                       {"action": "delete_selected", "_selected_action": [ops_only_admin.pk], "post": "yes"})
+    assert r.status_code == 200 and "운영팀 근무표에 재직 중인 관리자가 남지 않습니다" in r.content.decode()
+    assert User.objects.filter(pk=ops_only_admin.pk).exists()
+    other = make_member("가상기록없음")  # 관리자가 아니면 그대로 지운다
+    r = su_client.post(reverse("admin:duty_user_delete", args=[other.pk]), {"post": "yes"})
+    assert r.status_code == 302 and not User.objects.filter(pk=other.pk).exists()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_admin_users.py`
Expected: FAIL — `test_last_active_admin_kept_in_user_form[change0]`·`[change1]`·`test_delete_refused_for_last_active_admin`(3 failed, 12 passed)

- [ ] **Step 3: 구현한다**

```diff
diff --git a/duty/admin.py b/duty/admin.py
index 2ac2f9f..99a8c2d 100644
--- a/duty/admin.py
+++ b/duty/admin.py
@@ -3,6 +3,7 @@ from django.core.exceptions import PermissionDenied, ValidationError
 from django.contrib import admin, messages
 from django.contrib.admin.widgets import FilteredSelectMultiple
 from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
+from django.contrib.auth.forms import UserChangeForm
 from django.contrib.auth.models import Group
 from django.db import transaction
 from django.db.models import Count
@@ -136,8 +137,27 @@ class UserAddForm(forms.ModelForm):
         return user
 
 
+def _no_admin_left(board) -> str:
+    return f"{board.name} 근무표에 재직 중인 관리자가 남지 않습니다. 먼저 다른 관리자를 넣으세요."
+
+
+class UserForm(UserChangeForm):
+    """재직 관리자 한 명 이상(근무표 통합 설계 7.4, [근무표 설정]과 같은 검사 boards.left_without_admin):
+    마지막 재직 관리자의 관리 그룹을 빼거나 재직을 끄면 저장하지 않고 칸 오류."""
+
+    def clean(self):
+        c = super().clean()
+        if self.instance.pk and "groups" in c and "is_active" in c:
+            keep = {g.pk for g in c["groups"]} if c["is_active"] else set()
+            for board in boards.left_without_admin([self.instance]):  # 저장 전 DB 상태로 판단한다
+                if board.admin_group_id not in keep:
+                    self.add_error("groups" if c["is_active"] else "is_active", _no_admin_left(board))
+        return c
+
+
 @admin.register(User)
 class UserAdmin(DjangoUserAdmin):
+    form = UserForm
     add_form = UserAddForm
     add_form_template = None  # 기본 안내("아이디와 비밀번호를 먼저…")가 맞지 않아 일반 추가 화면을 쓴다
     add_fieldsets = ((None, {"fields": ("username", "name", "department", "part", "type")}),)
@@ -173,6 +193,12 @@ class UserAdmin(DjangoUserAdmin):
     def login_id(self, obj):
         return obj.username
 
+    def get_deleted_objects(self, objs, request):
+        """지우기(한 명·'선택한 사용자 삭제' 일괄)도 재직 관리자 한 명 이상을 지킨다: 남지 않는 근무표가 있으면
+        Django 의 '보호된 객체' 목록에 그 까닭을 넣어 아무것도 지우지 않는다(두 길 모두 이 목록이 비어야 지운다)."""
+        deleted, count, perms_needed, protected = super().get_deleted_objects(objs, request)
+        return deleted, count, perms_needed, [*protected, *map(_no_admin_left, boards.left_without_admin(objs))]
+
     def save_model(self, request, obj, form, change):
         old = User.objects.filter(pk=obj.pk).values_list("department_id", flat=True).first() if change else None
         super().save_model(request, obj, form, change)
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_admin_users.py` → `15 passed`
Run: `.venv/bin/pytest -W error -q` → `1345 passed`

- [ ] **Step 5: 브라우저로 본다**

관리 화면 → 사용자 → admin: "그룹"에서 "운영팀 근무표 관리"를 빼고 저장 → 그룹 칸 아래 "운영팀 근무표에 재직 중인 관리자가 남지 않습니다. 먼저 다른 관리자를 넣으세요."(저장되지 않음). 사용자 목록에서 admin 체크 → "선택한 사용자 삭제" → 확인 화면에 같은 까닭이 보이고 [삭제] 버튼이 없다(Django 의 "삭제할 수 없음" 화면). 1400px·390px·다크.

- [ ] **Step 6: 커밋한다**

```bash
git add duty/admin.py tests/test_admin_users.py
git commit -m "feat: 관리 화면 사용자 편집·지우기도 근무표마다 재직 관리자 한 명 이상을 지킨다

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 4: `duty/forms.py`·단계 저장·근무 정의와 부서 저장

> 범위: 설계 6.2 `save_steps`·`save_shifts`, 7.3 검사 재사용. 관리 화면의 근무 정의 폼과 단계 검사를 `duty/forms.py` 로 옮기고(관리 화면 동작 그대로), 설정 화면용 부서 폼·formset 을 더한다. 화면은 Task 6.

**Files:**
- Create: `duty/forms.py`
- Modify: `duty/admin.py` — `SHIFT_KEY_CHOICES`·`BoardShiftForm`·`BoardShiftFormSet`·`STEP_FIELDS` 를 지우고 `duty.forms` 에서 import, `BoardForm` 이 `StepsForm` 을 물려받음, `BoardAdmin.save_model`(끈 단계 안내), 쓰지 않게 된 import 정리
- Modify: `duty/services/board_settings.py` — `S`·`BEFORE_PUBLISH`·`INVALID`, `NeedsConfirm`·`stranded`·`save_steps`·`_names`·`save_shifts`
- Test: `tests/test_board_settings_shifts.py`(새 파일), `tests/test_admin_boards.py`(끈 단계 안내)

**Interfaces:**
- Consumes: `_require_admin`·`_audit`(Task 2), `boards.defs`, `collect` 의 "꺼진 근무조 행은 남는다" 규칙
- Produces:
  - `duty.forms`: `SHIFT_KEY_CHOICES`, `BoardShiftForm`, `BoardShiftFormSet`(속성 `planned_depts: dict[str, set[str]] | None`), `STEP_FIELDS`, `StepsForm`(Board ModelForm: `use_draft`·`use_close`·`STEP_FIELDS`), `DeptShiftsForm(data, instance=dept, prefix=..., defs=...)`(칸 `shifts`·`lunch_start`·`lunch_end`), `ShiftFormSet`(inline, prefix "shifts", 빈 줄 1, 지우기 없음), `shift_forms(board, data=None) -> (ShiftFormSet, list[DeptShiftsForm])`(부서 폼 prefix `d-<부서 코드>`, 부서 순서·코드 순)
  - `board_settings.NeedsConfirm(DutyError)`(속성 `rows: int`), `stranded(board) -> str`, `save_steps(by, board, form) -> str`(끈 단계 안내 또는 ""), `save_shifts(by, board, formset, dept_forms, confirm=None) -> list[str]`(경고들), 오류는 `DutyError(INVALID)` = "저장하지 않았습니다. 빨간 글씨로 표시한 칸을 고쳐 주세요."
  - `duty.admin.BoardForm(StepsForm)`: 필드 `["code", "name", *StepsForm.Meta.fields]`

- [ ] **Step 1: 실패 테스트를 쓴다**

`tests/test_board_settings_shifts.py`(새 파일):
```python
"""[근무표 설정] 근무 정의와 부서·회차 단계 저장(근무표 통합 설계 6.2·7.2·7.3). 이름은 모두 가상."""
from datetime import date, time, timedelta

import pytest
from django.contrib.admin.models import LogEntry
from django.core.exceptions import PermissionDenied
from django.utils.datastructures import MultiValueDict

from duty.errors import DutyError
from duty.forms import StepsForm, shift_forms
from duty.models import Board, BoardShift, Commute, Department, DutyAssignment, Period, User
from duty.services import board_settings as bs

S = Period.Status
MON = date(2026, 11, 16)


@pytest.fixture
def ops_admin(ops_board):
    u = User.objects.create_user("opsadm", password=None, name="가상운영")
    ops_board.admin_group.user_set.add(u)
    return u


def shift_data(board, change=None, extra=None, depts=None):
    """설정 화면이 보내는 것과 같은 값: 지금 근무 정의·부서 그대로에 change(키별)·extra(새 줄)·depts(부서 코드별)를 덮는다.
    체크박스는 켤 때만 보낸다(None = 끔)."""
    shifts = list(BoardShift.objects.filter(board=board).order_by("id"))
    data = {"shifts-TOTAL_FORMS": [str(len(shifts) + 1)], "shifts-INITIAL_FORMS": [str(len(shifts))]}

    def put(prefix, row):
        for k, v in row.items():
            if v not in (None, "", []):
                data[f"{prefix}-{k}"] = v if isinstance(v, list) else [str(v)]
    for i, s in enumerate(shifts):
        put(f"shifts-{i}", {"id": s.pk, "board": board.pk, "key": s.key, "name": s.name,
                            "start": s.start and f"{s.start:%H:%M}", "end": s.end and f"{s.end:%H:%M}",
                            "eligible_shifts": s.eligible_shifts, "eligible_types": s.eligible_types,
                            "default_alarm": "on" if s.default_alarm else None, "active": "on" if s.active else None,
                            **(change or {}).get(s.key, {})})
    put(f"shifts-{len(shifts)}", extra or {"active": "on"})  # 손대지 않은 빈 추가 줄(브라우저는 켜진 '사용'을 보낸다)
    for d in board.departments.all():
        put(f"d-{d.code}", {"shifts": d.shift_keys(), "lunch_start": d.lunch_start and f"{d.lunch_start:%H:%M}",
                            "lunch_end": d.lunch_end and f"{d.lunch_end:%H:%M}", **(depts or {}).get(d.code, {})})
    return MultiValueDict(data)


def save(by, board, data, confirm=None):
    formset, dept_forms = shift_forms(board, data)
    return bs.save_shifts(by, board, formset, dept_forms, confirm), formset, dept_forms


def _dept():
    return Department.objects.get(code="OPS")


# ── 근무 정의와 부서를 한 번에 ──

def test_saves_definitions_and_departments_together(ops_board, ops_admin):
    data = shift_data(ops_board, change={"normal": {"name": "중간"}},
                      depts={"OPS": {"shifts": ["dinner", "dawn"], "lunch_start": "11:30", "lunch_end": "12:30"}})
    assert save(ops_admin, ops_board, data)[0] == []
    assert BoardShift.objects.get(board=ops_board, key="normal").name == "중간"
    d = _dept()
    assert (d.shifts, d.lunch_start, d.lunch_end) == ("dawn,dinner", time(11, 30), time(12, 30))  # 시작 시각 순
    assert LogEntry.objects.get().change_message == "근무표 ops: 근무 정의·부서 저장"


def test_new_shift_is_saved_and_not_yet_in_department(ops_board, ops_admin):
    data = shift_data(ops_board, extra={"key": "night", "name": "밤", "start": "13:00", "end": "22:00", "active": "on"})
    save(ops_admin, ops_board, data)
    assert BoardShift.objects.get(board=ops_board, key="night").name == "밤"
    assert _dept().shifts == "dawn,normal,dinner"  # 새 근무조는 저장한 뒤 부서 칸에 생긴다(한 번 더 저장)


def test_turn_off_shift_and_move_department_in_same_save(ops_board, ops_admin):
    Department.objects.filter(code="OPS").update(shifts="dawn")
    data = shift_data(ops_board, change={"dawn": {"active": None}}, depts={"OPS": {"shifts": ["normal"]}})
    save(ops_admin, ops_board, data)
    assert not BoardShift.objects.get(board=ops_board, key="dawn").active and _dept().shifts == "normal"


def test_department_left_without_active_shift_is_refused(ops_board, ops_admin):
    Department.objects.filter(code="OPS").update(shifts="dawn")
    formset, dept_forms = shift_forms(ops_board, shift_data(ops_board, change={"dawn": {"active": None}}))
    with pytest.raises(DutyError, match="저장하지 않았습니다"):
        bs.save_shifts(ops_admin, ops_board, formset, dept_forms)
    assert formset.non_form_errors() == ["운영 부서에 켜진 근무조가 하나도 남지 않습니다. 아래 부서에서 켜진 근무조를 하나 이상 체크하세요."]
    assert BoardShift.objects.get(board=ops_board, key="dawn").active


@pytest.mark.parametrize("dept,msg", [
    ({"lunch_start": "11:30"}, "점심 시각은 둘 다 비우거나, 둘 다 넣고 시작을 끝보다 이르게 하세요."),
    ({"lunch_start": "12:30", "lunch_end": "11:30"}, "점심 시각은 둘 다 비우거나, 둘 다 넣고 시작을 끝보다 이르게 하세요."),
    ({"shifts": []}, "출근조를 하나 이상 선택하세요."),
])
def test_department_checks(ops_board, ops_admin, dept, msg):
    formset, dept_forms = shift_forms(ops_board, shift_data(ops_board, change={"normal": {"name": "중간"}}, depts={"OPS": dept}))
    with pytest.raises(DutyError, match="저장하지 않았습니다"):
        bs.save_shifts(ops_admin, ops_board, formset, dept_forms)
    assert msg in str(dept_forms[0].errors)
    assert BoardShift.objects.get(board=ops_board, key="normal").name == "가운데"  # 근무 정의도 저장하지 않는다


# ── 부서에서 근무조를 뺄 때: 배포 전 회차 출근표가 있으면 확인 ──

@pytest.fixture
def rows(ops_board):
    m = User.objects.create_user("OPS801", password=None, name="가상하나", department=_dept(), type="직원")
    open_ = Period.objects.create(board=ops_board, name="이번 회차", start_date=MON, end_date=MON, status=S.COLLECTING)
    done = Period.objects.create(board=ops_board, name="지난 회차", start_date=MON, end_date=MON, status=S.PUBLISHED)
    for p in (open_, done):
        Commute.objects.create(period=p, date=MON, member=m, shift="dinner")
    return open_


def test_removing_department_shift_with_rows_asks_again(ops_board, ops_admin, rows):
    data = shift_data(ops_board, depts={"OPS": {"shifts": ["dawn", "normal"]}})
    msg = ("운영 부서에서 '늦은'을 빼면 배포 전 회차(이번 회차)의 그 근무조 출근표 1행이 다음 표 저장 때 지워집니다. "
           "그래도 저장하려면 [그래도 저장]을 누르세요.")
    for confirm in (None, 2):  # 확인 없이, 또는 본 행 수가 지금과 다르면(그사이 바뀜) 다시 묻는다
        with pytest.raises(bs.NeedsConfirm) as e:
            save(ops_admin, ops_board, data, confirm)
        assert (str(e.value), e.value.rows) == (msg, 1)
        assert _dept().shifts == "dawn,normal,dinner"
    save(ops_admin, ops_board, data, confirm=1)
    assert _dept().shifts == "dawn,normal"


def test_turning_shift_off_does_not_ask(ops_board, ops_admin, rows):
    """꺼진 근무조의 출근표는 표 저장 때 남으므로(collect._kept_keys) 끄면서 빼면 묻지 않는다."""
    save(ops_admin, ops_board, shift_data(ops_board, change={"dinner": {"active": None}},
                                         depts={"OPS": {"shifts": ["dawn", "normal"]}}))
    assert _dept().shifts == "dawn,normal"


# ── 생성됨 회차에 배정이 남은 관제 정의를 끄면 경고 ──

def test_turning_off_slot_with_generated_rows_warns(it_board, depts, admin_user, make_member):
    m = make_member("가상가")
    p = Period.objects.create(board=it_board, name="가상 회차", start_date=MON, end_date=MON + timedelta(days=1),
                              status=S.GENERATED)
    for d in p.dates():
        DutyAssignment.objects.create(period=p, date=d, cell="slot0", member=m)
    warnings, *_ = save(admin_user, it_board, shift_data(it_board, change={"slot0": {"active": None}}))
    assert warnings == ["생성됨 회차(가상 회차)에 '08:30~09:30' 배정 2개가 남아 있습니다. "
                        "다시 생성하거나 다른 상태로 옮기면 지워지고, 그대로 배포하면 근무표에 나옵니다."]
    assert not BoardShift.objects.get(board=it_board, key="slot0").active


# ── 범위(IDOR)·권한 ──

def test_shift_forms_of_other_board_refused(ops_board, ops_admin, it_board, depts, admin_user):
    it_formset, it_depts = shift_forms(it_board, shift_data(it_board))
    ops_formset, ops_depts = shift_forms(ops_board, shift_data(ops_board))
    for formset, dept_forms in ((it_formset, ops_depts), (ops_formset, it_depts)):
        with pytest.raises(PermissionDenied):
            bs.save_shifts(ops_admin, ops_board, formset, dept_forms)
    with pytest.raises(PermissionDenied):  # IT 관리자는 운영팀 근무표를 고치지 못한다
        bs.save_shifts(admin_user, ops_board, ops_formset, ops_depts)
    assert not LogEntry.objects.exists()


# ── 회차 단계 ──

def _steps(board, **over):
    data = {f: getattr(board, f) for f in ("step_draft", "step_collecting", "step_closed", "step_generated", "step_published")}
    data |= {f: "on" for f in ("use_draft", "use_close") if getattr(board, f)}
    return StepsForm({k: v for k, v in (data | over).items() if v is not None}, instance=Board.objects.get(pk=board.pk))


def test_save_steps(ops_board, ops_admin):
    assert bs.save_steps(ops_admin, ops_board, _steps(ops_board, use_draft="on", step_draft="준비 중")) == ""
    ops_board.refresh_from_db()
    assert ops_board.steps()[:2] == ["draft", "collecting"] and ops_board.step_draft == "준비 중"
    assert LogEntry.objects.get().change_message == "근무표 ops: 회차 단계 저장"


def test_save_steps_warns_about_stranded_periods(it_board, admin_user):
    Period.objects.create(board=it_board, name="가상", start_date=MON, end_date=MON, status=S.CLOSED)
    assert (bs.save_steps(admin_user, it_board, _steps(it_board, use_close=None))
            == "'마감' 단계에 회차 1개가 남아 있습니다. 회차 화면에서 다른 단계로 옮기세요.")


def test_save_steps_refuses_bad_names_and_other_board(ops_board, ops_admin, it_board):
    form = _steps(ops_board, step_generated="됨")
    with pytest.raises(DutyError, match="저장하지 않았습니다"):
        bs.save_steps(ops_admin, ops_board, form)
    assert form.errors["step_generated"] == ["버튼 이름이 비거나 다른 버튼과 같아집니다: []"]
    with pytest.raises(PermissionDenied):
        bs.save_steps(ops_admin, ops_board, _steps(it_board))  # 다른 근무표의 단계 폼
    ops_board.refresh_from_db()
    assert ops_board.step_generated == "확정" and not LogEntry.objects.exists()
```

`tests/test_admin_boards.py`:
```diff
diff --git a/tests/test_admin_boards.py b/tests/test_admin_boards.py
index 6666ba7..aeb5a5b 100644
--- a/tests/test_admin_boards.py
+++ b/tests/test_admin_boards.py
@@ -1,5 +1,5 @@
 """관리 화면(슈퍼유저 전용): 근무표·근무 정의 편집과 설계 4.3 검증, 그룹 관리자 지정(3단계). 이름은 모두 가상."""
-from datetime import time
+from datetime import date, time
 
 import pytest
 from django.contrib.auth.models import Group
@@ -7,7 +7,7 @@ from django.core.exceptions import ValidationError
 from django.urls import reverse
 
 from duty.admin import STEP_FIELDS, BoardForm, DepartmentForm
-from duty.models import Board, BoardShift, Department, GroupKeeper, User
+from duty.models import Board, BoardShift, Department, GroupKeeper, Period, User
 from tests.it_defs import OPS_STEPS
 
 ADD = reverse("admin:duty_board_add")
@@ -283,6 +283,15 @@ def test_saved_board_steps_can_change(su_client, ops):
     assert r.status_code == 200 and "버튼 이름이 비거나 다른 버튼과 같아집니다: []" in r.content.decode()
 
 
+def test_change_warns_about_periods_in_turned_off_step(su_client, ops):
+    """끈 단계에 회차가 남아 있으면 저장 뒤 경고(설정 화면과 같은 글, board_settings.stranded)."""
+    board, a, b = ops
+    Period.objects.create(board=board, name="가상", start_date=date(2026, 11, 16), end_date=date(2026, 11, 16),
+                          status=Period.Status.DRAFT)
+    r = su_client.post(reverse("admin:duty_board_change", args=[board.pk]), change(board, [a, b]), follow=True)
+    assert "&#x27;작성 중&#x27; 단계에 회차 1개가 남아 있습니다. 회차 화면에서 다른 단계로 옮기세요." in r.content.decode()
+
+
 # ── 그룹 관리자 ──
 
 def test_group_page_hides_permissions_and_edits_keepers(su_client, it_board, admin_user, make_member):
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_settings_shifts.py tests/test_admin_boards.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'duty.forms'`(수집 오류). `tests/test_board_settings_shifts.py` 를 빼고 돌리면 `test_change_warns_about_periods_in_turned_off_step` FAIL.

- [ ] **Step 3: `duty/forms.py` 를 만든다**

`BoardShiftForm` 은 `duty/admin.py` 에 있던 것과 한 글자도 다르지 않다. `BoardShiftFormSet` 은 docstring 한 줄과 맨 끝 부서 검사(`planned_depts`)만 다르다. `StepsForm.clean` 의 단계 검사는 `BoardForm.clean` 에 있던 것 그대로다.

```python
"""관리 화면과 [근무표 설정]이 함께 쓰는 폼(근무표 통합 설계 6.2·7.3): 근무 정의 한 줄·근무표 전체 검사, 회차 단계 칸,
부서 출근조·점심 시각. 검사 규칙은 한 곳에만 둔다."""
from django import forms
from django.core.exceptions import ValidationError

from .models import Board, BoardShift, Department
from .services import boards
from .shifts import DEVELOPER, LUNCH, SHIFT_KEYS, STAFF, is_slot_cell, shift_defs

# 근무조 키 선택지(관리 화면 표시 이름 "근무조 1"~"근무조 4", 설계 4.1)
SHIFT_KEY_CHOICES = [(k, label) for k, label in BoardShift._meta.get_field("key").choices if k in SHIFT_KEYS]


class BoardShiftForm(forms.ModelForm):
    """근무 정의 한 줄의 검증(설계 4.3). 저장한 줄은 키 칸을 잠근다(BoardShift.clean 이 한 번 더 막는다).
    시각 오류는 start 칸에 붙인다: 그 칸이 오류면 DB 제약(boardshift_times_valid) 검사를 건너뛰어 영어 제약 문구가 함께 뜨지 않는다."""
    eligible_shifts = forms.MultipleChoiceField(label="자격 근무조", required=False, choices=SHIFT_KEY_CHOICES,
                                                widget=forms.CheckboxSelectMultiple,
                                                help_text="장중관제 칸만. 켜진 관제는 하나 이상 고릅니다")
    eligible_types = forms.MultipleChoiceField(label="자격 구분", required=False, choices=[(STAFF, STAFF), (DEVELOPER, DEVELOPER)],
                                               widget=forms.CheckboxSelectMultiple, help_text="장중관제 칸만. 비우면 전원")

    class Meta:
        model = BoardShift
        fields = ["key", "name", "start", "end", "eligible_shifts", "eligible_types", "default_alarm", "active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:  # 저장한 정의의 키는 바꾸지 않는다(보낸 값은 무시된다)
            self.fields["key"].disabled = True

    def clean_name(self):
        v = self.cleaned_data["name"].strip()
        if v in ("date", "day") or any(c in v for c in "(\r\n"):  # CSV 열 이름이 된다
            raise forms.ValidationError("이름은 date·day 가 아니어야 하고 ( 와 줄바꿈을 쓸 수 없습니다(CSV 열 이름이 됩니다).")
        return v

    def clean_eligible_shifts(self):
        return [k for k in SHIFT_KEYS if k in self.cleaned_data["eligible_shifts"]]

    def clean(self):
        c = super().clean()
        key, start, end = c.get("key"), c.get("start"), c.get("end")
        if not key:
            return c
        if key == LUNCH:
            if start or end:
                self.add_error("start", "점심당번은 시각을 비웁니다(점심 시각은 부서마다 정합니다).")
        elif not (start and end and start < end):
            self.add_error("start", "시작·끝 시각을 넣고 시작을 끝보다 이르게 하세요(당일 근무만).")
        if not is_slot_cell(key) and (c.get("eligible_shifts") or c.get("eligible_types")):
            self.add_error("eligible_shifts", "자격 근무조·자격 구분은 장중관제 칸에만 씁니다.")
        if is_slot_cell(key) and c.get("active") and not c.get("eligible_shifts"):  # 자격자가 없으면 생성이 그 칸을 못 채운다
            self.add_error("eligible_shifts", "장중관제 칸은 자격 근무조를 하나 이상 골라야 합니다.")
        if key not in SHIFT_KEYS and c.get("default_alarm"):
            self.add_error("default_alarm", "기본 알림 대상은 근무조에만 씁니다.")
        return c


class BoardShiftFormSet(forms.BaseInlineFormSet):
    """근무표 전체의 검증(설계 4.3). Django 기본 겹침 검사(영어 칸 이름이 섞인 문구)는 부르지 않고 한국어로 직접 본다:
    이름·키 겹침, 켜진 근무조 하나 이상, 켜진 근무조끼리 시작 시각이 다름(가장 이른 조·이른/가운데/늦은 조가 하나로 정해지게),
    관제 자격 근무조는 이 근무표의 근무조(켜진 관제는 켜진 근무조만), 끄고 나서도 부서마다 켜진 입력 근무조가 하나 이상.
    관리 화면 근무표 인라인과 [근무표 설정] 근무 정의 칸이 함께 쓴다."""

    def clean(self):
        if any(self.errors):
            return
        rows = [f.cleaned_data for f in self.forms if f.cleaned_data.get("key")]  # 비워 둔 추가 줄은 빠진다
        for field, label in (("name", "근무 정의 이름이 겹칩니다"), ("key", "키가 겹칩니다")):
            values = [r[field] for r in rows]
            dup = sorted({v for v in values if values.count(v) > 1})
            if dup:
                names = dict(BoardShift._meta.get_field("key").choices) if field == "key" else {}
                raise ValidationError(f"{label}: {', '.join(names.get(v, v) for v in dup)}")
        on = [r for r in rows if r["key"] in SHIFT_KEYS and r["active"]]
        if not on:
            raise ValidationError("켜진 근무조가 하나 이상 있어야 합니다.")
        if len({r["start"] for r in on}) != len(on):
            raise ValidationError("켜진 근무조끼리 시작 시각이 달라야 합니다(가장 이른 조를 하나로 정할 수 있게).")
        keys, on_keys = {r["key"] for r in rows if r["key"] in SHIFT_KEYS}, {r["key"] for r in on}
        for r in rows:
            picked = set(r.get("eligible_shifts") or ())
            if picked - keys:
                raise ValidationError(f"{r['name']}: 자격 근무조는 이 근무표의 근무조여야 합니다.")
            if r["active"] and picked - on_keys:
                raise ValidationError(f"{r['name']}: 켜진 관제의 자격 근무조는 켜진 근무조여야 합니다.")
        # 부서마다 켜진 입력 근무조 하나 이상. [근무표 설정]은 같은 저장의 부서 출근조(planned_depts = {부서 이름: 키들}, 설계 6.2),
        # 관리 화면은 저장된 부서 출근조로 본다
        planned = getattr(self, "planned_depts", None)
        if planned is not None:
            tail = "아래 부서에서 켜진 근무조를 하나 이상 체크하세요."
        else:
            planned = {d.name: set(d.shift_keys()) for d in self.instance.departments.all()} if self.instance.pk else {}
            tail = "부서의 출근조를 먼저 바꾸세요."
        for name, picked in planned.items():
            if not picked & on_keys:
                raise ValidationError(f"{name} 부서에 켜진 근무조가 하나도 남지 않습니다. {tail}")


STEP_FIELDS = ["step_draft", "step_collecting", "step_closed", "step_generated", "step_published"]


class StepsForm(forms.ModelForm):
    """회차 단계 칸(설계 5.1·5.4): 이름은 비지 않음(모델 제약)·줄바꿈 금지·서로 다름, 켠 단계에서 나오는 버튼 글자가 비거나
    서로 겹치면 그 이름 칸 오류. 관리 화면 근무표 폼(BoardForm)과 [근무표 설정] 단계 칸이 함께 쓴다."""

    class Meta:
        model = Board
        fields = ["use_draft", "use_close", *STEP_FIELDS]

    def clean(self):
        c = super().clean()
        names = [c.get(f) for f in STEP_FIELDS]
        for f, v in zip(STEP_FIELDS, names):  # 단계 이름(설계 5.1): 줄바꿈 금지, 서로 다름
            if v and ("\n" in v or "\r" in v):
                self.add_error(f, "단계 이름에 줄바꿈을 쓸 수 없습니다.")
            elif v and names.count(v) > 1:
                self.add_error(f, f"단계 이름이 겹칩니다: {v}")
        # 버튼 글자 검사(설계 5.4). 단계 칸 자체 오류가 없으면 본다
        if all(names) and not set(STEP_FIELDS) & set(self.errors):
            steps = Board(use_draft=c.get("use_draft"), use_close=c.get("use_close"), **dict(zip(STEP_FIELDS, names)))
            gen, slot = steps.step_buttons(False), steps.step_buttons(True)
            for x in steps.bad_buttons():  # 생성·취소 글자는 생성됨 이름에서, 열기·마감은 취합 중 이름에서 나온다
                # 관제 있을 때의 고정 글자([장중관제 생성]·[재생성]…)와 겹치면 생성됨 이름을 고쳐도 남는다
                fixed = x.strip() and x in (slot["generate"], slot["undo"], slot["regenerate"])
                field = ("step_generated" if x in (gen["generate"], gen["undo"]) and not fixed
                         else "step_closed" if x == gen["close"] and not fixed else "step_collecting")  # 마감 글자가 열기와 같으면 마감 이름 칸
                self.add_error(field, f"버튼 이름이 비거나 다른 버튼과 같아집니다: [{x}]")
        return c


class DeptShiftsForm(forms.ModelForm):
    """[근무표 설정] 부서 한 덩어리(설계 7.2): 가능한 출근조(그 근무표의 켜진 근무조, 시작 시각 순, "이름 시작~끝")와 점심 시각.
    점심 시각 검사는 모델 제약 department_lunch_valid(같은 한국어 문구). 출근조 저장은 board_settings.save_shifts 가 한다."""
    shifts = forms.MultipleChoiceField(label="가능한 출근조", widget=forms.CheckboxSelectMultiple,
                                       error_messages={"required": "출근조를 하나 이상 선택하세요."})

    class Meta:
        model = Department
        fields = ["lunch_start", "lunch_end"]
        widgets = {f: forms.TimeInput(format="%H:%M", attrs={"type": "time"}) for f in ("lunch_start", "lunch_end")}

    def __init__(self, *args, defs, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["shifts"].choices = [(x.key, f"{x.name} {x.start:%H:%M}~{x.end:%H:%M}")
                                         for x in shift_defs(defs) if x.active]
        self.initial.setdefault("shifts", self.instance.shift_keys())


# [근무표 설정] 근무 정의 칸: 관리 화면 인라인과 같은 폼·검사, 빈 추가 줄 하나, 지우기 없음(prefix "shifts")
ShiftFormSet = forms.inlineformset_factory(
    Board, BoardShift, form=BoardShiftForm, formset=BoardShiftFormSet, extra=1, can_delete=False,
    widgets={f: forms.TimeInput(format="%H:%M", attrs={"type": "time"}) for f in ("start", "end")})


def shift_forms(board, data=None):
    """[근무표 설정] 근무 정의와 부서 칸의 폼들(data 가 있으면 보낸 값으로): (근무 정의 formset, 부서마다 DeptShiftsForm).
    부서 폼은 그 근무표 부서만 만든다(prefix "d-<부서 코드>", 순서 = 부서 순서·코드)."""
    defs = boards.defs(board)
    return (ShiftFormSet(data, instance=board),
            [DeptShiftsForm(data, instance=d, prefix=f"d-{d.code}", defs=defs)
             for d in board.departments.order_by("order", "code")])
```

- [ ] **Step 4: `duty/admin.py` 를 고친다**(옮긴 클래스를 지우고 import, `BoardForm`·`save_model`)

```diff
diff --git a/duty/admin.py b/duty/admin.py
index 99a8c2d..76f6079 100644
--- a/duty/admin.py
+++ b/duty/admin.py
@@ -1,5 +1,5 @@
 from django import forms
-from django.core.exceptions import PermissionDenied, ValidationError
+from django.core.exceptions import PermissionDenied
 from django.contrib import admin, messages
 from django.contrib.admin.widgets import FilteredSelectMultiple
 from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
@@ -13,12 +13,10 @@ from django.utils.html import format_html, format_html_join
 from py_vapid import _check_sub
 
 from .accounts import issue_account, on_department_change
+from .forms import SHIFT_KEY_CHOICES, STEP_FIELDS, BoardShiftForm, BoardShiftFormSet, StepsForm
 from .models import AlarmSettings, Board, BoardShift, Department, GroupKeeper, Holiday, User
-from .services import alarm_settings, boards
-from .shifts import DEVELOPER, LUNCH, SHIFT_KEYS, STAFF, is_slot_cell, shift_defs
-
-# 근무조 키 선택지(관리 화면 표시 이름 "근무조 1"~"근무조 4", 설계 4.1)
-SHIFT_KEY_CHOICES = [(k, label) for k, label in BoardShift._meta.get_field("key").choices if k in SHIFT_KEYS]
+from .services import alarm_settings, board_settings, boards
+from .shifts import SHIFT_KEYS, shift_defs
 
 
 def _input_users(dept):
@@ -222,85 +220,6 @@ class UserAdmin(DjangoUserAdmin):
                 format_html_join("", "<br>{}", ((x,) for x in lines))), messages.WARNING)
 
 
-class BoardShiftForm(forms.ModelForm):
-    """근무 정의 한 줄의 검증(설계 4.3). 저장한 줄은 키 칸을 잠근다(BoardShift.clean 이 한 번 더 막는다).
-    시각 오류는 start 칸에 붙인다: 그 칸이 오류면 DB 제약(boardshift_times_valid) 검사를 건너뛰어 영어 제약 문구가 함께 뜨지 않는다."""
-    eligible_shifts = forms.MultipleChoiceField(label="자격 근무조", required=False, choices=SHIFT_KEY_CHOICES,
-                                                widget=forms.CheckboxSelectMultiple,
-                                                help_text="장중관제 칸만. 켜진 관제는 하나 이상 고릅니다")
-    eligible_types = forms.MultipleChoiceField(label="자격 구분", required=False, choices=[(STAFF, STAFF), (DEVELOPER, DEVELOPER)],
-                                               widget=forms.CheckboxSelectMultiple, help_text="장중관제 칸만. 비우면 전원")
-
-    class Meta:
-        model = BoardShift
-        fields = ["key", "name", "start", "end", "eligible_shifts", "eligible_types", "default_alarm", "active"]
-
-    def __init__(self, *args, **kwargs):
-        super().__init__(*args, **kwargs)
-        if self.instance.pk:  # 저장한 정의의 키는 바꾸지 않는다(보낸 값은 무시된다)
-            self.fields["key"].disabled = True
-
-    def clean_name(self):
-        v = self.cleaned_data["name"].strip()
-        if v in ("date", "day") or any(c in v for c in "(\r\n"):  # CSV 열 이름이 된다
-            raise forms.ValidationError("이름은 date·day 가 아니어야 하고 ( 와 줄바꿈을 쓸 수 없습니다(CSV 열 이름이 됩니다).")
-        return v
-
-    def clean_eligible_shifts(self):
-        return [k for k in SHIFT_KEYS if k in self.cleaned_data["eligible_shifts"]]
-
-    def clean(self):
-        c = super().clean()
-        key, start, end = c.get("key"), c.get("start"), c.get("end")
-        if not key:
-            return c
-        if key == LUNCH:
-            if start or end:
-                self.add_error("start", "점심당번은 시각을 비웁니다(점심 시각은 부서마다 정합니다).")
-        elif not (start and end and start < end):
-            self.add_error("start", "시작·끝 시각을 넣고 시작을 끝보다 이르게 하세요(당일 근무만).")
-        if not is_slot_cell(key) and (c.get("eligible_shifts") or c.get("eligible_types")):
-            self.add_error("eligible_shifts", "자격 근무조·자격 구분은 장중관제 칸에만 씁니다.")
-        if is_slot_cell(key) and c.get("active") and not c.get("eligible_shifts"):  # 자격자가 없으면 생성이 그 칸을 못 채운다
-            self.add_error("eligible_shifts", "장중관제 칸은 자격 근무조를 하나 이상 골라야 합니다.")
-        if key not in SHIFT_KEYS and c.get("default_alarm"):
-            self.add_error("default_alarm", "기본 알림 대상은 근무조에만 씁니다.")
-        return c
-
-
-class BoardShiftFormSet(forms.BaseInlineFormSet):
-    """근무표 전체의 검증(설계 4.3). Django 기본 겹침 검사(영어 칸 이름이 섞인 문구)는 부르지 않고 한국어로 직접 본다:
-    이름·키 겹침, 켜진 근무조 하나 이상, 켜진 근무조끼리 시작 시각이 다름(가장 이른 조·이른/가운데/늦은 조가 하나로 정해지게),
-    관제 자격 근무조는 이 근무표의 근무조(켜진 관제는 켜진 근무조만), 끄고 나서도 부서마다 켜진 입력 근무조가 하나 이상."""
-
-    def clean(self):
-        if any(self.errors):
-            return
-        rows = [f.cleaned_data for f in self.forms if f.cleaned_data.get("key")]  # 비워 둔 추가 줄은 빠진다
-        for field, label in (("name", "근무 정의 이름이 겹칩니다"), ("key", "키가 겹칩니다")):
-            values = [r[field] for r in rows]
-            dup = sorted({v for v in values if values.count(v) > 1})
-            if dup:
-                names = dict(BoardShift._meta.get_field("key").choices) if field == "key" else {}
-                raise ValidationError(f"{label}: {', '.join(names.get(v, v) for v in dup)}")
-        on = [r for r in rows if r["key"] in SHIFT_KEYS and r["active"]]
-        if not on:
-            raise ValidationError("켜진 근무조가 하나 이상 있어야 합니다.")
-        if len({r["start"] for r in on}) != len(on):
-            raise ValidationError("켜진 근무조끼리 시작 시각이 달라야 합니다(가장 이른 조를 하나로 정할 수 있게).")
-        keys, on_keys = {r["key"] for r in rows if r["key"] in SHIFT_KEYS}, {r["key"] for r in on}
-        for r in rows:
-            picked = set(r.get("eligible_shifts") or ())
-            if picked - keys:
-                raise ValidationError(f"{r['name']}: 자격 근무조는 이 근무표의 근무조여야 합니다.")
-            if r["active"] and picked - on_keys:
-                raise ValidationError(f"{r['name']}: 켜진 관제의 자격 근무조는 켜진 근무조여야 합니다.")
-        if self.instance.pk:
-            for dept in self.instance.departments.all():
-                if not set(dept.shift_keys()) & on_keys:
-                    raise ValidationError(f"{dept.name} 부서에 켜진 근무조가 하나도 남지 않습니다. 부서의 출근조를 먼저 바꾸세요.")
-
-
 class BoardShiftInline(admin.TabularInline):
     """저장한 줄은 지우지 않는다(끄기만). 아직 저장하지 않은 추가 줄은 화면에서 뺄 수 있다."""
     model = BoardShift
@@ -310,32 +229,12 @@ class BoardShiftInline(admin.TabularInline):
     can_delete = False
 
 
-STEP_FIELDS = ["step_draft", "step_collecting", "step_closed", "step_generated", "step_published"]
-
-
-class BoardForm(forms.ModelForm):
-    class Meta:
-        model = Board
-        fields = ["code", "name", "use_draft", "use_close", *STEP_FIELDS]
+class BoardForm(StepsForm):
+    class Meta(StepsForm.Meta):
+        fields = ["code", "name", *StepsForm.Meta.fields]
 
     def clean(self):
-        c = super().clean()
-        names = [c.get(f) for f in STEP_FIELDS]
-        for f, v in zip(STEP_FIELDS, names):  # 단계 이름(설계 5.1): 줄바꿈 금지, 서로 다름
-            if v and ("\n" in v or "\r" in v):
-                self.add_error(f, "단계 이름에 줄바꿈을 쓸 수 없습니다.")
-            elif v and names.count(v) > 1:
-                self.add_error(f, f"단계 이름이 겹칩니다: {v}")
-        # 버튼 글자 검사(설계 5.4). 단계 칸 자체 오류가 없으면 본다
-        if all(names) and not set(STEP_FIELDS) & set(self.errors):
-            steps = Board(use_draft=c.get("use_draft"), use_close=c.get("use_close"), **dict(zip(STEP_FIELDS, names)))
-            gen, slot = steps.step_buttons(False), steps.step_buttons(True)
-            for x in steps.bad_buttons():  # 생성·취소 글자는 생성됨 이름에서, 열기·마감은 취합 중 이름에서 나온다
-                # 관제 있을 때의 고정 글자([장중관제 생성]·[재생성]…)와 겹치면 생성됨 이름을 고쳐도 남는다
-                fixed = x.strip() and x in (slot["generate"], slot["undo"], slot["regenerate"])
-                field = ("step_generated" if x in (gen["generate"], gen["undo"]) and not fixed
-                         else "step_closed" if x == gen["close"] and not fixed else "step_collecting")  # 마감 글자가 열기와 같으면 마감 이름 칸
-                self.add_error(field, f"버튼 이름이 비거나 다른 버튼과 같아집니다: [{x}]")
+        c = super().clean()  # 단계 칸 검사(StepsForm)
         name = c.get("name")
         # Board.save 가 만들거나 바꿀 관리 그룹 이름이 이미 있으면 Group.name unique 위반(500) 대신 칸 오류로
         if name and Board.objects.exclude(pk=self.instance.pk).filter(name=name).exists():
@@ -369,6 +268,11 @@ class BoardAdmin(admin.ModelAdmin):
     def get_readonly_fields(self, request, obj=None):
         return [] if obj is None else ["code", "group_link"]
 
+    def save_model(self, request, obj, form, change):
+        super().save_model(request, obj, form, change)
+        if change and (w := board_settings.stranded(obj)):  # 단계를 꺼서 그 단계에 회차가 남았다(설계 5.1)
+            self.message_user(request, w, messages.WARNING)
+
     @admin.display(description="단계")
     def step_line(self, obj):
         return " → ".join(obj.step_name(s) for s in obj.steps())
```

- [ ] **Step 5: 서비스를 더한다** — `duty/services/board_settings.py`

```diff
diff --git a/duty/services/board_settings.py b/duty/services/board_settings.py
index 5f195b8..1a63c99 100644
--- a/duty/services/board_settings.py
+++ b/duty/services/board_settings.py
@@ -7,15 +7,19 @@ from django.contrib.admin.models import CHANGE, LogEntry
 from django.contrib.contenttypes.models import ContentType
 from django.core.exceptions import PermissionDenied
 from django.db import transaction
-from django.db.models import Q
+from django.db.models import Count, Q
 
 from .. import perms
 from ..errors import DutyError
-from ..models import Department, User
+from ..models import BoardShift, Commute, Department, DutyAssignment, Period, User
+from ..shifts import SHIFT_KEYS, is_slot_cell, josa, shift_defs
 from . import boards
 
 log = logging.getLogger(__name__)
 
+S = Period.Status
+BEFORE_PUBLISH = [S.DRAFT, S.COLLECTING, S.CLOSED, S.GENERATED]
+INVALID = "저장하지 않았습니다. 빨간 글씨로 표시한 칸을 고쳐 주세요."
 NO_ADMIN_LEFT = "재직 중인 관리자가 아무도 남지 않습니다. 회차·배포·설정을 할 사람이 없으니 다른 사람을 먼저 넣으세요."
 
 
@@ -99,3 +103,87 @@ def remove_assignee(by, board, dept, user) -> None:
         raise PermissionDenied("이 부서의 입력 담당자가 아닙니다.")
     dept.input_group.user_set.remove(user)
     _audit(by, board, user, user.username, f"{dept.code} 입력 담당자 빼기")
+
+
+class NeedsConfirm(DutyError):
+    """저장하지 않고 한 번 더 묻는다: 화면이 글을 보이고 [그래도 저장]이 rows 를 confirm 으로 다시 보낸다
+    (메모의 근무 없음 확인과 같은 방식: 그사이 rows 가 바뀌면 다시 묻는다)."""
+
+    def __init__(self, message: str, rows: int):
+        super().__init__(message)
+        self.rows = rows
+
+
+def stranded(board) -> str:
+    """끈 단계에 남은 회차 안내(설계 5.1·6.2). 없으면 빈 글자. 단계 저장 결과(설정 화면·관리 화면)에 쓴다."""
+    on = board.steps()
+    lines = [f"'{board.step_name(s)}' 단계에 회차 {n}개가 남아 있습니다." for s in (S.DRAFT, S.CLOSED)
+             if s not in on and (n := Period.objects.filter(board=board, status=s).count())]
+    return " ".join(lines) + " 회차 화면에서 다른 단계로 옮기세요." if lines else ""
+
+
+@transaction.atomic
+def save_steps(by, board, form) -> str:
+    """회차 단계 칸 저장(form = forms.StepsForm, instance 는 그 근무표를 새로 읽은 것). 끈 단계에 회차가 남으면 그 안내를 돌려준다."""
+    _require_admin(by, board)
+    if form.instance.pk != board.pk:
+        raise PermissionDenied("이 근무표의 단계가 아닙니다.")
+    if not form.is_valid():
+        raise DutyError(INVALID)
+    form.save()
+    _audit(by, board, board, board.code, "회차 단계 저장")
+    return stranded(form.instance)
+
+
+def _names(keys, labels) -> str:
+    """'이른'·'늦은'을 처럼 이름을 잇고 끝 이름에 맞는 '을/를'."""
+    names = [labels[k] for k in keys]
+    return "·".join(f"'{n}'" for n in names) + josa(names[-1], "을/를")
+
+
+@transaction.atomic
+def save_shifts(by, board, formset, dept_forms, confirm: int | None = None) -> list[str]:
+    """근무 정의(formset = forms.BoardShiftFormSet, instance=board)와 부서 출근조·점심 시각(dept_forms = 그 근무표 부서마다
+    forms.DeptShiftsForm)을 한 트랜잭션으로 저장한다(설계 6.2). 돌려주는 것 = 저장한 뒤 보일 경고 글들.
+    - 표 전체 검사의 '부서마다 켜진 입력 근무조 하나 이상'은 이번에 저장할 부서 출근조로 본다(같은 저장에서 근무조를 끄고 옮길 수 있게).
+    - 부서에서 켜진 근무조를 빼는데 배포 전 회차에 그 부서·근무조 출근표가 있으면 저장하지 않고 NeedsConfirm(confirm = 본 행 수).
+    - 생성됨 회차에 배정이 남은 장중관제 정의를 끄면 저장하고 경고."""
+    _require_admin(by, board)
+    if formset.instance.pk != board.pk or any(f.instance.board_id != board.pk for f in dept_forms):
+        raise PermissionDenied("이 근무표의 근무 정의·부서가 아닙니다.")
+    depts_ok = all([f.is_valid() for f in dept_forms])  # 모든 부서의 오류를 한 번에 보이게(목록으로 다 돌린다)
+    if depts_ok:
+        formset.planned_depts = {f.instance.name: set(f.cleaned_data["shifts"]) for f in dept_forms}
+    if not (formset.is_valid() and depts_ok):
+        raise DutyError(INVALID)
+    rows = [f.cleaned_data for f in formset.forms if f.cleaned_data.get("key")]
+    labels = {r["key"]: r["name"] for r in rows}
+    on_after = {r["key"] for r in rows if r["key"] in SHIFT_KEYS and r["active"]}
+    lost, total = [], 0
+    for f in dept_forms:  # 꺼진 근무조의 행은 표 저장 때 남으므로(collect._kept_keys) 켜진 근무조를 뺄 때만 묻는다
+        gone = [k for k in SHIFT_KEYS if k in set(f.instance.shift_keys()) - set(f.cleaned_data["shifts"]) and k in on_after]
+        qs = Commute.objects.filter(period__board=board, period__status__in=BEFORE_PUBLISH, member__department=f.instance,
+                                    shift__in=gone)
+        if gone and (n := qs.count()):
+            names = ", ".join(sorted(set(qs.values_list("period__name", flat=True))))
+            lost.append(f"{f.instance.name} 부서에서 {_names(gone, labels)} 빼면 배포 전 회차({names})의 "
+                        f"그 근무조 출근표 {n}행이 다음 표 저장 때 지워집니다.")
+            total += n
+    if total and confirm != total:
+        raise NeedsConfirm(" ".join(lost) + " 그래도 저장하려면 [그래도 저장]을 누르세요.", total)
+    was_on = dict(BoardShift.objects.filter(board=board).values_list("key", "active"))
+    turned_off = [r for r in rows if is_slot_cell(r["key"]) and was_on.get(r["key"]) and not r["active"]]
+    formset.save()
+    order = [x.key for x in shift_defs(boards.defs(board))]  # 부서 출근조는 시작 시각 순 쉼표 글자(입력 표 칸 순서)
+    for f in dept_forms:
+        dept = f.save(commit=False)
+        dept.shifts = ",".join(k for k in order if k in f.cleaned_data["shifts"])
+        dept.save()
+    generated = board.step_name(S.GENERATED)
+    warnings = [f"{generated} 회차({name})에 '{r['name']}' 배정 {n}개가 남아 있습니다. "
+                "다시 생성하거나 다른 상태로 옮기면 지워지고, 그대로 배포하면 근무표에 나옵니다."
+                for r in turned_off
+                for name, n in DutyAssignment.objects.filter(period__board=board, period__status=S.GENERATED, cell=r["key"])
+                .values_list("period__name").annotate(n=Count("id")).order_by("period__name")]
+    _audit(by, board, board, board.code, "근무 정의·부서 저장")
+    return warnings
```

- [ ] **Step 6: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_board_settings_shifts.py tests/test_admin_boards.py tests/test_admin_department.py` → PASS(`14` + 관리 화면 테스트)
Run: `.venv/bin/pytest -W error -q` → `1360 passed`
Run: `makemigrations duty --check --dry-run` → "No changes detected in app 'duty'"

- [ ] **Step 7: 브라우저로 본다**

관리 화면 → 근무표 → IT 당번표: 근무 정의 인라인·단계 묶음이 Task 3 상태와 같게 보이고(옮긴 폼), 이름 하나를 바꿔 저장했다가 되돌릴 수 있다. 운영팀에서 "작성 중 단계 사용"을 켜고 저장 → 성공. 다시 끈 뒤(그사이 회차를 만들지 않았으면) 경고 없음. [회차]에서 운영팀 작성 중 회차를 하나 만들고(작성 중을 켠 상태) 다시 끄고 저장하면 "'작성 중' 단계에 회차 1개가 남아 있습니다. 회차 화면에서 다른 단계로 옮기세요." 경고. 확인 뒤 그 회차를 지운다.

- [ ] **Step 8: 커밋한다**

```bash
git add duty/forms.py duty/admin.py duty/services/board_settings.py tests/test_board_settings_shifts.py tests/test_admin_boards.py
git commit -m "feat: 근무 정의·단계 검사 폼을 duty/forms.py 로 옮기고 단계 저장과 근무 정의·부서 한 번에 저장 서비스를 더한다

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 5: 설정 화면 1 — 들어가기·칸 바로가기·칸 안 메시지·관리자·입력 담당자

> 범위: 설계 7.1(주소·메뉴·제목·근무표 링크·404·바로가기·앵커·칸 안 메시지), 7.2 의 2·3번 칸. 근무 정의와 부서·단계 칸은 Task 6.

**Files:**
- Create: `duty/views/board_settings.py`, `duty/templates/duty/board_settings.html`, `duty/templates/duty/_section_msgs.html`
- Modify: `duty/urls.py`(`settings/`), `duty/context.py`(메뉴 [근무표 설정]), `duty/templates/duty/base.html`(맨 위 메시지는 칸 태그 없는 것만)
- Test: `tests/test_views_board_settings.py`(새 파일)

**Interfaces:**
- Consumes: `board_settings.add_admin`·`remove_admin`·`add_assignee`·`remove_assignee`·`admin_candidates`·`assignee_candidates`(Task 2), `views.common.admin_required`, `shifts.josa`
- Produces:
  - URL 이름 `board_settings` = `/settings/`(`?board=<code>`)
  - POST `do` 값: `add_admin`·`remove_admin`(+`user`), `add_assignee`·`remove_assignee`(+`dept`·`user`). 모르는 `do`·없는 id·범위 밖은 404. 성공 redirect `/settings/?board=<code>#admins`(또는 `#assignees`)
  - 템플릿 조각 `duty/_section_msgs.html`(`sec` = 칸 id): 그 칸 태그 메시지만
  - `views.board_settings.ACTIONS`(Task 6 이 `shifts`·`steps` 를 더한다), `_render(request, board, ...)`

- [ ] **Step 1: 실패 테스트를 쓴다** — `tests/test_views_board_settings.py`

```python
"""[근무표 설정] 화면(근무표 통합 설계 7·8절): 들어가기·칸 바로가기·칸 안 메시지·관리자·입력 담당자. 이름은 모두 가상."""
import pytest
from django.contrib.auth.models import Group

from duty.models import Department, User

URL = "/settings/"


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


def _admins(board):
    return set(board.admin_group.user_set.values_list("username", flat=True))


# ── 들어가기 ──

def test_menu_and_access(client, ops_board, ops_admin, make_member, admin_user):
    member = make_member("가상가", user=True)
    client.force_login(member)
    assert 'href="/settings/"' not in client.get("/").content.decode()
    assert client.get(URL).status_code == 403  # 관리자가 아니면(다른 관리자 화면과 같다)
    su = User.objects.create_superuser("root", password=None, name="가상슈퍼")
    client.force_login(su)
    assert client.get(URL).status_code == 403  # 슈퍼유저라도 관리 그룹에 없으면
    client.force_login(ops_admin)
    assert '<a href="/settings/" aria-current="page">근무표 설정</a>' in client.get(URL).content.decode()
    assert client.get(URL + "?board=it").status_code == 404  # 관리하지 않는 근무표
    assert client.get(URL + "?board=nope").status_code == 404
    client.logout()
    assert client.get(URL).status_code == 302  # 로그인 화면으로


def test_title_board_links_and_jump_bar(client, ops_board, admin_user):
    client.force_login(admin_user)
    body = client.get(URL).content.decode()
    assert "<h3>근무표 설정 · IT 당번표</h3>" in body and 'class="seg"' not in body  # 관리하는 근무표가 하나면 링크 없음
    for anchor in ("#admins", "#assignees"):
        assert f'href="{anchor}"' in body
    ops_board.admin_group.user_set.add(admin_user)
    body = client.get(URL + "?board=ops").content.decode()
    assert "<h3>근무표 설정 · 운영팀</h3>" in body
    assert '<a href="/settings/?board=it">IT 당번표</a>' in body and '<a href="/settings/?board=ops" aria-current="page">운영팀</a>' in body
    assert "<h3>근무표 설정 · IT 당번표</h3>" in client.get(URL).content.decode()  # ?board 없으면 내 근무표


def test_unknown_action_and_bad_ids_are_404(ops_client):
    assert ops_client.post(URL + "?board=ops", {"do": "nope"}).status_code == 404
    assert ops_client.post(URL + "?board=ops", {"do": "add_admin", "user": "x"}).status_code == 404
    assert ops_client.post(URL + "?board=ops", {"do": "add_assignee", "dept": "ZZ", "user": "1"}).status_code == 404


# ── 관리자 ──

def test_add_admin_message_inside_section(ops_client, ops_board):
    m = _ops_member("가상하나", "OPS801")
    r = ops_client.post(URL + "?board=ops", {"do": "add_admin", "user": m.pk})
    assert r.status_code == 302 and r["Location"] == "/settings/?board=ops#admins"
    body = ops_client.get(URL + "?board=ops").content.decode()
    msg = '<div class="msg success" role="status">가상하나를 관리자로 넣었습니다.</div>'
    assert body.index('<section id="admins"') < body.index(msg) < body.index('<section id="assignees"')  # 맨 위가 아니라 그 칸 안
    assert _admins(ops_board) == {"opsadm", "OPS801"}


def test_admin_rows(ops_client, ops_board, ops_admin):
    body = ops_client.get(URL + "?board=ops").content.decode()
    assert "마지막 관리자" in body and 'value="remove_admin"' not in body  # 재직 관리자가 나 하나
    other, gone = _ops_member("가상하나", "OPS801"), _ops_member("가상퇴사", "OPS802", active=False)
    ops_board.admin_group.user_set.add(other, gone)
    body = ops_client.get(URL + "?board=ops").content.decode()
    assert "가상퇴사 (퇴사)" in body and "빼기는 슈퍼유저에게" in body and "마지막 관리자" not in body
    assert body.count('value="remove_admin"') == 2  # 나와 퇴사자만
    admins = body[body.index('<section id="admins"'):body.index('<section id="assignees"')]
    assert f'<option value="{other.pk}">' not in admins  # 이미 관리자는 넣기 후보가 아니다


def test_cannot_remove_other_active_admin_or_add_outsider(ops_client, ops_board, make_member):
    other = _ops_member("가상하나", "OPS801")
    ops_board.admin_group.user_set.add(other)
    assert ops_client.post(URL + "?board=ops", {"do": "remove_admin", "user": other.pk}).status_code == 404
    it_person = make_member("가상아이티")
    assert ops_client.post(URL + "?board=ops", {"do": "add_admin", "user": it_person.pk}).status_code == 404
    assert _admins(ops_board) == {"opsadm", "OPS801"}


def test_remove_self(ops_client, ops_board, ops_admin):
    r = ops_client.post(URL + "?board=ops", {"do": "remove_admin", "user": ops_admin.pk}, follow=True)
    assert "재직 중인 관리자가 아무도 남지 않습니다" in r.content.decode()  # 마지막 재직 관리자
    ops_board.admin_group.user_set.add(_ops_member("가상하나", "OPS801"))
    r = ops_client.post(URL + "?board=ops", {"do": "remove_admin", "user": ops_admin.pk})
    assert r.status_code == 302 and r["Location"] == "/"  # 더 관리하는 근무표가 없으면 근무표 화면으로
    assert _admins(ops_board) == {"OPS801"}


# ── 입력 담당자 ──

def test_assignees(ops_client, ops_board):
    body = ops_client.get(URL + "?board=ops").content.decode()
    assert "담당자 없음 — 근무표 관리자만 입력합니다" in body
    a = _ops_member("가상하나", "OPS801")
    r = ops_client.post(URL + "?board=ops", {"do": "add_assignee", "dept": "OPS", "user": a.pk})
    assert r["Location"] == "/settings/?board=ops#assignees"
    dept = Department.objects.get(code="OPS")
    assert list(dept.input_group.user_set.all()) == [a]
    body = ops_client.get(URL + "?board=ops").content.decode()
    assert body.index('<section id="assignees"') < body.index("가상하나를 운영 입력 담당자로 넣었습니다.")
    assert "담당자 없음" not in body
    ops_client.post(URL + "?board=ops", {"do": "remove_assignee", "dept": "OPS", "user": a.pk})
    assert not dept.input_group.user_set.exists()


def test_assignee_other_board_dept_is_404(ops_client, depts, make_member):
    it_person = make_member("가상아이티")
    a = _ops_member("가상하나", "OPS801")
    assert ops_client.post(URL + "?board=ops", {"do": "add_assignee", "dept": "MEMS", "user": a.pk}).status_code == 404
    assert ops_client.post(URL + "?board=ops", {"do": "add_assignee", "dept": "OPS", "user": it_person.pk}).status_code == 404
    assert not depts["MEMS"].input_group.user_set.exists()


def test_assignee_group_name_clash_shown_in_section(ops_client):
    Group.objects.create(name="운영 출근표 입력")
    a = _ops_member("가상하나", "OPS801")
    r = ops_client.post(URL + "?board=ops", {"do": "add_assignee", "dept": "OPS", "user": a.pk}, follow=True)
    body = r.content.decode()
    assert body.index('<section id="assignees"') < body.index("같은 이름의 그룹이 이미 있습니다: 운영 출근표 입력. 슈퍼유저에게")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_views_board_settings.py`
Expected: FAIL — `/settings/` 가 404(`assert 404 == 403` 등, 10 failed)

- [ ] **Step 3: 구현한다**

`duty/urls.py`·`duty/context.py`·`duty/templates/duty/base.html`:
```diff
diff --git a/duty/context.py b/duty/context.py
index ad422e5..dc78eb3 100644
--- a/duty/context.py
+++ b/duty/context.py
@@ -20,6 +20,7 @@ def nav(request):
         if perms.stats_boards(user).exists():  # 통계는 slot* 정의가 있는 근무표의 관리 그룹만(설계 7절)
             items.append(("통계", "/stats/", ()))
         items.append(("이력", "/changes/", ()))
+        items.append(("근무표 설정", "/settings/", ()))  # 관리자·입력 담당자·근무 정의와 부서·단계(근무표 통합 설계 7절)
     if perms.kept_groups(user).exists():  # 그룹 관리자(GroupKeeper)만(설계 7절)
         items.append(("그룹", "/groups/", ()))
     if user.is_superuser:
diff --git a/duty/templates/duty/base.html b/duty/templates/duty/base.html
index 91607bd..291ccf0 100644
--- a/duty/templates/duty/base.html
+++ b/duty/templates/duty/base.html
@@ -181,7 +181,7 @@
     </div>
     {% if menu %}<nav class="menu" aria-label="메뉴"><ul>{% for m in menu %}<li><a href="{{ m.url }}"{% if m.active %} aria-current="page"{% endif %}>{{ m.label }}</a></li>{% endfor %}</ul></nav>{% endif %}
   </header>
-  {% for m in messages %}<div class="msg {{ m.tags }}" role="{% if m.level >= 40 %}alert{% else %}status{% endif %}">{{ m }}</div>{% endfor %}
+  {% for m in messages %}{% if not m.extra_tags %}<div class="msg {{ m.tags }}" role="{% if m.level >= 40 %}alert{% else %}status{% endif %}">{{ m }}</div>{% endif %}{% endfor %}{# 칸 태그가 있는 메시지는 그 칸 안에서(근무표 설정) #}
   {% block content %}{% endblock %}
   {% if repo_url %}<footer class="site-foot"><a href="{{ repo_url }}" target="_blank" rel="noopener">GitHub 저장소</a></footer>{% endif %}
 </main>
diff --git a/duty/urls.py b/duty/urls.py
index 9889854..c6aa4d5 100644
--- a/duty/urls.py
+++ b/duty/urls.py
@@ -5,6 +5,7 @@ from django.urls import path, register_converter
 
 from .views import alarms as alarm_views
 from .views import auth as auth_views_local
+from .views import board_settings as board_settings_views
 from .views import calendar as calendar_views
 from .views import collect as collect_views
 from .views import help as help_views
@@ -49,6 +50,7 @@ urlpatterns = [
     path("stats/", manage_views.stats_view, name="stats"),
     path("changes/", manage_views.change_log, name="changes"),
     path("groups/", manage_views.groups, name="groups"),
+    path("settings/", board_settings_views.index, name="board_settings"),
     path("alarms/", alarm_views.index, name="alarms"),
     path("alarms/telegram/", alarm_views.telegram_save, name="alarm_telegram"),
     path("alarms/telegram/link/", alarm_views.telegram_link, name="alarm_telegram_link"),
```

`duty/templates/duty/_section_msgs.html`(새 파일):
```django
{% for m in messages %}{% if m.extra_tags == sec %}<div class="msg {{ m.level_tag }}" role="{% if m.level >= 40 %}alert{% else %}status{% endif %}">{{ m }}</div>{% endif %}{% endfor %}
```

`duty/views/board_settings.py`(새 파일):
```python
"""[근무표 설정](근무표 통합 설계 7절): 근무표 관리자가 그 근무표의 관리자·입력 담당자·근무 정의와 부서·회차 단계를 고치는
한 화면(/settings/?board=<code>). 칸마다 따로 저장하고 저장 뒤 그 칸(#앵커)으로 돌아온다. 결과 메시지는 extra_tags 에 칸 id 를
넣어 그 칸 제목 바로 아래에 그린다(base.html 맨 위에는 칸 태그가 없는 메시지만). DB 쓰기는 services/board_settings.py."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from .. import perms
from ..errors import DutyError
from ..models import Department, User
from ..services import board_settings, boards
from ..shifts import josa
from .common import admin_required


def _board(request):
    """?board=<code> 의 근무표: 내가 관리하는 근무표만(아니면 404, 회차 화면과 같은 방식). 없으면 내 근무표(관리할 때) → 관리하는 첫 근무표."""
    mine = list(perms.admin_boards(request.user).order_by("id"))  # admin_required 를 지났으니 비어 있지 않다
    code = request.GET.get("board")
    if code:
        board = next((b for b in mine if b.code == code), None)
        if board is None:
            raise Http404
    else:
        home = boards.home(request.user)
        board = next((b for b in mine if b.pk == home.pk), mine[0])
    return board, mine


def _here(board) -> str:
    return f"{reverse('board_settings')}?board={board.code}"


def _user(request) -> User:
    pid = request.POST.get("user", "")
    user = User.objects.filter(pk=pid).first() if pid.isdigit() else None
    if user is None:
        raise Http404
    return user


def _dept(request) -> Department:
    dept = Department.objects.filter(pk=request.POST.get("dept", "")).first()
    if dept is None:
        raise Http404
    return dept


def _add_admin(request, board):
    user = _user(request)
    board_settings.add_admin(request.user, board, user)
    return f"{user.name}{josa(user.name, '을/를')} 관리자로 넣었습니다."


def _remove_admin(request, board):
    user = _user(request)
    board_settings.remove_admin(request.user, board, user)
    if user.pk == request.user.pk:  # 나를 뺐다: 이 근무표 설정에는 더 들어올 수 없다
        messages.success(request, f"{board.name} 관리자에서 나를 뺐습니다.")
        return redirect("board_settings" if perms.is_admin(request.user) else "roster")
    return f"{user.name}{josa(user.name, '을/를')} 관리자에서 뺐습니다."


def _add_assignee(request, board):
    dept, user = _dept(request), _user(request)
    board_settings.add_assignee(request.user, board, dept, user)
    return f"{user.name}{josa(user.name, '을/를')} {dept.name} 입력 담당자로 넣었습니다."


def _remove_assignee(request, board):
    dept, user = _dept(request), _user(request)
    board_settings.remove_assignee(request.user, board, dept, user)
    return f"{user.name}{josa(user.name, '을/를')} {dept.name} 입력 담당자에서 뺐습니다."


ACTIONS = {  # POST do → (칸 id, 처리). 처리는 결과 글(성공 메시지)이나 응답(다시 그리기·다른 곳으로)을 돌려준다
    "add_admin": ("admins", _add_admin), "remove_admin": ("admins", _remove_admin),
    "add_assignee": ("assignees", _add_assignee), "remove_assignee": ("assignees", _remove_assignee),
}


def _render(request, board, mine):
    me = request.user
    admins = sorted(board.admin_group.user_set.select_related("department"), key=lambda u: u.name)
    active_n = sum(u.is_active for u in admins)
    # 빼기: 나 자신(재직 관리자가 나 말고도 있을 때)과 퇴사한 관리자만. 다른 재직 관리자는 슈퍼유저(설계 7.2)
    admin_rows = [(u, "remove" if not u.is_active or (u.pk == me.pk and active_n > 1)
                   else "last" if u.pk == me.pk else "superuser") for u in admins]
    depts = [{"dept": d, "members": sorted(d.input_group.user_set.select_related("department"), key=lambda u: u.name)
              if d.input_group_id else [], "candidates": board_settings.assignee_candidates(board, d)}
             for d in board.departments.select_related("input_group").order_by("order", "code")]
    return render(request, "duty/board_settings.html", {
        "board": board, "boards": mine, "here": _here(board),
        "admin_rows": admin_rows, "admin_candidates": board_settings.admin_candidates(board), "depts": depts,
    })


@admin_required
def index(request):
    board, mine = _board(request)
    if request.method == "POST":
        if request.POST.get("do") not in ACTIONS:
            raise Http404
        section, act = ACTIONS[request.POST["do"]]
        try:
            out = act(request, board)
        except PermissionDenied:  # 그 근무표 밖의 부서·사람, 대상이 아닌 사람: 없는 것처럼
            raise Http404 from None
        except DutyError as e:
            messages.error(request, str(e), extra_tags=section)
        else:
            if not isinstance(out, str):
                return out
            messages.success(request, out, extra_tags=section)
        return redirect(f"{_here(board)}#{section}")
    return _render(request, board, mine)
```

`duty/templates/duty/board_settings.html`(새 파일):
```django
{% extends "duty/base.html" %}
{% block title %}근무표 설정 · {{ board.name }}{% endblock %}
{% block content %}
<h3>근무표 설정 · {{ board.name }}</h3>
{% if boards|length > 1 %}<p class="seg" role="group" aria-label="고칠 근무표">{% for b in boards %}<a href="{% url 'board_settings' %}?board={{ b.code }}"{% if b.pk == board.pk %} aria-current="page"{% endif %}>{{ b.name }}</a>{% endfor %}</p>{% endif %}
<nav class="jump" aria-label="칸 바로가기"><a href="#admins">관리자</a><a href="#assignees">입력 담당자</a></nav>

<section id="admins" class="cfg">
  <h4>관리자 <small>회차·생성·배포·메모·통계·이력과 이 설정을 하는 사람</small></h4>
  {% include "duty/_section_msgs.html" with sec="admins" %}
  <ul class="members">{% for u, how in admin_rows %}
    <li><span>{{ u.name }}{% if not u.is_active %} (퇴사){% endif %} <small>· {{ u.department.name|default:"부서 없음" }}</small></span>
      {% if how == "remove" %}<form method="post" action="{{ here }}#admins" onsubmit="return confirm('{{ u.name|escapejs }}을(를) {{ board.name|escapejs }} 관리자에서 뺄까요?{% if u.pk == user.pk %} 빼면 이 근무표의 회차·설정 화면에 들어올 수 없습니다.{% endif %}')">{% csrf_token %}
        <input type="hidden" name="do" value="remove_admin"><input type="hidden" name="user" value="{{ u.pk }}">
        <button class="outline secondary">빼기</button></form>
      {% elif how == "last" %}<small class="note">마지막 관리자</small>{% else %}<small class="note">빼기는 슈퍼유저에게</small>{% endif %}</li>{% endfor %}</ul>
  <form method="post" action="{{ here }}#admins" class="add labeled">{% csrf_token %}<input type="hidden" name="do" value="add_admin">
    <label>넣을 사람 <select name="user" required><option value="">고르세요</option>{% for u in admin_candidates %}<option value="{{ u.pk }}">{{ u.name }}({{ u.department.name|default:"부서 없음" }})</option>{% endfor %}</select></label>
    <button>넣기</button>
  </form>
</section>

<section id="assignees" class="cfg">
  <h4>입력 담당자 <small>취합 중인 회차에 자기 부서 출근표를 넣는 사람. 관리자는 담당자가 아니어도 모든 부서를 넣습니다</small></h4>
  {% include "duty/_section_msgs.html" with sec="assignees" %}
  {% for it in depts %}<article class="dept">
    <header><strong>{{ it.dept.name }}</strong></header>
    {% if it.members %}<ul class="members">{% for u in it.members %}
      <li><span>{{ u.name }}{% if not u.is_active %} (퇴사){% endif %}</span>
        <form method="post" action="{{ here }}#assignees" onsubmit="return confirm('{{ u.name|escapejs }}을(를) {{ it.dept.name|escapejs }} 입력 담당자에서 뺄까요?')">{% csrf_token %}
          <input type="hidden" name="do" value="remove_assignee"><input type="hidden" name="dept" value="{{ it.dept.pk }}"><input type="hidden" name="user" value="{{ u.pk }}">
          <button class="outline secondary">빼기</button></form></li>{% endfor %}</ul>
    {% else %}<p class="none">담당자 없음 — 근무표 관리자만 입력합니다</p>{% endif %}
    <form method="post" action="{{ here }}#assignees" class="add labeled">{% csrf_token %}<input type="hidden" name="do" value="add_assignee"><input type="hidden" name="dept" value="{{ it.dept.pk }}">
      <label>넣을 사람 <select name="user" required><option value="">고르세요</option>{% for u in it.candidates %}<option value="{{ u.pk }}">{{ u.name }}({{ u.department.name }})</option>{% endfor %}</select></label>
      <button>넣기</button>
    </form>
  </article>{% endfor %}
</section>
<style>
  nav.jump { display: flex; flex-wrap: wrap; gap: .4rem; margin: 0 0 1.5rem; }
  nav.jump a { display: inline-flex; align-items: center; min-height: 44px; padding: 0 1rem; border: 1px solid var(--duty-line); border-radius: .4rem; text-decoration: none; }
  section.cfg { margin: 0 0 2.5rem; scroll-margin-top: 1rem; }
  section.cfg > h4 { margin-bottom: .8rem; }
  section.cfg > h4 small { display: block; margin-top: .2rem; font-weight: 400; font-size: .85rem; opacity: .75; }
  section.cfg article.dept { max-width: 40rem; }
  ul.members { padding: 0; margin: 0 0 1rem; max-width: 40rem; }
  ul.members li { list-style: none; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem;
    min-height: 44px; padding: .4rem 0; border-bottom: 1px solid var(--duty-line); }
  ul.members form, ul.members button { width: auto; margin: 0; }
  ul.members button { min-height: 44px; padding: .4rem 1rem; }
  ul.members .note { opacity: .75; }
  p.none { margin: 0 0 1rem; font-weight: 700; }
  form.add { display: flex; flex-wrap: wrap; align-items: flex-end; gap: .5rem; max-width: 40rem; }
  form.add label { flex: 1 1 14rem; margin: 0; }
  form.add select { margin: 0; }
  form.add button { width: auto; margin: 0; min-height: 44px; }
</style>
{% endblock %}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_views_board_settings.py` → `10 passed`
Run: `.venv/bin/pytest -W error -q` → `1370 passed`(스냅샷 그대로: 메뉴는 `<header>` 안)

- [ ] **Step 5: 브라우저로 본다**(`admin`)

메뉴 [근무표 설정] → 제목 "근무표 설정 · IT 당번표", 아래 근무표 링크 [IT 당번표](채움)·[운영팀], 바로가기 [관리자] [입력 담당자]. [운영팀] → 관리자 칸에 나관리 한 줄과 "마지막 관리자"(운영팀 재직 관리자가 나 하나라 [빼기]가 없다). 넣을 사람에서 가상하나(운영)를 [넣기] → 같은 칸으로 돌아와 칸 제목 아래 "✓ 가상하나를 관리자로 넣었습니다."(맨 위가 아니라). 가상하나 줄에 "빼기는 슈퍼유저에게", 내 줄에 [빼기]. 입력 담당자 칸: "담당자 없음 — 근무표 관리자만 입력합니다" → 가상두리 [넣기] → 목록에 가상두리와 [빼기](확인창). 1400px: 목록 폭 40rem. 390px: 줄이 감기고 [빼기]·[넣기] 44px 이상, 가로 넘침 없음. 다크·아주 크게에서 메시지 색·글씨가 읽힌다. 확인 뒤 넣은 관리자는 관리 화면에서, 담당자는 [빼기]로 되돌린다.

- [ ] **Step 6: 커밋한다**

```bash
git add duty/views/board_settings.py duty/templates/duty/board_settings.html duty/templates/duty/_section_msgs.html duty/urls.py duty/context.py duty/templates/duty/base.html tests/test_views_board_settings.py
git commit -m "feat: 근무표 설정 화면(관리자·입력 담당자 칸, 칸 바로가기와 칸 안 결과 메시지)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 6: 설정 화면 2 — 근무 정의와 부서·회차 단계

> 범위: 설계 7.2 의 4·5번 칸. 근무 정의는 `fieldset` 카드를 CSS grid 로(1400px 여럿, 390px·아주 크게 하나), 부서는 부서마다 `fieldset`(근무조 체크 + 점심 시각), [저장] 하나로 함께(`save_shifts`). 배정 안 된 근무조 경고와 [부서 저장], 행 수 확인 [그래도 저장]. 단계 칸은 맨 아래 접힌 `<details>`, 미리보기(저장된 단계·실제 버튼 글자), 저장 확인창.

**Files:**
- Modify: `duty/views/board_settings.py` — `_mine`·`_board`, `_shifts`·`_steps`, `ACTIONS`, `_buttons`, `_render`(근무 정의·부서·단계 맥락)
- Modify: `duty/templates/duty/board_settings.html` — 바로가기 둘, `#shifts`·`#steps` 칸, CSS
- Test: `tests/test_views_board_settings.py`(맨 끝에 더함)

**Interfaces:**
- Consumes: `forms.shift_forms`·`StepsForm`(Task 4), `board_settings.save_shifts`·`save_steps`·`NeedsConfirm`(Task 4), `Board.step_buttons`, `shifts.shift_defs`·`slot_defs`
- Produces: POST `do=shifts`(근무 정의 formset prefix `shifts`, 부서 칸 `d-<코드>-shifts`·`-lunch_start`·`-lunch_end`, 선택 `confirm`), `do=steps`(`use_draft`·`use_close`·`step_*`). 성공 redirect `#shifts`·`#steps`, 오류·확인은 200 으로 다시 그림

- [ ] **Step 1: 실패 테스트를 쓴다**

```diff
diff --git a/tests/test_views_board_settings.py b/tests/test_views_board_settings.py
index aa0984a..20f35a1 100644
--- a/tests/test_views_board_settings.py
+++ b/tests/test_views_board_settings.py
@@ -1,8 +1,11 @@
 """[근무표 설정] 화면(근무표 통합 설계 7·8절): 들어가기·칸 바로가기·칸 안 메시지·관리자·입력 담당자. 이름은 모두 가상."""
+from datetime import date
+
 import pytest
 from django.contrib.auth.models import Group
 
-from duty.models import Department, User
+from duty.models import BoardShift, Commute, Department, Period, User
+from tests.test_board_settings_shifts import shift_data
 
 URL = "/settings/"
 
@@ -139,3 +142,99 @@ def test_assignee_group_name_clash_shown_in_section(ops_client):
     r = ops_client.post(URL + "?board=ops", {"do": "add_assignee", "dept": "OPS", "user": a.pk}, follow=True)
     body = r.content.decode()
     assert body.index('<section id="assignees"') < body.index("같은 이름의 그룹이 이미 있습니다: 운영 출근표 입력. 슈퍼유저에게")
+
+
+# ── 근무 정의와 부서 ──
+
+def _post_shifts(client, board, **kw):
+    confirm = kw.pop("confirm", None)
+    data = dict(shift_data(board, **kw).lists()) | {"do": "shifts"} | ({"confirm": confirm} if confirm else {})
+    return client.post(f"{URL}?board={board.code}", data)
+
+
+def test_shifts_section_shows_cards_and_departments(ops_client, ops_board):
+    body = ops_client.get(URL + "?board=ops").content.decode()
+    for name in ("이른", "가운데", "늦은", "점심당번"):
+        assert f"<legend>{name}</legend>" in body
+    assert "<legend>새 근무 정의(더할 때만 채웁니다)</legend>" in body and "<legend>운영</legend>" in body
+    assert "이른 07:30~16:30" in body  # 부서 출근조 체크박스: 이름과 시각
+    assert "아직 부서에 배정되지 않은 근무조" not in body and ">부서 저장</button>" not in body
+
+
+def test_new_shift_then_check_it_in_department(ops_client, ops_board):
+    r = _post_shifts(ops_client, ops_board, extra={"key": "night", "name": "밤", "start": "13:00", "end": "22:00", "active": "on"})
+    assert r.status_code == 302 and r["Location"] == "/settings/?board=ops#shifts"
+    body = ops_client.get(URL + "?board=ops").content.decode()
+    assert body.index('<section id="shifts"') < body.index("근무 정의와 부서를 저장했습니다.")
+    assert "아직 부서에 배정되지 않은 근무조: 밤. 아래 부서에서 체크하고 [부서 저장]을 누르세요." in body
+    assert '<button class="wide">부서 저장</button>' in body
+    _post_shifts(ops_client, ops_board, depts={"OPS": {"shifts": ["dawn", "normal", "dinner", "night"]}})
+    body = ops_client.get(URL + "?board=ops").content.decode()
+    assert "아직 부서에 배정되지 않은 근무조" not in body and Department.objects.get(code="OPS").shifts == "dawn,normal,dinner,night"
+
+
+def test_shift_errors_redraw_with_sent_values(ops_client, ops_board):
+    r = _post_shifts(ops_client, ops_board, change={"normal": {"name": "중간"}}, depts={"OPS": {"lunch_start": "11:30"}})
+    body = r.content.decode()
+    assert r.status_code == 200 and 'value="중간"' in body  # 보낸 값 그대로
+    assert body.index('<section id="shifts"') < body.index("저장하지 않았습니다. 빨간 글씨로 표시한 칸을 고쳐 주세요.")
+    assert "점심 시각은 둘 다 비우거나, 둘 다 넣고 시작을 끝보다 이르게 하세요." in body
+
+
+def test_shift_removal_confirm_flow(ops_client, ops_board):
+    m = _ops_member("가상하나", "OPS801")
+    p = Period.objects.create(board=ops_board, name="이번 회차", start_date=date(2026, 11, 16), end_date=date(2026, 11, 16),
+                              status=Period.Status.COLLECTING)
+    Commute.objects.create(period=p, date=p.start_date, member=m, shift="dinner")
+    r = _post_shifts(ops_client, ops_board, depts={"OPS": {"shifts": ["dawn", "normal"]}})
+    body = r.content.decode()
+    assert r.status_code == 200 and "그 근무조 출근표 1행이 다음 표 저장 때 지워집니다" in body
+    assert '<input type="hidden" name="confirm" value="1">' in body and ">그래도 저장</button>" in body
+    r = _post_shifts(ops_client, ops_board, depts={"OPS": {"shifts": ["dawn", "normal"]}}, confirm="1")
+    assert r.status_code == 302 and Department.objects.get(code="OPS").shifts == "dawn,normal"
+
+
+def test_shift_ids_of_other_board_are_404(ops_client, ops_board, it_board, depts):
+    it_shift = BoardShift.objects.filter(board=it_board).first()
+    data = dict(shift_data(ops_board).lists()) | {"do": "shifts"}
+    assert ops_client.post(URL + "?board=ops", data | {"shifts-0-id": [str(it_shift.pk)]}).status_code == 404
+    assert ops_client.post(URL + "?board=ops", data | {"d-MEMS-shifts": ["dawn"]}).status_code == 404
+    assert BoardShift.objects.get(pk=it_shift.pk).board_id == it_board.pk
+
+
+# ── 회차 단계 ──
+
+def _steps_post(board, **over):
+    data = {f: getattr(board, f) for f in ("step_draft", "step_collecting", "step_closed", "step_generated", "step_published")}
+    data |= {f: "on" for f in ("use_draft", "use_close") if getattr(board, f)}
+    return {k: v for k, v in (data | over | {"do": "steps"}).items() if v is not None}
+
+
+def test_steps_section_preview_and_folded(ops_client, ops_board, admin_user, client):
+    body = ops_client.get(URL + "?board=ops").content.decode()
+    assert '<section id="steps" class="cfg">\n  <details>' in body  # 접혀 있다
+    assert "저장된 단계: <strong>입력 중 → 확정 → 배포됨</strong>" in body
+    assert '<span class="btn-name">[확정]</span> <span class="btn-name">[확정 취소]</span> <span class="btn-name">[배포…]</span>' in body
+    assert "작성 중 이름 <small>(쓰지 않음 · 남은 회차·기록 표시용)</small>" in body
+    assert "return confirm('진행 중인 회차의 단계 이름과 버튼이 바로 바뀝니다. 계속할까요?')" in body
+    client.force_login(admin_user)
+    body = client.get(URL).content.decode()
+    assert "[취합 열기]</span> <span class=\"btn-name\">[취합 마감]</span> <span class=\"btn-name\">[장중관제 생성]</span> " \
+           "<span class=\"btn-name\">[재생성]</span> <span class=\"btn-name\">[배포…]" in body
+
+
+def test_save_steps_from_page(ops_client, ops_board):
+    r = ops_client.post(URL + "?board=ops", _steps_post(ops_board, use_close="on", step_closed="마감"))
+    assert r["Location"] == "/settings/?board=ops#steps"
+    body = ops_client.get(URL + "?board=ops").content.decode()
+    assert "<details open>" in body and body.index('<section id="steps"') < body.index("회차 단계를 저장했습니다.")
+    assert "저장된 단계: <strong>입력 중 → 마감 → 확정 → 배포됨</strong>" in body
+    ops_board.refresh_from_db()
+    assert ops_board.use_close
+
+
+def test_bad_step_names_redraw(ops_client, ops_board):
+    r = ops_client.post(URL + "?board=ops", _steps_post(ops_board, step_generated="됨"))
+    body = r.content.decode()
+    assert r.status_code == 200 and "<details open>" in body and "버튼 이름이 비거나 다른 버튼과 같아집니다: []" in body
+    assert "저장된 단계: <strong>입력 중 → 확정 → 배포됨</strong>" in body  # 미리보기는 저장된 값
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_views_board_settings.py`
Expected: FAIL — 7 failed, 11 passed(`test_shift_ids_of_other_board_are_404` 는 `do=shifts` 가 아직 없어 404 라 미리 통과한다)

- [ ] **Step 3: 뷰를 바꾼다** — `duty/views/board_settings.py` 전체를 아래로

```python
"""[근무표 설정](근무표 통합 설계 7절): 근무표 관리자가 그 근무표의 관리자·입력 담당자·근무 정의와 부서·회차 단계를 고치는
한 화면(/settings/?board=<code>). 칸마다 따로 저장하고 저장 뒤 그 칸(#앵커)으로 돌아온다. 결과 메시지는 extra_tags 에 칸 id 를
넣어 그 칸 제목 바로 아래에 그린다(base.html 맨 위에는 칸 태그가 없는 메시지만). DB 쓰기는 services/board_settings.py."""
import re

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from .. import perms
from ..errors import DutyError
from ..forms import StepsForm, shift_forms
from ..models import Board, Department, Period, User
from ..services import board_settings, boards
from ..shifts import josa, shift_defs, slot_defs
from .common import admin_required


def _mine(request) -> list[Board]:
    return list(perms.admin_boards(request.user).order_by("id"))  # admin_required 를 지났으니 비어 있지 않다


def _board(request) -> Board:
    """?board=<code> 의 근무표: 내가 관리하는 근무표만(아니면 404, 회차 화면과 같은 방식). 없으면 내 근무표(관리할 때) → 관리하는 첫 근무표."""
    mine, code = _mine(request), request.GET.get("board")
    if code:
        board = next((b for b in mine if b.code == code), None)
        if board is None:
            raise Http404
        return board
    home = boards.home(request.user)
    return next((b for b in mine if b.pk == home.pk), mine[0])


def _here(board) -> str:
    return f"{reverse('board_settings')}?board={board.code}"


def _user(request) -> User:
    pid = request.POST.get("user", "")
    user = User.objects.filter(pk=pid).first() if pid.isdigit() else None
    if user is None:
        raise Http404
    return user


def _dept(request) -> Department:
    dept = Department.objects.filter(pk=request.POST.get("dept", "")).first()
    if dept is None:
        raise Http404
    return dept


def _add_admin(request, board):
    user = _user(request)
    board_settings.add_admin(request.user, board, user)
    return f"{user.name}{josa(user.name, '을/를')} 관리자로 넣었습니다."


def _remove_admin(request, board):
    user = _user(request)
    board_settings.remove_admin(request.user, board, user)
    if user.pk == request.user.pk:  # 나를 뺐다: 이 근무표 설정에는 더 들어올 수 없다
        messages.success(request, f"{board.name} 관리자에서 나를 뺐습니다.")
        return redirect("board_settings" if perms.is_admin(request.user) else "roster")
    return f"{user.name}{josa(user.name, '을/를')} 관리자에서 뺐습니다."


def _add_assignee(request, board):
    dept, user = _dept(request), _user(request)
    board_settings.add_assignee(request.user, board, dept, user)
    return f"{user.name}{josa(user.name, '을/를')} {dept.name} 입력 담당자로 넣었습니다."


def _remove_assignee(request, board):
    dept, user = _dept(request), _user(request)
    board_settings.remove_assignee(request.user, board, dept, user)
    return f"{user.name}{josa(user.name, '을/를')} {dept.name} 입력 담당자에서 뺐습니다."


def _shifts(request, board):
    # 그 근무표 밖의 근무 정의 id·부서 칸을 섞어 보내면 404(설계 6.2 범위 검사. 폼도 그 근무표 것만 만든다)
    ids = {str(pk) for pk in board.shifts.values_list("pk", flat=True)}
    codes = set(board.departments.values_list("code", flat=True))
    for k, v in request.POST.items():
        other_shift = re.fullmatch(r"shifts-\d+-id", k) and v and v not in ids
        other_dept = k.startswith("d-") and k[2:].rsplit("-", 1)[0] not in codes
        if other_shift or other_dept:
            raise Http404
    formset, dept_forms = shift_forms(board, request.POST)
    confirm = request.POST.get("confirm", "")
    try:
        warnings = board_settings.save_shifts(request.user, board, formset, dept_forms,
                                              int(confirm) if confirm.isdigit() else None)
    except board_settings.NeedsConfirm as e:  # 저장하지 않았다: 보낸 값 그대로 다시 그리고 [그래도 저장]
        messages.warning(request, str(e), extra_tags="shifts")
        return _render(request, board, shifts=(formset, dept_forms), ask=e.rows)
    except DutyError as e:  # 칸 오류: 보낸 값 그대로 다시 그린다(다른 칸의 입력은 건드리지 않는다)
        messages.error(request, str(e), extra_tags="shifts")
        return _render(request, board, shifts=(formset, dept_forms))
    messages.success(request, "근무 정의와 부서를 저장했습니다.", extra_tags="shifts")
    for w in warnings:
        messages.warning(request, w, extra_tags="shifts")
    return redirect(f"{_here(board)}#shifts")


def _steps(request, board):
    form = StepsForm(request.POST, instance=Board.objects.get(pk=board.pk))  # 오류로 다시 그릴 때 화면의 board 가 바뀌지 않게 새로 읽는다
    try:
        warning = board_settings.save_steps(request.user, board, form)
    except DutyError as e:
        messages.error(request, str(e), extra_tags="steps")
        return _render(request, board, steps=form)
    if warning:  # 끈 단계에 회차가 남았다: 성공 대신 안내
        messages.warning(request, warning, extra_tags="steps")
    else:
        messages.success(request, "회차 단계를 저장했습니다.", extra_tags="steps")
    return redirect(f"{_here(board)}#steps")


ACTIONS = {  # POST do → (칸 id, 처리). 처리는 결과 글(성공 메시지)이나 응답(다시 그리기·다른 곳으로)을 돌려준다
    "add_admin": ("admins", _add_admin), "remove_admin": ("admins", _remove_admin),
    "add_assignee": ("assignees", _add_assignee), "remove_assignee": ("assignees", _remove_assignee),
    "shifts": ("shifts", _shifts), "steps": ("steps", _steps),
}


def _buttons(board, has_slots) -> list[str]:
    """미리보기: 켠 단계에서 회차 화면에 나오는 버튼 글자(설계 5.4, 회차 화면과 같은 step_buttons), 진행 순서대로."""
    b = board.step_buttons(has_slots)
    return ([b["open"]] * board.use_draft + [b["close"]] * board.use_close + [b["generate"]]
            + [x for x in (b["undo"], b["regenerate"]) if x] + ["배포…"])


def _render(request, board, shifts=None, steps=None, ask=None):
    me = request.user
    admins = sorted(board.admin_group.user_set.select_related("department"), key=lambda u: u.name)
    active_n = sum(u.is_active for u in admins)
    # 빼기: 나 자신(재직 관리자가 나 말고도 있을 때)과 퇴사한 관리자만. 다른 재직 관리자는 슈퍼유저(설계 7.2)
    admin_rows = [(u, "remove" if not u.is_active or (u.pk == me.pk and active_n > 1)
                   else "last" if u.pk == me.pk else "superuser") for u in admins]
    depts = [{"dept": d, "members": sorted(d.input_group.user_set.select_related("department"), key=lambda u: u.name)
              if d.input_group_id else [], "candidates": board_settings.assignee_candidates(board, d)}
             for d in board.departments.select_related("input_group").order_by("order", "code")]
    formset, dept_forms = shifts or shift_forms(board)
    active = boards.active_defs(board)
    assigned = {k for d in board.departments.all() for k in d.shift_keys()}
    steps = steps or StepsForm(instance=board)
    on = board.steps()
    return render(request, "duty/board_settings.html", {
        "board": board, "boards": _mine(request), "here": _here(board),
        "admin_rows": admin_rows, "admin_candidates": board_settings.admin_candidates(board), "depts": depts,
        "formset": formset, "dept_forms": dept_forms, "ask": ask,
        # 켜진 근무조 가운데 어느 부서에도 없는 것(새로 더한 근무조): 부서에서 체크해야 입력 표에 칸이 생긴다(설계 7.2)
        "unassigned": [x.name for x in shift_defs(active) if x.key not in assigned],
        "steps_form": steps, "step_rows": [(steps[f"step_{s}"], s not in on) for s in Period.Status.values],
        "step_line": " → ".join(board.step_name(s) for s in on), "buttons": _buttons(board, bool(slot_defs(active))),
        "open_steps": steps.is_bound or any(m.extra_tags == "steps" for m in messages.get_messages(request)),
    })


@admin_required
def index(request):
    board = _board(request)
    if request.method == "POST":
        if request.POST.get("do") not in ACTIONS:
            raise Http404
        section, act = ACTIONS[request.POST["do"]]
        try:
            out = act(request, board)
        except PermissionDenied:  # 그 근무표 밖의 부서·사람, 대상이 아닌 사람: 없는 것처럼
            raise Http404 from None
        except DutyError as e:
            messages.error(request, str(e), extra_tags=section)
        else:
            if not isinstance(out, str):
                return out
            messages.success(request, out, extra_tags=section)
        return redirect(f"{_here(board)}#{section}")
    return _render(request, board)
```

- [ ] **Step 4: 템플릿을 바꾼다** — `duty/templates/duty/board_settings.html` 전체를 아래로

```django
{% extends "duty/base.html" %}
{% block title %}근무표 설정 · {{ board.name }}{% endblock %}
{% block content %}
<h3>근무표 설정 · {{ board.name }}</h3>
{% if boards|length > 1 %}<p class="seg" role="group" aria-label="고칠 근무표">{% for b in boards %}<a href="{% url 'board_settings' %}?board={{ b.code }}"{% if b.pk == board.pk %} aria-current="page"{% endif %}>{{ b.name }}</a>{% endfor %}</p>{% endif %}
<nav class="jump" aria-label="칸 바로가기"><a href="#admins">관리자</a><a href="#assignees">입력 담당자</a><a href="#shifts">근무 정의와 부서</a><a href="#steps">회차 단계</a></nav>

<section id="admins" class="cfg">
  <h4>관리자 <small>회차·생성·배포·메모·통계·이력과 이 설정을 하는 사람</small></h4>
  {% include "duty/_section_msgs.html" with sec="admins" %}
  <ul class="members">{% for u, how in admin_rows %}
    <li><span>{{ u.name }}{% if not u.is_active %} (퇴사){% endif %} <small>· {{ u.department.name|default:"부서 없음" }}</small></span>
      {% if how == "remove" %}<form method="post" action="{{ here }}#admins" onsubmit="return confirm('{{ u.name|escapejs }}을(를) {{ board.name|escapejs }} 관리자에서 뺄까요?{% if u.pk == user.pk %} 빼면 이 근무표의 회차·설정 화면에 들어올 수 없습니다.{% endif %}')">{% csrf_token %}
        <input type="hidden" name="do" value="remove_admin"><input type="hidden" name="user" value="{{ u.pk }}">
        <button class="outline secondary">빼기</button></form>
      {% elif how == "last" %}<small class="note">마지막 관리자</small>{% else %}<small class="note">빼기는 슈퍼유저에게</small>{% endif %}</li>{% endfor %}</ul>
  <form method="post" action="{{ here }}#admins" class="add labeled">{% csrf_token %}<input type="hidden" name="do" value="add_admin">
    <label>넣을 사람 <select name="user" required><option value="">고르세요</option>{% for u in admin_candidates %}<option value="{{ u.pk }}">{{ u.name }}({{ u.department.name|default:"부서 없음" }})</option>{% endfor %}</select></label>
    <button>넣기</button>
  </form>
</section>

<section id="assignees" class="cfg">
  <h4>입력 담당자 <small>취합 중인 회차에 자기 부서 출근표를 넣는 사람. 관리자는 담당자가 아니어도 모든 부서를 넣습니다</small></h4>
  {% include "duty/_section_msgs.html" with sec="assignees" %}
  {% for it in depts %}<article class="dept">
    <header><strong>{{ it.dept.name }}</strong></header>
    {% if it.members %}<ul class="members">{% for u in it.members %}
      <li><span>{{ u.name }}{% if not u.is_active %} (퇴사){% endif %}</span>
        <form method="post" action="{{ here }}#assignees" onsubmit="return confirm('{{ u.name|escapejs }}을(를) {{ it.dept.name|escapejs }} 입력 담당자에서 뺄까요?')">{% csrf_token %}
          <input type="hidden" name="do" value="remove_assignee"><input type="hidden" name="dept" value="{{ it.dept.pk }}"><input type="hidden" name="user" value="{{ u.pk }}">
          <button class="outline secondary">빼기</button></form></li>{% endfor %}</ul>
    {% else %}<p class="none">담당자 없음 — 근무표 관리자만 입력합니다</p>{% endif %}
    <form method="post" action="{{ here }}#assignees" class="add labeled">{% csrf_token %}<input type="hidden" name="do" value="add_assignee"><input type="hidden" name="dept" value="{{ it.dept.pk }}">
      <label>넣을 사람 <select name="user" required><option value="">고르세요</option>{% for u in it.candidates %}<option value="{{ u.pk }}">{{ u.name }}({{ u.department.name }})</option>{% endfor %}</select></label>
      <button>넣기</button>
    </form>
  </article>{% endfor %}
</section>
<section id="shifts" class="cfg">
  <h4>근무 정의와 부서 <small>근무조·장중관제·점심당번의 이름과 시각, 부서마다 가능한 출근조와 점심 시각</small></h4>
  {% include "duty/_section_msgs.html" with sec="shifts" %}
  <p class="note-box">이름·시각을 운영 중에 바꾸면 발송 창이 열린 알림이 한 번 다시 나가고, 예전에 내려받은 CSV 의 열 이름이 맞지 않습니다.
    저장한 줄은 지우거나 키를 바꿀 수 없으니 '사용'을 끄고 새 줄을 더합니다. 근무조 1~4 는 이름일 뿐이고 이른·늦은 조는 시작 시각으로 정합니다.
    <strong>새 근무조를 더하면 저장한 뒤에야 아래 부서에 그 체크박스가 생기므로, 체크하고 한 번 더 저장합니다.</strong></p>
  <form method="post" action="{{ here }}#shifts" class="shifts">{% csrf_token %}<input type="hidden" name="do" value="shifts">
    {% if ask %}<input type="hidden" name="confirm" value="{{ ask }}">{% endif %}
    {{ formset.management_form }}
    {% for e in formset.non_form_errors %}<p class="err">{{ e }}</p>{% endfor %}
    <div class="cards">{% for f in formset %}<fieldset class="card">
      <legend>{% if f.instance.pk %}{{ f.instance.name }}{% else %}새 근무 정의(더할 때만 채웁니다){% endif %}</legend>
      {% for h in f.hidden_fields %}{{ h }}{% endfor %}
      {% for e in f.non_field_errors %}<p class="err">{{ e }}</p>{% endfor %}
      {% for fld in f.visible_fields %}<div class="fld">
        {% if fld.widget_type == "checkbox" %}<label>{{ fld }} {{ fld.label }}</label>
        {% elif fld.widget_type == "checkboxselectmultiple" %}<span class="lbl">{{ fld.label }}</span>{{ fld }}
        {% else %}<label for="{{ fld.id_for_label }}">{{ fld.label }}</label>{{ fld }}{% endif %}
        {% if fld.help_text %}<small>{{ fld.help_text }}</small>{% endif %}
        {% for e in fld.errors %}<p class="err">{{ e }}</p>{% endfor %}</div>{% endfor %}
    </fieldset>{% endfor %}</div>
    <button class="outline">저장</button>
    <h5>부서</h5>
    {% if unassigned %}<div class="msg warning" role="status">아직 부서에 배정되지 않은 근무조: {{ unassigned|join:", " }}. 아래 부서에서 체크하고 [부서 저장]을 누르세요. 체크하지 않으면 입력 표에 칸이 생기지 않습니다.</div>{% endif %}
    <div class="cards">{% for d in dept_forms %}<fieldset class="card">
      <legend>{{ d.instance.name }}</legend>
      {% for e in d.non_field_errors %}<p class="err">{{ e }}</p>{% endfor %}
      <div class="fld"><span class="lbl">가능한 출근조</span>{{ d.shifts }}{% for e in d.shifts.errors %}<p class="err">{{ e }}</p>{% endfor %}</div>
      <div class="pair">
        <div class="fld"><label for="{{ d.lunch_start.id_for_label }}">점심 시작</label>{{ d.lunch_start }}</div>
        <div class="fld"><label for="{{ d.lunch_end.id_for_label }}">점심 끝</label>{{ d.lunch_end }}</div>
      </div>
      <small>점심 시각은 점심당번 알림·캘린더에 씁니다. 비우면 점심당번이 시각 기준 알림·캘린더에서 빠집니다.</small>
    </fieldset>{% endfor %}</div>
    <button class="wide">{% if ask %}그래도 저장{% elif unassigned %}부서 저장{% else %}저장{% endif %}</button>
  </form>
</section>

<section id="steps" class="cfg">
  <details{% if open_steps %} open{% endif %}><summary><strong>회차 단계 — 근무표를 처음 만들 때 정하는 값</strong></summary>
  {% include "duty/_section_msgs.html" with sec="steps" %}
  <p>저장된 단계: <strong>{{ step_line }}</strong><br>버튼: {% for x in buttons %}<span class="btn-name">[{{ x }}]</span> {% endfor %}</p>
  <form method="post" action="{{ here }}#steps" class="steps" onsubmit="return confirm('진행 중인 회차의 단계 이름과 버튼이 바로 바뀝니다. 계속할까요?')">{% csrf_token %}
    <input type="hidden" name="do" value="steps">
    {% for e in steps_form.non_field_errors %}<p class="err">{{ e }}</p>{% endfor %}
    <label class="check">{{ steps_form.use_draft }} {{ steps_form.use_draft.label }}</label>
    <label class="check">{{ steps_form.use_close }} {{ steps_form.use_close.label }}</label>
    {% for fld, off in step_rows %}<div class="fld"><label for="{{ fld.id_for_label }}">{{ fld.label }}{% if off %} <small>(쓰지 않음 · 남은 회차·기록 표시용)</small>{% endif %}</label>{{ fld }}
      {% for e in fld.errors %}<p class="err">{{ e }}</p>{% endfor %}</div>{% endfor %}
    <button>저장</button>
  </form>
  </details>
</section>
<style>
  nav.jump { display: flex; flex-wrap: wrap; gap: .4rem; margin: 0 0 1.5rem; }
  nav.jump a { display: inline-flex; align-items: center; min-height: 44px; padding: 0 1rem; border: 1px solid var(--duty-line); border-radius: .4rem; text-decoration: none; }
  section.cfg { margin: 0 0 2.5rem; scroll-margin-top: 1rem; }
  section.cfg > h4 { margin-bottom: .8rem; }
  section.cfg > h4 small { display: block; margin-top: .2rem; font-weight: 400; font-size: .85rem; opacity: .75; }
  section.cfg article.dept { max-width: 40rem; }
  ul.members { padding: 0; margin: 0 0 1rem; max-width: 40rem; }
  ul.members li { list-style: none; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem;
    min-height: 44px; padding: .4rem 0; border-bottom: 1px solid var(--duty-line); }
  ul.members form, ul.members button { width: auto; margin: 0; }
  ul.members button { min-height: 44px; padding: .4rem 1rem; }
  ul.members .note { opacity: .75; }
  p.none { margin: 0 0 1rem; font-weight: 700; }
  form.add { display: flex; flex-wrap: wrap; align-items: flex-end; gap: .5rem; max-width: 40rem; }
  form.add label { flex: 1 1 14rem; margin: 0; }
  form.add select { margin: 0; }
  form.add button { width: auto; margin: 0; min-height: 44px; }
  p.note-box { max-width: 60rem; font-size: .95rem; }
  p.err { margin: .2rem 0; color: var(--nxt-red); font-weight: 700; }
  /* 근무 정의·부서는 카드(fieldset)를 늘어놓는다: 넓은 화면은 한 줄에 여럿, 좁은 화면·아주 크게는 하나(설계 7.2) */
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 19rem), 1fr)); gap: 1rem; margin-bottom: 1rem; }
  fieldset.card { margin: 0; padding: .8rem 1rem; border: 1px solid var(--duty-line); border-radius: .4rem; min-width: 0; }
  fieldset.card legend { padding: 0 .3rem; font-weight: 700; }
  fieldset.card .fld { margin-bottom: .6rem; }
  fieldset.card .fld > label:not(:has(input[type=checkbox])), fieldset.card .lbl { display: block; font-size: .85rem; margin-bottom: .2rem; }
  fieldset.card input:not([type=checkbox]), fieldset.card select { margin: 0; }
  fieldset.card small { display: block; opacity: .75; }
  fieldset.card .pair { display: flex; flex-wrap: wrap; gap: .5rem; }
  fieldset.card .pair .fld { flex: 1 1 8rem; }
  form.shifts > button, form.steps button { width: auto; min-height: 48px; padding: .5rem 1.5rem; }
  form.shifts > button.wide { display: block; width: 100%; max-width: 30rem; font-size: 1.05rem; }
  #steps details > summary { min-height: 44px; display: flex; align-items: center; }
  form.steps { max-width: 30rem; }
  form.steps label.check { display: flex; align-items: center; gap: .5rem; min-height: 44px; }
  .btn-name { white-space: nowrap; font-weight: 700; }
</style>
{% endblock %}
```

- [ ] **Step 5: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_views_board_settings.py` → `18 passed`
Run: `.venv/bin/pytest -W error -q` → `1378 passed`

- [ ] **Step 6: 브라우저로 본다**(`admin`)

`/settings/?board=ops`:
- 바로가기 넷. [근무 정의와 부서]: 1400px 에서 카드가 한 줄에 셋 이상(이른·가운데·늦은·점심당번·새 근무 정의), 390px·아주 크게에서 한 줄에 하나, 가로 넘침 없음. 저장한 줄의 "키"는 잠겨 있다. 경고 글이 칸 위에 있다.
- 새 근무 정의 카드: 키 "근무조 4", 이름 "밤", 시작 13:00, 끝 22:00 → 카드 아래 [저장] → `#shifts` 로 돌아와 "✓ 근무 정의와 부서를 저장했습니다." 와 "⚠ 아직 부서에 배정되지 않은 근무조: 밤. …", 부서 아래 큰 [부서 저장]. 운영 덩어리에 "밤 13:00~22:00" 을 체크하고 [부서 저장] → 경고와 [부서 저장]이 사라지고 [저장].
- 운영 덩어리에서 "늦은" 을 끄고 [저장] → (지난 2주가 배포됨이고 이번 2주에 행이 없으면) 바로 저장된다. 이번 2주(입력 중)에 늦은 조 행을 [표 입력]으로 하나 넣은 뒤 다시 하면 "운영 부서에서 '늦은'을 빼면 배포 전 회차(이번 2주)의 그 근무조 출근표 1행이 …" 와 [그래도 저장](보낸 값 그대로). 누르면 저장.
- 점심 시작만 넣고 [저장] → "저장하지 않았습니다. 빨간 글씨로 표시한 칸을 고쳐 주세요." 와 덩어리 안 빨간 글.
- [회차 단계]: 접혀 있다("회차 단계 — 근무표를 처음 만들 때 정하는 값"). 펼치면 "저장된 단계: 입력 중 → 확정 → 배포됨", "버튼: [확정] [확정 취소] [배포…]", 끈 단계 이름 옆 "(쓰지 않음 · 남은 회차·기록 표시용)". [저장] → 확인창 "진행 중인 회차의 단계 이름과 버튼이 바로 바뀝니다. 계속할까요?" → 취소하면 그대로. 생성됨 이름을 "됨" 으로 [저장]·확인 → 펼친 채 "버튼 이름이 비거나 다른 버튼과 같아집니다: []".
- `/settings/`(IT): 카드 15+1, 부서 넷, 버튼 미리보기 "[취합 열기] [취합 마감] [장중관제 생성] [재생성] [배포…]".
- 다크·아주 크게: 카드 테두리·빨간 오류 글·경고 상자가 읽힌다, 버튼 44~48px. 확인 뒤 바꾼 값을 되돌린다(근무조 4 는 '사용' 끄기).

- [ ] **Step 7: 커밋한다**

```bash
git add duty/views/board_settings.py duty/templates/duty/board_settings.html tests/test_views_board_settings.py
git commit -m "feat: 근무표 설정의 근무 정의와 부서 칸(한 번에 저장, 배정 안 된 근무조 경고, 출근표가 지워질 때 확인)과 접힌 회차 단계 칸(버튼 글자 미리보기)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 7: 그룹 정리 — `GroupKeeper`·0024·[그룹] 화면 지우기

> 범위: 설계 5.6·6.1·7.4·10.2. 그룹 관리자 표(`DeleteModel`, 0024), 관리 화면 `GroupKeeperInline`, 메뉴·화면 [그룹](`/groups/`, `views.manage.groups`·`_about`, `groups.html`), `services/groups.py`, `perms.kept_groups`, `tests/test_groups.py` 를 지운다. 관리 화면 "그룹"은 이름·멤버 보기만, 근무표 화면 "관리 그룹" 링크 글은 "관리자·입력 담당자는 앱의 [근무표 설정]에서 넣고 뺍니다."

**Files:**
- Create: `duty/migrations/0024_delete_groupkeeper.py`, `tests/test_migration_groupkeeper.py`
- Delete: `duty/services/groups.py`, `duty/templates/duty/groups.html`, `tests/test_groups.py`
- Modify: `duty/models.py`(`GroupKeeper` 지움), `duty/perms.py`(`kept_groups`·`Group` import 지움), `duty/context.py`(메뉴 [그룹]), `duty/urls.py`(`groups/`), `duty/views/manage.py`(`groups`·`_about`·쓰지 않는 import), `duty/admin.py`(`GroupKeeper` import·`GroupKeeperInline`·`GroupAdmin`·`BoardAdmin` 글)
- Modify(테스트): `tests/test_admin_boards.py`, `tests/test_boards_models.py`, `tests/test_views_board_settings.py`

**Interfaces:**
- Consumes: 없음
- Produces: 마이그레이션 `duty.0024_delete_groupkeeper`(의존 `0023_board_steps`), `/groups/` 404

- [ ] **Step 1: 실패 테스트를 쓴다**

`tests/test_migration_groupkeeper.py`(새 파일):
```python
"""0024: 그룹 관리자(GroupKeeper) 표 지우기(근무표 통합 설계 10.2). 거꾸로는 빈 표. 이름은 모두 가상."""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("duty", "0023_board_steps")]
AFTER = [("duty", "0024_delete_groupkeeper")]


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_apps():
    yield _migrate(BEFORE)
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())  # 다른 테스트를 위해 최신 스키마로


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_groupkeeper_rows_go_and_reverse_gives_empty_table(old_apps):
    group = old_apps.get_model("duty", "Board").objects.get(code="it").admin_group
    user = old_apps.get_model("duty", "User").objects.create(username="keep01", name="가상관리")
    old_apps.get_model("duty", "GroupKeeper").objects.create(group_id=group.pk, user=user)
    apps = _migrate(AFTER)
    with pytest.raises(LookupError):
        apps.get_model("duty", "GroupKeeper")
    assert "duty_groupkeeper" not in connection.introspection.table_names()
    assert apps.get_model("duty", "User").objects.filter(username="keep01").exists()  # 사람·그룹은 그대로
    assert apps.get_model("auth", "Group").objects.filter(pk=group.pk).exists()
    back = _migrate(BEFORE)
    assert not back.get_model("duty", "GroupKeeper").objects.exists()
```

기존 테스트:
```diff
diff --git a/tests/test_admin_boards.py b/tests/test_admin_boards.py
index aeb5a5b..2e92a65 100644
--- a/tests/test_admin_boards.py
+++ b/tests/test_admin_boards.py
@@ -7,7 +7,7 @@ from django.core.exceptions import ValidationError
 from django.urls import reverse
 
 from duty.admin import STEP_FIELDS, BoardForm, DepartmentForm
-from duty.models import Board, BoardShift, Department, GroupKeeper, Period, User
+from duty.models import Board, BoardShift, Department, Period, User
 from tests.it_defs import OPS_STEPS
 
 ADD = reverse("admin:duty_board_add")
@@ -292,19 +292,15 @@ def test_change_warns_about_periods_in_turned_off_step(su_client, ops):
     assert "&#x27;작성 중&#x27; 단계에 회차 1개가 남아 있습니다. 회차 화면에서 다른 단계로 옮기세요." in r.content.decode()
 
 
-# ── 그룹 관리자 ──
+# ── 그룹: 이름·멤버 보기만(그룹 관리자 없음, 근무표 통합 3단계) ──
 
-def test_group_page_hides_permissions_and_edits_keepers(su_client, it_board, admin_user, make_member):
+def test_group_page_is_name_only(su_client, it_board, admin_user):
     group = it_board.admin_group
     html = su_client.get(reverse("admin:auth_group_change", args=[group.pk])).content.decode()
     assert 'name="name"' in html and 'name="permissions"' not in html and 'name="members"' not in html
-    keeper = make_member("가상관리", user=True)
-    r = su_client.post(reverse("admin:auth_group_change", args=[group.pk]), {
-        "name": group.name, "keepers-TOTAL_FORMS": "1", "keepers-INITIAL_FORMS": "0",
-        "keepers-0-group": group.pk, "keepers-0-user": keeper.pk,
-    })
-    assert r.status_code == 302, errors(r)
-    assert list(GroupKeeper.objects.values_list("group", "user")) == [(group.pk, keeper.pk)]
+    assert "keepers-TOTAL_FORMS" not in html and "그룹 관리자" not in html
+    html = su_client.get(reverse("admin:duty_board_change", args=[it_board.pk])).content.decode()
+    assert "관리자·입력 담당자는 앱의 [근무표 설정]에서 넣고 뺍니다." in html
 
 
 # ── 새 부서: 근무표의 근무조만 ──
diff --git a/tests/test_boards_models.py b/tests/test_boards_models.py
index 90a8955..4d20c4e 100644
--- a/tests/test_boards_models.py
+++ b/tests/test_boards_models.py
@@ -6,7 +6,7 @@ from django.contrib.auth.models import Group
 from django.db import IntegrityError, transaction
 
 from duty.errors import DutyError
-from duty.models import Board, BoardShift, Department, GroupKeeper
+from duty.models import Board, BoardShift, Department
 from duty.shifts import KEYS
 from tests.it_defs import IT_DEFS2, OPS_STEPS
 
@@ -93,11 +93,6 @@ def test_boardshift_name_unique_per_board(it_board):
     _bad(lambda: BoardShift.objects.create(board=ops, key="normal", name="새벽", start=time(9), end=time(18)))
 
 
-def test_groupkeeper_unique(admin_user, it_board):
-    GroupKeeper.objects.create(group=it_board.admin_group, user=admin_user)
-    _bad(lambda: GroupKeeper.objects.create(group=it_board.admin_group, user=admin_user))
-
-
 def test_boardshift_key_labels_are_neutral():
     labels = dict(BoardShift._meta.get_field("key").choices)
     assert labels["dawn"] == "근무조 1" and labels["night"] == "근무조 4"
diff --git a/tests/test_views_board_settings.py b/tests/test_views_board_settings.py
index 20f35a1..05e094a 100644
--- a/tests/test_views_board_settings.py
+++ b/tests/test_views_board_settings.py
@@ -238,3 +238,10 @@ def test_bad_step_names_redraw(ops_client, ops_board):
     body = r.content.decode()
     assert r.status_code == 200 and "<details open>" in body and "버튼 이름이 비거나 다른 버튼과 같아집니다: []" in body
     assert "저장된 단계: <strong>입력 중 → 확정 → 배포됨</strong>" in body  # 미리보기는 저장된 값
+
+
+def test_groups_menu_and_page_are_gone(admin_client_ok):
+    """[그룹] 화면은 [근무표 설정]으로 바뀌었다(근무표 통합 3단계)."""
+    assert admin_client_ok.get("/groups/").status_code == 404
+    body = admin_client_ok.get("/").content.decode()
+    assert ">그룹</a>" not in body and 'href="/settings/"' in body
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_migration_groupkeeper.py tests/test_admin_boards.py tests/test_views_board_settings.py tests/test_boards_models.py`
Expected: FAIL — `test_group_page_is_name_only`(`keepers-TOTAL_FORMS` 가 있다), `test_groups_menu_and_page_are_gone`(`/groups/` 403), `test_groupkeeper_rows_go_and_reverse_gives_empty_table`(0024 노드 없음)

- [ ] **Step 3: 지운다**

```bash
git rm duty/services/groups.py duty/templates/duty/groups.html tests/test_groups.py
```

- [ ] **Step 4: 코드를 고친다**

```diff
diff --git a/duty/admin.py b/duty/admin.py
index 76f6079..172a19b 100644
--- a/duty/admin.py
+++ b/duty/admin.py
@@ -14,7 +14,7 @@ from py_vapid import _check_sub
 
 from .accounts import issue_account, on_department_change
 from .forms import SHIFT_KEY_CHOICES, STEP_FIELDS, BoardShiftForm, BoardShiftFormSet, StepsForm
-from .models import AlarmSettings, Board, BoardShift, Department, GroupKeeper, Holiday, User
+from .models import AlarmSettings, Board, BoardShift, Department, Holiday, User
 from .services import alarm_settings, board_settings, boards
 from .shifts import SHIFT_KEYS, shift_defs
 
@@ -248,7 +248,7 @@ class BoardForm(StepsForm):
 @admin.register(Board)
 class BoardAdmin(admin.ModelAdmin):
     """근무표(설계 4.2·4.3). code(boards.it_board() 가 IT 근무표를 찾는 열쇠)는 만든 뒤 바꾸지 않는다. 단계 칸은 언제든 고친다(근무표 통합 3단계).
-    지우기는 막는다. 관리 그룹은 Board.save 가 만들고, 그 그룹의 그룹 관리자는 '관리 그룹' 링크(그룹 화면)에서 정한다."""
+    지우기는 막는다. 관리 그룹은 Board.save 가 만들고, 관리자·입력 담당자는 앱의 [근무표 설정]에서 넣고 뺀다."""
     form = BoardForm
     list_display = ["name", "code", "step_line", "admin_group"]
     inlines = [BoardShiftInline]
@@ -279,19 +279,13 @@ class BoardAdmin(admin.ModelAdmin):
 
     @admin.display(description="관리 그룹")
     def group_link(self, obj):
-        return format_html('<a href="{}">{}</a> — 그룹 관리자는 이 링크에서, 멤버는 사용자 화면의 그룹 칸이나 [그룹] 화면에서 정합니다.',
+        return format_html('<a href="{}">{}</a> — 관리자·입력 담당자는 앱의 [근무표 설정]에서 넣고 뺍니다.',
                            reverse("admin:auth_group_change", args=[obj.admin_group_id]), obj.admin_group.name)
 
     def has_delete_permission(self, request, obj=None):
         return False
 
 
-class GroupKeeperInline(admin.TabularInline):
-    """그룹 관리자(설계 4.5): 이 그룹에 멤버를 넣고 빼는 사람. 슈퍼유저가 여기서 정하고, 그 뒤 멤버는 그 사람이 [그룹] 화면에서."""
-    model = GroupKeeper
-    extra = 0
-
-
 @admin.register(Holiday)
 class HolidayAdmin(admin.ModelAdmin):
     """휴장일(설계 5절): 임시공휴일 추가(직접 추가), 휴장일이 아닌 날은 '휴장'을 끈다. 자동 행은 작업자가 채운다.
@@ -316,11 +310,11 @@ admin.site.unregister(Group)  # django.contrib.auth.admin 이 등록한 기본 
 
 @admin.register(Group)
 class GroupAdmin(admin.ModelAdmin):
-    """permissions 칸만 숨긴다(Django 권한을 쓰지 않는다). 멤버는 사용자 화면의 '그룹' 칸이나, 그룹 관리자가 [그룹] 화면에서 넣는다."""
+    """이름·멤버 보기만(permissions 칸은 숨긴다: Django 권한을 쓰지 않는다). 멤버는 사용자 화면의 '그룹' 칸이나 앱의 [근무표 설정]에서
+    고친다(관리자·입력 담당자). 근무표 관리 그룹·부서 입력 그룹의 이름은 근무표·부서 이름을 따라가므로 여기서 바꾸지 않는다."""
     fields = ["name"]
     list_display = ["name", "member_names"]
     search_fields = ["name"]
-    inlines = [GroupKeeperInline]
 
     def get_queryset(self, request):
         return super().get_queryset(request).prefetch_related("user_set")
diff --git a/duty/context.py b/duty/context.py
index dc78eb3..f92f288 100644
--- a/duty/context.py
+++ b/duty/context.py
@@ -21,8 +21,6 @@ def nav(request):
             items.append(("통계", "/stats/", ()))
         items.append(("이력", "/changes/", ()))
         items.append(("근무표 설정", "/settings/", ()))  # 관리자·입력 담당자·근무 정의와 부서·단계(근무표 통합 설계 7절)
-    if perms.kept_groups(user).exists():  # 그룹 관리자(GroupKeeper)만(설계 7절)
-        items.append(("그룹", "/groups/", ()))
     if user.is_superuser:
         items.append(("관리", reverse("admin:index"), ()))
     items.append(("도움말", "/help/", ()))
diff --git a/duty/models.py b/duty/models.py
index 846faa4..1c39284 100644
--- a/duty/models.py
+++ b/duty/models.py
@@ -184,17 +184,6 @@ class BoardShift(models.Model):
         raise ValidationError("저장한 근무 정의는 지울 수 없습니다. '사용'을 끄세요.")
 
 
-class GroupKeeper(models.Model):
-    """그룹 관리자: 그 그룹에 멤버를 넣고 빼기만 한다."""
-    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="keepers", verbose_name="그룹")
-    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="kept_groups",
-                             verbose_name="그룹 관리자")
-
-    class Meta:
-        verbose_name = verbose_name_plural = "그룹 관리자"
-        constraints = [models.UniqueConstraint(fields=["group", "user"], name="groupkeeper_once")]
-
-
 class Department(models.Model):
     code = models.CharField("코드", max_length=8, primary_key=True)
     name = models.CharField("이름", max_length=32, unique=True)
diff --git a/duty/perms.py b/duty/perms.py
index 7232ec4..f87b731 100644
--- a/duty/perms.py
+++ b/duty/perms.py
@@ -6,7 +6,6 @@
 
 from datetime import date
 
-from django.contrib.auth.models import Group
 from django.core.exceptions import PermissionDenied
 from django.db.models import Q
 from django.utils import timezone
@@ -39,13 +38,6 @@ def stats_boards(user):
     return admin_boards(user).filter(shifts__key__startswith="slot").distinct()
 
 
-def kept_groups(user):
-    """내가 그룹 관리자(GroupKeeper)인 그룹들: [그룹] 화면에서 멤버를 넣고 뺀다(설계 7절)."""
-    if not user.is_authenticated:
-        return Group.objects.none()
-    return Group.objects.filter(keepers__user=user)
-
-
 def managed_departments(user):
     """출근표를 입력할 수 있는 부서: 입력 그룹 멤버인 부서 ∪ 내가 관리하는 근무표의 모든 부서."""
     if not user.is_authenticated:
diff --git a/duty/urls.py b/duty/urls.py
index c6aa4d5..471c919 100644
--- a/duty/urls.py
+++ b/duty/urls.py
@@ -49,7 +49,6 @@ urlpatterns = [
     path("periods/<int:pid>/publish/", manage_views.period_publish, name="period_publish"),
     path("stats/", manage_views.stats_view, name="stats"),
     path("changes/", manage_views.change_log, name="changes"),
-    path("groups/", manage_views.groups, name="groups"),
     path("settings/", board_settings_views.index, name="board_settings"),
     path("alarms/", alarm_views.index, name="alarms"),
     path("alarms/telegram/", alarm_views.telegram_save, name="alarm_telegram"),
diff --git a/duty/views/manage.py b/duty/views/manage.py
index 86e7605..0378a36 100644
--- a/duty/views/manage.py
+++ b/duty/views/manage.py
@@ -1,7 +1,6 @@
 from datetime import date
 
 from django.contrib import messages
-from django.contrib.auth.decorators import login_required
 from django.core.exceptions import PermissionDenied
 from django.db.models import Q
 from django.http import Http404
@@ -12,9 +11,8 @@ from .. import perms
 from ..csv_io import join_reason
 from ..errors import DutyError
 from ..generator import GenerationError
-from ..models import Board, ChangeLog, Department, DutyAssignment, Period, User
+from ..models import Board, ChangeLog, Department, DutyAssignment, Period
 from ..services import boards, collect, generate, periods, stats
-from ..services import groups as group_service
 from ..services import publish as publishing
 from ..shifts import LUNCH, by_key, cell_label, day_spans, gen_help, is_slot_cell, josa, slot_defs
 from .common import admin_required, date_param
@@ -266,47 +264,3 @@ def change_log(request):
     ]
     return render(request, "duty/changes.html", {"logs": logs, "name": name, "by": by, "start": start, "end": end,
                                                  "board_choices": mine if len(mine) > 1 else [], "board_code": board_code})
-
-
-def _about(group) -> str:
-    """그룹이 무슨 권한인지 한 줄(나이 든 관리자가 그룹 이름만 보고 헷갈리지 않게)."""
-    board = getattr(group, "admin_board", None)
-    if board:
-        return f"{board.name} 근무표 관리자(회차·배포·메모·지난 날짜 수정)"
-    dept = getattr(group, "input_department", None)
-    return f"{dept.name} 출근표 입력 담당" if dept else ""
-
-
-@login_required
-def groups(request):
-    """그룹 화면(설계 7절): 내가 그룹 관리자인 그룹의 멤버를 보고 넣고 뺀다. 그룹 관리자가 아니면 403."""
-    kept = list(perms.kept_groups(request.user).order_by("name").prefetch_related("user_set__department"))
-    if not kept:
-        raise PermissionDenied
-    if request.method == "POST":
-        group = next((g for g in kept if str(g.pk) == request.POST.get("group")), None)
-        pid = request.POST.get("member", "")
-        member = User.objects.filter(pk=pid).first() if pid.isdigit() else None
-        do = request.POST.get("do")
-        if group is None or member is None or do not in ("add", "remove"):  # 맡지 않은 그룹·없는 사람·모르는 동작
-            raise Http404
-        try:
-            if do == "remove":
-                warning = group_service.remove_member(request.user, group, member)
-                messages.success(request, f"{member.name}을(를) {group.name}에서 뺐습니다.")
-                if warning:
-                    messages.warning(request, warning)
-            else:
-                group_service.add_member(request.user, group, member)
-                messages.success(request, f"{member.name}을(를) {group.name}에 넣었습니다.")
-        except DutyError as e:
-            messages.error(request, str(e))
-        return redirect("groups")
-    active = list(User.objects.filter(is_active=True).select_related("department").order_by("name"))
-    items = []
-    for g in kept:
-        members = sorted(g.user_set.all(), key=lambda u: u.name)
-        ids = {u.pk for u in members}
-        items.append({"group": g, "about": _about(g), "members": members,
-                      "candidates": [u for u in active if u.pk not in ids]})  # 후보 = 재직 계정(퇴사자는 넣지 않는다)
-    return render(request, "duty/groups.html", {"items": items})
```

- [ ] **Step 5: 마이그레이션을 만든다**

`DUTY_DEBUG=1 DUTY_ENV_FILE= DUTY_DATA_DIR=$(mktemp -d) .venv/bin/python manage.py makemigrations duty -n delete_groupkeeper` 로 만든 뒤 위에 docstring 을 단다(결과 파일):

```python
"""그룹 관리자(GroupKeeper) 표를 지운다(근무표 통합 설계 5.6·10.2, 3단계). 멤버 넣고 빼기는 [근무표 설정]의 관리자·입력 담당자 칸이 한다.

- 행은 권한 지정일 뿐 기록(변경·상태)이 걸려 있지 않다. 업그레이드 전에 OPERATIONS 확인 ②대로 전부 CSV 로 내보내 둔다(참고용).
- 거꾸로는 빈 표가 돌아온다(거부하지 않는다: 늘 거부하면 0024 아래로 내려가는 마이그레이션 테스트가 모두 깨진다).
  행까지 되돌리는 롤백은 업그레이드 전 백업 복원만 지원한다.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('duty', '0023_board_steps'),
    ]

    operations = [
        migrations.DeleteModel(
            name='GroupKeeper',
        ),
    ]
```

- [ ] **Step 6: 통과를 확인한다**

Run: `git grep -n -E "GroupKeeper|kept_groups|group_service|/groups/|groups\.html" -- duty tests tools ':!duty/migrations'` → 아무것도 안 나온다.
Run: `.venv/bin/pytest -W error -q` → `1370 passed`(지운 `test_groups.py` 9개·`test_groupkeeper_unique`, 더한 마이그레이션 테스트·메뉴 테스트)
Run: `makemigrations duty --check --dry-run` → "No changes detected in app 'duty'"
Run(마이그레이션 왕복, 새 임시 DB):
```bash
W=$(mktemp -d); export DUTY_DEBUG=1 DUTY_ENV_FILE= DUTY_DATA_DIR=$W
.venv/bin/python manage.py migrate -v0 && .venv/bin/python manage.py migrate duty 0022 -v0 && .venv/bin/python manage.py migrate -v0
.venv/bin/python manage.py migrate duty 0023 -v0 && .venv/bin/python manage.py migrate -v0
.venv/bin/python manage.py showmigrations duty | tail -2     # [X] 0023_board_steps, [X] 0024_delete_groupkeeper
rm -rf $W; unset DUTY_DEBUG DUTY_ENV_FILE DUTY_DATA_DIR
```

- [ ] **Step 7: 브라우저로 본다**

`admin` 메뉴에 [그룹]이 없고 [근무표 설정]이 있다(1400px·390px 메뉴 줄 감김). `/groups/` 는 404. 관리 화면 → 그룹 → IT 근무표 관리: 이름 칸만, "그룹 관리자" 줄 없음. 관리 화면 → 근무표 → IT 당번표: 관리 그룹 링크 옆 "관리자·입력 담당자는 앱의 [근무표 설정]에서 넣고 뺍니다."

- [ ] **Step 8: 커밋한다**

```bash
git add -A duty tests
git commit -m "feat: 그룹 관리자와 [그룹] 화면을 지운다(마이그레이션 0024, 멤버 넣고 빼기는 근무표 설정에서)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 8: 글 도움말 "근무표 설정"·스냅샷·문서

> 범위: 설계 13(3단계 몫)과 10.3·10.4 의 3단계. `help.py` 에 글 도움말 하나("근무표 설정", 근무표 관리자), 스냅샷 `help-admin` 다시 쓰기, ARCHITECTURE(코드 지도·데이터·Board·근무표와 칸·역할·[근무표 설정]·회차·도움말·보안)·OPERATIONS(처음 한 번·근무표 추가하기·운영 중에 바꾸면·업그레이드 "근무표 통합 3단계로 올릴 때": 확인 ①②·롤백·기록 보는 곳·공지)·OVERVIEW(역할)·DEVELOPMENT(가짜 데이터)·PRINCIPLES(결정 기록 세 줄).

**Files:**
- Modify: `duty/help.py`(`TEXTS`·`STEPS["settings"]`·`allowed`·`texts_for`), `tests/test_help.py`(맨 끝), `tests/snapshots/help-admin.html`(다시 쓰기로)
- Modify: `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`, `docs/OVERVIEW.md`, `docs/DEVELOPMENT.md`, `docs/PRINCIPLES.md`

**Interfaces:**
- Consumes: Task 1~7 결과
- Produces: `help.TEXTS` 에 `("settings", "근무표 설정(관리자·입력 담당자·근무 정의·단계)", "근무표 관리자")`, `help.STEPS["settings"]`

- [ ] **Step 1: 실패 테스트를 쓴다**

```diff
diff --git a/tests/test_help.py b/tests/test_help.py
index 0208e5f..5127eb1 100644
--- a/tests/test_help.py
+++ b/tests/test_help.py
@@ -215,3 +215,17 @@ def test_manager_text_explains_fill(client, people, videos):
     client.force_login(people["manager"])
     body = client.get("/help/").content.decode()
     assert "[지난주와 같게]" in body and "[2주 전 기준으로 채우기]" in body and "<h4>글 도움말</h4>" not in body
+
+
+def test_settings_text_help_for_board_admins(client, people, videos):
+    """[근무표 설정] 글 도움말(근무표 통합 3단계): 관리자에게만, 단계 줄 없이."""
+    client.force_login(people["manager"])
+    assert "근무표 설정(관리자·입력 담당자·근무 정의·단계)" not in client.get("/help/").content.decode()
+    client.force_login(people["admin"])
+    body = client.get("/help/").content.decode()
+    i = body.index("근무표 설정(관리자·입력 담당자·근무 정의·단계)")
+    assert body.index("회차 운영(단계·출근표·생성·배포)") < i
+    part = body[i:]
+    for word in ("[근무표 설정]", "나 자신과 퇴사한 관리자", "[부서 저장]", "[그래도 저장]", "회차 단계", "슈퍼유저"):
+        assert word in part, word
+    assert "IT 당번표: 작성 중" not in part  # 단계 줄은 '회차 운영' 글에만
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_help.py`
Expected: FAIL — `test_settings_text_help_for_board_admins`(`ValueError: substring not found`)

- [ ] **Step 3: 구현한다** — `duty/help.py`

```diff
diff --git a/duty/help.py b/duty/help.py
index 2b59d52..b627ff3 100644
--- a/duty/help.py
+++ b/duty/help.py
@@ -9,6 +9,7 @@ VIDEOS = [  # (이름, 제목, 누구를 위한)
 
 TEXTS = [  # 영상 없이 글로만 보는 사용법 (이름, 제목, 누구를 위한)
     ("period", "회차 운영(단계·출근표·생성·배포)", "근무표 관리자"),
+    ("settings", "근무표 설정(관리자·입력 담당자·근무 정의·단계)", "근무표 관리자"),
 ]
 
 # 영상과 같은 내용의 글(화면 읽기 프로그램·소리 없이 보는 사람용). 영상 자막을 바꾸면 같이 고친다
@@ -61,6 +62,16 @@ STEPS = {
         "배포한 뒤에는 근무표 화면에서 칸을 눌러 바꿉니다. 잘못 배포했으면 회차 화면의 [배포 취소]로 되돌립니다(가장 최근 배포만).",
         "버튼 이름은 단계 이름에서 나옵니다(예: '취합 중' → [취합 열기]·[취합 마감], 장중관제가 없는 근무표의 '확정' → [확정]·[확정 취소]).",
     ],
+    "settings": [  # 근무표 통합 3단계: [근무표 설정] 화면
+        "메뉴 [근무표 설정]에서 내가 관리하는 근무표의 관리자·입력 담당자·근무 정의와 부서·회차 단계를 고칩니다. 관리하는 근무표가 둘 이상이면 제목 아래 근무표 이름을 눌러 고칠 근무표를 바꿉니다. 맨 위 바로가기를 누르면 그 칸으로 가고, 저장하면 같은 칸으로 돌아와 결과가 그 칸 제목 아래에 보입니다.",
+        "관리자: [넣기]로 그 근무표 사람이나 부서 없는 계정을 관리자로 넣습니다. 빼기는 나 자신과 퇴사한 관리자만 할 수 있고, 재직 중인 다른 관리자를 빼는 일은 슈퍼유저에게 부탁합니다. 재직 중인 관리자가 하나도 남지 않게는 뺄 수 없습니다.",
+        "입력 담당자: 부서마다 출근표를 넣을 사람을 넣고 뺍니다. 담당자가 없는 부서는 근무표 관리자만 입력합니다.",
+        "근무 정의와 부서: 근무조·장중관제·점심당번의 이름과 시각, 부서마다 가능한 출근조와 점심 시각을 고치고 [저장]을 누릅니다. 저장한 줄은 지울 수 없으니 쓰지 않으면 '사용'을 끕니다.",
+        "근무조를 새로 더하면 저장한 뒤에야 부서에 그 체크박스가 생깁니다. 아래 부서에서 체크하고 [부서 저장]을 한 번 더 누릅니다(체크하지 않으면 입력 표에 칸이 생기지 않습니다).",
+        "부서에서 근무조를 빼는데 아직 배포하지 않은 회차에 그 근무조 출근표가 있으면 몇 행이 지워지는지 알려 주고 저장하지 않습니다. 확인했으면 [그래도 저장]을 누릅니다.",
+        "회차 단계(맨 아래, 접혀 있음): 작성 중·마감 단계를 쓸지와 단계 이름을 정합니다. 버튼 이름은 단계 이름에서 나오고 '버튼:' 줄에 미리 보입니다. 진행 중인 회차에도 바로 바뀌니 보통은 근무표를 처음 만들 때만 고칩니다. 끈 단계에 회차가 남으면 회차 화면에서 다른 단계로 옮깁니다.",
+        "사람 추가·계정 발급과 비밀번호 초기화, 관리자 계정, 인사이동(부서 옮기기), 근무표 만들기는 슈퍼유저에게 부탁합니다.",
+    ],
 }
 
 
@@ -69,7 +80,7 @@ def allowed(user, name: str) -> bool:
         return True  # 가짜 데이터로 찍은 기본 사용법이라 로그인 전(로그인 화면의 도움말)에도 보여 준다
     if name == "manager":
         return perms.is_admin(user) or perms.managed_departments(user).exists()
-    return name in ("admin", "period") and perms.is_admin(user)
+    return name in ("admin", "period", "settings") and perms.is_admin(user)
 
 
 def for_user(user) -> list[dict]:
@@ -82,5 +93,5 @@ def _board_steps(user) -> list[str]:
 
 
 def texts_for(user) -> list[dict]:
-    return [{"name": n, "title": t, "who": w, "steps": _board_steps(user) + STEPS[n]}
+    return [{"name": n, "title": t, "who": w, "steps": (_board_steps(user) if n == "period" else []) + STEPS[n]}
             for n, t, w in TEXTS if allowed(user, n)]
```

- [ ] **Step 4: 스냅샷을 다시 쓰고 확인한다**

Run: `DUTY_SNAPSHOT_WRITE=1 .venv/bin/pytest -W error -q tests/test_snapshots.py` → 일부러 1 failed("스냅샷을 다시 썼습니다…")
Run: `git diff --stat tests/snapshots/` → `tests/snapshots/help-admin.html | 16 ++++++++++++++++` 하나뿐(근무표 설정 글 도움말 `<article>` 한 덩어리가 "회차 운영" 글 뒤, "설정 도움말" 앞에). 다른 파일이 바뀌었으면 멈추고 까닭을 찾는다.
Run: `.venv/bin/pytest -W error -q tests/test_help.py tests/test_snapshots.py` → PASS

- [ ] **Step 5: 문서를 고친다**(저장소 루트에서. 찾을 글이 정확히 한 번씩 나와야 하고, 아니면 멈춘다)

```bash
python3 - <<'PYEOF'
import sys
def edit(p, old, new):
    s=open(p).read(); n=s.count(old)
    if n!=1: sys.exit(f"{p}: {n}x {old[:80]!r}")
    open(p,'w').write(s.replace(old,new))
A='docs/ARCHITECTURE.md'
edit(A,"| `duty/services/` | **DB를 바꾸는 규칙은 전부 여기**. 뷰·관리 명령은 서비스만 부른다. 근무표·근무 정의 읽기와 그날의 주인은 `boards.py` | O |",
"| `duty/services/` | **DB를 바꾸는 규칙은 전부 여기**. 뷰·관리 명령은 서비스만 부른다. 근무표·근무 정의 읽기와 그날의 주인은 `boards.py`, [근무표 설정]의 쓰기는 `board_settings.py` | O |\n| `duty/forms.py` | 관리 화면과 [근무표 설정]이 함께 쓰는 폼(근무 정의 한 줄·근무표 전체 검사, 회차 단계 칸, 부서 출근조·점심 시각) | |")
edit(A,"| `duty/admin.py` | Django 관리 화면(사용자·부서(점심 시각)·근무표와 근무 정의(편집·설계 4.3 검증)·그룹(그룹 관리자)·휴장일·계정 발급·알림 설정) | |",
"| `duty/admin.py` | Django 관리 화면(사용자(재직 관리자 한 명 이상)·부서(점심 시각)·근무표와 근무 정의(편집·설계 4.3 검증)·그룹(이름·멤버 보기)·휴장일·계정 발급·알림 설정) | |")
edit(A,"auth.Group: Board.admin_group(근무표 관리), Department.input_group(출근표 입력) ─< GroupKeeper(그룹 관리자)",
"auth.Group: Board.admin_group(근무표 관리), Department.input_group(출근표 입력, 첫 담당자를 넣을 때 생긴다)")
edit(A,"근무표를 만들면 관리 그룹 \"<이름> 근무표 관리\"가, 마감 단계를 쓰는 근무표에 부서를 만들면 입력 그룹 \"<부서> 출근표 입력\"이 저절로 생긴다(1단계 임시 기준 `boards.legacy_admin_entry`, 근무표 통합 3단계에서 첫 입력 담당자를 넣을 때 만들기로 바뀐다).",
"근무표를 만들면 관리 그룹 \"<이름> 근무표 관리\"가 저절로 생긴다. 부서의 입력 그룹 \"<부서> 출근표 입력\"은 **첫 입력 담당자를 넣을 때** 생긴다(`Department.ensure_input_group`: [근무표 설정]의 `board_settings.add_assignee` 와 관리 화면 부서 폼. 같은 이름의 그룹이 이미 있으면 \"같은 이름의 그룹이 이미 있습니다: …. 슈퍼유저에게 그 그룹 이름을 바꿔 달라고 하세요.\"로 막는다). 입력 그룹이 없는 부서와 빈 그룹인 부서는 똑같이 \"근무표 관리자만 입력\"이다(`perms.managed_departments`).")
edit(A,"- 근무표와 근무 정의는 슈퍼유저가 관리 화면 \"근무표\"에서 추가·편집한다(운영자 절차는 OPERATIONS.md \"근무표 추가하기\". `admin.BoardShiftForm`·`BoardShiftFormSet`):",
"- 근무표는 슈퍼유저가 관리 화면 \"근무표\"에서 만든다(운영자 절차는 OPERATIONS.md \"근무표 추가하기\"). 근무 정의·부서 출근조·점심 시각·회차 단계는 관리 화면과 그 근무표 관리자의 [근무표 설정]이 같은 검사로 고친다(`forms.BoardShiftForm`·`BoardShiftFormSet`·`StepsForm`·`DeptShiftsForm`):")
edit(A,"회차 단계 칸은 만들 때 정하고 저장된 근무표에서는 읽기 전용이다(1·2단계: 입력 그룹 기준 `legacy_admin_entry` 와 섞인 상태를 막는다. 3단계에서 기준 함수를 지우며 연다). 단계 이름은 비울 수 없고 줄바꿈 금지·서로 다름, 켠 단계에서 나오는 버튼 글자가 비거나 서로 겹치는 이름도 막는다(`BoardForm`·`Board.bad_buttons`·제약 `board_step_names_set`). 부서 수 제한은 없다. 마감을 안 쓰는 근무표의 부서는 입력 담당자를 고를 수 없다(관리자가 입력, `DepartmentForm`, 1단계 임시 기준).",
"회차 단계 칸은 저장된 근무표에서도 고친다(진행 중인 회차의 단계 이름·버튼이 바로 바뀌고, 끈 단계에 회차가 남으면 저장 뒤 \"'마감' 단계에 회차 1개가 남아 있습니다. 회차 화면에서 다른 단계로 옮기세요.\", `board_settings.stranded`). 단계 이름은 비울 수 없고 줄바꿈 금지·서로 다름, 켠 단계에서 나오는 버튼 글자가 비거나 서로 겹치는 이름도 막는다(`forms.StepsForm`, 관리 화면 `BoardForm` 은 그것을 물려받는다, `Board.bad_buttons`·제약 `board_step_names_set`). 부서 수 제한은 없다. 어느 근무표의 부서든 입력 담당자를 고를 수 있다(처음 고를 때 입력 그룹이 생긴다).")
edit(A,"| 근무표 관리자(근무표 관리 그룹 멤버, IT = \"IT 근무표 관리\") | 그 근무표의 회차 관리·생성·배포, 메모(근무 없음 포함), 통계, 변경 이력, 지난 날짜 수정, 그 근무표 전 부서 출근표.",
"| 근무표 관리자(근무표 관리 그룹 멤버, IT = \"IT 근무표 관리\") | 그 근무표의 회차 관리·생성·배포, 메모(근무 없음 포함), 통계, 변경 이력, 지난 날짜 수정, 그 근무표 전 부서 출근표, [근무표 설정](관리자 넣기·나 자신과 퇴사자 빼기, 입력 담당자, 근무 정의와 부서, 회차 단계).")
edit(A,"| 그룹 관리자(`GroupKeeper`) | 맡은 그룹에 멤버를 넣고 뺀다(메뉴 [그룹], `/groups/`, `services/groups.py`, POST 는 `do=add`·`remove` 만 받고 다른 값은 404). 후보는 재직 계정, 퇴사자는 \"(퇴사)\"로 보여 뺄 수 있다. 근무표 관리 그룹이 비면 경고만 한다. 넣고 빼기는 로그(아이디)로 남는다 |\n","")
edit(A,"| 슈퍼유저 | Django 관리 화면: 사용자(\"그룹\" 칸으로 근무표 관리자 지정)·부서(점심 시각 포함)·휴장일·근무표와 근무 정의(추가·편집)·그룹(이름, 그룹 관리자 지정)·계정 발급·로그인 잠금 해제·알림 설정.",
"| 슈퍼유저 | Django 관리 화면: 사용자(\"그룹\" 칸으로 근무표 관리자 지정, 재직 중인 다른 관리자 빼기)·부서(점심 시각 포함)·휴장일·근무표와 근무 정의(추가·편집)·그룹(이름·멤버 보기)·계정 발급·로그인 잠금 해제·알림 설정.")
edit(A,"- 그룹 관리자는 `Group`에 걸린 표라서(근무표로 가는 FK가 없다) 관리 화면 \"그룹\"의 인라인에서 정한다. 근무표 화면에는 관리 그룹 링크가 있다.\n",
"""- **[근무표 설정]**(`/settings/?board=<code>`, `views/board_settings.py`, 쓰기는 `services/board_settings.py`): 메뉴는 어느 근무표든 관리자에게 보이고, 그 근무표 관리자가 아니면 404(슈퍼유저라도 관리 그룹 밖이면 못 들어온다). 칸 바로가기(#admins·#assignees·#shifts·#steps), 칸마다 따로 저장하고 그 칸 앵커로 돌아오며 결과 메시지는 `messages` 의 `extra_tags`(칸 id)로 그 칸 제목 아래에 그린다(`base.html` 맨 위에는 칸 태그가 없는 메시지만). 서비스 함수마다 첫 줄 `_require_admin`, 받은 부서·사람·근무 정의가 그 근무표 것인지 다시 본다(범위 밖이면 `PermissionDenied`, 뷰는 404. 근무 정의 formset 은 `instance=board`, 부서 폼은 그 근무표 부서만 만들고 다른 id·부서 칸이 섞인 POST 는 404). 관리자 넣기 후보 = 재직 중인 그 근무표 사람 + 부서 없는 계정. 관리자 빼기는 **나 자신이나 퇴사한 관리자만**(재직 중인 다른 관리자 빼기는 슈퍼유저 — 빼고 나서 그 계정을 다루는 우회를 막는다). **재직 관리자는 근무표마다 한 명 이상**(`boards.left_without_admin`): 앱의 빼기와 관리 화면 사용자 편집(관리 그룹을 빼거나 재직을 끔, 칸 오류)·지우기(`UserAdmin.get_deleted_objects` 가 보호 목록에 까닭을 넣어 한 명 지우기·일괄 지우기 모두 막는다)가 같은 검사를 쓴다. 근무 정의와 부서는 [저장] 하나로 한 트랜잭션(`save_shifts`): "부서마다 켜진 입력 근무조 하나 이상"은 이번에 저장할 부서 출근조로 보고, 부서에서 켜진 근무조를 빼는데 배포 전 회차에 그 출근표가 있으면 저장하지 않고 행 수를 보인 뒤 [그래도 저장](본 행 수를 `confirm` 으로, 그사이 바뀌면 다시 묻는다), 생성됨 회차에 배정이 남은 관제 정의를 끄면 저장하고 경고, 켜진 근무조 중 어느 부서에도 없는 것이 있으면 경고 상자와 [부서 저장]. 단계 칸은 맨 아래 접힌 칸이고 저장된 단계·실제 버튼 글자 미리보기와 저장 확인창이 있다.
- 쓰기마다 로그 한 줄 `board <code>: <동작> <대상 아이디·부서 코드·근무표 code> by <아이디>` 와 Django `LogEntry` 한 줄(대상 사람·근무표, `object_repr` 는 아이디·code, `change_message` "근무표 <code>: <동작>")을 남긴다. 실명은 넣지 않는다(`log_actions` 는 `object_repr` 에 실명을 넣어 쓰지 않는다, `board_settings._audit`). 관리 화면에서 그 사람·근무표 편집 페이지의 [기록]으로 본다(첫 화면 "최근 작업"은 로그인한 슈퍼유저 자신의 작업만 보인다).
""")
edit(A,"""  - 1단계 임시 기준 `boards.legacy_admin_entry(board)`(= 마감을 안 쓰는 근무표)는 입력 그룹 자동 생성(`Department.save`)과 부서 폼의 입력 담당자 금지에만 남는다. 그래서 관리 화면 단계 칸도 2단계까지 읽기 전용이다(3단계에서 첫 입력 담당자를 넣을 때 그룹을 만들기로 바꾸며 함수를 지우고 단계 편집을 연다).
""","""  - 단계 칸(켜고 끄기·이름)은 관리 화면 "근무표"와 [근무표 설정] "회차 단계" 칸에서 고친다(근무표 통합 3단계에서 1단계 임시 기준 `legacy_admin_entry` 를 지우며 열었다). 단계를 켜고 끄는 것은 막지 않는다. 끈 단계에 남은 회차는 저장 뒤 안내와 회차 화면 한 줄이 알리고 "다른 상태로 옮기기"로 켠 단계로 옮긴다.
""")
edit(A,"출근표 입력 글(`STEPS[\"manager\"]`)에는 영상 뒤에 생긴 채우기 버튼 설명이 한 줄 있다.",
"글 도움말 \"근무표 설정\"(`STEPS[\"settings\"]`, 근무표 관리자)은 [근무표 설정] 칸마다 할 일이다(단계 줄은 붙지 않는다). 출근표 입력 글(`STEPS[\"manager\"]`)에는 영상 뒤에 생긴 채우기 버튼 설명이 한 줄 있다.")
edit(A,"- 실명은 커밋하지 않는다. 테스트는 가상 이름만 쓴다.\n",
"- 실명은 커밋하지 않는다. 테스트는 가상 이름만 쓴다.\n- [근무표 설정]에서 한 일은 로그 한 줄과 `LogEntry`(아이디·부서 코드·근무표 code 만)로 남는다. 근무표 관리자는 자기 근무표에 관리자를 넣을 수 있다(권한을 나눠 주는 권한을 슈퍼유저에서 근무표 관리자로 내린 결정, PRINCIPLES 2026-11-18). 막는 것: 다른 근무표 사람을 관리자로 넣기, 재직 중인 다른 관리자 빼기, 재직 관리자 0명.\n")

O='docs/OPERATIONS.md'
edit(O,"사이트에 다시 들어가 메뉴에 [회차]·[이력](관제 정의가 있으면 [통계]도)이 보이면 된다. 그룹 관리자(그룹에 사람을 넣고 빼는 사람)는 관리 화면 \"그룹\" → 그 그룹 → \"그룹 관리자\" 줄에서 정한다. 그 사람에게는 메뉴 [그룹]이 보이고, 거기서 멤버를 넣고 뺀다.",
"사이트에 다시 들어가 메뉴에 [회차]·[이력]·[근무표 설정](관제 정의가 있으면 [통계]도)이 보이면 된다. 그 뒤 다른 관리자와 부서 입력 담당자는 근무표 관리자가 사이트 메뉴 [근무표 설정]에서 넣고 뺀다.")
edit(O,"\"사용자\" → 그 사람 → \"그룹\" 칸에서 \"IT 근무표 관리\"를 넣고 뺀다(그룹 관리자가 있으면 그 사람이 [그룹] 화면에서도 넣고 뺀다). \"스태프 권한\" 체크는 관리자 판정에 쓰이지 않는다.",
"\"사용자\" → 그 사람 → \"그룹\" 칸에서 \"IT 근무표 관리\"를 넣고 뺀다. 근무표 관리자도 사이트 [근무표 설정] → 관리자에서 그 근무표 사람이나 부서 없는 계정을 넣고, 나 자신과 퇴사한 관리자를 뺀다. 재직 중인 다른 관리자를 빼는 일은 여기(사용자 \"그룹\" 칸)서만 한다. 어느 쪽에서든 **재직 중인 관리자가 하나도 남지 않게는 빼거나 재직을 끌 수 없다**(\"<근무표> 근무표에 재직 중인 관리자가 남지 않습니다. 먼저 다른 관리자를 넣으세요.\", 사용자 지우기도 같다). \"스태프 권한\" 체크는 관리자 판정에 쓰이지 않는다.")
edit(O,"- 부서 입력 담당자는 부서 화면의 \"입력 담당자\"에서 지정한다(그 부서의 입력 그룹 \"<부서> 출근표 입력\" 멤버가 된다. 부서를 만들면 입력 그룹이 저절로 생긴다).",
"- 부서 입력 담당자는 근무표 관리자가 사이트 [근무표 설정] → 입력 담당자에서 넣고 뺀다(관리 화면 부서 화면의 \"입력 담당자\"로도 된다). 그 부서의 입력 그룹 \"<부서> 출근표 입력\" 멤버가 되고, 그룹은 첫 담당자를 넣을 때 생긴다(같은 이름의 그룹이 이미 있으면 막히니 관리 화면 \"그룹\"에서 그 그룹 이름을 바꾼다). 담당자가 없는 부서는 근무표 관리자만 입력한다.")
edit(O,"| 작성 중 단계 사용 / 마감 단계 사용 | 둘 다 끈다 | \"회차 단계\" 묶음. 끄면 그 단계를 건너뛰고 근무표 관리자가 출근표를 직접 넣는다(IT 는 둘 다 켬, 부서 담당자가 넣는다). 저장 뒤 못 바꾼다 |",
"| 작성 중 단계 사용 / 마감 단계 사용 | 둘 다 끈다 | \"회차 단계\" 묶음. 끄면 그 단계를 건너뛴다(IT 는 둘 다 켬). 나중에 [근무표 설정]에서도 바꿀 수 있지만 진행 중인 회차에 바로 반영되니 처음에 정한다 |")
edit(O,"| 단계 이름 | 취합 중 이름 \"입력 중\", 생성됨 이름 \"확정\"(나머지 그대로) | 회차 화면 단계·버튼 이름이 된다(\"입력 중\"·[확정]·[확정 취소]). 다섯 이름은 서로 달라야 한다. 저장 뒤 못 바꾼다 |",
"| 단계 이름 | 취합 중 이름 \"입력 중\", 생성됨 이름 \"확정\"(나머지 그대로) | 회차 화면 단계·버튼 이름이 된다(\"입력 중\"·[확정]·[확정 취소]). 다섯 이름은 서로 달라야 한다 |")
edit(O,"| 입력 담당자 | 비워 둔다 | 마감을 끈 근무표는 근무표 관리자가 입력한다(고르면 오류) |",
"| 입력 담당자 | 비워 둔다 | 비우면 근무표 관리자만 입력한다. 담당자가 필요하면 근무표 관리자가 나중에 [근무표 설정]에서 넣는다 |")
edit(O,"### 4. 근무표 관리자·그룹 관리자 (관리 화면 → 사용자·그룹)","### 4. 근무표 관리자 (관리 화면 → 사용자)")
edit(O,"관리자에게는 메뉴 [출근표 입력]·[회차]·[이력]과 도움말 \"회차 운영(단계·출근표·생성·배포)\"이 보인다.",
"관리자에게는 메뉴 [출근표 입력]·[회차]·[이력]·[근무표 설정]과 도움말 \"회차 운영(단계·출근표·생성·배포)\"·\"근무표 설정\"이 보인다. 그 뒤 일상 작업(관리자 더하기, 입력 담당자, 근무 정의·부서 출근조·점심 시각)은 근무표 관리자가 [근무표 설정]에서 한다.")
edit(O,"""- **그룹 관리자**(선택): 관리자가 바뀔 때 슈퍼유저 없이 사람을 넣고 빼게 하려면, 근무표 화면의 "관리 그룹" 링크(또는 관리 화면 → 그룹 → "시장운영실 근무표 관리") → "그룹 관리자" 줄에서 [그룹 관리자 더 추가하기]로 사람을 고르고 저장한다(선택 목록은 이름만 보인다. 이름은 모든 근무표에서 겹치지 않으니 이름으로 고른다). 그 사람에게 메뉴 [그룹]이 생기고 거기서 멤버를 넣고 뺀다.
- 이 그룹 화면에는 멤버 목록이 없다(멤버는 사용자 화면의 "그룹" 칸이나 사이트 메뉴 [그룹]에서 본다). **그룹 "이름" 칸은 고치지 않는다**""","""- 관리 화면 "그룹"은 이름·멤버를 보기만 한다(멤버는 사용자 화면의 "그룹" 칸이나 사이트 [근무표 설정]에서 고친다). **그룹 "이름" 칸은 고치지 않는다**""")
edit(O,"| 부서 이름 | 부서 화면 \"이름\" | 부서 이름만 바뀐다(마감을 끈 근무표의 부서는 입력 그룹이 없다) |",
"| 부서 이름 | 부서 화면 \"이름\" | 부서 이름이 바뀌고, 입력 그룹이 있으면 그 이름도 \"<새 이름> 출근표 입력\"으로 같이 바뀐다(같은 이름의 그룹이 있으면 막힌다) |")
edit(O,"| 근무 정의 이름·시각 | 근무표 화면 근무 정의 줄 |","| 근무 정의 이름·시각 | 근무표 화면 근무 정의 줄 또는 [근무표 설정] → 근무 정의와 부서 |")
edit(O,"| 근무조를 새로 씀 | [근무 정의 더 추가하기] | 남은 키(근무조 1~4 중 안 쓴 것)로 줄을 더하고, 부서 화면 \"가능한 출근조\"에도 체크한다 |",
"| 근무조를 새로 씀 | [근무 정의 더 추가하기] 또는 [근무표 설정]의 빈 \"새 근무 정의\" 칸 | 남은 키(근무조 1~4 중 안 쓴 것)로 줄을 더해 저장하고, 부서 \"가능한 출근조\"에도 체크해 한 번 더 저장한다([근무표 설정]은 체크하지 않은 근무조를 경고하고 [부서 저장]을 보인다). 부서에서 근무조를 뺄 때 배포 전 회차에 그 출근표가 있으면 [근무표 설정]이 행 수를 보이고 [그래도 저장]을 한 번 더 누르게 한다 |")
edit(O,"| 점심 시각 | 부서 화면 \"점심 시작\"·\"점심 끝\" |","| 점심 시각 | 부서 화면 \"점심 시작\"·\"점심 끝\" 또는 [근무표 설정]의 부서 칸 |")
edit(O,"| 코드·회차 단계, 부서의 근무표·코드 | — | 저장 뒤 바꿀 수 없다(읽기 전용). 근무표는 지울 수도 없으니 잘못 만들었으면 더 손대지 말고 개발 담당에게 묻는다 |",
"| 회차 단계 | 근무표 화면 \"회차 단계\" 또는 [근무표 설정] 맨 아래(접힌 칸) | 진행 중인 회차의 단계 이름·버튼이 바로 바뀐다. 단계를 끄면 그 단계에 있던 회차는 저장 뒤 안내대로 회차 화면의 \"다른 상태로 옮기기\"로 옮긴다 |\n| 코드, 부서의 근무표·코드 | — | 저장 뒤 바꿀 수 없다(읽기 전용). 근무표는 지울 수도 없으니 잘못 만들었으면 더 손대지 말고 개발 담당에게 묻는다 |")
edit(O,"| 관리자 교체 | 사용자 \"그룹\" 칸 또는 메뉴 [그룹] | 그날부터 새 관리자가 회차·메모·지난 날짜 수정을 한다 |",
"| 관리자 교체 | [근무표 설정] → 관리자(넣기, 나 자신·퇴사자 빼기) 또는 사용자 \"그룹\" 칸(재직 중인 다른 관리자 빼기) | 그날부터 새 관리자가 회차·메모·지난 날짜 수정·설정을 한다. 재직 관리자가 하나도 남지 않게는 어디서도 뺄 수 없다(새 관리자를 먼저 넣는다) |")
edit(O,"- nginx 를 켜 둔 서버는 이 묶음을 마친 뒤",
"""- **근무표 통합 3단계로 올릴 때 (한 번, 되돌리기는 업그레이드 전 백업 복원으로만)**: `migrate` 가 0024 를 적용한다(그룹 관리자 표 삭제). 메뉴 [그룹]이 사라지고 근무표 관리자에게 [근무표 설정]이 생긴다(관리자·입력 담당자·근무 정의와 부서 출근조·점심 시각·회차 단계). 관리 화면 "근무표"의 단계 칸이 저장된 근무표에서도 고쳐진다. 관리 화면 사용자 편집·지우기가 근무표마다 마지막 재직 관리자를 빼지 못하게 막는다. 새 입력 그룹은 첫 입력 담당자를 넣을 때만 생긴다(기존 그룹은 그대로). IT 회차 화면·알림은 그대로다.
  - 업그레이드 전 확인 ①(읽기 전용, **올리기 전에 해결**): 근무표별 재직 관리자 수. 0 인 근무표가 있으면 올리기 전에 관리 화면 사용자 편집의 "그룹" 칸으로 그 근무표 관리 그룹에 재직자를 넣는다(3단계부터는 재직 관리자 0명인 근무표를 앱에서 아무도 고칠 수 없다. 관리 화면은 빼는 쪽만 막으므로 넣기는 된다). `코드|재직 관리자 수`, 모든 줄이 1 이상이어야 한다.
    `sudo -u duty sqlite3 -readonly data/db.sqlite3 "SELECT b.code, (SELECT COUNT(*) FROM duty_user_groups ug JOIN duty_user u ON u.id = ug.user_id WHERE ug.group_id = b.admin_group_id AND u.is_active = 1) AS active_admins FROM duty_board b ORDER BY 1;"`
  - 업그레이드 전 확인 ②(내보내 둘 것, 참고용): 그룹 관리자 **전부**(슈퍼유저, 근무표·부서에 걸리지 않은 그룹 포함)를 `아이디,그룹 이름` CSV 로 서버 파일에 남긴다(아이디·그룹 이름만이라 실명은 없다. `data/` 안이라 백업·권한 규칙을 따른다). 0024 를 거꾸로 돌려도 빈 표만 돌아오고, 이 파일은 복원 도구가 아니라 "누가 그룹 관리자였는지" 사람이 보는 기록이다. 그중 근무표 관리자가 아닌 사람이 계속 멤버를 고쳐야 하면, 업그레이드 뒤 그 근무표 관리자가 [근무표 설정]에서 관리자로 넣을지 정한다(자동으로 넣지 않는다: 관리자는 회차·배포까지 할 수 있어 권한이 넓어진다).
    `sudo -u duty sqlite3 -readonly -csv data/db.sqlite3 "SELECT u.username, g.name FROM duty_groupkeeper k JOIN auth_group g ON g.id = k.group_id JOIN duty_user u ON u.id = k.user_id ORDER BY 2, 1;" | sudo -u duty tee data/groupkeepers-before-phase3.csv`
  - 되돌리기는 위 "롤백"(코드 되돌리기 + 업그레이드 전 백업 `restore`)만 지원한다(그룹 관리자도 그대로 돌아온다). `migrate` 거꾸로(`migrate duty 0023`)는 빈 그룹 관리자 표를 만들 뿐이라 쓰지 않는다. 업그레이드 뒤 [근무표 설정]에서 단계·근무 정의를 고쳤으면 백업 복원으로 그 변경도 사라진다.
  - [근무표 설정]에서 누가 무엇을 바꿨는지: 관리 화면에서 그 사람·근무표 편집 페이지 오른쪽 위 [기록](관리 화면 첫 화면의 "최근 작업"은 로그인한 슈퍼유저 자신의 작업만 보여 거기서는 안 보인다). 웹 로그에도 `board <코드>: <동작> <대상> by <아이디>` 줄로 남는다(14일).
  - 공지(지금 쓰는 메신저로). 알릴 사람: 근무표 관리자 전원, 그룹 관리자였던 사람(확인 ② 목록). "[그룹] 메뉴가 [근무표 설정]으로 바뀌었습니다. 근무표 관리자는 여기서 관리자·입력 담당자·근무 정의·부서 출근조와 점심 시각을 직접 고칩니다. 그룹 관리자였지만 근무표 관리자가 아닌 분은 이제 그 근무표 관리자에게 부탁하세요."
- nginx 를 켜 둔 서버는 이 묶음을 마친 뒤""")

P='docs/PRINCIPLES.md'
s=open(P).read().rstrip("\n")+"\n"
s+="""| 2026-11-18 | 권한을 셋(근무표 관리자·부서 입력 담당자·슈퍼유저)으로 줄인다. 그룹 관리자(`GroupKeeper`, 마이그레이션 0024 로 표 삭제)·[그룹] 화면·`services/groups.py` 를 지우고, 근무표 관리자가 [근무표 설정](`services/board_settings.py`)에서 그 근무표의 관리자·입력 담당자·근무 정의와 부서 출근조·점심 시각·회차 단계를 고친다. 권한을 나눠 주는 권한(관리자 넣기)이 슈퍼유저에서 근무표 관리자로 내려온다(2026-11-16 "권한을 나눠 주는 권한은 슈퍼유저에게"를 바꾸는 결정, 받아들인 위험: 관리자가 자기 근무표 사람·부서 없는 계정을 관리자로 넣는 것은 막지 않고 모든 설정 쓰기를 로그 한 줄과 `LogEntry`(아이디·코드만)로 남긴다) | 사용자 지적: 관리자가 바뀌거나 사람이 들어올 때마다 슈퍼유저를 거치는 것이 운영 공수다. 권한 개념이 넷이면 누가 무엇을 하는지 헷갈린다 |
| 2026-11-18 | 근무표마다 재직 관리자 한 명 이상(앱의 빼기와 관리 화면 사용자 편집·지우기가 같은 검사 `boards.left_without_admin`). 앱에서 관리자 빼기는 나 자신이나 퇴사한 관리자만, 재직 중인 다른 관리자 빼기는 슈퍼유저 | 회차·배포·설정을 할 사람이 없는 근무표를 막고, 빼고 나서 그 계정을 다루는 두 걸음 우회를 막는다 |
| 2026-11-18 | 입력 그룹은 첫 입력 담당자를 넣을 때 만든다(`Department.ensure_input_group`, 이름이 겹치면 한국어 오류). 1단계 임시 기준 `legacy_admin_entry` 를 지우고 관리 화면·[근무표 설정]의 단계 칸 편집을 연다 | 그룹이 없는 부서와 빈 그룹인 부서는 권한상 같아 미리 만들 까닭이 없고, 업그레이드가 이름 겹침으로 멈출 길이 없다. 임시 기준이 사라져 단계를 바꿔도 섞인 상태가 생기지 않는다 |
"""
open(P,'w').write(s)

V='docs/OVERVIEW.md'
edit(V,"| 관리자(근무표 관리 그룹) | IT 운영 담당 | 회차 만들기·취합·생성·배포·배포 취소, 지난 날짜 수정, 메모(근무 없음 포함), 통계·이력 |",
"| 관리자(근무표 관리 그룹) | IT 운영 담당 | 회차 만들기·취합·생성·배포·배포 취소, 지난 날짜 수정, 메모(근무 없음 포함), 통계·이력, [근무표 설정](관리자·입력 담당자·근무 정의와 부서 출근조·점심 시각·회차 단계) |")
edit(V,"| 그룹 관리자 | 슈퍼유저가 정한 사람 | 맡은 그룹(근무표 관리·출근표 입력)에 사람을 넣고 빼기([그룹] 화면) |\n","")
edit(V,"| 슈퍼유저 | 관리자 중 1~2명 | 관리 화면: 계정 발급·부서(점심 시각)·입력 담당자·관리자 지정(사용자의 그룹 칸)·근무표와 근무 정의 추가·편집·그룹 관리자 지정·휴장일·로그인 잠금 해제·알림 설정 |",
"| 슈퍼유저 | 관리자 중 1~2명 | 관리 화면: 근무표 만들기·계정 발급·부서 만들기·인사이동·관리자 지정과 재직 중인 다른 관리자 빼기(사용자의 그룹 칸)·휴장일·로그인 잠금 해제·알림 설정 |")

D='docs/DEVELOPMENT.md'
edit(D,"manager 를 MEMS 입력 그룹에 넣는다(관리자·담당자 판정이 그룹이라서).","manager 를 MEMS 입력 그룹에 넣는다(첫 담당자라 `ensure_input_group` 이 그룹을 만든다. 관리자·담당자 판정이 그룹이라서).")
print("ok")
PYEOF
```

Run: `git grep -n -E "\[그룹\]|그룹 관리자|GroupKeeper|legacy_admin_entry" -- docs/ARCHITECTURE.md docs/OVERVIEW.md` → 아무것도 안 나온다. OPERATIONS 에는 지난 단계 업그레이드 메모와 "근무표 통합 3단계로 올릴 때"에만 남는다.

- [ ] **Step 6: 전체를 확인한다**

Run: `.venv/bin/pytest -W error -q` → `1371 passed`
Run: `makemigrations duty --check --dry-run` → "No changes detected in app 'duty'"
Run(업그레이드 확인 ①②의 열 이름, 임시 DB — 실제 운영 DB 가 아니다):
```bash
W=$(mktemp -d); export DUTY_DEBUG=1 DUTY_ENV_FILE= DUTY_DATA_DIR=$W
.venv/bin/python manage.py migrate -v0 && .venv/bin/python manage.py migrate duty 0023 -v0
sqlite3 -readonly $W/db.sqlite3 "SELECT b.code, (SELECT COUNT(*) FROM duty_user_groups ug JOIN duty_user u ON u.id = ug.user_id WHERE ug.group_id = b.admin_group_id AND u.is_active = 1) AS active_admins FROM duty_board b ORDER BY 1;"   # it|0
sqlite3 -readonly -csv $W/db.sqlite3 "SELECT u.username, g.name FROM duty_groupkeeper k JOIN auth_group g ON g.id = k.group_id JOIN duty_user u ON u.id = k.user_id ORDER BY 2, 1;"   # (빈 결과)
rm -rf $W; unset DUTY_DEBUG DUTY_ENV_FILE DUTY_DATA_DIR
```

- [ ] **Step 7: 브라우저로 본다**

`admin` [도움말] → "글 도움말" 아래 "회차 운영" 다음에 "근무표 설정(관리자·입력 담당자·근무 정의·단계) · 근무표 관리자" 여덟 줄. `manager` 로는 보이지 않는다. 390px·아주 크게에서 줄이 감기고 가로 넘침 없음.

- [ ] **Step 8: 커밋한다**

```bash
git add duty/help.py tests/test_help.py tests/snapshots/help-admin.html docs/ARCHITECTURE.md docs/OPERATIONS.md docs/OVERVIEW.md docs/DEVELOPMENT.md docs/PRINCIPLES.md
git commit -m "docs: 근무표 통합 3단계(근무표 설정 화면, 그룹 관리자 정리, 늦은 입력 그룹)와 업그레이드 확인·롤백·공지, 글 도움말 '근무표 설정'

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

## 자체 점검(설계 12절 3단계 대조표)

| 설계 | 작업 |
|---|---|
| 5.1 단계 칸 편집 열기(관리 화면·설정 화면) | Task 1(관리 화면), Task 6(설정 화면), 끈 단계 안내 Task 4 |
| 5.3 늦은 입력 그룹·`ensure_input_group`·이름 겹침 오류·관리 화면 부서 폼·`legacy_admin_entry` 삭제 | Task 1(모델·관리 화면), Task 2(`add_assignee`) |
| 5.4 버튼 글자 검사(같은 함수, 미리보기는 실제 글자) | Task 4(`StepsForm` = `BoardForm` 의 부모), Task 6(미리보기) |
| 5.6 GroupKeeper 삭제·0024·인라인 | Task 7 |
| 6.1 `perms.kept_groups`·`services/groups.py` 삭제 | Task 7 |
| 6.2 공통 규칙(`_require_admin`·IDOR·로그·`LogEntry` `_audit`, 실명 없음) | Task 2, Task 4 |
| 6.2 `save_steps`·`save_shifts`(같은 저장의 부서 출근조, 관제 끄기 경고, 근무조 빼기 확인)·`add_admin`·`remove_admin`·`add_assignee`·`remove_assignee` | Task 2, Task 4 |
| 7.1 주소·메뉴·제목·근무표 링크·404·바로가기·앵커·칸 안 메시지 | Task 5 |
| 7.2 관리자 칸(나·퇴사자만 빼기, "마지막 관리자", "빼기는 슈퍼유저에게", 후보) | Task 5 |
| 7.2 입력 담당자 칸("담당자 없음 — 근무표 관리자만 입력합니다") | Task 5 |
| 7.2 근무 정의와 부서 칸(카드 grid, 부서 덩어리, 두 번 저장 안내, 배정 안 된 근무조 경고·[부서 저장], 관리 화면과 같은 경고) | Task 6 |
| 7.2 회차 단계 칸(맨 아래·접힘·끈 단계 표시·미리보기·확인창·저장 뒤 경고) | Task 6 |
| 7.3 검사 재사용 | Task 4 |
| 7.4 관리 화면: 단계 편집, 그룹 보기만, 링크 글, 재직 관리자 한 명 이상(편집·지우기), 기록 보는 곳 | Task 1·3·7·8 |
| 8 권한(관리자가 관리자를 넣음, 막는 것 세 가지) | Task 2·3·5, 문서 Task 8 |
| 10.2 0024(거꾸로 빈 표) | Task 7 |
| 10.3 3단계 ①(재직 관리자 수)·②(그룹 관리자 CSV) | Task 8(OPERATIONS, 임시 DB 로 확인) |
| 10.4 3단계 공지·롤백(백업 복원만) | Task 8 |
| 11 테스트(권한·범위·재직 관리자·입력 그룹·관리 화면 규칙·근무 정의와 부서·단계·0024·로그) | Task 1~7 |
| 13 문서·글 도움말 | Task 8 |

- 4단계로 넘기는 것: 사람 칸(설계 7.2 의 1번), 5.7 계정 함수, `issue`·`set_person`·`set_active`·`future_cells`, 바로가기 [사람], 도움말·공지의 사람 부분.
