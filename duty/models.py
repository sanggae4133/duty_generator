from django.conf import settings
from django.contrib.auth.models import AbstractUser, Group, UserManager as DjangoUserManager
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Func, Q, Value
from django.db.models.lookups import Exact

from .csv_io import split_reason
from .shifts import DEVELOPER, KEYS, REASONS, SHIFT_KEYS, SLOT_KEYS, STAFF, is_slot_cell, slot_index, weekdays

REASON_CHOICES = [("", "없음"), *((r, r) for r in REASONS)]


def _one_of(field: str, values, name: str) -> models.CheckConstraint:
    # SQLite에는 enum 타입이 없어 choices를 DB CHECK로도 강제한다(앱을 거치지 않은 쓰기 방지)
    return models.CheckConstraint(condition=models.Q(**{f"{field}__in": list(values)}), name=name)


def validate_chat_id(value: int) -> None:
    """텔레그램 chat_id: 개인은 양수, 그룹·단톡방은 음수. 0 은 없다."""
    if value == 0:
        raise ValidationError("0은 쓸 수 없습니다. 개인은 양수, 단톡방은 -로 시작하는 숫자입니다.")


def validate_member_name(value: str) -> None:
    # '>', ',', 줄바꿈, 앞 '+'는 라벨(A>B, +B)·CSV 문법이라 이름에 쓰면 깨진다.
    # 앞 = - @ 탭은 CSV 를 엑셀로 열 때 수식으로 실행된다
    if any(c in value for c in ">,\n\r") or value.startswith(("+", "=", "-", "@", "\t")):
        raise ValidationError("이름에 > , 줄바꿈을 쓸 수 없고 + = - @ 탭으로 시작할 수 없습니다.")
    if split_reason(value)[1]:  # 표·CSV 의 "이름(휴가)"와 헷갈린다
        raise ValidationError("이름이 (휴가)·(출장)·(교육)으로 끝날 수 없습니다.")


class InputMode(models.TextChoices):
    COLLECT = "collect", "부서별 취합"
    DIRECT = "direct", "관리자 직접 입력"


class Board(models.Model):
    """근무표 하나(IT 당번표, 시장운영실…). 회차·부서·근무 정의가 여기에 속한다."""
    InputMode = InputMode

    code = models.CharField("코드", max_length=16, unique=True, help_text="짧은 영문. IT = it")
    name = models.CharField("이름", max_length=32)
    input_mode = models.CharField("입력 방식", max_length=8, choices=InputMode.choices, default=InputMode.COLLECT)
    admin_group = models.OneToOneField(Group, on_delete=models.PROTECT, related_name="admin_board",
                                       verbose_name="관리 그룹", editable=False)

    class Meta:
        verbose_name = verbose_name_plural = "근무표"
        ordering = ["id"]
        constraints = [_one_of("input_mode", InputMode.values, "board_input_mode_valid")]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.admin_group_id is None:  # 어느 길로 만들어도 관리 그룹이 빠지지 않게
            self.admin_group = Group.objects.create(name=f"{self.name} 근무표 관리")
        super().save(*args, **kwargs)


def _key_label(key: str) -> str:
    # 관리 화면 표시는 중립적으로(시장운영실이 dawn 을 '새벽'으로 오해하지 않게). DB 값은 키 그대로
    return f"관제 {slot_index(key) + 1}" if is_slot_cell(key) else f"근무조 {SHIFT_KEYS.index(key) + 1}"


class BoardShift(models.Model):
    """근무 정의: 근무표가 쓰는 키 하나에 붙인 이름·시각·자격."""
    board = models.ForeignKey(Board, on_delete=models.PROTECT, related_name="shifts", verbose_name="근무표")
    key = models.CharField("키", max_length=8, choices=[(k, _key_label(k)) for k in KEYS])
    name = models.CharField("이름", max_length=32)
    start = models.TimeField("시작", null=True, blank=True)
    end = models.TimeField("끝", null=True, blank=True)
    eligible_shifts = models.JSONField("자격 근무조", default=list, blank=True)
    eligible_types = models.JSONField("자격 구분", default=list, blank=True)
    default_alarm = models.BooleanField("기본 알림 대상", default=False)
    active = models.BooleanField("사용", default=True)

    class Meta:
        verbose_name = verbose_name_plural = "근무 정의"
        constraints = [
            models.UniqueConstraint(fields=["board", "key"], name="boardshift_one_per_key"),
            # 이름은 CSV 열 이름·화면 라벨이 된다. 겹치면 CSV 열이 하나로 합쳐져 값이 사라지므로 DB 가 막는다
            models.UniqueConstraint(fields=["board", "name"], name="boardshift_one_per_name"),
            _one_of("key", KEYS, "boardshift_key_valid"),
            # 1단계 키(근무조·관제)는 시각이 필수이고 당일 근무만(2단계에 시각 없는 점심당번을 더한다)
            models.CheckConstraint(name="boardshift_times_valid",
                                   condition=Q(start__isnull=False, end__isnull=False, start__lt=models.F("end"))),
        ]

    def __str__(self):
        return f"{self.board} {self.name}"


