from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from duty import ics

KST = ZoneInfo("Asia/Seoul")
T0 = datetime(2026, 11, 10, 6, 30, tzinfo=KST)
T1 = datetime(2026, 11, 10, 15, 30, tzinfo=KST)


def event(**kw):
    base = dict(uid="20261110-dawn-1@duty-generator", dtstamp=datetime(2026, 11, 1, tzinfo=timezone.utc),
                start=T0, end=T1, summary="새벽 출근 06:30~15:30", url=None)
    return ics.Event(**{**base, **kw})


def lines(body: bytes) -> list[str]:
    text = body.decode()
    assert text.endswith("\r\n")
    return text[:-2].split("\r\n")


def test_escape_text():
    assert ics.escape_text("a\\b;c,d\ne") == "a\\\\b\\;c\\,d\\ne"
    assert ics.escape_text("x\r\ny") == "x\\ny"


def test_fold_ascii():
    line = "SUMMARY:" + "x" * 200
    folded = ics.fold(line)
    parts = folded.split("\r\n")
    assert len(parts) > 1
    assert all(len(p.encode()) <= 75 for p in parts)
    assert all(p.startswith(" ") for p in parts[1:])
    assert parts[0] + "".join(p[1:] for p in parts[1:]) == line


def test_fold_korean_keeps_multibyte():
    line = "SUMMARY:" + "가나다" * 40
    parts = ics.fold(line).split("\r\n")
    assert all(len(p.encode("utf-8")) <= 75 for p in parts)
    for p in parts:
        p.encode("utf-8").decode("utf-8")  # 쪼개진 문자 없음
    assert parts[0] + "".join(p[1:] for p in parts[1:]) == line


def test_fold_boundaries():
    assert ics.fold("A" * 75) == "A" * 75
    assert ics.fold("A" * 76) == "A" * 75 + "\r\n A"
    assert ics.fold("A" * 74 + "가") == "A" * 74 + "\r\n 가"  # 3바이트 문자가 경계에 걸리면 통째로 다음 줄
    assert ics.fold("A" * 72 + "가") == "A" * 72 + "가"  # 정확히 75옥텟


def test_short_line_not_folded():
    assert ics.fold("VERSION:2.0") == "VERSION:2.0"


def test_empty_calendar():
    body = ics.calendar("IT 당번(내 일정)", [])
    ls = lines(body)
    assert ls[0] == "BEGIN:VCALENDAR" and ls[-1] == "END:VCALENDAR"
    assert "VERSION:2.0" in ls and "PRODID:-//duty_generator//calendar//KO" in ls
    assert "CALSCALE:GREGORIAN" in ls
    assert "NAME:IT 당번(내 일정)" in ls and "X-WR-CALNAME:IT 당번(내 일정)" in ls
    assert "REFRESH-INTERVAL;VALUE=DURATION:PT6H" in ls and "X-PUBLISHED-TTL:PT6H" in ls
    assert not any(line.startswith("METHOD") for line in ls)
    assert "BEGIN:VEVENT" not in ls


def test_event_properties_utc():
    ls = lines(ics.calendar("c", [event()]))
    assert "UID:20261110-dawn-1@duty-generator" in ls
    assert "DTSTAMP:20261101T000000Z" in ls
    assert "DTSTART:20261109T213000Z" in ls
    assert "DTEND:20261110T063000Z" in ls
    assert "SUMMARY:새벽 출근 06:30~15:30" in ls
    assert "TRANSP:TRANSPARENT" in ls and "STATUS:CONFIRMED" in ls
    assert not any(line.startswith(("URL", "DESCRIPTION", "SEQUENCE", "BEGIN:VALARM")) for line in ls)
    assert ls.count("BEGIN:VEVENT") == 1 and ls.count("END:VEVENT") == 1


def test_url_not_escaped_description_escaped():
    url = "https://duty.example/a,b;c/me/"
    ls = lines(ics.calendar("c", [event(url=url)]))
    assert f"URL:{url}" in ls
    assert "DESCRIPTION:근무표: https://duty.example/a\\,b\\;c/me/" in ls


def test_summary_escaped():
    ls = lines(ics.calendar("c", [event(summary="a,b")]))
    assert "SUMMARY:a\\,b" in ls


def test_all_lines_crlf():
    body = ics.calendar("c", [event(summary="가" * 100, url="https://duty.example/me/")])
    assert b"\n" not in body.replace(b"\r\n", b"")
    assert all(len(p) <= 75 for p in body.split(b"\r\n"))


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        event(start=datetime(2026, 11, 10, 6, 30))
    with pytest.raises(ValueError):
        event(dtstamp=datetime(2026, 11, 10))
