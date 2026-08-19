<script setup lang="ts">
/**
 * Surface 1 of 3 for SL/TP editing (spec §3). Writes to the order store, which
 * is what keeps it, the chart and the position bar from disagreeing.
 *
 * The panel's job is to make the cost of the numbers obvious *before* they are
 * sent. Under the price basis at 10x, a "2%" stop is a 20% account loss — so
 * that figure is rendered next to the input, in dollars where a balance is
 * known, and a stop past liquidation blocks submission outright rather than
 * being routed and silently never triggering.
 */
const { t } = useI18n()
const order = useOrderStore()
const trading = useTradingStore()
const accounts = useAccountsStore()
const market = useMarketStore()
const positions = usePositionsStore()
const { money, pct } = useFormat()

const sideOptions = computed(() => [
  { value: 'long', label: t('side.long'), tone: 'long' as const },
  { value: 'short', label: t('side.short'), tone: 'short' as const },
])

const typeOptions = computed(() => [
  { value: 'market', label: t('ticket.market') },
  { value: 'limit', label: t('ticket.limit') },
])

const basisOptions = computed(() => [
  { value: 'price', label: t('risk.basis.price') },
  { value: 'margin', label: t('risk.basis.margin') },
])

const marketOptions = computed(() => [
  { value: 'futures', label: t('market.futures') },
  { value: 'spot', label: t('market.spot') },
])

/**
 * What the stop costs in money, summed over the accounts that would actually
 * take the trade. Percentages are abstract; "$412 across 6 accounts" is not.
 */
const lossInDollars = computed(() => {
  const lossPct = order.slAccountLossPct
  if (lossPct === null) return null
  return (accounts.tradeableUsdt * lossPct) / 100
})

const gainInDollars = computed(() => {
  const gainPct = order.tpAccountGainPct
  if (gainPct === null) return null
  return (accounts.tradeableUsdt * gainPct) / 100
})

const noAccounts = computed(() => !accounts.initial && accounts.tradeable.length === 0)
const halted = computed(() => trading.halted)
/**
 * Spec §5: 99% of the balance goes into the trade, so an account cannot hold
 * two. The ticket says so instead of letting the order be sent and rejected.
 */
const alreadyInTrade = computed(() => positions.hasPosition)
const canSubmit = computed(
  () =>
    !trading.submitting &&
    order.hasProtection &&
    !order.slBeyondLiquidation &&
    !noAccounts.value &&
    !halted.value &&
    !alreadyInTrade.value,
)

const leverageRange = computed(() => trading.policy?.leverage_range ?? [1, 10])

/** Total dollar size this order would commit, across every eligible account. */
const totalMargin = computed(
  () => accounts.tradeableUsdt * Number(trading.policy?.balance_fraction ?? 0.99),
)
const totalNotional = computed(() =>
  order.market === 'futures' ? totalMargin.value * order.leverage : totalMargin.value,
)

/**
 * Preset stops, in the basis currently selected. Typing "1.5" into a box is
 * fine; reaching for a common value should not need the keyboard at all.
 */
const SL_PRESETS = [0.5, 1, 2, 5]
const TP_PRESETS = [1, 2, 5, 10]

async function submit() {
  try {
    await trading.open({
      symbol: order.symbol,
      side: order.side,
      market: order.market,
      order_type: order.orderType,
      leverage: order.leverage,
      sl_pct: order.slPct,
      tp_pct: order.tpPct,
      limit_price: order.limitPrice,
    })
    await positions.load()
  } catch {
    // The store holds the message; per-account failures arrive as spec §4
    // notifications, which outlive this component.
  }
}

/** A limit order with no price typed defaults to the market — never to zero. */
function useMarketPrice() {
  if (market.mark !== null) order.limitPrice = Number(market.mark.toFixed(2))
}
</script>

