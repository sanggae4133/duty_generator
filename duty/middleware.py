from django.shortcuts import redirect
from django.urls import reverse

from .logging import FEED_PREFIX


# XSS 두 번째 방어 겹. 인라인 <script>·<style>·onsubmit 을 쓰므로 'unsafe-inline' 은 남기고, 바깥 출처·<object>·<base>·
# 남의 사이트에 끼우기·남의 주소로 폼 보내기를 막는다. t.me: 텔레그램 연결 POST 가 t.me 로 리다이렉트한다.
# img data: 는 Pico.css 의 체크·화살표 그림
# ponytail: script-src 'unsafe-inline' — 인라인 스크립트를 static 파일로 옮기면 'self' 로 좁힐 수 있다
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self' https://t.me")


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        r = self._call(request)
        r.headers.setdefault("Content-Security-Policy", CSP)
        return r

    def _call(self, request):
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
        # 퇴사(재직 끔) 계정의 세션은 Django 가 익명으로 돌린다(ModelBackend.get_user)
        if request.user.is_authenticated and request.user.must_change_password and request.path not in {reverse("password_change"), reverse("logout")}:
            return redirect("password_change")
        r = self.get_response(request)
        if request.user.is_authenticated:  # 로그아웃 뒤 '뒤로 가기'로 화면·입력값이 복원되지 않게(뷰가 정한 값은 그대로)
            r.headers.setdefault("Cache-Control", "private, no-store")
        return r
