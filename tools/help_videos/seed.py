"""사용법 영상 녹화용 가짜 데이터(실명 없음). record.mjs 가 빈 DUTY_DATA_DIR 에서 `manage.py shell < seed.py` 로 부른다.

계정(비밀번호 모두 Demo-pass-123): member(일반), manager(MEMS 출근표 입력 담당), admin(관리자)
"""
from datetime import timedelta

from duty import perms
from duty.models import Commute, Department, Period, User
from duty.services import alarm_settings, changes, generate, publish

PW = "Demo-pass-123"
NAMES = "김가나 이다라 박마바 최사아 정자차 강카타 조파하 윤가람 장나래 임다솜 한라온 오마루 서바다 신사랑 권아름 황자람".split()
FREE = "문하늘 배다온 노은별".split()  # 근무가 없는 사람(근무 바꾸기에서 넣을 수 있게)
SHIFTS = ["normal", "dinner", "normal", "dinner", "normal", "night", "dinner", "dawn"]

depts = {code: Department.objects.create(code=code, name=code, shifts=sh) for code, sh in [
    ("MEMS", "dawn,normal,dinner,night"), ("TMCH", "dawn,normal,dinner,night"),
    ("MD", "dawn,normal,dinner,night"), ("UI", "normal,dinner,night")]}
order = list(depts.values())
people = []
for i, n in enumerate(NAMES + FREE):
    d = order[i % 4]
    people.append(User.objects.create_user(f"{d.code}{i:02d}", password=PW, name=n, department=d,
                                           type="직원" if i in (5, 11) else "개발자", help_dismissed=True))
member = User.objects.create_user("member", password=PW, name="나사용", department=depts["MD"], type="개발자", help_dismissed=True)
manager = User.objects.create_user("manager", password=PW, name="나담당", department=depts["MEMS"], type="개발자", help_dismissed=True)
admin = User.objects.create_superuser("admin", password=PW, name="나관리", help_dismissed=True)
depts["MEMS"].managers.add(manager)
workers = people[:len(NAMES)] + [member, manager]


def fill(period, who):
    for x in period.dates():
        for i, u in enumerate(who):
            sh = SHIFTS[i % len(SHIFTS)]
            if "dawn" not in u.department.shift_keys() and sh == "dawn":
                sh = "normal"
            Commute.objects.create(period=period, date=x, member=u, shift=sh)


today = perms.today()
mon = today - timedelta(days=today.weekday())
now = Period.objects.create(name="이번 회차", start_date=mon, end_date=mon + timedelta(days=11), status=Period.Status.CLOSED)
fill(now, workers)
generate.run_generation(now, seed=1, by=admin)
publish.publish(now, mon, by=admin)
d = today if today.weekday() < 5 else mon + timedelta(days=7)
row = Commute.objects.filter(period=now, date=d, shift="normal").exclude(member__in=[member, manager]).first()
changes.change_cell(admin, d, "normal", row.member, people[-1])  # 바뀐 칸 표시용

nxt = Period.objects.create(name="다음 회차", start_date=mon + timedelta(days=14), end_date=mon + timedelta(days=25),
                            status=Period.Status.COLLECTING)
fill(nxt, [u for u in workers if u.department.code != "MEMS"])  # MEMS 는 담당자 영상에서 입력
mems = [u for u in workers if u.department.code == "MEMS"]
for x in nxt.dates()[:-1]:  # 마지막 하루만 비워 둔다
    for i, u in enumerate(mems):
        Commute.objects.create(period=nxt, date=x, member=u, shift=SHIFTS[i % len(SHIFTS)])
# 알림 화면이 "봇 미설정" 안내 대신 평소 모습으로 보이게(가짜 값, 녹화 중 실제 발송·연결은 하지 않는다)
conf = alarm_settings.current()
conf.telegram_bot_token = "1" * 10 + ":" + "DEMO" + "x" * 31
conf.telegram_bot_username = "nxt_duty_demo_bot"
alarm_settings.save(conf)
print("seeded")
