from datetime import date

import pytest
from django.core.exceptions import PermissionDenied

from duty.errors import DutyError
from duty.models import ChangeLog, Commute, ControlDuty, Period
from duty.services import changes
from duty.services.roster import find_day

S = Period.Status
D = date(2026, 11, 10)


@pytest.fixture
def world(make_member, fixed_today):
    fixed_today(D)
    p = Period.objects.create(name="p", start_date=D, end_date=D, status=S.PUBLISHED)
    m = {n: make_member(n, user=True) for n in ["가", "나", "다", "라"]}
    m["직원"] = make_member("직원", type="직원", user=True)
    Commute.objects.create(period=p, date=D, member=m["가"], shift="normal")
    Commute.objects.create(period=p, date=D, member=m["나"], shift="night")
    Commute.objects.create(period=p, date=D, member=m["라"], shift="dinner")
    ControlDuty.objects.create(period=p, date=D, slot=0, member=m["가"])
    ControlDuty.objects.create(period=p, date=D, slot=1, member=m["라"])
    return p, m


def test_replace_commute(world):
    p, m = world
    changes.change_cell(m["다"], D, "normal", m["가"], m["다"])
    assert Commute.objects.get(period=p, date=D, member=m["다"]).shift == "normal"
    assert find_day(D).cells["normal"].labels == ["가>다"]
    assert ChangeLog.objects.get().by == m["다"]


def test_removing_commute_warns_when_member_has_duty(world):
    _, m = world
    r = changes.change_cell(m["가"], D, "normal", m["가"], None)
    assert any("관제" in w for w in r)
    assert find_day(D).cells["normal"].removed == ["가"]


def test_add_commute(world):
    _, m = world
    changes.change_cell(m["다"], D, "dawn", None, m["다"])
    assert find_day(D).cells["dawn"].labels == ["+다"]


def test_after_already_in_other_shift_rejected(world):
    _, m = world
    with pytest.raises(DutyError):
        changes.change_cell(m["가"], D, "normal", m["가"], m["나"])


def test_before_not_in_cell_rejected(world):
    _, m = world
    with pytest.raises(DutyError):
        changes.change_cell(m["가"], D, "dawn", m["가"], m["다"])


def test_duty_replace_warns_on_ineligible(world):
    p, m = world
    r = changes.change_cell(m["가"], D, "slot0", m["가"], m["직원"])
    assert ControlDuty.objects.get(period=p, date=D, slot=0).member == m["직원"]
    assert len(r) == 2  # 개발자 아님 + 출근조 없음


def test_duty_only_replace(world):
    _, m = world
    with pytest.raises(DutyError):
        changes.change_cell(m["가"], D, "slot0", m["가"], None)


def test_duty_replace_into_second_slot_warns(world):
    p, m = world
    r = changes.change_cell(m["가"], D, "slot0", m["가"], m["라"])
    assert ControlDuty.objects.filter(period=p, date=D, member=m["라"]).count() == 2
    assert any("다른 관제 칸" in w and "09:30~10:30" in w for w in r)


def test_swap_duty_when_member_holds_two_slots(world):
    p, m = world
    ControlDuty.objects.create(period=p, date=D, slot=2, member=m["나"])
    changes.change_cell(m["가"], D, "slot0", m["가"], m["라"])  # 라: slot0, slot1
    changes.swap(m["가"], D, "slot0", m["라"], "slot2", m["나"])
    slots = lambda n: set(ControlDuty.objects.filter(period=p, date=D, member=m[n]).values_list("slot", flat=True))
    assert slots("라") == {1, 2} and slots("나") == {0}


def test_swap_commute(world):
    p, m = world
    changes.swap(m["가"], D, "normal", m["가"], "night", m["나"])
    assert Commute.objects.get(period=p, date=D, member=m["가"]).shift == "night"
    day = find_day(D)
    assert day.cells["normal"].labels == ["가>나"] and day.cells["night"].labels == ["나>가"]
    assert ChangeLog.objects.count() == 2


def test_swap_duty(world):
    p, m = world
    changes.swap(m["가"], D, "slot0", m["가"], "slot1", m["라"])
    assert ControlDuty.objects.get(period=p, date=D, slot=0).member == m["라"]
    assert ControlDuty.objects.get(period=p, date=D, slot=1).member == m["가"]


def test_swap_across_kinds_rejected(world):
    _, m = world
    with pytest.raises(DutyError):
        changes.swap(m["가"], D, "normal", m["가"], "slot1", m["라"])


def test_past_date_admin_only(world, fixed_today, admin_user):
    _, m = world
    fixed_today(date(2026, 11, 11))
    with pytest.raises(PermissionDenied):
        changes.change_cell(m["다"], D, "normal", m["가"], m["다"])
    changes.change_cell(admin_user, D, "normal", m["가"], m["다"])


def test_unpublished_date_rejected(world):
    _, m = world
    with pytest.raises(DutyError):
        changes.change_cell(m["가"], date(2026, 11, 11), "normal", None, m["다"])


def test_inactive_after_rejected(world):
    _, m = world
    m["다"].is_active = False
    m["다"].save()
    with pytest.raises(DutyError):
        changes.change_cell(m["가"], D, "dawn", None, m["다"])


