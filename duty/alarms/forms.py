from datetime import time

from django import forms
from django.db.models import Case, Value, When

from ..models import AlarmKind, AlarmTiming, Board, Department
from ..services import boards, prefs
from ..shifts import DEVELOPER, STAFF


class RuleForm(forms.Form):
    enabled = forms.BooleanField(label="켬", required=False, initial=True)
    kind = forms.ChoiceField(label="종류", choices=AlarmKind.choices, initial="personal", widget=forms.RadioSelect)
    board = forms.ModelChoiceField(label="근무표", queryset=Board.objects.order_by("id"), required=False,
                                   empty_label=None)
    timing = forms.ChoiceField(label="기준", choices=AlarmTiming.choices, initial="before_start", widget=forms.RadioSelect)
    hours = forms.IntegerField(label="시간", min_value=0, max_value=168, required=False, initial=2)
    minutes = forms.IntegerField(label="분", min_value=0, max_value=59, required=False, initial=0)
    days = forms.IntegerField(label="일 수", min_value=0, max_value=30, required=False, initial=1)
    at_time = forms.TimeField(label="발송 시각", required=False, initial=time(18, 0),
                              widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))
    telegram = forms.BooleanField(label="텔레그램", required=False, initial=True)
    push = forms.BooleanField(label="푸시", required=False)
    shifts = forms.MultipleChoiceField(label="근무", required=False, widget=forms.CheckboxSelectMultiple)
    depts = forms.MultipleChoiceField(label="부서", required=False, widget=forms.CheckboxSelectMultiple)
    types = forms.MultipleChoiceField(label="구분", choices=[(STAFF, STAFF), (DEVELOPER, DEVELOPER)], required=False,
                                      widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        all_boards = list(Board.objects.order_by("id"))
        self.home = boards.home(user) if user else all_boards[0]  # 내 근무표(user 없이 만든 폼은 첫 근무표)
        all_boards = boards.in_order(all_boards, self.home)  # 내 근무표 맨 위(설계 9.5). 아래 Case/When 과 같은 순서를 지킨다
        # 근무표가 하나면 칸을 숨기고 그 근무표로 고정(1단계 화면 그대로)
        self.fixed_board = all_boards[0] if len(all_boards) == 1 else None
        if self.fixed_board is None:
            self.fields["board"].label_from_instance = lambda b: b.name
            # boards.in_order 와 같은 순서(내 근무표 먼저, id 순). 한쪽을 바꾸면 다른 쪽도 바꾼다
            self.fields["board"].queryset = Board.objects.order_by(
                Case(When(pk=self.home.pk, then=Value(0)), default=Value(1)), "id")
        else:
            del self.fields["board"]
        board = self._shift_board(all_boards, user)
        self.fields["shifts"].choices = list(prefs.choices(boards.active_defs(board)).items())
        if not prefs.has_types(boards.active_defs(board)):  # 유형은 관제 있는 근무표에만(근무표 화면과 같은 규칙)
            del self.fields["types"]
        # 부서 선택지 = 고른 근무표의 부서(설계 8.1). 개인 규칙은 부서 칸을 숨기고 저장 때 버리므로 막지 않는다
        report = (self.data if self.is_bound else self.initial).get("kind") == "report"
        depts = Department.objects.filter(board=board) if self.fixed_board or report else Department.objects.all()
        self.fields["depts"].choices = list(depts.values_list("code", "name"))

    def _shift_board(self, all_boards, user):
        """스케줄 선택지의 근무표(설계 8.1). 근무표가 하나면 그것, 보고서 = 보낸(편집 땐 규칙의) 근무표, 개인 = 주인의 내 근무표."""
        if self.fixed_board is not None:
            return self.fixed_board
        src = self.data if self.is_bound else self.initial
        if src.get("kind") == "report":
            picked = str(src.get("board") or "")
            return next((b for b in all_boards if str(b.pk) == picked), all_boards[0])  # 안 골랐으면 목록 첫 줄 = 내 근무표
        # 화면에서 종류·근무표를 바꾸면 redraw 로 다시 그린다(alarm_rule_form.html)
        return self.home

    @classmethod
    def redraw(cls, data, user=None):
        """종류·근무표를 바꿨을 때 다시 그리는 빈 폼(검사·저장 없음): 입력한 값은 두고 스케줄·부서는 새 근무표의 '전부'로."""
        probe = cls(data, user=user)  # 바뀐 종류·근무표 기준의 선택지
        initial = {n: f.widget.value_from_datadict(data, None, n) for n, f in probe.fields.items()}
        initial.update(shifts=[c for c, _ in probe.fields["shifts"].choices],
                       depts=[c for c, _ in probe.fields["depts"].choices])
        return cls(initial=initial, user=user)

    @staticmethod
    def initial_from(rule) -> dict:
        h, m = divmod(rule.offset, 60)
        timed = rule.timing == "before_start"
        # '전부'를 체크로 그릴 근무표: 보고서 = 규칙의 근무표, 개인 = 주인의 내 근무표
        board = rule.board if rule.board_id else boards.home(rule.user)
        return dict(enabled=rule.enabled, kind=rule.kind, board=board.pk, timing=rule.timing,
                    hours=h if timed else 2, minutes=m if timed else 0, days=1 if timed else rule.offset,
                    at_time=time(18, 0) if timed else time(*divmod(rule.at_minute, 60)),
                    telegram=rule.telegram, push=rule.push,
                    # 저장은 '전부 = 빈 목록'이라 그대로 그리면 전부 해제로 보인다 → 전부 체크로
                    shifts=rule.shifts or list(prefs.choices(boards.active_defs(board))),
                    depts=rule.depts or list(Department.objects.filter(board=board).values_list("code", flat=True)),
                    types=rule.types or [STAFF, DEVELOPER])

    def clean(self):
        c = super().clean()
        if self.errors:
            return c
        board = c.get("board") if "board" in self.fields else self.fixed_board
        if c["kind"] == "personal":  # 숨긴 체크박스 값이 와도 버린다. 개인 규칙의 근무표 = 주인의 근무표
            c["depts"], c["types"], board = [], [], None
        elif board is None:
            raise forms.ValidationError("근무표를 고르세요.")
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
        c["rule"] = dict(enabled=c["enabled"], kind=c["kind"], board_id=board.pk if board else None,
                         timing=c["timing"], offset=offset, at_minute=at_minute, telegram=c["telegram"],
                         push=c["push"], shifts=c["shifts"], depts=c["depts"], types=c.get("types", []))
        return c
