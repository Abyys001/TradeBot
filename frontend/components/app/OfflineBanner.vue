<script setup lang="ts">
/**
 * One line, across the top, when the panel cannot reach the server.
 *
 * The alternative — and what this replaces — was every poller printing its own
 * `[GET] "/api/…": <no response> Failed to fetch` into whatever card it lived
 * in. Four endpoints polling gave four unreadable errors a second and none of
 * them said the one thing the reader could act on.
 *
 * It clears itself. Every poller on the page is still retrying, and the first
 * request that comes back resets `stores/connection.ts`, so nothing has to be
 * pressed and nothing has to be reloaded.
 *
 * Deliberately **not** a modal and not dismissible: while this is up, nothing
 * on the page is current, and a dismissed warning over a stale price is exactly
 * the situation the rest of this platform is built to avoid.
 */
const { t } = useI18n()
const connection = useConnectionStore()

/** How long it has been down, ticking. A frozen "2m ago" reads as a stuck page. */
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  connection.bind()
  timer = setInterval(() => (now.value = Date.now()), 1000)
})
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})

const downFor = computed(() => {
  if (!connection.lostAt) return ''
  return formatDuration(Math.max(0, Math.round((now.value - connection.lostAt) / 1000)))
})
</script>

<template>
  <Transition
    enter-active-class="transition-all duration-200"
    enter-from-class="opacity-0 -translate-y-2"
    leave-active-class="transition-all duration-200"
    leave-to-class="opacity-0 -translate-y-2"
  >
    <div
      v-if="connection.down"
      class="sticky top-0 z-40 px-3 py-2 bg-short-dim border-b border-short/60 text-short
             flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-xs"
      role="status"
      aria-live="polite"
    >
      <span class="w-3.5 h-3.5 rounded-full border-2 border-short/40 border-t-short animate-spin" />
      <strong>{{ t('connection.offlineTitle') }}</strong>
      <span class="text-short/90">{{ t('connection.offlineDetail') }}</span>
      <span v-if="downFor" class="num text-short/70">{{ t('connection.offlineFor', { for: downFor }) }}</span>
    </div>
  </Transition>
</template>
