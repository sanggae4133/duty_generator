from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse

from . import perms


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        member = perms.member_of(request.user)
        if member and not member.is_active and not request.user.is_staff:
            logout(request)
            messages.error(request, "재직 중이 아닌 계정입니다. 관리자에게 문의하세요.")
            return redirect("login")
        if member and member.must_change_password and request.path not in {
                reverse("password_change"), reverse("logout"), reverse("sw_js"), reverse("manifest")}:
            return redirect("password_change")
        return self.get_response(request)
