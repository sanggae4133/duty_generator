from django.apps import AppConfig


class DutyConfig(AppConfig):
    name = "duty"
    verbose_name = "NXT 당번표"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from .accounts import on_login
        user_logged_in.connect(on_login, dispatch_uid="duty.help_popup")
