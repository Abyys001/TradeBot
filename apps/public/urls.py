from django.urls import path

from . import views

urlpatterns = [
    path("public/performance/", views.PublicPerformanceView.as_view(), name="public-performance"),
    path("public/leads/", views.LeadCreateView.as_view(), name="public-lead-create"),
]
