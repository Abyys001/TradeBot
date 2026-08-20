<script setup lang="ts">
/**
 * A KPI tile: one number, said once.
 *
 * Deliberately not a chart. A single current value has no shape to plot, and
 * wrapping it in a sparkline or a donut would add ink without adding
 * information. The optional `trend` slot exists for the cases where the number
 * genuinely has history behind it.
 *
 * `tone` is semantic, not decorative — `signal` means something is wrong, and
 * amber is reserved for exactly that across the whole panel.
 */
withDefaults(
  defineProps<{
    label: string
    value: string | number
    unit?: string
    sub?: string
    icon?: IconName
    tone?: 'default' | 'ok' | 'signal' | 'long' | 'short'
    loading?: boolean
    to?: string
  }>(),
  { tone: 'default' },
)

const TONE: Record<string, string> = {
  default: 'text-ink',
  ok: 'text-ok',
  signal: 'text-signal',
  long: 'text-long',
  short: 'text-short',
}
</script>

<template>
  <component
    :is="to ? resolveComponent('NuxtLink') : 'div'"
    :to="to"
    class="panel p-3 sm:p-4 flex flex-col gap-1.5 sm:gap-2 min-w-0 transition-colors"
    :class="[to ? 'hover:border-line-strong hover:bg-raised' : '', tone === 'signal' ? 'border-signal/40' : '']"
  >
    <div class="flex items-center gap-2 min-w-0">
      <UiIcon v-if="icon" :name="icon" :size="14" class="text-ink-faint" />
      <span class="label truncate">{{ label }}</span>
      <UiIcon
        v-if="to"
        name="chevronRight"
        :size="14"
        class="ms-auto text-ink-faint flip-rtl"
      />
    </div>

    <div v-if="loading" class="skeleton h-8 w-24" />
    <p v-else class="num text-stat leading-none flex items-baseline gap-1" :class="TONE[tone]">
      <span class="truncate">{{ value }}</span>
      <span v-if="unit" class="text-sm text-ink-faint">{{ unit }}</span>
    </p>

    <p v-if="sub" class="text-xs text-ink-muted truncate">{{ sub }}</p>
    <slot />
  </component>
</template>
