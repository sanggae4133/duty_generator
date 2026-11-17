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
    body = re.sub(r'(<option value=")\d+(")', r"\1N\2", body)  # 사용자·근무표 pk 도 DB 순번이라 지운다
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
