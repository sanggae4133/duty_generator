from datetime import time

from django import forms

from ..models import AlarmKind, AlarmTiming, Department
from ..services.prefs import SHIFT_CHOICES
from ..shifts import DEVELOPER, STAFF


class RuleForm(forms.Form):
    enabled = forms.BooleanField(label="켬", required=False, initial=True)
    kind = forms.ChoiceField(label="종류", choices=AlarmKind.choices, initial="personal", widget=forms.RadioSelect)
    timing = forms.ChoiceField(label="기준", choices=AlarmTiming.choices, initial="before_start", widget=forms.RadioSelect)
    hours = forms.IntegerField(label="시간", min_value=0, max_value=168, required=False, initial=2)
    minutes = forms.IntegerField(label="분", min_value=0, max_value=59, required=False, initial=0)
    days = forms.IntegerField(label="일 수", min_value=0, max_value=30, required=False, initial=1)
    at_time = forms.TimeField(label="발송 시각", required=False, initial=time(18, 0),
                              widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))
    telegram = forms.BooleanField(label="텔레그램", required=False, initial=True)
    push = forms.BooleanField(label="푸시", required=False)
    shifts = forms.MultipleChoiceField(label="스케줄", choices=list(SHIFT_CHOICES.items()), required=False,
                                       widget=forms.CheckboxSelectMultiple)
    depts = forms.MultipleChoiceField(label="부서", required=False, widget=forms.CheckboxSelectMultiple)
    types = forms.MultipleChoiceField(label="유형", choices=[(STAFF, STAFF), (DEVELOPER, DEVELOPER)], required=False,
                                      widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["depts"].choices = list(Department.objects.values_list("code", "name"))

    @staticmethod
    def initial_from(rule) -> dict:
        h, m = divmod(rule.offset, 60)
        timed = rule.timing == "before_start"
        return dict(enabled=rule.enabled, kind=rule.kind, timing=rule.timing,
                    hours=h if timed else 2, minutes=m if timed else 0, days=1 if timed else rule.offset,
                    at_time=time(18, 0) if timed else time(*divmod(rule.at_minute, 60)),
                    telegram=rule.telegram, push=rule.push, shifts=rule.shifts, depts=rule.depts, types=rule.types)

    def clean(self):
        c = super().clean()
        if self.errors:
            return c
        if c["kind"] == "personal":  # 숨긴 체크박스 값이 와도 버린다
            c["depts"], c["types"] = [], []
        if c["timing"] == "before_start":
            offset, at_minute = (c["hours"] or 0) * 60 + (c["minutes"] or 0), 0
            if not 1 <= offset <= 10080:
                raise forms.ValidationError("시작 전 시간은 1분 이상 168시간 이하로 입력하세요.")
        else:
            offset, t = c["days"], c["at_time"]
            low = 1 if c["timing"] == "bizdays" else 0
            if offset is None or not low <= offset <= 30:
                raise forms.ValidationError(f"일 수는 {low}~30 사이로 입력하세요.")
            if t is None:
                raise forms.ValidationError("발송 시각을 입력하세요.")
            at_minute = t.hour * 60 + t.minute
        if not (c["telegram"] or c["push"]):
            raise forms.ValidationError("텔레그램이나 푸시 중 하나 이상 선택하세요.")
        c["rule"] = dict(enabled=c["enabled"], kind=c["kind"], timing=c["timing"], offset=offset, at_minute=at_minute,
                         telegram=c["telegram"], push=c["push"], shifts=c["shifts"], depts=c["depts"], types=c["types"])
        return c
