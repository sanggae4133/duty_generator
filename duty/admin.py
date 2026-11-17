from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib import admin, messages
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from py_vapid import _check_sub

from .accounts import issue_account, on_department_change
from .models import AlarmSettings, Board, BoardShift, Department, GroupKeeper, Holiday, User
from .services import alarm_settings, boards
from .shifts import DEVELOPER, LUNCH, SHIFT_KEYS, STAFF, is_slot_cell, shift_defs

# 근무조 키 선택지(관리 화면 표시 이름 "근무조 1"~"근무조 4", 설계 4.1)
SHIFT_KEY_CHOICES = [(k, label) for k, label in BoardShift._meta.get_field("key").choices if k in SHIFT_KEYS]


def _input_users(dept):
    """부서 입력 그룹 멤버. 새 부서·직접 입력 근무표 부서(그룹 없음)는 빈 목록."""
    return dept.input_group.user_set.all() if dept.input_group_id else User.objects.none()


class DepartmentForm(forms.ModelForm):
    # DB에는 지금처럼 "normal,dinner,night" 문자열로 저장하고, 입력만 체크박스로 받는다
    shifts = forms.MultipleChoiceField(
        label="가능한 출근조", widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "출근조를 하나 이상 선택하세요."},
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
        board, name = c.get("board"), c.get("name")
        # Department.save 가 만들거나 바꿀 입력 그룹 이름이 이미 있으면 Group.name unique 위반(500) 대신 칸 오류로
        group = f"{name} 출근표 입력"
        has_group = self.instance.input_group_id or (board and not boards.legacy_admin_entry(board))  # 1단계 임시 기준
        if c.get("managers") and board and boards.legacy_admin_entry(board):
            self.add_error("managers", "직접 입력 근무표의 부서는 입력 담당자가 없습니다. 근무표 관리자가 입력합니다.")
        if (name and has_group and "name" in self.changed_data  # 이름을 바꿀 때만 그룹 이름이 바뀐다
                and Group.objects.exclude(pk=self.instance.input_group_id).filter(name=group).exists()):
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

    @admin.display(description="가능한 출근조")
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
        if form.instance.input_group_id:  # 직접 입력 근무표의 부서는 입력 그룹이 없다
            form.instance.input_group.user_set.set(form.cleaned_data["managers"])


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
        if mine:
            self.message_user(request, "자기 계정은 발급에서 뺐습니다. 내 비밀번호는 메뉴의 [비밀번호]에서 바꾸세요.",
                              messages.INFO)
        if lines:
            self.message_user(request, format_html(  # 한 줄에 한 사람: 1:1로 옮길 때 섞이지 않게
                "임시 비밀번호 — 이 화면에서만 보입니다. 사람마다 1:1로만 전달하세요.{}",
                format_html_join("", "<br>{}", ((x,) for x in lines))), messages.WARNING)


