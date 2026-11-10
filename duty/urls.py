from datetime import date

from django.contrib.auth import views as auth_views
from django.urls import path, register_converter

from . import api
from .views import auth as auth_views_local
from .views import collect as collect_views
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
    path("swap/<isodate:d>/", roster_views.swap, name="swap"),
    path("me/", roster_views.me, name="me"),
    path("collect/", collect_views.index, name="collect_index"),
    path("collect/<int:pid>/<str:code>/", collect_views.table, name="collect_table"),
    path("collect/<int:pid>/<str:code>/upload/", collect_views.upload, name="collect_upload"),
    path("collect/<int:pid>/<str:code>/export.csv", collect_views.export, name="collect_export"),
    path("periods/", manage_views.period_list, name="periods"),
    path("periods/<int:pid>/", manage_views.period_detail, name="period_detail"),
    path("periods/<int:pid>/action/<str:action>/", manage_views.period_action, name="period_action"),
    path("periods/<int:pid>/publish/", manage_views.period_publish, name="period_publish"),
    path("stats/", manage_views.stats_view, name="stats"),
    path("changes/", manage_views.change_log, name="changes"),
    path("schema/", manage_views.schema, name="schema"),
    path("api/assignments", api.assignments, name="api_assignments"),
]
