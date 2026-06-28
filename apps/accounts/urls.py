from django.urls import path

from . import views

urlpatterns = [
    path("auth/csrf/", views.csrf_token, name="csrf"),
    path("auth/login/", views.login_view, name="login"),
    path("auth/logout/", views.logout_view, name="logout"),
    path("me/", views.me_view, name="me"),
]
