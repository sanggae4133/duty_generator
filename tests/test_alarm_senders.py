import io
import json
import socket
import urllib.error
from types import SimpleNamespace

import pytest
from pywebpush import WebPushException

from duty.alarms import senders

CFG = senders.Config(telegram_token="TOK", vapid_private_key="PRIV", vapid_subject="mailto:a@b.c")


class Resp:
    def __init__(self, body):
        self.body = body

    def read(self):
        return json.dumps(self.body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def http_error(code, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else b"not json"
    return urllib.error.HTTPError("u", code, "m", headers or {}, io.BytesIO(data))


@pytest.fixture
def tg(monkeypatch):
    calls = []
    state = {"result": Resp({"ok": True, "result": {"chat": {"type": "private"}}}), "raise": None}

    def fake(req, timeout=None):
        calls.append((req, timeout))
        if state["raise"]:
            raise state["raise"]
        return state["result"]

    monkeypatch.setattr(senders.urllib.request, "urlopen", fake)
    return calls, state


def test_telegram_send_request(tg):
    calls, _ = tg
    r = senders.telegram_send(CFG, "123", "안녕")
    req, timeout = calls[0]
    assert req.full_url == "https://api.telegram.org/botTOK/sendMessage"
    assert json.loads(req.data) == {"chat_id": "123", "text": "안녕"}
    assert timeout == 10
    assert r["chat"]["type"] == "private"


@pytest.mark.parametrize("code,exc", [(400, senders.Permanent), (401, senders.Permanent),
                                      (403, senders.Permanent), (404, senders.Permanent),
                                      (500, senders.Temporary), (502, senders.Temporary)])
def test_telegram_errors(tg, code, exc):
    _, state = tg
    state["raise"] = http_error(code, {"ok": False})
    with pytest.raises(exc) as e:
        senders.telegram_send(CFG, "1", "x")
    assert e.value.status == code
    assert "TOK" not in str(e.value)


def test_telegram_429_retry_after(tg):
    _, state = tg
    state["raise"] = http_error(429, {"ok": False, "parameters": {"retry_after": 7}})
    with pytest.raises(senders.RetryLater) as e:
        senders.telegram_send(CFG, "1", "x")
    assert e.value.seconds == 7 and e.value.status == 429


def test_telegram_429_non_json(tg):
    _, state = tg
    state["raise"] = http_error(429)
    with pytest.raises(senders.RetryLater) as e:
        senders.telegram_send(CFG, "1", "x")
    assert e.value.seconds is None


@pytest.mark.parametrize("err", [urllib.error.URLError("x"), socket.timeout(), TimeoutError()])
def test_telegram_network(tg, err):
    _, state = tg
    state["raise"] = err
    with pytest.raises(senders.Temporary) as e:
        senders.telegram_send(CFG, "1", "x")
    assert e.value.status is None


def test_config_repr_hides_secrets():
    cfg = senders.Config(telegram_token="TOK-secret", vapid_private_key="PRIV-secret", vapid_subject="mailto:a@b.c")
    assert "secret" not in repr(cfg) and "secret" not in str(cfg)


SUB = SimpleNamespace(endpoint="https://fcm.googleapis.com/x", p256dh="P", auth="A")


@pytest.fixture
def wp(monkeypatch):
    calls = []
    state = {"raise": None}

    def fake(**kw):
        calls.append(kw)
        if state["raise"]:
            raise state["raise"]

    monkeypatch.setattr(senders, "webpush", fake)
    return calls, state


def wpe(code, headers=None):
    return WebPushException("boom", response=SimpleNamespace(status_code=code, headers=headers or {}))


def test_push_bad_vapid_is_temporary(wp):
    from py_vapid import VapidException
    _, state = wp
    state["raise"] = VapidException("Missing 'sub' from claims.")
    with pytest.raises(senders.Temporary) as e:
        senders.push_send(CFG, SUB, "t", "b", "/u", 60)
    assert e.value.status is None


def test_push_send_args(wp):
    calls, _ = wp
    senders.push_send(CFG, SUB, "제목", "본문", "/u", 300)
    kw = calls[0]
    assert kw["subscription_info"] == {"endpoint": SUB.endpoint, "keys": {"p256dh": "P", "auth": "A"}}
    assert json.loads(kw["data"]) == {"title": "제목", "body": "본문", "url": "/u"}
    assert kw["vapid_private_key"] == "PRIV"
    assert kw["vapid_claims"] == {"sub": "mailto:a@b.c"}
    assert kw["timeout"] == 10 and kw["ttl"] == 300


@pytest.mark.parametrize("code,exc", [(404, senders.Gone), (410, senders.Gone),
                                      (400, senders.Permanent), (413, senders.Permanent),
                                      (401, senders.Temporary), (403, senders.Temporary),
                                      (500, senders.Temporary), (502, senders.Temporary)])
def test_push_errors(wp, code, exc):
    _, state = wp
    state["raise"] = wpe(code)
    with pytest.raises(exc) as e:
        senders.push_send(CFG, SUB, "t", "b", "/u", 60)
    assert e.value.status == code
    assert SUB.endpoint not in str(e.value)


@pytest.mark.parametrize("code", [429, 503])
def test_push_retry_after(wp, code):
    _, state = wp
    state["raise"] = wpe(code, {"Retry-After": "12"})
    with pytest.raises(senders.RetryLater) as e:
        senders.push_send(CFG, SUB, "t", "b", "/u", 60)
    assert e.value.seconds == 12
    state["raise"] = wpe(code, {"Retry-After": "Wed, 21 Oct"})
    with pytest.raises(senders.RetryLater) as e:
        senders.push_send(CFG, SUB, "t", "b", "/u", 60)
    assert e.value.seconds is None


def test_push_network_and_noresponse(wp):
    _, state = wp
    for err in [WebPushException("x"), TimeoutError(), OSError("net")]:
        state["raise"] = err
        with pytest.raises(senders.Temporary):
            senders.push_send(CFG, SUB, "t", "b", "/u", 60)


# --- fix round 1 ---
@pytest.mark.parametrize("code", [405, 422, 409])
def test_telegram_other_4xx_permanent(tg, code):
    _, state = tg
    state["raise"] = http_error(code, {"ok": False})
    with pytest.raises(senders.Permanent) as e:
        senders.telegram_send(CFG, "1", "x")
    assert e.value.status == code


@pytest.mark.parametrize("body", [[1], "str", {"parameters": "x"}, {"parameters": {"retry_after": "7"}}])
def test_telegram_429_odd_body(tg, body):
    _, state = tg
    state["raise"] = http_error(429, body)
    with pytest.raises(senders.RetryLater) as e:
        senders.telegram_send(CFG, "1", "x")
    assert e.value.seconds is None


def test_telegram_no_token_no_request(tg):
    calls, _ = tg
    with pytest.raises(senders.Permanent) as e:
        senders.telegram_send(senders.Config(), "1", "x")
    assert e.value.status is None and calls == []


@pytest.mark.parametrize("code", [429, 503])
def test_push_no_retry_after(wp, code):
    _, state = wp
    state["raise"] = wpe(code)
    with pytest.raises(senders.RetryLater) as e:
        senders.push_send(CFG, SUB, "t", "b", "/u", 60)
    assert e.value.seconds is None and e.value.status == code


@pytest.mark.parametrize("hdr,expected", [
    ("Wed, 21 Oct 2026 07:28:00 GMT", 20),        # now 07:27:39.5 -> ceil 21? see below
    ("Wed, 21 Oct 2026 07:27:00 GMT", None),      # past
    ("Wed, 21 Oct 2026 07:27:40 GMT", 1),
    ("-5", None), ("0", 0), ("30", 30), ("abc", None), ("", None),
    ("Wed, 99 Foo 2026 07:28:00 GMT", None),
])
def test_push_retry_after_forms(wp, monkeypatch, hdr, expected):
    from datetime import datetime, timezone
    monkeypatch.setattr(senders, "_utcnow", lambda: datetime(2026, 10, 21, 7, 27, 39, 500000, tzinfo=timezone.utc))
    if hdr.startswith("Wed, 21 Oct 2026 07:28"):
        expected = 21
    _, state = wp
    state["raise"] = wpe(429, {"Retry-After": hdr})
    with pytest.raises(senders.RetryLater) as e:
        senders.push_send(CFG, SUB, "t", "b", "/u", 60)
    assert e.value.seconds == expected


@pytest.mark.parametrize("err", [ValueError("secret-key"), TypeError("secret-key")])
def test_push_bad_key_temporary(wp, err):
    _, state = wp
    state["raise"] = err
    with pytest.raises(senders.Temporary) as e:
        senders.push_send(CFG, SUB, "t", "b", "/u", 60)
    assert e.value.status is None and "secret" not in str(e.value)


def test_telegram_get_updates(tg):
    calls, state = tg
    state["result"] = Resp({"ok": True, "result": [{"update_id": 5}]})
    assert senders.telegram_get_updates(CFG) == [{"update_id": 5}]
    assert senders.telegram_get_updates(CFG, offset=6, limit=50) == [{"update_id": 5}]
    assert calls[0][0].full_url == "https://api.telegram.org/botTOK/getUpdates"
    assert json.loads(calls[0][0].data) == {"limit": 100, "allowed_updates": ["message"]}
    assert json.loads(calls[1][0].data) == {"offset": 6, "limit": 50, "allowed_updates": ["message"]}


def test_telegram_get_updates_409_and_malformed(tg):
    _, state = tg
    state["raise"] = http_error(409, {"ok": False})
    with pytest.raises(senders.Permanent) as e:
        senders.telegram_get_updates(CFG)
    assert e.value.status == 409
    state["raise"] = None
    state["result"] = Resp({"ok": True, "result": {"not": "list"}})
    with pytest.raises(senders.Temporary):
        senders.telegram_get_updates(CFG)


def test_push_send_rechecks_endpoint(wp):
    calls, _ = wp
    with pytest.raises(senders.Gone):
        senders.push_send(CFG, SimpleNamespace(endpoint="https://evil.example\\.fcm.googleapis.com/x", p256dh="P", auth="A"),
                          "t", "b", "/u", 60)
    assert calls == []