<template>
  <div class="p-4 space-y-4">
    <UiSegmented
      :model-value="order.side"
      :options="sideOptions"
      @update:model-value="order.side = $event as 'long' | 'short'"
    />

    <div class="grid grid-cols-2 gap-2">
      <UiSegmented
        :model-value="order.market"
        :options="marketOptions"
        size="sm"
        @update:model-value="order.market = $event as 'futures' | 'spot'"
      />
      <UiSegmented
        :model-value="order.orderType"
        :options="typeOptions"
        size="sm"
        @update:model-value="order.orderType = $event as 'market' | 'limit'"
      />
    </div>

    <!-- The pair is chosen in the chart header, not here. Two editable symbol
         fields on one screen is how an order goes out for the instrument the
         admin is not looking at. -->
    <div class="flex items-baseline justify-between gap-3 px-3 py-2 rounded-lg bg-sunken border border-line">
      <span class="label">{{ t('ticket.symbol') }}</span>
      <span class="num text-sm font-medium">{{ order.symbol }}</span>
    </div>

    <UiField v-if="order.orderType === 'limit'" v-slot="{ id }" :label="t('ticket.limitPrice')">
      <div class="flex gap-2">
        <input :id="id" v-model.number="order.limitPrice" class="field" inputmode="decimal" />
        <!-- "Use the current price" needs a current price: with the feed stale
             this button would write the last number that arrived, whenever that
             was, straight into a live limit order. -->
        <button
          class="btn-ghost btn-sm shrink-0"
          :disabled="market.mark === null || market.stale"
          @click="useMarketPrice"
        >
          {{ t('ticket.useMark') }}
        </button>
      </div>
    </UiField>

    <!-- Leverage: a slider, because the value is chosen by feel against the
         liquidation distance shown under it, not typed. -->
    <div v-if="order.market === 'futures'">
      <div class="flex items-baseline justify-between">
        <span class="label">{{ t('ticket.leverage') }}</span>
        <span class="num text-sm">{{ order.leverage }}x</span>
      </div>
      <input
        v-model.number="order.leverage"
        type="range"
        :min="leverageRange[0]"
        :max="leverageRange[1]"
        class="w-full mt-2 accent-brand"
      />
      <p class="label mt-1">
        {{ t('ticket.liqDistance', { pct: order.liquidationDistancePct.toFixed(1) }) }}
      </p>
    </div>

    <div>
      <span class="label">{{ t('ticket.sltpBasis') }}</span>
      <UiSegmented
        :model-value="order.basis"
        :options="basisOptions"
        size="sm"
        class="mt-1.5"
        @update:model-value="order.setBasis($event as Basis)"
      />
    </div>

    <div class="grid grid-cols-2 gap-3">
      <UiField v-slot="{ id }" :label="t('ticket.sl')">
        <input
          :id="id"
          :value="order.slPct"
          class="field"
          inputmode="decimal"
          @input="order.setSL(Number(($event.target as HTMLInputElement).value) || null, 'ticket')"
        />
        <div class="flex gap-1 mt-1.5">
          <button
            v-for="preset in SL_PRESETS"
            :key="preset"
            class="num flex-1 text-[0.65rem] py-0.5 rounded-md border border-line
                   text-ink-muted hover:text-short hover:border-short/50 transition-colors"
            :class="order.slPct === preset ? 'text-short border-short/60 bg-short-dim' : ''"
            @click="order.setSL(preset, 'ticket')"
          >
            {{ preset }}%
          </button>
        </div>
      </UiField>
      <UiField v-slot="{ id }" :label="t('ticket.tp')">
        <input
          :id="id"
          :value="order.tpPct"
          class="field"
          inputmode="decimal"
          @input="order.setTP(Number(($event.target as HTMLInputElement).value) || null, 'ticket')"
        />
        <div class="flex gap-1 mt-1.5">
          <button
            v-for="preset in TP_PRESETS"
            :key="preset"
            class="num flex-1 text-[0.65rem] py-0.5 rounded-md border border-line
                   text-ink-muted hover:text-long hover:border-long/50 transition-colors"
            :class="order.tpPct === preset ? 'text-long border-long/60 bg-long-dim' : ''"
            @click="order.setTP(preset, 'ticket')"
          >
            {{ preset }}%
          </button>
        </div>
      </UiField>
    </div>

    <!-- The cost of those two numbers, in the units that matter. -->
    <dl
      v-if="order.slAccountLossPct !== null || order.tpAccountGainPct !== null"
      class="rounded-lg border border-line bg-sunken p-3 space-y-2 text-xs"
    >
      <div v-if="order.slAccountLossPct !== null" class="flex items-baseline justify-between gap-3">
        <dt class="text-ink-muted">{{ t('ticket.riskLabel') }}</dt>
        <dd class="num text-short text-end">
          {{ pct(order.slAccountLossPct) }}
          <span v-if="lossInDollars !== null" class="text-ink-faint">
            · ${{ money(lossInDollars) }}
          </span>
        </dd>
      </div>
      <div v-if="order.tpAccountGainPct !== null" class="flex items-baseline justify-between gap-3">
        <dt class="text-ink-muted">{{ t('ticket.rewardLabel') }}</dt>
        <dd class="num text-long text-end">
          {{ pct(order.tpAccountGainPct) }}
          <span v-if="gainInDollars !== null" class="text-ink-faint">
            · ${{ money(gainInDollars) }}
          </span>
        </dd>
      </div>
      <div
        v-if="order.slPct && order.tpPct"
        class="flex items-baseline justify-between gap-3 border-t border-line pt-2"
      >
        <dt class="text-ink-muted">{{ t('ticket.rr') }}</dt>
        <dd class="num">1 : {{ (order.tpPct / order.slPct).toFixed(2) }}</dd>
      </div>
    </dl>

    <!-- What is actually about to be committed, in dollars, across everyone. -->
    <dl class="rounded-lg border border-line bg-sunken p-3 space-y-2 text-xs">
      <div class="flex items-baseline justify-between gap-3">
        <dt class="text-ink-muted">{{ t('ticket.totalMargin') }}</dt>
        <dd class="num">${{ money(totalMargin) }}</dd>
      </div>
      <div v-if="order.market === 'futures'" class="flex items-baseline justify-between gap-3">
        <dt class="text-ink-muted">{{ t('ticket.totalNotional') }}</dt>
        <dd class="num">${{ money(totalNotional) }}</dd>
      </div>
      <div v-if="market.mark !== null" class="flex items-baseline justify-between gap-3">
        <dt class="text-ink-muted">{{ t('position.mark') }}</dt>
        <dd class="num">
          {{ money(market.mark, 2) }}
          <!-- The last real quote, with the feed since gone. Said plainly:
               this number is stale, not current. -->
          <span v-if="!market.live" class="text-signal">{{ t('terminal.feedDown') }}</span>
        </dd>
      </div>
    </dl>

    <p v-if="!order.hasProtection" class="alert p-2.5 text-xs leading-relaxed">
      {{ t('ticket.sltpRequired') }}
    </p>

    <p v-if="order.slBeyondLiquidation" class="alert p-2.5 text-xs leading-relaxed">
      {{ t('ticket.slBeyondLiquidation') }}
    </p>

    <p class="text-xs text-ink-faint leading-relaxed">{{ t('ticket.sizingNote') }}</p>

    <div class="space-y-2">
      <button
        class="w-full font-medium"
        :class="order.side === 'long' ? 'btn bg-long text-ink-invert' : 'btn bg-short text-ink-invert'"
        :disabled="!canSubmit"
        @click="submit"
      >
        {{
          trading.submitting
            ? t('ticket.sending')
            : t('ticket.submitSide', {
                side: t(`side.${order.side}`),
                n: accounts.tradeable.length,
              })
        }}
      </button>

      <p v-if="halted" class="alert p-2.5 text-xs">{{ t('ticket.haltedNote') }}</p>
      <p v-else-if="alreadyInTrade" class="alert p-2.5 text-xs">{{ t('ticket.alreadyOpen') }}</p>
      <p v-else-if="noAccounts" class="alert p-2.5 text-xs">{{ t('ticket.noAccounts') }}</p>
      <p v-if="trading.error" class="text-xs text-short">{{ trading.error }}</p>
    </div>

    <TerminalFanOutSummary v-if="trading.lastResult" :result="trading.lastResult" />
  </div>
</template>
