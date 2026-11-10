from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path(f"{settings.ADMIN_PATH}/", admin.site.urls),
    path("", include("duty.urls")),
]
