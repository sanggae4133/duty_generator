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
    r = client.get("/help/video/member.mp4")  # 일반 사용자 영상은 로그인 전에도(가짜 데이터)
    assert r.status_code == 200
    r.close()
    for name in ("manager", "admin"):
        r = client.get(f"/help/video/{name}.mp4")
        assert r.status_code == 302 and r.url.startswith("/login/")
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
    assert r.status_code == status and b"".join(r.streaming_content) == part
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


def test_popup_flag_survives_partial_responses(client, people, videos):
    """부분 응답(근무 변경 팝업·manifest)이 먼저 와도 팝업 표시 기회를 잃지 않는다."""
    u = people["member"]
    client.post(reverse("login"), {"username": u.username, "password": "unused-Pw-123"})
    client.get("/manifest.webmanifest")
    client.get("/cell/2026-11-10/normal/")
    assert 'id="help-welcome"' in client.get("/").content.decode()


def test_video_range_huge_number(client, people, videos):
    client.force_login(people["member"])
    r = client.get("/help/video/member.mp4", HTTP_RANGE="bytes=" + "9" * 5000 + "-")
    assert r.status_code in (200, 416)  # 500 이 아니면 된다(형식 밖은 전체 응답)
    r.close()


def test_help_page_has_text_steps(client, people, videos):
    client.force_login(people["admin"])
    body = client.get("/help/").content.decode()
    assert body.count("글로 보기") == 3 and "취합 마감" in body



def test_public_help_before_login(client, db, videos):
    """로그인 화면의 버튼으로 들어가는 도움말: 로그인 안내 + 일반 사용자 영상만, 권한 영상·설정 도움말은 숨김."""
    login = client.get("/login/").content.decode()
    assert 'href="/help/"' in login and "사용법" in login
    body = client.get("/help/").content.decode()
    assert "멤버 코드" in body and "15분" in body and "/help/video/member.mp4" in body
    assert "/help/video/manager.mp4" not in body and "/help/video/admin.mp4" not in body
    assert 'href="/help/telegram/"' not in body and "로그인" in body



def test_range_is_capped_and_streamed(client, people, settings, tmp_path):
    """공개 영상: 큰 Range 도 한 번에 최대 1MB 를 조금씩 보내고(메모리 고정), HEAD 는 파일을 읽지 않는다."""
    big = bytes(range(256)) * (5 * 4096)  # 5MB
    (tmp_path / "member.mp4").write_bytes(big)
    settings.HELP_VIDEO_DIR = tmp_path
    r = client.get("/help/video/member.mp4", HTTP_RANGE="bytes=0-")
    assert r.status_code == 206 and r.streaming
    body = b"".join(r.streaming_content)
    assert body == big[:1 << 20] and r["Content-Range"] == f"bytes 0-{(1 << 20) - 1}/{len(big)}"
    from unittest import mock
    with mock.patch("builtins.open", side_effect=AssertionError("HEAD 가 파일을 열었다")):
        h = client.head("/help/video/member.mp4", HTTP_RANGE="bytes=0-")
        assert h.status_code == 206 and h["Content-Length"] == str(1 << 20)
        h = client.head("/help/video/member.mp4")  # Range 없는 HEAD 도
        assert h.status_code == 200 and h["Content-Length"] == str(len(big)) and h["Accept-Ranges"] == "bytes"
