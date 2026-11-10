from datetime import date

from duty.models import ChangeLog, Commute, ControlDuty, Period
from duty.services.roster import api_assignments, chain, department_table, member_schedule, published_days

S = Period.Status
D = date(2026, 11, 10)


def test_chain_replace_twice():
    labels, removed, replaced = chain(["C"], [("A", "B"), ("B", "C")])
    assert labels == ["A>B>C"] and removed == [] and replaced["C"] == "B"


def test_chain_add_and_remove():
    labels, removed, _ = chain(["B", "X"], [(None, "B"), ("A", None)])
    assert labels == ["+B", "X"] and removed == ["A"]


def make_published(make_member):
    p = Period.objects.create(name="p", start_date=D, end_date=D, status=S.PUBLISHED)
    staff = make_member("직원1", type="직원")
    a, b, c = make_member("가"), make_member("나", dept="TMCH"), make_member("다")
    Commute.objects.create(period=p, date=D, member=staff, shift="normal")
    Commute.objects.create(period=p, date=D, member=b, shift="normal")
    Commute.objects.create(period=p, date=D, member=c, shift="dawn")
    ControlDuty.objects.create(period=p, date=D, slot=0, member=b)
    ChangeLog.objects.create(period=p, date=D, cell="normal", before=a, after=b)
    return p


def test_published_days_builds_cells(make_member):
    make_published(make_member)
    [day] = published_days()
    assert day.members["normal"] == ["직원1", "나"]
    assert day.cells["normal"].labels == ["직원1", "가>나"] and day.cells["normal"].changed
    assert day.cells["slot0"].labels == ["나"] and not day.cells["slot0"].changed


def test_unpublished_is_hidden(make_member):
    p = make_published(make_member)
    p.status = S.GENERATED
    p.save()
    assert published_days() == []


def test_api_assignments(make_member):
    make_published(make_member)
    rows = api_assignments(None, None)
    assert {"date": "2026-11-10", "shift": "정상", "name": "나", "replaced": "가"} in rows
    assert {"date": "2026-11-10", "shift": "08:30~09:30", "name": "나", "replaced": None} in rows
    assert {"date": "2026-11-10", "shift": "새벽", "name": "다", "replaced": None} in rows


def test_member_schedule(make_member):
    make_published(make_member)
    from duty.models import Member

    assert member_schedule(Member.objects.get(name="나"), D) == [(D, ["정상", "08:30~09:30"])]


def test_department_table_it_splits_type(make_member):
    make_published(make_member)
    title, header, rows = department_table("it")
    assert title == "IT운영본부"
    assert header[:3] == ["날짜", "요일", "구분"] and header[3] == "새벽 매칭엔진실"
    staff_row, dev_row = rows
    assert staff_row[2] == "직원" and dev_row[2] == "개발자"
    normal_tmch = header.index("정상 매매지원실")
    assert dev_row[normal_tmch] == "나"
    assert staff_row[header.index("정상 매칭엔진실")] == "직원1"


def test_chain_replaced_cleared_when_readded():
    _, _, replaced = chain(["X"], [("A", "X"), ("X", None), (None, "X")])
    assert "X" not in replaced
