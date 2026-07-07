import json

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.middleware.csrf import get_token
from django.views.decorators.http import require_GET, require_POST

from .serializers import UserSerializer


@require_GET
@ensure_csrf_cookie
def csrf_token(request):
    return JsonResponse({"csrfToken": get_token(request)})


@csrf_exempt
@require_POST
def login_view(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError) as e:
        return JsonResponse({"detail": f"Invalid JSON: {e}"}, status=400)

    username = data.get("username", "")
    password = data.get("password", "")
    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({"detail": "Invalid credentials"}, status=401)

    login(request, user)
    return JsonResponse(UserSerializer(user).data)


@require_POST
def logout_view(request):
    logout(request)
    return JsonResponse({"detail": "Logged out"})


@require_GET
def me_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Not authenticated"}, status=401)
    return JsonResponse(UserSerializer(request.user).data)


@require_POST
def change_password_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Not authenticated"}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError) as e:
        return JsonResponse({"detail": f"Invalid JSON: {e}"}, status=400)

    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")
    user = request.user

    if not user.check_password(old_password):
        return JsonResponse({"detail": "Current password is incorrect"}, status=400)

    try:
        validate_password(new_password, user=user)
    except ValidationError as e:
        return JsonResponse({"detail": e.messages}, status=400)

    user.set_password(new_password)
    user.must_change_password = False
    user.save(update_fields=["password", "must_change_password"])
    update_session_auth_hash(request, user)
    return JsonResponse(UserSerializer(user).data)
