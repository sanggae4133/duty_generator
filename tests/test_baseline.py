"""실제 1년치 출근표(2026-09-07~2027-09-03)로 생성 품질을 고정한다.
기존 Apps Script 결과는 편차 6(Phase 2 미동작). 이식본은 목표 2에 도달해야 한다."""

import json
from datetime import date
from pathlib import Path

from duty.generator import generate_control_duty


def test_baseline_reaches_target_spread():
    data = json.loads((Path(__file__).parent / "fixtures" / "baseline_commutes.json").read_text())
    days = {date.fromisoformat(d): {k: set(v) for k, v in s.items()} for d, s in data["days"].items()}
    out = generate_control_duty(sorted(days), days, set(data["developers"]), seed=20261109)
    assert out.reached, f"spread={out.spread}"
    assert sum(out.counts.values()) == len(days) * 10
