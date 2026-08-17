<script setup lang="ts">
/**
 * The signed-in shell: rail on desktop, tab bar plus drawer on a phone.
 *
 * It also owns the app-wide side effects, because they belong to the session
 * rather than to any one page:
 *
 *  - one WebSocket, opened here and shared by every page (stores/live.ts)
 *  - the accounts list, loaded once
 *  - spec §4 notices, reconciled from REST so a reload cannot silently clear
 *    an outstanding failure
 *
 * Every page used to do its own version of these, which meant four sockets and
 * four disagreeing copies of the same data.
 *
 * The system log is deliberately *not* preloaded here: `/logs` loads its own
 * page on mount, so an eager fetch on every navigation was pure waste — worse,
 * before the API gained a response cap it meant every page load shipped the
 * *entire* log table over the wire. Live entries still arrive on this page's
 * socket via `stores/live.ts`'s `system_log` handler regardless of route, so
 * nothing is missed between app open and a first visit to `/logs`.
 */
const live = useLiveStore()
const accounts = useAccountsStore()
const notifications = useNotificationStore()
const trading = useTradingStore()
const ui = useUiStore()
const route = useRoute()

// The chart page wants the rail out of the way; leaving it collapses back to
// whatever the admin themselves chose. Driven from here rather than from the
// page, so the transition happens with the navigation instead of a frame later.
watch(
  () => String(route.name ?? '').split('___')[0],
  (name) => ui.syncToRoute(name),
  { immediate: true },
)

onMounted(async () => {
  live.connect()
  await accounts.ensure()
  // Spec §6: balances must be current at all times, not current-when-clicked.
  accounts.startAutoRefresh()
  await notifications.hydrate()
  trading.loadPolicy()
})

onBeforeUnmount(() => {
  live.disconnect()
  accounts.stopAutoRefresh()
})
</script>

<template>
  <div class="min-h-[100dvh] flex bg-base">
    <AppSidebar />

    <div class="flex-1 flex flex-col min-w-0">
      <AppTopbar />

      <main class="flex-1 min-w-0 pb-[4.5rem] lg:pb-0">
        <slot />
      </main>
    </div>

    <AppToasts />
    <AppMobileNav />
  </div>
</template>
