<script setup lang="ts">
/**
 * Everything about the account whose history is on screen.
 *
 * Spec §8 asks for a *per-account* trade log, and the moment the filter narrows
 * to one account the next question is always about that account rather than
 * about the list: what is it, where is it connected, is it still trading, and
 * how does the PnL below compare with what was put into it. The trade rows
 * cannot answer any of those, so they get their own panel above them.
 *
 * The money figures are the ledger's, fetched from the server and not
 * recomputed here — the same numbers the finance page shows, so the two pages
 * can never disagree about one account.
 */
const props = defineProps<{
  accountId: number
  /** Computed by the page from the trades it already has, under its filters. */
  stats: {
    trades: number
    legs: number
    settled: number
    failed: number
    wins: number
    scored: number
    pnl: number
    margin: number
  }
}>()

const { t } = useI18n()
const api = useApi()
const localePath = useLocalePath()
const accounts = useAccountsStore()
const { money, pct, dateTime, since } = useFormat()

const row = ref<LedgerRow | null>(null)
const loading = ref(true)

const account = computed(() => accounts.items.find((a) => a.id === props.accountId) ?? null)

async function load() {
  loading.value = true
  try {
    const snapshot = await api.ledger()
    row.value = snapshot.accounts.find((r) => r.account === props.accountId) ?? null
  } catch {
    // The trade log is the page; a ledger that will not answer costs the money
    // strip, not the page. It says so by rendering "—" rather than a zero.
    row.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.accountId, load)

const pnlTone = computed(() => {
  const value = Number(row.value?.pnl ?? 0)
  if (row.value?.pnl == null || value === 0) return 'text-ink'
  return value > 0 ? 'text-long' : 'text-short'
})

function pnlText(value: string | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const n = Number(value)
  return `${n > 0 ? '+' : n < 0 ? '−' : ''}$${money(Math.abs(n))}`
}

const winRate = computed(() =>
  props.stats.scored ? `${Math.round((props.stats.wins / props.stats.scored) * 100)}%` : '—',
)

/** Return on the margin this account committed to the trades in view. */
const realisedPct = computed(() =>
  props.stats.settled && props.stats.margin > 0
    ? (props.stats.pnl / props.stats.margin) * 100
    : null,
)
</script>

<template>
  <UiCard v-if="account" :tone="account.status === 'active' ? 'default' : 'signal'">
    <template #header>
      <div class="flex flex-wrap items-center gap-2 min-w-0">
        <h2 class="text-sm font-medium truncate">{{ account.label }}</h2>
        <UiBadge tone="neutral">{{ account.exchange_label }}</UiBadge>
        <UiBadge :tone="account.status === 'active' ? 'ok' : 'signal'" dot>
          {{ t(`accounts.state.${account.status}`) }}
        </UiBadge>
        <UiBadge v-if="account.testnet" tone="brand">{{ t('accounts.testnet') }}</UiBadge>
        <UiBadge v-if="account.hidden" tone="brand">{{ t('accounts.hidden') }}</UiBadge>
      </div>
    </template>

    <template #actions>
      <NuxtLink :to="localePath('/accounts')" class="btn-quiet btn-sm">
        {{ t('history.account.manage') }}
      </NuxtLink>
    </template>

    <dl class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 text-sm">
      <div>
        <dt class="label">{{ t('history.account.balance') }}</dt>
        <dd class="num mt-1">
          {{ account.last_balance === null ? '—' : money(account.last_balance) }}
          <span class="text-ink-faint text-xs">{{ account.last_balance_asset }}</span>
        </dd>
        <dd v-if="account.last_balance_at" class="text-[0.65rem] text-ink-faint mt-0.5">
          {{ since(account.last_balance_at) }}
        </dd>
      </div>
      <div>
        <dt class="label">{{ t('history.account.invested') }}</dt>
        <dd class="num mt-1">
          <span v-if="loading" class="skeleton inline-block h-4 w-16 align-middle" />
          <template v-else>{{ row ? `$${money(row.net_invested)}` : '—' }}</template>
        </dd>
      </div>
      <div>
        <dt class="label">{{ t('history.account.sinceInception') }}</dt>
        <dd class="num mt-1" :class="pnlTone">
          <span v-if="loading" class="skeleton inline-block h-4 w-16 align-middle" />
          <template v-else>{{ pnlText(row?.pnl) }}</template>
        </dd>
        <dd v-if="row?.pnl_pct" class="text-[0.65rem] text-ink-faint mt-0.5 num">
          {{ pct(row.pnl_pct) }}
        </dd>
      </div>
      <div>
        <dt class="label">{{ t('history.account.realised') }}</dt>
        <dd
          class="num mt-1"
          :class="
            !stats.settled || stats.pnl === 0
              ? 'text-ink'
              : stats.pnl > 0
                ? 'text-long'
                : 'text-short'
          "
        >
          {{ stats.settled ? pnlText(String(stats.pnl)) : '—' }}
          <span v-if="realisedPct !== null" class="text-xs">
            ({{ realisedPct > 0 ? '+' : '' }}{{ realisedPct.toFixed(2) }}%)
          </span>
        </dd>
        <dd class="text-[0.65rem] text-ink-faint mt-0.5">
          {{ t('history.account.legsCounted', { n: stats.settled, total: stats.legs }) }}
        </dd>
      </div>
      <div>
        <dt class="label">{{ t('history.stat.winRate') }}</dt>
        <dd class="num mt-1">{{ winRate }}</dd>
        <dd class="text-[0.65rem] text-ink-faint mt-0.5">
          {{
            stats.scored
              ? t('history.stat.winRateSub', { wins: stats.wins, n: stats.scored })
              : t('history.stat.winRateNone')
          }}
        </dd>
      </div>
      <div>
        <dt class="label">{{ t('history.account.failed') }}</dt>
        <dd class="num mt-1" :class="stats.failed ? 'text-short' : 'text-ink'">
          {{ stats.failed }}
        </dd>
        <dd class="text-[0.65rem] text-ink-faint mt-0.5">
          {{ t('history.account.ofTrades', { n: stats.trades }) }}
        </dd>
      </div>
    </dl>

    <!-- A key that has never been checked cannot route orders (spec §7), and
         this is the page where an account's silence gets noticed. -->
    <p v-if="account.last_error" class="alert p-2.5 text-xs mt-3">
      {{ account.last_error }}
    </p>
    <p v-else-if="!account.withdrawal_checked_at" class="alert p-2.5 text-xs mt-3">
      {{ t('history.account.unchecked') }}
    </p>
    <p v-else class="text-[0.65rem] text-ink-faint mt-3">
      {{ t('history.account.checkedAt', { when: dateTime(account.withdrawal_checked_at) }) }}
    </p>
  </UiCard>
</template>
