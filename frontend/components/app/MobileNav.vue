<script setup lang="ts">
/**
 * Phone navigation: a fixed tab bar for the four destinations that matter, plus
 * a drawer for the rest.
 *
 * A tab bar rather than a hamburger alone because the admin switching between
 * the terminal and the accounts list mid-incident should not have to open a
 * menu to do it. The bar sits above the home indicator via safe-area padding.
 */
const { items, isActive } = useNavigation()
const ui = useUiStore()
const auth = useAuthStore()
const route = useRoute()
const localePath = useLocalePath()
const { t } = useI18n()

const primary = computed(() => items.value.filter((i) => i.primary))
const secondary = computed(() => items.value.filter((i) => !i.primary))

// Any navigation closes the drawer; leaving it open over the new page is the
// classic mobile-nav bug.
watch(() => route.fullPath, () => ui.closeDrawer())

async function signOut() {
  ui.closeDrawer()
  await auth.logout()
  await navigateTo(localePath('/'))
}
</script>

<template>
  <div class="lg:hidden">
    <!-- Drawer -->
    <Transition
      enter-active-class="transition-opacity duration-150"
      enter-from-class="opacity-0"
      leave-active-class="transition-opacity duration-150"
      leave-to-class="opacity-0"
    >
      <div
        v-if="ui.drawerOpen"
        class="fixed inset-0 z-50 scrim backdrop-blur-sm"
        @click.self="ui.closeDrawer()"
      >
        <nav
          class="absolute inset-y-0 start-0 w-72 max-w-[85vw] bg-panel border-e border-line
                 flex flex-col animate-slide-in"
          :aria-label="t('nav.primary')"
        >
          <div class="h-14 flex items-center gap-2.5 px-4 border-b border-line">
            <span
              class="w-8 h-8 rounded-lg bg-brand-dim border border-brand/30 grid place-items-center text-brand"
            >
              <UiIcon name="bolt" :size="16" />
            </span>
            <span class="display text-sm">{{ t('app.short') }}</span>
            <button class="btn-quiet btn-sm ms-auto -me-1.5" :aria-label="t('common.close')" @click="ui.closeDrawer()">
              <UiIcon name="close" :size="18" />
            </button>
          </div>

          <div class="flex-1 p-2 overflow-y-auto space-y-0.5">
            <NuxtLink
              v-for="item in items"
              :key="item.name"
              :to="item.path"
              class="flex items-center gap-3 rounded-lg px-3 h-11 text-sm transition-colors"
              :class="
                isActive(item)
                  ? 'bg-brand-dim text-brand'
                  : 'text-ink-muted hover:text-ink hover:bg-raised'
              "
            >
              <UiIcon :name="item.icon" :size="18" />
              <span>{{ item.label }}</span>
              <span
                v-if="item.badge"
                class="num ms-auto text-[0.65rem] rounded-full bg-signal-dim text-signal px-1.5 py-0.5"
              >
                {{ item.badge }}
              </span>
            </NuxtLink>
          </div>

          <div class="p-3 border-t border-line space-y-3">
            <!-- The two controls the top bar gives up on a phone. -->
            <div class="flex items-center gap-2">
              <AppThemeToggle />
              <AppLocaleToggle />
            </div>

            <div>
              <p class="label">{{ t('nav.signedInAs') }}</p>
              <div class="flex items-center gap-2 mt-1">
                <p class="text-sm truncate flex-1">{{ auth.username }}</p>
                <button class="btn-ghost btn-sm" @click="signOut">
                  {{ t('nav.signOut') }}
                </button>
              </div>
            </div>
          </div>
        </nav>
      </div>
    </Transition>

    <!-- Tab bar -->
    <nav
      class="fixed inset-x-0 bottom-0 z-40 bg-panel/95 backdrop-blur border-t border-line
             flex"
      :style="{ paddingBottom: 'env(safe-area-inset-bottom)' }"
      :aria-label="t('nav.primary')"
    >
      <NuxtLink
        v-for="item in primary"
        :key="item.name"
        :to="item.path"
        class="flex-1 flex flex-col items-center justify-center gap-1 py-2 min-h-[3.25rem] relative
               transition-colors"
        :class="isActive(item) ? 'text-brand' : 'text-ink-faint'"
      >
        <span v-if="isActive(item)" class="absolute top-0 inset-x-6 h-0.5 rounded-full bg-brand" />
        <UiIcon :name="item.icon" :size="19" />
        <span class="text-[0.65rem] leading-none">{{ item.label }}</span>
        <span
          v-if="item.badge"
          class="absolute top-1.5 ms-6 w-1.5 h-1.5 rounded-full bg-signal"
        />
      </NuxtLink>

      <button
        class="flex-1 flex flex-col items-center justify-center gap-1 py-2 text-ink-faint"
        :class="secondary.some(isActive) ? 'text-brand' : ''"
        @click="ui.openDrawer()"
      >
        <UiIcon name="menu" :size="19" />
        <span class="text-[0.65rem] leading-none">{{ t('nav.more') }}</span>
      </button>
    </nav>
  </div>
</template>
