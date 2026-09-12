from django.urls import path

from apps.telegram import views

urlpatterns = [
    path("", views.settings_view, name="telegram-settings"),
    path("token/", views.token_view, name="telegram-token"),
    path("link/", views.link_view, name="telegram-link"),
    path("unlink/", views.unlink_view, name="telegram-unlink"),
    path("test/", views.test_view, name="telegram-test"),
]
