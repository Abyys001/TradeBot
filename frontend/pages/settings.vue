<script setup lang="ts">
/**
 * Settings — what is in force, and the one control that is genuinely live.
 *
 * The page is organised by *what the admin can do about it*, not by where the
 * value happens to be stored:
 *
 *   1. Emergency halt — the only thing here that changes platform behaviour
 *      from a browser. It leads, because when it is wanted it is wanted fast.
 *   2. Execution & risk policy — read-only. These are `.env` values; a UI that
 *      appeared to change them without changing the deployment would be lying.
 *      Each row names the question in `questions.md` it answers, so the screen
 *      and the decision record stay tied together.
 *   3. Connection & data — what the panel is actually talking to right now:
 *      socket state, round-trip latency, and whether prices are a real feed.
 *   4. Exchange coverage — per-adapter capabilities, testnet honesty (Q9).
 *   5. Preferences — theme and language, which are this browser's business.
 *
 * The previous version was one flat list of key/value rows with no grouping and
 * no live state at all, which is why it read as a dump rather than a page.
 */
const { t, te } = useI18n()
const api = useApi()
const trading = useTradingStore()
const live = useLiveStore()
const market = useMarketStore()
const { theme, isDark, toggle } = useTheme()
const { locale, locales, setLocale } = useI18n()

useHead({ title: t('nav.settings') })

const exchanges = ref<ExchangeInfo[]>([])
const loading = ref(true)
const confirmResume = ref(false)

onMounted(async () => {
  await trading.loadPolicy()
  // One quote, purely to show whether the price feed is real on this deployment.
  market.loadTicker()
  try {
    exchanges.value = (await api.exchanges()).exchanges
  } finally {
    loading.value = false
  }
})

const policy = computed(() => trading.policy)

/** Grouped so a reader can find "how big is a position" without scanning. */
const groups = computed(() => {
  const p = policy.value
  if (!p) return []
  return [
    {
      key: 'sizing',
      rows: [
        {
          key: 'balance_fraction',
          value: `${(Number(p.balance_fraction) * 100).toFixed(0)}%`,
          question: 'Q12',
          tone: 'brand' as const,
        },
        { key: 'leverage_range', value: `${p.leverage_range[0]}x – ${p.leverage_range[1]}x` },
      ],
    },
    {
      key: 'sltp',
      rows: [
        { key: 'sltp_basis', value: t(`risk.basis.${p.sltp_basis}`), question: 'Q5a' },
        { key: 'sltp_reference', value: p.sltp_reference, question: 'Q5b/Q5c' },
        { key: 'sltp_amend_strategy', value: p.sltp_amend_strategy, question: 'Q5d' },
        { key: 'sltp_failure_policy', value: p.sltp_failure_policy, question: 'Q5e' },
        {
          key: 'reject_sl_beyond_liquidation',
          value: p.reject_sl_beyond_liquidation ? t('common.on') : t('common.off'),
          tone: p.reject_sl_beyond_liquidation ? ('ok' as const) : ('signal' as const),
        },
      ],
    },
    {
      key: 'execution',
      rows: [{ key: 'fanout_timeout_seconds', value: `${p.fanout_timeout_seconds}s` }],
    },
  ]
})

const PING_TONE = { good: 'ok', fair: 'signal', poor: 'short' } as const

const socketReason = computed(() => {
  const key = `connection.down.${live.statusDetail}`
  return te(key) ? t(key) : live.statusDetail
})

const diagnostics = computed(() => [
  {
    key: 'socket',
    // Never the bare state. "Connecting" alone was the same word for a
    // handshake in flight, an upgrade the proxy never forwarded, and a session
    // the engine refused — three different fixes shown identically.
    value:
      live.status === 'live'
        ? t('common.live')
        : `${t(`common.${live.status}`)} · ${socketReason.value}`,
    tone: live.status === 'live' ? ('ok' as const) : ('signal' as const),
  },
  {
    key: 'latency',
    value: live.pingMedian === null ? '—' : `${live.pingMedian}ms`,
    tone: live.pingQuality ? PING_TONE[live.pingQuality] : ('neutral' as const),
  },
  {
    // The hop an order actually travels. Measured on real market-data calls,
    // blank when nothing has been measured recently — never a stand-in number.
    key: 'exchangeLatency',
    value:
      live.exchangeMs === null
        ? '—'
        : `${Math.round(live.exchangeMs)}ms${live.exchangeName ? ` · ${live.exchangeName}` : ''}`,
    tone: live.exchangeQuality ? PING_TONE[live.exchangeQuality] : ('neutral' as const),
  },
  {
    // Names the venue *and* how the prices arrive. Both are real exchange
    // data, but a streamed tick and a 15-second poll are different promises,
    // and this card exists to say which one is in force.
    key: 'feed',
    value: !market.live
      ? t('terminal.feedDown')
      : market.streaming
        ? `${market.streamSource || market.source} · ${t('terminal.streaming')}`
        : market.source || t('common.live'),
    tone: market.live ? ('ok' as const) : ('signal' as const),
  },
])
</script>

