from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Count

from .accounts import issue_account
from .errors import DutyError
from .models import Department, Member
from .shifts import COMMUTE_SHIFTS


class DepartmentForm(forms.ModelForm):
    # DB에는 지금처럼 "normal,dinner,night" 문자열로 저장하고, 입력만 체크박스로 받는다
    shifts = forms.MultipleChoiceField(
        label="가능한 출근조", choices=list(COMMUTE_SHIFTS.items()), widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "출근조를 하나 이상 선택하세요."},
    )

    class Meta:
        model = Department
        fields = ["code", "name", "shifts", "managers"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["shifts"] = self.instance.shift_keys()

    def clean_shifts(self):
        picked = set(self.cleaned_data["shifts"])
        return ",".join(k for k in COMMUTE_SHIFTS if k in picked)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    form = DepartmentForm
    list_display = ["code", "name", "shift_labels", "member_count", "manager_names"]
    filter_horizontal = ["managers"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_n=Count("members", distinct=True)).prefetch_related("managers")

    @admin.display(description="가능한 출근조")
    def shift_labels(self, obj):
        return "·".join(COMMUTE_SHIFTS.get(k, k) for k in obj.shift_keys())

    @admin.display(description="인원", ordering="_n")
    def member_count(self, obj):
        return obj._n

    @admin.display(description="입력 담당자")
    def manager_names(self, obj):
        return ", ".join(m.name for m in obj.managers.all()) or "(없음)"


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "department", "part", "type", "is_active", "user"]
    list_filter = ["department", "type", "is_active"]
    search_fields = ["code", "name"]
    raw_id_fields = ["user"]
    actions = ["issue_accounts"]

    @admin.action(description="계정 발급 / 비밀번호 초기화")
    def issue_accounts(self, request, queryset):
        try:
            with transaction.atomic():  # 중간 실패 시 이미 발급된 비밀번호가 사라지지 않도록 전체 롤백
                lines = [f"{m.name}({m.code}): {issue_account(m)}" for m in queryset]
        except DutyError as e:
            self.message_user(request, str(e), messages.ERROR)
            return
        self.message_user(request, "임시 비밀번호 — 이 화면에서만 보입니다. " + " / ".join(lines), messages.WARNING)
