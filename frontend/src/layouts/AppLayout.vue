<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { RouterView } from 'vue-router'
import { useIntervalFn } from '@vueuse/core'
<<<<<<< HEAD
import AppSidebar from '../components/AppSidebar.vue'
=======
import AppSidebar from './AppSidebar.vue'
>>>>>>> 1af07065fe5a87dc8ca34e162c3bf176e3907b0c
import HealthHeader from '../modules/health/HealthHeader.vue'
import { useDashboardWebSocket } from '../composables/useDashboardWebSocket'
import { useHealthStore } from '../stores/health'
import { useStrategyStore } from '../stores/strategy'
import { useTerminalStore } from '../stores/terminal'
import { useToast } from '../composables/useToast'

const health = useHealthStore()
const strategy = useStrategyStore()
const terminal = useTerminalStore()
const ws = useDashboardWebSocket()
const { toasts, dismiss } = useToast()

<<<<<<< HEAD
=======
const { pause, resume } = useIntervalFn(() => health.fetchHealth(), 10000)

>>>>>>> 1af07065fe5a87dc8ca34e162c3bf176e3907b0c
onMounted(async () => {
  await Promise.all([health.fetchHealth(), strategy.fetchAll(), terminal.fetchLogs()])
  ws.connect()
  resume()
})

onUnmounted(pause)
</script>

<template>
  <div class="flex h-screen flex-col overflow-hidden bg-zinc-950">
    <HealthHeader />
    <div class="flex flex-1 min-h-0">
      <AppSidebar />
<<<<<<< HEAD
      <main class="flex flex-1 flex-col min-w-0 overflow-hidden">
        <RouterView />
      </main>
    </div>

    <div class="fixed top-4 end-4 z-50 flex flex-col gap-2 max-w-sm">
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
=======
      <main class="flex flex-1 flex-col min-w-0 min-h-0 overflow-hidden">
        <RouterView v-slot="{ Component }">
          <component :is="Component" class="h-full min-h-0 flex flex-col" />
        </RouterView>
      </main>
    </div>

    <div class="pointer-events-none fixed top-4 end-4 z-50 flex max-w-sm flex-col gap-2">
      <TransitionGroup
        enter-active-class="transition-all duration-200 ease-out"
        enter-from-class="translate-x-4 opacity-0"
        enter-to-class="translate-x-0 opacity-100"
        leave-active-class="transition-all duration-200 ease-in"
        leave-from-class="translate-x-0 opacity-100"
        leave-to-class="translate-x-4 opacity-0"
>>>>>>> 1af07065fe5a87dc8ca34e162c3bf176e3907b0c
      >
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="pointer-events-auto cursor-pointer rounded-lg border px-4 py-2 text-sm shadow-lg"
          :class="{
            'border-emerald-800 bg-emerald-950 text-emerald-300': toast.type === 'success',
            'border-red-800 bg-red-950 text-red-300': toast.type === 'error',
            'border-zinc-700 bg-zinc-900 text-zinc-300': toast.type === 'info',
          }"
          @click="dismiss(toast.id)"
        >
          {{ toast.message }}
        </div>
      </TransitionGroup>
    </div>
  </div>
</template>
