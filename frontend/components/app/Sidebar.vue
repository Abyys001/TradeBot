<script setup lang="ts">
/**
 * The desktop rail.
 *
 * Collapsible to icons, because the chart wants every pixel of width and the
 * admin who lives on that page should not pay 200px for a menu they know by
 * heart. It collapses itself on arrival there and restores the admin's own
 * preference on the way out (stores/ui.ts).
 *
 * Collapsed, every row is the same 40×40 square centred in the same 4.25rem
 * column — logo, links, user, toggle. The previous version left the labels'
 * start-padding in place when they were hidden, so the icons sat off-centre and
 * each row drifted by a different amount.
 */
const { items, isActive } = useNavigation()
const ui = useUiStore()
const auth = useAuthStore()
const localePath = useLocalePath()
const { t } = useI18n()

/** One row geometry, used by every row, so collapsing cannot make them differ. */
const row = computed(() =>
  ui.sidebarCollapsed
    ? 'w-10 h-10 mx-auto justify-center px-0'
    : 'w-full h-10 justify-start px-2.5',
)
</script>

<template>
  <aside
    class="hidden lg:flex flex-col border-e border-line bg-panel transition-[width] duration-200 ease-out"
    :class="ui.sidebarCollapsed ? 'w-[4.25rem]' : 'w-56'"
  >
    <div class="h-14 flex items-center border-b border-line px-2">
      <NuxtLink
        :to="localePath('/dashboard')"
        class="flex items-center gap-2.5 min-w-0 group rounded-lg transition-colors"
        :class="row"
        :title="t('app.name')"
      >
        <span
          class="w-8 h-8 rounded-lg bg-brand-dim border border-brand/30 grid place-items-center
                 text-brand shrink-0 group-hover:bg-brand/25 transition-colors"
        >
          <UiIcon name="bolt" :size="16" />
        </span>
        <span v-if="!ui.sidebarCollapsed" class="display text-sm truncate">
          {{ t('app.short') }}
        </span>
      </NuxtLink>
    </div>

    <nav class="flex-1 p-2 space-y-1 overflow-y-auto overflow-x-hidden" :aria-label="t('nav.primary')">
      <NuxtLink
        v-for="item in items"
        :key="item.name"
        :to="item.path"
        :title="ui.sidebarCollapsed ? item.label : undefined"
        class="flex items-center gap-3 rounded-lg text-sm transition-colors relative"
        :class="[
          row,
          isActive(item)
            ? 'bg-brand-dim text-brand'
            : 'text-ink-muted hover:text-ink hover:bg-raised',
        ]"
      >
        <!-- The active marker is a bar, not just a tint: at a glance from a
             metre away the tint alone is not legible on a dark ground.
             Collapsed, it moves to the outer edge of the rail so it still reads
             as a marker rather than a stripe through the icon. -->
        <span
          v-if="isActive(item)"
          class="absolute top-2 bottom-2 w-0.5 rounded-full bg-brand"
          :class="ui.sidebarCollapsed ? '-start-1.5' : 'start-0'"
        />
        <UiIcon :name="item.icon" :size="18" class="shrink-0" />
        <span v-if="!ui.sidebarCollapsed" class="truncate">{{ item.label }}</span>
        <span
          v-if="item.badge"
          class="num text-[0.65rem] rounded-full bg-signal-dim text-signal leading-none"
          :class="
            ui.sidebarCollapsed
              ? 'absolute -top-0.5 -end-0.5 min-w-[1rem] h-4 px-1 grid place-items-center'
              : 'ms-auto px-1.5 py-0.5'
          "
        >
          {{ item.badge }}
        </span>
      </NuxtLink>
    </nav>

    <div class="p-2 border-t border-line space-y-1">
      <!-- The user row keeps the same geometry as a nav row when collapsed: an
           initial in a 40px square, not a disappearing block that shifts
           everything below it. -->
      <div
        class="flex items-center gap-3 rounded-lg min-w-0"
        :class="row"
        :title="ui.sidebarCollapsed ? auth.username : undefined"
      >
        <span
          class="w-7 h-7 rounded-full bg-raised border border-line grid place-items-center
                 text-xs uppercase shrink-0"
        >
          {{ (auth.username || '?').slice(0, 1) }}
        </span>
        <span v-if="!ui.sidebarCollapsed" class="min-w-0">
          <span class="label block">{{ t('nav.signedInAs') }}</span>
          <span class="text-sm truncate block">{{ auth.username }}</span>
        </span>
      </div>

      <button
        class="flex items-center gap-3 rounded-lg text-sm text-ink-muted
               hover:text-ink hover:bg-raised transition-colors"
        :class="row"
        :title="ui.sidebarCollapsed ? t('nav.expand') : undefined"
        :aria-label="ui.sidebarCollapsed ? t('nav.expand') : t('nav.collapse')"
        @click="ui.toggleSidebar()"
      >
        <UiIcon
          name="chevronRight"
          :size="18"
          class="shrink-0 flip-rtl transition-transform duration-200"
          :class="ui.sidebarCollapsed ? '' : 'rotate-180'"
        />
        <span v-if="!ui.sidebarCollapsed" class="truncate">{{ t('nav.collapse') }}</span>
      </button>
    </div>
  </aside>
</template>
