<script setup lang="ts">
/**
 * Who this order is about to hit, and what happened to each of them last time.
 *
 * Spec §5 says sizing differs per account and everything else is identical, so
 * the useful preview is each account's own margin at 99% of its own balance —
 * shown *before* sending, next to the exchange minimum that would skip it.
 *
 * Once an order goes out, the same rows carry the live per-leg result from the
 * WebSocket, so a slow or failing exchange is visible while the fan-out is
 * still running rather than in the summary afterwards — and then the marked-to
 * -market PnL for that account, which is the number the partner will ask about.
 */
const { t } = useI18n()
const accounts = useAccountsStore()
const order = useOrderStore()
const trading = useTradingStore()
const positions = usePositionsStore()
const live = useLiveStore()
const { money, ms } = useFormat()

/** Spec §5 / Q12: 99% of that account's own USDT, leverage on top. */
const fraction = computed(() => Number(trading.policy?.balance_fraction ?? 0.99))

const rows = computed(() =>
  accounts.byCapital.map((account) => {
    const balance = Number(account.last_balance ?? 0)
    const margin = account.balance_is_usdt ? balance * fraction.value : 0
    const notional = order.market === 'futures' ? margin * order.leverage : margin
    const leg = live.legResults[account.id]
    const openLeg = trading.openTrade?.legs.find((l) => l.account === account.id)
    // While a trade is open the projected size is history; show what the
    // account actually holds and what it is worth right now instead.
    const position = positions.byAccount(account.id)
    return { account, margin, notional, leg, openLeg, position }
  }),
)

const inTrade = computed(() => positions.hasPosition)
</script>

<template>
  <div class="divide-y divide-line">
    <div class="px-4 py-2.5 flex items-baseline gap-2">
      <span class="label">{{ inTrade ? t('terminal.inTrade') : t('terminal.routingTo') }}</span>
      <span class="num text-xs ms-auto">
        {{ inTrade ? positions.filled.length : accounts.tradeable.length }}/{{ accounts.items.length }}
      </span>
    </div>

    <div
      v-for="row in rows"
      :key="row.account.id"
      class="px-4 py-2.5 flex items-center gap-3"
      :class="row.account.status !== 'active' ? 'opacity-50' : ''"
    >
      <span
        class="w-1.5 h-1.5 rounded-full shrink-0"
        :class="{
          'bg-ok': row.leg?.ok || row.openLeg?.ok,
          'bg-short': row.leg?.ok === false || row.openLeg?.ok === false,
          'bg-ink-faint': !row.leg && !row.openLeg,
        }"
      />

      <div class="min-w-0 flex-1">
        <p class="text-xs truncate">{{ row.account.label }}</p>
        <p class="text-[0.65rem] text-ink-faint truncate">
          {{ row.account.exchange_label }}
          <template v-if="row.leg"> · {{ ms(row.leg.ms) }}</template>
        </p>
      </div>

      <div class="text-end shrink-0">
        <template v-if="row.position?.ok">
          <p
            class="num text-xs"
            :class="Number(row.position.pnl ?? 0) >= 0 ? 'text-long' : 'text-short'"
          >
            {{ Number(row.position.pnl ?? 0) >= 0 ? '+' : '' }}${{ money(row.position.pnl) }}
          </p>
          <p class="num text-[0.65rem] text-ink-faint">
            ${{ money(row.position.margin) }} {{ t('position.margin').toLowerCase() }}
          </p>
        </template>
        <template v-else>
          <p class="num text-xs">${{ money(row.margin) }}</p>
          <p v-if="order.market === 'futures'" class="num text-[0.65rem] text-ink-faint">
            ${{ money(row.notional) }} {{ t('terminal.notional') }}
          </p>
        </template>
      </div>
    </div>

    <p v-if="!rows.length" class="px-4 py-6 text-xs text-ink-muted text-center">
      {{ t('accounts.empty') }}
    </p>
  </div>
</template>
