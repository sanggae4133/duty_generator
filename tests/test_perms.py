from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied

from duty import perms


def test_past_date_is_admin_only(fixed_today, make_member, admin_user):
    fixed_today(date(2026, 11, 10))
    m = make_member("가", user=True)
    perms.assert_can_edit_date(m.user, date(2026, 11, 10))  # 오늘은 누구나
    with pytest.raises(PermissionDenied):
        perms.assert_can_edit_date(m.user, date(2026, 11, 9))
    perms.assert_can_edit_date(admin_user, date(2026, 11, 9))


def test_can_input_department(depts, make_member, admin_user):
    m = make_member("가", user=True)
    depts["MEMS"].managers.add(m)
    assert perms.can_input_department(m.user, depts["MEMS"])
    assert not perms.can_input_department(m.user, depts["MD"])
    assert perms.can_input_department(admin_user, depts["MD"])


def test_managed_departments(depts, make_member, admin_user):
    m = make_member("가", user=True)
    depts["MD"].managers.add(m)
    assert list(perms.managed_departments(m.user)) == [depts["MD"]]
    assert perms.managed_departments(admin_user).count() == 4
    assert perms.managed_departments(AnonymousUser()).count() == 0


def test_member_of(make_member, admin_user):
    m = make_member("가", user=True)
    assert perms.member_of(m.user) == m
    assert perms.member_of(admin_user) is None
