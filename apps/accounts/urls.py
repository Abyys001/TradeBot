from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("admin/investors", views.InvestorViewSet, basename="investor")

urlpatterns = [
    path("auth/csrf/", views.csrf_token, name="csrf"),
    path("auth/login/", views.login_view, name="login"),
    path("auth/logout/", views.logout_view, name="logout"),
    path("auth/change-password/", views.change_password_view, name="change-password"),
    path("me/", views.me_view, name="me"),
] + router.urls