class BoardShiftForm(forms.ModelForm):
    """근무 정의 한 줄의 검증(설계 4.3). 저장한 줄은 키 칸을 잠근다(BoardShift.clean 이 한 번 더 막는다).
    시각 오류는 start 칸에 붙인다: 그 칸이 오류면 DB 제약(boardshift_times_valid) 검사를 건너뛰어 영어 제약 문구가 함께 뜨지 않는다."""
    eligible_shifts = forms.MultipleChoiceField(label="자격 근무조", required=False, choices=SHIFT_KEY_CHOICES,
                                                widget=forms.CheckboxSelectMultiple,
                                                help_text="장중관제 칸만. 켜진 관제는 하나 이상 고릅니다")
    eligible_types = forms.MultipleChoiceField(label="자격 구분", required=False, choices=[(STAFF, STAFF), (DEVELOPER, DEVELOPER)],
                                               widget=forms.CheckboxSelectMultiple, help_text="장중관제 칸만. 비우면 전원")

    class Meta:
        model = BoardShift
        fields = ["key", "name", "start", "end", "eligible_shifts", "eligible_types", "default_alarm", "active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:  # 저장한 정의의 키는 바꾸지 않는다(보낸 값은 무시된다)
            self.fields["key"].disabled = True

    def clean_name(self):
        v = self.cleaned_data["name"].strip()
        if v in ("date", "day") or any(c in v for c in "(\r\n"):  # CSV 열 이름이 된다
            raise forms.ValidationError("이름은 date·day 가 아니어야 하고 ( 와 줄바꿈을 쓸 수 없습니다(CSV 열 이름이 됩니다).")
        return v

    def clean_eligible_shifts(self):
        return [k for k in SHIFT_KEYS if k in self.cleaned_data["eligible_shifts"]]

    def clean(self):
        c = super().clean()
        key, start, end = c.get("key"), c.get("start"), c.get("end")
        if not key:
            return c
        if key == LUNCH:
            if start or end:
                self.add_error("start", "점심당번은 시각을 비웁니다(점심 시각은 부서마다 정합니다).")
        elif not (start and end and start < end):
            self.add_error("start", "시작·끝 시각을 넣고 시작을 끝보다 이르게 하세요(당일 근무만).")
        if not is_slot_cell(key) and (c.get("eligible_shifts") or c.get("eligible_types")):
            self.add_error("eligible_shifts", "자격 근무조·자격 구분은 장중관제 칸에만 씁니다.")
        if is_slot_cell(key) and c.get("active") and not c.get("eligible_shifts"):  # 자격자가 없으면 생성이 그 칸을 못 채운다
            self.add_error("eligible_shifts", "장중관제 칸은 자격 근무조를 하나 이상 골라야 합니다.")
        if key not in SHIFT_KEYS and c.get("default_alarm"):
            self.add_error("default_alarm", "기본 알림 대상은 근무조에만 씁니다.")
        return c


class BoardShiftFormSet(forms.BaseInlineFormSet):
    """근무표 전체의 검증(설계 4.3). Django 기본 겹침 검사(영어 칸 이름이 섞인 문구)는 부르지 않고 한국어로 직접 본다:
    이름·키 겹침, 켜진 근무조 하나 이상, 켜진 근무조끼리 시작 시각이 다름(가장 이른 조·이른/가운데/늦은 조가 하나로 정해지게),
    관제 자격 근무조는 이 근무표의 근무조(켜진 관제는 켜진 근무조만), 끄고 나서도 부서마다 켜진 입력 근무조가 하나 이상."""

    def clean(self):
        if any(self.errors):
            return
        rows = [f.cleaned_data for f in self.forms if f.cleaned_data.get("key")]  # 비워 둔 추가 줄은 빠진다
        for field, label in (("name", "근무 정의 이름이 겹칩니다"), ("key", "키가 겹칩니다")):
            values = [r[field] for r in rows]
            dup = sorted({v for v in values if values.count(v) > 1})
            if dup:
                names = dict(BoardShift._meta.get_field("key").choices) if field == "key" else {}
                raise ValidationError(f"{label}: {', '.join(names.get(v, v) for v in dup)}")
        on = [r for r in rows if r["key"] in SHIFT_KEYS and r["active"]]
        if not on:
            raise ValidationError("켜진 근무조가 하나 이상 있어야 합니다.")
        if len({r["start"] for r in on}) != len(on):
            raise ValidationError("켜진 근무조끼리 시작 시각이 달라야 합니다(가장 이른 조를 하나로 정할 수 있게).")
        keys, on_keys = {r["key"] for r in rows if r["key"] in SHIFT_KEYS}, {r["key"] for r in on}
        for r in rows:
            picked = set(r.get("eligible_shifts") or ())
            if picked - keys:
                raise ValidationError(f"{r['name']}: 자격 근무조는 이 근무표의 근무조여야 합니다.")
            if r["active"] and picked - on_keys:
                raise ValidationError(f"{r['name']}: 켜진 관제의 자격 근무조는 켜진 근무조여야 합니다.")
        if self.instance.pk:
            for dept in self.instance.departments.all():
                if not set(dept.shift_keys()) & on_keys:
                    raise ValidationError(f"{dept.name} 부서에 켜진 근무조가 하나도 남지 않습니다. 부서의 출근조를 먼저 바꾸세요.")


class BoardShiftInline(admin.TabularInline):
    """저장한 줄은 지우지 않는다(끄기만). 아직 저장하지 않은 추가 줄은 화면에서 뺄 수 있다."""
    model = BoardShift
    form = BoardShiftForm
    formset = BoardShiftFormSet
    extra = 0
    can_delete = False


STEP_FIELDS = ["step_draft", "step_collecting", "step_closed", "step_generated", "step_published"]


class BoardForm(forms.ModelForm):
    class Meta:
        model = Board
        fields = ["code", "name", "use_draft", "use_close", *STEP_FIELDS]

    def clean(self):
        c = super().clean()
        names = [c.get(f) for f in STEP_FIELDS]
        for f, v in zip(STEP_FIELDS, names):  # 단계 이름(설계 5.1): 줄바꿈 금지, 서로 다름
            if v and ("\n" in v or "\r" in v):
                self.add_error(f, "단계 이름에 줄바꿈을 쓸 수 없습니다.")
            elif v and names.count(v) > 1:
                self.add_error(f, f"단계 이름이 겹칩니다: {v}")
        # 버튼 글자 검사(설계 5.4): 저장된 근무표는 단계 칸이 읽기 전용이라 만들 때만. 단계 칸 자체 오류가 없으면 본다
        if all(names) and not set(STEP_FIELDS) & set(self.errors):
            steps = Board(use_draft=c.get("use_draft"), use_close=c.get("use_close"), **dict(zip(STEP_FIELDS, names)))
            gen, slot = steps.step_buttons(False), steps.step_buttons(True)
            for x in steps.bad_buttons():  # 생성·취소 글자는 생성됨 이름에서, 열기·마감은 취합 중 이름에서 나온다
                # 관제 있을 때의 고정 글자([장중관제 생성]·[재생성]…)와 겹치면 생성됨 이름을 고쳐도 남는다
                fixed = x.strip() and x in (slot["generate"], slot["undo"], slot["regenerate"])
                field = ("step_generated" if x in (gen["generate"], gen["undo"]) and not fixed
                         else "step_closed" if x == gen["close"] and not fixed else "step_collecting")  # 마감 글자가 열기와 같으면 마감 이름 칸
                self.add_error(field, f"버튼 이름이 비거나 다른 버튼과 같아집니다: [{x}]")
        name = c.get("name")
        # Board.save 가 만들거나 바꿀 관리 그룹 이름이 이미 있으면 Group.name unique 위반(500) 대신 칸 오류로
        if name and Board.objects.exclude(pk=self.instance.pk).filter(name=name).exists():
            self.add_error("name", f"같은 이름의 근무표가 이미 있습니다: {name}")
        elif (name and "name" in self.changed_data  # 이름을 바꿀 때만 관리 그룹 이름이 바뀐다
              and Group.objects.exclude(pk=self.instance.admin_group_id).filter(name=f"{name} 근무표 관리").exists()):
            self.add_error("name", f"같은 이름의 그룹이 이미 있습니다: {name} 근무표 관리")
        return c


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    """근무표(설계 4.2·4.3). code(boards.it_board() 가 IT 근무표를 찾는 열쇠)는 만든 뒤 바꾸지 않는다. 단계 칸은 1·2단계에서 만들 때만 정한다.
    지우기는 막는다. 관리 그룹은 Board.save 가 만들고, 그 그룹의 그룹 관리자는 '관리 그룹' 링크(그룹 화면)에서 정한다."""
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
                    "시장운영실 = 둘 다 끔, 취합 중 '입력 중'·생성됨 '확정'. 저장한 근무표의 단계는 지금은 바꾸지 않습니다.")})]

    def get_readonly_fields(self, request, obj=None):
        # 1단계: 저장된 근무표의 단계 칸은 읽기 전용(임시 기준 legacy_admin_entry 와 섞인 상태를 막는다, 설계 5.1). 3단계에서 연다
        return [] if obj is None else ["code", "use_draft", "use_close", *STEP_FIELDS, "group_link"]

    @admin.display(description="단계")
    def step_line(self, obj):
        return " → ".join(obj.step_name(s) for s in obj.steps())

    @admin.display(description="관리 그룹")
    def group_link(self, obj):
        return format_html('<a href="{}">{}</a> — 그룹 관리자는 이 링크에서, 멤버는 사용자 화면의 그룹 칸이나 [그룹] 화면에서 정합니다.',
                           reverse("admin:auth_group_change", args=[obj.admin_group_id]), obj.admin_group.name)

    def has_delete_permission(self, request, obj=None):
        return False


class GroupKeeperInline(admin.TabularInline):
    """그룹 관리자(설계 4.5): 이 그룹에 멤버를 넣고 빼는 사람. 슈퍼유저가 여기서 정하고, 그 뒤 멤버는 그 사람이 [그룹] 화면에서."""
    model = GroupKeeper
    extra = 0


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
    """permissions 칸만 숨긴다(Django 권한을 쓰지 않는다). 멤버는 사용자 화면의 '그룹' 칸이나, 그룹 관리자가 [그룹] 화면에서 넣는다."""
    fields = ["name"]
    list_display = ["name", "member_names"]
    search_fields = ["name"]
    inlines = [GroupKeeperInline]

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
