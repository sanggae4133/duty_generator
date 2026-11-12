"""도움말: 권한별 사용법 영상, 영상 전달(Range), 첫 로그인 팝업·다시 보지 않기."""
import pytest
from django.urls import reverse

from duty.models import User

BODY = bytes(range(256)) * 4  # 가짜 영상 1024바이트


@pytest.fixture
def videos(settings, tmp_path):
    for name in ("member", "manager", "admin"):
        (tmp_path / f"{name}.mp4").write_bytes(BODY)
    settings.HELP_VIDEO_DIR = tmp_path
    return tmp_path


@pytest.fixture
def people(make_member, admin_user, depts):
    member = make_member("가", user=True)
    manager = make_member("나", user=True)
    depts["MEMS"].managers.add(manager)
    return {"member": member, "manager": manager, "admin": admin_user}


@pytest.mark.parametrize("who,seen", [
    ("member", ["member"]), ("manager", ["member", "manager"]), ("admin", ["member", "manager", "admin"]),
])
def test_help_page_lists_videos_by_role(client, people, videos, who, seen):
    client.force_login(people[who])
    body = client.get("/help/").content.decode()
    for name in ("member", "manager", "admin"):
        assert (f"/help/video/{name}.mp4" in body) == (name in seen), name
    assert 'href="/help/telegram/"' in body and 'href="/help/calendar/"' in body


@pytest.mark.parametrize("who,name,code", [
    ("member", "member", 200), ("member", "manager", 403), ("member", "admin", 403),
    ("manager", "manager", 200), ("manager", "admin", 403), ("admin", "admin", 200), ("admin", "manager", 200),
])
def test_video_permission(client, people, videos, who, name, code):
    client.force_login(people[who])
    r = client.get(f"/help/video/{name}.mp4")
    assert r.status_code == code
    if code == 200:
        assert r["Content-Type"] == "video/mp4" and r["Accept-Ranges"] == "bytes"
        assert b"".join(r.streaming_content if r.streaming else [r.content]) == BODY


def test_video_needs_login_and_known_name(client, people, videos):
    assert client.get("/help/video/member.mp4").status_code == 302
    client.force_login(people["admin"])
    assert client.get("/help/video/nope.mp4").status_code == 404
    (videos / "member.mp4").unlink()
    assert client.get("/help/video/member.mp4").status_code == 404  # 아직 녹화 전


@pytest.mark.parametrize("rng,status,part,crange", [
    ("bytes=0-9", 206, BODY[:10], "bytes 0-9/1024"),
    ("bytes=1000-", 206, BODY[1000:], "bytes 1000-1023/1024"),
    ("bytes=-4", 206, BODY[-4:], "bytes 1020-1023/1024"),
    ("bytes=10-99999", 206, BODY[10:], "bytes 10-1023/1024"),
])
def test_video_range(client, people, videos, rng, status, part, crange):
    """아이폰 Safari 는 Range 로 조각을 받아야 재생한다."""
    client.force_login(people["member"])
    r = client.get("/help/video/member.mp4", HTTP_RANGE=rng)
    assert r.status_code == status and r.content == part
    assert r["Content-Range"] == crange and r["Content-Length"] == str(len(part))


def test_video_range_unsatisfiable(client, people, videos):
    client.force_login(people["member"])
    r = client.get("/help/video/member.mp4", HTTP_RANGE="bytes=2000-")
    assert r.status_code == 416 and r["Content-Range"] == "bytes */1024"


def test_welcome_popup_on_login_until_dismissed(client, people, videos):
    u = people["member"]
    client.post(reverse("login"), {"username": u.username, "password": "unused-Pw-123"})
    assert 'id="help-welcome"' in client.get("/").content.decode()  # 로그인 직후 한 번
    assert 'id="help-welcome"' not in client.get("/").content.decode()  # 같은 로그인 안에서는 다시 안 뜬다
    client.logout()
    client.post(reverse("login"), {"username": u.username, "password": "unused-Pw-123"})
    assert 'id="help-welcome"' in client.get("/").content.decode()  # 그냥 닫았으면 다음 로그인에 또
    r = client.post("/help/dismiss/")
    assert r.status_code in (200, 204) and User.objects.get(pk=u.pk).help_dismissed
    client.logout()
    client.post(reverse("login"), {"username": u.username, "password": "unused-Pw-123"})
    assert 'id="help-welcome"' not in client.get("/").content.decode()
    assert "/help/" in client.get("/").content.decode()  # 메뉴의 도움말에서는 언제든


def test_welcome_popup_waits_for_password_change(client, make_member, videos):
    from duty.accounts import issue_account
    u = make_member("다")
    pw = issue_account(u)
    client.post(reverse("login"), {"username": u.username, "password": pw})
    assert 'id="help-welcome"' not in client.get(reverse("password_change")).content.decode()


def test_dismiss_requires_post(client, people):
    client.force_login(people["member"])
    assert client.get("/help/dismiss/").status_code == 405
