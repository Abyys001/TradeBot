<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { setLocale } from '../../i18n'
import { api } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import { useHealthStore } from '../../stores/health'
import KillSwitchModal from './KillSwitchModal.vue'

const { t, locale } = useI18n()
const auth = useAuthStore()
const health = useHealthStore()
const showKill = ref(false)

function statusColor(status: string) {
  if (status === 'connected' || status === 'ok') return 'bg-emerald-500'
  if (status === 'stale') return 'bg-amber-500'
  return 'bg-red-500'
}

function toggleLocale() {
  setLocale(locale.value === 'en' ? 'fa' : 'en')
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
  <header class="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-zinc-800 bg-zinc-900/80 px-2 py-1.5 backdrop-blur sm:gap-x-4 sm:px-4 sm:py-2">
    <h1 class="text-sm font-semibold text-zinc-300 me-auto">{{ t('app.title') }}</h1>

    <div class="flex items-center gap-2 text-xs text-zinc-400" :title="health.health?.hl_market_feed?.status">
      <span class="h-2 w-2 rounded-full" :class="statusColor(health.health?.hl_market_feed?.status ?? 'disconnected')" />
      {{ t('health.hl') }}
    </div>

    <div class="flex items-center gap-2 text-xs text-zinc-400">
      <span class="h-2 w-2 rounded-full" :class="statusColor(health.health?.celery?.status ?? 'error')" />
      {{ t('health.celery') }}
    </div>

    <div
      class="rounded px-2 py-0.5 text-xs font-medium"
      :class="auth.user?.is_trading_enabled ? 'bg-emerald-900/50 text-emerald-400' : 'bg-zinc-800 text-zinc-500'"
    >
      {{ t('health.trading') }}: {{ auth.user?.is_trading_enabled ? t('health.on') : t('health.off') }}
    </div>

    <button
      type="button"
      class="rounded px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-700"
      @click="toggleLocale"
    >
      {{ locale === 'en' ? 'FA' : 'EN' }}
    </button>

    <button
      type="button"
      class="rounded-lg bg-red-600 px-4 py-1.5 text-xs font-bold uppercase tracking-wide text-white hover:bg-red-500 transition-colors"
      @click="showKill = true"
    >
      {{ t('health.killSwitch') }}
    </button>

    <button type="button" class="text-xs text-zinc-500 hover:text-zinc-300" @click="logout">
      {{ t('auth.logout') }}
    </button>

    <KillSwitchModal v-if="showKill" @close="showKill = false" @confirm="onKillConfirm" />
  </header>
</template>
