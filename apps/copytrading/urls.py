from django.urls import path

from . import views

urlpatterns = [
    # Investor
    path("copytrading/my/summary/", views.MyCopySummaryView.as_view(), name="copy-my-summary"),
    path("copytrading/my/trades/", views.MyCopyTradesView.as_view(), name="copy-my-trades"),
    path("copytrading/my/equity/", views.MyCopyEquityView.as_view(), name="copy-my-equity"),
    # Admin
    path("copytrading/fee-config/", views.FeeConfigView.as_view(), name="copy-fee-config"),
    path("copytrading/admin/overview/", views.AdminCopyOverviewView.as_view(), name="copy-admin-overview"),
    path("copytrading/admin/ledger/", views.AdminFeeLedgerView.as_view(), name="copy-admin-ledger"),
]
