from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError

from .. import perms


class DifferentPasswordForm(PasswordChangeForm):
    def clean(self):
        data = super().clean()
        if data.get("new_password1") and data.get("new_password1") == data.get("old_password"):
            raise ValidationError("임시 비밀번호와 다른 비밀번호를 입력하세요.")
        return data


class PasswordChange(auth_views.PasswordChangeView):
    form_class = DifferentPasswordForm
    template_name = "duty/password_change.html"
    success_url = "/"

    def form_valid(self, form):
        response = super().form_valid(form)
        member = perms.member_of(self.request.user)
        if member and member.must_change_password:
            member.must_change_password = False
            member.save(update_fields=["must_change_password"])
        return response
