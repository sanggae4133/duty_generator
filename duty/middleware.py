from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse

from . import perms


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 공개 PWA 파일은 회원 상태와 무관하게 그대로 준다(리다이렉트되면 서비스 워커 갱신이 실패한다)
        if request.path in {reverse("sw_js"), reverse("manifest")}:
            return self.get_response(request)
        member = perms.member_of(request.user)
        if member and not member.is_active and not request.user.is_staff:
            logout(request)
            messages.error(request, "재직 중이 아닌 계정입니다. 관리자에게 문의하세요.")
            return redirect("login")
        if member and member.must_change_password and request.path not in {reverse("password_change"), reverse("logout")}:
            return redirect("password_change")
        return self.get_response(request)
