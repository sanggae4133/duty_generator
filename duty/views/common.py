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


def date_param(request, name: str) -> date | None:
    raw = request.GET.get(name, "")
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def safe_next(request, fallback: str) -> str:
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    return nxt if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}) else fallback
