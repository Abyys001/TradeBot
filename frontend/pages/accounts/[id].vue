<script setup lang="ts">
/**
 * One connection, whole.
 *
 * The accounts list can only ever answer "is it connected and what is it worth
 * right now". Every other question an operator has about a partner's account —
 * when it joined, what was paid in, what came out, which legs it was actually
 * given and what each one returned — needs the account's own page, and needs
 * them side by side: a PnL figure without the deposits behind it is a number
 * nobody can act on.
 *
 * All of it arrives in one request (`/accounts/accounts/<id>/report/`). The
 * money is the ledger's own arithmetic, computed server-side in Decimal, so
 * this page and the finance page can never disagree about one account. Nothing
 * is recomputed in the browser.
 */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const api = useApi()
const accounts = useAccountsStore()
const { money, pct, dateTime, since } = useFormat()

const id = computed(() => Number(route.params.id))

const report = ref<AccountReport | null>(null)
const loading = ref(true)
const error = ref('')
const busy = ref(false)
const actionError = ref('')
const pendingDelete = ref(false)
const pendingStatement = ref(false)
const tab = ref<'overview' | 'trades' | 'cash' | 'activity'>('overview')

const account = computed(() => report.value?.account ?? null)
const ledger = computed(() => report.value?.ledger ?? null)

useHead({
  title: computed(() =>
    account.value
      ? `${account.value.label} — ${account.value.exchange_label}`
      : t('nav.accounts'),
  ),
})

async function load() {
  loading.value = true
  try {
    report.value = await api.accountReport(id.value)
    error.value = ''
  } catch (e: any) {
    // A 404 here is the visibility filter doing its job as much as it is a
    // wrong id, so the message stays the server's rather than being guessed at.
    error.value = errorMessage(e)
    report.value = null
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await Promise.all([accounts.ensure(), load()])
})
watch(id, load)

