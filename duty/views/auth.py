from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError

from .. import accounts


class DifferentPasswordForm(PasswordChangeForm):
    def __init__(self, user, *args, request=None, **kwargs):
        self.request = request
        super().__init__(user, *args, **kwargs)

    def clean_old_password(self):
        """authenticate 로 확인해 로그인과 같이 실패를 세고 잠근다(axes). 그냥 check_password 면 잠금 없이 맞춰 볼 수 있다."""
        old = self.cleaned_data["old_password"]
        if authenticate(self.request, username=self.user.get_username(), password=old) is None:
            raise ValidationError(self.error_messages["password_incorrect"], code="password_incorrect")
        return old

    def clean(self):
        data = super().clean()
        if data.get("new_password1") and data.get("new_password1") == data.get("old_password"):
            raise ValidationError("지금 비밀번호와 다른 비밀번호를 입력하세요.")
        return data


class PasswordChange(auth_views.PasswordChangeView):
    form_class = DifferentPasswordForm
    template_name = "duty/password_change.html"
    success_url = "/"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "request": self.request}

    def form_valid(self, form):
        response = super().form_valid(form)
        accounts.password_changed(self.request.user)
        messages.success(self.request, "비밀번호를 바꿨습니다.")
        return response
