"""근무표 단계 설정과 단계 규칙(근무표 통합 설계 5.1·5.2). 쿼리 없는 Board 메서드. 이름은 모두 가상."""
import pytest
from django.db import IntegrityError, transaction

from duty.models import Board, Period
from duty.services import boards
from tests.it_defs import OPS_STEPS

S = Period.Status
D, C, X, G, P = S.DRAFT, S.COLLECTING, S.CLOSED, S.GENERATED, S.PUBLISHED

# (use_draft, use_close) → 켠 단계, 첫 단계, 생성 받는 상태, 기간 수정 상태, {상태: 옮기기 대상}
RULES = [
    ((True, True), [D, C, X, G, P], D, X, {D},
     {D: [C, X], C: [D, X], X: [D, C], G: [D, C, X], P: []}),          # IT
    ((False, False), [C, G, P], C, C, {D, C},
     {D: [C], C: [], X: [C], G: [C], P: []}),                          # 시장운영실(끈 단계에 남은 회차는 취합 중으로만)
    ((False, True), [C, X, G, P], C, X, {D, C},
     {D: [C, X], C: [X], X: [C], G: [C, X], P: []}),                   # 작성 중만 끔
    ((True, False), [D, C, G, P], D, C, {D},
     {D: [C], C: [D], X: [D, C], G: [D, C], P: []}),                   # 마감만 끔
]


@pytest.mark.parametrize("flags,steps,first,gen_from,editable,targets", RULES)
def test_step_rules(flags, steps, first, gen_from, editable, targets):
    b = Board(code="x", name="x", use_draft=flags[0], use_close=flags[1])
    assert b.steps() == steps and b.first_step() == first and b.generate_from() == gen_from
    assert b.editable() == editable
    assert {s: b.move_targets(s) for s in S.values} == targets


def test_default_names_are_status_labels():
    b = Board(code="x", name="x")
    assert [b.step_name(s) for s in S.values] == [label for _, label in S.choices]


def test_ops_names_keep_turned_off_steps():
    b = Board(code="x", name="x", **OPS_STEPS)
    assert [b.step_name(s) for s in S.values] == ["작성 중", "입력 중", "마감", "확정", "배포됨"]


def test_legacy_rule_is_close_off():
    assert boards.legacy_admin_entry(Board(use_close=False)) and not boards.legacy_admin_entry(Board())


@pytest.mark.parametrize("field", ["step_draft", "step_collecting", "step_closed", "step_generated", "step_published"])
def test_step_names_cannot_be_empty(db, field):
    with pytest.raises(IntegrityError), transaction.atomic():
        Board.objects.create(code="x", name="x", **{field: ""})