class GroupKeeper(models.Model):
    """그룹 관리자: 그 그룹에 멤버를 넣고 빼기만 한다."""
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="keepers", verbose_name="그룹")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="kept_groups",
                             verbose_name="그룹 관리자")

    class Meta:
        verbose_name = verbose_name_plural = "그룹 관리자"
        constraints = [models.UniqueConstraint(fields=["group", "user"], name="groupkeeper_once")]


class Department(models.Model):
    code = models.CharField("코드", max_length=8, primary_key=True)
    name = models.CharField("이름", max_length=32, unique=True)
    shifts = models.CharField("가능한 출근조", max_length=64, help_text="쉼표 구분: dawn,normal,dinner,night")
    board = models.ForeignKey(Board, on_delete=models.PROTECT, related_name="departments", verbose_name="근무표")
    order = models.IntegerField("순서", default=99, help_text="근무표 부서 필터 순서(작은 값이 앞, 기본 99는 맨 뒤)")
    input_group = models.OneToOneField(Group, on_delete=models.PROTECT, null=True, blank=True, editable=False,
                                       related_name="input_department", verbose_name="입력 그룹")

    class Meta:
        verbose_name = verbose_name_plural = "부서"
        ordering = ["code"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # 부서별 취합 근무표의 부서는 입력 그룹이 있어야 한다(픽스처·관리 화면·서비스 어느 길로 만들어도)
        if self.input_group_id is None and self.board_id is not None and self.board.input_mode == InputMode.COLLECT:
            self.input_group = Group.objects.create(name=f"{self.name} 출근표 입력")
        super().save(*args, **kwargs)

    def shift_keys(self) -> list[str]:
        return [s for s in self.shifts.split(",") if s]

    @property
    def managers(self):
        """1단계 호환(2단계 끝에 지운다): 출근표 입력 담당 = 입력 그룹 멤버. 그룹이 없으면(직접 입력 근무표) 빈 목록."""
        return self.input_group.user_set if self.input_group_id else User.objects.none()


class UserManager(DjangoUserManager):
    def roster(self):
        """근무표 후보: 재직 중이고 부서가 있는 계정. 역사·표시에는 쓰지 않는다(퇴사자·부서 없는 계정도 보여야 함)."""
        return self.filter(department__isnull=False, is_active=True)


class User(AbstractUser):
    """로그인 계정 겸 근무표 멤버. username = 멤버 코드, department 없음 = 근무표 대상 아님(어드민 전용)."""
    name = models.CharField("이름", max_length=32, unique=True, validators=[validate_member_name])
    department = models.ForeignKey(Department, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="members", verbose_name="부서")
    part = models.CharField("파트", max_length=32, blank=True)
    type = models.CharField("구분", max_length=8, choices=[(STAFF, STAFF), (DEVELOPER, DEVELOPER)], blank=True)
    is_active = models.BooleanField("재직", default=True, help_text="끄면 로그인할 수 없고 근무표 후보에서 빠집니다.")
    must_change_password = models.BooleanField("첫 로그인 비번 변경 필요", default=False)
    help_dismissed = models.BooleanField("사용법 팝업 다시 보지 않기", default=False)
    notify_changes = models.BooleanField("내 근무가 바뀌면 알림", default=True)

    objects = UserManager()
    REQUIRED_FIELDS = ["name"]  # createsuperuser 가 이름을 묻는다

    class Meta:
        verbose_name = verbose_name_plural = "사용자"
        ordering = ["username"]
        constraints = [models.CheckConstraint(
            name="user_type_matches_department",
            condition=Q(department__isnull=False, type__in=[STAFF, DEVELOPER]) | Q(department__isnull=True, type=""),
            violation_error_message="부서가 있으면 구분(직원·개발자)을 고르고, 부서가 없으면 구분을 비워 두세요.",
        )]

    def __str__(self):
        return self.name


class PeriodStatus(models.TextChoices):
    DRAFT = "draft", "작성 중"
    COLLECTING = "collecting", "취합 중"
    CLOSED = "closed", "마감"
    GENERATED = "generated", "생성됨"
    PUBLISHED = "published", "배포됨"


class Period(models.Model):
    Status = PeriodStatus  # Meta에서 참조하려고 모듈 수준에 둔다

    name = models.CharField("이름", max_length=64)
    start_date = models.DateField("시작일")
    end_date = models.DateField("종료일")
    status = models.CharField("상태", max_length=16, choices=Status.choices, default=Status.DRAFT)
    seed = models.BigIntegerField(null=True, blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    overwrite_from = models.DateField(null=True, blank=True)
    board = models.ForeignKey(Board, on_delete=models.PROTECT, related_name="periods", verbose_name="근무표")
    # 휴장일 건너뛰기(설계 5절): 근무표를 만드는 도구가 휴장일을 건너뛴다. 2단계 전 회차는 거짓(마이그레이션 0018), 새 회차는 참
    skip_holidays = models.BooleanField("휴장일 건너뛰기", default=True)
    # 배포가 지운 행 목록: ["c", 회차 id, 날짜, 멤버 id, 출근조, 사유] | ["a", 회차 id, 날짜, 멤버 id, 당번 칸]. 배포 취소 때 되살린다.
    # 사유 칸이 없는 옛 c 행(2단계 전 배포)도 읽는다. null = 되돌릴 정보 없음
    publish_undo = models.JSONField(null=True, blank=True, editable=False)
    # 이 번호 이하의 ChangeLog 는 근무표·알림에 쓰지 않는다(배포 취소 때 그 시점 최대 번호로 정함). 시각 대신 번호라 시계와 무관
    log_floor = models.BigIntegerField(default=0, editable=False)

    class Meta:
        verbose_name = verbose_name_plural = "회차"
        constraints = [
            _one_of("status", PeriodStatus.values, "period_status_valid"),
            models.CheckConstraint(condition=models.Q(start_date__lte=models.F("end_date")), name="period_dates_ordered"),
        ]

    def __str__(self):
        return self.name

    def dates(self):
        return weekdays(self.start_date, self.end_date)


class HolidaySource(models.TextChoices):
    AUTO = "auto", "자동"
    MANUAL = "manual", "직접 추가"


class Holiday(models.Model):
    """휴장일(모든 근무표 공통, 설계 5절). auto = services/holidays.sync 가 넣은 행, manual = 슈퍼유저가 관리 화면에서 추가.
    sync 는 있는 행을 건드리지 않으므로 끈 자동 휴장일은 꺼진 채 남는다."""
    Source = HolidaySource

    date = models.DateField("날짜", unique=True)
    name = models.CharField("이름", max_length=64)
    source = models.CharField("출처", max_length=8, choices=Source.choices, default=Source.MANUAL)
    active = models.BooleanField("휴장", default=True, help_text="끄면 휴장일이 아닙니다(이미 있는 배정은 그대로).")

    class Meta:
        verbose_name = verbose_name_plural = "휴장일"
        ordering = ["date"]
        constraints = [_one_of("source", HolidaySource.values, "holiday_source_valid")]

    def __str__(self):
        return f"{self.date} {self.name}"


def _strftime(fmt: str):
    """SQLite strftime(fmt, date). %w: 일요일 0 … 월요일 1, %d: 01~31."""
    return Func(Value(fmt), F("date"), function="strftime", output_field=models.CharField())


class MemoScope(models.TextChoices):
    DAY = "day", "날"
    WEEK = "week", "주"
    MONTH = "month", "달"


class Memo(models.Model):
    """메모(설계 4.8·6.5): 회차가 아니라 (근무표, 날짜)에 붙는다. week = 그 주 월요일, month = 그 달 1일에 저장한다.
    no_work(근무 없음)는 날 메모에만: 그날은 배정이 늘 비어 있고 근무 변경을 막는다(services/memos.save 가 배정을 지운다)."""
    Scope = MemoScope

    board = models.ForeignKey(Board, on_delete=models.PROTECT, related_name="memos", verbose_name="근무표")
    scope = models.CharField("범위", max_length=8, choices=Scope.choices)
    date = models.DateField("날짜")
    text = models.CharField("내용", max_length=500, blank=True)
    no_work = models.BooleanField("근무 없음", default=False)

    class Meta:
        verbose_name = verbose_name_plural = "메모"
        constraints = [
            models.UniqueConstraint(fields=["board", "scope", "date"], name="memo_one_per_date"),
            _one_of("scope", MemoScope.values, "memo_scope_valid"),
            models.CheckConstraint(name="memo_no_work_day_only", condition=Q(no_work=False) | Q(scope="day")),
            models.CheckConstraint(name="memo_not_empty", condition=Q(no_work=True) | ~Q(text="")),
            # 주 메모는 월요일, 달 메모는 1일에만(서비스가 맞춰 저장한다). __week_day 같은 lookup 은 Django 가 연결마다
            # 등록하는 함수(django_date_extract)를 CHECK 에 넣어 sqlite3 셸에서 쓰기가 깨지므로 SQLite 내장 strftime 으로
            models.CheckConstraint(name="memo_date_aligned", condition=(
                Q(scope="day") | Q(Exact(_strftime("%w"), "1"), scope="week") | Q(Exact(_strftime("%d"), "01"), scope="month"))),
        ]


class PeriodEvent(models.Model):
    """회차 상태 변경 기록. from_status '' = 새로 만듦."""
    period = models.ForeignKey(Period, on_delete=models.PROTECT, related_name="events")  # 기록 있는 회차는 지우지 않는다
    at = models.DateTimeField(auto_now_add=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    from_status = models.CharField(max_length=16, blank=True, choices=PeriodStatus.choices)
    to_status = models.CharField(max_length=16, choices=PeriodStatus.choices)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["at", "id"]
        constraints = [
            _one_of("from_status", ["", *PeriodStatus.values], "periodevent_from_valid"),
            _one_of("to_status", PeriodStatus.values, "periodevent_to_valid"),
        ]


class Commute(models.Model):
    period = models.ForeignKey(Period, on_delete=models.CASCADE)
    date = models.DateField()
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    shift = models.CharField(max_length=8, choices=[(k, k) for k in SHIFT_KEYS])
    reason = models.CharField(max_length=4, choices=REASON_CHOICES, blank=True, default="")  # 있으면 근무로 치지 않는다

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["period", "date", "member"], name="commute_one_shift_per_day"),
            _one_of("shift", SHIFT_KEYS, "commute_shift_valid"),
            _one_of("reason", ["", *REASONS], "commute_reason_valid"),
        ]
        indexes = [models.Index(fields=["date"])]


class DutyAssignment(models.Model):
    """당번 배정 한 칸(1단계는 장중관제 slot0~slot9). 생성이 만들고 근무 변경이 바꾼다."""
    period = models.ForeignKey(Period, on_delete=models.CASCADE, related_name="duty_assignments")
    date = models.DateField()
    cell = models.CharField(max_length=8, choices=[(k, k) for k in SLOT_KEYS])
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["period", "date", "cell", "member"], name="dutyassignment_once"),
            # 관제 칸은 칸당 한 명(DB가 계속 보장)
            models.UniqueConstraint(fields=["period", "date", "cell"], condition=Q(cell__startswith="slot"),
                                    name="dutyassignment_one_per_slot"),
            _one_of("cell", SLOT_KEYS, "dutyassignment_cell_valid"),
        ]
        indexes = [models.Index(fields=["date"])]