<template>
  <div class="max-w-5xl mx-auto p-3 sm:p-4 lg:p-6 space-y-4 sm:space-y-5">
    <header>
      <h1 class="display text-xl sm:text-2xl">{{ t('settings.title') }}</h1>
      <p class="text-xs text-ink-muted mt-1.5 max-w-2xl leading-relaxed">
        {{ t('settings.subtitle') }}
      </p>
    </header>

    <!-- 1. Spec §7 kill switch -->
    <section
      class="panel p-4 sm:p-5"
      :class="trading.halted ? 'border-signal/50 bg-signal-dim' : ''"
    >
      <div class="flex flex-wrap items-start gap-4">
        <span
          class="w-10 h-10 rounded-xl grid place-items-center shrink-0"
          :class="trading.halted ? 'bg-signal-dim text-signal' : 'bg-raised text-ink-faint'"
        >
          <UiIcon name="alert" :size="18" />
        </span>

        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 flex-wrap">
            <h2 class="text-sm font-medium" :class="trading.halted ? 'text-signal' : ''">
              {{ trading.halted ? t('settings.stopAllTitle') : t('settings.stopAllReadyTitle') }}
            </h2>
            <UiBadge :tone="trading.halted ? 'signal' : 'ok'" dot>
              {{ trading.halted ? t('policy.stopAllActive') : t('settings.routingLive') }}
            </UiBadge>
          </div>
          <p class="text-xs text-ink-muted mt-1.5 leading-relaxed max-w-2xl">
            {{ trading.halted ? t('settings.stopAllBody') : t('settings.stopAllReadyBody') }}
          </p>
          <p v-if="trading.halted && trading.haltLocked" class="text-xs text-signal mt-2">
            {{ t('policy.stopAllLocked') }}
          </p>
          <p v-else-if="trading.halted && trading.haltReason" class="text-xs text-ink-faint mt-2">
            {{ t('policy.haltedBecause', { reason: trading.haltReason }) }}
          </p>
        </div>

        <button
          class="btn-sm shrink-0 w-full sm:w-auto"
          :class="trading.halted ? 'btn-brand' : 'btn-danger'"
          :disabled="trading.haltPending || (trading.halted && trading.haltLocked)"
          @click="
            trading.halted ? (confirmResume = true) : trading.setHalt(true, 'halted from settings')
          "
        >
          {{ trading.halted ? t('policy.resume') : t('policy.stopAll') }}
        </button>
      </div>
    </section>

    <!-- 3. Live diagnostics, first because they change; the policy below does not. -->
    <UiCard :title="t('settings.connection')" :hint="t('settings.connectionHint')">
      <dl class="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div
          v-for="row in diagnostics"
          :key="row.key"
          class="rounded-lg border border-line bg-sunken px-3 py-2.5"
        >
          <dt class="label">{{ t(`settings.diag.${row.key}`) }}</dt>
          <dd class="mt-1.5 flex items-center gap-2">
            <UiBadge :tone="row.tone" dot>{{ row.value }}</UiBadge>
          </dd>
          <p class="text-[0.7rem] text-ink-faint mt-1.5 leading-relaxed">
            {{ t(`settings.diagHint.${row.key}`) }}
          </p>
        </div>
      </dl>
    </UiCard>

    <!-- 2. Policy, grouped -->
    <div v-if="!policy" class="panel p-4 space-y-2">
      <div v-for="i in 6" :key="i" class="skeleton h-10" />
    </div>

    <UiCard
      v-for="group in groups"
      v-else
      :key="group.key"
      :title="t(`settings.group.${group.key}`)"
      :hint="t(`settings.group.${group.key}Hint`)"
      flush
    >
      <template #actions>
        <UiBadge tone="neutral">{{ t('settings.readOnly') }}</UiBadge>
      </template>

      <ul class="divide-y divide-line">
        <li
          v-for="row in group.rows"
          :key="row.key"
          class="px-4 py-3 flex flex-wrap items-baseline gap-x-4 gap-y-1.5"
        >
          <div class="min-w-0 flex-1 basis-48">
            <p class="text-sm">{{ t(`settings.keys.${row.key}.label`) }}</p>
            <p class="text-xs text-ink-muted mt-0.5 leading-relaxed">
              {{ t(`settings.keys.${row.key}.hint`) }}
            </p>
          </div>
          <UiBadge v-if="row.question" tone="brand">{{ row.question }}</UiBadge>
          <UiBadge :tone="row.tone ?? 'neutral'" class="num">{{ row.value }}</UiBadge>
        </li>
      </ul>
    </UiCard>

    <!-- 4. Spec §9 / Q9: an exchange with no test environment is labelled, never
         given a testnet toggle that quietly trades real money. -->
    <UiCard :title="t('settings.exchanges')" :hint="t('settings.exchangesHint')" flush>
      <div v-if="loading" class="p-4 space-y-2">
        <div v-for="i in 5" :key="i" class="skeleton h-9" />
      </div>

      <template v-else>
        <!-- Table from md up, cards below: five columns on a phone is a
             horizontal scroll nobody performs. -->
        <div class="hidden md:block overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-line">
                <th class="label text-start font-normal px-4 py-2.5">{{ t('settings.exchange') }}</th>
                <th class="label text-start font-normal py-2.5">{{ t('settings.markets') }}</th>
                <th class="label text-start font-normal py-2.5">{{ t('settings.testnet') }}</th>
                <th class="label text-start font-normal px-4 py-2.5">
                  {{ t('settings.capabilities') }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="exchange in exchanges"
                :key="exchange.exchange"
                class="border-b border-line/60 last:border-0 hover:bg-raised/40 transition-colors"
              >
                <td class="px-4 py-3 font-medium whitespace-nowrap">{{ exchange.label }}</td>
                <td class="py-3 text-ink-muted whitespace-nowrap">
                  {{ exchange.markets.join(', ') || '—' }}
                </td>
                <td class="py-3">
                  <UiBadge :tone="exchange.has_testnet ? 'ok' : 'signal'" dot>
                    {{ exchange.has_testnet ? t('common.yes') : t('common.no') }}
                  </UiBadge>
                </td>
                <td class="px-4 py-3">
                  <div class="flex flex-wrap gap-1.5">
                    <UiBadge v-if="exchange.native_sltp_amend" tone="neutral">
                      {{ t('settings.nativeAmend') }}
                    </UiBadge>
                    <UiBadge v-if="exchange.wallet_based_auth" tone="neutral">
                      {{ t('settings.walletAuth') }}
                    </UiBadge>
                    <UiBadge v-if="exchange.per_key_rate_limits" tone="neutral">
                      {{ t('settings.perKeyLimits') }}
                    </UiBadge>
                    <span v-if="exchange.note" class="text-xs text-signal">{{ exchange.note }}</span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <ul class="md:hidden divide-y divide-line">
          <li v-for="exchange in exchanges" :key="exchange.exchange" class="p-4 space-y-2">
            <div class="flex items-center gap-2">
              <span class="font-medium text-sm">{{ exchange.label }}</span>
              <UiBadge :tone="exchange.has_testnet ? 'ok' : 'signal'" dot class="ms-auto">
                {{ exchange.has_testnet ? t('settings.testnet') : t('settings.noTestnet') }}
              </UiBadge>
            </div>
            <p class="text-xs text-ink-muted">{{ exchange.markets.join(', ') || '—' }}</p>
            <div class="flex flex-wrap gap-1.5">
              <UiBadge v-if="exchange.native_sltp_amend" tone="neutral">
                {{ t('settings.nativeAmend') }}
              </UiBadge>
              <UiBadge v-if="exchange.wallet_based_auth" tone="neutral">
                {{ t('settings.walletAuth') }}
              </UiBadge>
              <UiBadge v-if="exchange.per_key_rate_limits" tone="neutral">
                {{ t('settings.perKeyLimits') }}
              </UiBadge>
            </div>
            <p v-if="exchange.note" class="text-xs text-signal leading-relaxed">
              {{ exchange.note }}
            </p>
          </li>
        </ul>
      </template>
    </UiCard>

    <!-- 5. This browser's preferences -->
    <UiCard :title="t('settings.appearance')" :hint="t('settings.appearanceHint')">
      <div class="space-y-4">
        <UiSwitch
          :model-value="isDark"
          :label="t('settings.darkMode')"
          :hint="t('settings.darkModeHint')"
          @update:model-value="toggle()"
        />

        <div class="border-t border-line pt-4">
          <p class="text-sm">{{ t('settings.language') }}</p>
          <p class="text-xs text-ink-muted mt-0.5 leading-relaxed">
            {{ t('settings.languageHint') }}
          </p>
          <div class="flex gap-2 mt-2.5">
            <button
              v-for="option in locales"
              :key="(option as any).code"
              class="btn-sm"
              :class="locale === (option as any).code ? 'btn-brand' : 'btn-ghost'"
              @click="setLocale((option as any).code)"
            >
              {{ (option as any).name }}
            </button>
          </div>
        </div>
      </div>
      <p class="sr-only">{{ theme }}</p>
    </UiCard>

    <!-- Spec §11. Not legal advice and not a disclaimer to bury: this platform
         routes other people's capital, and the person operating it should meet
         that sentence somewhere other than a markdown file. -->
    <p class="text-xs text-ink-faint leading-relaxed px-1 pb-2">
      {{ t('settings.legalNote') }}
    </p>

    <UiModal v-model="confirmResume" :title="t('policy.resumeTitle')" size="sm">
      <p class="text-sm leading-relaxed">{{ t('policy.resumeBody') }}</p>
      <template #footer>
        <div class="flex gap-2 justify-end">
          <button class="btn-ghost" @click="confirmResume = false">{{ t('common.cancel') }}</button>
          <button
            class="btn-brand"
            @click="confirmResume = false; trading.setHalt(false)"
          >
            {{ t('policy.resume') }}
          </button>
        </div>
      </template>
    </UiModal>
  </div>
</template>
