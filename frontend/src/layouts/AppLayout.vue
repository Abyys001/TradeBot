<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useIntervalFn } from '@vueuse/core'
import HealthHeader from '../modules/health/HealthHeader.vue'
import { useDashboardWebSocket } from '../composables/useDashboardWebSocket'
import { useHealthStore } from '../stores/health'
import { useStrategyStore } from '../stores/strategy'
import { useTerminalStore } from '../stores/terminal'
import { useToast } from '../composables/useToast'

const { t } = useI18n()
const route = useRoute()
const health = useHealthStore()
const strategy = useStrategyStore()
const terminal = useTerminalStore()
const ws = useDashboardWebSocket()
const { toasts, dismiss } = useToast()

const navItems = [
  { name: 'overview', path: '/', label: 'nav.overview' },
  { name: 'strategies', path: '/strategies', label: 'nav.strategies' },
  { name: 'data', path: '/data', label: 'nav.data' },
  { name: 'analytics', path: '/analytics', label: 'nav.analytics' },
  { name: 'orders', path: '/orders', label: 'nav.orders' },
  { name: 'journal', path: '/journal', label: 'nav.journal' },
  { name: 'marketplace', path: '/marketplace', label: 'nav.marketplace' },
  { name: 'settings', path: '/settings', label: 'nav.settings' },
]

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}

onMounted(async () => {
  await Promise.all([health.fetchHealth(), strategy.fetchAll(), terminal.fetchLogs()])
  ws.connect()
})

const { pause, resume } = useIntervalFn(() => health.fetchHealth(), 10000)
onMounted(resume)
onUnmounted(pause)
</script>

<template>
  <div class="flex h-screen flex-col overflow-hidden bg-zinc-950">
    <HealthHeader />
    <div class="flex flex-1 min-h-0">
      <aside class="w-48 shrink-0 border-e border-zinc-800 bg-zinc-900/50 flex flex-col py-3">
        <RouterLink
          v-for="item in navItems"
          :key="item.name"
          :to="item.path"
          class="mx-2 mb-1 rounded-lg px-3 py-2 text-sm transition-colors"
          :class="
            isActive(item.path)
              ? 'bg-zinc-800 text-zinc-100 font-medium'
              : 'text-zinc-500 hover:bg-zinc-800/50 hover:text-zinc-300'
          "
        >
          {{ t(item.label) }}
        </RouterLink>
      </aside>
      <main class="flex flex-1 flex-col min-w-0 min-h-0 overflow-y-auto">
        <RouterView />
      </main>
    </div>

    <div class="fixed bottom-4 end-4 z-50 flex flex-col gap-2 max-w-sm">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="rounded-lg border px-4 py-2 text-sm shadow-lg cursor-pointer"
        :class="{
          'border-emerald-800 bg-emerald-950 text-emerald-300': toast.type === 'success',
          'border-red-800 bg-red-950 text-red-300': toast.type === 'error',
          'border-zinc-700 bg-zinc-900 text-zinc-300': toast.type === 'info',
        }"
        @click="dismiss(toast.id)"
      >
        {{ toast.message }}
      </div>
    </div>
  </div>
</template>
