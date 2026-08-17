<script setup lang="ts">
/**
 * The position row under the chart — spec §3's third SL/TP surface, and the
 * panel that has to show "entry price, liquidation price, current PnL, position
 * size, and other standard position details".
 *
 * Two states, deliberately not two components:
 *
 *   flat   the numbers the *pending* order would produce, so the row is never
 *          a dead strip of em dashes
 *   open   the aggregate of every account's real position, marked to market by
 *          the backend (see stores/positions.ts for why PnL is not computed here)
 *
 * Editing SL/TP while a trade is open does not just update local state — it
 * fans the amendment out to every account, which spec §4 caps at one second.
 * The push happens on `change` rather than on every keystroke: each change is N
 * orders to N exchanges, and we are not sending one per digit typed.
 */
const { t } = useI18n()
const order = useOrderStore()
const trading = useTradingStore()
const positions = usePositionsStore()
const market = useMarketStore()
const accounts = useAccountsStore()
const { money, pct, qty } = useFormat()

const amending = ref(false)
const closing = ref(false)
const confirmClose = ref(false)

const open = computed(() => positions.hasPosition)
const totals = computed(() => positions.totals)

/** Flat: what the ticket would commit right now, at 99% per account (spec §5). */
const projectedMargin = computed(
  () => accounts.tradeableUsdt * Number(trading.policy?.balance_fraction ?? 0.99),
)
const projectedNotional = computed(() =>
  order.market === 'futures' ? projectedMargin.value * order.leverage : projectedMargin.value,
)

const pnl = computed(() => positions.pnl)
const pnlTone = computed(() =>
  pnl.value === null || pnl.value === 0 ? 'text-ink' : pnl.value > 0 ? 'text-long' : 'text-short',
)

async function pushAmend() {
  if (!trading.hasOpenTrade) return
  amending.value = true
  try {
    await trading.amend(order.slPct, order.tpPct)
    await positions.load()
  } catch {
    // Surfaced by the store; per-account failures raise §4 notifications.
  } finally {
    amending.value = false
  }
}

async function closeAll() {
  closing.value = true
  confirmClose.value = false
  try {
    await trading.close()
    order.reset()
    positions.clear()
    await positions.load()
  } finally {
    closing.value = false
  }
}
</script>

