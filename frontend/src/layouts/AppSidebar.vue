<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useLayoutStore } from '../stores/layout'
import { useAuthStore } from '../stores/auth'

const { t } = useI18n()
const route = useRoute()
const layout = useLayoutStore()
const auth = useAuthStore()

// `role` gates an item: undefined = everyone, 'admin'/'investor' = that role only.
// Ordered by workflow: connect → build → trade → review → account.
const allNavItems = [
  { name: 'overview', path: '/', label: 'nav.overview', icon: 'overview' },
  { name: 'api-setup', path: '/api-setup', label: 'nav.apiSetup', icon: 'settings' },
  { name: 'strategies', path: '/strategies', label: 'nav.strategies', icon: 'strategies', role: 'admin' },
  { name: 'admin', path: '/admin', label: 'nav.admin', icon: 'overview', role: 'admin' },
  { name: 'invest-marketplace', path: '/invest', label: 'nav.invest', icon: 'marketplace', role: 'investor' },
  { name: 'invest-portfolio', path: '/invest/portfolio', label: 'nav.portfolio', icon: 'analytics', role: 'investor' },
  { name: 'live', path: '/live', label: 'nav.live', icon: 'live', role: 'admin' },
  { name: 'data', path: '/data', label: 'nav.data', icon: 'data', role: 'admin' },
  { name: 'analytics', path: '/analytics', label: 'nav.analytics', icon: 'analytics' },
  { name: 'orders', path: '/orders', label: 'nav.orders', icon: 'orders' },
  { name: 'journal', path: '/journal', label: 'nav.journal', icon: 'journal' },
  { name: 'marketplace', path: '/marketplace', label: 'nav.marketplace', icon: 'marketplace', role: 'admin' },
  { name: 'settings', path: '/settings', label: 'nav.settings', icon: 'settings' },
] as const

const navItems = computed(() =>
  allNavItems.filter((item) => {
    const role = (item as { role?: string }).role
    if (!role) return true
    if (role === 'admin') return auth.isAdmin
    if (role === 'investor') return auth.isInvestor
    return true
  }),
)

const asideClass = computed(() =>
  layout.navCollapsed
    ? 'w-16'
    : 'w-60',
)

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<template>
  <aside
    class="shrink-0 border-e border-zinc-800 bg-zinc-900/50 flex flex-col py-3 transition-[width] duration-200 overflow-hidden"
    :class="asideClass"
    :style="{ '--nav-width': layout.navWidth }"
  >
    <button
      type="button"
      class="mx-2 mb-3 flex items-center justify-center rounded-lg p-2 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
      :title="layout.navCollapsed ? t('nav.toggleExpand') : t('nav.toggleCollapse')"
      :aria-label="layout.navCollapsed ? t('nav.toggleExpand') : t('nav.toggleCollapse')"
      @click="layout.toggleNav()"
    >
      <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path v-if="layout.navCollapsed" stroke-linecap="round" d="M4 6h16M4 12h16M4 18h16" />
        <template v-else>
          <path stroke-linecap="round" d="M4 6h16M4 12h10M4 18h16" />
        </template>
      </svg>
    </button>

    <RouterLink
      v-for="item in navItems"
      :key="item.name"
      :to="item.path"
      class="mx-2 mb-1 flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors"
      :class="
        isActive(item.path)
          ? 'bg-zinc-800 text-zinc-100 font-medium'
          : 'text-zinc-500 hover:bg-zinc-800/50 hover:text-zinc-300'
      "
      :title="layout.navCollapsed ? t(item.label) : undefined"
    >
      <span class="flex h-5 w-5 shrink-0 items-center justify-center">
        <svg v-if="item.icon === 'overview'" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" />
          <rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" />
        </svg>
        <svg v-else-if="item.icon === 'strategies'" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" d="M4 19V5M4 19h16M8 19V9M12 19V13M16 19V7" />
        </svg>
        <svg v-else-if="item.icon === 'live'" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M3 12h4l2 6 4-14 2 8h6" />
        </svg>
        <svg v-else-if="item.icon === 'data'" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
          <path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3" />
        </svg>
        <svg v-else-if="item.icon === 'analytics'" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" d="M3 3v18h18M7 16l4-8 4 4 5-9" />
        </svg>
        <svg v-else-if="item.icon === 'orders'" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" />
          <rect x="9" y="3" width="6" height="4" rx="1" />
        </svg>
        <svg v-else-if="item.icon === 'journal'" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" d="M12 20h9M16.5 3.5a2.12 2.12 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
        </svg>
        <svg v-else-if="item.icon === 'marketplace'" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
          <polyline points="9 22 9 12 15 12 15 22" />
        </svg>
        <svg v-else class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="3" />
          <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
        </svg>
      </span>
      <span v-if="!layout.navCollapsed" class="truncate">{{ t(item.label) }}</span>
    </RouterLink>
  </aside>
</template>
