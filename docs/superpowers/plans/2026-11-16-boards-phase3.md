# 근무표 일반화 3단계(직접 입력 방식과 그룹 화면) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 직접 입력(`input_mode=direct`) 근무표의 회차 흐름(입력 중 → 확정 → 배포됨)과 입력 표의 채우기 버튼, 그룹 관리자의 그룹 화면, 관리 화면의 근무표·근무 정의·그룹 관리자 편집(설계 4.3 검증), 직접 입력 근무표 관리자용 글 도움말을 만든다. 4단계(시장운영실 개시)를 코드 변경 없이 관리 화면 설정만으로 할 수 있게 한다.

**Architecture:** DB 상태 5개와 제약은 그대로 두고, 직접 입력 근무표에서는 화면 이름만 입력 중(취합 중)·확정(생성됨)·배포됨으로 바꾼다(`models.step_label`). 직접 입력의 회차 규칙은 기존 서비스 세 곳(`periods.save_draft`·`periods.move`·`generate.run_generation`)에 근무표의 입력 방식으로 갈래를 둔다. 채우기는 저장하지 않는 서비스 함수(`collect.fill_week`)가 화면의 표로 그 주만 다시 그리고, 저장은 기존 [표 저장] 한 길이다. 그룹 화면은 새 서비스 `services/groups.py`(쓰기)와 `perms.kept_groups`(읽기). 관리 화면 검증은 폼·폼셋(`admin.BoardShiftForm`·`BoardShiftFormSet`)과 모델 `clean`(저장한 근무 정의의 키 고정·지우기 금지, 근무표 코드, 직접 입력 근무표의 부서 하나). **스키마 변경이 없어 마이그레이션이 없다.**

**Tech Stack:** Python 3.12, Django 5.2, SQLite(WAL), pytest + pytest-django, htmx, Pico.css. 새 의존성 없음.

**Spec:** `docs/superpowers/specs/2026-11-15-boards-design.md` (3단계 = 11절 "3단계". 참고: 4.2·4.3 근무표·근무 정의와 검증, 4.5 그룹 관리자, 6.1 회차 화면 단계, 6.2 출근표 입력·채우기 버튼, 6.3 생성·확정, 7절 화면, 9절 권한, 12절 테스트)

## 판단한 것 (설계가 정하지 않은 곳, 컨트롤러 검토용)

1. **마이그레이션 없음.** 3단계는 스키마를 바꾸지 않는다(다음 번호 0023 은 쓰지 않는다). 근무 정의 시각 제약(`boardshift_times_valid`)의 한국어 문구는 제약에 `violation_error_message` 를 다는 대신(AlterConstraint 마이그레이션이 생긴다) 폼이 같은 검사를 먼저 해서 `start` 칸에 붙인다. 오류가 난 칸은 Django 가 제약 검사에서 빼므로 영어 제약 문구가 같이 뜨지 않는다.
2. **직접 입력 회차 상태:** 새 회차는 `save_draft` 가 바로 취합 중(= 입력 중)으로 저장한다(작성 중을 거치지 않음, 상태 기록 `"" → 취합 중`). 작성 중·마감은 직접 입력에서 쓰지 않는다: `periods.move` 는 직접 입력 회차를 취합 중으로만 옮기고([확정 취소]), `run_generation` 은 직접 입력에서 취합 중·생성됨만 받는다(마감 거부). [확정 취소]는 새 뷰 없이 기존 `period_move`(to=collecting)를 쓴다. 기존 테스트 `tests/test_boards_generate.py` 의 `ops_period` 기본 상태(직접 입력 근무표인데 마감)를 취합 중으로 바꾼다(기계적 변경, 테스트 3개).
3. **화면 이름:** `models.DIRECT_STEPS`·`step_label(board, status)`·`Period.status_label` 이 회차 제목·단계 띠·회차 목록·상태 기록·입력 표 문구·서비스 오류 문구("입력 중인 회차가 아닙니다")·배포 취소 확인창과 설명("확정으로 되돌릴까요", "확정으로 돌아갑니다")·배포 오류("확정한 회차만 배포할 수 있습니다")·빈 [출근표 입력] 목록("입력 중인 회차가 없습니다", 관리하는 근무표가 섞이면 "취합 중·입력 중인 회차가 없습니다")에 쓰인다. 부서별 취합은 지금 글자 그대로("취합 중인 회차가 아닙니다" 테스트 그대로). 회차 삭제 확인창의 "생성 결과" 같은 일반 낱말은 그대로 둔다.
4. **확정 경고:** 그 근무표 부서 중 하나라도 출근표가 없는 평일(건너뛰는 날 제외)을 날짜만 모아(`periods.empty_days`) 회차 화면(확정 전, ⚠ 줄)과 확정 뒤 메시지 둘 다에 보인다. 점심당번을 못 채운 날 경고(2단계)는 그대로 따로 나온다(같은 날이 두 경고에 다 나올 수 있다).
5. **채우기 버튼:** 표 저장과 같은 폼 안의 제출 버튼(`fill=2w:YYYY-MM-DD` / `1w:…`)으로 보낸다. 그래서 다른 주에 저장 전 고친 값이 그대로 남고, 회차 기간 안 기준 데이터는 DB 가 아니라 **화면의 표**(저장 전 고친 값 포함)를 쓴다. 회차 밖 날은 배포된 근무표(그날의 주인, `roster.published_days`)를 쓴다. 칸에서 Enter 를 누르면 채우기가 아니라 저장이 되도록 폼 맨 앞에 화면 밖 [표 저장] 버튼을 둔다. 버튼은 직접 입력 근무표의 입력 중 회차에서만 보인다. 주 머리 줄의 날짜와 버튼 값은 그 주 **월요일**이다(회차가 주 중간에 시작해도, `week_start`).
6. **[지난주와 같게]의 "사유 제외"** = 근무조는 옮기고 사유는 옮기지 않는다(지난주 휴가였던 사람도 같은 근무조로 들어간다). 지난주 같은 요일에 아무도 없던 날은 이번 주도 빈 줄이 된다("그대로"). 그 주의 줄은 통째로 바뀐다(채우기 전 그 주 값은 버린다).
7. **[2주 전 기준으로 채우기]:** 2주 전 **그 주 월~금 전체**(회차 기간과 무관)를 본다. 대표 근무조의 세 번째 기준(시작 시각)은 한 사람이 하루 한 근무조라 갈 일이 없어 코드에 두지 않는다(주석). 보이는 조건 = 그 부서의 입력 근무조(`collect.input_keys`)가 정확히 3개. 사람 = 지금 재직하는 그 부서 사람(입력 표가 부서 단위라서). 순수 함수 `shifts.two_week_rotation` 에 둔다(새 파일을 만들지 않음).
8. **그룹 화면:** 서비스 `services/groups.py`(`add_member`·`remove_member`), 뷰는 `views/manage.py` 의 `groups`(새 뷰 파일 없음), 주소 `/groups/` 하나(POST 는 `group`·`member`·`do=add|remove`). 넣을 후보 = 재직 계정 전부(부서 없는 관리 전용 계정 포함). 넣고 빼기는 로그(`duty.services.groups`, 아이디만)로만 남기고 기록 표는 만들지 않는다. 경고는 **근무표 관리 그룹**이 비었을 때만(입력 그룹은 비어도 경고 없음). 그룹마다 무슨 권한인지 한 줄 설명을 붙인다.
9. **관리 화면:** 근무표의 `code`(`boards.it_board()` 의 열쇠)와 `input_mode` 는 만든 뒤 읽기 전용(입력 방식을 바꾸면 회차 상태·입력 그룹이 맞지 않는다). 근무표 지우기는 막는다. 코드는 만들 때 짧은 영문(`[a-z][a-z0-9]{0,15}`, `Board.clean`)만 받는다. 근무표 이름이 다른 근무표와 같으면 한국어 오류.
   - **저장한 근무 정의는 키를 바꾸거나 지울 수 없다**(쓰였는지 따지지 않는다, 결정됨). 바꿀 수 있는 것은 이름·시각·자격·기본 알림·'사용'. 관리 화면은 저장한 줄의 키 칸을 잠그고 지우기 칸을 없앤다(`can_delete=False`, 아직 저장하지 않은 추가 줄만 화면에서 뺀다). 모델도 막는다: `BoardShift.clean`(키·근무표가 DB 값과 다르면 오류), `BoardShift.delete`(늘 오류). 쿼리셋 일괄 삭제(`QuerySet.delete`)는 거치지 않는다 — 받아들인 한계(`ponytail:` 주석). 그래서 기존 `tests/test_lunch.py` 의 준비 코드 `lunch.delete()` 세 곳을 쿼리셋 삭제로 바꾼다(기계적 변경).
   - **직접 입력 근무표는 부서 하나**(설계 6.2): `Department.clean` 이 둘째 부서를 막는다(관리 화면 부서 폼이 부른다). ORM `objects.create` 는 거치지 않는다(기존 테스트의 여러 부서 픽스처는 그대로 돈다).
   - 폼셋 검증(Django 기본 겹침 검사는 부르지 않고 한국어로): 이름 겹침 "근무 정의 이름이 겹칩니다: X", 키 겹침 "키가 겹칩니다: 근무조 1", **켜진** 근무조 1개 이상(그래서 "장중관제·점심당번은 근무조가 있어야 함"도 지켜진다), 켜진 근무조끼리 시작 시각이 다름, 관제 자격 근무조는 이 근무표의 근무조이고 **켜진 관제는 켜진 근무조만**, 근무조를 끈 뒤에도 그 근무표의 부서마다 켜진 입력 근무조가 하나 이상. 설계 4.3 표의 "장중관제만"(자격)·"근무조만"(기본 알림)도 검사한다. 저장된 줄끼리 이름을 맞바꾸는 것처럼 DB 값과 부딪히는 경우는 Django 의 한국어 번역 문구("…을/를 가진 근무 정의이/가 이미 존재합니다")가 나온다.
   - 자격 근무조·자격 구분은 JSON 글 대신 체크박스. 그룹 관리자는 관리 화면 "그룹"의 인라인에서 편집한다(GroupKeeper 는 Group 에 걸린 표라 근무표 인라인이 될 수 없다). 근무표 화면에는 관리 그룹 링크를 둔다.
10. **새 부서 폼:** 지금은 새 부서의 출근조 선택지를 IT 정의에서 읽는다(1단계 "새 부서는 IT"). 4단계에서 다른 근무표의 부서를 만들어야 하므로, 새 부서는 중립 이름("근무조 1"~"근무조 4")으로 보이고 저장 때 고른 근무표의 켜진 근무조인지 검사한다(시작 시각 순으로 저장). 저장된 부서는 지금처럼 그 근무표 이름.
11. **도움말:** 직접 입력 근무표 관리자에게만 `/help/` 에 글 도움말 한 덩어리(`help.TEXTS`·`STEPS["direct"]`, 영상 없음, 로그인 팝업은 그대로). IT 관리자 영상 글은 영상 자막과 맞아야 해서 고치지 않는다.
12. **[출근표 입력] 메뉴 목록**(`/collect/`)은 직접 입력 회차도 "취합 중"인 동안 그대로 보인다(제목·문구는 그대로 둔다. 직접 입력 관리자는 회차 화면의 [표 입력]으로 들어간다).

## Global Constraints

- IT 알림 문구·hash 는 바뀌지 않는다. `tests/test_alarm_texts_it.py` 는 고치지 않고 그대로 통과한다(알림 코드를 건드리지 않는다).
- 각 작업이 끝난 시점에 `.venv/bin/pytest -W error -q` 전체가 통과한다(경고 0개). 기대 테스트 수는 참고값(지금 main c93a455 **1125 passed**).
- TDD(테스트를 먼저 쓰고 실패를 확인한 뒤 구현). DB 를 바꾸는 규칙은 `duty/services/`(뷰·명령에서 모델을 직접 고치지 않는다. 관리 화면의 Django 기본 저장은 그대로). 순수 모듈(`shifts`·`generator`·`csv_io`·`ics`·`alarms/`(senders 제외)·`market_days`)에는 ORM 없음.
- "오늘"은 `from . import perms` 후 `perms.today()`. 정해진 값 칸은 `choices` + DB `CheckConstraint`, 기록을 남길 FK는 `PROTECT`. 마이그레이션 파일은 지우지 않는다(3단계는 새 마이그레이션이 없다. `makemigrations duty --check --dry-run` → "No changes detected").
- 화면 문구·오류 메시지는 한국어. 커밋 메시지는 `feat:`/`fix:`/`docs:`/`style:` + 한국어 요약, 끝에 아래 두 줄:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va
  ```
- 실명 데이터 금지(테스트·가짜 데이터는 "가상가" 같은 가상 이름만). `data/`, DB 파일, `.superpowers/`, `.env` 는 열지 않는다. 로그에는 아이디(멤버 코드)만, 실명 금지.
- 운영은 단순하게: 새 deploy 파일·셸 스크립트·타이머를 만들지 않는다. 정적 파일은 CDN 없이.
- 화면을 바꾸는 작업은 테스트 통과만으로 끝내지 않고 아래 "브라우저 확인 준비"대로 띄운 가짜 데이터 DB 에서 PC 1400px·휴대폰 390px, 글씨 **아주 크게**(오른쪽 위 [가] 두 번), **다크 모드**(오른쪽 위 ◐ 로 다크)로 본다. 모든 브라우저 단계에서 페이지 가로 넘침을 콘솔로 잰다. 보는 사람은 시력이 좋지 않고 변화를 싫어하는 60세 가까운 관리자다: 화면마다 진한 버튼 하나, 큰 누름 영역(44px 이상), 가로 스크롤 없음(콘솔 `document.documentElement.scrollWidth > innerWidth` 가 `false`, 넓은 표는 표 안에서만 스크롤).

### 브라우저 확인 준비(모든 화면 작업 공통, Task 1 이후)

가짜 데이터만 쓰는 임시 폴더에서 띄우고, 끝나면 서버를 PID 로 끄고 폴더를 지운다.

```bash
W=$(mktemp -d)
export DUTY_ENV_FILE= DUTY_DEBUG=1 DUTY_DATA_DIR=$W/data
.venv/bin/python manage.py migrate -v0
.venv/bin/python manage.py shell < tools/help_videos/seed.py > /dev/null     # IT 가짜 데이터(계정 비밀번호 Demo-pass-123)
.venv/bin/python manage.py shell <<'EOF'
# 가짜 직접 입력 근무표 '운영팀'(실명 없음). seed.py 다음에 같은 임시 DB 에서만 돌린다
from datetime import time, timedelta
from duty import perms
from duty.models import Board, BoardShift, Commute, Department, GroupKeeper, Period, User
from duty.services import periods, publish
from duty.services.generate import run_generation
admin = User.objects.get(username="admin")
ops = Board.objects.create(code="ops", name="운영팀", input_mode=Board.InputMode.DIRECT)
for key, name, h in (("dawn", "이른", 7), ("normal", "가운데", 9), ("dinner", "늦은", 11)):
    BoardShift.objects.create(board=ops, key=key, name=name, start=time(h, 30), end=time(h + 9, 0), default_alarm=True)
BoardShift.objects.create(board=ops, key="lunch", name="점심당번")
dept = Department.objects.create(code="OPS", name="운영", shifts="dawn,normal,dinner", board=ops, order=0,
                                 lunch_start=time(11, 30), lunch_end=time(12, 30))
team = [User.objects.create_user(f"OPS{i}", password="Demo-pass-123", name=n, department=dept, type="직원", help_dismissed=True)
        for i, n in enumerate("가상하나 가상두리 가상세찬 가상네모 가상다섯 가상여섯".split())]
ops.admin_group.user_set.add(admin)
GroupKeeper.objects.create(group=ops.admin_group, user=admin)  # [그룹] 메뉴 확인용
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
(위 셸 스니펫은 Task 1 의 서비스 동작(직접 입력 회차는 바로 입력 중, 입력 중에서 확정)을 쓴다. 사본에서 돌려 "운영팀 준비 끝"을 확인했다.)

로그인: `admin` / `Demo-pass-123`(슈퍼유저 + IT·운영팀 관리 그룹 + 운영팀 관리 그룹의 그룹 관리자), `member` / `Demo-pass-123`(일반). 관리 화면은 `http://127.0.0.1:8795/admin/`.

끝나면:
```bash
kill $(cat $W/server.pid); rm -rf $W; unset DUTY_ENV_FILE DUTY_DEBUG DUTY_DATA_DIR
```

## 작업 순서와 마이그레이션 번호

| Task | 내용 | 마이그레이션 | 테스트 수(참고) |
|---|---|---|---|
| 1 | 직접 입력 회차 서비스(입력 중 → 확정, 입력 중 기간 수정, 확정 경고, 확정 취소, 화면 단계 이름) | 없음 | 1140 |
| 2 | 직접 입력 회차 화면(단계·[표 입력]·[확정]·[확정 취소]·경고, 목록·상태 기록·입력 표·배포 취소·배포 오류·빈 입력 목록 문구) | 없음 | 1150 |
| 3 | 입력 표의 [2주 전 기준으로 채우기]·[지난주와 같게] | 없음 | 1161 |
| 4 | 그룹 화면(그룹 관리자의 멤버 넣고 빼기, 메뉴 [그룹]) | 없음 | 1169 |
| 5 | 관리 화면의 근무표·근무 정의·그룹 관리자 편집과 검증(저장한 정의 키 고정·지우기 금지, 코드·부서 하나·새 부서 출근조 검사) | 없음 | 1194 |
| 6 | 직접 입력 근무표 관리자용 글 도움말 | 없음 | 1195 |
| 7 | 문서(ARCHITECTURE·OVERVIEW·OPERATIONS·PRINCIPLES 결정 기록) | 없음 | 1195 |

