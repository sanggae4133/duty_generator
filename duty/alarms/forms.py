from datetime import time

from django import forms

from ..models import AlarmKind, AlarmTiming, Board, Department
from ..services import boards, prefs
from ..shifts import DEVELOPER, STAFF


def _first_board_id():
    return Board.objects.order_by("id").values_list("pk", flat=True).first()


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
    shifts = forms.MultipleChoiceField(label="스케줄", required=False, widget=forms.CheckboxSelectMultiple)
    depts = forms.MultipleChoiceField(label="부서", required=False, widget=forms.CheckboxSelectMultiple)
    types = forms.MultipleChoiceField(label="유형", choices=[(STAFF, STAFF), (DEVELOPER, DEVELOPER)], required=False,
                                      widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        all_boards = list(Board.objects.order_by("id"))
        # 근무표가 하나면 칸을 숨기고 그 근무표로 고정(1단계 화면 그대로). 부서 선택지는 그 근무표의 부서
        self.fixed_board = all_boards[0] if len(all_boards) == 1 else None
        if self.fixed_board is None:
            self.fields["board"].label_from_instance = lambda b: b.name
            depts = Department.objects.all()  # 고른 근무표 밖의 부서는 normalize 가 막는다
        else:
            del self.fields["board"]
            depts = Department.objects.filter(board=self.fixed_board)
        self.fields["shifts"].choices = list(prefs.choices(boards.active_defs(self._shift_board(all_boards, user))).items())
        self.fields["depts"].choices = list(depts.values_list("code", "name"))

    def _shift_board(self, all_boards, user):
        """스케줄 선택지의 근무표(설계 8.1). 근무표가 하나면 그것, 보고서 = 보낸(편집 땐 규칙의) 근무표, 개인 = 주인의 근무표."""
        if self.fixed_board is not None:
            return self.fixed_board
        src = self.data if self.is_bound else self.initial
        if src.get("kind") == "report":
            picked = str(src.get("board") or "")
            return next((b for b in all_boards if str(b.pk) == picked), all_boards[0] if all_boards else boards.it_board())
        # ponytail: 빈 폼은 처음 그릴 때의 종류·근무표 기준이라 화면에서 종류·근무표를 바꿔도 체크박스는 그대로(저장 때 POST 값으로 다시 검사).
        # 고르는 즉시 다시 그리기는 2단계 근무표 고르기 화면과 함께
        return (boards.board_of(user) if user else None) or boards.it_board()

    @staticmethod
    def initial_from(rule) -> dict:
        h, m = divmod(rule.offset, 60)
        timed = rule.timing == "before_start"
        board_id = rule.board_id or _first_board_id()
        return dict(enabled=rule.enabled, kind=rule.kind, board=board_id, timing=rule.timing,
                    hours=h if timed else 2, minutes=m if timed else 0, days=1 if timed else rule.offset,
                    at_time=time(18, 0) if timed else time(*divmod(rule.at_minute, 60)),
                    telegram=rule.telegram, push=rule.push,
                    # 저장은 '전부 = 빈 목록'이라 그대로 그리면 전부 해제로 보인다 → 전부 체크로
                    shifts=rule.shifts or list(prefs.choices(boards.active_defs(Board.objects.get(pk=board_id)))),
                    depts=rule.depts or list(Department.objects.filter(board_id=board_id).values_list("code", flat=True)),
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
                         push=c["push"], shifts=c["shifts"], depts=c["depts"], types=c["types"])
        return c
