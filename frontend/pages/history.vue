<script setup lang="ts">
/**
 * Spec §8: per-account trade log — pair, time, PnL.
 *
 * "Per-account" is the requirement, so the account filter is a first-class
 * control rather than something to scroll for: it re-queries the API, which
 * already supports `?account=`, and every summary figure recomputes with it.
 *
 * Trades expand to their legs instead of rendering every leg of every trade at
 * once. Twenty trades across ten accounts is two hundred rows, and none of them
 * answers the first question the page is opened with.
 */
const { t } = useI18n()
const api = useApi()
const accounts = useAccountsStore()
const trading = useTradingStore()
const { money, ms, qty, dateTime } = useFormat()

useHead({ title: t('nav.history') })

const trades = ref<Trade[]>([])
const loading = ref(true)
const error = ref('')
const accountFilter = ref<number | null>(null)
const sideFilter = ref<'all' | 'long' | 'short'>('all')
const expanded = ref<Set<number>>(new Set())

async function load() {
  loading.value = true
  try {
    trades.value = await api.trades(accountFilter.value)
    error.value = ''
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await accounts.ensure()
  await load()
})

watch(accountFilter, load)

const visible = computed(() =>
  sideFilter.value === 'all'
    ? trades.value
    : trades.value.filter((trade) => trade.side === sideFilter.value),
)

/**
 * Summaries respect the filter. A "total PnL" that ignores the account you
 * just selected is worse than no total at all.
 */
const summary = computed(() => {
  const legs = visible.value.flatMap((trade) =>
    accountFilter.value === null
      ? trade.legs
      : trade.legs.filter((leg) => leg.account === accountFilter.value),
  )
  const pnl = legs.reduce((sum, leg) => sum + Number(leg.pnl ?? 0), 0)
  const wins = legs.filter((leg) => Number(leg.pnl ?? 0) > 0).length
  const scored = legs.filter((leg) => leg.pnl !== null && Number(leg.pnl) !== 0).length
  const failed = legs.filter((leg) => !leg.ok).length
  const breaches = visible.value.filter(
    (trade) => (trade.fanout_ms ?? 0) > trading.fanoutBudgetMs,
  ).length
  return { pnl, wins, scored, failed, breaches, legs: legs.length }
})

/** What the account panel above the log reports, under the current filters. */
const panelStats = computed(() => ({ ...summary.value, trades: visible.value.length }))

const sideOptions = computed(() => [
  { value: 'all', label: t('history.all') },
  { value: 'long', label: t('side.long'), tone: 'long' as const },
  { value: 'short', label: t('side.short'), tone: 'short' as const },
])

function toggle(id: number) {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expanded.value = next
}

function legsOf(trade: Trade) {
  return accountFilter.value === null
    ? trade.legs
    : trade.legs.filter((leg) => leg.account === accountFilter.value)
}

function tradePnl(trade: Trade) {
  return legsOf(trade).reduce((sum, leg) => sum + Number(leg.pnl ?? 0), 0)
}
</script>