> 검증: Task 1~6 의 코드를 이 브랜치(origin/main c93a455 위, PR #38 포함) 사본(`git archive`)에 그대로 넣어 확인했다(Codex 리뷰 반영 뒤 다시 확인). 저장소는 고치지 않았다. 결과: 작업마다 위 표의 수로 `.venv/bin/pytest -W error -q` 전체 통과, 경고 0개, `makemigrations duty --check --dry-run` → "No changes detected in app 'duty'". 각 작업의 "실패 확인" 기대 결과도 사본에서 재현했다. 브라우저 확인은 사본에서 하지 않았다(가짜 데이터 셸 스니펫이 도는 것까지만 확인) — 각 작업의 브라우저 단계에서 사람이 본다.

---

### Task 1: 직접 입력 회차 서비스

> 범위: 서비스와 모델 도우미만. 화면은 Task 2.

**Files:**
- Modify: `duty/models.py` — `class PeriodStatus` 바로 뒤(`DIRECT_STEPS`·`step_label`), `class Period` 의 `dates()` 뒤(`status_label`)
- Modify: `duty/services/periods.py` — models import, `save_draft` 맨 앞·`period.save()` 앞, `move` 의 `to not in MOVABLE` 검사 뒤, `missing_dates` 앞(`empty_days`)
- Modify: `duty/services/generate.py` — import 두 줄, `run_generation` 의 상태 검사·빈 날 검사, `_fill_lunch` 앞(`_days`)과 끝 줄
- Modify: `duty/services/collect.py` — models import, `_require_input` 의 상태 오류 문구
- Modify(기계적 변경, 단언 그대로): `tests/test_boards_generate.py` — `ops_period` 의 기본 상태 `S.CLOSED` → `S.COLLECTING`
- Test: `tests/test_direct_periods.py`(새 파일)

**Interfaces:**
- Consumes: `duty.models.InputMode`(`COLLECT`/`DIRECT`), `Board.input_mode`, `periods.save_draft(period, by=None)`·`move(period, to, by=None)`·`missing_dates(period) -> dict[str, list[date]]`·`MOVABLE`, `generate.run_generation(period, seed=None, by=None) -> GenerationOutput`(`.warnings: list[str]`), `collect._require_input`
- Produces:
  - `duty.models.DIRECT_STEPS: list[tuple[PeriodStatus, str]]` = `[(COLLECTING, "입력 중"), (GENERATED, "확정"), (PUBLISHED, "배포됨")]`
  - `duty.models.step_label(board, status: str) -> str`: 직접 입력이면 위 이름(없는 상태는 원래 이름), 아니면 `PeriodStatus(status).label`
  - `Period.status_label: str`(property) = `step_label(self.board, self.status)`
  - `periods.empty_days(period) -> list[date]`: `missing_dates` 의 날짜를 합쳐 정렬
  - 동작: 직접 입력 새 회차는 `save_draft` 가 `COLLECTING` 으로 저장(상태 기록 `"" → collecting`). 직접 입력은 `DRAFT`·`COLLECTING` 에서 기간 수정, 그 밖은 `DutyError("기간은 입력 중에만 수정할 수 있습니다.")`. 직접 입력 `move` 는 `to == COLLECTING` 만(아니면 `DutyError("직접 입력 근무표는 입력 중으로만 옮길 수 있습니다.")`). 직접 입력 `run_generation` 은 `COLLECTING`·`GENERATED` 만(아니면 `DutyError("입력 중인 회차만 확정할 수 있습니다.")`), 빈 평일은 막지 않고 `out.warnings[0] = "입력하지 않은 평일이 있습니다(그날은 근무자가 없습니다): 11/20"` 모양(점심당번 경고보다 앞). `_require_input` 의 상태 오류 = `"{step_label(board, COLLECTING)}인 회차가 아닙니다."`(취합 중 / 입력 중).

- [ ] **Step 1: 실패 테스트를 쓴다**

`tests/test_direct_periods.py`(새 파일):
```python
"""직접 입력 근무표의 회차 흐름(설계 6.1·6.3): 입력 중 → 확정 → 배포됨. 이름은 모두 가상."""
from datetime import date, time

import pytest

from duty.errors import DutyError
from duty.models import Board, BoardShift, Commute, Department, DutyAssignment, Period, PeriodEvent, User
from duty.services import collect, periods
from duty.services.generate import run_generation

S = Period.Status
MON, FRI = date(2026, 11, 16), date(2026, 11, 20)


@pytest.fixture
def ops(it_board):
    """가짜 직접 입력 근무표 '운영팀': 근무조 셋(이른·가운데·늦은) + 점심당번, 부서 하나."""
    board = Board.objects.create(code="ops", name="운영팀", input_mode=Board.InputMode.DIRECT)
    for key, name, h in (("dawn", "이른", 7), ("normal", "가운데", 9), ("dinner", "늦은", 11)):
        BoardShift.objects.create(board=board, key=key, name=name, start=time(h, 30), end=time(h + 9, 30))
    BoardShift.objects.create(board=board, key="lunch", name="점심당번")
    dept = Department.objects.create(code="OPS", name="운영", shifts="dawn,normal,dinner", board=board)
    return board, dept


def ops_member(dept, name):
    return User.objects.create_user(f"OPS{User.objects.count() + 1:03d}", password=None, name=name,
                                    department=dept, part="", type="직원")


def new_period(board, start=MON, end=FRI):
    return periods.save_draft(Period(board=board, name="운영 11월", start_date=start, end_date=end))


def test_new_direct_period_starts_in_input(ops, admin_user):
    p = periods.save_draft(Period(board=ops[0], name="운영 11월", start_date=MON, end_date=FRI), by=admin_user)
    assert p.status == S.COLLECTING and p.status_label == "입력 중"
    ev = PeriodEvent.objects.get(period=p)
    assert (ev.from_status, ev.to_status, ev.by) == ("", S.COLLECTING, admin_user)


def test_new_collect_period_still_draft(it_board):
    p = new_period(it_board)
    assert p.status == S.DRAFT and p.status_label == "작성 중"


def test_direct_dates_editable_while_input(ops):
    board, dept = ops
    p = new_period(board)
    m = ops_member(dept, "가상가")
    for x in p.dates():
        Commute.objects.create(period=p, date=x, member=m, shift="dawn")
    p.end_date = date(2026, 11, 18)
    periods.save_draft(p)
    assert sorted(Commute.objects.filter(period=p).values_list("date", flat=True)) == [MON, date(2026, 11, 17), date(2026, 11, 18)]


def test_direct_dates_locked_after_confirm(ops):
    p = new_period(ops[0])
    Period.objects.filter(pk=p.pk).update(status=S.GENERATED)
    p.end_date = date(2026, 11, 18)
    with pytest.raises(DutyError, match="기간은 입력 중에만 수정할 수 있습니다"):
        periods.save_draft(p)


def test_collect_dates_still_draft_only(it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=MON, end_date=FRI, status=S.COLLECTING)
    with pytest.raises(DutyError, match="작성 중"):
        periods.save_draft(p)


def test_confirm_fills_lunch_and_warns_empty_days(ops, admin_user):
    board, dept = ops
    p = new_period(board)
    a, b = ops_member(dept, "가상가"), ops_member(dept, "가상나")
    for x in p.dates()[:4]:  # 금요일은 비워 둔다
        Commute.objects.create(period=p, date=x, member=a, shift="dawn")
        Commute.objects.create(period=p, date=x, member=b, shift="dinner")
    out = run_generation(p, by=admin_user)
    p.refresh_from_db()
    assert p.status == S.GENERATED and p.status_label == "확정"
    assert out.warnings[0] == "입력하지 않은 평일이 있습니다(그날은 근무자가 없습니다): 11/20"
    assert set(DutyAssignment.objects.filter(period=p).values_list("cell", "member")) == {("lunch", a.pk)}
    assert PeriodEvent.objects.filter(period=p).last().to_status == S.GENERATED


def test_confirm_without_empty_days_has_no_warning(ops):
    board, dept = ops
    p = new_period(board)
    a = ops_member(dept, "가상가")
    for x in p.dates():
        Commute.objects.create(period=p, date=x, member=a, shift="dawn")
    assert run_generation(p).warnings == []


@pytest.mark.parametrize("status", [S.DRAFT, S.CLOSED, S.PUBLISHED])
def test_confirm_only_from_input_or_confirmed(ops, status):
    p = Period.objects.create(board=ops[0], name="p", start_date=MON, end_date=FRI, status=status)
    with pytest.raises(DutyError, match="입력 중인 회차만 확정할 수 있습니다"):
        run_generation(p)


def test_collect_generation_still_needs_closed(it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=MON, end_date=FRI, status=S.COLLECTING)
    with pytest.raises(DutyError, match="마감된 회차만 생성할 수 있습니다"):
        run_generation(p)


def test_cancel_confirm_goes_back_to_input(ops, admin_user):
    board, dept = ops
    p = new_period(board)
    a = ops_member(dept, "가상가")
    for x in p.dates():
        Commute.objects.create(period=p, date=x, member=a, shift="dawn")
    run_generation(p)
    periods.move(p, S.COLLECTING, by=admin_user)
    p.refresh_from_db()
    assert p.status == S.COLLECTING and not DutyAssignment.objects.filter(period=p).exists()
    assert Commute.objects.filter(period=p).count() == 5  # 출근표는 그대로


@pytest.mark.parametrize("to", [S.DRAFT, S.CLOSED])
def test_direct_moves_only_to_input(ops, to):
    p = Period.objects.create(board=ops[0], name="p", start_date=MON, end_date=FRI, status=S.GENERATED)
    with pytest.raises(DutyError, match="입력 중으로만"):
        periods.move(p, to)


def test_input_closed_message_uses_direct_name(ops, admin_user):
    board, dept = ops
    board.admin_group.user_set.add(admin_user)
    p = Period.objects.create(board=board, name="p", start_date=MON, end_date=FRI, status=S.GENERATED)
    with pytest.raises(DutyError, match="입력 중인 회차가 아닙니다"):
        collect.apply_table(admin_user, p, dept, {})
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_direct_periods.py`
Expected: `12 failed, 3 passed`(`AttributeError: 'Period' object has no attribute 'status_label'`, 직접 입력 회차가 작성 중으로 만들어짐, 마감 오류 문구 등)

- [ ] **Step 3: 모델 도우미를 더한다**

`duty/models.py` — `class PeriodStatus(...)` 정의 바로 뒤, `class Period` 앞에:
```python
# 직접 입력 근무표의 화면 단계(설계 6.1): DB 상태는 그대로 두고 이름만 바꾼다. 새 회차는 만들자마자 취합 중(= 입력 중)
DIRECT_STEPS = [(PeriodStatus.COLLECTING, "입력 중"), (PeriodStatus.GENERATED, "확정"), (PeriodStatus.PUBLISHED, "배포됨")]


def step_label(board, status: str) -> str:
    """화면에 보일 회차 단계 이름: 직접 입력 근무표는 입력 중·확정·배포됨, 부서별 취합은 상태 이름 그대로."""
    if board.input_mode == InputMode.DIRECT:
        return dict(DIRECT_STEPS).get(status, PeriodStatus(status).label)
    return PeriodStatus(status).label
```
(`dict(DIRECT_STEPS).get("collecting")` 은 찾아진다: TextChoices 멤버는 값 문자열과 hash·비교가 같다. 사본에서 확인.)

같은 파일 `class Period` 의
```python
    def dates(self):
        return weekdays(self.start_date, self.end_date)
```
바로 뒤에:
```python

    @property
    def status_label(self) -> str:
        return step_label(self.board, self.status)
```

- [ ] **Step 4: 기간 수정·새 회차·상태 옮기기·빈 날 목록(`services/periods.py`)**

import 줄을 바꾼다:
```python
from ..models import ChangeLog, Commute, Department, DutyAssignment, InputMode, Period, PeriodEvent
```

`save_draft` 맨 앞 두 줄
```python
    if period.pk and Period.objects.get(pk=period.pk).status != S.DRAFT:
        raise DutyError("기간은 작성 중(draft) 상태에서만 수정할 수 있습니다.")
```
을 바꾼다:
```python
    direct = period.board.input_mode == InputMode.DIRECT
    editable = {S.DRAFT, S.COLLECTING} if direct else {S.DRAFT}  # 직접 입력은 입력 중(= 취합 중)에도 기간을 고친다(설계 6.1)
    if period.pk and Period.objects.get(pk=period.pk).status not in editable:
        raise DutyError("기간은 입력 중에만 수정할 수 있습니다." if direct
                        else "기간은 작성 중(draft) 상태에서만 수정할 수 있습니다.")
```

같은 함수의
```python
    new = period.pk is None
    period.save()
```
를 바꾼다:
```python
    new = period.pk is None
    if new and direct:
        period.status = S.COLLECTING  # 직접 입력: 만들자마자 입력 중
    period.save()
```
(줄어든 기간 밖 행을 지우는 기존 `else` 갈래가 입력 중 회차에도 그대로 돈다.)

`move` 의
```python
    if to not in MOVABLE:
        raise DutyError("옮길 수 없는 상태입니다.")
```
바로 뒤에:
```python
    if period.board.input_mode == InputMode.DIRECT and to != S.COLLECTING:  # 직접 입력의 [확정 취소]는 입력 중으로만
        raise DutyError("직접 입력 근무표는 입력 중으로만 옮길 수 있습니다.")
```

`def missing_dates(` 바로 앞에:
```python
def empty_days(period: Period) -> list[date]:
    """그 근무표 부서 중 하나라도 출근표가 없는 평일(건너뛰는 날 제외), 날짜 순. 직접 입력 회차의 확정 경고."""
    return sorted({d for ds in missing_dates(period).values() for d in ds})


```

- [ ] **Step 5: 확정(`services/generate.py`)**

import 두 줄을 바꾼다:
```python
from ..models import Commute, DutyAssignment, InputMode, Period, User
```
```python
from .periods import empty_days, missing_dates, record
```

`run_generation` 의
```python
    period.refresh_from_db()
    if period.status not in {S.CLOSED, S.GENERATED}:
        raise DutyError("마감된 회차만 생성할 수 있습니다.")
    holidays.sync(perms.today())  # 작업자가 꺼져 있어도 휴장일 표가 비어 있지 않게
    missing = missing_dates(period)
    if missing:
        detail = ", ".join(f"{code} {len(ds)}일" for code, ds in missing.items())
        raise DutyError(f"출근표가 비어 있는 날짜가 있습니다: {detail}")
```
를 바꾼다:
```python
    period.refresh_from_db()
    direct = period.board.input_mode == InputMode.DIRECT  # 직접 입력의 [확정](설계 6.1·6.3)
    if direct and period.status not in {S.COLLECTING, S.GENERATED}:
        raise DutyError("입력 중인 회차만 확정할 수 있습니다.")
    if not direct and period.status not in {S.CLOSED, S.GENERATED}:
        raise DutyError("마감된 회차만 생성할 수 있습니다.")
    holidays.sync(perms.today())  # 작업자가 꺼져 있어도 휴장일 표가 비어 있지 않게
    warnings = []
    if direct:  # 직접 입력은 빈 평일을 막지 않고 경고로만 알린다
        empty = empty_days(period)
        if empty:
            warnings.append(f"입력하지 않은 평일이 있습니다(그날은 근무자가 없습니다): {_days(empty)}")
    else:
        missing = missing_dates(period)
        if missing:
            detail = ", ".join(f"{code} {len(ds)}일" for code, ds in missing.items())
            raise DutyError(f"출근표가 비어 있는 날짜가 있습니다: {detail}")
```

같은 함수의
```python
    if LUNCH in by_key(active) and shift_defs(active):
        out.warnings += _fill_lunch(period, dates, skip, shift_defs(active)[0])
```
를 바꾼다:
```python
    out.warnings[:0] = warnings
    if LUNCH in by_key(active) and shift_defs(active):
        out.warnings += _fill_lunch(period, dates, skip, shift_defs(active)[0])
```

`def _fill_lunch(` 바로 앞에:
```python
def _days(days) -> str:
    return ", ".join(f"{d.month}/{d.day}" for d in days)


```
그리고 `_fill_lunch` 끝 줄을 같은 도우미로:
```python
    return [f"점심당번을 채우지 못한 날({early.name} 출근 없음): {_days(empty)}"]
```

- [ ] **Step 6: 입력 오류 문구(`services/collect.py`)**

import:
```python
from ..models import Commute, Department, Period, User, step_label
```
`_require_input` 의 마지막 두 줄을:
```python
    if period.status != Period.Status.COLLECTING:
        raise DutyError(f"{step_label(period.board, Period.Status.COLLECTING)}인 회차가 아닙니다.")  # 취합 중 / 입력 중
```

- [ ] **Step 7: 기존 테스트 준비 코드를 맞춘다(기계적 변경)**

`tests/test_boards_generate.py` 의 운영팀(직접 입력) 회차는 이제 마감에서 확정할 수 없다. 준비 함수의 기본 상태만 바꾼다(단언 그대로):
```python
def ops_period(board, member, status=S.COLLECTING):  # 직접 입력 근무표는 입력 중에서 확정한다(3단계)
```

- [ ] **Step 8: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_direct_periods.py tests/test_boards_generate.py tests/test_period_lifecycle.py tests/test_views_collect.py`
Expected: 모두 PASS

Run: `.venv/bin/pytest -W error -q`
Expected: 모두 PASS(사본 기준 **1140 passed**), 경고 0개

- [ ] **Step 9: 커밋**

```bash
git add duty/models.py duty/services/periods.py duty/services/generate.py duty/services/collect.py tests/test_direct_periods.py tests/test_boards_generate.py
git commit -m "feat: 직접 입력 근무표 회차 흐름(바로 입력 중, 입력 중 기간 수정, 빈 평일은 확정 경고, 확정 취소는 입력 중으로만)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 2: 직접 입력 회차 화면

**Files:**
- Modify: `duty/views/manage.py` — models import, `period_list` 의 회차 목록(`select_related`), `_render_detail`
- Modify: `duty/templates/duty/period_detail.html`, `duty/templates/duty/periods.html`, `duty/templates/duty/collect_table.html`
- Modify: `duty/views/collect.py` — models import, `index` 의 render(`waiting`), `_render_table` 컨텍스트(`direct`)
- Modify: `duty/templates/duty/collect_index.html` — 빈 목록 문구
- Modify: `duty/services/publish.py` — models import, `_validate` 의 상태 오류 문구
- Test: `tests/test_views_direct.py`(새 파일)

**Interfaces:**
- Consumes(Task 1): `DIRECT_STEPS`, `step_label`, `Period.status_label`, `periods.empty_days`, `InputMode`
- Produces:
  - `_render_detail` 컨텍스트에 `direct: bool`, `steps`(직접 입력이면 `DIRECT_STEPS`), `movable`(직접 입력이면 `[]`), `events: list[tuple[PeriodEvent, str, str]]`(기록, 전 상태 화면 이름 또는 `""`, 후 상태 화면 이름), `input_depts`(직접 입력이면 그 근무표 부서, `order`·`code` 순), `empty_days`(직접 입력 입력 중일 때만)
  - `_render_detail` 컨텍스트에 `generated_label`(= `step_label(board, GENERATED)`: 생성됨 / 확정) — 배포 취소 확인창·설명에 쓴다
  - `collect_table.html` 컨텍스트에 `direct: bool`(Task 3 도 쓴다), `collect_index.html` 컨텍스트에 `waiting: str`(관리하는 부서들 근무표의 취합 중 단계 이름, 겹치면 한 번, "·"로 이음)
  - `publish._validate`: 직접 입력이면 `DutyError("확정한 회차만 배포할 수 있습니다.")`, 아니면 지금 문구
  - 화면: 직접 입력 입력 중 = 기간 폼 + [표 입력](부서마다) + [확정](확인창) + ⚠ 빈 평일 줄. 확정 = [배포…] + [확정 취소](`period_move`, `to=collecting`, 확인창). 입력 현황·편차 표·생성 방식·"다른 상태로 옮기기"는 숨김. 진한 버튼은 하나: 빈 평일이 있으면 [표 입력], 없으면 [확정].

- [ ] **Step 1: 실패 테스트를 쓴다**

`tests/test_views_direct.py`(새 파일):
```python
"""직접 입력 근무표의 회차 화면(설계 7절): 입력 중 → 확정 → 배포됨, [표 입력]·[확정]·[확정 취소], 확정 경고. 이름은 모두 가상."""
from datetime import date, time

import pytest

from duty.models import Board, BoardShift, Commute, Department, Period, User

S = Period.Status
MON, FRI = date(2026, 11, 16), date(2026, 11, 20)


@pytest.fixture
def ops(it_board, admin_user):
    """가짜 직접 입력 근무표 '운영팀'(근무조 셋 + 점심당번, 부서 하나). admin_user 는 IT·운영팀 둘 다 관리한다."""
    board = Board.objects.create(code="ops", name="운영팀", input_mode=Board.InputMode.DIRECT)
    for key, name, h in (("dawn", "이른", 7), ("normal", "가운데", 9), ("dinner", "늦은", 11)):
        BoardShift.objects.create(board=board, key=key, name=name, start=time(h, 30), end=time(h + 9, 30))
    BoardShift.objects.create(board=board, key="lunch", name="점심당번")
    dept = Department.objects.create(code="OPS", name="운영", shifts="dawn,normal,dinner", board=board)
    board.admin_group.user_set.add(admin_user)
    return board, dept


def ops_member(dept, name):
    return User.objects.create_user(f"OPS{User.objects.count() + 1:03d}", password=None, name=name,
                                    department=dept, part="", type="직원")


def fill(p, member, days):
    for x in days:
        Commute.objects.create(period=p, date=x, member=member, shift="dawn")


def test_create_direct_period_from_list(admin_client_ok, ops):
    r = admin_client_ok.post("/periods/", {"board": ops[0].pk, "name": "운영 11월",
                                           "start_date": "2026-11-16", "end_date": "2026-11-20"})
    p = Period.objects.get(name="운영 11월")
    assert r.status_code == 302 and p.status == S.COLLECTING
    body = admin_client_ok.get("/periods/").content.decode()
    assert '<span class="pill st-collecting">입력 중</span>' in body


def test_input_page_shows_direct_steps_and_buttons(admin_client_ok, ops):
    board, dept = ops
    p = Period.objects.create(board=board, name="p", start_date=MON, end_date=FRI, status=S.COLLECTING)
    fill(p, ops_member(dept, "가상가"), p.dates()[:3])
    body = admin_client_ok.get(f"/periods/{p.pk}/").content.decode()
    assert "<small>(입력 중)</small>" in body
    assert body.index(">입력 중<") < body.index(">확정<") < body.index(">배포됨<")
    assert "취합 중" not in body and "작성 중" not in body and "마감" not in body
    assert f'href="/collect/{p.pk}/OPS/">표 입력</a>' in body
    assert f'action="/periods/{p.pk}/action/generate/"' in body and ">확정</button>" in body
    assert 'name="start_date"' in body  # 입력 중에도 기간을 고친다
    assert "⚠ 아직 입력하지 않은 평일: 11/19, 11/20." in body
    assert "부서별 입력 현황" not in body and "생성 방식" not in body and "다른 상태로 옮기기" not in body


def test_confirmed_page_shows_publish_and_cancel(admin_client_ok, ops):
    board, dept = ops
    p = Period.objects.create(board=board, name="p", start_date=MON, end_date=FRI, status=S.GENERATED)
    body = admin_client_ok.get(f"/periods/{p.pk}/").content.decode()
    assert "<small>(확정)</small>" in body and "배포…</a>" in body
    assert f'action="/periods/{p.pk}/move/"' in body and 'name="to" value="collecting"' in body and "확정 취소" in body
    assert 'name="start_date"' not in body and ">표 입력</a>" not in body


def test_confirm_shows_empty_day_warning(admin_client_ok, ops):
    board, dept = ops
    p = Period.objects.create(board=board, name="p", start_date=MON, end_date=FRI, status=S.COLLECTING)
    fill(p, ops_member(dept, "가상가"), p.dates()[:4])
    r = admin_client_ok.post(f"/periods/{p.pk}/action/generate/", follow=True)
    body = r.content.decode()
    assert "입력하지 않은 평일이 있습니다(그날은 근무자가 없습니다): 11/20" in body
    assert "<small>(확정)</small>" in body
    assert "확정 → 확정" not in body and "입력 중 → 확정" in body  # 상태 기록도 화면 이름으로


def test_cancel_confirm_returns_to_input(admin_client_ok, ops):
    board, dept = ops
    p = Period.objects.create(board=board, name="p", start_date=MON, end_date=FRI, status=S.GENERATED)
    admin_client_ok.post(f"/periods/{p.pk}/move/", {"to": "collecting"})
    p.refresh_from_db()
    assert p.status == S.COLLECTING


def test_input_table_links_back_and_names_closed_state(admin_client_ok, ops):
    board, dept = ops
    p = Period.objects.create(board=board, name="p", start_date=MON, end_date=FRI, status=S.GENERATED)
    body = admin_client_ok.get(f"/collect/{p.pk}/OPS/").content.decode()
    assert f'href="/periods/{p.pk}/"' in body and "입력 중인 회차가 아니라 저장할 수 없습니다" in body


def test_collect_period_page_unchanged(admin_client_ok, it_board):
    p = Period.objects.create(board=it_board, name="p", start_date=MON, end_date=FRI, status=S.COLLECTING)
    body = admin_client_ok.get(f"/periods/{p.pk}/").content.decode()
    assert "<small>(취합 중)</small>" in body and "취합 마감" in body and "부서별 입력 현황" in body
    assert ">표 입력</a>" not in body and ">확정</button>" not in body


def test_published_page_names_confirmed_state_in_unpublish(admin_client_ok, ops):
    board, dept = ops
    from duty.services.publish import publish
    p = Period.objects.create(board=board, name="p", start_date=MON, end_date=FRI, status=S.GENERATED)
    publish(p, MON)
    body = admin_client_ok.get(f"/periods/{p.pk}/").content.decode()
    assert "<small>(배포됨)</small>" in body
    assert "이 회차를 확정으로 되돌릴까요?" in body and "이 회차는 확정으로 돌아갑니다" in body and "생성됨" not in body


def test_publish_error_names_confirm(ops):
    from duty.errors import DutyError
    from duty.services.publish import publish
    p = Period.objects.create(board=ops[0], name="p", start_date=MON, end_date=FRI, status=S.COLLECTING)
    with pytest.raises(DutyError, match="확정한 회차만 배포할 수 있습니다"):
        publish(p, MON)


def test_empty_input_list_names_input_state(client, ops, admin_user, it_board):
    it_board.admin_group.user_set.remove(admin_user)  # 운영팀(직접 입력)만 관리
    client.force_login(admin_user)
    assert "<p>입력 중인 회차가 없습니다.</p>" in client.get("/collect/").content.decode()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_views_direct.py`
Expected: `8 failed, 2 passed`(화면·문구가 아직 "취합 중"·[취합 마감]·"생성됨"·"생성이 끝난"이다. 확정 취소 POST 와 IT 화면 테스트는 이미 통과)

- [ ] **Step 3: 회차 화면 컨텍스트(`views/manage.py`)**

models import 를 바꾼다:
```python
from ..models import DIRECT_STEPS, Board, ChangeLog, Department, InputMode, Period, step_label
```

`period_list` 의 render 컨텍스트에서 회차 목록이 근무표를 한 번에 읽게(`status_label` 이 근무표를 본다):
```python
        "periods": Period.objects.filter(board__in=mine).select_related("board").order_by("-start_date"), "boards": mine,
```

`_render_detail` 의 앞부분
```python
def _render_detail(request, period, failures):
    counts, spread, reached = stats.period_duty_counts(period)
    slot_names = [x.name for x in slot_defs(boards.active_defs(period.board))]  # generator 의 칸 번호 = 켜진 관제 정의 순서
    return render(request, "duty/period_detail.html", {
        "period": period, "S": Period.Status,
        "steps": Period.Status.choices, "movable": [] if period.status == Period.Status.PUBLISHED
        else [(s, Period.Status(s).label) for s in periods.MOVABLE if s != period.status],
        "events": period.events.select_related("by"),
```
를 바꾼다(그 아래 `"undo": …` 줄부터는 그대로):
```python
def _render_detail(request, period, failures):
    counts, spread, reached = stats.period_duty_counts(period)
    slot_names = [x.name for x in slot_defs(boards.active_defs(period.board))]  # generator 의 칸 번호 = 켜진 관제 정의 순서
    direct = period.board.input_mode == InputMode.DIRECT  # 직접 입력: 입력 중 → 확정 → 배포됨(설계 6.1·7)
    S = Period.Status
    return render(request, "duty/period_detail.html", {
        "period": period, "S": S, "direct": direct, "generated_label": step_label(period.board, S.GENERATED),
        "steps": DIRECT_STEPS if direct else S.choices,
        "movable": [] if direct or period.status == S.PUBLISHED  # 직접 입력은 [확정 취소] 하나로 되돌린다
        else [(s, S(s).label) for s in periods.MOVABLE if s != period.status],
        "events": [(e, e.from_status and step_label(period.board, e.from_status), step_label(period.board, e.to_status))
                   for e in period.events.select_related("by")],
        "input_depts": Department.objects.filter(board=period.board).order_by("order", "code") if direct else [],
        "empty_days": periods.empty_days(period) if direct and period.status == S.COLLECTING else [],
```

- [ ] **Step 4: 회차 화면 템플릿(`period_detail.html`)**

맨 위 세 줄
```html
<h3>{{ period.name }} <small>({{ period.get_status_display }})</small></h3>
<ol class="lifecycle">{% for code, label in steps %}<li><span{% if code == period.status %} class="now"{% endif %}>{{ label }}</span></li>{% endfor %}</ol>
{% if period.status == S.DRAFT %}
```
을 바꾼다:
```html
<h3>{{ period.name }} <small>({{ period.status_label }})</small></h3>
<ol class="lifecycle">{% for code, label in steps %}<li><span{% if code == period.status %} class="now"{% endif %}>{{ label }}</span></li>{% endfor %}</ol>
{% if period.status == S.DRAFT or direct and period.status == S.COLLECTING %}
```

```html
<div class="actions">
  {% if period.status == S.DRAFT %}
```
를 바꾼다(그 아래 `<form … 'open' …>취합 열기` 줄부터 IT 갈래는 그대로, `{% if %}` 가 `{% elif %}` 로 이어진다):
```html
<div class="actions">
  {% if direct %}
  {% if period.status == S.COLLECTING %}
  {% for d in input_depts %}<a role="button"{% if not empty_days %} class="outline"{% endif %} href="{% url 'collect_table' period.pk d.code %}">표 입력{% if input_depts|length > 1 %} · {{ d.name }}{% endif %}</a>{% endfor %}
  <form method="post" action="{% url 'period_action' period.pk 'generate' %}" onsubmit="return confirm('확정할까요? 확정하면 배포할 수 있고, 표를 고치려면 [확정 취소]를 누릅니다.')">{% csrf_token %}<button{% if empty_days %} class="outline"{% endif %}>확정</button></form>
  {% elif period.status == S.GENERATED %}
  <a role="button" href="{% url 'period_publish' period.pk %}">배포…</a>
  <form method="post" action="{% url 'period_move' period.pk %}" onsubmit="return confirm('확정을 취소하고 입력 중으로 돌아갈까요? 출근표는 그대로 남습니다.')">{% csrf_token %}<input type="hidden" name="to" value="{{ S.COLLECTING }}"><button class="outline secondary">확정 취소</button></form>
  {% endif %}
  {% elif period.status == S.DRAFT %}
```

```html
{% if missing and period.status != S.DRAFT and period.status != S.PUBLISHED %}<p class="note">
```
로 시작하는 줄을 바꾼다(줄 끝까지 같은 글, 앞에 한 줄 더하고 `not direct` 조건만 붙인다):
```html
{% if empty_days %}<p class="note warn">⚠ 아직 입력하지 않은 평일: {% for d in empty_days %}{{ d|date:"n/j" }}{% if not forloop.last %}, {% endif %}{% endfor %}. 확정은 할 수 있지만 그날은 근무자가 없습니다.</p>{% endif %}
{% if missing and not direct and period.status != S.DRAFT and period.status != S.PUBLISHED %}<p class="note">출근표가 비어 있는 부서가 있어 아직 생성할 수 없습니다(아래 입력 현황).</p>{% endif %}
```

입력 현황을 감싼다:
```html
{% if not direct %}
<h4>부서별 입력 현황</h4>
<ul>{% for code, p in progress.items %}<li>{{ code }}: {{ p.0 }} / {{ p.1 }}일
  {% if code in missing %}<small>(비어 있는 날짜 있음)</small>{% endif %}</li>{% endfor %}</ul>
{% endif %}
```

편차 표 조건 `{% if counts %}` → `{% if counts and not direct %}`.

배포 취소 상자의 두 곳(확인창과 설명)에서 "생성됨"을 화면 이름으로:
```html
onsubmit="return confirm('배포를 취소하고 이 회차를 {{ generated_label }}으로 되돌릴까요?')">
```
```html
이 회차는 {{ generated_label }}으로 돌아갑니다(근무표에서 빠집니다).
```
(바꾸기 전 글자는 각각 `onsubmit="return confirm('배포를 취소하고 이 회차를 생성됨으로 되돌릴까요?')">` 와 `이 회차는 생성됨으로 돌아갑니다(근무표에서 빠집니다).`)

상태 기록 표의 `<tbody>…</tbody>` 두 줄을:
```html
<tbody>{% for e, frm, to in events %}<tr><td class="nw">{{ e.at|date:"Y-m-d H:i" }}</td><td class="nw">{% if e.by %}{{ e.by.name|default:e.by.username }}{% else %}-{% endif %}</td>
  <td class="nw">{% if frm %}{{ frm }} → {% endif %}{{ to }}</td><td>{{ e.note }}</td></tr>{% endfor %}</tbody></table></div>
```

`<style>` 안 `p.note { … }` 줄 뒤에:
```css
  p.note.warn { opacity: 1; padding: .5rem .8rem; border-left: 4px solid #c77700; background: rgba(199, 119, 0, .1); }
```

맨 아래 `<dialog id="gen-help">…</dialog>` 를 `{% if not direct %}` … `{% endif %}` 로 감싼다(`{% endblock %}` 바로 앞에 `{% endif %}`).

- [ ] **Step 5: 회차 목록과 입력 표 문구**

`periods.html`: `{{ p.get_status_display }}` → `{{ p.status_label }}`.

`views/collect.py` — import `from ..models import Board, Department, Period, User, step_label`, `index` 의 마지막 줄
```python
    return render(request, "duty/collect_index.html", {"items": items})
```
을:
```python
    # 목록이 비었을 때 문구: 근무표의 화면 단계 이름(취합 중 / 입력 중), 겹치는 이름은 한 번만
    waiting = "·".join(dict.fromkeys(step_label(d.board, Period.Status.COLLECTING) for d in depts))
    return render(request, "duty/collect_index.html", {"items": items, "waiting": waiting})
```
그리고 `_render_table` 컨텍스트의
```python
        "is_open": period.status == Period.Status.COLLECTING,
```
를:
```python
        "is_open": period.status == Period.Status.COLLECTING, "direct": period.board.input_mode == Board.InputMode.DIRECT,
```

`collect_table.html` 의
```html
{% if not is_open %}<p>취합이 열려 있지 않아 저장할 수 없습니다.</p>{% endif %}
```
를:
```html
{% if direct %}<p><a href="{% url 'period_detail' period.pk %}">← 회차 화면으로(확정·배포)</a></p>{% endif %}
{% if not is_open %}<p>{% if direct %}입력 중인 회차가 아니라{% else %}취합이 열려 있지 않아{% endif %} 저장할 수 없습니다.</p>{% endif %}
```

`collect_index.html` 의
```html
{% empty %}<p>취합 중인 회차가 없습니다.</p>{% endfor %}
```
를:
```html
{% empty %}<p>{{ waiting }}인 회차가 없습니다.</p>{% endfor %}
```

`services/publish.py` — import 를 `from ..models import ChangeLog, Commute, DutyAssignment, InputMode, Period, PeriodEvent, User` 로, `_validate` 의
```python
        raise DutyError("생성이 끝난 회차만 배포할 수 있습니다.")
```
를:
```python
        raise DutyError("확정한 회차만 배포할 수 있습니다." if period.board.input_mode == InputMode.DIRECT
                        else "생성이 끝난 회차만 배포할 수 있습니다.")
```

- [ ] **Step 6: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_views_direct.py tests/test_views_manage.py tests/test_views_collect.py tests/test_boards_generate.py tests/test_publish.py`
Expected: 모두 PASS

Run: `.venv/bin/pytest -W error -q`
Expected: 모두 PASS(사본 기준 **1150 passed**), 경고 0개

- [ ] **Step 7: 브라우저로 확인한다(PC 1400px·휴대폰 390px·아주 크게·다크 모드)**

"브라우저 확인 준비"대로 띄우고 `admin` 으로:
- [회차] 목록에 "이번 2주"가 **입력 중** 알약으로, "지난 2주"가 **배포됨**으로 보인다. IT 회차는 지금 글자 그대로.
- "이번 2주": 단계 띠 입력 중 → 확정 → 배포됨, 기간 폼, 진한 [표 입력]과 테두리 [확정], ⚠ 빈 평일 줄(모든 평일). [표 입력] → 입력 표 위 "← 회차 화면으로" 링크.
- 표에 한두 날만 넣고 저장 → 회차 화면에서 [확정] → 확인창 → 경고 메시지 두 줄(빈 평일, 점심당번 못 채운 날). 단계 "확정", [배포…]·[확정 취소]. [확정 취소] → 확인창 → 입력 중으로 돌아옴. 상태 기록이 "입력 중 → 확정"처럼 보인다.
- "지난 2주"(배포됨): 배포 취소 상자가 "이 회차는 확정으로 돌아갑니다", 확인창이 "확정으로 되돌릴까요?". [출근표 입력] 메뉴에서 회차가 없을 때 "입력 중인 회차가 없습니다"(admin 은 IT 도 관리하므로 "취합 중·입력 중인 회차가 없습니다"로 보일 수 있다).
- 390px·아주 크게, 그리고 다크 모드에서 버튼이 줄바꿈되고 ⚠ 줄·단계 띠 글씨가 읽힌다. 화면마다 콘솔 `document.documentElement.scrollWidth > innerWidth` 가 `false`.

끝나면 서버를 끄고 임시 폴더를 지운다.

- [ ] **Step 8: 커밋**

```bash
git add duty/views/manage.py duty/views/collect.py duty/services/publish.py duty/templates/duty/period_detail.html duty/templates/duty/periods.html duty/templates/duty/collect_table.html duty/templates/duty/collect_index.html tests/test_views_direct.py
git commit -m "feat: 직접 입력 회차 화면(입력 중·확정·배포됨 단계, 표 입력·확정·확정 취소, 빈 평일 경고)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 3: 입력 표의 [2주 전 기준으로 채우기]·[지난주와 같게]

**Files:**
- Modify: `duty/shifts.py` — 파일 끝(`two_week_rotation`, 순수)
- Modify: `duty/services/collect.py` — import, 파일 끝(`FILL_2W`·`FILL_1W`·`can_rotate`·`_base`·`fill_week`)
- Modify: `duty/views/collect.py` — import, `_render_table`(주 표시·바뀐 칸·채우기 컨텍스트), 새 `_posted`, `table()` 의 POST
- Modify: `duty/templates/duty/collect_table.html`
- Test: `tests/test_fill.py`(새 파일)

**Interfaces:**
- Consumes: Task 2 의 `direct` 컨텍스트, `collect.input_keys(dept) -> list[str]`, `shift_defs`, `boards.active_defs`·`skip_dates(period) -> set[date]`, `roster.published_days(board, start, end) -> list[Day]`(`Day.members[key] -> list[이름]`, `Day.reason(key, name) -> str`), `csv_io.split_reason(name) -> (이름, 사유)`, `CommuteTable = dict[date, dict[str, list[str]]]`
- Produces:
  - `duty.shifts.two_week_rotation(base: dict[date, dict[str, str]], names: list[str], keys: list[str]) -> dict[str, str]`(순수). `keys = [이른, 가운데, 늦은]`
  - `duty.services.collect.FILL_2W = "2w"`, `FILL_1W = "1w"`, `can_rotate(dept) -> bool`(입력 근무조 3개), `fill_week(period, dept, table: CommuteTable, day: date, how: str) -> CommuteTable`(저장 안 함. 오류는 `DutyError`: 직접 입력이 아님 / 알 수 없는 채우기 / 근무조 3개가 아님 / 회차 기간 밖의 주)
  - 화면: 직접 입력 입력 중 회차의 입력 표에 주마다 머리 줄(`<tr class="week">`, 행의 `week_start` = 그 주 월요일. "11/16 주", 버튼 `name="fill" value="2w:2026-11-16"`·`"1w:…"` — 회차가 수요일에 시작해도 월요일). 채운 결과는 바뀐 칸에 `class="filled"`, 위에 "N칸을 채웠습니다(색칠한 칸). 아직 저장하지 않았습니다. …". 폼 맨 앞에 화면 밖 `<button class="enter-save">표 저장</button>`.

- [ ] **Step 1: 실패 테스트를 쓴다**

`tests/test_fill.py`(새 파일):
```python
"""입력 표의 [2주 전 기준으로 채우기]·[지난주와 같게](설계 6.2). 이름은 모두 가상."""
from datetime import date, time

import pytest

from duty.errors import DutyError
from duty.models import Board, BoardShift, Commute, Department, Holiday, Period, User
from duty.services import collect
from duty.shifts import two_week_rotation

S = Period.Status
KEYS = ["dawn", "normal", "dinner"]  # 이른·가운데·늦은


def d(m, day):
    return date(2026, m, day)


# ── 순수 함수: 대표 근무조와 맞바꾸기 ──

def test_rotation_swaps_early_and_late():
    base = {d(11, 2): {"가": "dawn", "나": "dinner", "다": "normal"}, d(11, 3): {"가": "dawn", "나": "dinner"}}
    assert two_week_rotation(base, ["가", "나", "다", "라"], KEYS) == {
        "가": "dinner", "나": "dawn", "다": "normal", "라": "normal"}  # 2주 전 근무가 없던 라는 가운데


def test_rotation_uses_most_frequent_then_first_seen():
    base = {d(11, 2): {"가": "normal", "나": "dinner"}, d(11, 3): {"가": "dawn", "나": "dawn"},
            d(11, 4): {"가": "dawn"}}
    out = two_week_rotation(base, ["가", "나"], KEYS)
    assert out["가"] == "dinner"  # dawn 2번 > normal 1번
    assert out["나"] == "dawn"  # dinner·dawn 1번씩 → 먼저 나온 dinner


# ── 서비스 ──

@pytest.fixture
def ops(it_board, fixed_today):
    """가짜 직접 입력 근무표 '운영팀'(근무조 셋, 부서 하나)과 사람들.
    11/2~11/13 배포됨, 11/16~12/4 입력 중(11/18 휴장일). 가상마는 퇴사, 가상라는 새로 왔다."""
    fixed_today(d(11, 1))
    board = Board.objects.create(code="ops", name="운영팀", input_mode=Board.InputMode.DIRECT)
    for key, name, h in (("dawn", "이른", 7), ("normal", "가운데", 9), ("dinner", "늦은", 11)):
        BoardShift.objects.create(board=board, key=key, name=name, start=time(h, 30), end=time(h + 9, 30))
    dept = Department.objects.create(code="OPS", name="운영", shifts="dawn,normal,dinner", board=board)
    people = {n: User.objects.create_user(f"OPS{i}", password=None, name=n, department=dept, part="", type="직원")
              for i, n in enumerate(["가상가", "가상나", "가상다", "가상라", "가상마", "가상바"])}
    people["가상마"].is_active = False
    people["가상마"].save()
    old = Period.objects.create(board=board, name="지난", start_date=d(11, 2), end_date=d(11, 13),
                                status=S.PUBLISHED, overwrite_from=d(11, 2))

    def put(day, name, shift, reason=""):
        Commute.objects.create(period=old, date=day, member=people[name], shift=shift, reason=reason)

    for day in (2, 3, 4, 5, 6):  # 2주 전 주
        put(d(11, day), "가상가", "dawn")
        put(d(11, day), "가상나", "dinner")
        put(d(11, day), "가상다", "normal" if day < 5 else "dawn")  # normal 3번 > dawn 2번
        put(d(11, day), "가상마", "dawn")  # 퇴사자: 넣지 않는다
        put(d(11, day), "가상바", "dawn", "휴가")  # 근무로 친 날이 없다 → 가운데
    put(d(11, 9), "가상가", "dinner", "휴가")  # 지난주
    put(d(11, 9), "가상나", "dawn")
    put(d(11, 9), "가상다", "normal")
    put(d(11, 11), "가상나", "dawn")  # 11/18(휴장일)로 옮겨질 줄
    now = Period.objects.create(board=board, name="이번", start_date=d(11, 16), end_date=d(12, 4), status=S.COLLECTING)
    Holiday.objects.create(date=d(11, 18), name="가상휴일")
    return now, dept


def test_two_weeks_ago_fills_that_week_only(ops):
    p, dept = ops
    table = {d(11, 23): {"dawn": ["가상가"]}}  # 다른 주는 그대로
    out = collect.fill_week(p, dept, table, d(11, 19), collect.FILL_2W)
    week = {"dawn": ["가상나"], "normal": ["가상다", "가상라", "가상바"], "dinner": ["가상가"]}
    assert out == {d(11, 16): week, d(11, 17): week, d(11, 19): week, d(11, 20): week, d(11, 23): {"dawn": ["가상가"]}}
    assert Commute.objects.filter(period=p).count() == 0  # 저장하지 않는다


def test_two_weeks_ago_inside_period_reads_screen_table(ops):
    p, dept = ops
    table = {d(11, 16): {"dawn": ["가상다"], "dinner": ["가상가(교육)"]},
             d(11, 17): {"dawn": ["가상다"], "dinner": ["가상가"]}}  # 아직 저장하지 않은 화면의 표
    out = collect.fill_week(p, dept, table, d(11, 30), collect.FILL_2W)
    assert out[d(11, 30)] == {"dawn": ["가상가"], "normal": ["가상나", "가상라", "가상바"], "dinner": ["가상다"]}
    assert out[d(11, 16)] == table[d(11, 16)]


def test_same_as_last_week_copies_weekday_without_reason(ops):
    p, dept = ops
    out = collect.fill_week(p, dept, {d(11, 17): {"dawn": ["가상라"]}}, d(11, 16), collect.FILL_1W)
    assert out == {d(11, 16): {"dawn": ["가상나"], "normal": ["가상다"], "dinner": ["가상가"]}}  # 11/17 은 지난주가 비어 비움, 11/18 은 휴장일


def test_fill_errors(ops, it_board):
    p, dept = ops
    with pytest.raises(DutyError, match="알 수 없는 채우기"):
        collect.fill_week(p, dept, {}, d(11, 16), "3w")
    with pytest.raises(DutyError, match="회차 기간 밖"):
        collect.fill_week(p, dept, {}, d(12, 7), collect.FILL_1W)
    dept.shifts = "dawn,dinner"
    dept.save()
    with pytest.raises(DutyError, match="근무조가 3개일 때만"):
        collect.fill_week(p, dept, {}, d(11, 16), collect.FILL_2W)
    it = Period.objects.create(board=it_board, name="it", start_date=d(11, 16), end_date=d(11, 20), status=S.COLLECTING)
    mems = Department.objects.create(code="MEMS", name="매칭엔진실", shifts="dawn,normal,dinner", board=it_board)
    with pytest.raises(DutyError, match="직접 입력 근무표에서만"):
        collect.fill_week(it, mems, {}, d(11, 16), collect.FILL_1W)


# ── 화면 ──

@pytest.fixture
def ops_admin(client, ops, admin_user):
    ops[1].board.admin_group.user_set.add(admin_user)
    client.force_login(admin_user)
    return client


def test_buttons_per_week_and_enter_saves(ops_admin, ops):
    p, _ = ops
    body = ops_admin.get(f"/collect/{p.pk}/OPS/").content.decode()
    assert body.count('name="fill" value="2w:') == 3 and body.count('name="fill" value="1w:') == 3
    assert "<strong>11/16 주</strong>" in body and 'value="2w:2026-11-30"' in body
    assert body.index('class="enter-save"') < body.index('name="fill"')  # 칸에서 Enter = 저장


def test_two_weeks_button_needs_three_shifts(ops_admin, ops):
    p, dept = ops
    dept.shifts = "dawn,dinner"
    dept.save()
    body = ops_admin.get(f"/collect/{p.pk}/OPS/").content.decode()
    assert 'value="2w:' not in body and 'value="1w:2026-11-16"' in body


def test_fill_post_draws_without_saving(ops_admin, ops):
    p, _ = ops
    r = ops_admin.post(f"/collect/{p.pk}/OPS/", {"fill": "2w:2026-11-16", "c_2026-11-23_dawn": "가상가"})
    body = r.content.decode()
    assert r.status_code == 200 and Commute.objects.filter(period=p).count() == 0
    assert 'name="c_2026-11-16_dawn" value="가상나" class="filled"' in body
    assert 'name="c_2026-11-23_dawn" value="가상가" ' in body  # 다른 주는 화면 값 그대로, 색칠 없음
    assert "12칸을 채웠습니다(색칠한 칸). 아직 저장하지 않았습니다." in body  # 4일 × 3칸(11/18 휴장일)


def test_no_fill_buttons_on_collect_board_or_closed_period(client, admin_user, it_board, ops):
    p, _ = ops
    p.status = S.GENERATED
    p.save()
    ops[1].board.admin_group.user_set.add(admin_user)
    Department.objects.create(code="MEMS", name="매칭엔진실", shifts="dawn,normal,dinner", board=it_board)
    it = Period.objects.create(board=it_board, name="it", start_date=d(11, 16), end_date=d(11, 20), status=S.COLLECTING)
    client.force_login(admin_user)
    assert 'name="fill"' not in client.get(f"/collect/{it.pk}/MEMS/").content.decode()
    assert 'name="fill"' not in client.get(f"/collect/{p.pk}/OPS/").content.decode()


def test_week_header_uses_monday_when_period_starts_midweek(ops_admin, ops):
    p, _ = ops
    p.start_date = d(11, 18)  # 수요일에 시작
    p.save()
    body = ops_admin.get(f"/collect/{p.pk}/OPS/").content.decode()
    assert "<strong>11/16 주</strong>" in body and 'value="2w:2026-11-16"' in body and 'value="1w:2026-11-16"' in body
    assert body.count('name="fill" value="1w:') == 3  # 11/16·11/23·11/30 주
    r = ops_admin.post(f"/collect/{p.pk}/OPS/", {"fill": "1w:2026-11-16"})
    assert 'name="c_2026-11-18_dawn"' in r.content.decode()  # 월·화는 회차 밖이라 줄이 없다
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_fill.py`
Expected: 수집 오류 `ImportError: cannot import name 'two_week_rotation' from 'duty.shifts'`

- [ ] **Step 3: 순수 함수(`shifts.py` 끝)**

```python


def two_week_rotation(base: dict[date, dict[str, str]], names: list[str], keys: list[str]) -> dict[str, str]:
    """[2주 전 기준으로 채우기](설계 6.2): 사람마다 이번 주에 넣을 근무조 {이름: 키}.
    keys = [이른, 가운데, 늦은] 근무조(시작 시각 순), base = 2주 전 그 주의 {날짜: {이름: 근무조}}(근무로 친 날만).
    대표 근무조 = 가장 많이 나온 근무조, 같으면 그 주에 먼저 나온 것(한 사람은 하루 한 근무조라 첫 날이 겹치지 않아
    설계의 세 번째 기준 '시작 시각'까지 갈 일이 없다). 이른 → 늦은, 늦은 → 이른, 나머지·2주 전 근무가 없던 사람 → 가운데."""
    early, mid, late = keys
    out = {}
    for name in names:
        seen = [day[name] for _, day in sorted(base.items()) if name in day]
        top = max(map(seen.count, seen), default=0)
        rep = next((k for k in seen if seen.count(k) == top), None)
        out[name] = {early: late, late: early}.get(rep, mid)
    return out
```

Run: `.venv/bin/pytest -W error -q tests/test_fill.py -k rotation`
Expected: 2 passed

- [ ] **Step 4: 서비스(`services/collect.py`)**

파일 맨 위 import 를 바꾼다:
```python
from datetime import date, timedelta

from django.core.exceptions import PermissionDenied
```
```python
from ..models import Board, Commute, Department, Period, User, step_label
from ..shifts import SHIFT_KEYS, by_key, shift_defs, two_week_rotation, weekdays
from . import boards, roster
```

파일 끝에:
```python


FILL_2W, FILL_1W = "2w", "1w"  # [2주 전 기준으로 채우기], [지난주와 같게]


def can_rotate(dept: Department) -> bool:
    """[2주 전 기준으로 채우기]는 입력 근무조가 정확히 3개일 때만(이른·가운데·늦은 조가 정해지게, 설계 6.2)."""
    return len(input_keys(dept)) == 3


def _base(period: Period, table: CommuteTable, dates: list[date]) -> dict[date, dict[str, tuple[str, str]]]:
    """채우기의 기준 {날짜: {이름: (근무조, 사유)}}(설계 6.2): 회차 기간 안의 날은 지금 화면의 표(table, 저장 전 고친 것 포함),
    밖의 날은 배포된 근무표(그날의 주인 회차)."""
    inside = [d for d in dates if period.start_date <= d <= period.end_date]
    out = {d: {name: (k, why) for k, names in table.get(d, {}).items() for name, why in map(split_reason, names)}
           for d in inside}
    outside = [d for d in dates if d not in inside]
    if outside:
        for day in roster.published_days(period.board, min(outside), max(outside)):
            if day.date in outside:
                out[day.date] = {n: (k, day.reason(k, n)) for k in SHIFT_KEYS for n in day.members.get(k, [])}
    return out


def fill_week(period: Period, dept: Department, table: CommuteTable, day: date, how: str) -> CommuteTable:
    """[2주 전 기준으로 채우기](how=FILL_2W)·[지난주와 같게](FILL_1W)(설계 6.2): day 가 든 주(회차 기간 ∩ 월~금)의 줄만
    다시 채운 새 표를 돌려준다. 다른 주는 table 그대로. 저장하지 않는다(저장은 [표 저장]과 기존 검증).
    지금 재직하는 그 부서 사람만 넣고, 건너뛰는 날(휴장일·근무 없음)은 비운다."""
    _same_board(period, dept)
    if period.board.input_mode != Board.InputMode.DIRECT:
        raise DutyError("채우기는 직접 입력 근무표에서만 씁니다.")
    if how not in (FILL_2W, FILL_1W):
        raise DutyError("알 수 없는 채우기입니다.")
    if how == FILL_2W and not can_rotate(dept):
        raise DutyError("2주 전 기준으로 채우기는 근무조가 3개일 때만 씁니다.")
    monday = day - timedelta(days=day.weekday())
    week = [d for d in period.dates() if monday <= d <= monday + timedelta(days=4)]
    if not week:
        raise DutyError("회차 기간 밖의 주입니다.")
    keys = input_keys(dept)
    names = list(User.objects.roster().filter(department=dept).order_by("name").values_list("name", flat=True))
    if how == FILL_2W:
        base = _base(period, table, weekdays(monday - timedelta(days=14), monday - timedelta(days=10)))
        counted = {d: {n: k for n, (k, why) in rows.items() if not why} for d, rows in base.items()}  # 근무로 친 날만
        order = [x.key for x in shift_defs(boards.active_defs(dept.board)) if x.key in keys]  # 시작 시각 순
        picks = two_week_rotation(counted, names, order)
        plan = {d: picks for d in week}
    else:  # 지난주 같은 요일을 그대로(사유는 옮기지 않는다)
        base = _base(period, table, [d - timedelta(days=7) for d in week])
        plan = {d: {n: k for n, (k, _) in base.get(d - timedelta(days=7), {}).items()} for d in week}
    skip = boards.skip_dates(period)
    out = {d: v for d, v in table.items() if d not in week}
    for d in week:
        row = {k: [n for n in names if plan[d].get(n) == k] for k in keys}
        if d not in skip and any(row.values()):
            out[d] = row
    return out
```

Run: `.venv/bin/pytest -W error -q tests/test_fill.py -k "rotation or fills or inside or same_as or errors"`
Expected: 6 passed(화면 테스트 5개는 아직 FAIL)

- [ ] **Step 5: 화면(`views/collect.py`)**

import 맨 위에:
```python
from datetime import date, timedelta

```

`_render_table` 을 통째로 바꾸고 바로 뒤에 `_posted` 를 더한다:
```python
def _render_table(request, period, dept, table, errors, before=None):
    """before: 채우기 전 표(채우기 결과를 그릴 때만). 그것과 다른 칸을 색칠한다."""
    keys = collect.input_keys(dept)
    today, admin = perms.today(), perms.is_board_admin(request.user, period.board)
    skip = boards.skip_reasons(period)  # 건너뛰는 날: 칸을 잠그고(disabled 라 보내지 않는다) 까닭을 보인다
    rows, weeks = [], set()
    for d in period.dates():
        monday = d - timedelta(days=d.weekday())
        cells = [{"name": f"c_{d.isoformat()}_{k}", "value": ", ".join(table.get(d, {}).get(k, [])),
                  "changed": before is not None
                  and sorted(table.get(d, {}).get(k, [])) != sorted(before.get(d, {}).get(k, []))} for k in keys]
        rows.append({"date": d, "weekday": DAY_LABELS[d.weekday()], "locked": d < today and not admin,
                     "closed": skip.get(d, ""), "cells": cells,
                     "week_start": None if monday in weeks else monday})  # 그 주 첫 줄에만: 그 주 월요일(회차가 주 중간에 시작해도)
        weeks.add(monday)
    is_open = period.status == Period.Status.COLLECTING
    direct = period.board.input_mode == Board.InputMode.DIRECT
    return render(request, "duty/collect_table.html", {
        "period": period, "dept": dept, "rows": rows, "errors": errors,
        "shift_labels": list(collect.shift_names(dept).values()),
        "names": list(User.objects.roster().filter(department=dept).order_by("name").values_list("name", flat=True)),
        "is_open": is_open, "direct": direct, "ncols": len(keys) + 2,
        "show_fill": is_open and direct, "can_rotate": collect.can_rotate(dept),  # 채우기 버튼(설계 6.2): 직접 입력의 입력 중 회차만
        "filled": before is not None, "changed": sum(c["changed"] for r in rows for c in r["cells"]),
    }, status=400 if errors else 200)


def _posted(request, period, dept):
    posted = {}
    for d in period.dates():
        day = {k: split_names(request.POST.get(f"c_{d.isoformat()}_{k}", "")) for k in collect.input_keys(dept)}
        if any(day.values()):
            posted[d] = day
    return posted
```

`table()` 의 POST 앞부분
```python
    if request.method == "POST":
        posted = {}
        for d in period.dates():
            day = {k: split_names(request.POST.get(f"c_{d.isoformat()}_{k}", "")) for k in collect.input_keys(dept)}
            if any(day.values()):
                posted[d] = day
        try:
```
를 바꾼다(`try:` 아래 저장 갈래는 그대로):
```python
    if request.method == "POST":
        posted = _posted(request, period, dept)
        if request.POST.get("fill"):  # 채우기: 저장하지 않고 그 주를 채운 표를 그려 보여 주기만 한다
            how, _, raw = request.POST["fill"].partition(":")
            try:
                day = date.fromisoformat(raw)
            except ValueError:
                raise Http404
            try:
                filled = collect.fill_week(period, dept, posted, day, how)
            except DutyError as e:
                messages.error(request, str(e))
                return _render_table(request, period, dept, posted, [])
            return _render_table(request, period, dept, filled, [], before=posted)
        try:
```

- [ ] **Step 6: 화면(`collect_table.html`)**

```html
<form method="post">{% csrf_token %}
<div class="grid-wrap">
```
를 바꾼다:
```html
{% if filled %}<div class="msg warning" role="status">{% if changed %}{{ changed }}칸을 채웠습니다(색칠한 칸). 아직 저장하지 않았습니다. 확인하고 고친 뒤 [표 저장]을 누르세요.{% else %}바뀐 칸이 없습니다.{% endif %}</div>{% endif %}
<form method="post">{% csrf_token %}
{% if show_fill %}<button class="enter-save" tabindex="-1" aria-hidden="true">표 저장</button>{% endif %}{# 칸에서 Enter 를 누르면 채우기가 아니라 저장(첫 제출 버튼)이 눌리게 #}
<div class="grid-wrap">
```

```html
  <tbody>{% for r in rows %}
    <tr>
```
를 바꾼다(`<tr>` 뒤는 그대로):
```html
  <tbody>{% for r in rows %}
    {% if show_fill and r.week_start %}<tr class="week"><td colspan="{{ ncols }}"><strong>{{ r.week_start|date:"n/j" }} 주</strong>
      {% if can_rotate %}<button name="fill" value="2w:{{ r.week_start|date:'Y-m-d' }}" class="outline">2주 전 기준으로 채우기</button>{% endif %}
      <button name="fill" value="1w:{{ r.week_start|date:'Y-m-d' }}" class="outline">지난주와 같게</button></td></tr>{% endif %}
    <tr>
```

칸 입력 줄
```html
      {% for c in r.cells %}<td><input name="{{ c.name }}" value="{{ c.value }}" {% if r.closed %}disabled{% elif r.locked %}readonly{% endif %}></td>{% endfor %}
```
를:
```html
      {% for c in r.cells %}<td><input name="{{ c.name }}" value="{{ c.value }}"{% if c.changed %} class="filled"{% endif %} {% if r.closed %}disabled{% elif r.locked %}readonly{% endif %}></td>{% endfor %}
```

`<style>` 의 `.savebar button { … }` 줄 뒤에:
```css
  tr.week td { padding-top: 1rem; }
  tr.week button { width: auto; margin: .2rem .4rem .2rem 0; padding: .5rem 1rem; }
  table.roster td input.filled { background: rgba(199, 119, 0, .18); outline: 2px solid #c77700; }
  .enter-save { position: absolute; left: -9999px; width: 1px; height: 1px; overflow: hidden; }
```

- [ ] **Step 7: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_fill.py tests/test_views_collect.py tests/test_skip_days.py tests/test_reasons.py`
Expected: 모두 PASS

Run: `.venv/bin/pytest -W error -q`
Expected: 모두 PASS(사본 기준 **1161 passed**), 경고 0개

- [ ] **Step 8: 브라우저로 확인한다(PC 1400px·휴대폰 390px·아주 크게·다크 모드)**

"브라우저 확인 준비"대로 띄우고 `admin` 으로 [회차] → "이번 2주" → [표 입력]:
- 주마다 "M/D 주"(그 주 월요일) 줄에 [2주 전 기준으로 채우기]·[지난주와 같게]. 첫 주 [2주 전 기준으로 채우기] → 이른 조 ↔ 늦은 조가 바뀐 표, 바뀐 칸이 색칠되고 위에 "N칸을 채웠습니다 … 아직 저장하지 않았습니다". 다른 주에 미리 적어 둔 이름은 그대로.
- [지난주와 같게]는 지난주가 이 회차 밖이면 배포된 "지난 2주"의 같은 요일을 옮긴다.
- 칸에 커서를 두고 Enter → 저장된다("N명분을 저장했습니다"), 채우기가 눌리지 않는다.
- [표 저장] → 저장. 390px·아주 크게에서 버튼이 표 안에서 줄바꿈되고(표는 표 안에서만 가로 스크롤), 콘솔 `document.documentElement.scrollWidth > innerWidth` 가 `false`.
- 다크 모드에서 색칠한 칸(주황 테두리)과 채움 안내가 읽힌다.
- IT 회차의 입력 표(manager 계정)에는 버튼이 없다.

- [ ] **Step 9: 커밋**

```bash
git add duty/shifts.py duty/services/collect.py duty/views/collect.py duty/templates/duty/collect_table.html tests/test_fill.py
git commit -m "feat: 직접 입력 표의 2주 전 기준으로 채우기·지난주와 같게(저장 전 그 주만 그려 보임, 바뀐 칸 색칠)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 4: 그룹 화면

**Files:**
- Modify: `duty/perms.py` — import, `managed_departments` 앞(`kept_groups`)
- Create: `duty/services/groups.py`
- Modify: `duty/views/manage.py` — import, 파일 끝(`_about`, `groups`)
- Modify: `duty/urls.py` — `changes/` 줄 뒤
- Modify: `duty/context.py` — `관리` 메뉴 앞
- Create: `duty/templates/duty/groups.html`
- Test: `tests/test_groups.py`(새 파일)

**Interfaces:**
- Consumes: `GroupKeeper(group, user)`(related_name: `Group.keepers`), `Board.admin_group`(역방향 `group.admin_board`), `Department.input_group`(역방향 `group.input_department`)
- Produces:
  - `perms.kept_groups(user) -> QuerySet[Group]`: 내가 그룹 관리자인 그룹(익명은 빈 목록)
  - `duty.services.groups.add_member(by, group, member) -> None`, `remove_member(by, group, member) -> str`(근무표 관리 그룹이 비면 경고 문구, 아니면 `""`). 그룹 관리자가 아니면 `PermissionDenied`, 규칙 위반은 `DutyError`
  - 주소 `/groups/`(name `groups`): GET = 맡은 그룹 목록(아니면 403), POST `group`·`member`·`do=add|remove`(맡지 않은 그룹·없는 사람은 404) → `groups` 로 되돌아감
  - 메뉴 [그룹]: `perms.kept_groups(user).exists()` 일 때만, [관리] 앞

- [ ] **Step 1: 실패 테스트를 쓴다**

`tests/test_groups.py`(새 파일):
```python
"""그룹 화면(설계 7절): 그룹 관리자(GroupKeeper)가 맡은 그룹의 멤버를 넣고 뺀다. 이름은 모두 가상."""
import pytest
from django.core.exceptions import PermissionDenied

from duty.errors import DutyError
from duty.models import GroupKeeper
from duty.services import groups


@pytest.fixture
def keeper(make_member, it_board, depts):
    """IT 근무표 관리 그룹과 매칭엔진실 입력 그룹을 맡은 가상관리."""
    k = make_member("가상관리", user=True)
    GroupKeeper.objects.create(group=it_board.admin_group, user=k)
    GroupKeeper.objects.create(group=depts["MEMS"].input_group, user=k)
    return k


# ── 서비스 ──

def test_keeper_adds_and_removes(keeper, it_board, make_member):
    m = make_member("가상가")
    groups.add_member(keeper, it_board.admin_group, m)
    assert it_board.admin_group.user_set.filter(pk=m.pk).exists()
    assert groups.remove_member(keeper, it_board.admin_group, m) == "IT 당번표 근무표 관리자가 아무도 없습니다. 회차·배포를 할 사람이 없으니 다른 사람을 넣으세요."
    assert not it_board.admin_group.user_set.exists()


def test_no_warning_while_admins_remain_or_for_input_group(keeper, it_board, depts, admin_user, make_member):
    m = make_member("가상가")
    groups.add_member(keeper, it_board.admin_group, m)
    assert groups.remove_member(keeper, it_board.admin_group, m) == ""  # admin_user 가 남아 있다
    group = depts["MEMS"].input_group
    groups.add_member(keeper, group, m)
    assert groups.remove_member(keeper, group, m) == ""  # 입력 그룹은 비어도 경고하지 않는다


def test_only_keeper_of_that_group(keeper, depts, make_member):
    m = make_member("가상가")
    with pytest.raises(PermissionDenied):
        groups.add_member(keeper, depts["TMCH"].input_group, m)
    with pytest.raises(PermissionDenied):
        groups.add_member(m, depts["MEMS"].input_group, m)


def test_rules(keeper, depts, make_member):
    group = depts["MEMS"].input_group
    gone = make_member("가상퇴사", active=False)
    with pytest.raises(DutyError, match="퇴사한 사람은 넣을 수 없습니다"):
        groups.add_member(keeper, group, gone)
    m = make_member("가상가")
    groups.add_member(keeper, group, m)
    with pytest.raises(DutyError, match="이미 이 그룹에 있습니다"):
        groups.add_member(keeper, group, m)
    with pytest.raises(DutyError, match="이 그룹에 없는 사람입니다"):
        groups.remove_member(keeper, group, gone)


# ── 화면 ──

def test_menu_and_page_only_for_keepers(client, keeper, make_member):
    other = make_member("가상가", user=True)
    client.force_login(other)
    assert ">그룹</a>" not in client.get("/").content.decode()
    assert client.get("/groups/").status_code == 403
    client.force_login(keeper)
    assert 'href="/groups/"' in client.get("/").content.decode()
    assert client.get("/groups/").status_code == 200


def test_page_lists_kept_groups_members_and_candidates(client, keeper, it_board, depts, admin_user, make_member):
    gone = make_member("가상퇴사", active=False)
    depts["MEMS"].input_group.user_set.add(gone)
    make_member("가상후보")
    client.force_login(keeper)
    body = client.get("/groups/").content.decode()
    assert "<strong>IT 근무표 관리</strong>" in body and "<strong>매칭엔진실 출근표 입력</strong>" in body and "매매지원실 출근표 입력" not in body
    assert "IT 당번표 근무표 관리자(회차·배포·메모·지난 날짜 수정)" in body and "매칭엔진실 출근표 입력 담당" in body
    assert "가상퇴사 (퇴사)" in body  # 퇴사자도 보여 뺄 수 있게
    assert body.count(">가상후보 · 매칭엔진실</option>") == 2  # 두 그룹 모두 후보
    assert ">가상퇴사 · 매칭엔진실</option>" not in body  # 퇴사자는 넣을 후보가 아니다
    assert f'<option value="{admin_user.pk}">관리자</option>' in body  # 부서 없는 계정도 후보(입력 그룹 후보)


def test_post_add_remove_and_warning(client, keeper, it_board, admin_user, make_member):
    m = make_member("가상가")
    client.force_login(keeper)
    g = it_board.admin_group.pk
    r = client.post("/groups/", {"group": g, "member": m.pk, "do": "add"}, follow=True)
    assert "가상가을(를) IT 근무표 관리에 넣었습니다." in r.content.decode()  # 그룹 이름은 마이그레이션 0011 이 정했다
    client.post("/groups/", {"group": g, "member": m.pk, "do": "remove"})
    r = client.post("/groups/", {"group": g, "member": admin_user.pk, "do": "remove"}, follow=True)
    assert "근무표 관리자가 아무도 없습니다" in r.content.decode()
    assert not it_board.admin_group.user_set.exists()


def test_post_to_group_not_kept_is_404(client, keeper, depts, make_member):
    m = make_member("가상가")
    client.force_login(keeper)
    assert client.post("/groups/", {"group": depts["TMCH"].input_group.pk, "member": m.pk, "do": "add"}).status_code == 404
    assert client.post("/groups/", {"group": depts["MEMS"].input_group.pk, "member": "x", "do": "add"}).status_code == 404
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_groups.py`
Expected: 수집 오류 `ImportError: cannot import name 'groups' from 'duty.services'`

- [ ] **Step 3: 읽기 권한과 서비스**

`duty/perms.py` — import 에 한 줄:
```python
from django.contrib.auth.models import Group
```
`def managed_departments(` 바로 앞에:
```python
def kept_groups(user):
    """내가 그룹 관리자(GroupKeeper)인 그룹들: [그룹] 화면에서 멤버를 넣고 뺀다(설계 7절)."""
    if not user.is_authenticated:
        return Group.objects.none()
    return Group.objects.filter(keepers__user=user)


```

`duty/services/groups.py`(새 파일):
```python
"""그룹 화면(설계 7절): 그룹 관리자(GroupKeeper)가 맡은 그룹의 멤버를 넣고 뺀다. 넣고 빼면 그 권한이 바로 바뀐다."""
import logging

from django.core.exceptions import PermissionDenied
from django.db import transaction

from .. import perms
from ..errors import DutyError
from ..models import Board

log = logging.getLogger(__name__)


def _require_keeper(by, group) -> None:
    if not perms.kept_groups(by).filter(pk=group.pk).exists():
        raise PermissionDenied("이 그룹을 맡고 있지 않습니다.")


@transaction.atomic
def add_member(by, group, member) -> None:
    _require_keeper(by, group)
    if not member.is_active:
        raise DutyError(f"퇴사한 사람은 넣을 수 없습니다: {member.name}")
    if group.user_set.filter(pk=member.pk).exists():
        raise DutyError(f"이미 이 그룹에 있습니다: {member.name}")
    group.user_set.add(member)
    log.info("group %s: %s added by %s", group.pk, member.username, by.username)  # 실명 대신 아이디(멤버 코드)


@transaction.atomic
def remove_member(by, group, member) -> str:
    """빼고, 근무표 관리 그룹이 비게 되면 경고 문구를 돌려준다(막지는 않는다, 설계 7절). 아니면 빈 글자."""
    _require_keeper(by, group)
    if not group.user_set.filter(pk=member.pk).exists():
        raise DutyError(f"이 그룹에 없는 사람입니다: {member.name}")
    group.user_set.remove(member)
    log.info("group %s: %s removed by %s", group.pk, member.username, by.username)
    board = Board.objects.filter(admin_group=group).first()
    if board and not group.user_set.exists():
        return f"{board.name} 근무표 관리자가 아무도 없습니다. 회차·배포를 할 사람이 없으니 다른 사람을 넣으세요."
    return ""
```

Run: `.venv/bin/pytest -W error -q tests/test_groups.py -k "keeper_adds or no_warning or only_keeper or rules"`
Expected: 4 passed

- [ ] **Step 4: 화면·주소·메뉴**

`duty/views/manage.py` — import:
```python
from django.contrib import messages
from django.contrib.auth.decorators import login_required
```
```python
from ..models import DIRECT_STEPS, Board, ChangeLog, Department, InputMode, Period, User, step_label
from ..services import boards, collect, generate, groups as group_service, periods, stats
```
파일 끝에:
```python


def _about(group) -> str:
    """그룹이 무슨 권한인지 한 줄(나이 든 관리자가 그룹 이름만 보고 헷갈리지 않게)."""
    board = getattr(group, "admin_board", None)
    if board:
        return f"{board.name} 근무표 관리자(회차·배포·메모·지난 날짜 수정)"
    dept = getattr(group, "input_department", None)
    return f"{dept.name} 출근표 입력 담당" if dept else ""


@login_required
def groups(request):
    """그룹 화면(설계 7절): 내가 그룹 관리자인 그룹의 멤버를 보고 넣고 뺀다. 그룹 관리자가 아니면 403."""
    kept = list(perms.kept_groups(request.user).order_by("name").prefetch_related("user_set__department"))
    if not kept:
        raise PermissionDenied
    if request.method == "POST":
        group = next((g for g in kept if str(g.pk) == request.POST.get("group")), None)
        pid = request.POST.get("member", "")
        member = User.objects.filter(pk=pid).first() if pid.isdigit() else None
        if group is None or member is None:  # 맡지 않은 그룹·없는 사람
            raise Http404
        try:
            if request.POST.get("do") == "remove":
                warning = group_service.remove_member(request.user, group, member)
                messages.success(request, f"{member.name}을(를) {group.name}에서 뺐습니다.")
                if warning:
                    messages.warning(request, warning)
            else:
                group_service.add_member(request.user, group, member)
                messages.success(request, f"{member.name}을(를) {group.name}에 넣었습니다.")
        except DutyError as e:
            messages.error(request, str(e))
        return redirect("groups")
    active = list(User.objects.filter(is_active=True).select_related("department").order_by("name"))
    items = []
    for g in kept:
        members = sorted(g.user_set.all(), key=lambda u: u.name)
        ids = {u.pk for u in members}
        items.append({"group": g, "about": _about(g), "members": members,
                      "candidates": [u for u in active if u.pk not in ids]})  # 후보 = 재직 계정(퇴사자는 넣지 않는다)
    return render(request, "duty/groups.html", {"items": items})
```
(`getattr(…, None)`: 역방향 OneToOne 이 없을 때의 `RelatedObjectDoesNotExist` 는 `AttributeError` 의 하위라 기본값이 돌아온다.)

`duty/urls.py` — `path("changes/", …)` 줄 뒤에:
```python
    path("groups/", manage_views.groups, name="groups"),
```

`duty/context.py` 의
```python
    if user.is_superuser:
        items.append(("관리", reverse("admin:index"), ()))
```
앞에:
```python
    if perms.kept_groups(user).exists():  # 그룹 관리자(GroupKeeper)만(설계 7절)
        items.append(("그룹", "/groups/", ()))
```

`duty/templates/duty/groups.html`(새 파일):
```html
{% extends "duty/base.html" %}
{% block content %}
<h3>그룹</h3>
<p class="guide">내가 맡은 그룹에 사람을 넣고 뺍니다. 넣으면 바로 그 권한이 생기고, 빼면 바로 없어집니다.</p>
{% for it in items %}
<article class="grp">
  <header><strong>{{ it.group.name }}</strong>{% if it.about %}<br><small>{{ it.about }}</small>{% endif %}</header>
  {% if it.members %}<ul class="members">{% for u in it.members %}
    <li><span>{{ u.name }}{% if not u.is_active %} (퇴사){% endif %}{% if u.department %} <small>· {{ u.department.name }}</small>{% endif %}</span>
      <form method="post" onsubmit="return confirm('{{ u.name|escapejs }}을(를) {{ it.group.name|escapejs }}에서 뺄까요?')">{% csrf_token %}
        <input type="hidden" name="group" value="{{ it.group.pk }}"><input type="hidden" name="member" value="{{ u.pk }}">
        <button name="do" value="remove" class="outline secondary">빼기</button></form></li>{% endfor %}</ul>
  {% else %}<p>아직 아무도 없습니다.</p>{% endif %}
  <form method="post" class="add labeled">{% csrf_token %}<input type="hidden" name="group" value="{{ it.group.pk }}">
    <label>넣을 사람 <select name="member" required><option value="">고르세요</option>{% for u in it.candidates %}<option value="{{ u.pk }}">{{ u.name }}{% if u.department %} · {{ u.department.name }}{% endif %}</option>{% endfor %}</select></label>
    <button name="do" value="add">넣기</button>
  </form>
</article>
{% endfor %}
<style>
  p.guide { margin: 0 0 1rem; }
  article.grp { max-width: 40rem; }
  ul.members { padding: 0; margin: 0 0 1rem; }
  ul.members li { list-style: none; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem;
    padding: .4rem 0; border-bottom: 1px solid var(--duty-line); }
  ul.members form, ul.members button { width: auto; margin: 0; }
  ul.members button { min-height: 44px; padding: .4rem 1rem; }
  form.add { display: flex; flex-wrap: wrap; align-items: flex-end; gap: .5rem; }
  form.add label { flex: 1 1 14rem; margin: 0; }
  form.add select { margin: 0; }
  form.add button { width: auto; margin: 0; min-height: 44px; }
</style>
{% endblock %}
```

- [ ] **Step 5: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_groups.py tests/test_perms.py tests/test_views_manage.py`
Expected: 모두 PASS

Run: `.venv/bin/pytest -W error -q`
Expected: 모두 PASS(사본 기준 **1169 passed**), 경고 0개

- [ ] **Step 6: 브라우저로 확인한다(PC 1400px·휴대폰 390px·아주 크게·다크 모드)**

"브라우저 확인 준비"대로 띄운다. `admin` 은 운영팀 관리 그룹의 그룹 관리자다(가짜 데이터 셸이 넣음).
- 메뉴에 [그룹]이 [관리] 앞에 보인다. `member` 로는 안 보이고 `/groups/` 가 403.
- "운영팀 근무표 관리" 카드: 설명 한 줄, 멤버(나관리), [빼기]는 테두리, [넣기]는 진한 버튼. 가상하나를 넣고 → 성공 메시지 → 목록에 보임. 가상하나를 [빼기] → 확인창 → 빠짐. 나관리를 빼면(마지막 멤버) ⚠ "운영팀 근무표 관리자가 아무도 없습니다…" 경고가 나온다(나관리는 IT 관리자이기도 해서 메뉴 [회차]는 남는다. 확인 뒤 [넣기]로 다시 넣는다).
- 관리 화면에서 가상두리를 퇴사(재직 끔)로 바꾼 뒤 그룹에 남아 있으면 "가상두리 (퇴사)"로 보이고 뺄 수 있다.
- 390px·아주 크게에서 이름과 [빼기]가 줄바꿈되고 버튼 높이가 손가락 크기다. 다크 모드에서 카드·구분선이 보인다. 콘솔 `document.documentElement.scrollWidth > innerWidth` 가 `false`.

- [ ] **Step 7: 커밋**

```bash
git add duty/perms.py duty/services/groups.py duty/views/manage.py duty/urls.py duty/context.py duty/templates/duty/groups.html tests/test_groups.py
git commit -m "feat: 그룹 화면(그룹 관리자가 맡은 그룹 멤버 넣고 빼기, 관리 그룹이 비면 경고)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 5: 관리 화면의 근무표·근무 정의·그룹 관리자 편집과 검증

**Files:**
- Modify: `duty/models.py` — `import re`, `Board.clean`(만들 때 코드 검사), `BoardShift.clean`·`delete`(저장한 정의의 키·근무표 바꾸기와 지우기 금지), `Department.clean`(직접 입력 근무표는 부서 하나)
- Modify: `duty/admin.py` — import, `SHIFT_KEY_CHOICES`, `DepartmentForm.__init__`·`clean_shifts`, `_ViewOnly`·`BoardShiftInline`·`BoardAdmin`·`GroupKeeperInline` 교체, `GroupAdmin` 설명
- Modify(기계적 변경, 단언 그대로): `tests/test_lunch.py` — 점심당번 정의를 지우는 준비 코드 세 곳 `lunch.delete()` → `BoardShift.objects.filter(pk=lunch.pk).delete()`(이제 `instance.delete()` 는 막힌다)
- Modify(기대 값 변경: 1단계 보기 전용 → 3단계 편집): `tests/test_admin_boards.py` 통째로 다시 씀
- Test: `tests/test_admin_boards.py`

**Interfaces:**
- Consumes: `BoardShift` 모델(키 선택지 표시 이름 "근무조 1"~"근무조 4"·"관제 1"~"관제 10"·"점심당번"), `Board.save`(관리 그룹 자동 생성), `GroupKeeper`, `Department.shift_keys()`, `Board.departments`(related_name)
- Produces:
  - `Board.clean()`: 새 근무표의 `code` 가 `[a-z][a-z0-9]{0,15}` 이 아니면 `ValidationError({"code": "코드는 영문 소문자로 시작하는 영문 소문자·숫자 16자 이내입니다(예: ops)."})`(만든 뒤에는 보지 않는다 — 관리 화면에서 읽기 전용)
  - `BoardShift.clean()`: 저장한 줄의 `(board, key)` 가 DB 값과 다르면 `ValidationError("저장한 근무 정의의 키·근무표는 바꿀 수 없습니다. …")`. `BoardShift.delete()`: 늘 `ValidationError("저장한 근무 정의는 지울 수 없습니다. '사용'을 끄세요.")`(쿼리셋 일괄 삭제 `QuerySet.delete()` 는 이 검사를 거치지 않는다 — 받아들인 한계, 코드에 `ponytail:` 주석)
  - `Department.clean()`: 직접 입력 근무표에 다른 부서가 이미 있으면 `ValidationError({"board": "직접 입력 근무표에는 부서를 하나만 둘 수 있습니다."})`(관리 화면 부서 폼이 이 검사를 부른다)
  - `admin.SHIFT_KEY_CHOICES: list[tuple[str, str]]`(근무조 키 4개와 중립 이름)
  - `admin.BoardShiftForm`: 저장한 줄은 `key` 칸 disabled(보낸 값 무시). 한 줄 검증: 이름 규칙, 시각(start 칸에 오류), 자격은 장중관제만, 기본 알림은 근무조만
  - `admin.BoardShiftFormSet.clean()`: Django 기본 겹침 검사를 부르지 않고 한국어로 — "근무 정의 이름이 겹칩니다: X", "키가 겹칩니다: 근무조 1", 켜진 근무조 ≥ 1, 켜진 근무조 시작 시각이 서로 다름, 관제 자격 근무조 ⊆ 이 근무표 근무조, 켜진 관제의 자격 근무조 ⊆ 켜진 근무조, 저장된 근무표면 부서마다 (부서 출근조 ∩ 켜진 근무조) ≠ ∅
  - `BoardShiftInline.can_delete = False`(저장한 줄은 지우기 칸이 없다. 아직 저장하지 않은 추가 줄은 Django 화면의 ✕ 로 뺀다)
  - `admin.BoardForm.clean()`: 같은 이름의 다른 근무표가 있으면 "같은 이름의 근무표가 이미 있습니다: X", 새 근무표의 관리 그룹 이름이 이미 있으면 "같은 이름의 그룹이 이미 있습니다: X 근무표 관리"
  - `BoardAdmin`: 추가·편집 가능, 만든 뒤 `code`·`input_mode` 읽기 전용, 관리 그룹 링크(`group_link`), 지우기 금지. `GroupKeeperInline`: 편집 가능(관리 화면 "그룹").
  - 새 부서 폼: 출근조 선택지 = `SHIFT_KEY_CHOICES`, 저장 때 고른 근무표의 켜진 근무조인지 검사(오류 "이 근무표에 켜진 근무조가 아닙니다: 근무조 2"), 시작 시각 순으로 저장.

- [ ] **Step 1: 실패 테스트를 쓴다(1단계 보기 전용 테스트를 3단계 편집 테스트로)**

`tests/test_admin_boards.py` 를 통째로 바꾼다(1단계 "보기만" 테스트 6개는 3단계에서 동작이 바뀌어 지운다. 그룹 화면의 권한 칸 숨김 확인은 새 테스트에 남긴다):
```python
"""관리 화면(슈퍼유저 전용): 근무표·근무 정의 편집과 설계 4.3 검증, 그룹 관리자 지정(3단계). 이름은 모두 가상."""
from datetime import time

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.urls import reverse

from duty.admin import DepartmentForm
from duty.models import Board, BoardShift, Department, GroupKeeper

ADD = reverse("admin:duty_board_add")


@pytest.fixture
def su(admin_user):
    admin_user.is_superuser = True
    admin_user.save()
    return admin_user


@pytest.fixture
def su_client(client, su):
    client.force_login(su)
    return client


def row(i, key, name, start="", end="", pk="", board="", **more):
    """근무 정의 인라인 한 줄(prefix "shifts"). 체크박스는 켤 때만 보낸다(active 는 기본 켬)."""
    data = {f"shifts-{i}-id": pk, f"shifts-{i}-board": board, f"shifts-{i}-key": key, f"shifts-{i}-name": name,
            f"shifts-{i}-start": start, f"shifts-{i}-end": end}
    if more.pop("active", True):
        data[f"shifts-{i}-active"] = "on"
    for k, v in more.items():
        data[f"shifts-{i}-{k}"] = v
    return data


def form(rows, initial=0, **board):
    data = {"shifts-TOTAL_FORMS": str(len(rows)), "shifts-INITIAL_FORMS": str(initial), **board}
    for r in rows:
        data.update(r)
    return data


def three(board=""):
    return [row(0, "dawn", "이른", "07:30", "16:30", board=board), row(1, "normal", "가운데", "09:00", "18:00", board=board),
            row(2, "dinner", "늦은", "11:00", "20:00", board=board)]


@pytest.fixture
def ops(it_board):
    """가짜 직접 입력 근무표 '운영팀'(근무조 둘)."""
    board = Board.objects.create(code="ops", name="운영팀", input_mode=Board.InputMode.DIRECT)
    a = BoardShift.objects.create(board=board, key="dawn", name="이른", start=time(7, 30), end=time(16, 30))
    b = BoardShift.objects.create(board=board, key="dinner", name="늦은", start=time(11), end=time(20))
    return board, a, b


def change(board, shifts, *extra, **fields):
    """지금 정의를 그대로 보내고(필요하면 fields 로 바꾼 값) extra 줄을 더한다."""
    rows = [row(i, **{"key": s.key, "name": s.name, "start": f"{s.start:%H:%M}" if s.start else "",
                      "end": f"{s.end:%H:%M}" if s.end else "", "pk": s.pk, "board": board.pk, "active": s.active,
                      **fields.get(s.key, {})}) for i, s in enumerate(shifts)]
    rows += [{k.replace("shifts-0-", f"shifts-{len(rows) + j}-"): v for k, v in r.items()} for j, r in enumerate(extra)]
    return form(rows, initial=len(shifts), name=board.name)


def errors(r):
    return r.content.decode() if r.status_code == 200 else ""


# ── 근무표 추가 ──

def test_add_board_with_definitions(su_client, it_board):
    r = su_client.post(ADD, form(three(), code="ops", name="운영팀", input_mode="direct"))
    assert r.status_code == 302, errors(r)
    board = Board.objects.get(code="ops")
    assert board.admin_group.name == "운영팀 근무표 관리"
    assert list(BoardShift.objects.filter(board=board).order_by("start").values_list("key", "name")) == [
        ("dawn", "이른"), ("normal", "가운데"), ("dinner", "늦은")]


@pytest.mark.parametrize("code", ["운영", "Ops", "1ops", "ops-team", "a" * 17])
def test_add_board_code_must_be_short_ascii(su_client, it_board, code):
    r = su_client.post(ADD, form(three(), code=code, name="운영팀", input_mode="direct"))
    assert r.status_code == 200 and "코드는 영문 소문자로 시작하는 영문 소문자·숫자 16자 이내입니다" in r.content.decode()
    assert not Board.objects.filter(name="운영팀").exists()


def test_add_board_needs_a_shift(su_client, it_board):
    r = su_client.post(ADD, form([row(0, "lunch", "점심당번")], code="ops", name="운영팀", input_mode="direct"))
    assert r.status_code == 200 and "켜진 근무조가 하나 이상 있어야 합니다." in r.content.decode()
    assert not Board.objects.filter(code="ops").exists()


def test_add_board_group_name_clash(su_client, it_board):
    Group.objects.create(name="운영팀 근무표 관리")
    r = su_client.post(ADD, form(three(), code="ops", name="운영팀", input_mode="direct"))
    assert r.status_code == 200 and "같은 이름의 그룹이 이미 있습니다: 운영팀 근무표 관리" in r.content.decode()


def test_board_name_must_be_unique(su_client, ops, it_board):
    r = su_client.post(ADD, form(three(), code="ops2", name="운영팀", input_mode="direct"))
    assert r.status_code == 200 and "같은 이름의 근무표가 이미 있습니다: 운영팀" in r.content.decode()
    board, a, b = ops
    data = change(board, [a, b])
    data["name"] = it_board.name
    r = su_client.post(reverse("admin:duty_board_change", args=[board.pk]), data)
    assert r.status_code == 200 and f"같은 이름의 근무표가 이미 있습니다: {it_board.name}" in r.content.decode()


@pytest.mark.parametrize("rows,message", [
    ([row(0, "dawn", "이른", "07:30", "16:30"), row(1, "dinner", "늦은", "07:30", "20:00")],
     "켜진 근무조끼리 시작 시각이 달라야 합니다"),
    ([row(0, "dawn", "이른", "16:30", "07:30")], "시작·끝 시각을 넣고 시작을 끝보다 이르게 하세요"),
    ([row(0, "dawn", "이른", "07:30", "16:30"), row(1, "lunch", "점심당번", "12:00", "13:00")], "점심당번은 시각을 비웁니다"),
    ([row(0, "dawn", "date", "07:30", "16:30")], "이름은 date·day 가 아니어야 하고"),
    ([row(0, "dawn", "이른(조)", "07:30", "16:30")], "이름은 date·day 가 아니어야 하고"),
    ([row(0, "dawn", "이른", "07:30", "16:30"), row(1, "slot0", "점검", "09:00", "10:00", eligible_shifts="night")],
     "점검: 자격 근무조는 이 근무표의 근무조여야 합니다."),
    ([row(0, "dawn", "이른", "07:30", "16:30"), row(1, "normal", "가운데", "09:00", "18:00", active=False),
      row(2, "slot0", "점검", "09:00", "10:00", eligible_shifts="normal")],
     "점검: 켜진 관제의 자격 근무조는 켜진 근무조여야 합니다."),
    ([row(0, "dawn", "이른", "07:30", "16:30", eligible_types="직원")], "자격 근무조·자격 구분은 장중관제 칸에만 씁니다."),
    ([row(0, "dawn", "이른", "07:30", "16:30"), row(1, "slot0", "점검", "09:00", "10:00", default_alarm="on")],
     "기본 알림 대상은 근무조에만 씁니다."),
    ([row(0, "dawn", "같음", "07:30", "16:30"), row(1, "dinner", "같음", "11:00", "20:00")], "근무 정의 이름이 겹칩니다: 같음"),
    ([row(0, "dawn", "이른", "07:30", "16:30"), row(1, "dawn", "늦은", "11:00", "20:00")], "키가 겹칩니다: 근무조 1"),
])
def test_definition_rules(su_client, it_board, rows, message):
    r = su_client.post(ADD, form(rows, code="ops", name="운영팀", input_mode="direct"))
    body = r.content.decode()
    assert r.status_code == 200 and message in body
    assert "Constraint" not in body and "제약" not in body and "name의" not in body and "key의" not in body
    assert not Board.objects.filter(code="ops").exists()


def test_slot_with_shift_eligibility_saves(su_client, it_board):
    rows = three() + [row(3, "slot0", "점검", "09:00", "10:00", eligible_shifts="normal", eligible_types="직원")]
    r = su_client.post(ADD, form(rows, code="ops", name="운영팀", input_mode="direct"))
    assert r.status_code == 302, errors(r)
    s = BoardShift.objects.get(board__code="ops", key="slot0")
    assert (s.eligible_shifts, s.eligible_types) == (["normal"], ["직원"])


# ── 근무표 고치기 ──

def test_change_page_locks_code_mode_keys_and_has_no_delete(su_client, ops):
    board, *_ = ops
    body = su_client.get(reverse("admin:duty_board_change", args=[board.pk])).content.decode()
    assert 'name="name"' in body and 'name="code"' not in body and 'name="input_mode"' not in body
    assert reverse("admin:auth_group_change", args=[board.admin_group_id]) in body  # 관리 그룹 링크(그룹 관리자 지정)
    assert 'name="shifts-0-active"' in body and 'name="shifts-0-DELETE"' not in body
    assert '<select name="shifts-0-key"' in body and "disabled" in body.split('name="shifts-0-key"')[1].split(">")[0]


def test_rename_board_and_add_definition(su_client, ops):
    board, a, b = ops
    data = change(board, [a, b], row(0, "normal", "가운데", "09:00", "18:00", board=board.pk))
    data["name"] = "운영팀2"
    r = su_client.post(reverse("admin:duty_board_change", args=[board.pk]), data)
    assert r.status_code == 302, errors(r)
    board.refresh_from_db()
    assert board.name == "운영팀2" and BoardShift.objects.filter(board=board).count() == 3


def test_saved_definition_key_and_delete_ignored_but_can_be_turned_off(su_client, ops):
    board, a, b = ops
    url = reverse("admin:duty_board_change", args=[board.pk])
    data = change(board, [a, b], dawn={"key": "normal", "active": False})  # 키는 잠겨 있어 보낸 값이 무시된다
    data["shifts-0-DELETE"] = "on"  # 지우기 칸이 없다
    data["shifts-1-name"] = "늦은조"
    r = su_client.post(url, data)
    assert r.status_code == 302, errors(r)
    assert sorted(BoardShift.objects.filter(board=board).values_list("key", "name", "active")) == [
        ("dawn", "이른", False), ("dinner", "늦은조", True)]


def test_turning_off_last_input_shift_of_a_department_is_refused(su_client, ops):
    board, a, b = ops
    Department.objects.create(code="OPS", name="운영", shifts="dawn", board=board)
    r = su_client.post(reverse("admin:duty_board_change", args=[board.pk]), change(board, [a, b], dawn={"active": False}))
    assert r.status_code == 200 and "운영 부서에 켜진 근무조가 하나도 남지 않습니다" in r.content.decode()
    a.refresh_from_db()
    assert a.active


def test_board_cannot_be_deleted(su_client, ops):
    board, *_ = ops
    assert su_client.post(reverse("admin:duty_board_delete", args=[board.pk]), {"post": "yes"}).status_code == 403
    assert Board.objects.filter(pk=board.pk).exists()


# ── 모델에서도 막는다(관리 화면을 거치지 않는 길) ──

def test_model_refuses_key_change_and_delete(ops):
    board, a, b = ops
    a.key = "normal"
    with pytest.raises(ValidationError, match="저장한 근무 정의의 키·근무표는 바꿀 수 없습니다"):
        a.full_clean()
    a.refresh_from_db()
    with pytest.raises(ValidationError, match="저장한 근무 정의는 지울 수 없습니다"):
        a.delete()
    assert BoardShift.objects.filter(pk=a.pk).exists()


def test_model_refuses_bad_code_on_create(it_board):
    with pytest.raises(ValidationError, match="코드는 영문 소문자로"):
        Board(code="운영", name="운영팀").full_clean()


def test_direct_board_has_one_department(ops, it_board):
    board, *_ = ops
    Department.objects.create(code="OPS", name="운영", shifts="dawn", board=board)
    data = {"code": "OPS2", "name": "운영2", "board": board.pk, "order": 1, "shifts": ["dawn"], "managers": []}
    f = DepartmentForm(data)
    assert not f.is_valid() and "직접 입력 근무표에는 부서를 하나만 둘 수 있습니다." in str(f.errors["board"])
    with pytest.raises(ValidationError, match="부서를 하나만"):
        Department(code="OPS3", name="운영3", shifts="dawn", board=board).full_clean()
    it = DepartmentForm({**data, "board": it_board.pk, "shifts": ["dawn"]})
    assert it.is_valid(), it.errors  # 부서별 취합 근무표는 여러 부서


# ── 그룹 관리자 ──

def test_group_page_hides_permissions_and_edits_keepers(su_client, it_board, admin_user, make_member):
    group = it_board.admin_group
    html = su_client.get(reverse("admin:auth_group_change", args=[group.pk])).content.decode()
    assert 'name="name"' in html and 'name="permissions"' not in html and 'name="members"' not in html
    keeper = make_member("가상관리", user=True)
    r = su_client.post(reverse("admin:auth_group_change", args=[group.pk]), {
        "name": group.name, "keepers-TOTAL_FORMS": "1", "keepers-INITIAL_FORMS": "0",
        "keepers-0-group": group.pk, "keepers-0-user": keeper.pk,
    })
    assert r.status_code == 302, errors(r)
    assert list(GroupKeeper.objects.values_list("group", "user")) == [(group.pk, keeper.pk)]


# ── 새 부서: 근무표의 근무조만 ──

def test_new_department_shifts_checked_against_chosen_board(su_client, ops):
    board, *_ = ops
    url = reverse("admin:duty_department_add")
    assert "근무조 1" in su_client.get(url).content.decode()  # 근무표를 고르기 전이라 중립 이름
    data = {"code": "OPS", "name": "운영", "board": board.pk, "order": 1, "shifts": ["dawn", "normal"], "managers": []}
    r = su_client.post(url, data)
    assert r.status_code == 200 and "이 근무표에 켜진 근무조가 아닙니다: 근무조 2" in r.content.decode()
    r = su_client.post(url, {**data, "shifts": ["dinner", "dawn"]})
    assert r.status_code == 302, errors(r)
    assert Department.objects.get(code="OPS").shifts == "dawn,dinner"  # 시작 시각 순
```

`tests/test_lunch.py` 의 `lunch.delete()` 세 줄을 바꾼다(기계적 변경, 단언 그대로):
```python
    BoardShift.objects.filter(pk=lunch.pk).delete()  # 저장한 정의는 instance.delete() 가 막는다(3단계), 시험 준비는 쿼리셋으로
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_admin_boards.py`
Expected: `30 failed, 1 passed`(근무표 추가·고치기가 403, 그룹 관리자 인라인이 보기 전용, 모델 검사 없음. 근무표 지우기 403 테스트만 이미 통과)

- [ ] **Step 3: 모델 검사(`models.py`)**

맨 위에:
```python
import re

```
`class Board` 의 `def save(` 바로 앞에:
```python
    def clean(self):
        # 코드는 ?board= 쿼리에 쓰는 짧은 영문(설계 4.2). 만들 때만 본다(만든 뒤에는 관리 화면에서 읽기 전용)
        if self._state.adding and not re.fullmatch(r"[a-z][a-z0-9]{0,15}", self.code or ""):
            raise ValidationError({"code": "코드는 영문 소문자로 시작하는 영문 소문자·숫자 16자 이내입니다(예: ops)."})

```
`class BoardShift` 의 `__str__` 뒤에:
```python

    def clean(self):
        # 저장한 정의의 키·근무표는 바꾸지 않는다(지난 행·기록이 키로 이름을 찾는다, 설계 4.3). 관리 화면은 키 칸을 잠근다
        if self.pk:
            old = BoardShift.objects.filter(pk=self.pk).values_list("board_id", "key").first()
            if old and old != (self.board_id, self.key):
                raise ValidationError("저장한 근무 정의의 키·근무표는 바꿀 수 없습니다. 이 줄은 '사용'을 끄고 새 줄을 더하세요.")

    def delete(self, *args, **kwargs):
        # 저장한 정의는 지우지 않고 끈다. ponytail: 쿼리셋 일괄 삭제(QuerySet.delete)는 이 검사를 거치지 않는다
        raise ValidationError("저장한 근무 정의는 지울 수 없습니다. '사용'을 끄세요.")
```
(`clean` 의 오류는 칸 이름 없이 둔다: 관리 화면에서 key 칸이 disabled 라도 폼에 없는 칸 이름으로 오류를 붙이면 `ValueError` 가 난다.)

`class Department` 의 `def save(` 바로 앞에:
```python
    def clean(self):
        # 직접 입력 근무표는 부서 하나짜리(설계 6.2): 입력 표·채우기·확정 경고가 부서 하나를 전제로 한다
        if (self.board_id and self.board.input_mode == InputMode.DIRECT
                and Department.objects.filter(board_id=self.board_id).exclude(pk=self.pk).exists()):
            raise ValidationError({"board": "직접 입력 근무표에는 부서를 하나만 둘 수 있습니다."})

```

Run: `.venv/bin/pytest -W error -q tests/test_admin_boards.py -k "model or one_department"`
Expected: 3 passed(모델 검사 테스트. 관리 화면 테스트는 아직 FAIL 이라 `-k` 로 뺐다)

Run: `.venv/bin/pytest -W error -q tests/test_lunch.py`
Expected: 모두 PASS(준비 코드를 쿼리셋 삭제로 바꿨다)

- [ ] **Step 4: 관리 화면(`admin.py`)**

import 를 바꾼다:
```python
from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
```
```python
from django.urls import reverse
from django.utils.html import format_html
from py_vapid import _check_sub
```
```python
from .shifts import DEVELOPER, LUNCH, SHIFT_KEYS, STAFF, is_slot_cell, shift_defs

# 근무조 키 선택지(관리 화면 표시 이름 "근무조 1"~"근무조 4", 설계 4.1)
SHIFT_KEY_CHOICES = [(k, label) for k, label in BoardShift._meta.get_field("key").choices if k in SHIFT_KEYS]
```
(`.shifts import` 한 줄이 위 두 줄로 바뀐다.)

`DepartmentForm.__init__` 의
```python
        if self.instance.board_id:  # 1단계: 저장된 부서의 근무표는 바꿀 수 없다(옮기기는 필요해지면 별도 기능, 설계 4.4)
            self.fields["board"].disabled = True
        board = self.instance.board if self.instance.board_id else boards.it_board()  # 1단계: 새 부서는 IT
        self.fields["shifts"].choices = [(x.key, x.name) for x in shift_defs(boards.active_defs(board))]
```
를 바꾼다:
```python
        if self.instance.board_id:  # 저장된 부서의 근무표는 바꿀 수 없다(옮기기는 필요해지면 별도 기능, 설계 4.4)
            self.fields["board"].disabled = True
            self.fields["shifts"].choices = [(x.key, x.name) for x in shift_defs(boards.active_defs(self.instance.board))]
        else:  # 새 부서: 근무표를 같은 폼에서 고르므로 중립 이름으로 보이고 clean_shifts 가 그 근무표에 있는지 본다
            self.fields["shifts"].choices = SHIFT_KEY_CHOICES
```

`DepartmentForm.clean_shifts` 를 바꾼다:
```python
    def clean_shifts(self):
        picked = set(self.cleaned_data["shifts"])
        board = self.cleaned_data.get("board")
        if board is None:  # 근무표 칸 오류가 따로 보인다
            return ",".join(sorted(picked))
        order = [x.key for x in shift_defs(boards.active_defs(board))]  # 시작 시각 순으로 저장(입력 표 칸 순서)
        if picked - set(order):
            names = dict(SHIFT_KEY_CHOICES)
            raise forms.ValidationError("이 근무표에 켜진 근무조가 아닙니다: "
                                        + ", ".join(names[k] for k in SHIFT_KEYS if k in picked - set(order)))
        return ",".join(k for k in order if k in picked)
```
(`board` 칸은 `shifts` 보다 앞이라 `clean_shifts` 때 이미 있다. 저장된 부서는 board 칸이 disabled 라 저장된 근무표가 들어온다.)

`class _ViewOnly:` 부터 `@admin.register(Holiday)` 바로 앞까지(`_ViewOnly`·`BoardShiftInline`·`BoardAdmin`·`GroupKeeperInline`)를 통째로 바꾼다:
```python
class BoardShiftForm(forms.ModelForm):
    """근무 정의 한 줄의 검증(설계 4.3). 저장한 줄은 키 칸을 잠근다(BoardShift.clean 이 한 번 더 막는다).
    시각 오류는 start 칸에 붙인다: 그 칸이 오류면 DB 제약(boardshift_times_valid) 검사를 건너뛰어 영어 제약 문구가 함께 뜨지 않는다."""
    eligible_shifts = forms.MultipleChoiceField(label="자격 근무조", required=False, choices=SHIFT_KEY_CHOICES,
                                                widget=forms.CheckboxSelectMultiple, help_text="장중관제 칸만")
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
        if key not in SHIFT_KEYS and c.get("default_alarm"):
            self.add_error("default_alarm", "기본 알림 대상은 근무조에만 씁니다.")
        return c


class BoardShiftFormSet(forms.BaseInlineFormSet):
    """근무표 전체의 검증(설계 4.3). Django 기본 겹침 검사(영어 칸 이름이 섞인 문구)는 부르지 않고 한국어로 직접 본다:
    이름·키 겹침, 켜진 근무조 하나 이상, 켜진 근무조끼리 시작 시각이 다름(가장 이른 조·이른/가운데/늦은 조가 하나로 정해지게),
    관제 자격 근무조는 이 근무표의 근무조(켜진 관제는 켜진 근무조만), 끄고 나서도 부서마다 켜진 입력 근무조가 하나 이상."""

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
        if self.instance.pk:
            for dept in self.instance.departments.all():
                if not set(dept.shift_keys()) & on_keys:
                    raise ValidationError(f"{dept.name} 부서에 켜진 근무조가 하나도 남지 않습니다. 부서의 출근조를 먼저 바꾸세요.")


class BoardShiftInline(admin.TabularInline):
    """저장한 줄은 지우지 않는다(끄기만). 아직 저장하지 않은 추가 줄은 화면에서 뺄 수 있다."""
    model = BoardShift
    form = BoardShiftForm
    formset = BoardShiftFormSet
    extra = 0
    can_delete = False


class BoardForm(forms.ModelForm):
    class Meta:
        model = Board
        fields = ["code", "name", "input_mode"]

    def clean(self):
        c = super().clean()
        name = c.get("name")
        # Board.save 가 만들 관리 그룹 이름이 이미 있으면 Group.name unique 위반(500) 대신 칸 오류로
        if name and Board.objects.exclude(pk=self.instance.pk).filter(name=name).exists():
            self.add_error("name", f"같은 이름의 근무표가 이미 있습니다: {name}")
        elif name and not self.instance.pk and Group.objects.filter(name=f"{name} 근무표 관리").exists():
            self.add_error("name", f"같은 이름의 그룹이 이미 있습니다: {name} 근무표 관리")
        return c


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    """근무표(설계 4.2·4.3). code(boards.it_board() 가 IT 근무표를 찾는 열쇠)와 입력 방식은 만든 뒤 바꾸지 않는다.
    지우기는 막는다. 관리 그룹은 Board.save 가 만들고, 그 그룹의 그룹 관리자는 '관리 그룹' 링크(그룹 화면)에서 정한다."""
    form = BoardForm
    list_display = ["name", "code", "input_mode", "admin_group"]
    inlines = [BoardShiftInline]

    def get_fieldsets(self, request, obj=None):
        fields = ["code", "name", "input_mode"] + ([] if obj is None else ["group_link"])
        return [(None, {"fields": fields, "description": (
            "근무 정의의 이름·시각을 운영 중에 바꾸면 발송 창이 열린 알림이 한 번 다시 나가고, 예전에 내려받은 CSV 의 "
            "열 이름이 맞지 않습니다. 저장한 정의는 지우거나 키를 바꿀 수 없으니 '사용'을 끄고 새 줄을 더합니다. "
            "근무조 1~4 는 이름일 뿐이고 이른·늦은 조는 시작 시각으로 정합니다. 직접 입력 근무표에는 부서를 하나만 둡니다.")})]

    def get_readonly_fields(self, request, obj=None):
        return [] if obj is None else ["code", "input_mode", "group_link"]

    @admin.display(description="관리 그룹")
    def group_link(self, obj):
        return format_html('<a href="{}">{}</a> — 그룹 관리자는 이 링크에서, 멤버는 사용자 화면의 그룹 칸이나 [그룹] 화면에서 정합니다.',
                           reverse("admin:auth_group_change", args=[obj.admin_group_id]), obj.admin_group.name)

    def has_delete_permission(self, request, obj=None):
        return False


class GroupKeeperInline(admin.TabularInline):
    """그룹 관리자(설계 4.5): 이 그룹에 멤버를 넣고 빼는 사람. 슈퍼유저가 여기서 정하고, 그 뒤 멤버는 그 사람이 [그룹] 화면에서."""
    model = GroupKeeper
    extra = 0
```

`GroupAdmin` 의 설명 줄을 바꾼다:
```python
    """permissions 칸만 숨긴다(Django 권한을 쓰지 않는다). 멤버는 사용자 화면의 '그룹' 칸이나, 그룹 관리자가 [그룹] 화면에서 넣는다."""
```

- [ ] **Step 5: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_admin_boards.py tests/test_admin_department.py tests/test_boards_models.py tests/test_lunch.py`
Expected: 모두 PASS

Run: `.venv/bin/pytest -W error -q`
Expected: 모두 PASS(사본 기준 **1194 passed**: 1169 + 새 31 − 지운 6), 경고 0개

Run: `DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --check --dry-run`
Expected: `No changes detected in app 'duty'`

- [ ] **Step 6: 브라우저로 확인한다(관리 화면. PC 1400px·다크 모드, 390px·아주 크게는 깨지거나 페이지 가로 스크롤이 생기지 않는지만)**

"브라우저 확인 준비"대로 띄우고 `admin` 으로 `/admin/`:
- "근무표" → [근무표 추가]: 코드 `tst`, 이름 "시험팀", 직접 입력, 근무 정의 줄을 더해 근무조 2개(시각 다르게) 저장 → 목록에 보이고 "그룹"에 "시험팀 근무표 관리"가 생긴다. 코드에 한글·대문자, 근무조 없이, 같은 시작 시각, 같은 이름 두 줄, 점심당번에 시각 넣기로 저장하면 한국어 오류가 칸이나 위에 보이고 영어 "Constraint"·"name의" 문구가 없다.
- "운영팀" 고치기: 코드·입력 방식은 글자로만, 저장한 줄의 키는 잠겨 있고 지우기 칸이 없다. 새로 더한 줄은 저장 전 ✕ 로 뺄 수 있다. "이른"의 '사용'만 끄고 저장 → 저장된다(다시 켜 둔다). 운영 부서의 출근조가 모두 꺼지게 끄면 "운영 부서에 켜진 근무조가 하나도 남지 않습니다".
- "관리 그룹" 링크 → 그룹 화면에서 "그룹 관리자" 줄을 더해 가상하나를 지정 → 저장. 가상하나(`OPS0` / `Demo-pass-123`)로 로그인하면 메뉴 [그룹]이 보인다.
- "부서" → [부서 추가]: 출근조가 "근무조 1~4"로 보인다. 운영팀을 고르면 "직접 입력 근무표에는 부서를 하나만 둘 수 있습니다". 시험팀을 고르고 시험팀에 없는 근무조를 체크하면 "이 근무표에 켜진 근무조가 아닙니다".

- [ ] **Step 7: 커밋**

```bash
git add duty/models.py duty/admin.py tests/test_admin_boards.py tests/test_lunch.py
git commit -m "feat: 관리 화면에서 근무표·근무 정의·그룹 관리자 편집(설계 4.3 검증, 저장한 정의는 끄기만, 코드·부서 하나 검사)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 6: 직접 입력 근무표 관리자용 글 도움말

**Files:**
- Modify: `duty/help.py` — import, `VIDEOS` 뒤(`TEXTS`), `STEPS` 끝(`"direct"`), `allowed`, 파일 끝(`texts_for`)
- Modify: `duty/views/help.py` — `index` 컨텍스트
- Modify: `duty/templates/duty/help.html` — 영상 목록 뒤
- Test: `tests/test_help.py`(끝에 테스트 하나)

**Interfaces:**
- Consumes: `perms.admin_boards(user)`, `InputMode.DIRECT`
- Produces: `help.TEXTS = [("direct", "직접 입력 근무표 운영(입력 중·확정·배포)", "직접 입력 근무표 관리자")]`, `help.STEPS["direct"]: list[str]`, `help.allowed(user, "direct")`(직접 입력 근무표의 관리 그룹 멤버), `help.texts_for(user) -> list[dict]`(`for_user` 와 같은 모양). 영상 주소(`/help/video/direct.mp4`)는 없다(404, `VIDEOS` 에 없음). 로그인 팝업(`for_user`)은 그대로.

- [ ] **Step 1: 실패 테스트를 쓴다**

`tests/test_help.py` 끝에:
```python


def test_direct_board_admin_text_help(client, people, videos, make_member):
    """직접 입력 근무표 관리자에게만 글 도움말(영상 없음)이 보인다(3단계)."""
    from duty.models import Board
    ops = Board.objects.create(code="ops", name="운영팀", input_mode=Board.InputMode.DIRECT)
    client.force_login(people["admin"])  # IT(부서별 취합)만 관리
    assert "직접 입력 근무표 운영" not in client.get("/help/").content.decode()
    ops.admin_group.user_set.add(people["admin"])
    body = client.get("/help/").content.decode()
    assert "직접 입력 근무표 운영(입력 중·확정·배포)" in body and "· 직접 입력 근무표 관리자" in body
    for word in ("[2주 전 기준으로 채우기]", "[지난주와 같게]", "[표 저장]", "[확정]", "[확정 취소]", "[배포…]"):
        assert word in body, word
    assert body.count("글로 보기") == 3  # 영상 글은 그대로, 직접 입력 글은 영상이 없다
    assert client.get("/help/video/direct.mp4").status_code == 404
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_help.py -k direct_board`
Expected: FAIL(`AssertionError`: "직접 입력 근무표 운영(입력 중·확정·배포)" 없음)

- [ ] **Step 3: 구현한다**

`duty/help.py` — 맨 위 import:
```python
from . import perms
from .models import InputMode
```
`VIDEOS = [...]` 바로 뒤에:
```python

TEXTS = [  # 영상 없이 글로만 보는 사용법 (이름, 제목, 누구를 위한)
    ("direct", "직접 입력 근무표 운영(입력 중·확정·배포)", "직접 입력 근무표 관리자"),
]
```
`STEPS` 의 `"admin": [...]` 뒤(닫는 `}` 앞)에:
```python
    "direct": [
        "직접 입력 근무표는 부서 담당자 취합 없이 근무표 관리자가 출근표를 직접 넣습니다. 단계는 입력 중 → 확정 → 배포됨 셋입니다.",
        "[회차]에서 [+ 새 회차]로 이름과 기간을 정해 만들면 바로 '입력 중'이 됩니다. 입력 중에는 기간도 고칠 수 있습니다(줄이면 기간 밖 출근표는 지워집니다).",
        "회차 화면의 [표 입력]을 누르면 날짜별 표가 나옵니다. 칸마다 이름을 쉼표(,)로 적고, 휴가·출장·교육은 이름(휴가)처럼 붙입니다. 휴장일·근무 없음 날은 잠겨 있습니다.",
        "주마다 [2주 전 기준으로 채우기]를 누르면 2주 전 그 주를 보고 이른 조와 늦은 조를 맞바꿔 채웁니다. 가운데 조였던 사람과 새로 온 사람은 가운데 조로 들어갑니다. 근무조가 3개일 때만 보입니다.",
        "[지난주와 같게]는 지난주 같은 요일을 그대로 옮깁니다. 사유(휴가 등)는 옮기지 않고, 지금 재직하는 사람만 넣습니다.",
        "채우기는 그 주 표를 그려 보여 주기만 합니다. 바뀐 칸은 색칠됩니다. 확인하고 고친 뒤 화면 아래 [표 저장]을 눌러야 저장됩니다.",
        "다 넣었으면 회차 화면에서 [확정]을 누릅니다. 점심당번이 있으면 가장 이른 근무조 사람으로 채웁니다. 비어 있는 평일이 있으면 경고만 보이고 확정은 됩니다.",
        "확정한 뒤 [배포…]로 근무표에 내보냅니다. 배포 전에 고칠 것이 있으면 [확정 취소]로 입력 중으로 돌아갑니다(출근표는 그대로, 점심당번은 다시 확정할 때 새로 채웁니다).",
        "배포한 뒤에는 근무표 화면에서 칸을 눌러 바꿉니다. 잘못 배포했으면 회차 화면의 [배포 취소]로 되돌립니다(가장 최근 배포만, 회차는 확정으로 돌아갑니다).",
    ],
```
`allowed` 의 마지막 줄 `return name == "admin" and perms.is_admin(user)` 바로 앞에:
```python
    if name == "direct":
        return perms.admin_boards(user).filter(input_mode=InputMode.DIRECT).exists()
```
파일 끝에:
```python


def texts_for(user) -> list[dict]:
    return [{"name": n, "title": t, "who": w, "steps": STEPS[n]} for n, t, w in TEXTS if allowed(user, n)]
```

`duty/views/help.py` 의 `index`:
```python
    return render(request, "duty/help.html", {"videos": guide.for_user(request.user), "texts": guide.texts_for(request.user)})
```

`duty/templates/duty/help.html` 의 영상 목록 `{% endfor %}` 와 `{% if user.is_authenticated %}`(설정 도움말) 사이에:
```html
{% for t in texts %}
<article class="howto">
  <header><strong>{{ t.title }}</strong> <small>· {{ t.who }}</small></header>
  <ol>{% for s in t.steps %}<li>{{ s }}</li>{% endfor %}</ol>
</article>
{% endfor %}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/pytest -W error -q tests/test_help.py`
Expected: 모두 PASS

Run: `.venv/bin/pytest -W error -q`
Expected: 모두 PASS(사본 기준 **1195 passed**), 경고 0개

- [ ] **Step 5: 브라우저로 확인한다(PC 1400px·휴대폰 390px·아주 크게·다크 모드)**

"브라우저 확인 준비"대로 띄우고 `admin`(운영팀 관리자)으로 [도움말]: 영상 셋 아래 "직접 입력 근무표 운영(입력 중·확정·배포)" 글이 펼쳐진 번호 목록으로 보인다. `member` 와 IT 입력 담당(`manager`)에게는 안 보인다. 아주 크게 + 390px, 다크 모드에서 글이 줄바꿈되어 읽히고 콘솔 `document.documentElement.scrollWidth > innerWidth` 가 `false`.

- [ ] **Step 6: 커밋**

```bash
git add duty/help.py duty/views/help.py duty/templates/duty/help.html tests/test_help.py
git commit -m "feat: 직접 입력 근무표 관리자용 글 도움말(입력 중·채우기·확정·배포)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

### Task 7: 문서

**Files:**
- Modify: `docs/ARCHITECTURE.md`, `docs/OVERVIEW.md`, `docs/OPERATIONS.md`, `docs/PRINCIPLES.md`

**Interfaces:**
- Consumes: Task 1~6 의 동작
- Produces: 문서만(코드 변경 없음). 설계 문서(`docs/superpowers/specs/…`)는 4단계 끝에 합치고 지우므로 지금은 두지 않는다(손대지 않음).

- [ ] **Step 1: ARCHITECTURE.md**

코드 지도 표:
- `duty/shifts.py` 줄의 "하는 일"을 `칸 키 목록(`KEYS`)과 키의 성격(`kind`), 사유 목록(`REASONS`), 근무 정의 목록(defs)을 받는 헬퍼, 날짜 계산, [2주 전 기준으로 채우기]의 맞바꾸기(`two_week_rotation`)` 로.
- `duty/admin.py` 줄을 `Django 관리 화면(사용자·부서(점심 시각)·근무표와 근무 정의(편집·설계 4.3 검증)·그룹(그룹 관리자)·휴장일·계정 발급·알림 설정)` 로.

"근무표와 칸"의
```
- 근무표와 근무 정의는 관리 화면 "근무표"에서 보기만 한다(1단계). 근무표 추가·편집·근무 정의 편집은 3단계에서 설계 4.3 검증과 함께 연다. code 는 `boards.it_board()` 가 IT 근무표를 찾는 열쇠라 바꾸지 않는다.
```
를 바꾼다:
```
- 근무표와 근무 정의는 슈퍼유저가 관리 화면 "근무표"에서 추가·편집한다(`admin.BoardShiftForm`·`BoardShiftFormSet`): 시각이 있으면 시작 < 끝(점심당번은 시각 없음), 이름·키 겹침 없음, 켜진 근무조 하나 이상, 켜진 근무조끼리 시작 시각이 다름, 관제 자격 근무조는 그 근무표의 근무조(켜진 관제는 켜진 근무조만), 근무조를 꺼도 부서마다 켜진 입력 근무조가 하나 이상, 자격은 장중관제만·기본 알림은 근무조만, 이름은 `date`·`day`·`(`·줄바꿈 금지(CSV 열 이름). **저장한 정의는 키를 바꾸거나 지울 수 없고** '사용'을 끈다(관리 화면은 키 칸을 잠그고 지우기 칸이 없다. 모델도 `BoardShift.clean`·`delete` 로 막는다, 쿼리셋 일괄 삭제만 예외). code 는 만들 때 짧은 영문 소문자(`Board.clean`)이고, code(`boards.it_board()` 가 IT 근무표를 찾는 열쇠)와 입력 방식은 만든 뒤 바꾸지 않으며, 근무표는 지우지 않는다. 직접 입력 근무표에는 부서를 하나만 둔다(`Department.clean`). 새 부서의 출근조는 중립 이름(근무조 1~4)으로 고르고 저장 때 그 근무표의 켜진 근무조인지 본다.
```

역할 표의 그룹 관리자·슈퍼유저 두 줄을 바꾼다:
```
| 그룹 관리자(`GroupKeeper`) | 맡은 그룹에 멤버를 넣고 뺀다(메뉴 [그룹], `/groups/`, `services/groups.py`). 후보는 재직 계정, 퇴사자는 "(퇴사)"로 보여 뺄 수 있다. 근무표 관리 그룹이 비면 경고만 한다. 넣고 빼기는 로그(아이디)로 남는다 |
| 슈퍼유저 | Django 관리 화면: 사용자("그룹" 칸으로 근무표 관리자 지정)·부서(점심 시각 포함)·휴장일·근무표와 근무 정의(추가·편집)·그룹(이름, 그룹 관리자 지정)·계정 발급·로그인 잠금 해제·알림 설정. 근무표 관리자 권한은 자동으로 받지 않는다(관리 그룹에 넣어야 한다) |
```
그 아래
```
- 그룹 관리자는 `Group`에 걸린 표라서(근무표로 가는 FK가 없다) 관리 화면 "그룹"에 보기 전용 인라인으로 보인다(편집은 3단계). 근무표 화면에서는 관리 그룹이 읽기 전용으로만 보인다.
```
를:
```
- 그룹 관리자는 `Group`에 걸린 표라서(근무표로 가는 FK가 없다) 관리 화면 "그룹"의 인라인에서 정한다. 근무표 화면에는 관리 그룹 링크가 있다.
```

"회차" 절의 상태 그림 아래 첫 항목 앞에 한 항목을 더한다:
```
- **직접 입력 근무표**(`input_mode=direct`)는 같은 DB 상태를 쓰고 화면 이름만 **입력 중(취합 중) → 확정(생성됨) → 배포됨**이다(`models.DIRECT_STEPS`·`step_label`·`Period.status_label`). 새 회차는 만들자마자 입력 중이고(`periods.save_draft`), 입력 중에도 기간을 고친다. 관리자가 회차 화면의 [표 입력]으로 출근표를 넣고 [확정](`generate.run_generation`: 입력 중·확정에서, 빈 평일은 막지 않고 경고 — `periods.empty_days`)하면 배포할 수 있다. [확정 취소]는 입력 중으로만 옮긴다(`periods.move`, 당번 배정을 지우고 출근표는 남긴다). 작성 중·마감은 쓰지 않는다. 입력 현황·편차 표·생성 방식은 보이지 않는다.
```

"출근표 입력" 항목 끝에 문장을 더한다:
```
 직접 입력 근무표의 입력 중 회차에는 주마다 **[2주 전 기준으로 채우기]**(입력 근무조가 3개일 때만: 2주 전 그 주 월~금에 근무로 친 날이 가장 많은 근무조(같으면 먼저 나온 것)를 보고 이른 ↔ 늦은, 나머지·근무가 없던 사람은 가운데)와 **[지난주와 같게]**(지난주 같은 요일의 근무조, 사유는 옮기지 않음)가 있다(`collect.fill_week`). 기준은 회차 기간 안이면 화면의 표(저장 전 고친 것 포함), 밖이면 배포된 근무표(그날의 주인)다. 지금 재직하는 그 부서 사람만 넣고 건너뛰는 날은 비운다. 누르면 그 주의 줄만 다시 그려 보여 주고(바뀐 칸 색칠) 저장은 [표 저장]으로만 한다. 칸에서 Enter 는 저장이다(폼 맨 앞의 화면 밖 저장 버튼).
```

"도움말" 절 첫 항목 끝에 문장을 더한다:
```
 직접 입력 근무표 관리자에게는 영상 없이 글 도움말(`help.TEXTS`·`STEPS["direct"]`)이 하나 더 보인다.
```

- [ ] **Step 2: OVERVIEW.md**

역할 표: 관리자 줄 다음에 한 줄을 더하고 슈퍼유저 줄을 바꾼다:
```
| 그룹 관리자 | 슈퍼유저가 정한 사람 | 맡은 그룹(근무표 관리·출근표 입력)에 사람을 넣고 빼기([그룹] 화면) |
| 슈퍼유저 | 관리자 중 1~2명 | 관리 화면: 계정 발급·부서(점심 시각)·입력 담당자·관리자 지정(사용자의 그룹 칸)·근무표와 근무 정의 추가·편집·그룹 관리자 지정·휴장일·로그인 잠금 해제·알림 설정 |
```

"한 회차의 흐름" 코드 블록 아래 첫 항목 앞에:
```
- 직접 입력 근무표(시장운영실처럼 관리자가 출근표를 직접 넣는 팀)는 **입력 중 → 확정 → 배포됨**: 회차를 만들면 바로 입력 중, 관리자가 표에 넣고(주마다 [2주 전 기준으로 채우기]·[지난주와 같게]) [확정]하면 배포할 수 있다. 확정을 되돌리려면 [확정 취소].
```

용어 표 "회차" 줄을:
```
| 회차 | 근무표를 만드는 기간 단위. 작성 중 → 취합 중 → 마감 → 생성됨 → 배포됨(직접 입력 근무표는 입력 중 → 확정 → 배포됨) |
```

- [ ] **Step 3: OPERATIONS.md**

"처음 한 번: 계정 만들기"의 "이어서 바로 (한 번)" 항목 끝 문장 `그룹 관리자 지정은 3단계 그룹 화면에서 한다.` 를 바꾼다:
```
그룹 관리자(그룹에 사람을 넣고 빼는 사람)는 관리 화면 "그룹" → 그 그룹 → "그룹 관리자" 줄에서 정한다. 그 사람에게는 메뉴 [그룹]이 보이고, 거기서 멤버를 넣고 뺀다.
```

"근무표 관리자" 항목(`**근무표 관리자**(회차·생성·…)`)의 괄호 문장 `(관리 화면 "그룹"은 이름과 멤버 목록만 보인다)` 를 `(그룹 관리자가 있으면 그 사람이 [그룹] 화면에서도 넣고 뺀다)` 로.

"업그레이드·롤백"의 2단계 묶음 뒤, `- nginx 를 켜 둔 서버는 …` 항목 앞에:
```
- **근무표 일반화 3단계로 올릴 때**: 마이그레이션이 없다(업그레이드 절차 그대로, `migrate` 는 "No migrations to apply"). 바뀌는 것: 관리 화면 "근무표"에서 근무표·근무 정의를 추가·편집한다(저장한 정의는 지우거나 키를 바꾸지 못하고 '사용'을 끈다, code·입력 방식은 만든 뒤 못 바꾼다, 직접 입력 근무표에는 부서 하나). 관리 화면 "그룹"에서 그룹 관리자를 정하면 그 사람에게 메뉴 [그룹]이 생긴다(1단계 마이그레이션이 지금 슈퍼유저를 모든 그룹의 그룹 관리자로 넣어 두었으므로 슈퍼유저에게도 [그룹]이 보인다). 새 부서의 출근조는 "근무조 1~4"로 고르고 고른 근무표에 있는 근무조만 저장된다. 직접 입력 근무표의 회차 화면(입력 중 → 확정 → 배포됨)과 채우기 버튼은 직접 입력 근무표가 생길 때(4단계)부터 보인다. IT 화면·알림은 그대로다.
```

- [ ] **Step 4: PRINCIPLES.md 결정 기록(표 끝에 네 줄)**

```
| 2026-11-16 | 직접 입력 근무표는 DB 상태를 그대로 쓰고 화면 이름만 입력 중(취합 중)·확정(생성됨)·배포됨으로 바꾼다. 새 회차는 바로 입력 중, 입력 중에도 기간 수정, 빈 평일은 확정 경고만, [확정 취소]는 입력 중으로만 | 상태·제약·배포·배포 취소 코드를 하나로 두고, 부서 취합이 없는 팀에서 취합 열기·마감 단계를 없앤다 |
| 2026-11-16 | 채우기 버튼은 저장하지 않고 그 주의 줄만 다시 그린다. 회차 안의 기준은 화면의 표(저장 전 고친 것 포함), 밖은 배포된 근무표. [지난주와 같게]는 근무조만 옮기고 사유는 옮기지 않는다 | 저장은 [표 저장]의 기존 검증 한 길로만. 저장 전에 고친 다른 주가 날아가지 않게. 지난주 휴가가 이번 주로 따라오면 안 된다 |
| 2026-11-16 | 그룹 화면은 그룹 관리자만, 멤버 넣고 빼기만(근무표 관리 그룹이 비면 경고만, 기록은 로그). 그룹 관리자 지정은 슈퍼유저가 관리 화면 "그룹"에서 | 관리자를 바꿀 때마다 슈퍼유저를 거치지 않게 하되, 권한을 나눠 주는 권한은 슈퍼유저에게 둔다 |
| 2026-11-16 | 관리 화면에서 근무표·근무 정의를 편집한다(설계 4.3 검증은 폼이 먼저 해서 한국어로, 마이그레이션 없음). code·입력 방식은 만든 뒤 바꾸지 않고, 저장한 근무 정의는 쓰였는지와 상관없이 지우거나 키를 바꾸지 않고 끈다(모델에서도 막음). 근무표는 지우지 않고, 직접 입력 근무표는 부서 하나 | code 는 `boards.it_board()` 의 열쇠이고, 입력 방식을 바꾸면 회차 상태·입력 그룹이 맞지 않는다. 지난 행·기록·알림 발송 기록이 키로 이름을 찾고, "쓰였나" 판단은 빠뜨리기 쉽다. 입력 표·채우기·확정 경고가 부서 하나를 전제로 한다 |
```

- [ ] **Step 5: 남은 옛 말이 없는지 본다**

```bash
grep -n "3단계에서\|편집은 3단계\|보기 전용 인라인\|1단계는 보기만\|그룹 화면에서 한다\|이름과 멤버 목록만" docs/ARCHITECTURE.md docs/OVERVIEW.md docs/OPERATIONS.md
```
Expected: 출력 없음(OPERATIONS 의 1단계 업그레이드 묶음 "그룹 관리자는 보기만 한다"는 그때의 기록이라 그대로 둔다 — 위 grep 에 걸리지 않는다)

- [ ] **Step 6: 전체 확인**

```bash
.venv/bin/pytest -W error -q                                                       # 모두 PASS(사본 기준 1195 passed), 경고 0개
.venv/bin/pytest -W error -q tests/test_alarm_texts_it.py                          # 그대로 통과(IT 문구 불변)
DJANGO_SETTINGS_MODULE=config.test_settings .venv/bin/python manage.py makemigrations duty --check --dry-run   # No changes detected
git diff --stat main -- tests/test_alarm_texts_it.py                               # 출력 없음(고치지 않았다)
```

마지막으로 "브라우저 확인 준비"대로 한 번 더 띄워 IT 화면(`member`: 근무표 주간·월간, `admin`: IT 회차 화면·입력 표)이 3단계 전과 같은지(단계 띠·버튼·문구) 1400px·390px·아주 크게·다크 모드로 보고(가로 넘침 콘솔 확인 포함) 서버를 끈 뒤 임시 폴더를 지운다.

- [ ] **Step 7: 커밋**

```bash
git add docs/ARCHITECTURE.md docs/OVERVIEW.md docs/OPERATIONS.md docs/PRINCIPLES.md
git commit -m "docs: 3단계 반영(직접 입력 회차·채우기 버튼·그룹 화면·관리 화면 편집, 3단계 업그레이드, 결정 기록)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0176vw5QvA1tvXbXPDiNL1Va"
```

---

## 설계 대조(자체 검토)

| 설계 11절 3단계 | 작업 |
|---|---|
| direct 회차 흐름(입력 중 → 확정 → 배포됨, 입력 중 기간 수정, 확정 경고) — 6.1·6.3·7 | Task 1(서비스), Task 2(화면) |
| 입력 표의 [2주 전 기준으로 채우기]·[지난주와 같게] — 6.2 | Task 3 |
| 그룹 화면 — 7절, 9절 메뉴 | Task 4 |
| 관리 화면의 Board·BoardShift·GroupKeeper 편집과 검증 — 4.2·4.3·7절 | Task 5 |
| direct 근무표 관리자용 글 도움말 | Task 6 |
| 문서·결정 기록 — 13절 | Task 7 |

- 10절 마이그레이션: 3단계 항목 없음 → 마이그레이션 없음(판단 1).
- 12절 테스트: 두 근무표 픽스처(IT + 가짜 "운영팀")로 직접 입력 동작이 IT(부서별 취합)에 영향이 없음을 Task 1·2·3 테스트가 확인한다(IT 생성은 여전히 마감에서, IT 회차 화면 그대로, IT 입력 표에 채우기 버튼 없음).
- 4단계 준비: 근무표 추가(관리 그룹 자동) → 근무 정의 → 부서(새 부서 출근조 검사, 점심 시각) → 그룹 멤버·그룹 관리자 → 사람이 관리 화면만으로 된다(Task 5, 판단 10).
