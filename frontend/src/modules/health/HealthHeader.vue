<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import { useHealthStore } from '../../stores/health'
import { useLayoutStore } from '../../stores/layout'
import KillSwitchModal from './KillSwitchModal.vue'
import ThemeToggle from '../../components/ThemeToggle.vue'
import LanguageToggle from '../../components/LanguageToggle.vue'

const { t } = useI18n()
const auth = useAuthStore()
const health = useHealthStore()
const layout = useLayoutStore()
const showKill = ref(false)
const showMenu = ref(false)

function statusColor(status: string) {
  if (status === 'connected' || status === 'ok') return 'bg-positive'
  if (status === 'stale') return 'bg-warning'
  return 'bg-negative'
}

// Aggregate dot for the compact phone view: worst of the two feed statuses.
const worstStatusColor = computed(() => {
  const hl = health.health?.hl_market_feed?.status ?? 'disconnected'
  const celery = health.health?.celery?.status ?? 'error'
  if (statusColor(hl) === 'bg-negative' || statusColor(celery) === 'bg-negative') return 'bg-negative'
  if (statusColor(hl) === 'bg-warning' || statusColor(celery) === 'bg-warning') return 'bg-warning'
  return 'bg-positive'
})

const worstStatusTitle = computed(
  () => `${t('health.hl')}: ${health.health?.hl_market_feed?.status ?? 'disconnected'} · ${t('health.celery')}: ${health.health?.celery?.status ?? 'error'}`,
)

async function logout() {
  await auth.logout()
  window.location.href = '/login'
}

async function onKillConfirm() {
  await api.post('/me/kill-switch/', { enabled: false, close_positions: true })
  showKill.value = false
  await health.fetchHealth()
  auth.setTradingEnabled(false)
}
</script>

<template>
  <header class="relative flex items-center gap-x-2 border-b border-border bg-surface-muted/80 px-2 py-1.5 backdrop-blur sm:gap-x-4 sm:px-4 sm:py-2">
    <button
      type="button"
      class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-fg-muted hover:bg-surface-raised hover:text-fg lg:hidden"
      :aria-label="t('nav.openMenu')"
      @click="layout.toggleMobileNavOpen()"
    >
      <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" d="M4 6h16M4 12h16M4 18h16" />
      </svg>
    </button>

    <h1 class="truncate text-sm font-semibold text-fg me-auto max-w-[7rem] sm:max-w-none">{{ t('app.title') }}</h1>

    <div class="hidden items-center gap-2 text-xs text-fg-muted sm:flex" :title="health.health?.hl_market_feed?.status">
      <span class="h-2 w-2 rounded-full" :class="statusColor(health.health?.hl_market_feed?.status ?? 'disconnected')" />
      {{ t('health.hl') }}
    </div>

    <div class="hidden items-center gap-2 text-xs text-fg-muted sm:flex">
      <span class="h-2 w-2 rounded-full" :class="statusColor(health.health?.celery?.status ?? 'error')" />
      {{ t('health.celery') }}
    </div>

    <span class="h-2 w-2 shrink-0 rounded-full sm:hidden" :class="worstStatusColor" :title="worstStatusTitle" />

    <div
      class="hidden rounded px-2 py-0.5 text-xs font-medium sm:block"
      :class="auth.user?.is_trading_enabled ? 'bg-success-bg text-positive' : 'bg-surface-raised text-fg-muted'"
    >
      {{ t('health.trading') }}: {{ auth.user?.is_trading_enabled ? t('health.on') : t('health.off') }}
    </div>

    <ThemeToggle />
    <LanguageToggle />

    <button
      type="button"
      class="shrink-0 rounded-lg bg-red-600 px-2 py-1.5 text-xs font-bold uppercase tracking-wide text-white hover:bg-red-500 transition-colors sm:px-4"
      @click="showKill = true"
    >
      {{ t('health.killSwitch') }}
    </button>

    <button type="button" class="hidden text-xs text-fg-muted hover:text-fg sm:block" @click="logout">
      {{ t('auth.logout') }}
    </button>

    <div class="relative sm:hidden">
      <button
        type="button"
        class="flex h-8 w-8 items-center justify-center rounded-lg text-fg-muted hover:bg-surface-raised hover:text-fg"
        :aria-label="t('nav.moreActions')"
        @click="showMenu = !showMenu"
      >
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
          <circle cx="12" cy="5" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="12" cy="19" r="1.5" />
        </svg>
      </button>
      <div v-if="showMenu" class="fixed inset-0 z-10" @click="showMenu = false" />
      <div
        v-if="showMenu"
        class="absolute end-0 top-full z-20 mt-1 w-40 overflow-hidden rounded-lg border border-border bg-surface-raised shadow-xl"
      >
        <div
          class="flex items-center justify-between px-3 py-1.5 text-xs"
          :class="auth.user?.is_trading_enabled ? 'text-positive' : 'text-fg-muted'"
        >
          <span>{{ t('health.trading') }}</span>
          <span>{{ auth.user?.is_trading_enabled ? t('health.on') : t('health.off') }}</span>
        </div>
        <ThemeToggle variant="menu-item" />
        <LanguageToggle variant="menu-item" @change="showMenu = false" />
        <button
          type="button"
          class="block w-full px-3 py-2 text-start text-xs text-fg hover:bg-surface-muted"
          @click="() => { showMenu = false; logout() }"
        >
          {{ t('auth.logout') }}
        </button>
      </div>
    </div>

    <KillSwitchModal v-if="showKill" @close="showKill = false" @confirm="onKillConfirm" />
  </header>
</template>
