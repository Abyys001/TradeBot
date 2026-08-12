<script setup lang="ts">
/**
 * The top bar carries the three facts that are true regardless of which page is
 * open: is the engine reachable, is routing halted, and who is signed in.
 *
 * Connection state is not decoration here. A disconnected socket means the
 * admin is looking at figures that may already be stale, and on a page that
 * moves real money that has to be visible without being hunted for.
 */
const { t } = useI18n()
const ui = useUiStore()
const auth = useAuthStore()
const localePath = useLocalePath()
const { items, isActive } = useNavigation()

const pageTitle = computed(() => items.value.find((i) => isActive(i))?.label ?? '')

async function signOut() {
  await auth.logout()
  await navigateTo(localePath('/'))
}
</script>

<template>
  <header
    class="h-14 shrink-0 border-b border-line bg-panel/90 backdrop-blur sticky top-0 z-30
           flex items-center gap-2 px-3 sm:px-4"
  >
    <button
      class="btn-quiet btn-sm lg:hidden -ms-1.5"
      :aria-label="t('nav.openMenu')"
      @click="ui.openDrawer()"
    >
      <UiIcon name="menu" :size="20" />
    </button>

    <h1 class="text-sm font-medium truncate">{{ pageTitle }}</h1>

    <div class="ms-auto flex items-center gap-1 sm:gap-2">
      <!-- Spec §7 kill switch: a control, not a status light. Loudest thing in
           the bar when it is on. -->
      <AppStopAll />

      <!-- Link health and round-trip latency to the engine. -->
      <AppConnectionStatus />

      <!-- Spec §4 failure notices. In the bar rather than docked over the page,
           where they covered the chart; still persistent, still unmissable. -->
      <AppNotificationCenter />

      <span class="w-px h-5 bg-line hidden sm:block" />

      <!-- Theme and language live in the drawer on a phone: six controls in a
           360px bar leaves each one too small to hit and the page title with
           nowhere to go. -->
      <div class="hidden sm:flex items-center gap-1.5">
        <AppThemeToggle />
        <AppLocaleToggle />
      </div>

      <button
        class="btn-quiet btn-sm hidden sm:inline-flex"
        :title="t('nav.signOut')"
        :aria-label="t('nav.signOut')"
        @click="signOut"
      >
        <UiIcon name="logout" :size="16" class="flip-rtl" />
      </button>
    </div>
  </header>
</template>
