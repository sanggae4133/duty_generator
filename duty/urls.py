from datetime import date

from django.contrib.auth import views as auth_views
from django.urls import path, register_converter

from . import api
from .views import auth as auth_views_local


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
    path("api/assignments", api.assignments, name="api_assignments"),
]
