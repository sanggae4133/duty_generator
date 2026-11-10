from . import perms


def nav(request):
    user = request.user
    return {"can_collect": user.is_authenticated and perms.managed_departments(user).exists()}
