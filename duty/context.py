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
    items = [("근무표", "/", ("/day/", "/cell/", "/swap/")), ("내 근무", "/me/", ()), ("알림·캘린더", "/alarms/", ())]
    if out["can_collect"]:
        items.append(("출근표 입력", "/collect/", ()))
    if user.is_staff:
        items += [("회차", "/periods/", ()), ("통계", "/stats/", ()), ("이력", "/changes/", ())]
    if user.is_superuser:
        items.append(("관리", reverse("admin:index"), ()))
    items.append(("도움말", "/help/", ()))
    # 로그인 직후 첫 화면에 사용법 팝업(비밀번호 변경 화면에서는 미룬다)
    if request.path != reverse("password_change") and request.session.pop("show_help", False):
        out["welcome_videos"] = guide.for_user(user)
    path = request.path
    out["menu"] = [
        {"label": label, "url": url,
         "active": path == url or (url != "/" and path.startswith(url)) or path.startswith(more)}
        for label, url, more in items
    ]
    return out
