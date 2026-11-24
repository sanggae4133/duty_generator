import json

from django import forms
from django.core.exceptions import PermissionDenied
from django.contrib import admin, messages
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Count
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from py_vapid import _check_sub

from .accounts import issue_account, on_department_change
from .forms import SHIFT_KEY_CHOICES, STEP_FIELDS, BoardShiftForm, BoardShiftFormSet, StepsForm
from .models import AlarmSettings, Board, BoardShift, Department, Holiday, User
from .services import alarm_settings, board_settings, boards
from .shifts import SHIFT_KEYS, shift_defs


def _input_users(dept):
    """부서 입력 그룹 멤버. 입력 그룹이 없는 부서(새 부서, 담당자를 넣은 적 없는 부서)는 빈 목록."""
    return dept.input_group.user_set.all() if dept.input_group_id else User.objects.none()


class DepartmentForm(forms.ModelForm):
    # DB에는 지금처럼 "normal,dinner,night" 문자열로 저장하고, 입력만 체크박스로 받는다
    shifts = forms.MultipleChoiceField(
        label="가능한 근무조", widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "근무조를 하나 이상 선택하세요."},
    )
    # 입력 담당자 = 부서 입력 그룹 멤버. 모델 칸이 아니라 DepartmentAdmin.save_related 가 그룹에 넣는다
    managers = forms.ModelMultipleChoiceField(
        label="입력 담당자", queryset=User.objects.none(), required=False,
        widget=FilteredSelectMultiple("입력 담당자", is_stacked=False),
    )

    class Meta:
        model = Department
        fields = ["code", "name", "board", "order", "shifts", "lunch_start", "lunch_end"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.board_id:  # 저장된 부서의 근무표는 바꿀 수 없다(옮기기는 필요해지면 별도 기능, 설계 4.4)
            self.fields["board"].disabled = True
            self.fields["shifts"].choices = [(x.key, x.name) for x in shift_defs(boards.active_defs(self.instance.board))]
        else:  # 새 부서: 근무표를 같은 폼에서 고르므로 중립 이름으로 보이고 clean_shifts 가 그 근무표에 있는지 본다
            self.fields["shifts"].choices = SHIFT_KEY_CHOICES
        # 후보는 roster()만. 지금 담당자는 퇴사·부서 해제됐어도 보여야 저장할 때 조용히 빠지지 않는다
        current = _input_users(self.instance)
        self.fields["managers"].queryset = (User.objects.roster() | current).distinct()
        self.initial.setdefault("managers", list(current))
        if self.instance.pk:
            self.initial["shifts"] = self.instance.shift_keys()

    def clean_shifts(self):
        picked = set(self.cleaned_data["shifts"])
        board = self.cleaned_data.get("board")
        if board is None:  # 근무표 칸 오류가 따로 보인다
            return ",".join(sorted(picked))
        order = [x.key for x in shift_defs(boards.active_defs(board))]  # 시작 시각 순으로 저장(입력 표 칸 순서)
        if picked - set(order):
            names = dict(SHIFT_KEY_CHOICES)
            raise forms.ValidationError("이 근무표에 켜진 근무조가 아닙니다: "
                                        + ", ".join(names[k] for k in SHIFT_KEYS if k in picked - set(order)))
        return ",".join(k for k in order if k in picked)

    def clean(self):
        c = super().clean()
        name = c.get("name")
        # 입력 그룹은 첫 담당자를 고를 때 생기고(save_related → ensure_input_group), 부서 이름을 바꾸면 따라 바뀐다(설계 5.3).
        # 그 그룹 이름이 이미 있으면 Group.name unique 위반(500) 대신 이름 칸 오류로
        group = Department(name=name).input_group_name()
        makes = not self.instance.input_group_id and c.get("managers")
        renames = self.instance.input_group_id and "name" in self.changed_data
        if name and (makes or renames) and Group.objects.exclude(pk=self.instance.input_group_id).filter(name=group).exists():
            self.add_error("name", f"같은 이름의 그룹이 이미 있습니다: {group}")
        return c


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    form = DepartmentForm
    list_display = ["code", "name", "shift_labels", "member_count", "manager_names"]

    def get_readonly_fields(self, request, obj=None):
        return ("code",) if obj else ()  # 코드는 기본키: 바꾸면 새 부서가 생긴다

    def get_queryset(self, request):
        return (super().get_queryset(request).annotate(_n=Count("members", distinct=True))
                .prefetch_related("input_group__user_set"))

    @admin.display(description="가능한 근무조")
    def shift_labels(self, obj):
        defs = boards.defs(obj.board)  # 꺼진 근무조도 이름으로 보인다. 순서는 입력 표와 같은 시작 시각 순
        names = {x.key: x.name for x in defs}
        return "·".join(names[k] for k in boards.dept_keys(obj, defs))

    @admin.display(description="인원", ordering="_n")
    def member_count(self, obj):
        return obj._n

    @admin.display(description="입력 담당자")
    def manager_names(self, obj):
        return ", ".join(m.name for m in _input_users(obj)) or "(없음)"

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        dept, picked = form.instance, form.cleaned_data["managers"]
        if picked:  # 첫 담당자를 고를 때 입력 그룹을 만든다(이름 겹침은 clean 이 먼저 막았다)
            dept.ensure_input_group()
        if dept.input_group_id:
            dept.input_group.user_set.set(picked)


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


def _no_admin_left(board) -> str:
    return f"{board.name} 근무표에 재직 중인 관리자가 남지 않습니다. 먼저 다른 관리자를 넣으세요."


class UserForm(UserChangeForm):
    """재직 관리자 한 명 이상(근무표 통합 설계 7.4, [근무표 설정]과 같은 검사 boards.left_without_admin):
    마지막 재직 관리자의 관리 그룹을 빼거나 재직을 끄면 저장하지 않고 칸 오류."""

    def clean(self):
        c = super().clean()
        if self.instance.pk and "groups" in c and "is_active" in c:
            keep = {g.pk for g in c["groups"]} if c["is_active"] else set()
            for board in boards.left_without_admin([self.instance]):  # 저장 전 DB 상태로 판단한다
                if board.admin_group_id not in keep:
                    self.add_error("groups" if c["is_active"] else "is_active", _no_admin_left(board))
        return c


MINE_SKIPPED = "자기 계정은 발급에서 뺐습니다. 내 비밀번호는 메뉴의 [비밀번호]에서 바꾸세요."


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserForm
    add_form = UserAddForm
    add_form_template = None  # 기본 안내("아이디와 비밀번호를 먼저…")가 맞지 않아 일반 추가 화면을 쓴다
    add_fieldsets = ((None, {"fields": ("username", "name", "department", "part", "type")}),)
    fieldsets = (
        # Django 비밀번호 칸(초기화·설정 버튼)은 뺀다: 비밀번호는 액션 '계정 발급 / 비밀번호 초기화' 한 길로만 준다
        # (그 화면으로 정하면 첫 로그인 변경·기본 알림 규칙·임시 비밀번호 유효 기간을 거치지 않는다)
        (None, {"fields": ("username", "must_change_password")}),
        ("근무표", {"fields": ("name", "department", "part", "type")}),
        ("도움말·알림", {"fields": ("help_dismissed", "notify_changes"),
                     "description": "'사용법 팝업 다시 보지 않기'를 끄면 다음 로그인 때 사용법 팝업이 다시 뜹니다."}),
        # 기본 "개인정보"(이름·성·이메일)는 근무표 "이름"과 헷갈려 숨긴다(칸은 유지).
        # Django 사용자 권한(user_permissions)은 쓰지 않는다: 근무표 관리자·입력 담당은 그룹으로 정한다
        (DjangoUserAdmin.fieldsets[2][0], {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
        *DjangoUserAdmin.fieldsets[3:],
    )
    list_display = ["login_id", "name", "department", "part", "type", "is_active", "group_names"]
    list_filter = ["department", "type", "is_active", "groups"]
    search_fields = ["username", "name"]
    list_select_related = ["department"]
    actions = ["issue_accounts"]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("groups")

    @admin.display(description="그룹")
    def group_names(self, obj):
        return ", ".join(g.name for g in obj.groups.all())

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["username"].label = "아이디"  # 모델 칸은 그대로 두고 화면 라벨만
        return form

    @admin.display(description="아이디", ordering="username")
    def login_id(self, obj):
        return obj.username

    def get_deleted_objects(self, objs, request):
        """지우기(한 명·'선택한 사용자 삭제' 일괄)도 재직 관리자 한 명 이상을 지킨다: 남지 않는 근무표가 있으면
        Django 의 '보호된 객체' 목록에 그 까닭을 넣어 아무것도 지우지 않는다(두 길 모두 이 목록이 비어야 지운다)."""
        deleted, count, perms_needed, protected = super().get_deleted_objects(objs, request)
        return deleted, count, perms_needed, [*protected, *map(_no_admin_left, boards.left_without_admin(objs))]

    def changelist_view(self, request, extra_context=None):
        """'선택한 사용자 삭제'는 위 검사와 지우기를 따로 부른다: POST 를 한 트랜잭션(IMMEDIATE, 쓰기가 줄 선다)으로 묶어
        두 슈퍼유저가 관리자를 하나씩 동시에 지워도 재직 관리자가 0명이 되지 않게(한 명 지우기는 Django 가 이미 한 트랜잭션)."""
        if request.method != "POST":
            return super().changelist_view(request, extra_context)
        with transaction.atomic():
            return super().changelist_view(request, extra_context)

    # 관리 화면 기록(LogEntry.object_repr)은 Django 기본이 str(user) = 실명이라 아이디로 남긴다(로그에 실명 금지)
    def _log(self, request, objs, flag, message=""):
        return LogEntry.objects.bulk_create(
            LogEntry(user_id=request.user.pk, content_type=ContentType.objects.get_for_model(User), object_id=str(o.pk),
                     object_repr=o.username, action_flag=flag,
                     change_message=json.dumps(message) if isinstance(message, list) else message) for o in objs)

    def log_addition(self, request, obj, message):
        return self._log(request, [obj], ADDITION, message)[0]

    def log_change(self, request, obj, message):
        return self._log(request, [obj], CHANGE, message)[0]

    def log_deletions(self, request, queryset):
        return self._log(request, queryset, DELETION)

    def save_model(self, request, obj, form, change):
        old = User.objects.filter(pk=obj.pk).values_list("department_id", flat=True).first() if change else None
        super().save_model(request, obj, form, change)
        if change:  # 부서를 옮겨 근무표가 바뀌면 개인 알림 발송 기록 정리
            on_department_change(obj, old)

    @admin.action(description="계정 발급 / 비밀번호 초기화", permissions=["change"])
    def issue_accounts(self, request, queryset):
        if not request.user.is_superuser:  # 관리 화면 자체가 슈퍼유저 전용이지만 액션에서도 한 번 더
            raise PermissionDenied
        mine = queryset.filter(pk=request.user.pk).exists()
        queryset = queryset.exclude(pk=request.user.pk)  # 자기 비밀번호가 바뀌면 세션과 함께 이 목록도 사라진다
        with transaction.atomic():  # 중간 실패 시 이미 발급된 비밀번호가 사라지지 않도록 전체 롤백
            lines = [f"{u.name}({u.username}): {issue_account(u)}" for u in queryset]
        if lines:  # 임시 비밀번호는 이 응답 본문에만: messages(세션 DB)·로그에 싣지 않는다([근무표 설정]과 같은 규칙)
            return TemplateResponse(request, "admin/duty/user/issued.html", {
                **self.admin_site.each_context(request), "opts": self.opts, "title": "임시 비밀번호",
                "lines": lines, "mine": MINE_SKIPPED if mine else ""})
        if mine:
            self.message_user(request, MINE_SKIPPED, messages.INFO)


class BoardShiftInline(admin.TabularInline):
    """저장한 줄은 지우지 않는다(끄기만). 아직 저장하지 않은 추가 줄은 화면에서 뺄 수 있다."""
    model = BoardShift
    form = BoardShiftForm
    formset = BoardShiftFormSet
    extra = 0
    can_delete = False


class BoardForm(StepsForm):
    class Meta(StepsForm.Meta):
        fields = ["code", "name", *StepsForm.Meta.fields]

    def clean(self):
        c = super().clean()  # 단계 칸 검사(StepsForm)
        name = c.get("name")
        # Board.save 가 만들거나 바꿀 관리 그룹 이름이 이미 있으면 Group.name unique 위반(500) 대신 칸 오류로
        if name and Board.objects.exclude(pk=self.instance.pk).filter(name=name).exists():
            self.add_error("name", f"같은 이름의 근무표가 이미 있습니다: {name}")
        elif (name and "name" in self.changed_data  # 이름을 바꿀 때만 관리 그룹 이름이 바뀐다
              and Group.objects.exclude(pk=self.instance.admin_group_id).filter(name=(group := Board(name=name).admin_group_name())).exists()):
            self.add_error("name", f"같은 이름의 그룹이 이미 있습니다: {group}")
        return c


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    """근무표(설계 4.2·4.3). code(주소 ?board= 와 기억한 근무표 RosterPref.boards 의 열쇠)는 만든 뒤 바꾸지 않는다. 단계 칸은 언제든 고친다(근무표 통합 3단계).
    지우기는 막는다. 관리 그룹은 Board.save 가 만들고, 관리자·입력 담당자는 앱의 [근무표 설정]에서 넣고 뺀다."""
    form = BoardForm
    list_display = ["name", "code", "step_line", "admin_group"]
    inlines = [BoardShiftInline]

    def get_fieldsets(self, request, obj=None):
        fields = ["code", "name"] + ([] if obj is None else ["group_link"])
        return [(None, {"fields": fields, "description": (
            "근무 정의의 이름·시각을 운영 중에 바꾸면 발송 창이 열린 알림이 한 번 다시 나가고, 예전에 내려받은 CSV 의 "
            "열 이름이 맞지 않습니다. 저장한 정의는 지우거나 키를 바꿀 수 없으니 '사용'을 끄고 새 줄을 더합니다. "
            "근무조 1~4 는 이름일 뿐이고 이른·늦은 조는 시작 시각으로 정합니다.")}),
                ("회차 단계", {"fields": ["use_draft", "use_close", *STEP_FIELDS], "description": (
                    "작성 중·마감을 끄면 그 단계를 건너뜁니다. 이름은 화면에 보이는 단계 이름이고, 버튼 이름은 단계 이름에서 "
                    "나옵니다(예: '취합 중' → [취합 열기]). IT = 둘 다 켬, 작성 중·취합 중·마감·생성됨·배포됨. "
                    "시장운영실 = 둘 다 끔, 취합 중 '입력 중'·생성됨 '확정'. 바꾸면 진행 중인 회차의 단계 이름과 버튼이 바로 바뀌고, "
                    "끈 단계에 남은 회차는 회차 화면의 '다른 상태로 옮기기'로 옮깁니다.")})]

    def get_readonly_fields(self, request, obj=None):
        return [] if obj is None else ["code", "group_link"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change and (w := board_settings.stranded(obj)):  # 단계를 꺼서 그 단계에 회차가 남았다(설계 5.1)
            self.message_user(request, w, messages.WARNING)

    @admin.display(description="단계")
    def step_line(self, obj):
        return " → ".join(obj.step_name(s) for s in obj.steps())

    @admin.display(description="관리 그룹")
    def group_link(self, obj):
        return format_html('<a href="{}">{}</a> — 관리자·입력 담당자는 앱의 [근무표 설정]에서 넣고 뺍니다.',
                           reverse("admin:auth_group_change", args=[obj.admin_group_id]), obj.admin_group.name)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    """휴장일(설계 5절): 임시공휴일 추가(직접 추가), 휴장일이 아닌 날은 '휴장'을 끈다. 자동 행은 작업자가 채운다.
    지우기는 막는다(지운 자동 휴장일은 다음 바퀴에 다시 생긴다). 이미 있는 배정은 바뀌지 않는다."""
    list_display = ["date", "name", "source", "active"]
    list_filter = ["active", "source"]
    list_editable = ["active"]
    date_hierarchy = "date"

    def get_fields(self, request, obj=None):
        return ["date", "name", "active"] if obj is None else ["date", "name", "source", "active"]

    def get_readonly_fields(self, request, obj=None):
        return [] if obj is None else ["date", "source"]  # 날짜를 옮기면 자동 행과 겹친다: 끄고 새로 추가한다

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.unregister(Group)  # django.contrib.auth.admin 이 등록한 기본 그룹 화면(권한 칸)을 바꾼다


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    """이름·멤버 보기만(permissions 칸은 숨긴다: Django 권한을 쓰지 않는다). 멤버는 사용자 화면의 '그룹' 칸이나 앱의 [근무표 설정]에서
    고친다(관리자·입력 담당자). 근무표 관리 그룹·부서 입력 그룹의 이름은 근무표·부서 이름을 따라가므로 여기서 바꾸지 않는다."""
    fields = ["name"]
    list_display = ["name", "member_names"]
    search_fields = ["name"]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("user_set")

    @admin.display(description="멤버")
    def member_names(self, obj):
        return ", ".join(u.name for u in obj.user_set.all()) or "(없음)"


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
