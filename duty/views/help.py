import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .. import accounts, help as guide


@login_required
def index(request):
    return render(request, "duty/help.html", {"videos": guide.for_user(request.user)})


@login_required
def video(request, name):
    if name not in {n for n, *_ in guide.VIDEOS}:
        raise Http404
    if not guide.allowed(request.user, name):
        return HttpResponse(status=403)
    path = settings.HELP_VIDEO_DIR / f"{name}.mp4"
    if not path.is_file():
        raise Http404
    size = path.stat().st_size
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", request.headers.get("Range", "").strip())
    if not m or m[1] == m[2] == "":
        r = FileResponse(open(path, "rb"), content_type="video/mp4")
    else:  # 아이폰 Safari 는 Range 로 조각을 받아야 재생한다
        start, end = (size - int(m[2]), size - 1) if m[1] == "" else (int(m[1]), min(int(m[2] or size - 1), size - 1))
        start = max(start, 0)
        if start > end:
            r = HttpResponse(status=416)
            r["Content-Range"] = f"bytes */{size}"
            return r
        with open(path, "rb") as f:  # ponytail: 조각을 메모리로 읽는다. 영상이 수 MB 라 충분, 커지면 스트리밍
            f.seek(start)
            r = HttpResponse(f.read(end - start + 1), status=206, content_type="video/mp4")
        r["Content-Range"] = f"bytes {start}-{end}/{size}"
        r["Content-Length"] = str(end - start + 1)
    r["Accept-Ranges"] = "bytes"
    r["Cache-Control"] = "private, max-age=3600"
    return r


@login_required
@require_POST
def dismiss(request):
    accounts.dismiss_help(request.user)
    return HttpResponse(status=204)
