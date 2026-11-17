"""사용법 영상 녹화용 가짜 데이터(실명 없음). record.mjs 가 빈 DUTY_DATA_DIR 에서 `manage.py shell < seed.py` 로 부른다.

계정(비밀번호 모두 Demo-pass-123): member(일반), manager(MEMS 출근표 입력 그룹), admin(슈퍼유저 + IT 근무표 관리 그룹)
2단계 화면 예시: 휴장일(이번 회차), 날·주·달 메모, 근무 없음 날(다음 회차), 사유(휴가) 한 명, 점심당번(생성이 새벽 근무자로 채움)
"""
from datetime import time, timedelta

from duty import perms
from duty.models import Commute, Department, Holiday, Period, User
from duty.services import alarm_settings, boards, changes, generate, holidays, memos, publish

PW = "Demo-pass-123"
NAMES = "김가나 이다라 박마바 최사아 정자차 강카타 조파하 윤가람 장나래 임다솜 한라온 오마루 서바다 신사랑 권아름 황자람".split()
FREE = "문하늘 배다온 노은별".split()  # 근무가 없는 사람(근무 바꾸기에서 넣을 수 있게)
SHIFTS = ["normal", "dinner", "normal", "dinner", "normal", "night", "dawn", "dinner"]  # 7번째(MD 부서) = 새벽 → 점심당번
LUNCH = (time(11, 30), time(12, 30))  # 운영 마이그레이션 0022 가 IT 부서에 넣는 점심 시각과 같다

if User.objects.exists():  # 고정 비밀번호 계정을 만드니 운영 DB 에서 돌면 안 된다
    raise SystemExit("빈 임시 DB 에서만 돌립니다. 이미 계정이 있는 DB 입니다(DUTY_DATA_DIR 을 새 빈 폴더로 지정하세요).")

it = boards.it_board()  # 마이그레이션이 빈 DB 에도 만들어 둔 IT 당번표
depts = {code: Department.objects.create(code=code, name=code, shifts=sh, board=it, order=i, lunch_start=LUNCH[0], lunch_end=LUNCH[1])
         for i, (code, sh) in enumerate([
    ("MEMS", "dawn,normal,dinner,night"), ("TMCH", "dawn,normal,dinner,night"),
    ("MD", "dawn,normal,dinner,night"), ("UI", "normal,dinner,night")])}
order = list(depts.values())
people = []
for i, n in enumerate(NAMES + FREE):
    d = order[i % 4]
    people.append(User.objects.create_user(f"{d.code}{i:02d}", password=PW, name=n, department=d,
                                           type="직원" if i in (5, 11) else "개발자", help_dismissed=True))
member = User.objects.create_user("member", password=PW, name="나사용", department=depts["MD"], type="개발자", help_dismissed=True)
manager = User.objects.create_user("manager", password=PW, name="나담당", department=depts["MEMS"], type="개발자", help_dismissed=True)
admin = User.objects.create_superuser("admin", password=PW, name="나관리", help_dismissed=True)
depts["MEMS"].ensure_input_group().user_set.add(manager)  # 출근표 입력 담당 = 부서 입력 그룹 멤버(첫 담당자라 그룹을 만든다)
it.admin_group.user_set.add(admin)  # 근무표 관리자 = IT 근무표 관리 그룹 멤버(슈퍼유저라고 자동으로 관리자가 아니다)
workers = people[:len(NAMES)] + [member, manager]


def fill(period, who):
    skip = boards.skip_dates(period)  # 휴장일·근무 없음 날은 비운다(입력 표가 그날 행을 잠그는 것과 같게)
    for x in period.dates():
        if x in skip:
            continue
        for i, u in enumerate(who):
            sh = SHIFTS[i % len(SHIFTS)]
            if "dawn" not in u.department.shift_keys() and sh == "dawn":
                sh = "normal"
            Commute.objects.create(period=period, date=x, member=u, shift=sh)


today = perms.today()
mon = today - timedelta(days=today.weekday())
now = Period.objects.create(board=it, name="이번 회차", start_date=mon, end_date=mon + timedelta(days=11),
                            status=Period.Status.CLOSED)
nxt = Period.objects.create(board=it, name="다음 회차", start_date=mon + timedelta(days=14), end_date=mon + timedelta(days=25),
                            status=Period.Status.COLLECTING)
holidays.sync(today)  # 실제 공휴일(작업자가 하는 일)
# 가짜 임시 휴장일: 오늘이 월~목이면 이번 주 금요일, 아니면 다음 주 금요일(영상 첫 화면 또는 [월간]에 보이게)
Holiday.objects.update_or_create(date=mon + timedelta(days=4 if today.weekday() < 4 else 11),
                                 defaults={"name": "임시 휴장일", "source": Holiday.Source.MANUAL, "active": True})
memos.save(admin, it, "day", nxt.start_date + timedelta(days=2), "부서 워크숍", no_work=True)  # 근무 없음 날
fill(now, workers)
generate.run_generation(now, seed=1, by=admin)  # 장중관제 + 점심당번(새벽 근무자)
publish.publish(now, mon, by=admin)
skip = boards.skip_dates(now)
d = next(x for x in now.dates() if x >= today and x not in skip)  # 오늘(주말이면 다음 평일)
row = Commute.objects.filter(period=now, date=d, shift="normal").exclude(member__in=[member, manager]).first()
changes.change_cell(admin, it, d, "normal", row.member, people[-1])  # 바뀐 칸 표시용
off = Commute.objects.filter(period=now, date=d, shift="dinner").exclude(member__in=[member, manager]).first()
changes.set_reason(admin, it, d, off.member, "휴가")  # 취소선·회색 이름(휴가)
memos.save(admin, it, "day", d, "분기 보고 마감")
memos.save(admin, it, "week", d, "목요일 오후 전산 점검")
memos.save(admin, it, "month", d, "본부 점심: 김가나, 이다라")

fill(nxt, [u for u in workers if u.department.code != "MEMS"])  # MEMS 는 담당자 영상에서 입력
mems = [u for u in workers if u.department.code == "MEMS"]
nskip = boards.skip_dates(nxt)
for x in [x for x in nxt.dates() if x not in nskip][:-1]:  # 마지막 하루만 비워 둔다
    for i, u in enumerate(mems):
        Commute.objects.create(period=nxt, date=x, member=u, shift=SHIFTS[i % len(SHIFTS)])
# 알림 화면이 "봇 미설정" 안내 대신 평소 모습으로 보이게(가짜 값, 녹화 중 실제 발송·연결은 하지 않는다)
conf = alarm_settings.current()
conf.telegram_bot_token = "1" * 10 + ":" + "DEMO" + "x" * 31
conf.telegram_bot_username = "nxt_duty_demo_bot"
alarm_settings.save(conf)
print("seeded")
