<script setup lang="ts">
/**
 * The finance page's answer to "who is owed what", on the dashboard.
 *
 * A bento rather than another four-across stat row: these six figures are not
 * peers. The profit is the one number the other five are derived from, so it
 * gets the large tile, and the three role shares sit beside it as the division
 * of exactly that figure. Capital in and capital now are the context that makes
 * the profit mean anything, so they are small and adjacent rather than absent.
 *
 * Every number comes from `/accounts/ledger/` and none is recomputed here — the
 * dashboard and the finance page must never disagree about the same money.
 * Shares divide *profit only*: on a loss there is nothing to divide and the
 * three tiles read zero, which is the honest answer, not a hidden card.
 */
const { t } = useI18n()
const api = useApi()
const localePath = useLocalePath()
const { money, compact, pct } = useFormat()

const SPLIT_ROLES = ['investor', 'trader', 'programmer'] as const

const snapshot = ref<LedgerSnapshot | null>(null)
const loading = ref(true)
const failed = ref(false)

onMounted(async () => {
  try {
    snapshot.value = await api.ledger()
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
})

const totals = computed(() => snapshot.value?.totals ?? null)
const pnl = computed(() => Number(totals.value?.pnl ?? 0))
const inProfit = computed(() => pnl.value > 0)
</script>

<template>
  <UiCard
    :title="t('dashboard.split.title')"
    :hint="t('dashboard.split.hint')"
    flush
  >
    <template #actions>
      <UiBadge v-if="snapshot?.pending_detections" tone="signal" dot>
        {{ t('dashboard.split.pending', { n: snapshot.pending_detections }) }}
      </UiBadge>
      <NuxtLink :to="localePath('/finance')" class="btn-quiet btn-sm">
        {{ t('dashboard.split.open') }}
      </NuxtLink>
    </template>

    <div v-if="loading" class="p-4 grid grid-cols-2 lg:grid-cols-4 gap-3">
      <div class="skeleton h-28 rounded-panel lg:col-span-2" />
      <div v-for="i in 3" :key="i" class="skeleton h-28 rounded-panel" />
    </div>

    <UiEmpty
      v-else-if="failed || !totals"
      class="p-6"
      icon="ledger"
      :title="t('dashboard.split.emptyTitle')"
      :body="t('dashboard.split.emptyBody')"
    />

    <div v-else class="p-3 sm:p-4 grid grid-cols-2 lg:grid-cols-4 gap-3">
      <!-- The pool. Twice the width, because the three tiles beside it are
           slices of this one number and nothing else on the card is. -->
      <div
        class="rounded-panel border p-4 flex flex-col justify-between lg:col-span-2 lg:row-span-2"
        :class="
          pnl === 0
            ? 'border-line bg-raised/40'
            : inProfit
              ? 'border-long/30 bg-long-dim'
              : 'border-short/30 bg-short-dim'
        "
      >
        <div>
          <p class="label">{{ t('dashboard.split.profit') }}</p>
          <p
            class="num text-stat mt-1"
            :class="pnl === 0 ? 'text-ink' : inProfit ? 'text-long' : 'text-short'"
          >
            {{ pnl > 0 ? '+' : pnl < 0 ? '−' : '' }}${{ money(Math.abs(pnl)) }}
          </p>
          <p class="text-xs text-ink-muted mt-1">
            {{ inProfit ? t('dashboard.split.dividing') : t('dashboard.split.nothingToDivide') }}
          </p>
        </div>

        <dl class="grid grid-cols-3 gap-3 mt-4 pt-3 border-t border-line/60 text-xs">
          <div>
            <dt class="label">{{ t('finance.stat.invested') }}</dt>
            <dd class="num mt-0.5">${{ compact(totals.net_invested) }}</dd>
          </div>
          <div>
            <dt class="label">{{ t('finance.stat.current') }}</dt>
            <dd class="num mt-0.5">${{ compact(totals.current_balance) }}</dd>
          </div>
          <div>
            <dt class="label">{{ t('dashboard.split.return') }}</dt>
            <dd class="num mt-0.5">{{ pct(totals.pnl_pct) }}</dd>
          </div>
        </dl>
      </div>

      <!-- One tile per role: the percentage it is owed, and what that is worth
           right now. Both, because a percentage of nothing is not a payout. -->
      <div
        v-for="role in SPLIT_ROLES"
        :key="role"
        class="rounded-panel border border-line bg-raised/40 p-4 flex flex-col justify-between"
      >
        <div class="flex items-baseline justify-between gap-2">
          <p class="label">{{ t(`finance.role.${role}`) }}</p>
          <p class="num text-xs text-ink-muted">{{ money(snapshot?.split[role], 0) }}%</p>
        </div>
        <p class="num text-lg mt-2" :class="inProfit ? 'text-long' : 'text-ink-faint'">
          ${{ money(totals.shares[role]) }}
        </p>
      </div>

      <!-- Fills the sixth cell: the accounts the totals above are built from. -->
      <div
        class="rounded-panel border border-line bg-raised/40 p-4 flex flex-col justify-between"
      >
        <p class="label">{{ t('dashboard.split.counted') }}</p>
        <p class="num text-lg mt-2">
          {{ totals.accounts }}
          <span class="text-xs text-ink-faint">
            {{ t('dashboard.split.accounts', { n: snapshot?.accounts.length ?? 0 }) }}
          </span>
        </p>
      </div>
    </div>
  </UiCard>
</template>
