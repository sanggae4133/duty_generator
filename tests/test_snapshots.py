"""화면 스냅샷: 핵심 화면 셋(근무표 하나인 주간·월간·하루)만 본문(<main> 안, 메뉴 빼고)을 tests/snapshots/ 의
기준 HTML 과 비교한다. 보이는 동작을 일부러 바꾸는 PR 만 DUTY_SNAPSHOT_WRITE=1 로 다시 쓰고 바뀐 줄을 PR diff 로 리뷰한다.
나머지 화면(회차·입력 표·회차 목록·출근표 입력·도움말·남의 근무표·겹친 화면)은 지키던 성질만 일반 assert 로 본다
(결정 기록 2026-11-26: 화면 PR 마다 기준을 다시 써서 리뷰 가치가 떨어졌다). 이름은 모두 가상."""
import os
import re
from datetime import date, datetime, time, timezone
from pathlib import Path

import pytest

from duty.models import Board, BoardShift, Commute, Department, DutyAssignment, Period, PeriodEvent, User
from duty.services.generate import run_generation

SNAP = Path(__file__).parent / "snapshots"
S = Period.Status
MON, FRI = date(2026, 11, 16), date(2026, 11, 20)
TUE = date(2026, 11, 17)
AT = datetime(2026, 11, 16, 9, tzinfo=timezone.utc)


def _main(body: str, tokens: dict) -> str:
    main = body.index("<main")
    body = body[body.index("</header>", main) + len("</header>"):body.index("</main>")]  # 메뉴는 보지 않는다(3단계에서 바뀐다)
    body = re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', 'name="csrfmiddlewaretoken"', body)
    # pk 는 DB 순번이라 픽스처가 만든 것만 이름표(P_it_draft·B_ops·U_MEMS901)로 바꾼다. 모르는 번호는 그대로 남겨
    # 다른 대상을 가리키게 된 회귀가 diff 로 보이게 한다.
    body = re.sub(r"/(periods|collect)/(\d+)/",
                  lambda m: f"/{m[1]}/{tokens['period'].get(int(m[2]), m[2])}/", body)
    kinds = {"board": "board", "member": "user"}  # <select name> → 그 option value 가 가리키는 모델

    def options(m):
        kind = kinds.get(m[1])
        if kind is None:
            return m[0]
        return re.sub(r'(<option value=")(\d+)(")',
                      lambda o: f"{o[1]}{tokens[kind].get(int(o[2]), o[2])}{o[3]}", m[0])
    body = re.sub(r'<select name="([^"]+)".*?</select>', options, body, flags=re.S)
    kept = []  # <textarea>·<pre> 안 글은 공백까지 내용이라 그대로 둔다

    def keep(m):
        kept.append(m[2])
        return f"{m[1]}\x00{len(kept) - 1}\x00{m[3]}"
    body = re.sub(r"(<(?:textarea|pre)\b[^>]*>)(.*?)(</(?:textarea|pre)>)", keep, body, flags=re.S)
    body = re.sub(r"\s+", " ", body)  # 템플릿 줄바꿈·들여쓰기 차이는 보지 않는다
    body = re.sub(r">\s*<", ">\n<", body).strip() + "\n"  # 태그마다 한 줄(리뷰할 diff 를 읽기 쉽게)
    return re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m[1])], body)


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
    tokens = {"period": {x.pk: f"P_{tag}_{st}".replace("-", "_") for (tag, st), x in out.items()},
              "board": {b.pk: f"B_{b.code}" for b in Board.objects.all()},
              "user": {u.pk: f"U_{u.username}" for u in User.objects.all()}}
    return out, it_m, tokens


def _pages(client, admin_user, world):
    p, member, tokens = world
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
        got[name] = _main(r.content.decode(), tokens)
    client.force_login(member)  # 근무표 하나 고른 화면: 내 근무표 주간·월간·하루, 남의 근무표(보기 전용). 보기는 주소로 고정
    for name, url in (("roster-mine", "/?view=week"), ("roster-month", "/?view=month"), ("day", "/day/2026-11-16/"),
                      ("roster-other", "/?board=ops&view=week"),
                      # 겹친 화면(5단계): 두 근무표를 주소로 고른 주간·월간·하루. 운영팀 구역은 보기만
                      ("roster-both", "/?board=it&board=ops&view=week"), ("roster-both-month", "/?board=it&board=ops&view=month"),
                      ("day-both", "/day/2026-11-16/?board=it&board=ops")):
        r = client.get(url)
        assert r.status_code == 200, name
        got[name] = _main(r.content.decode(), tokens)
    return got


SNAPSHOTS = ("roster-mine", "roster-month", "day")  # 근무표 하나인 화면은 겹쳐 보기 전과 같아야 한다(5단계 불변)


