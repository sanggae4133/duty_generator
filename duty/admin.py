from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.db import transaction
from django.db.models import Count

from .accounts import issue_account
from .models import Department, User
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
        # 후보는 roster()만. 지금 담당자는 퇴사·부서 해제됐어도 보여야 저장할 때 조용히 빠지지 않는다
        current = self.instance.managers.all() if self.instance.pk else User.objects.none()
        self.fields["managers"].queryset = (User.objects.roster() | current).distinct()
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


class UserAddForm(forms.ModelForm):
    """추가는 비밀번호 없이: 사용할 수 없는 비밀번호로 만들고 [계정 발급] 액션으로 임시 비밀번호를 준다."""

    class Meta:
        model = User
        fields = ["username", "name", "department", "part", "type"]

    def clean_username(self):
        v = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=v).exists():  # 대소문자만 다른 아이디는 로그인·잠금에서 헷갈린다
            raise forms.ValidationError("같은 아이디가 이미 있습니다(대소문자 구분 없음).")
        return v

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_unusable_password()
        if commit:
            user.save()
        return user


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = UserAddForm
    add_form_template = None  # 기본 안내("아이디와 비밀번호를 먼저…")가 맞지 않아 일반 추가 화면을 쓴다
    add_fieldsets = ((None, {"fields": ("username", "name", "department", "part", "type")}),)
    fieldsets = (
        (None, {"fields": ("username", "password", "must_change_password")}),
        ("근무표", {"fields": ("name", "department", "part", "type")}),
        *DjangoUserAdmin.fieldsets[2:],  # 기본 "개인정보"(이름·성·이메일)는 근무표 "이름"과 헷갈려 숨긴다(칸은 유지)
    )
    list_display = ["login_id", "name", "department", "part", "type", "is_active", "is_staff"]
    list_filter = ["department", "type", "is_active", "is_staff"]
    search_fields = ["username", "name"]
    list_select_related = ["department"]
    actions = ["issue_accounts"]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["username"].label = "아이디"  # 모델 칸은 그대로 두고 화면 라벨만
        return form

    @admin.display(description="아이디", ordering="username")
    def login_id(self, obj):
        return obj.username

    @admin.action(description="계정 발급 / 비밀번호 초기화")
    def issue_accounts(self, request, queryset):
        with transaction.atomic():  # 중간 실패 시 이미 발급된 비밀번호가 사라지지 않도록 전체 롤백
            lines = [f"{u.name}({u.username}): {issue_account(u)}" for u in queryset]
        self.message_user(request, "임시 비밀번호 — 이 화면에서만 보입니다. " + " / ".join(lines), messages.WARNING)
