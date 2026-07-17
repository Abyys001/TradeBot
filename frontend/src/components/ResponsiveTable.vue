<script setup lang="ts">
withDefaults(
  defineProps<{
    loading?: boolean
    empty?: boolean
    /** Pin the header while scrolling a bounded-height table (e.g. inside a drawer). */
    stickyHead?: boolean
  }>(),
  {
    loading: false,
    empty: false,
    stickyHead: false,
  },
)
</script>

<template>
  <div>
    <div v-if="loading" class="p-3 text-sm text-fg-muted">
      <slot name="loading" />
    </div>
    <div v-else-if="empty" class="p-3 text-sm text-fg-muted">
      <slot name="empty" />
    </div>
    <template v-else>
      <div class="hidden overflow-x-auto md:block">
        <table class="w-full text-sm">
          <thead class="bg-surface-muted/50 text-xs uppercase text-fg-muted" :class="{ 'sticky top-0 z-10': stickyHead }">
            <tr>
              <slot name="head" />
            </tr>
          </thead>
          <tbody>
            <slot name="row" />
          </tbody>
        </table>
      </div>
      <div class="flex flex-col gap-2 p-2 md:hidden">
        <slot name="card" />
      </div>
    </template>
  </div>
</template>
