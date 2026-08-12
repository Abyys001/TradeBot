<script setup lang="ts">
/**
 * Spec §4 is a hard promise: every account within one second. This shows
 * whether the last action actually met it, so a regression is visible the day
 * it happens rather than months later.
 *
 * The bar is the budget, not a decoration — the fill is the share of the
 * second that was used, and it turns amber the moment it is all of it.
 */
const props = defineProps<{ result: FanOutResult }>()
const { t } = useI18n()
const accounts = useAccountsStore()
const { ms } = useFormat()

const used = computed(() => Math.min(100, (props.result.total_ms / 1000) * 100))
</script>

<template>
  <div class="border-t border-line pt-3 space-y-2">
    <div class="flex items-baseline justify-between gap-2">
      <span class="label">{{ t('fanout.title') }}</span>
      <span class="num text-xs" :class="result.within_budget ? 'text-ok' : 'text-signal'">
        {{ ms(result.total_ms) }} / 1000ms
      </span>
    </div>

    <div class="h-1 rounded-full bg-raised overflow-hidden">
      <div
        class="h-full rounded-full transition-[width] duration-500 ease-out"
        :class="result.within_budget ? 'bg-ok/70' : 'bg-signal'"
        :style="{ width: `${Math.max(2, used)}%` }"
      />
    </div>

    <p class="text-xs text-ink-muted">
      {{ t('fanout.counts', { ok: result.succeeded.length, failed: result.failed.length }) }}
    </p>

    <p v-if="!result.within_budget" class="text-xs text-signal">{{ t('fanout.overBudget') }}</p>

    <ul v-if="result.failed.length" class="space-y-1">
      <li v-for="leg in result.failed" :key="leg.account_id" class="text-xs text-short">
        <span class="text-ink">{{ accounts.labelFor(leg.account_id) }}</span> — {{ leg.error }}
      </li>
    </ul>
  </div>
</template>
