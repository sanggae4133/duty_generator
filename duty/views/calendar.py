import hashlib

from django.http import Http404, HttpResponse
from django.utils.cache import get_conditional_response
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_safe

from ..services import calendar

HEADERS = {"Cache-Control": "private, no-cache", "Referrer-Policy": "no-referrer"}


@csrf_exempt  # POST 가 CSRF 403(경로가 django.security.csrf 로그에 남음) 대신 405 로 끝나게
@require_safe
def feed(request, token):
    body = calendar.feed(token)
    if body is None:
        raise Http404
    etag = f'"{hashlib.sha256(body).hexdigest()}"'
    r = HttpResponse(b"" if request.method == "HEAD" else body, content_type="text/calendar; charset=utf-8")
    r = get_conditional_response(request, etag=etag, response=r)
    for k, v in {**HEADERS, "ETag": etag}.items():  # 304 에도 같은 헤더
        r[k] = v
    return r
