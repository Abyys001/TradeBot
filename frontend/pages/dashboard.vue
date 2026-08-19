<script setup lang="ts">
/**
 * The command centre.
 *
 * Reading order is deliberate and matches how the admin actually opens this
 * page: *is anything wrong* first, then *what is running*, then the numbers
 * that explain both. Charts sit below the fold on a phone because none of them
 * answers a question you need in the first two seconds.
 *
 * Nothing here is synthetic. Every figure comes from the accounts and trades
 * endpoints; where there is no data yet the panel says so rather than drawing a
 * plausible-looking line.
 */
const { t } = useI18n()
const localePath = useLocalePath()
const accounts = useAccountsStore()
const trading = useTradingStore()
const positions = usePositionsStore()
const live = useLiveStore()
const { money, compact, ms, since } = useFormat()

useHead({ title: t('nav.dashboard') })

onMounted(() => {
  accounts.ensure()
  trading.ensureTrades()
  // An open position's PnL moves with the market, so it is polled while this
  // page is on screen and stopped when it is not — a number that silently
  // stopped updating is worse than no number.
  positions.start()
})

onBeforeUnmount(() => positions.stop())

// --- KPI row --------------------------------------------------------------

const openTrade = computed(() => trading.openTrade)

const lastFanout = computed(() => {
  const value = trading.lastFanoutMs ?? trading.latest?.fanout_ms ?? null
  return value === null ? null : { ms: value, over: value > trading.fanoutBudgetMs }
})

// --- capital allocation ---------------------------------------------------

const capitalRows = computed<BarRow[]>(() =>
  accounts.byCapital.map((account) => ({
    key: account.id,
    label: account.label,
    value: Number(account.last_balance ?? 0),
    display: account.last_balance
      ? `${money(account.last_balance)} ${account.last_balance_asset}`
      : t('dashboard.noBalance'),
    sub:
      account.status !== 'active'
        ? t(`accounts.state.${account.status}`)
        : !account.balance_is_usdt && account.last_balance_asset
          ? t('dashboard.notUsdt')
          : undefined,
    // Amber is the failure colour, so it marks the rows that cannot trade —
    // never the merely small ones.
    tone:
      account.status !== 'active' || (!account.balance_is_usdt && account.last_balance_asset)
        ? 'signal'
        : 'default',
  })),
)

// --- fan-out latency ------------------------------------------------------

const fanoutPoints = computed<ColumnPoint[]>(() =>
  trading.fanoutSeries.map((point) => ({
    key: point.id,
    value: Math.round(point.ms),
    label: point.symbol,
    meta: new Date(point.at).toLocaleString('en-US', {
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }),
    over: point.ms > trading.fanoutBudgetMs,
  })),
)

const worstFanout = computed(() =>
  fanoutPoints.value.length ? Math.max(...fanoutPoints.value.map((p) => p.value)) : null,
)

// --- realised result ------------------------------------------------------

/**
 * Cumulative realised PnL over closed legs, oldest first. Open legs are
 * excluded on purpose: an unrealised number that moves with the market does not
 * belong on the same line as banked results.
 */
const pnlSeries = computed(() => {
  const closed = trading.legs
    .filter((leg) => leg.closed_at && leg.pnl !== null)
    .sort((a, b) => String(a.closed_at).localeCompare(String(b.closed_at)))
  let running = 0
  return closed.map((leg) => {
    running += Number(leg.pnl ?? 0)
    return {
      label: `${leg.trade.symbol} · ${leg.account_label}`,
      value: running,
      meta: leg.closed_at ? new Date(leg.closed_at).toISOString().slice(0, 16).replace('T', ' ') : '',
    }
  })
})
</script>