<template>
  <div class="border-t border-line">
    <div class="flex items-end">
      <div class="flex-1 min-w-0 px-3 sm:px-4 py-2.5 flex items-end gap-4 sm:gap-6 overflow-x-auto no-scrollbar">
      <!-- Live PnL leads: it is the number the admin looks at first. -->
      <div v-if="open" class="shrink-0">
        <span class="label">{{ t('position.pnl') }}</span>
        <p class="num text-sm mt-0.5 font-semibold" :class="pnlTone">
          {{ pnl === null ? '—' : `${pnl >= 0 ? '+' : ''}$${money(pnl)}` }}
          <span v-if="positions.roePct !== null" class="text-[0.65rem] font-normal">
            ({{ positions.roePct >= 0 ? '+' : '' }}{{ pct(positions.roePct) }})
          </span>
        </p>
      </div>

      <div class="shrink-0">
        <span class="label">{{ open ? t('position.entry') : t('position.reference') }}</span>
        <p class="num text-sm mt-0.5">{{ money(order.entryPrice, 1) }}</p>
      </div>

      <div v-if="open" class="shrink-0">
        <span class="label">{{ t('position.mark') }}</span>
        <p class="num text-sm mt-0.5" :class="market.stale ? 'text-ink-faint' : ''">
          {{ money(positions.markPrice ?? market.mark, 1) }}
        </p>
      </div>

      <div class="shrink-0">
        <span class="label">{{ t('position.size') }}</span>
        <p class="num text-sm mt-0.5">
          {{ open ? qty(totals?.qty) : '≈' }}
          <span class="text-[0.65rem] text-ink-faint">
            ${{ money(open ? totals?.notional : projectedNotional) }}
          </span>
        </p>
      </div>

      <div class="shrink-0">
        <span class="label">{{ t('position.margin') }}</span>
        <p class="num text-sm mt-0.5">
          ${{ money(open ? totals?.margin : projectedMargin) }}
        </p>
      </div>

      <div class="shrink-0">
        <span class="label">{{ t('position.liquidation') }}</span>
        <p class="num text-sm mt-0.5 text-signal">{{ money(order.liquidationPrice, 1) }}</p>
      </div>

      <div class="shrink-0">
        <span class="label">{{ t('position.leverage') }}</span>
        <p class="num text-sm mt-0.5">{{ order.leverage }}x</p>
      </div>

      <!-- Surface 3 of 3 for SL/TP (spec §3). -->
      <div class="shrink-0">
        <span class="label">{{ t('ticket.sl') }}</span>
        <div class="flex items-baseline gap-1.5">
          <input
            :value="order.slPct"
            class="field mt-0.5 py-1 w-20 text-xs"
            inputmode="decimal"
            :aria-label="t('ticket.sl')"
            @input="order.setSL(Number(($event.target as HTMLInputElement).value) || null, 'position')"
            @change="pushAmend"
          />
          <span v-if="order.slPrice" class="num text-[0.65rem] text-ink-faint">
            {{ money(order.slPrice, 1) }}
          </span>
        </div>
      </div>
      <div class="shrink-0">
        <span class="label">{{ t('ticket.tp') }}</span>
        <div class="flex items-baseline gap-1.5">
          <input
            :value="order.tpPct"
            class="field mt-0.5 py-1 w-20 text-xs"
            inputmode="decimal"
            :aria-label="t('ticket.tp')"
            @input="order.setTP(Number(($event.target as HTMLInputElement).value) || null, 'position')"
            @change="pushAmend"
          />
          <span v-if="order.tpPrice" class="num text-[0.65rem] text-ink-faint">
            {{ money(order.tpPrice, 1) }}
          </span>
        </div>
      </div>

      <div v-if="!open && order.slAccountLossPct !== null" class="shrink-0">
        <span class="label">{{ t('ticket.riskLabel') }}</span>
        <p class="num text-sm mt-0.5 text-short">{{ pct(order.slAccountLossPct) }}</p>
      </div>

      <div v-if="open" class="shrink-0">
        <span class="label">{{ t('position.accounts') }}</span>
        <p class="num text-sm mt-0.5">
          {{ totals?.accounts ?? 0 }}
          <span v-if="totals?.failed" class="text-short text-[0.65rem]">
            +{{ totals.failed }} {{ t('position.failedShort') }}
          </span>
        </p>
      </div>

      </div>

      <div class="shrink-0 px-3 sm:px-4 py-2.5 flex items-center gap-2">
        <span v-if="amending" class="label text-signal whitespace-nowrap">
          {{ t('position.pushing') }}
        </span>
        <span v-else-if="order.lastEditedFrom" class="label hidden md:inline whitespace-nowrap">
          {{ t('position.editedFrom', { source: t(`position.source.${order.lastEditedFrom}`) }) }}
        </span>

        <button
          class="btn-danger btn-sm"
          :disabled="!trading.hasOpenTrade || closing"
          @click="confirmClose = true"
        >
          {{ closing ? t('position.closing') : t('position.close') }}
        </button>
      </div>
    </div>

    <!-- A leg holding a position with no stop attached is spec §4's quiet
         failure: it will not show up as an error anywhere else. -->
    <p
      v-if="positions.unprotected.length"
      class="alert px-3 sm:px-4 py-2 text-xs flex items-center gap-2"
    >
      <UiIcon name="alert" :size="14" class="shrink-0" />
      {{ t('position.unprotected', { n: positions.unprotected.length }) }}
    </p>

    <!-- Closing hits every account at market. It asks once. -->
    <UiModal v-model="confirmClose" :title="t('position.confirmCloseTitle')" size="sm">
      <p class="text-sm leading-relaxed">
        {{ t('position.confirmCloseBody', { n: totals?.accounts ?? 0, symbol: order.symbol }) }}
      </p>
      <template #footer>
        <div class="flex gap-2 justify-end">
          <button class="btn-ghost" @click="confirmClose = false">{{ t('common.cancel') }}</button>
          <button class="btn-danger" @click="closeAll">{{ t('position.close') }}</button>
        </div>
      </template>
    </UiModal>
  </div>
</template>
