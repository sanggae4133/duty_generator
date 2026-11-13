from django import forms
from django.core.exceptions import PermissionDenied
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.db import transaction
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse
from py_vapid import _check_sub

from .accounts import issue_account
from .models import AlarmSettings, Department, User
from .services import alarm_settings
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
        ("도움말·알림", {"fields": ("help_dismissed", "notify_changes"),
                     "description": "'사용법 팝업 다시 보지 않기'를 끄면 다음 로그인 때 사용법 팝업이 다시 뜹니다."}),
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

    @admin.action(description="계정 발급 / 비밀번호 초기화", permissions=["change"])
    def issue_accounts(self, request, queryset):
        if not request.user.is_superuser:  # 관리 화면 자체가 슈퍼유저 전용이지만 액션에서도 한 번 더
            raise PermissionDenied
        mine = queryset.filter(pk=request.user.pk).exists()
        queryset = queryset.exclude(pk=request.user.pk)  # 자기 비밀번호가 바뀌면 세션과 함께 이 목록도 사라진다
        with transaction.atomic():  # 중간 실패 시 이미 발급된 비밀번호가 사라지지 않도록 전체 롤백
            lines = [f"{u.name}({u.username}): {issue_account(u)}" for u in queryset]
        if mine:
            self.message_user(request, "자기 계정은 발급에서 뺐습니다. 내 비밀번호는 메뉴의 [비밀번호]에서 바꾸세요.",
                              messages.INFO)
        if lines:
            self.message_user(request, "임시 비밀번호 — 이 화면에서만 보입니다. 사람마다 1:1로만 전달하세요. "
                              + " / ".join(lines), messages.WARNING)


class AlarmSettingsForm(forms.ModelForm):
    """토큰은 화면에 다시 내보내지 않는다: 비워 두면 그대로, 넣으면 교체, [토큰 지우기]로 비움."""
    telegram_bot_token = forms.CharField(
        label="텔레그램 봇 토큰", required=False, strip=True,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "off"}),
        help_text="@BotFather 가 준 토큰. 비워 두면 지금 값을 그대로 둔다. 바꾸면 모든 사용자의 텔레그램 연결을 다시 해야 한다.")
    clear_token = forms.BooleanField(label="토큰 지우기", required=False,
                                     help_text="체크하고 저장하면 토큰을 비운다(텔레그램 알림이 꺼진다).")
    regenerate_push_keys = forms.BooleanField(
        label="푸시 키 다시 만들기", required=False,
        help_text="체크하고 저장하면 새 키를 만들고 모든 기기의 푸시 구독이 끊긴다. "
                  "사용자마다 [이 기기에서 푸시 받기]를 다시 눌러야 한다. 키가 유출됐을 때만 쓴다.")

    class Meta:
        model = AlarmSettings
        fields = ["telegram_bot_token", "clear_token", "telegram_bot_username", "ops_chat_id", "vapid_subject",
                  "regenerate_push_keys"]

    def clean_vapid_subject(self):
        v = self.cleaned_data["vapid_subject"].strip()
        # 발송 때 py_vapid 가 쓰는 검사와 같은 것으로(여기서 통과하면 서명 단계에서 걸리지 않는다)
        if not v or any(c.isspace() for c in v) or not _check_sub(v):
            raise forms.ValidationError("mailto:주소@도메인 또는 https://호스트 형식이어야 합니다(예: mailto:admin@example.com).")
        return v

    def clean_telegram_bot_token(self):
        v = self.cleaned_data["telegram_bot_token"]
        if self.data.get("clear_token"):
            return ""
        return v or self.instance.telegram_bot_token


@admin.register(AlarmSettings)
class AlarmSettingsAdmin(admin.ModelAdmin):
    form = AlarmSettingsForm
    readonly_fields = ["token_status", "push_status", "updated_at"]
    fieldsets = (
        ("텔레그램", {"fields": ("token_status", "telegram_bot_token", "clear_token", "telegram_bot_username",
                              "ops_chat_id"),
                    "description": "토큰과 사용자명이 둘 다 있어야 사용자가 [텔레그램 연결]을 쓸 수 있다. "
                                   "이 봇은 이 웹앱만 써야 한다(다른 프로그램이 같은 봇을 쓰면 연결 확인이 실패한다)."}),
        ("웹 푸시", {"fields": ("push_status", "vapid_subject", "regenerate_push_keys"),
                   "description": "푸시 키는 처음 필요할 때 자동으로 만든다."}),
        (None, {"fields": ("updated_at",)}),
    )

    @admin.display(description="지금 토큰")
    def token_status(self, obj):
        t = obj.telegram_bot_token
        return f"…{t[-4:]} (끝 4자리)" if t else "(없음 — 텔레그램 알림 꺼짐)"

    @admin.display(description="푸시 키")
    def push_status(self, obj):
        return "있음" if obj.push_on else "아직 없음(처음 필요할 때 만든다)"

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not AlarmSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        if not self.has_view_or_change_permission(request):
            return super().changelist_view(request, extra_context)  # 권한 없음 처리는 Django 에 맡긴다
        return redirect(reverse("admin:duty_alarmsettings_change", args=[AlarmSettings.objects.get_or_create(pk=1)[0].pk]))

    def save_model(self, request, obj, form, change):
        n = alarm_settings.save(obj, regenerate_push_keys=form.cleaned_data.get("regenerate_push_keys", False))
        if form.cleaned_data.get("regenerate_push_keys"):
            self.message_user(request, "푸시 키를 새로 만들고 모든 기기 구독을 지웠습니다. "
                                       "사용자마다 [이 기기에서 푸시 받기]를 다시 눌러야 합니다.", messages.WARNING)
        if n:
            self.message_user(request, f"봇이 바뀌어 {n}명의 텔레그램 연결 확인을 비웠습니다. "
                                       "각자 /alarms/ 에서 [텔레그램 연결]을 다시 해야 합니다.", messages.WARNING)


# 관리 화면은 슈퍼유저만(운영 문서의 약속을 코드로). 스태프에게 모델 권한을 줘도 들어오지 못한다
admin.site.has_permission = lambda request: request.user.is_active and request.user.is_staff and request.user.is_superuser
