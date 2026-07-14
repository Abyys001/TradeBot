import json

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.middleware.csrf import get_token
from django.views.decorators.http import require_GET, require_POST
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import User
from .permissions import IsAdminRole
from .serializers import InvestorCreateSerializer, InvestorSerializer, UserSerializer


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


class InvestorViewSet(viewsets.ModelViewSet):
    """Admin-only management of investor accounts.

    Create an investor (username + temp password, forced first-login change),
    list them, reset a password, or toggle their trading kill-switch / active
    state. Hard deletes are disabled — deactivate instead of destroy.
    """

    permission_classes = [IsAdminRole]
    queryset = User.objects.filter(role=User.Role.INVESTOR).order_by("-created_at")
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return InvestorCreateSerializer
        return InvestorSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(InvestorSerializer(user).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        user = self.get_object()
        password = request.data.get("password", "")
        try:
            validate_password(password, user=user)
        except ValidationError as e:
            return Response({"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(password)
        user.must_change_password = True
        user.save(update_fields=["password", "must_change_password"])
        return Response(InvestorSerializer(user).data)

    @action(detail=True, methods=["post"], url_path="set-trading")
    def set_trading(self, request, pk=None):
        user = self.get_object()
        user.is_trading_enabled = bool(request.data.get("enabled", False))
        user.save(update_fields=["is_trading_enabled"])
        return Response(InvestorSerializer(user).data)

    @action(detail=True, methods=["post"], url_path="set-active")
    def set_active(self, request, pk=None):
        user = self.get_object()
        user.is_active = bool(request.data.get("active", True))
        user.save(update_fields=["is_active"])
        return Response(InvestorSerializer(user).data)
