import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..alarms import senders
from ..alarms.forms import RuleForm
from ..alarms.schedule import same_day_notice
from ..errors import DutyError
from ..models import AlarmRule, Department, TelegramAlarmProfile
from ..services import alarms
from ..services.prefs import SHIFT_CHOICES

BOT_MISSING = "텔레그램 봇이 설정되지 않았습니다."


def _hm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def timing_label(r) -> str:
    if r.timing == "before_start":
        h, m = divmod(r.offset, 60)
        return "시작 " + " ".join(p for p in (f"{h}시간" if h else "", f"{m}분" if m else "") if p) + " 전"
    if r.timing == "days":
        return f"당일 {_hm(r.at_minute)}" if r.offset == 0 else f"{r.offset}일 전 {_hm(r.at_minute)}"
    return f"{r.offset}영업일 전 {_hm(r.at_minute)}"


def _names(vals, labels: dict) -> str:
    return "·".join(labels.get(v, v) for v in vals) or "전부"


def condition_label(r, dept_names: dict) -> str:
    s = f"스케줄: {_names(r.shifts, SHIFT_CHOICES)}"
    if r.kind == "personal":
        return s
    return f"부서: {_names(r.depts, dept_names)} / 유형: {_names(r.types, {})} / {s}"


def _bot_link() -> str:
    return f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}" if settings.TELEGRAM_BOT_USERNAME else ""


@login_required
def index(request):
    dept_names = dict(Department.objects.values_list("code", "name"))
    rules = [
        {"r": r, "timing": timing_label(r), "cond": condition_label(r, dept_names),
         "channels": "·".join(n for n, on in (("텔레그램", r.telegram), ("푸시", r.push)) if on)}
        for r in AlarmRule.objects.filter(user=request.user)
    ]
    return render(request, "duty/alarms.html", {
        "tg": TelegramAlarmProfile.objects.filter(user=request.user).first(),
        "tg_token": senders.telegram_enabled(),
        "bot_ready": senders.telegram_enabled() and bool(settings.TELEGRAM_BOT_USERNAME),
        "rules": rules,
    })


@require_POST
@login_required
def telegram_save(request):
    raw = request.POST.get("chat_id", "").strip()
    if not raw:
        alarms.clear_telegram(request.user)
        messages.info(request, "텔레그램 연결을 해제했습니다.")
        return redirect("alarms")
    if not re.fullmatch(r"\d{1,19}", raw) or not 1 <= int(raw) <= 2**63 - 1:
        messages.error(request, "개인 채팅 chat_id(양수 숫자)만 입력하세요.")
    elif not senders.telegram_enabled():
        messages.error(request, BOT_MISSING)
    elif not alarms.take_cooldown(request.user):
        messages.error(request, "잠시 후 다시 시도하세요.")
    else:
        try:
            kind = senders.telegram_check(raw)
        except senders.SendError:
            messages.error(request, "테스트 발송 실패: 봇에게 먼저 /start를 보냈는지 확인하세요.")
        else:
            if kind != "private":
                messages.error(request, "개인 채팅이 아닙니다.")
            else:
                alarms.set_telegram(request.user, str(int(raw)), verified=True)
                messages.success(request, "텔레그램이 연결되었습니다. 테스트 메시지를 확인하세요.")
    return redirect("alarms")


@require_POST
@login_required
def telegram_link(request):
    if not (senders.telegram_enabled() and settings.TELEGRAM_BOT_USERNAME):
        messages.error(request, BOT_MISSING)
        return redirect("alarms")
    return redirect(f"{_bot_link()}?start={alarms.new_link_code(request.user)}")


@require_POST
@login_required
def telegram_link_check(request):
    try:
        messages.success(request, alarms.check_link(request.user))
    except DutyError as e:
        messages.error(request, str(e))
    return redirect("alarms")


def _rule_form(request, rule=None):
    if request.method == "POST":
        form = RuleForm(request.POST)
        if form.is_valid():
            try:
                saved = alarms.save_rule(request.user, form.cleaned_data["rule"], rule)
            except DutyError as e:
                form.add_error(None, str(e))
            else:
                notice = same_day_notice(saved.kind, saved.timing, saved.offset, saved.at_minute, saved.shifts)
                messages.success(request, "규칙을 저장했습니다.")
                if notice:
                    messages.warning(request, notice)
                return redirect("alarms")
    else:
        form = RuleForm(initial=RuleForm.initial_from(rule) if rule else None)
    return render(request, "duty/alarm_rule_form.html", {"form": form, "rule": rule})


@login_required
def rule_new(request):
    return _rule_form(request)


@login_required
def rule_edit(request, pk):
    return _rule_form(request, get_object_or_404(AlarmRule, pk=pk, user=request.user))


@require_POST
@login_required
def rule_delete(request, pk):
    alarms.delete_rule(get_object_or_404(AlarmRule, pk=pk, user=request.user))
    messages.info(request, "규칙을 삭제했습니다.")
    return redirect("alarms")


@require_POST
@login_required
def rule_toggle(request, pk):
    alarms.toggle_rule(get_object_or_404(AlarmRule, pk=pk, user=request.user))
    return redirect("alarms")


@login_required
def help_telegram(request):
    return render(request, "duty/help_telegram.html", {
        "bot_username": settings.TELEGRAM_BOT_USERNAME, "bot_link": _bot_link()})
