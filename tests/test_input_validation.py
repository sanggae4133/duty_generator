"""입력 검사 강화(검토 3번): 제어 문자, CSV 수식 시작 문자, 회차 기간 한도, 관리 화면 주소, 근무 변경 창의 아이디 노출. 이름은 모두 가상."""
import os
import subprocess
import sys
from datetime import date
from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from openpyxl import load_workbook

from duty import xlsx
from duty.errors import DutyError
from duty.forms import BoardShiftForm
from duty.models import Commute, Period, validate_member_name
from duty.services import periods
from tests.test_views_roster import D, world  # noqa: F401 (world 는 픽스처)


@pytest.mark.parametrize("name", ["가\x0b상", "가\x00", "가\x7f", "가\x1b상"])
def test_member_name_rejects_control_chars(name):
    with pytest.raises(ValidationError):
        validate_member_name(name)


def _shift_name_errors(name):
    f = BoardShiftForm(data={"key": "dawn", "name": name, "start": "06:30", "end": "15:30", "default_alarm": 30})
    f.is_valid()
    return f.errors.get("name")


@pytest.mark.parametrize("name", ["=1+1", "-A1", "+가", "@가", "새\x0b벽"])
def test_shift_name_rejects_formula_start_and_control_chars(db, name):
    assert _shift_name_errors(name)


def test_shift_name_plain_ok(db):
    assert not _shift_name_errors("새벽 A-1")


def test_xlsx_drops_illegal_chars_instead_of_500():
    """이미 저장된 값에 제어 문자가 있어도 엑셀 다운로드는 열린다(글자만 빠진다)."""
    ws = load_workbook(BytesIO(xlsx.build([(D, "월", "IT", "새\x0b벽", "", "가\x01상", "", "")]))).active
    assert ws["D2"].value == "새벽" and ws["F2"].value == "가상"


@pytest.mark.parametrize("start,end", [(date(2026, 11, 2), date(2027, 11, 10)),   # 1년 넘음
                                       (date(1999, 12, 27), date(2000, 1, 7)),    # 2000 년 앞
                                       (date(2099, 12, 28), date(2100, 1, 8))])   # 2099 년 뒤
def test_period_length_and_year_limits(it_board, start, end):
    with pytest.raises(DutyError):
        periods.save_draft(Period(board=it_board, name="a", start_date=start, end_date=end))


def test_period_one_year_ok(it_board):
    assert periods.save_draft(Period(board=it_board, name="a", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))).pk


def _prod_admin_path(tmp_path, value):
    env = {**os.environ, "DUTY_ENV_FILE": "", "DUTY_DEBUG": "0", "DUTY_SECRET_KEY": "x" * 50, "DUTY_DATA_DIR": str(tmp_path)}
    env.pop("DUTY_ADMIN_PATH", None)
    if value is not None:
        env["DUTY_ADMIN_PATH"] = value
    return subprocess.run([sys.executable, "-c", "import config.settings as s; print(s.ADMIN_PATH)"], env=env,
                          capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))


@pytest.mark.parametrize("value", [None, "", "admin", "/admin/"])
def test_prod_needs_unguessable_admin_path(tmp_path, value):
    r = _prod_admin_path(tmp_path, value)
    assert r.returncode != 0 and "DUTY_ADMIN_PATH" in r.stderr


def test_prod_admin_path_set(tmp_path):
    r = _prod_admin_path(tmp_path, "ops-x7")
    assert r.returncode == 0 and r.stdout.strip().endswith("ops-x7")


def test_cell_form_hides_login_ids(client, world, make_member):
    """근무 변경 창(From/To)은 로그인 아이디 대신 번호를 값으로 쓴다(보기 전용 사용자도 GET 으로 받는 목록)."""
    a, b = world
    c = make_member("다")
    client.force_login(a)
    body = client.get(f"/cell/{D}/normal/").content.decode()
    for u in (a, b, c):
        assert f'value="{u.username}"' not in body
    assert f'value="{a.pk}"' in body and f'value="{c.pk}"' in body
    r = client.post(f"/cell/{D}/normal/", {"before": a.pk, "after": c.pk})
    assert r.status_code == 302 and Commute.objects.filter(date=D, member=c, shift="normal").exists()


def test_cell_post_rejects_username_and_garbage(client, world, make_member):
    a, _ = world
    c = make_member("다")
    client.force_login(a)
    for after in (c.username, "x", "999999"):
        client.post(f"/cell/{D}/normal/", {"before": a.pk, "after": after})
        assert Commute.objects.filter(date=D, member=a, shift="normal").exists()  # 조작된 값이 '빼기'로 해석되지 않는다
