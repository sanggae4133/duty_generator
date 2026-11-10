from django.contrib import admin, messages

from .accounts import issue_account
from .errors import DutyError
from .models import Department, Member


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "shifts"]
    filter_horizontal = ["managers"]


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
            lines = [f"{m.name}({m.code}): {issue_account(m)}" for m in queryset]
        except DutyError as e:
            self.message_user(request, str(e), messages.ERROR)
            return
        self.message_user(request, "임시 비밀번호 — 이 화면에서만 보입니다. " + " / ".join(lines), messages.WARNING)
