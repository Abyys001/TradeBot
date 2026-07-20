<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useLayoutStore } from '../stores/layout'
import { useAuthStore } from '../stores/auth'
import { useResponsiveDrawer } from '../composables/useResponsiveDrawer'
import { useBreakpoints } from '../composables/useBreakpoints'

const { t } = useI18n()
const route = useRoute()
const layout = useLayoutStore()
const auth = useAuthStore()
const { isMobile } = useBreakpoints()

useResponsiveDrawer({
  isOpen: computed(() => layout.mobileNavOpen),
  setOpen: layout.setMobileNavOpen,
  closeOnRouteChange: true,
})

const allNavItems = [
  { name: 'overview', path: '/', label: 'nav.overview', icon: 'overview' },
  { name: 'investors', path: '/investors', label: 'nav.investors', icon: 'investors', adminOnly: true },
  { name: 'admin-bots', path: '/admin/bots', label: 'nav.botScripts', icon: 'bots', adminOnly: true },
  { name: 'strategies', path: '/strategies', label: 'nav.strategies', icon: 'strategies' },
  { name: 'live', path: '/live', label: 'nav.live', icon: 'live' },
  { name: 'data', path: '/data', label: 'nav.data', icon: 'data' },
  { name: 'analytics', path: '/analytics', label: 'nav.analytics', icon: 'analytics' },
  { name: 'orders', path: '/orders', label: 'nav.orders', icon: 'orders' },
  { name: 'journal', path: '/journal', label: 'nav.journal', icon: 'journal' },
  { name: 'marketplace', path: '/marketplace', label: 'nav.marketplace', icon: 'marketplace' },
  { name: 'settings', path: '/settings', label: 'nav.settings', icon: 'settings' },
  { name: 'telegram-settings', path: '/settings/telegram', label: 'nav.telegram', icon: 'telegram' },
] as const

const navItems = computed(() =>
  allNavItems.filter((item) => !(item as { adminOnly?: boolean }).adminOnly || auth.user?.role === 'admin'),
)

const asideWidthClass = computed(() =>
  layout.navCollapsed ? 'lg:w-16' : 'lg:w-60',
)

const showLabels = computed(() => isMobile.value || !layout.navCollapsed)

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<template>
  <aside
    class="sidebar border-e border-border/60 bg-surface-muted/40 flex flex-col py-3 overflow-hidden fixed inset-y-0 start-0 z-40 w-64 max-w-[80vw] shadow-2xl transition-transform duration-200 lg:relative lg:inset-auto lg:z-auto lg:max-w-none lg:shadow-none lg:translate-x-0 lg:rtl:translate-x-0 lg:transition-[width] lg:shrink-0"
    :class="[asideWidthClass, layout.mobileNavOpen ? 'translate-x-0' : '-translate-x-full rtl:translate-x-full']"
    :style="{ '--nav-width': layout.navWidth }"
  >
    <!-- Logo / collapse toggle -->
    <div class="mx-2 mb-3 flex items-center gap-1">
      <button
        type="button"
        class="hidden flex-1 items-center justify-start rounded-lg px-3 py-2 text-fg-muted transition-colors hover:bg-surface-raised hover:text-fg lg:flex"
        :title="layout.navCollapsed ? t('nav.toggleExpand') : t('nav.toggleCollapse')"
        :aria-label="layout.navCollapsed ? t('nav.toggleExpand') : t('nav.toggleCollapse')"
        @click="layout.toggleNav()"
      >
        <svg class="h-5 w-5 transition-transform duration-200" :class="{ 'rotate-90': layout.navCollapsed }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" d="M9 5l7 7-7 7" />
        </svg>
      </button>
      <button
        type="button"
        class="flex flex-1 items-center justify-between rounded-lg px-3 py-2 text-sm font-medium text-fg lg:hidden"
        :aria-label="t('nav.toggleCollapse')"
        @click="layout.setMobileNavOpen(false)"
      >
        <span>{{ t('app.title') }}</span>
        <svg class="h-5 w-5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
    </div>

    <!-- Nav items -->
    <nav class="flex-1 overflow-y-auto px-2 space-y-0.5">
      <RouterLink
        v-for="item in navItems"
        :key="item.name"
        :to="item.path"
        class="nav-item group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all duration-150"
        :class="
          isActive(item.path)
            ? 'bg-accent/10 text-accent font-medium shadow-sm'
            : 'text-fg-muted hover:bg-surface-raised/60 hover:text-fg'
        "
        :title="!showLabels ? t(item.label) : undefined"
      >
        <!-- Active indicator bar -->
        <span
          v-if="isActive(item.path)"
          class="absolute start-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-accent"
        />

        <span class="relative flex h-5 w-5 shrink-0 items-center justify-center">
          <svg v-if="item.icon === 'overview'" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" />
          </svg>
          <svg v-else-if="item.icon === 'investors'" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="9" cy="8" r="3" />
            <path stroke-linecap="round" d="M3 20c0-3 2.5-5 6-5s6 2 6 5M17 5a3 3 0 010 6M18 20c0-2-.7-3.5-2-4.5" />
          </svg>
          <svg v-else-if="item.icon === 'strategies'" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" d="M4 19V5M4 19h16M8 19V9M12 19V13M16 19V7" />
          </svg>
          <svg v-else-if="item.icon === 'live'" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M3 12h4l2 6 4-14 2 8h6" />
          </svg>
          <svg v-else-if="item.icon === 'bots'" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M13 2L4 14h6l-1 8 9-12h-6l1-8z" />
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
          <svg v-else-if="item.icon === 'telegram'" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" d="M21 3L2 11l7 3 3 7 9-18z" />
            <path stroke-linecap="round" d="M12 14l4-4" />
          </svg>
          <svg v-else class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
          </svg>
        </span>
        <span v-if="showLabels" class="truncate">{{ t(item.label) }}</span>
      </RouterLink>
    </nav>
  </aside>
</template>

<style scoped>
.sidebar {
  --transition-duration: 200ms;
}

.nav-item {
  position: relative;
}

/* Active item glow on hover */
.nav-item.bg-accent\/10:hover {
  background-color: color-mix(in srgb, var(--tb-accent) 15%, transparent);
}
</style>
