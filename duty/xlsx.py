"""엑셀(.xlsx) 다운로드 파일 만들기. 순수 모듈(ORM 없음): 줄 목록을 받아 파일 바이트를 돌려준다."""

from io import BytesIO
from urllib.parse import quote

from openpyxl import Workbook
from openpyxl.styles import Font

HEAD = ("날짜", "요일", "근무표", "칸", "시간", "이름", "부서", "사유")
WIDTHS = (12, 6, 16, 12, 14, 12, 14, 8)  # 한글 한 글자 ≈ 2칸
MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def build(rows) -> bytes:
    """rows = (날짜(date), 요일, 근무표, 칸, 시간, 이름, 부서, 사유) 줄들. 머리줄 굵게·고정, 자동 필터."""
    wb = Workbook()
    ws = wb.active
    ws.title = "근무"
    ws.append(HEAD)
    for r in rows:
        ws.append([v or None for v in r])  # 빈 사유는 빈 칸
        for c in ws[ws.max_row]:  # '=' 로 시작하는 이름도 글자로(관리자가 넣은 값이 받는 사람 엑셀에서 수식으로 돌지 않게)
            if isinstance(c.value, str) and c.value.startswith("="):
                c.data_type = "s"
    for c in ws[1]:
        c.font = Font(bold=True)
    for c in ws["A"][1:]:
        c.number_format = "yyyy-mm-dd"
    for i, w in enumerate(WIDTHS):
        ws.column_dimensions[chr(65 + i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def disposition(filename: str) -> str:
    """한글 파일 이름(RFC 5987 filename*)과 옛 프로그램용 ASCII 이름."""
    return f"attachment; filename=\"duty.xlsx\"; filename*=UTF-8''{quote(filename)}"
