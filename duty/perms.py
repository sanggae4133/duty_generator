"""권한 규칙. 다른 모듈은 `from . import perms` 후 `perms.today()` 형태로 호출한다(테스트 monkeypatch 용)."""

from datetime import date

from django.core.exceptions import PermissionDenied
from django.utils import timezone

from .models import Department


def today() -> date:
    return timezone.localdate()


def is_admin(user) -> bool:
    return bool(user.is_authenticated and user.is_staff)


def managed_departments(user):
    if is_admin(user):
        return Department.objects.all()
    if not user.is_authenticated:
        return Department.objects.none()
    return user.managed_departments.all()


def can_input_department(user, dept: Department) -> bool:
    return is_admin(user) or managed_departments(user).filter(pk=dept.pk).exists()


def assert_can_edit_date(user, d: date) -> None:
    if d < today() and not is_admin(user):
        raise PermissionDenied("지난 날짜는 어드민만 수정할 수 있습니다.")