class ChangeLog(models.Model):
    at = models.DateTimeField(auto_now_add=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)  # null = 예전 시트 가져오기 기록. 계정은 삭제 대신 비활성화
    period = models.ForeignKey(Period, on_delete=models.PROTECT)  # 변경 기록은 남긴다: 기록 있는 회차는 삭제 불가
    date = models.DateField()
    cell = models.CharField(max_length=8)  # dawn|normal|dinner|night|slot0..slot9
    before = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    after = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    notified = models.BooleanField(default=False)  # 당사자에게 '근무 변경' 알림을 보냈는지(작업자가 표시)
    # 사유(근무조 칸만). 사유만 바뀐 기록은 before == after: 이력에만 보이고 화면 변경 표시·변경 알림은 건너뛴다
    reason_before = models.CharField(max_length=4, choices=REASON_CHOICES, blank=True, default="")
    reason_after = models.CharField(max_length=4, choices=REASON_CHOICES, blank=True, default="")

    class Meta:
        ordering = ["at", "id"]
        constraints = [
            _one_of("cell", KEYS, "changelog_cell_valid"),
            _one_of("reason_before", ["", *REASONS], "changelog_reason_before_valid"),
            _one_of("reason_after", ["", *REASONS], "changelog_reason_after_valid"),
            models.CheckConstraint(condition=models.Q(before__isnull=False) | models.Q(after__isnull=False), name="changelog_not_empty"),
        ]


