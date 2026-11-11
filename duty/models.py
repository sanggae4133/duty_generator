from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from .shifts import CELLS, COMMUTE_SHIFTS, CONTROL_SLOTS, DEVELOPER, STAFF, weekdays


def _one_of(field: str, values, name: str) -> models.CheckConstraint:
    # SQLite에는 enum 타입이 없어 choices를 DB CHECK로도 강제한다(앱을 거치지 않은 쓰기 방지)
    return models.CheckConstraint(condition=models.Q(**{f"{field}__in": list(values)}), name=name)


def validate_member_name(value: str) -> None:
    # '>', ',', 줄바꿈, 앞 '+'는 라벨(A>B, +B)·CSV 문법이라 이름에 쓰면 깨진다
    if any(c in value for c in ">,\n\r") or value.startswith("+"):
        raise ValidationError("이름에 > , 줄바꿈을 쓸 수 없고 +로 시작할 수 없습니다.")


class Department(models.Model):
    code = models.CharField("코드", max_length=8, primary_key=True)
    name = models.CharField("이름", max_length=32, unique=True)
    shifts = models.CharField("가능한 출근조", max_length=64, help_text="쉼표 구분: dawn,normal,dinner,night")
    managers = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="managed_departments", verbose_name="입력 담당자")

    class Meta:
        verbose_name = verbose_name_plural = "부서"
        ordering = ["code"]

    def __str__(self):
        return self.name

    def shift_keys(self) -> list[str]:
        return [s for s in self.shifts.split(",") if s]


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


class Commute(models.Model):
    period = models.ForeignKey(Period, on_delete=models.CASCADE)
    date = models.DateField()
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    shift = models.CharField(max_length=8, choices=list(COMMUTE_SHIFTS.items()))

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["period", "date", "member"], name="commute_one_shift_per_day"),
            _one_of("shift", COMMUTE_SHIFTS, "commute_shift_valid"),
        ]
        indexes = [models.Index(fields=["date"])]


class ControlDuty(models.Model):
    period = models.ForeignKey(Period, on_delete=models.CASCADE)
    date = models.DateField()
    slot = models.PositiveSmallIntegerField()
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["period", "date", "slot"], name="duty_one_member_per_slot"),
            models.CheckConstraint(condition=models.Q(slot__lt=len(CONTROL_SLOTS)), name="duty_slot_range"),
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

    class Meta:
        ordering = ["at", "id"]
        constraints = [
            _one_of("cell", CELLS, "changelog_cell_valid"),
            models.CheckConstraint(condition=models.Q(before__isnull=False) | models.Q(after__isnull=False), name="changelog_not_empty"),
        ]


class RosterPref(models.Model):
    """사용자별 근무표 필터·보기 저장값. 빈 목록 = 전체."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    depts = models.JSONField(default=list)
    types = models.JSONField(default=list)
    shifts = models.JSONField(default=list)
    view = models.CharField(max_length=5, choices=[("week", "주간"), ("month", "월간")], default="week")

    class Meta:
        constraints = [_one_of("view", ("week", "month"), "rosterpref_view_valid")]


class CalendarFeed(models.Model):
    """사용자별 캘린더 구독 주소. 토큰 원문은 저장하지 않고 sha256 만 둔다."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calendar_feed")
    token_hash = models.CharField(max_length=64, unique=True)
    issued_at = models.DateTimeField()


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
    ops_chat_id = models.PositiveBigIntegerField(
        "장애 알림 받을 chat_id", null=True, blank=True, validators=[MinValueValidator(1)],
        help_text="관리자 개인 텔레그램 chat_id(숫자). 비우면 장애 알림은 worker.log 에만 남는다.")
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
            models.UniqueConstraint(name="alarmrule_unique",
                                    fields=["user", "kind", "timing", "offset", "at_minute", "shifts", "depts", "types"]),
        ]


class AlarmDeliveryStatus(models.TextChoices):
    SENT = "sent", "성공"
    FAILED = "failed", "실패"


class AlarmDelivery(models.Model):
    """목적지별 발송 시도 기록. destination = 텔레그램 chat_id 또는 sub:<구독 id>."""
    rule = models.ForeignKey(AlarmRule, on_delete=models.CASCADE, related_name="deliveries")
    date = models.DateField()
    cell = models.CharField(max_length=8)  # CELLS 또는 "report"
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
            _one_of("cell", [*CELLS, "report"], "alarmdelivery_cell_valid"),
            _one_of("status", AlarmDeliveryStatus.values, "alarmdelivery_status_valid"),
            models.CheckConstraint(name="alarmdelivery_attempts_nonneg", condition=Q(attempts__gte=0)),
            models.UniqueConstraint(fields=["rule", "date", "cell", "channel", "destination"], name="alarmdelivery_once"),
        ]
