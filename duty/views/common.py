import re
from datetime import date
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.utils.http import url_has_allowed_host_and_scheme

from .. import perms


def admin_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not perms.is_admin(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return login_required(wrapped)


def int_param(raw: str | None) -> int | None:
    """보낸 id·확인 수: ASCII 숫자 18자리까지만 int(아니면 None). str.isdigit() 는 '²' 같은 글자도 참이라 int() 가 터지고,
    아주 긴 숫자는 SQLite 정수 범위를 넘어 500 이 난다."""
    return int(raw) if raw and re.fullmatch(r"\d{1,18}", raw, re.ASCII) else None


LOW, HIGH = date(2000, 1, 1), date(2099, 12, 31)  # 받는 날짜 범위(밖은 날짜 계산이 넘친다). 회차 기간도 이 안(periods)


def date_param(request, name: str) -> date | None:
    """?name=YYYY-MM-DD. 형식이 틀리거나 LOW~HIGH 밖이면 None."""
    raw = request.GET.get(name, "")
    try:
        d = date.fromisoformat(raw) if raw else None
    except ValueError:
        return None
    return d if d and LOW <= d <= HIGH else None


def safe_next(request, fallback: str) -> str:
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    ok = nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}, require_https=request.is_secure())
    return nxt if ok else fallback
