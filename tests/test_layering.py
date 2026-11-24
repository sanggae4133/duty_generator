import subprocess
import sys


def test_pure_modules_do_not_import_orm():
    """순수 모듈(CLAUDE.md)은 import 만으로 모델·서비스를 끌어오지 않는다. pytest 는 Django 를 이미 올렸으니 새 프로세스에서 본다."""
    code = ("import sys, duty.shifts, duty.generator, duty.csv_io, duty.ics, duty.alarms.plan, duty.alarms.schedule, "
            "duty.alarms.messages, duty.alarms.senders\n"
            "print(sorted(m for m in sys.modules if m == 'duty.models' or m.startswith(('duty.services', 'django.db'))))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"
