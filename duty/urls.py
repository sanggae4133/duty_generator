from datetime import date

from django.contrib.auth import views as auth_views
from django.urls import path, register_converter

from .views import alarms as alarm_views
from .views import auth as auth_views_local
from .views import calendar as calendar_views
from .views import collect as collect_views
from .views import help as help_views
from .views import manage as manage_views
from .views import roster as roster_views


class IsoDateConverter:
    regex = r"\d{4}-\d{2}-\d{2}"

    def to_python(self, value):
        return date.fromisoformat(value)

    def to_url(self, value):
        return value.isoformat()


register_converter(IsoDateConverter, "isodate")

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="duty/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password/", auth_views_local.PasswordChange.as_view(), name="password_change"),
    path("", roster_views.roster, name="roster"),
    path("day/<isodate:d>/", roster_views.day, name="day"),
    path("cell/<isodate:d>/<str:cell>/", roster_views.cell, name="cell"),
    path("me/", roster_views.me, name="me"),
    path("collect/", collect_views.index, name="collect_index"),
    path("collect/<int:pid>/<str:code>/", collect_views.table, name="collect_table"),
    path("collect/<int:pid>/<str:code>/upload/", collect_views.upload, name="collect_upload"),
    path("collect/<int:pid>/<str:code>/export.csv", collect_views.export, name="collect_export"),
    path("periods/", manage_views.period_list, name="periods"),
    path("periods/<int:pid>/", manage_views.period_detail, name="period_detail"),
    path("periods/<int:pid>/action/<str:action>/", manage_views.period_action, name="period_action"),
    path("periods/<int:pid>/delete/", manage_views.period_delete, name="period_delete"),
    path("periods/<int:pid>/move/", manage_views.period_move, name="period_move"),
    path("periods/<int:pid>/publish/", manage_views.period_publish, name="period_publish"),
    path("stats/", manage_views.stats_view, name="stats"),
    path("changes/", manage_views.change_log, name="changes"),
    path("alarms/", alarm_views.index, name="alarms"),
    path("alarms/telegram/", alarm_views.telegram_save, name="alarm_telegram"),
    path("alarms/telegram/link/", alarm_views.telegram_link, name="alarm_telegram_link"),
    path("alarms/telegram/link/check/", alarm_views.telegram_link_check, name="alarm_telegram_check"),
    path("alarms/changes/", alarm_views.notify_changes, name="alarm_notify_changes"),
    path("alarms/rules/new/", alarm_views.rule_new, name="alarm_rule_new"),
    path("alarms/rules/<int:pk>/", alarm_views.rule_edit, name="alarm_rule_edit"),
    path("alarms/rules/<int:pk>/delete/", alarm_views.rule_delete, name="alarm_rule_delete"),
    path("alarms/rules/<int:pk>/toggle/", alarm_views.rule_toggle, name="alarm_rule_toggle"),
    path("alarms/push/subscribe/", alarm_views.push_subscribe, name="alarm_push_subscribe"),
    path("alarms/push/unsubscribe/", alarm_views.push_unsubscribe, name="alarm_push_unsubscribe"),
    path("alarms/push/<int:pk>/delete/", alarm_views.push_delete, name="alarm_push_delete"),
    path("alarms/push/delete-all/", alarm_views.push_delete_all, name="alarm_push_delete_all"),
    path("alarms/push/test/", alarm_views.push_test, name="alarm_push_test"),
    path("help/", help_views.index, name="help"),
    path("help/video/<str:name>.mp4", help_views.video, name="help_video"),
    path("help/dismiss/", help_views.dismiss, name="help_dismiss"),
    path("help/push/", alarm_views.help_push, name="help_push"),
    path("sw.js", alarm_views.sw_js, name="sw_js"),
    path("manifest.webmanifest", alarm_views.manifest, name="manifest"),
    path("help/telegram/", alarm_views.help_telegram, name="help_telegram"),
    path("alarms/calendar/issue/", alarm_views.calendar_issue, name="alarm_calendar_issue"),
    path("alarms/calendar/revoke/", alarm_views.calendar_revoke, name="alarm_calendar_revoke"),
    path("help/calendar/", alarm_views.help_calendar, name="help_calendar"),
    path("calendar/<str:token>.ics", calendar_views.feed, name="calendar_feed"),
]