class RosterPref(models.Model):
    """사용자별 근무표 필터·보기 저장값. 빈 목록 = 전체."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    depts = models.JSONField(default=list)
    types = models.JSONField(default=list)
    shifts = models.JSONField(default=list)
    view = models.CharField(max_length=5, choices=[("week", "주간"), ("month", "월간")], default="week")
    history = models.BooleanField(default=True)  # 변경 내역(A>B·+B·취소선) 표시. 끄면 지금 근무하는 사람만
    board = models.ForeignKey(Board, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")  # 마지막으로 본 근무표

    class Meta:
        constraints = [_one_of("view", ("week", "month"), "rosterpref_view_valid")]


class CalendarFeed(models.Model):
    """사용자별 캘린더 구독 주소. 토큰 원문은 저장하지 않고 sha256 만 둔다."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calendar_feed")
    token_hash = models.CharField(max_length=64, unique=True)
    issued_at = models.DateTimeField()
    shifts = models.JSONField(default=list, blank=True)  # 넣을 근무(dawn·normal·dinner·night·slots). 빈 목록 = 전부


class AlarmKind(models.TextChoices):
    PERSONAL = "personal", "개인"
    REPORT = "report", "보고서형"


class AlarmTiming(models.TextChoices):
    BEFORE_START = "before_start", "시작 전"
    DAYS = "days", "일 전"
    BIZDAYS = "bizdays", "영업일 전"