<template>
  <div class="max-w-[100rem] mx-auto p-3 sm:p-4 lg:p-6 space-y-3 sm:space-y-4">
    <div class="flex flex-wrap items-center gap-3">
      <div class="min-w-0">
        <h1 class="display text-xl sm:text-2xl">{{ t('history.title') }}</h1>
        <p class="text-xs text-ink-muted mt-1">{{ t('history.subtitle') }}</p>
      </div>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
      <UiStat
        :label="t('history.stat.pnl')"
        :value="`${summary.pnl >= 0 ? '+' : ''}$${money(summary.pnl)}`"
        :sub="t('history.stat.pnlSub', { n: summary.legs })"
        :tone="summary.pnl === 0 ? 'default' : summary.pnl > 0 ? 'long' : 'short'"
        icon="wallet"
        :loading="loading"
      />
      <UiStat
        :label="t('history.stat.trades')"
        :value="visible.length"
        :sub="t('history.stat.tradesSub', { n: summary.failed })"
        icon="history"
        :loading="loading"
      />
      <UiStat
        :label="t('history.stat.winRate')"
        :value="summary.scored ? `${Math.round((summary.wins / summary.scored) * 100)}%` : '—'"
        :sub="t('history.stat.winRateSub', { wins: summary.wins, n: summary.scored })"
        icon="check"
        :loading="loading"
      />
      <UiStat
        :label="t('history.stat.breaches')"
        :value="summary.breaches"
        :sub="t('history.stat.breachesSub')"
        :tone="summary.breaches ? 'signal' : 'ok'"
        icon="bolt"
        :loading="loading"
      />
    </div>

    <!-- Filters in one row above the log. -->
    <div class="flex flex-wrap items-center gap-2">
      <select
        v-model="accountFilter"
        class="field w-auto min-w-[12rem] text-xs py-1.5"
        :aria-label="t('history.filterAccount')"
      >
        <option :value="null">{{ t('history.allAccounts') }}</option>
        <option v-for="account in accounts.items" :key="account.id" :value="account.id">
          {{ account.label }} — {{ account.exchange_label }}
        </option>
      </select>

      <UiSegmented v-model="sideFilter" :options="sideOptions" size="sm" :block="false" />

      <button class="btn-ghost btn-sm ms-auto" :disabled="loading" @click="load">
        <UiIcon name="refresh" :size="14" :class="loading ? 'animate-spin' : ''" />
        <span class="hidden xs:inline">{{ t('common.reload') }}</span>
      </button>
    </div>

    <!-- Narrowed to one account, the next question is about the account. -->
    <HistoryAccountPanel
      v-if="accountFilter !== null"
      :key="accountFilter"
      :account-id="accountFilter"
      :stats="panelStats"
    />

    <p v-if="error" class="alert p-3 text-xs">{{ error }}</p>

    <div v-if="loading" class="space-y-3">
      <div v-for="i in 3" :key="i" class="skeleton h-20 rounded-panel" />
    </div>

    <UiCard v-else-if="visible.length" flush>
      <ul class="divide-y divide-line">
        <li v-for="trade in visible" :key="trade.id">
          <button
            class="w-full text-start px-4 py-3 flex flex-wrap items-center gap-x-4 gap-y-2
                   hover:bg-raised/60 transition-colors"
            :aria-expanded="expanded.has(trade.id)"
            @click="toggle(trade.id)"
          >
            <UiIcon
              name="chevronRight"
              :size="14"
              class="text-ink-faint transition-transform flip-rtl"
              :class="expanded.has(trade.id) ? 'rotate-90' : ''"
            />
            <span class="num text-sm font-medium">{{ trade.symbol }}</span>
            <UiBadge :tone="trade.side === 'long' ? 'long' : 'short'">
              {{ t(`side.${trade.side}`) }} {{ trade.leverage }}x
            </UiBadge>
            <UiBadge v-if="trade.status === 'open'" tone="brand" dot>
              {{ t('history.open') }}
            </UiBadge>

            <span class="text-xs text-ink-muted hidden sm:inline">
              {{ t('dashboard.legsFilled', {
                filled: legsOf(trade).filter((l) => l.ok).length,
                total: legsOf(trade).length,
              }) }}
            </span>

            <span class="num text-xs text-ink-faint ms-auto">{{ dateTime(trade.opened_at) }}</span>

            <span
              class="num text-xs"
              :class="
                (trade.fanout_ms ?? 0) > trading.fanoutBudgetMs ? 'text-signal' : 'text-ink-muted'
              "
            >
              {{ ms(trade.fanout_ms) }}
            </span>

            <span
              class="num text-sm w-24 text-end"
              :class="
                tradePnl(trade) === 0
                  ? 'text-ink-faint'
                  : tradePnl(trade) > 0
                    ? 'text-long'
                    : 'text-short'
              "
            >
              {{ tradePnl(trade) === 0 ? '—' : `${tradePnl(trade) > 0 ? '+' : ''}$${money(tradePnl(trade))}` }}
            </span>
          </button>

          <!-- Legs -->
          <div v-if="expanded.has(trade.id)" class="bg-sunken/60 border-t border-line">
            <div class="hidden sm:block overflow-x-auto">
              <table class="w-full text-xs">
                <thead>
                  <tr class="border-b border-line">
                    <th class="label text-start font-normal px-4 py-2">{{ t('dashboard.account') }}</th>
                    <th class="label text-start font-normal py-2">{{ t('dashboard.exchange') }}</th>
                    <th class="label text-end font-normal py-2">{{ t('dashboard.qty') }}</th>
                    <th class="label text-end font-normal py-2">{{ t('dashboard.entry') }}</th>
                    <th class="label text-end font-normal py-2">{{ t('history.exit') }}</th>
                    <th class="label text-end font-normal py-2">{{ t('history.pnl') }}</th>
                    <th class="label text-start font-normal px-4 py-2">{{ t('history.note') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="leg in legsOf(trade)" :key="leg.id" class="border-b border-line/50 last:border-0">
                    <td class="px-4 py-2">{{ leg.account_label }}</td>
                    <td class="text-ink-muted py-2">{{ leg.exchange }}</td>
                    <td class="num text-end py-2">{{ qty(leg.qty) }}</td>
                    <td class="num text-end py-2">{{ money(leg.entry_price) }}</td>
                    <td class="num text-end py-2">{{ money(leg.exit_price) }}</td>
                    <td
                      class="num text-end py-2"
                      :class="Number(leg.pnl ?? 0) >= 0 ? 'text-long' : 'text-short'"
                    >
                      {{ leg.pnl === null ? '—' : money(leg.pnl) }}
                    </td>
                    <td class="px-4 py-2">
                      <span v-if="!leg.ok" class="text-short">{{ leg.error }}</span>
                      <span v-else-if="!leg.sltp_attached" class="text-signal">
                        {{ t('history.unprotected') }}
                      </span>
                      <span v-else class="text-ink-faint">{{ ms(leg.dispatch_ms) }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <ul class="sm:hidden divide-y divide-line">
              <li v-for="leg in legsOf(trade)" :key="leg.id" class="px-4 py-3 space-y-1">
                <div class="flex items-baseline justify-between gap-2">
                  <span class="text-xs">{{ leg.account_label }}</span>
                  <span
                    class="num text-xs"
                    :class="Number(leg.pnl ?? 0) >= 0 ? 'text-long' : 'text-short'"
                  >
                    {{ leg.pnl === null ? '—' : money(leg.pnl) }}
                  </span>
                </div>
                <p class="num text-[0.65rem] text-ink-faint">
                  {{ qty(leg.qty) }} @ {{ money(leg.entry_price) }}
                  <template v-if="leg.exit_price"> → {{ money(leg.exit_price) }}</template>
                </p>
                <p v-if="!leg.ok" class="text-[0.65rem] text-short">{{ leg.error }}</p>
                <p v-else-if="!leg.sltp_attached" class="text-[0.65rem] text-signal">
                  {{ t('history.unprotected') }}
                </p>
              </li>
            </ul>
          </div>
        </li>
      </ul>
    </UiCard>

    <UiCard v-else>
      <UiEmpty
        icon="history"
        :title="t('history.empty')"
        :body="trades.length ? t('history.emptyFilter') : t('history.emptyBody')"
      />
    </UiCard>
  </div>
</template>
