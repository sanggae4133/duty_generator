from django.contrib.auth import views as auth_views

from .. import perms


class PasswordChange(auth_views.PasswordChangeView):
    template_name = "duty/password_change.html"
    success_url = "/"

    def form_valid(self, form):
        response = super().form_valid(form)
        member = perms.member_of(self.request.user)
        if member and member.must_change_password:
            member.must_change_password = False
            member.save(update_fields=["must_change_password"])
        return response