class AlarmChannel(models.TextChoices):
    TELEGRAM = "telegram", "텔레그램"
    PUSH = "push", "푸시"


class AlarmSettings(models.Model):
    """알림 봇·푸시 키(한 행, pk=1). 슈퍼유저가 관리 화면 → 알림 설정에서 고친다. 읽기는 services.alarm_settings.current()."""
    telegram_bot_token = models.CharField(
        "텔레그램 봇 토큰", max_length=200, blank=True,
        validators=[RegexValidator(r"^\d+:[A-Za-z0-9_-]+$", "봇 토큰 형식이 아닙니다(숫자:영문·숫자).")])
    telegram_bot_username = models.CharField(
        "텔레그램 봇 사용자명", max_length=33, blank=True, help_text="@ 없이(붙여도 저장할 때 뗀다).",
        validators=[RegexValidator(r"^@?[A-Za-z0-9_]{5,32}$", "봇 사용자명은 영문·숫자·_ 5~32자입니다.")])
    ops_chat_id = models.BigIntegerField(
        "장애 알림 받을 chat_id", null=True, blank=True, validators=[validate_chat_id],
        help_text="개인은 양수, 단톡방은 음수(-100…, 봇을 방에 초대해 둔다). 비우면 장애 알림은 worker.log 에만 남는다.")
    vapid_public_key = models.CharField("웹 푸시 공개키", max_length=200, blank=True)
    vapid_private_key = models.CharField("웹 푸시 개인키", max_length=200, blank=True)
    vapid_subject = models.CharField(
        "웹 푸시 연락처", max_length=200, default="mailto:admin@localhost",
        help_text="mailto:주소 형식. 푸시 서비스가 문제 시 연락하는 주소.")
    updated_at = models.DateTimeField("고친 시각", auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = "알림 설정"
        constraints = [models.CheckConstraint(condition=Q(pk=1), name="alarmsettings_single_row")]

    def __str__(self):
        return "알림 설정"

    def save(self, *args, **kwargs):
        self.telegram_bot_username = self.telegram_bot_username.lstrip("@")
        super().save(*args, **kwargs)

    @property
    def telegram_on(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def bot_ready(self) -> bool:
        """[텔레그램 연결] 자동 연결까지 가능"""
        return bool(self.telegram_bot_token and self.telegram_bot_username)

    @property
    def push_on(self) -> bool:
        return bool(self.vapid_public_key and self.vapid_private_key)

    def sender_config(self):
        from .alarms.senders import Config
        return Config(self.telegram_bot_token, self.vapid_private_key, self.vapid_subject)


class TelegramAlarmProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="telegram_alarm")
    chat_id = models.CharField("텔레그램 chat_id", max_length=32, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    last_test_at = models.DateTimeField(null=True, blank=True)
    link_code = models.CharField(max_length=32, null=True, blank=True, unique=True)  # 텔레그램 자동 연결 일회용 코드
    link_expires_at = models.DateTimeField(null=True, blank=True)


class PushAlarmSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.CharField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    label = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AlarmRule(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alarm_rules")
    enabled = models.BooleanField("켬", default=True)
    kind = models.CharField("종류", max_length=8, choices=AlarmKind.choices)
    timing = models.CharField("기준", max_length=12, choices=AlarmTiming.choices)
    offset = models.IntegerField("간격")
    at_minute = models.IntegerField("발송 시각(분)", default=0)
    telegram = models.BooleanField("텔레그램", default=False)
    push = models.BooleanField("푸시", default=False)
    shifts = models.JSONField("스케줄", default=list)
    depts = models.JSONField("부서", default=list)
    types = models.JSONField("유형", default=list)
    # 보고서 규칙의 근무표. 개인 규칙은 비운다(주인 부서의 근무표)
    board = models.ForeignKey(Board, on_delete=models.PROTECT, null=True, blank=True, related_name="alarm_rules",
                              verbose_name="근무표")

    class Meta:
        ordering = ["id"]
        constraints = [
            _one_of("kind", AlarmKind.values, "alarmrule_kind_valid"),
            _one_of("timing", AlarmTiming.values, "alarmrule_timing_valid"),
            models.CheckConstraint(name="alarmrule_offset_range", condition=(
                Q(timing="before_start", offset__gte=1, offset__lte=10080)
                | Q(timing="days", offset__gte=0, offset__lte=30)
                | Q(timing="bizdays", offset__gte=1, offset__lte=30))),
            models.CheckConstraint(name="alarmrule_at_minute_range", condition=Q(at_minute__gte=0, at_minute__lte=1439)),
            models.CheckConstraint(name="alarmrule_before_start_no_time", condition=~Q(timing="before_start") | Q(at_minute=0)),
            models.CheckConstraint(name="alarmrule_has_channel", condition=Q(telegram=True) | Q(push=True)),
            models.CheckConstraint(name="alarmrule_personal_no_filters", condition=Q(kind="report") | Q(depts=[], types=[])),
            # 개인 = 주인의 근무표(null), 보고서 = 근무표 하나
            models.CheckConstraint(name="alarmrule_board_by_kind", condition=(
                Q(kind="personal", board__isnull=True) | Q(kind="report", board__isnull=False))),
            models.UniqueConstraint(name="alarmrule_unique_personal", condition=Q(kind="personal"),
                                    fields=["user", "kind", "timing", "offset", "at_minute", "shifts", "depts", "types"]),
            models.UniqueConstraint(name="alarmrule_unique_report", condition=Q(kind="report"),
                                    fields=["user", "kind", "board", "timing", "offset", "at_minute", "shifts", "depts",
                                            "types"]),
        ]


class AlarmDeliveryStatus(models.TextChoices):
    SENT = "sent", "성공"
    FAILED = "failed", "실패"


class AlarmDelivery(models.Model):
    """목적지별 발송 시도 기록. destination = 텔레그램 chat_id 또는 sub:<구독 id>."""
    rule = models.ForeignKey(AlarmRule, on_delete=models.CASCADE, related_name="deliveries")
    date = models.DateField()
    cell = models.CharField(max_length=8)  # KEYS 또는 "report"
    channel = models.CharField(max_length=8, choices=AlarmChannel.choices)
    destination = models.CharField(max_length=64)
    status = models.CharField(max_length=8, choices=AlarmDeliveryStatus.choices)
    attempts = models.IntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    content_hash = models.CharField(max_length=64)  # 마지막 시도 내용
    last_sent_hash = models.CharField(max_length=64, null=True, blank=True)  # 마지막 성공 내용
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            _one_of("channel", AlarmChannel.values, "alarmdelivery_channel_valid"),
            _one_of("cell", [*KEYS, "report"], "alarmdelivery_cell_valid"),
            _one_of("status", AlarmDeliveryStatus.values, "alarmdelivery_status_valid"),
            models.CheckConstraint(name="alarmdelivery_attempts_nonneg", condition=Q(attempts__gte=0)),
            models.UniqueConstraint(fields=["rule", "date", "cell", "channel", "destination"], name="alarmdelivery_once"),
        ]
