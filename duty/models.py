from django.conf import settings
from django.db import models

from .shifts import COMMUTE_SHIFTS, DEVELOPER, STAFF, weekdays


class Department(models.Model):
    code = models.CharField("코드", max_length=8, primary_key=True)
    name = models.CharField("이름", max_length=32, unique=True)
    shifts = models.CharField("가능한 출근조", max_length=64, help_text="쉼표 구분: dawn,normal,dinner,night")
    managers = models.ManyToManyField("Member", blank=True, related_name="managed_departments", verbose_name="입력 담당자")

    class Meta:
        verbose_name = verbose_name_plural = "부서"
        ordering = ["code"]

    def __str__(self):
        return self.name

    def shift_keys(self) -> list[str]:
        return [s for s in self.shifts.split(",") if s]


class Member(models.Model):
    code = models.CharField("코드", max_length=16, unique=True)
    name = models.CharField("이름", max_length=32, unique=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="members", verbose_name="부서")
    part = models.CharField("파트", max_length=32, blank=True)
    type = models.CharField("구분", max_length=8, choices=[(STAFF, STAFF), (DEVELOPER, DEVELOPER)])
    is_active = models.BooleanField("재직", default=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="member")
    must_change_password = models.BooleanField("첫 로그인 비번 변경 필요", default=False)

    class Meta:
        verbose_name = verbose_name_plural = "멤버"
        ordering = ["code"]

    def __str__(self):
        return self.name


class Period(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "작성 중"
        COLLECTING = "collecting", "취합 중"
        CLOSED = "closed", "마감"
        GENERATED = "generated", "생성됨"
        PUBLISHED = "published", "배포됨"

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

    def __str__(self):
        return self.name

    def dates(self):
        return weekdays(self.start_date, self.end_date)


class Commute(models.Model):
    period = models.ForeignKey(Period, on_delete=models.CASCADE)
    date = models.DateField()
    member = models.ForeignKey(Member, on_delete=models.PROTECT)
    shift = models.CharField(max_length=8, choices=list(COMMUTE_SHIFTS.items()))

    class Meta:
        constraints = [models.UniqueConstraint(fields=["period", "date", "member"], name="commute_one_shift_per_day")]
        indexes = [models.Index(fields=["date"])]


class ControlDuty(models.Model):
    period = models.ForeignKey(Period, on_delete=models.CASCADE)
    date = models.DateField()
    slot = models.PositiveSmallIntegerField()
    member = models.ForeignKey(Member, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["period", "date", "slot"], name="duty_one_member_per_slot"),
            models.UniqueConstraint(fields=["period", "date", "member"], name="duty_one_slot_per_member"),
        ]
        indexes = [models.Index(fields=["date"])]


class ChangeLog(models.Model):
    at = models.DateTimeField(auto_now_add=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)  # null = import. 계정은 삭제 대신 비활성화
    period = models.ForeignKey(Period, on_delete=models.CASCADE)
    date = models.DateField()
    cell = models.CharField(max_length=8)  # dawn|normal|dinner|night|slot0..slot9
    before = models.ForeignKey(Member, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    after = models.ForeignKey(Member, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["at", "id"]