<template>
  <div class="max-w-[100rem] mx-auto p-3 sm:p-4 lg:p-6 space-y-3 sm:space-y-4">
    <!-- Page header -->
    <div class="flex flex-wrap items-center gap-3">
      <div class="min-w-0">
        <h1 class="display text-xl sm:text-2xl">{{ t('dashboard.title') }}</h1>
        <p class="text-xs text-ink-muted mt-1">
          {{
            accounts.loadedAt
              ? t('dashboard.updated', { when: since(new Date(accounts.loadedAt).toISOString()) })
              : t('common.loading')
          }}
        </p>
      </div>

      <div class="ms-auto flex items-center gap-2">
        <button
          class="btn-ghost btn-sm"
          :disabled="accounts.refreshing"
          @click="accounts.refresh()"
        >
          <UiIcon name="refresh" :size="14" :class="accounts.refreshing ? 'animate-spin' : ''" />
          <span class="hidden xs:inline">
            {{ accounts.refreshing ? t('accounts.refreshing') : t('accounts.refresh') }}
          </span>
        </button>
        <NuxtLink :to="localePath('/chart')" class="btn-brand btn-sm">
          <UiIcon name="bolt" :size="14" />
          {{ t('dashboard.trade') }}
        </NuxtLink>
      </div>
    </div>

    <!-- KPIs -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
      <UiStat
        :label="t('dashboard.kpi.capital')"
        :value="`$${compact(accounts.totalUsdt)}`"
        :sub="t('dashboard.kpi.capitalSub', { n: accounts.tradeable.length })"
        icon="wallet"
        :loading="accounts.initial"
        :to="localePath('/accounts')"
      />
      <UiStat
        :label="t('dashboard.kpi.accounts')"
        :value="`${accounts.active.length}/${accounts.items.length}`"
        :sub="t('dashboard.kpi.accountsSub', { n: accounts.exchangeCount })"
        icon="accounts"
        :tone="accounts.failing.length ? 'signal' : 'default'"
        :loading="accounts.initial"
        :to="localePath('/accounts')"
      />
      <UiStat
        :label="t('dashboard.kpi.position')"
        :value="openTrade ? openTrade.symbol : t('dashboard.kpi.flat')"
        :sub="
          openTrade
            ? `${t(`side.${openTrade.side}`)} · ${openTrade.leverage}x · ${
                positions.pnl === null
                  ? `${openTrade.legs.filter((l) => l.ok).length} ${t('dashboard.kpi.legs')}`
                  : `${positions.pnl >= 0 ? '+' : ''}$${money(positions.pnl)}`
              }`
            : t('dashboard.kpi.flatSub')
        "
        :tone="
          openTrade
            ? positions.pnl === null
              ? openTrade.side === 'long'
                ? 'long'
                : 'short'
              : positions.pnl >= 0
                ? 'long'
                : 'short'
            : 'default'
        "
        icon="terminal"
        :loading="!trading.tradesLoaded"
        :to="localePath('/chart')"
      />
      <UiStat
        :label="t('dashboard.kpi.fanout')"
        :value="lastFanout ? ms(lastFanout.ms) : '—'"
        :sub="
          lastFanout
            ? lastFanout.over
              ? t('dashboard.kpi.overBudget')
              : t('dashboard.kpi.withinBudget')
            : t('dashboard.kpi.noTrades')
        "
        :tone="lastFanout ? (lastFanout.over ? 'signal' : 'ok') : 'default'"
        icon="bolt"
        :loading="!trading.tradesLoaded"
      />
    </div>

    <!-- What needs you -->
    <DashboardAlerts />

    <!-- Running state -->
    <DashboardOpenPosition />

    <!-- Markets: the same list as the chart rail, with room to edit. -->
    <UiCard flush class="min-h-0">
      <MarketWatchlist variant="full" />
    </UiCard>

    <!-- Numbers behind it -->
    <div class="grid gap-3 sm:gap-4 lg:grid-cols-3">
      <UiCard
        :title="t('dashboard.capital')"
        :hint="t('dashboard.capitalHint')"
        class="lg:col-span-1"
      >
        <div v-if="accounts.initial" class="space-y-3">
          <div v-for="i in 4" :key="i" class="skeleton h-8" />
        </div>
        <UiBarSeries v-else-if="capitalRows.length" :rows="capitalRows" />
        <UiEmpty
          v-else
          icon="wallet"
          :title="t('dashboard.noAccountsTitle')"
          :body="t('dashboard.noAccountsBody')"
        >
          <NuxtLink :to="localePath('/accounts')" class="btn-brand btn-sm">
            {{ t('accounts.connect') }}
          </NuxtLink>
        </UiEmpty>
      </UiCard>

      <UiCard
        :title="t('dashboard.latency')"
        :hint="t('dashboard.latencyHint')"
        class="lg:col-span-2"
      >
        <template #actions>
          <UiBadge v-if="trading.budgetBreaches" tone="signal">
            {{ t('dashboard.breaches', { n: trading.budgetBreaches }) }}
          </UiBadge>
          <UiBadge v-else-if="worstFanout !== null" tone="ok">
            {{ t('dashboard.worst', { ms: worstFanout }) }}
          </UiBadge>
        </template>

        <UiColumnChart
          v-if="fanoutPoints.length"
          :points="fanoutPoints"
          :reference="trading.fanoutBudgetMs"
          :reference-label="t('dashboard.budget', { s: trading.fanoutBudgetMs / 1000 })"
          :height="150"
        >
          <template #caption>{{ t('dashboard.latencyCaption') }}</template>
        </UiColumnChart>
        <UiEmpty
          v-else
          icon="bolt"
          :title="t('dashboard.noLatencyTitle')"
          :body="t('dashboard.noLatencyBody')"
        />
      </UiCard>
    </div>

    <div class="grid gap-3 sm:gap-4 lg:grid-cols-3">
      <DashboardRecentTrades class="lg:col-span-2" />

      <UiCard :title="t('dashboard.realised')" :hint="t('dashboard.realisedHint')">
        <template v-if="pnlSeries.length">
          <p
            class="num text-stat mb-2"
            :class="trading.realisedPnl >= 0 ? 'text-long' : 'text-short'"
          >
            {{ trading.realisedPnl >= 0 ? '+' : '' }}${{ money(trading.realisedPnl) }}
          </p>
          <UiTrendChart
            :points="pnlSeries"
            :height="110"
            :format="(n: number) => `${n >= 0 ? '+' : ''}$${money(n)}`"
          />
        </template>
        <UiEmpty
          v-else
          icon="history"
          :title="t('dashboard.noPnlTitle')"
          :body="t('dashboard.noPnlBody')"
        />
      </UiCard>
    </div>

    <!-- The live channel is what makes every number above trustworthy; when it
         drops, say so here rather than letting stale figures pass as fresh. -->
    <p v-if="live.status === 'offline'" class="alert p-3 text-xs flex items-center gap-2">
      <UiIcon name="alert" :size="14" />
      {{ t('dashboard.socketOffline') }}
    </p>
  </div>
</template>
