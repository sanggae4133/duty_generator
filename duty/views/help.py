import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .. import accounts, help as guide


CHUNK = 1 << 20  # Range 응답 한 번의 최대 크기


def _read(path, start: int, length: int):
    with open(path, "rb") as f:
        f.seek(start)
        while length > 0:
            b = f.read(min(64 * 1024, length))
            if not b:
                return
            length -= len(b)
            yield b


def index(request):
    """로그인 전에도 열린다(로그인 화면의 [사용법 보기]): 로그인 안내 + 일반 사용자 영상. 권한 영상·설정 도움말은 로그인 뒤."""
    return render(request, "duty/help.html", {"videos": guide.for_user(request.user)})


def video(request, name):
    if name not in {n for n, *_ in guide.VIDEOS}:
        raise Http404
    if not guide.allowed(request.user, name):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        return HttpResponse(status=403)
    path = settings.HELP_VIDEO_DIR / f"{name}.mp4"
    if not path.is_file():
        raise Http404
    size = path.stat().st_size
    m = re.fullmatch(r"bytes=(\d{0,15})-(\d{0,15})", request.headers.get("Range", "").strip())
    if not m or m[1] == m[2] == "":
        r = FileResponse(open(path, "rb"), content_type="video/mp4")
    else:  # 아이폰 Safari 는 Range 로 조각을 받아야 재생한다
        start, end = (size - int(m[2]), size - 1) if m[1] == "" else (int(m[1]), min(int(m[2] or size - 1), size - 1))
        start = max(start, 0)
        if start > end:
            r = HttpResponse(status=416)
            r["Content-Range"] = f"bytes */{size}"
            return r
        # 로그인 전에도 열린 주소라 한 번에 최대 1MB 만, 조금씩 읽어 보낸다(메모리 고정). 브라우저가 다음 조각을 다시 요청한다
        end = min(end, start + CHUNK - 1)
        length = end - start + 1
        if request.method == "HEAD":
            r = HttpResponse(status=206, content_type="video/mp4")
        else:
            r = StreamingHttpResponse(_read(path, start, length), status=206, content_type="video/mp4")
        r["Content-Range"] = f"bytes {start}-{end}/{size}"
        r["Content-Length"] = str(length)
    r["Accept-Ranges"] = "bytes"
    r["Cache-Control"] = "private, max-age=3600"
    return r


@login_required
@require_POST
def dismiss(request):
    accounts.dismiss_help(request.user)
    return HttpResponse(status=204)
