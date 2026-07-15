<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { setLocale } from '../../i18n'
import { api } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import { useHealthStore } from '../../stores/health'
import { useLayoutStore } from '../../stores/layout'
import KillSwitchModal from './KillSwitchModal.vue'

const { t, locale } = useI18n()
const auth = useAuthStore()
const health = useHealthStore()
const layout = useLayoutStore()
const showKill = ref(false)
const showMenu = ref(false)

function statusColor(status: string) {
  if (status === 'connected' || status === 'ok') return 'bg-emerald-500'
  if (status === 'stale') return 'bg-amber-500'
  return 'bg-red-500'
}

// Aggregate dot for the compact phone view: worst of the two feed statuses.
const worstStatusColor = computed(() => {
  const hl = health.health?.hl_market_feed?.status ?? 'disconnected'
  const celery = health.health?.celery?.status ?? 'error'
  if (statusColor(hl) === 'bg-red-500' || statusColor(celery) === 'bg-red-500') return 'bg-red-500'
  if (statusColor(hl) === 'bg-amber-500' || statusColor(celery) === 'bg-amber-500') return 'bg-amber-500'
  return 'bg-emerald-500'
})

const worstStatusTitle = computed(
  () => `${t('health.hl')}: ${health.health?.hl_market_feed?.status ?? 'disconnected'} · ${t('health.celery')}: ${health.health?.celery?.status ?? 'error'}`,
)

function toggleLocale() {
  setLocale(locale.value === 'en' ? 'fa' : 'en')
  showMenu.value = false
}

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
  <header class="relative flex items-center gap-x-2 border-b border-zinc-800 bg-zinc-900/80 px-2 py-1.5 backdrop-blur sm:gap-x-4 sm:px-4 sm:py-2">
    <button
      type="button"
      class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 lg:hidden"
      :aria-label="t('nav.openMenu')"
      @click="layout.toggleMobileNavOpen()"
    >
      <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" d="M4 6h16M4 12h16M4 18h16" />
      </svg>
    </button>

    <h1 class="truncate text-sm font-semibold text-zinc-300 me-auto max-w-[7rem] sm:max-w-none">{{ t('app.title') }}</h1>

    <div class="hidden items-center gap-2 text-xs text-zinc-400 sm:flex" :title="health.health?.hl_market_feed?.status">
      <span class="h-2 w-2 rounded-full" :class="statusColor(health.health?.hl_market_feed?.status ?? 'disconnected')" />
      {{ t('health.hl') }}
    </div>

    <div class="hidden items-center gap-2 text-xs text-zinc-400 sm:flex">
      <span class="h-2 w-2 rounded-full" :class="statusColor(health.health?.celery?.status ?? 'error')" />
      {{ t('health.celery') }}
    </div>

    <span class="h-2 w-2 shrink-0 rounded-full sm:hidden" :class="worstStatusColor" :title="worstStatusTitle" />

    <div
      class="hidden rounded px-2 py-0.5 text-xs font-medium sm:block"
      :class="auth.user?.is_trading_enabled ? 'bg-emerald-900/50 text-emerald-400' : 'bg-zinc-800 text-zinc-500'"
    >
      {{ t('health.trading') }}: {{ auth.user?.is_trading_enabled ? t('health.on') : t('health.off') }}
    </div>

    <button
      type="button"
      class="hidden rounded px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-700 sm:block"
      @click="toggleLocale"
    >
      {{ locale === 'en' ? 'FA' : 'EN' }}
    </button>

    <button
      type="button"
      class="shrink-0 rounded-lg bg-red-600 px-2 py-1.5 text-xs font-bold uppercase tracking-wide text-white hover:bg-red-500 transition-colors sm:px-4"
      @click="showKill = true"
    >
      {{ t('health.killSwitch') }}
    </button>

    <button type="button" class="hidden text-xs text-zinc-500 hover:text-zinc-300 sm:block" @click="logout">
      {{ t('auth.logout') }}
    </button>

    <div class="relative sm:hidden">
      <button
        type="button"
        class="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
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
        class="absolute end-0 top-full z-20 mt-1 w-40 overflow-hidden rounded-lg border border-zinc-700 bg-zinc-900 shadow-xl"
      >
        <div
          class="flex items-center justify-between px-3 py-1.5 text-xs"
          :class="auth.user?.is_trading_enabled ? 'text-emerald-400' : 'text-zinc-500'"
        >
          <span>{{ t('health.trading') }}</span>
          <span>{{ auth.user?.is_trading_enabled ? t('health.on') : t('health.off') }}</span>
        </div>
        <button
          type="button"
          class="block w-full px-3 py-2 text-start text-xs text-zinc-300 hover:bg-zinc-800"
          @click="toggleLocale"
        >
          {{ locale === 'en' ? 'فارسی' : 'English' }}
        </button>
        <button
          type="button"
          class="block w-full px-3 py-2 text-start text-xs text-zinc-300 hover:bg-zinc-800"
          @click="() => { showMenu = false; logout() }"
        >
          {{ t('auth.logout') }}
        </button>
      </div>
    </div>

    <KillSwitchModal v-if="showKill" @close="showKill = false" @confirm="onKillConfirm" />
  </header>
</template>
