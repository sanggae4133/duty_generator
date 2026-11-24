"""관리 화면과 [근무표 설정]이 함께 쓰는 폼(근무표 통합 설계 6.2·7.3): 근무 정의 한 줄·근무표 전체 검사, 회차 단계 칸,
부서 출근조·점심 시각. 검사 규칙은 한 곳에만 둔다."""
from django import forms
from django.core.exceptions import ValidationError

from .models import Board, BoardShift, Department, unsafe_cell_text
from .services import boards
from .shifts import DEVELOPER, LUNCH, SHIFT_KEYS, STAFF, is_slot_cell, shift_defs

# 근무조 키 선택지(관리 화면 표시 이름 "근무조 1"~"근무조 4", 설계 4.1)
SHIFT_KEY_CHOICES = [(k, label) for k, label in BoardShift._meta.get_field("key").choices if k in SHIFT_KEYS]


class BoardShiftForm(forms.ModelForm):
    """근무 정의 한 줄의 검증(설계 4.3). 저장한 줄은 키 칸을 잠근다(BoardShift.clean 이 한 번 더 막는다).
    시각 오류는 start 칸에 붙인다: 그 칸이 오류면 DB 제약(boardshift_times_valid) 검사를 건너뛰어 영어 제약 문구가 함께 뜨지 않는다."""
    eligible_shifts = forms.MultipleChoiceField(label="자격 근무조", required=False, choices=SHIFT_KEY_CHOICES,
                                                widget=forms.CheckboxSelectMultiple,
                                                help_text="장중관제 칸만. 켜진 관제는 하나 이상 고릅니다")
    eligible_types = forms.MultipleChoiceField(label="자격 구분", required=False, choices=[(STAFF, STAFF), (DEVELOPER, DEVELOPER)],
                                               widget=forms.CheckboxSelectMultiple, help_text="장중관제 칸만. 비우면 전원")

    class Meta:
        model = BoardShift
        fields = ["key", "name", "start", "end", "eligible_shifts", "eligible_types", "default_alarm", "active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:  # 저장한 정의의 키는 바꾸지 않는다(보낸 값은 무시된다)
            self.fields["key"].disabled = True

    def clean_name(self):
        v = self.cleaned_data["name"].strip()
        if v in ("date", "day") or "(" in v or unsafe_cell_text(v):  # CSV 열 이름이 된다
            raise forms.ValidationError("이름은 date·day 가 아니어야 하고 ( 와 줄바꿈·제어 문자를 쓸 수 없고 + = - @ 로 시작할 수 없습니다(CSV 열 이름이 됩니다).")
        return v

    def clean_eligible_shifts(self):
        return [k for k in SHIFT_KEYS if k in self.cleaned_data["eligible_shifts"]]

    def clean(self):
        c = super().clean()
        key, start, end = c.get("key"), c.get("start"), c.get("end")
        if not key:
            return c
        if key == LUNCH:
            if start or end:
                self.add_error("start", "점심당번은 시각을 비웁니다(점심 시각은 부서마다 정합니다).")
        elif not (start and end and start < end):
            self.add_error("start", "시작·끝 시각을 넣고 시작을 끝보다 이르게 하세요(당일 근무만).")
        if not is_slot_cell(key) and (c.get("eligible_shifts") or c.get("eligible_types")):
            self.add_error("eligible_shifts", "자격 근무조·자격 구분은 장중관제 칸에만 씁니다.")
        if is_slot_cell(key) and c.get("active") and not c.get("eligible_shifts"):  # 자격자가 없으면 생성이 그 칸을 못 채운다
            self.add_error("eligible_shifts", "장중관제 칸은 자격 근무조를 하나 이상 골라야 합니다.")
        if key not in SHIFT_KEYS and c.get("default_alarm"):
            self.add_error("default_alarm", "기본 알림 대상은 근무조에만 씁니다.")
        return c


class BoardShiftFormSet(forms.BaseInlineFormSet):
    """근무표 전체의 검증(설계 4.3). Django 기본 겹침 검사(영어 칸 이름이 섞인 문구)는 부르지 않고 한국어로 직접 본다:
    이름·키 겹침, 켜진 근무조 하나 이상, 켜진 근무조끼리 시작 시각이 다름(가장 이른 조·이른/가운데/늦은 조가 하나로 정해지게),
    관제 자격 근무조는 이 근무표의 근무조(켜진 관제는 켜진 근무조만), 끄고 나서도 부서마다 켜진 입력 근무조가 하나 이상.
    관리 화면 근무표 인라인과 [근무표 설정] 근무 정의 칸이 함께 쓴다."""

    def clean(self):
        if any(self.errors):
            return
        rows = [f.cleaned_data for f in self.forms if f.cleaned_data.get("key")]  # 비워 둔 추가 줄은 빠진다
        for field, label in (("name", "근무 정의 이름이 겹칩니다"), ("key", "키가 겹칩니다")):
            values = [r[field] for r in rows]
            dup = sorted({v for v in values if values.count(v) > 1})
            if dup:
                names = dict(BoardShift._meta.get_field("key").choices) if field == "key" else {}
                raise ValidationError(f"{label}: {', '.join(names.get(v, v) for v in dup)}")
        on = [r for r in rows if r["key"] in SHIFT_KEYS and r["active"]]
        if not on:
            raise ValidationError("켜진 근무조가 하나 이상 있어야 합니다.")
        if len({r["start"] for r in on}) != len(on):
            raise ValidationError("켜진 근무조끼리 시작 시각이 달라야 합니다(가장 이른 조를 하나로 정할 수 있게).")
        keys, on_keys = {r["key"] for r in rows if r["key"] in SHIFT_KEYS}, {r["key"] for r in on}
        for r in rows:
            picked = set(r.get("eligible_shifts") or ())
            if picked - keys:
                raise ValidationError(f"{r['name']}: 자격 근무조는 이 근무표의 근무조여야 합니다.")
            if r["active"] and picked - on_keys:
                raise ValidationError(f"{r['name']}: 켜진 관제의 자격 근무조는 켜진 근무조여야 합니다.")
        # 부서마다 켜진 입력 근무조 하나 이상. [근무표 설정]은 같은 저장의 부서 출근조(planned_depts = {부서 이름: 키들}, 설계 6.2),
        # 관리 화면은 저장된 부서 출근조로 본다
        planned = getattr(self, "planned_depts", None)
        if planned is not None:
            tail = "아래 부서에서 켜진 근무조를 하나 이상 체크하세요."
        else:
            planned = {d.name: set(d.shift_keys()) for d in self.instance.departments.all()} if self.instance.pk else {}
            tail = "부서의 출근조를 먼저 바꾸세요."
        for name, picked in planned.items():
            if not picked & on_keys:
                raise ValidationError(f"{name} 부서에 켜진 근무조가 하나도 남지 않습니다. {tail}")


STEP_FIELDS = ["step_draft", "step_collecting", "step_closed", "step_generated", "step_published"]


class StepsForm(forms.ModelForm):
    """회차 단계 칸(설계 5.1·5.4): 이름은 비지 않음(모델 제약)·줄바꿈 금지·서로 다름, 켠 단계에서 나오는 버튼 글자가 비거나
    서로 겹치면 그 이름 칸 오류. 관리 화면 근무표 폼(BoardForm)과 [근무표 설정] 단계 칸이 함께 쓴다."""

    class Meta:
        model = Board
        fields = ["use_draft", "use_close", *STEP_FIELDS]

    def clean(self):
        c = super().clean()
        names = [c.get(f) for f in STEP_FIELDS]
        for f, v in zip(STEP_FIELDS, names):  # 단계 이름(설계 5.1): 줄바꿈 금지, 서로 다름
            if v and ("\n" in v or "\r" in v):
                self.add_error(f, "단계 이름에 줄바꿈을 쓸 수 없습니다.")
            elif v and names.count(v) > 1:
                self.add_error(f, f"단계 이름이 겹칩니다: {v}")
        # 버튼 글자 검사(설계 5.4). 단계 칸 자체 오류가 없으면 본다
        if all(names) and not set(STEP_FIELDS) & set(self.errors):
            steps = Board(use_draft=c.get("use_draft"), use_close=c.get("use_close"), **dict(zip(STEP_FIELDS, names)))
            gen, slot = steps.step_buttons(False), steps.step_buttons(True)
            for x in steps.bad_buttons():  # 생성·취소 글자는 생성됨 이름에서, 열기·마감은 취합 중 이름에서 나온다
                # 관제 있을 때의 고정 글자([장중관제 생성]·[재생성]…)와 겹치면 생성됨 이름을 고쳐도 남는다
                fixed = x.strip() and x in (slot["generate"], slot["undo"], slot["regenerate"])
                field = ("step_generated" if x in (gen["generate"], gen["undo"]) and not fixed
                         else "step_closed" if x == gen["close"] and not fixed else "step_collecting")  # 마감 글자가 열기와 같으면 마감 이름 칸
                self.add_error(field, f"버튼 이름이 비거나 다른 버튼과 같아집니다: [{x}]")
        return c


class DeptShiftsForm(forms.ModelForm):
    """[근무표 설정] 부서 한 덩어리(설계 7.2): 가능한 출근조(그 근무표의 켜진 근무조, 시작 시각 순, "이름 시작~끝")와 점심 시각.
    점심 시각 검사는 모델 제약 department_lunch_valid(같은 한국어 문구). 출근조 저장은 board_settings.save_shifts 가 한다."""
    shifts = forms.MultipleChoiceField(label="가능한 출근조", widget=forms.CheckboxSelectMultiple,
                                       error_messages={"required": "출근조를 하나 이상 선택하세요."})

    class Meta:
        model = Department
        fields = ["lunch_start", "lunch_end"]
        widgets = {f: forms.TimeInput(format="%H:%M", attrs={"type": "time"}) for f in ("lunch_start", "lunch_end")}

    def __init__(self, *args, defs, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["shifts"].choices = [(x.key, f"{x.name} {x.start:%H:%M}~{x.end:%H:%M}")
                                         for x in shift_defs(defs) if x.active]
        self.initial.setdefault("shifts", self.instance.shift_keys())

    def shown(self) -> set[str]:
        """화면이 그린 때 체크박스로 보인 키(템플릿이 숨은 칸 "<prefix>-shown" 으로 보낸다). 보내지 않았으면 지금 선택지
        (save_shifts 는 숨은 칸이 없는 부서를 그린 뒤 생긴 부서로 보고 저장하지 않는다).
        save_shifts 는 이 밖의 저장된 키를 남긴다: 그린 뒤 다른 관리자가 켠 근무조를 이 저장이 빼지 않게.
        보낸 값은 참고일 뿐이다: 저장된 키를 남기게만 할 뿐 키를 더하지는 못한다(더하는 것은 체크한 출근조뿐)."""
        raw = self.data.get(self.add_prefix("shown")) if self.is_bound else None
        return set(raw.split(",")) - {""} if raw is not None else {k for k, _ in self.fields["shifts"].choices}

    def shown_value(self) -> str:
        """숨은 칸에 실을 값. 보낸 폼을 다시 그릴 때(확인·오류)는 보낸 값 그대로: 처음 그린 때 보인 키를 지킨다."""
        raw = self.data.get(self.add_prefix("shown")) if self.is_bound else None
        return raw if raw is not None else ",".join(k for k, _ in self.fields["shifts"].choices)


# [근무표 설정] 근무 정의 칸: 관리 화면 인라인과 같은 폼·검사, 빈 추가 줄 하나, 지우기 없음(prefix "shifts")
ShiftFormSet = forms.inlineformset_factory(
    Board, BoardShift, form=BoardShiftForm, formset=BoardShiftFormSet, extra=1, can_delete=False,
    widgets={f: forms.TimeInput(format="%H:%M", attrs={"type": "time"}) for f in ("start", "end")})


def shift_forms(board, data=None):
    """[근무표 설정] 근무 정의와 부서 칸의 폼들(data 가 있으면 보낸 값으로): (근무 정의 formset, 부서마다 DeptShiftsForm).
    부서 폼은 그 근무표 부서만 만든다(prefix "d-<부서 코드>", 순서 = 부서 순서·코드)."""
    defs = boards.defs(board)
    return (ShiftFormSet(data, instance=board),
            [DeptShiftsForm(data, instance=d, prefix=f"d-{d.code}", defs=defs)
             for d in board.departments.order_by("order", "code")])
