"""duty.User(AUTH_USER_MODEL): 마이그레이션 그래프·DB 제약·후보 목록."""
import io

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction

from duty.models import AlarmRule, User


def test_auth_user_model_is_duty_user():
    assert get_user_model() is User


@pytest.mark.django_db
def test_migrated_tables():
    tables = connection.introspection.table_names()
    assert "duty_user" in tables and "auth_user" not in tables
    for t in ("django_admin_log", "auth_group", "django_content_type", "axes_accessattempt", "django_session"):
        assert t in tables
    with connection.cursor() as c:
        fks = connection.introspection.get_relations(c, "django_admin_log")
    assert fks["user_id"][1] == "duty_user"


@pytest.mark.django_db
def test_user_contenttype_and_default_permissions():
    ct = ContentType.objects.get(app_label="duty", model="user")
    assert set(Permission.objects.filter(content_type=ct).values_list("codename", flat=True)) == {
        "add_user", "change_user", "delete_user", "view_user"}


@pytest.mark.django_db
def test_no_pending_migrations():
    call_command("makemigrations", "--check", "--dry-run", stdout=io.StringIO())


@pytest.mark.parametrize("dept,type_,ok", [
    ("MEMS", "개발자", True), ("MEMS", "", False), (None, "", True), (None, "스태프", False),
])
def test_type_matches_department(depts, dept, type_, ok):
    def make():
        User.objects.create_user("u1", name="가", department=depts[dept] if dept else None, type=type_)
    if ok:
        make()
    else:
        with pytest.raises(IntegrityError), transaction.atomic():
            make()


def test_roster_is_active_and_in_department(make_member, depts):
    a = make_member("가")
    make_member("나", active=False)
    User.objects.create_user("adm", name="관리")
    assert list(User.objects.roster()) == [a]


def test_str_is_name(make_member):
    assert str(make_member("가")) == "가"


def test_creating_user_makes_no_alarm_rules(make_member):
    make_member("가", user=True)
    assert not AlarmRule.objects.exists()


def test_admin_login_and_lockout_smoke(client, db):
    User.objects.create_superuser("root", password="Correct-Horse-9", name="루트")
    for _ in range(5):
        client.post("/admin/login/", {"username": "root", "password": "wrong"})
    r = client.post("/admin/login/", {"username": "root", "password": "Correct-Horse-9"})
    assert r.status_code == 429 and "_auth_user_id" not in client.session
    from axes.utils import reset
    reset(username="root")
    r = client.post("/admin/login/?next=/admin/", {"username": "root", "password": "Correct-Horse-9"})
    assert r.status_code == 302 and client.get("/admin/").status_code == 200
