from django.conf import settings
from django.urls import reverse

from . import help as guide
from . import perms


def nav(request):
    """상단 메뉴(지금 화면 표시 포함)와 저장소 링크."""
    user = request.user
    out = {"repo_url": settings.REPO_URL, "can_collect": False, "menu": []}
    if not user.is_authenticated:
        return out
    out["can_collect"] = perms.managed_departments(user).exists()
    items = [("근무표", "/", ("/day/", "/cell/")), ("내 근무", "/me/", ()), ("알림·캘린더", "/alarms/", ())]
    if out["can_collect"]:
        items.append(("출근표 입력", "/collect/", ()))
    if perms.is_admin(user):  # 어느 근무표든 관리 그룹 멤버(스태프 표시는 관리자 판정에 쓰지 않는다)
        items.append(("회차", "/periods/", ()))
        if perms.stats_boards(user).exists():  # 통계는 slot* 정의가 있는 근무표의 관리 그룹만(설계 7절)
            items.append(("통계", "/stats/", ()))
        items.append(("이력", "/changes/", ()))
        items.append(("근무표 설정", "/settings/", ()))  # 관리자·입력 담당자·근무 정의와 부서·단계(근무표 통합 설계 7절)
    if user.is_superuser:
        items.append(("관리", reverse("admin:index"), ()))
    items.append(("도움말", "/help/", ()))
    # 로그인 직후 첫 화면에 사용법 팝업(비밀번호 변경 화면에서는 미룬다). base.html 이 실제로 그릴 때만
    # 세션 표시를 소비한다(템플릿이 부를 때 실행) — 근무 변경 팝업 같은 부분 응답이 먼저 와도 잃지 않게
    if request.path != reverse("password_change"):
        def welcome():
            return guide.for_user(user) if request.session.pop("show_help", False) else []
        out["welcome_videos"] = welcome
    path = request.path
    out["menu"] = [
        {"label": label, "url": url,
         "active": path == url or (url != "/" and path.startswith(url)) or path.startswith(more)}
        for label, url, more in items
    ]
    return out
