<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { RouterView } from 'vue-router'
import { useIntervalFn } from '@vueuse/core'
import AppSidebar from './AppSidebar.vue'
import HealthHeader from '../modules/health/HealthHeader.vue'
import { useDashboardWebSocket } from '../composables/useDashboardWebSocket'
import { useHealthStore } from '../stores/health'
import { useStrategyStore } from '../stores/strategy'
import { useTerminalStore } from '../stores/terminal'
import { useToast } from '../composables/useToast'
import { useLayoutStore } from '../stores/layout'

const health = useHealthStore()
const strategy = useStrategyStore()
const terminal = useTerminalStore()
const ws = useDashboardWebSocket()
const { toasts, dismiss } = useToast()
const layout = useLayoutStore()

const { pause, resume } = useIntervalFn(() => health.fetchHealth(), 10000)

onMounted(async () => {
  await Promise.all([health.fetchHealth(), strategy.fetchAll(), terminal.fetchLogs()])
  ws.connect()
  resume()
})

onUnmounted(pause)
</script>

<template>
  <div class="flex h-dvh flex-col overflow-hidden bg-surface">
    <HealthHeader />
    <div class="flex flex-1 min-h-0">
      <AppSidebar />
      <main class="flex flex-1 flex-col min-w-0 min-h-0 overflow-hidden">
        <RouterView v-slot="{ Component }">
          <Transition
            mode="out-in"
            enter-active-class="transition-all duration-200 ease-out"
            enter-from-class="opacity-0 -translate-y-1"
            enter-to-class="opacity-100 translate-y-0"
            leave-active-class="transition-all duration-150 ease-in"
            leave-from-class="opacity-100 translate-y-0"
            leave-to-class="opacity-0 translate-y-1"
          >
            <component :is="Component" class="h-full min-h-0 flex flex-col" />
          </Transition>
        </RouterView>
      </main>
    </div>

    <!-- Mobile overlay -->
    <Transition
      enter-active-class="transition-opacity duration-200"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition-opacity duration-150"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="layout.mobileNavOpen"
        class="fixed inset-0 z-30 bg-black/50 backdrop-blur-sm lg:hidden"
        @click="layout.setMobileNavOpen(false)"
      />
    </Transition>

    <!-- Toast container -->
    <div class="pointer-events-none fixed top-4 end-4 z-50 flex max-w-sm flex-col gap-2">
      <TransitionGroup
        enter-active-class="transition-all duration-200 ease-out"
        enter-from-class="translate-x-4 opacity-0"
        enter-to-class="translate-x-0 opacity-100"
        leave-active-class="transition-all duration-200 ease-in"
        leave-from-class="translate-x-0 opacity-100"
        leave-to-class="translate-x-4 opacity-0"
      >
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="pointer-events-auto cursor-pointer rounded-xl border px-4 py-3 text-sm shadow-lg backdrop-blur-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-xl"
          :class="{
            'border-positive/40 bg-success-bg text-positive': toast.type === 'success',
            'border-negative/40 bg-danger-bg text-negative': toast.type === 'error',
            'border-border bg-surface-raised/90 text-fg': toast.type === 'info',
          }"
          @click="dismiss(toast.id)"
        >
          {{ toast.message }}
        </div>
      </TransitionGroup>
    </div>
  </div>
</template>
