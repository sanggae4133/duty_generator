from datetime import date

from django.contrib.auth import views as auth_views
from django.urls import path, register_converter

from . import api
from .views import auth as auth_views_local
from .views import collect as collect_views
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
    path("dept/<str:key>/", roster_views.dept, name="dept"),
    path("me/", roster_views.me, name="me"),
    path("collect/", collect_views.index, name="collect_index"),
    path("collect/<int:pid>/<str:code>/", collect_views.table, name="collect_table"),
    path("collect/<int:pid>/<str:code>/upload/", collect_views.upload, name="collect_upload"),
    path("collect/<int:pid>/<str:code>/export.csv", collect_views.export, name="collect_export"),
    path("api/assignments", api.assignments, name="api_assignments"),
]
