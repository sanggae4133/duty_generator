import json
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..alarms import senders
from ..alarms.forms import RuleForm
from ..alarms.schedule import same_day_notice
from ..errors import DutyError
from ..models import AlarmRule, CalendarFeed, Department, PushAlarmSubscription, TelegramAlarmProfile
from ..services import alarm_settings, alarms, calendar
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


def _bot_link(conf) -> str:
    return f"https://t.me/{conf.telegram_bot_username}" if conf.telegram_bot_username else ""


@login_required
def index(request):
    return _index(request)


def _index(request, **extra):
    dept_names = dict(Department.objects.values_list("code", "name"))
    rules = [
        {"r": r, "timing": timing_label(r), "cond": condition_label(r, dept_names),
         "channels": "·".join(n for n, on in (("텔레그램", r.telegram), ("푸시", r.push)) if on)}
        for r in AlarmRule.objects.filter(user=request.user)
    ]
    conf = alarm_settings.ensure_push_keys()
    return render(request, "duty/alarms.html", {
        "tg": TelegramAlarmProfile.objects.filter(user=request.user).first(),
        "tg_token": conf.telegram_on,
        "bot_ready": conf.bot_ready,
        "rules": rules,
        "push_on": conf.push_on,
        "vapid_key": conf.vapid_public_key,
        "subs": PushAlarmSubscription.objects.filter(user=request.user).order_by("created_at"),
        "cal": CalendarFeed.objects.filter(user=request.user).first(), "shift_choices": list(SHIFT_CHOICES.items()),
        "cal_member": request.user.department_id is not None,
        **extra,
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
    elif not (conf := alarm_settings.current()).telegram_on:
        messages.error(request, BOT_MISSING)
    elif not alarms.take_cooldown(request.user):
        messages.error(request, "잠시 후 다시 시도하세요.")
    else:
        try:
            kind = senders.telegram_check(conf.sender_config(), raw)
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
    conf = alarm_settings.current()
    if not conf.bot_ready:
        messages.error(request, BOT_MISSING)
        return redirect("alarms")
    return redirect(f"{_bot_link(conf)}?start={alarms.new_link_code(request.user)}")


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
    conf = alarm_settings.current()
    return render(request, "duty/help_telegram.html", {
        "bot_username": conf.telegram_bot_username, "bot_link": _bot_link(conf)})


# ---- 웹 푸시 ----

PUSH_MISSING = "웹 푸시 키를 만들지 못했습니다. 관리자에게 알려 주세요."


def sw_js(request):
    r = render(request, "duty/sw.js", content_type="application/javascript")
    r["Service-Worker-Allowed"] = "/"
    r["Cache-Control"] = "no-cache, max-age=0, must-revalidate"  # 배포한 서비스 워커가 바로 반영되게
    return r


def manifest(request):
    r = render(request, "duty/manifest.webmanifest", content_type="application/manifest+json")
    r["Cache-Control"] = "max-age=3600"
    return r


def _json_body(request) -> dict:
    try:
        data = json.loads(request.body)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise DutyError("잘못된 요청입니다.")
    return data


@require_POST
@login_required
def push_subscribe(request):
    try:
        data = _json_body(request)
        keys = data.get("keys")
        if not isinstance(keys, dict):
            raise DutyError("잘못된 푸시 구독입니다.")
        if not alarm_settings.ensure_push_keys().push_on:
            raise DutyError(PUSH_MISSING)
        alarms.add_subscription(request.user, data.get("endpoint"), keys.get("p256dh"), keys.get("auth"),
                                request.META.get("HTTP_USER_AGENT", ""), data.get("replaces"))
    except alarms.SubscriptionConflict as e:
        return JsonResponse({"error": str(e)}, status=409)
    except DutyError as e:
        return JsonResponse({"error": str(e)}, status=400)
    return JsonResponse({"ok": True})


@require_POST
@login_required
def push_unsubscribe(request):
    try:
        endpoint = _json_body(request).get("endpoint")
    except DutyError as e:
        return JsonResponse({"error": str(e)}, status=400)
    if isinstance(endpoint, str):
        alarms.remove_subscription(request.user, endpoint)
    return JsonResponse({"ok": True})


@require_POST
@login_required
def push_delete(request, pk):
    alarms.delete_subscription(get_object_or_404(PushAlarmSubscription, pk=pk, user=request.user))
    messages.info(request, "기기를 해제했습니다.")
    return redirect("alarms")


@require_POST
@login_required
def push_delete_all(request):
    alarms.delete_all_subscriptions(request.user)
    messages.info(request, "모든 기기를 해제했습니다.")
    return redirect("alarms")


@require_POST
@login_required
def push_test(request):
    if not alarm_settings.ensure_push_keys().push_on:
        messages.error(request, PUSH_MISSING)
    elif not alarms.take_cooldown(request.user):
        messages.error(request, "잠시 후 다시 시도하세요(테스트는 30초에 한 번).")
    else:
        ok, fail = alarms.test_push(request.user)
        messages.info(request, f"테스트 푸시: 성공 {ok} / 실패 {fail}")
    return redirect("alarms")


@require_POST
@login_required
def notify_changes(request):
    on = bool(request.POST.get("on"))
    alarms.set_notify_changes(request.user, on)
    messages.success(request, "내 근무가 바뀌면 알림을 " + ("켰습니다." if on else "껐습니다."))
    return redirect("alarms")


@login_required
def help_push(request):
    return render(request, "duty/help_push.html")


# ---- 캘린더 구독 ----

@require_POST
@login_required
def calendar_issue(request):
    """주소는 이 응답에만 싣는다(리다이렉트·messages·세션 금지)."""
    try:
        url = calendar.issue(request.user)
    except DutyError as e:
        return _index(request, cal_error=str(e))
    r = _index(request, cal_url=url)
    r["Cache-Control"] = "private, no-store"
    r["Referrer-Policy"] = "no-referrer"
    return r


@require_POST
@login_required
def calendar_shifts(request):
    try:
        calendar.set_shifts(request.user, request.POST.getlist("shift"))
    except DutyError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "캘린더에 넣을 근무를 저장했습니다. 캘린더 앱이 새로 고칠 때 반영됩니다.")
    return redirect("alarms")


@require_POST
@login_required
def calendar_revoke(request):
    calendar.revoke(request.user)
    messages.info(request, "캘린더 구독을 껐습니다.")
    return redirect("alarms")


@login_required
def help_calendar(request):
    return render(request, "duty/help_calendar.html")
