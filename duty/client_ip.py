"""로그인 잠금(axes)이 쓰는 접속 IP. 웹(8090)은 127.0.0.1 에만 열려 있고 앞단은 nginx·tailscaled 뿐이다.
tailscaled 는 X-Forwarded-For 를 실제 접속 IP 하나로 덮어쓰고(클라이언트가 보낸 값은 버린다), nginx 는 그 값을 하나로 넘긴다.
그래서 127.0.0.1 에서 온 요청만 그 헤더의 마지막 값(가장 가까운 프록시가 적은 값)을 믿는다."""

LOCAL = {"127.0.0.1", "::1"}


def client_ip(request) -> str | None:
    remote = request.META.get("REMOTE_ADDR")
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if remote in LOCAL and forwarded.strip():
        return forwarded.split(",")[-1].strip()
    return remote
