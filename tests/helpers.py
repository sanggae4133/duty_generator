"""여러 테스트 파일이 같이 쓰는 회차 헬퍼(픽스처 아님)."""
from duty.models import Board, Commute, DutyAssignment, Period
from duty.shifts import weekdays


def make_period(name, start, end, status, member, board=None, slots=True):
    """평일마다 member 를 정상 출근 + (slots 면) 장중관제 첫 칸에. board 를 안 주면 IT 근무표(make_member·me 픽스처가 만든다)."""
    p = Period.objects.create(board=board or Board.objects.get(code="it"), name=name, start_date=start, end_date=end, status=status)
    for x in weekdays(start, end):
        Commute.objects.create(period=p, date=x, member=member, shift="normal")
        if slots:
            DutyAssignment.objects.create(period=p, date=x, cell="slot0", member=member)
    return p


def rows(p):
    """회차의 (출근 행, 당번 행) — 정렬해서 비교용."""
    c = sorted(Commute.objects.filter(period=p).values_list("date", "member_id", "shift"))
    a = sorted(DutyAssignment.objects.filter(period=p).values_list("date", "member_id", "cell"))
    return c, a
