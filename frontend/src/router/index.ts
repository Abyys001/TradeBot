import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
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
          path: 'settings',
          name: 'settings',
          component: () => import('../views/SettingsView.vue'),
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
      if (to.meta.requiresAuth) return { name: 'login' }
    }
  }
  if (to.meta.guest && auth.user) return { name: 'overview' }
  return true
})

export default router