def test_swap_commute_warns_when_duty_holder_loses_qualifying_shift(world):
    _, m = world
    r = changes.swap(m["가"], D, "normal", m["가"], "night", m["나"])
    assert any("가" in w and "관제" in w for w in r)


def test_add_commute_warns_for_duty_holder_without_qualifying_shift(world):
    p, m = world
    Commute.objects.filter(member=m["가"]).delete()
    r = changes.change_cell(m["가"], D, "dawn", None, m["가"])
    assert any("가" in w and "관제" in w for w in r)


def test_malformed_cell_rejected(world):
    _, m = world
    with pytest.raises(DutyError):
        changes.change_cell(m["가"], D, "slotx", m["가"], m["다"])
    with pytest.raises(DutyError):
        changes.swap(m["가"], D, "slotx", m["가"], "slot1", m["라"])


@pytest.mark.parametrize("who", ["가", "나"])
def test_swap_rejects_inactive_either_side(world, who):
    _, m = world
    m[who].is_active = False
    m[who].save()
    with pytest.raises(DutyError, match=f"{who}은\\(는\\) 재직 중이 아닙니다"):
        changes.swap(m["라"], D, "normal", m["가"], "night", m["나"])
    assert Commute.objects.get(member=m["가"]).shift == "normal"


@pytest.mark.parametrize("who", ["가", "나"])
def test_swap_rejects_department_less_either_side(world, who):
    _, m = world
    m[who].department = None
    m[who].type = ""
    m[who].save()
    with pytest.raises(DutyError, match=f"{who}은\\(는\\) 근무표 대상이 아닙니다"):
        changes.swap(m["라"], D, "normal", m["가"], "night", m["나"])
    assert Commute.objects.get(member=m["가"]).shift == "normal"


def test_inactive_existing_assignment_shown_and_removable(world):
    _, m = world
    m["가"].is_active = False
    m["가"].save()
    day = find_day(D)
    assert "가" in day.members["normal"] and "가" in day.members["slot0"]
    changes.change_cell(m["라"], D, "slot0", m["가"], m["다"])  # 퇴사자를 빼는 교체는 된다
    changes.change_cell(m["라"], D, "normal", m["가"], None)
    assert not Commute.objects.filter(member=m["가"]).exists()


@pytest.mark.parametrize("cell,before", [("dawn", None), ("normal", "가"), ("slot0", "가")])
def test_no_department_user_cannot_be_assigned(world, admin_user, cell, before):
    _, m = world
    rows = (Commute.objects.count(), ControlDuty.objects.count(), ChangeLog.objects.count())
    with pytest.raises(DutyError, match="관리자은\\(는\\) 근무표 대상이 아닙니다"):
        changes.change_cell(m["라"], D, cell, m[before] if before else None, admin_user)
    assert (Commute.objects.count(), ControlDuty.objects.count(), ChangeLog.objects.count()) == rows
    assert not Commute.objects.filter(member=admin_user).exists()
    assert not ControlDuty.objects.filter(member=admin_user).exists()


# ── 근무 변경 창의 기본 = 맞교환(exchange) ──

def test_exchange_swaps_when_to_has_other_shift(world):
    p, m = world  # 가=정상, 나=야간
    changes.exchange(m["가"], D, "normal", m["가"], m["나"])
    assert Commute.objects.get(period=p, date=D, member=m["가"]).shift == "night"
    assert Commute.objects.get(period=p, date=D, member=m["나"]).shift == "normal"
    assert ChangeLog.objects.count() == 2


def test_exchange_replaces_when_to_is_free(world):
    p, m = world  # 다=근무 없음
    changes.exchange(m["가"], D, "normal", m["가"], m["다"])
    assert Commute.objects.get(period=p, date=D, member=m["다"]).shift == "normal"
    assert not Commute.objects.filter(period=p, date=D, member=m["가"]).exists()


def test_exchange_same_cell_rejected(world):
    p, m = world
    Commute.objects.create(period=p, date=D, member=m["다"], shift="normal")
    with pytest.raises(DutyError, match="이미 이 칸"):
        changes.exchange(m["가"], D, "normal", m["가"], m["다"])


def test_exchange_slots(world):
    p, m = world  # 가=slot0, 라=slot1, 나=관제 없음
    changes.exchange(m["가"], D, "slot0", m["가"], m["라"])
    assert ControlDuty.objects.get(period=p, date=D, slot=0).member == m["라"]
    assert ControlDuty.objects.get(period=p, date=D, slot=1).member == m["가"]
    changes.exchange(m["가"], D, "slot1", m["가"], m["나"])  # 관제 없는 사람이면 교체
    assert ControlDuty.objects.get(period=p, date=D, slot=1).member == m["나"]


def test_exchange_add_or_remove_only(world):
    p, m = world
    changes.exchange(m["가"], D, "normal", m["가"], None)  # 빼기만
    assert not Commute.objects.filter(period=p, date=D, member=m["가"]).exists()
    changes.exchange(m["가"], D, "dawn", None, m["다"])  # 넣기만
    assert Commute.objects.get(period=p, date=D, member=m["다"]).shift == "dawn"
