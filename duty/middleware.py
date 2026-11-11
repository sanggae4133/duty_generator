from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse

from . import perms
from .logging import FEED_PREFIX


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 공개 PWA 파일은 회원 상태와 무관하게 그대로 준다(리다이렉트되면 서비스 워커 갱신이 실패한다)
        # 캘린더 피드는 로그인과 무관하게 토큰으로만 접근한다(구독 앱이 읽는다)
        if request.path in {reverse("sw_js"), reverse("manifest")}:
            return self.get_response(request)
        if request.path.startswith(FEED_PREFIX):
            r = self.get_response(request)
            # 200/304 는 뷰가 이미 정했고, 404·405 등에도 같은 헤더를 붙인다
            r.headers.setdefault("Cache-Control", "private, no-cache")
            r.headers.setdefault("Referrer-Policy", "no-referrer")
            return r
        member = perms.member_of(request.user)
        if member and not member.is_active and not request.user.is_staff:
            logout(request)
            messages.error(request, "재직 중이 아닌 계정입니다. 관리자에게 문의하세요.")
            return redirect("login")
        if member and member.must_change_password and request.path not in {reverse("password_change"), reverse("logout")}:
            return redirect("password_change")
        return self.get_response(request)
