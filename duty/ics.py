"""iCalendar(RFC 5545) 직렬화. 순수 모듈(ORM 없음)."""

from dataclasses import dataclass
from datetime import datetime, timezone


def escape_text(s: str) -> str:
    s = s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return s.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")


def fold(line: str) -> str:
    """UTF-8 75옥텟마다 CRLF+공백으로 접는다(이어지는 줄은 공백 포함 75옥텟, 멀티바이트 문자는 쪼개지 않음)."""
    parts, cur = [], b""
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > 75:
            parts.append(cur)
            cur = b" "
        cur += b
    parts.append(cur)
    return b"\r\n".join(parts).decode()


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass
class Event:
    uid: str
    dtstamp: datetime
    start: datetime
    end: datetime
    summary: str
    url: str | None = None

    def __post_init__(self):
        for dt in (self.dtstamp, self.start, self.end):
            if dt.utcoffset() is None:
                raise ValueError("시간대가 없는 datetime 입니다.")


def calendar(name: str, events: list[Event]) -> bytes:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//duty_generator//calendar//KO",
        "CALSCALE:GREGORIAN",
        f"NAME:{escape_text(name)}",
        f"X-WR-CALNAME:{escape_text(name)}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
        "X-WR-TIMEZONE:Asia/Seoul",
        # RFC 5545 §3.6: 컴포넌트가 최소 1개 있어야 하므로 빈 캘린더도 유효하도록 항상 둔다
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Seoul",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        "TZOFFSETFROM:+0900",
        "TZOFFSETTO:+0900",
        "TZNAME:KST",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]
    for e in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{escape_text(e.uid)}",
            f"DTSTAMP:{_utc(e.dtstamp)}",
            f"DTSTART:{_utc(e.start)}",
            f"DTEND:{_utc(e.end)}",
            f"SUMMARY:{escape_text(e.summary)}",
            "TRANSP:TRANSPARENT",
            "STATUS:CONFIRMED",
        ]
        if e.url:
            lines += [f"URL:{e.url}", f"DESCRIPTION:{escape_text('근무표: ' + e.url)}"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "".join(fold(line) + "\r\n" for line in lines).encode()