/** Every control on this page changes something the report already showed. */
async function run(fn: () => Promise<unknown>) {
  busy.value = true
  actionError.value = ''
  try {
    await fn()
    await load()
  } catch (e: any) {
    actionError.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}

const toggle = () =>
  account.value &&
  run(() => accounts.setPaused(account.value!, account.value!.status === 'active'))

const verify = () => account.value && run(() => accounts.verify(account.value!))

async function confirmDelete() {
  if (!account.value) return
  await run(() => accounts.remove(id.value))
  pendingDelete.value = false
  router.push(localePath('/accounts'))
}

const tabs = computed(() => [
  { value: 'overview', label: t('accounts.report.tab.overview') },
  {
    value: 'trades',
    label: `${t('accounts.report.tab.trades')} ${report.value?.trading.legs ?? 0}`,
  },
  {
    value: 'cash',
    label: `${t('accounts.report.tab.cash')} ${report.value?.movements.length ?? 0}`,
  },
  { value: 'activity', label: t('accounts.report.tab.activity') },
])

const STATUS_TONE = { active: 'ok', paused: 'signal', error: 'short' } as const

function pnlTone(value: string | number | null | undefined): 'default' | 'long' | 'short' {
  const n = Number(value)
  if (value === null || value === undefined || Number.isNaN(n) || n === 0) return 'default'
  return n > 0 ? 'long' : 'short'
}

const PNL_TEXT = { default: 'text-ink', long: 'text-long', short: 'text-short' } as const

/** "+$12.34" / "−$5.00" / "—". Unknown is an em dash, never a zero. */
function pnlText(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const n = Number(value)
  if (Number.isNaN(n)) return '—'
  return `${n > 0 ? '+' : n < 0 ? '−' : ''}$${money(Math.abs(n))}`
}

/** The realised curve, oldest first — the one series this page plots. */
const curve = computed(() =>
  (report.value?.curve ?? []).map((point) => ({
    label: dateTime(point.at),
    value: Number(point.cumulative),
    meta: `${point.symbol} · ${pnlText(point.pnl)}`,
  })),
)

/**
 * Where the money was made or lost. Bars are magnitudes, so a losing pair is
 * drawn by how much it lost and coloured as the problem it is.
 */
const symbolRows = computed<BarRow[]>(() =>
  (report.value?.symbols ?? []).map((row) => ({
    key: row.symbol,
    label: row.symbol,
    value: Math.abs(Number(row.pnl)),
    display: pnlText(row.pnl),
    sub: t('accounts.report.symbolSub', { legs: row.legs, wins: row.wins }),
    tone: Number(row.pnl) < 0 ? ('signal' as const) : ('default' as const),
  })),
)

const SPLIT_ROLES = ['investor', 'trader', 'programmer'] as const

/** Only what the §7 check can actually prove — see the note in CLAUDE.md. */
const checkText = computed(() => {
  const a = account.value
  if (!a) return ''
  if (!a.withdrawal_checked_at) return t('accounts.report.checkNever')
  return a.withdrawal_check_passed
    ? t('accounts.report.checkPassed', { when: dateTime(a.withdrawal_checked_at) })
    : t('accounts.report.checkUnprovable', { when: dateTime(a.withdrawal_checked_at) })
})
</script>

<template>
  <div class="max-w-[100rem] mx-auto p-3 sm:p-4 lg:p-6 space-y-3 sm:space-y-4">
    <!-- The way back is the first control on the page, not the browser's. A
         report opened from a link has no history to go back through. -->
    <NuxtLink :to="localePath('/accounts')" class="btn-quiet btn-sm -ms-2.5">
      <UiIcon name="arrowRight" :size="14" class="rotate-180 flip-rtl" />
      {{ t('accounts.report.back') }}
    </NuxtLink>

    <div v-if="loading && !report" class="space-y-3">
      <div class="skeleton h-16 rounded-panel" />
      <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div v-for="i in 5" :key="i" class="skeleton h-24 rounded-panel" />
      </div>
      <div class="skeleton h-64 rounded-panel" />
    </div>

    <UiCard v-else-if="error" tone="signal">
      <UiEmpty icon="alert" :title="t('accounts.report.unavailable')" :body="error">
        <NuxtLink :to="localePath('/accounts')" class="btn-ghost btn-sm">
          {{ t('accounts.report.back') }}
        </NuxtLink>
      </UiEmpty>
    </UiCard>

    <template v-else-if="report && account">
      <!-- Identity and the controls that change it, in one bar. -->
      <div class="flex flex-wrap items-start gap-3">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <h1 class="display text-xl sm:text-2xl truncate">{{ account.label }}</h1>
            <UiBadge :tone="STATUS_TONE[account.status]" dot>
              {{ t(`accounts.state.${account.status}`) }}
            </UiBadge>
            <UiBadge v-if="account.testnet" tone="brand">{{ t('accounts.testnet') }}</UiBadge>
            <UiBadge v-if="account.hidden" tone="signal">
              <UiIcon name="eyeOff" :size="12" />
              {{ t('accounts.hidden') }}
            </UiBadge>
          </div>
          <p class="text-xs text-ink-muted mt-1">
            {{ account.exchange_label }} ·
            {{ t('accounts.report.connectedAt', { when: dateTime(report.connected_at) }) }}
            <span class="text-ink-faint">({{ since(report.connected_at) }})</span>
          </p>
        </div>

        <div class="ms-auto flex flex-wrap items-center gap-2">
          <button class="btn-ghost btn-sm" :disabled="loading" @click="load">
            <UiIcon name="refresh" :size="14" :class="loading ? 'animate-spin' : ''" />
            <span class="hidden xs:inline">{{ t('common.reload') }}</span>
          </button>
          <button
            :class="account.status === 'active' ? 'btn-warn' : 'btn-ok'"
            class="btn-sm"
            :disabled="busy"
            @click="toggle"
          >
            <UiIcon
              :name="busy ? 'refresh' : account.status === 'active' ? 'pause' : 'play'"
              :size="13"
              :class="busy ? 'animate-spin' : ''"
            />
            {{ account.status === 'active' ? t('accounts.pause') : t('accounts.resume') }}
          </button>
          <button class="btn-info btn-sm" :disabled="busy" @click="verify">
            <UiIcon name="shield" :size="13" />
            <span class="hidden sm:inline">{{ t('accounts.verify') }}</span>
          </button>
          <!-- The one control here that produces something to hand to somebody
               else, so it asks for the period first rather than guessing. -->
          <button class="btn-brand btn-sm" @click="pendingStatement = true">
            <UiIcon name="download" :size="13" />
            <span class="hidden sm:inline">{{ t('accounts.statement.action') }}</span>
          </button>
          <button class="btn-danger btn-sm btn-icon" :aria-label="t('accounts.delete')" @click="pendingDelete = true">
            <UiIcon name="trash" :size="13" />
          </button>
        </div>
      </div>

      <p v-if="actionError" class="alert p-3 text-xs">{{ actionError }}</p>
      <p v-else-if="account.last_error" class="alert p-3 text-xs">{{ account.last_error }}</p>

      <!-- The five numbers the page exists to answer, before any table. -->
      <div class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3 sm:gap-4">
        <UiStat
          :label="t('accounts.report.stat.balance')"
          :value="account.last_balance === null ? '—' : `$${money(account.last_balance)}`"
          :sub="
            account.last_balance_at
              ? t('accounts.report.stat.balanceSub', { when: since(account.last_balance_at) })
              : t('accounts.neverFetched')
          "
          icon="wallet"
        />
        <UiStat
          :label="t('accounts.report.stat.invested')"
          :value="`$${money(ledger!.net_invested)}`"
          :sub="
            t('accounts.report.stat.investedSub', {
              in: money(ledger!.deposits),
              out: money(ledger!.withdrawals),
            })
          "
          icon="ledger"
        />
        <UiStat
          :label="t('accounts.report.stat.pnl')"
          :value="pnlText(ledger!.pnl)"
          :sub="ledger!.pnl_pct ? pct(ledger!.pnl_pct) : t('accounts.report.stat.pnlUnknown')"
          :tone="pnlTone(ledger!.pnl)"
          icon="trend"
        />
        <UiStat
          :label="t('accounts.report.stat.realised')"
          :value="pnlText(report.trading.realised_pnl)"
          :sub="t('accounts.report.stat.realisedSub', { n: report.trading.scored })"
          :tone="pnlTone(report.trading.realised_pnl)"
          icon="history"
        />
        <UiStat
          :label="t('history.stat.winRate')"
          :value="report.trading.win_rate ? `${Math.round(Number(report.trading.win_rate))}%` : '—'"
          :sub="
            t('history.stat.winRateSub', {
              wins: report.trading.wins,
              n: report.trading.scored,
            })
          "
          icon="check"
        />
      </div>

      <div class="overflow-x-auto no-scrollbar -my-1 py-1">
        <UiSegmented v-model="tab" :options="tabs" size="sm" :block="false" />
      </div>

      <!-- ── Overview ────────────────────────────────────────────────── -->
      <template v-if="tab === 'overview'">
        <div class="grid lg:grid-cols-3 gap-3 sm:gap-4">
          <UiCard
            class="lg:col-span-2"
            :title="t('accounts.report.curve')"
            :hint="t('accounts.report.curveHint')"
          >
            <UiTrendChart
              v-if="curve.length > 1"
              :points="curve"
              :format="(n: number) => pnlText(n)"
            />
            <UiEmpty
              v-else
              icon="trend"
              :title="t('accounts.report.noCurve')"
              :body="t('accounts.report.noCurveBody')"
            />

            <dl class="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm mt-4 pt-4 border-t border-line">
              <div>
                <dt class="label">{{ t('accounts.report.trading.best') }}</dt>
                <dd class="num mt-1 text-long">{{ pnlText(report.trading.best) }}</dd>
              </div>
              <div>
                <dt class="label">{{ t('accounts.report.trading.worst') }}</dt>
                <dd class="num mt-1 text-short">{{ pnlText(report.trading.worst) }}</dd>
              </div>
              <div>
                <dt class="label">{{ t('accounts.report.trading.average') }}</dt>
                <dd class="num mt-1" :class="PNL_TEXT[pnlTone(report.trading.average_pnl)]">
                  {{ pnlText(report.trading.average_pnl) }}
                </dd>
              </div>
              <div>
                <dt class="label">{{ t('accounts.report.trading.profitFactor') }}</dt>
                <dd class="num mt-1">
                  {{ report.trading.profit_factor ? Number(report.trading.profit_factor).toFixed(2) : '—' }}
                </dd>
                <dd class="text-[0.65rem] text-ink-faint mt-0.5">
                  {{ t('accounts.report.trading.profitFactorSub') }}
                </dd>
              </div>
            </dl>
          </UiCard>

          <UiCard :title="t('accounts.report.connection')">
            <dl class="space-y-3 text-sm">
              <div class="flex items-baseline gap-3">
                <dt class="label shrink-0 w-32">{{ t('accounts.exchange') }}</dt>
                <dd class="min-w-0 truncate">{{ account.exchange_label }}</dd>
              </div>
              <div class="flex items-baseline gap-3">
                <dt class="label shrink-0 w-32">{{ t('accounts.report.connected') }}</dt>
                <dd class="min-w-0 num">{{ dateTime(report.connected_at) }}</dd>
              </div>
              <!-- Spec §6: a resumed account rejoins from the next trade, so
                   this moves forward while the connection date does not. -->
              <div class="flex items-baseline gap-3">
                <dt class="label shrink-0 w-32">{{ t('accounts.report.eligible') }}</dt>
                <dd class="min-w-0 num">{{ dateTime(report.eligible_from) }}</dd>
              </div>
              <div v-if="account.key_fingerprint" class="flex items-baseline gap-3">
                <dt class="label shrink-0 w-32">{{ t('accounts.report.fingerprint') }}</dt>
                <!-- A fingerprint of the key, never the key: the server does
                     not send credentials at all (spec §7). -->
                <dd class="min-w-0 num truncate">{{ account.key_fingerprint }}</dd>
              </div>
              <div v-if="account.wallet_address" class="flex items-baseline gap-3">
                <dt class="label shrink-0 w-32">{{ t('accounts.masterAddress') }}</dt>
                <dd class="min-w-0 num truncate">{{ account.wallet_address }}</dd>
              </div>
              <div v-if="account.credential_expires_at" class="flex items-baseline gap-3">
                <dt class="label shrink-0 w-32">{{ t('accounts.report.expires') }}</dt>
                <!-- The date alone is not a warning. An agent approval is
                     pruned at expiry with no error from the exchange, so the
                     countdown beside it is what says the account is about to
                     stop trading in silence (spec §7). -->
                <dd class="min-w-0 num flex items-center gap-2">
                  {{ dateTime(account.credential_expires_at) }}
                  <UiBadge
                    v-if="account.credential_state"
                    :tone="account.credential_state === 'expired' ? 'short' : 'signal'"
                  >
                    {{
                      (account.credential_days_left ?? 0) < 0
                        ? t('accounts.expiry.expired', { n: Math.abs(account.credential_days_left ?? 0) })
                        : t('accounts.expiry.days', { n: account.credential_days_left ?? 0 })
                    }}
                  </UiBadge>
                </dd>
              </div>
              <div class="flex items-baseline gap-3">
                <dt class="label shrink-0 w-32">{{ t('accounts.report.asset') }}</dt>
                <dd class="min-w-0">
                  {{ account.last_balance_asset || '—' }}
                  <UiBadge v-if="account.last_balance_asset && !account.balance_is_usdt" tone="signal">
                    {{ t('accounts.stat.nonUsdtSub') }}
                  </UiBadge>
                </dd>
              </div>
            </dl>

            <p class="text-xs text-ink-muted mt-4 pt-3 border-t border-line leading-relaxed">
              <UiIcon name="shield" :size="13" class="inline align-[-2px] me-1" />
              {{ checkText }}
            </p>
          </UiCard>
        </div>

        <div class="grid lg:grid-cols-2 gap-3 sm:gap-4">
          <UiCard :title="t('accounts.report.bySymbol')" :hint="t('accounts.report.bySymbolHint')">
            <UiBarSeries v-if="symbolRows.length" :rows="symbolRows" />
            <UiEmpty v-else icon="chart" :title="t('accounts.report.noTrades')" />
          </UiCard>

          <UiCard :title="t('accounts.report.execution')" :hint="t('accounts.report.executionHint')">
            <dl class="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
              <div>
                <dt class="label">{{ t('accounts.report.trading.legs') }}</dt>
                <dd class="num mt-1">{{ report.trading.legs }}</dd>
              </div>
              <div>
                <dt class="label">{{ t('accounts.report.trading.filled') }}</dt>
                <dd class="num mt-1">{{ report.trading.filled }}</dd>
              </div>
              <div>
                <dt class="label">{{ t('accounts.report.trading.failed') }}</dt>
                <dd class="num mt-1" :class="report.trading.failed ? 'text-short' : 'text-ink'">
                  {{ report.trading.failed }}
                </dd>
              </div>
              <div>
                <dt class="label">{{ t('accounts.report.trading.open') }}</dt>
                <dd class="num mt-1">{{ report.trading.open }}</dd>
              </div>
              <div>
                <dt class="label">{{ t('accounts.report.trading.volume') }}</dt>
                <dd class="num mt-1">${{ money(report.trading.volume) }}</dd>
              </div>
              <div>
                <dt class="label">{{ t('accounts.report.trading.last') }}</dt>
                <dd class="num mt-1 text-xs">
                  {{ report.trading.last_trade_at ? since(report.trading.last_trade_at) : '—' }}
                </dd>
              </div>
            </dl>

            <!-- Profit-only, by the global split. A loss has nothing to divide,
                 which is why these read zero rather than negative. -->
            <div class="mt-4 pt-4 border-t border-line">
              <p class="label mb-3">{{ t('accounts.report.shares') }}</p>
              <ul class="space-y-2 text-sm">
                <li v-for="role in SPLIT_ROLES" :key="role" class="flex items-baseline gap-3">
                  <span class="text-ink-muted">{{ t(`finance.role.${role}`) }}</span>
                  <span class="text-xs text-ink-faint num">{{ money(report.split[role], 0) }}%</span>
                  <span class="num ms-auto">${{ money(ledger!.shares[role]) }}</span>
                </li>
              </ul>
            </div>
          </UiCard>
        </div>
      </template>

      <!-- ── Trades ─────────────────────────────────────────────────── -->
      <AccountsReportLegs v-else-if="tab === 'trades'" :report="report" />

      <!-- ── Cash flow ──────────────────────────────────────────────── -->
      <AccountsReportCash v-else-if="tab === 'cash'" :report="report" />

      <!-- ── Activity ───────────────────────────────────────────────── -->
      <AccountsReportActivity v-else :report="report" />
    </template>

    <AccountsStatementDialog
      v-if="account"
      v-model="pendingStatement"
      :account-id="id"
      :label="account.label"
      :connected-at="report!.connected_at"
    />

    <UiModal
      :model-value="pendingDelete"
      :title="t('accounts.deleteTitle')"
      size="sm"
      @update:model-value="pendingDelete = false"
    >
      <p class="text-sm leading-relaxed">
        {{ t('accounts.confirmDelete', { label: account?.label ?? '' }) }}
      </p>
      <template #footer>
        <div class="flex gap-2 justify-end">
          <button class="btn-ghost" @click="pendingDelete = false">{{ t('common.cancel') }}</button>
          <button class="btn-danger" :disabled="busy" @click="confirmDelete">
            {{ t('accounts.delete') }}
          </button>
        </div>
      </template>
    </UiModal>
  </div>
</template>
