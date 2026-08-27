from django.urls import path

from apps.security import views

urlpatterns = [
    path("policy/", views.policy_view, name="security-policy"),
    path("events/", views.events_view, name="security-events"),
    path("step-up/", views.step_up_view, name="security-step-up"),
    path("totp/", views.totp_view, name="security-totp"),
    path("totp/begin/", views.totp_begin, name="security-totp-begin"),
    path("totp/confirm/", views.totp_confirm, name="security-totp-confirm"),
    path("totp/acknowledge/", views.totp_acknowledge, name="security-totp-acknowledge"),
    path("totp/disable/", views.totp_disable, name="security-totp-disable"),
    path("trusted/forget/", views.trusted_forget, name="security-trusted-forget"),
    # Unauthenticated on purpose: it reports the Content-Security-Policy the
    # panel is already sending in a response header, so it says nothing a
    # browser could not read anyway. The Nuxt server reads it to decide which
    # header to attach to the HTML it renders.
    path("csp/", views.csp_view, name="security-csp"),
]
