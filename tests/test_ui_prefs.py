"""글씨 크기 3단계(기기마다 기억)와 로그인 유지 90일."""
from django.conf import settings

DAYS90 = 90 * 24 * 3600


def test_size_button_next_to_theme_button(client, make_member):
    client.force_login(make_member("가", user=True))
    body = client.get("/me/").content.decode()
    head = body.split("</head>")[0]
    assert "duty-size" in head.split('<link rel="stylesheet"')[0]  # 스타일보다 먼저 적용(깜빡임 없게)
    assert ":root[data-size=l]" in head and ":root[data-size=xl]" in head
    assert "* 1.15" in head and "* 1.3" in head
    top = body.split('id="theme-btn"')[1].split("</div>")[0]
    assert 'id="size-btn"' in top and ">가</button>" in top  # 화면 모드 버튼 바로 옆
    assert "duty-size" in client.get("/login/").content.decode()  # 로그인 화면도


def test_login_lasts_90_days_from_login(client, make_member):
    assert settings.SESSION_COOKIE_AGE == DAYS90
    assert settings.SESSION_SAVE_EVERY_REQUEST is False  # 화면을 열 때 세션 DB 쓰기를 만들지 않는다
    client.force_login(make_member("가", user=True))
    assert client.session.get_expiry_age() == DAYS90
    client.get("/me/")  # 로그인 뒤 첫 화면은 사용법 안내 표시(show_help)를 세션에서 꺼내며 한 번 쓴다
    r = client.get("/me/")
    assert r.status_code == 200 and settings.SESSION_COOKIE_NAME not in r.cookies  # 요청마다 늘리지 않는다
