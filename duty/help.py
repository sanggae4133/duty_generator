"""권한별 사용법 영상 목록. 영상 파일은 settings.HELP_VIDEO_DIR/<name>.mp4."""
from . import perms

VIDEOS = [  # (이름, 제목, 누구를 위한)
    ("member", "근무표 보기·바꾸기", "모든 사용자"),
    ("manager", "출근표 입력", "출근표 입력 담당"),
    ("admin", "회차 운영(취합·생성·배포)", "관리자"),
]


def allowed(user, name: str) -> bool:
    if name == "member":
        return user.is_authenticated
    if name == "manager":
        return perms.is_admin(user) or perms.managed_departments(user).exists()
    return name == "admin" and perms.is_admin(user)


def for_user(user) -> list[dict]:
    return [{"name": n, "title": t, "who": w} for n, t, w in VIDEOS if allowed(user, n)]
