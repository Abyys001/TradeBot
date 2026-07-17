import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/welcome',
      name: 'landing',
      component: () => import('../views/LandingView.vue'),
      meta: { guest: true },
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { guest: true },
    },
    {
      path: '/',
      component: () => import('../layouts/AppLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          name: 'overview',
          component: () => import('../views/OverviewView.vue'),
        },
        {
          path: 'strategies',
          name: 'strategies',
          component: () => import('../views/StrategiesListView.vue'),
        },
        {
          path: 'strategies/:id',
          name: 'strategy-detail',
          component: () => import('../views/StrategyDetailView.vue'),
        },
        {
          path: 'live',
          name: 'live',
          component: () => import('../views/LiveTradingView.vue'),
        },
        {
          path: 'api-setup',
          name: 'api-setup',
          component: () => import('../views/ApiSetupView.vue'),
        },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('../views/SettingsView.vue'),
        },
        {
          path: 'data',
          name: 'data',
          component: () => import('../views/DataView.vue'),
        },
        {
          path: 'analytics',
          name: 'analytics',
          component: () => import('../views/AnalyticsView.vue'),
        },
        {
          path: 'orders',
          name: 'orders',
          component: () => import('../views/OrdersView.vue'),
        },
        {
          path: 'journal',
          name: 'journal',
          component: () => import('../views/JournalView.vue'),
        },
        {
          path: 'marketplace',
          name: 'marketplace',
          component: () => import('../views/MarketplaceView.vue'),
        },
        // Admin-only
        {
          path: 'admin',
          name: 'admin',
          component: () => import('../modules/admin/AdminDashboardView.vue'),
          meta: { role: 'admin' },
        },
        // Investor-only
        {
          path: 'invest',
          name: 'invest-marketplace',
          component: () => import('../modules/investor/InvestorMarketplaceView.vue'),
          meta: { role: 'investor' },
        },
        {
          path: 'invest/portfolio',
          name: 'invest-portfolio',
          component: () => import('../modules/investor/InvestorPortfolioView.vue'),
          meta: { role: 'investor' },
        },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.user && !to.meta.guest) {
    try {
      await auth.fetchMe()
    } catch {
      // Unauthenticated → send visitors to the marketing landing page.
      if (to.meta.requiresAuth) return { name: 'landing' }
    }
  }
  if (to.meta.guest && auth.user) return { name: 'overview' }
  // Role gating: block routes tagged with a role the user does not hold.
  const requiredRole = to.meta.role as string | undefined
  if (requiredRole && auth.user) {
    if (requiredRole === 'admin' && !auth.isAdmin) return { name: 'overview' }
    if (requiredRole === 'investor' && !auth.isInvestor) return { name: 'overview' }
  }
  return true
})

export default router
