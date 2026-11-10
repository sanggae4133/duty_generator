from django.shortcuts import redirect
from django.urls import reverse

from . import perms


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        member = perms.member_of(request.user)
        if member and member.must_change_password and request.path not in {reverse("password_change"), reverse("logout")}:
            return redirect("password_change")
        return self.get_response(request)