def test_pages_match_snapshots(client, admin_user, world):
    got = {k: v for k, v in _pages(client, admin_user, world).items() if k in SNAPSHOTS}
    if os.environ.get("DUTY_SNAPSHOT_WRITE") == "1":
        SNAP.mkdir(exist_ok=True)
        for old in SNAP.glob("*.html"):
            old.unlink()
        for name, body in got.items():
            (SNAP / f"{name}.html").write_text(body, encoding="utf-8")
        pytest.fail("스냅샷을 다시 썼습니다. git diff tests/snapshots/ 로 바뀐 줄을 보고, 변수 없이 다시 돌리세요.")
    assert sorted(f.stem for f in SNAP.glob("*.html")) == sorted(got)
    for name, body in got.items():
        assert body == (SNAP / f"{name}.html").read_text(encoding="utf-8"), name


def _buttons(body: str) -> list[str]:
    return [t.strip() for t in re.findall(r'<(?:button|a [^>]*role="button")[^>]*>([^<]*)', body)]


# 회차 화면 버튼 순서: 단계 이름에서 나온 글자·임시 기준(마감 안 쓰는 근무표)·관제 이력 근무표가 main 과 같은지(옛 스냅샷이 지키던 것)
PERIOD_BUTTONS = {
    "it-draft": ["기간 저장", "취합 열기", "옮기기", "회차 삭제", "닫기"],
    "it-collecting": ["취합 마감", "옮기기", "표 입력", "표 입력", "표 입력", "표 입력", "회차 삭제", "닫기"],
    "it-closed": ["장중관제 생성", "생성 방식", "옮기기", "회차 삭제", "닫기"],
    "it-generated": ["배포…", "재생성", "생성 방식", "옮기기", "회차 삭제", "닫기"],
    "it-published": ["배포 취소", "닫기"],
    "it-full-closed": ["장중관제 생성", "생성 방식", "옮기기", "회차 삭제", "닫기"],
    "it-full-generated": ["배포…", "재생성", "생성 방식", "옮기기", "회차 삭제", "닫기"],
    "ops-draft": ["기간 저장", "옮기기", "회차 삭제"],
    "ops-collecting": ["기간 저장", "표 입력", "확정", "표 입력", "회차 삭제"],
    "ops-closed": ["옮기기", "회차 삭제"],
    "ops-generated": ["배포…", "확정 취소", "회차 삭제"],
    "ops-published": ["배포 취소"],
    "ops-slot-history": ["배포…", "확정 취소", "회차 삭제"],
}
TABLE_BUTTONS = {
    "table-it-collecting": ["CSV 올리기(이 표 전체 교체)", "CSV 내려받기", "표 저장", "지난주와 같게", "표 저장"],
    "table-it-closed": ["CSV 내려받기"],
    "table-ops-collecting": ["CSV 올리기(이 표 전체 교체)", "CSV 내려받기", "표 저장", "2주 전 기준으로 채우기", "지난주와 같게",
                             "표 저장"],
    "table-ops-generated": ["CSV 내려받기"],
}


def test_other_pages_keep_their_shape(client, admin_user, world):
    got = _pages(client, admin_user, world)
    assert {f"period-{k}" for k in PERIOD_BUTTONS} | set(TABLE_BUTTONS) <= set(got)
    for k, want in PERIOD_BUTTONS.items():
        assert _buttons(got[f"period-{k}"]) == want, k
    assert "⚠ 출근표가 비어 있는 날: 정보분배 5일" in got["period-it-closed"]  # 빈 평일 경고
    for k, want in TABLE_BUTTONS.items():
        assert _buttons(got[k]) == want, k
    assert "'취합 중'인 회차가 아니라 저장할 수 없습니다." in got["table-it-closed"]
    assert "'입력 중'인 회차가 아니라 저장할 수 없습니다." in got["table-ops-generated"]
    # 회차 목록: 회차가 다 보인다. 출근표 입력: 받는 회차만, 부서마다 채운 날 수
    assert _buttons(got["periods"]) == ["만들기"]
    assert all(f">{x.name}</a>" in got["periods"] for x in world[0].values())
    idx = got["collect-index"]
    assert "it collecting" in idx and "ops collecting" in idx and "it closed" not in idx
    assert "매칭엔진실</a> — 3 / 5일" in idx and "운영</a> — 3 / 5일" in idx
    assert "· 관리자" in got["help-admin"] and "· 근무표 관리자" in got["help-admin"]
    # 남의 근무표: 보기만(칸 링크·필터 없음), 겹친 모양 없음
    other = got["roster-other"]
    assert "hx-get" not in other and "data-d=" not in other and "bname" not in other
    # 겹친 화면: 날짜마다 구역 이름표 둘·운영팀은 "보기만"·날짜 앵커. 칸 링크와 필터는 내 근무표 구역에만(하나일 때와 같은 수)
    for both, one, days in (("roster-both", "roster-mine", 7), ("roster-both-month", "roster-month", 35)):
        b = got[both]
        assert 'class="bnames">IT 당번표 + 운영팀<' in b, both
        assert b.count('class="bname">IT 당번표<') == days and b.count("보기만") == days and b.count('id="d-') == days
        assert b.count("hx-get") == got[one].count("hx-get") and b.count("data-d=") == got[one].count("data-d=")
    assert got["day-both"].count('class="bname"') == 2 and got["day-both"].count("보기만") == 1
