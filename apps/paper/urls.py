from django.urls import path

from .views import PaperAccountView, PaperPositionsView, PaperTradesView

urlpatterns = [
    path("paper/<int:strategy_id>/", PaperAccountView.as_view(), name="paper-account"),
    path("paper/<int:strategy_id>/trades/", PaperTradesView.as_view(), name="paper-trades"),
    path("paper/<int:strategy_id>/positions/", PaperPositionsView.as_view(), name="paper-positions"),
]
