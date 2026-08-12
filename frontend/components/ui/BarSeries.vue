<script setup lang="ts">
/**
 * Horizontal bars for magnitude with an identity label — "how much capital sits
 * on each account".
 *
 * Horizontal rather than vertical because the category labels are account
 * names, and rotated names are unreadable. One hue, because there is one
 * series: colour here would encode nothing, so the bars stay a single ink and
 * the value is direct-labelled at the end of every row.
 *
 * `tone: 'signal'` on a row is the one exception, and it means the row is a
 * problem (paused, unverified, non-USDT) — the same amber the failure
 * notifications use.
 */
const props = defineProps<{ rows: BarRow[]; max?: number }>()

const ceiling = computed(() => props.max ?? Math.max(...props.rows.map((r) => r.value), 1))

function width(value: number): string {
  if (ceiling.value <= 0) return '0%'
  // A 2px floor so a small-but-nonzero account is still visibly present rather
  // than reading as an empty row.
  return `max(2px, ${Math.max(0, (value / ceiling.value) * 100)}%)`
}

const FILL: Record<string, string> = {
  default: 'bg-brand/70',
  signal: 'bg-signal/70',
  muted: 'bg-ink-faint/40',
}
</script>

<template>
  <ul class="space-y-2.5">
    <li v-for="row in rows" :key="row.key" class="group">
      <div class="flex items-baseline gap-3 min-w-0">
        <span class="text-xs truncate min-w-0 flex-1" :class="row.tone === 'signal' ? 'text-signal' : 'text-ink'">
          {{ row.label }}
        </span>
        <span class="num text-xs text-ink-muted shrink-0">{{ row.display }}</span>
      </div>
      <div class="mt-1 h-1.5 rounded-full bg-raised overflow-hidden">
        <div
          class="h-full rounded-full transition-[width] duration-500 ease-out"
          :class="FILL[row.tone ?? 'default']"
          :style="{ width: width(row.value) }"
        />
      </div>
      <p v-if="row.sub" class="text-[0.65rem] text-ink-faint mt-1">{{ row.sub }}</p>
    </li>
  </ul>
</template>
