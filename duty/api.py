import hmac
from datetime import date

from django.conf import settings
from django.http import JsonResponse

from .services.roster import api_assignments


def assignments(request):
    token = settings.API_TOKEN
    given = request.headers.get("Authorization", "")
    if not token or not hmac.compare_digest(given.encode(), f"Bearer {token}".encode()):
        return JsonResponse({"error": "unauthorized"}, status=401)
    try:
        start = date.fromisoformat(request.GET["from"]) if request.GET.get("from") else None
        end = date.fromisoformat(request.GET["to"]) if request.GET.get("to") else None
    except ValueError:
        return JsonResponse({"error": "from/to 는 YYYY-MM-DD 형식이어야 합니다."}, status=400)
    return JsonResponse(api_assignments(start, end), safe=False, json_dumps_params={"ensure_ascii": False})
