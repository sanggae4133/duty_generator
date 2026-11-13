"""WSGI 요청 가드(Django 앞). 웹은 gunicorn 스레드 4개뿐이라 몇 개의 연결로 전체가 멈출 수 있다.

1. 본문이 max_body 를 넘으면 413.
2. 본문을 Django 보다 먼저 끝까지 읽는다. deadline 안에 다 오지 않으면 소켓 읽기를 닫고 408.
   (gunicorn 은 본문을 읽는 동안 시한이 없고, Funnel 도 본문을 그대로 흘려보낸다.
   recv 마다 settimeout 을 거는 방식은 1바이트씩 흘리면 끝나지 않아 전체 마감을 타이머로 건다.)
3. 비밀번호 해시를 계산하는 POST(login_paths)는 동시에 login_limit 개까지만, 넘치면 바로 429.
"""
import io
import socket
import threading

MAX_BODY = 2 * 1024 * 1024  # 정상 요청 중 가장 큰 것은 출근표 CSV 1MB
DEADLINE = 15  # 초


def _reply(start_response, status, text):
    body = text.encode()
    start_response(status, [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(body))),
                            ("Connection", "close")])
    return [body]


def _shutdown(sock):
    try:
        sock.shutdown(socket.SHUT_RD)
    except OSError:
        pass


def _too_large(environ, start_response):
    # gunicorn 은 Connection: close 를 떼고 남은 본문을 읽어 버리려 한다 → 읽기를 먼저 닫아 바로 끝낸다
    if sock := environ.get("gunicorn.socket"):
        _shutdown(sock)
    return _reply(start_response, "413 Content Too Large", "요청 크기가 너무 큽니다.")


class RequestGuard:
    def __init__(self, app, login_paths=(), max_body=MAX_BODY, deadline=DEADLINE, login_limit=2):
        self.app, self.login_paths = app, set(login_paths)
        self.max_body, self.deadline = max_body, deadline
        self.login_slots = threading.BoundedSemaphore(login_limit)

    def __call__(self, environ, start_response):
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            return _reply(start_response, "400 Bad Request", "잘못된 요청입니다.")
        chunked = "chunked" in environ.get("HTTP_TRANSFER_ENCODING", "").lower()
        if length > self.max_body:
            return _too_large(environ, start_response)
        if length or chunked:
            want = self.max_body + 1 if chunked else length
            sock = environ.get("gunicorn.socket")
            timer = threading.Timer(self.deadline, _shutdown, (sock,)) if sock else None
            if timer:
                timer.daemon = True
                timer.start()
            try:
                body = environ["wsgi.input"].read(want)
            except Exception:  # 마감에 닫혀 청크가 끊긴 경우 등
                body = None
            finally:
                if timer:
                    timer.cancel()
            if body is None or (not chunked and len(body) < length):
                return _reply(start_response, "408 Request Timeout", "요청을 제때 받지 못했습니다. 다시 시도하세요.")
            if len(body) > self.max_body:
                return _too_large(environ, start_response)
            environ["wsgi.input"] = io.BytesIO(body)
            environ["CONTENT_LENGTH"] = str(len(body))
        if environ.get("REQUEST_METHOD") == "POST" and environ.get("PATH_INFO") in self.login_paths:
            if not self.login_slots.acquire(blocking=False):
                return _reply(start_response, "429 Too Many Requests", "로그인 요청이 몰리고 있습니다. 잠시 후 다시 시도하세요.")
            try:
                return self.app(environ, start_response)
            finally:
                self.login_slots.release()
        return self.app(environ, start_response)
