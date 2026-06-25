from django.urls import path

from .views import OptimizeGridView, OptimizeMonteCarloView, OptimizePortfolioView, OptimizeWalkForwardView

urlpatterns = [
    path("optimize/grid/", OptimizeGridView.as_view(), name="optimize-grid"),
    path("optimize/walk-forward/", OptimizeWalkForwardView.as_view(), name="optimize-walk-forward"),
    path("optimize/monte-carlo/", OptimizeMonteCarloView.as_view(), name="optimize-monte-carlo"),
    path("optimize/portfolio/", OptimizePortfolioView.as_view(), name="optimize-portfolio"),
]
