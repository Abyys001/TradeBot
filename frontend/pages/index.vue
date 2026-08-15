<script setup lang="ts">
/**
 * Landing page.
 *
 * Its one job: make the fan-out legible in five seconds, then hand over real
 * state — how many accounts are connected, how the last trade actually
 * performed against the one-second promise. Not a brochure; the operator opens
 * this to see whether the thing is ready to trade.
 *
 * The sections after the hero are constraints, not features. "One failure stays
 * one failure" is a guarantee someone is trusting with their capital, and it
 * earns more space than a list of buttons would.
 */
definePageMeta({ layout: 'public' })

const { t } = useI18n()
const localePath = useLocalePath()
const auth = useAuthStore()
const trading = useTradingStore()
const { ms } = useFormat()

const legs = ref<{ label: string; ms: number; ok: boolean }[]>([])
const accountCount = ref<number | null>(null)
const exchangeCount = ref<number | null>(null)
const lastFanout = ref<{ ms: number; withinBudget: boolean; symbol: string } | null>(null)

// Real numbers when signed in; the diagram falls back to its demo cycle
// otherwise, so a signed-out visitor still learns what the platform does.
onMounted(async () => {
  if (!auth.checked) await auth.check()
  if (!auth.authenticated) return
  const api = useApi()
  try {
    // The budget line must be the backend's actual deadline (Q19), not a guess.
    const [accounts, trades, policy] = await Promise.all([
      api.accounts(),
      api.trades(),
      api.policy().catch(() => null),
    ])
    if (policy) trading.policy = policy
    accountCount.value = accounts.length
    exchangeCount.value = new Set(accounts.map((a) => a.exchange)).size
    const latest = trades[0]
    if (latest) {
      lastFanout.value = {
        ms: latest.fanout_ms ?? 0,
        withinBudget: (latest.fanout_ms ?? 0) <= trading.fanoutBudgetMs,
        symbol: latest.symbol,
      }
      legs.value = latest.legs.map((leg) => ({
        label: leg.account_label,
        ms: leg.dispatch_ms ?? 0,
        ok: leg.ok,
      }))
    }
  } catch {
    // Signed in but the API is unreachable — the demo diagram still renders.
  }
})

const truths = computed(() => [
  { icon: 'shield' as IconName, key: 'isolation' },
  { icon: 'wallet' as IconName, key: 'sizing' },
  { icon: 'bolt' as IconName, key: 'stops' },
])

const steps = computed(() => ['connect', 'trade', 'watch'])

const EXCHANGES = [
  'Hyperliquid',
  'Bybit',
  'Binance',
  'OKX',
  'Gate.io',
  'KuCoin',
  'Toobit',
  'LBank',
]
</script>

<template>
  <div>
    <!-- Hero -->
    <section class="max-w-6xl mx-auto px-4 pt-10 sm:pt-16 pb-10 sm:pb-14">
      <div class="grid lg:grid-cols-[1fr_1.05fr] gap-10 lg:gap-14 items-center">
        <div class="min-w-0">
          <p class="label mb-4 sm:mb-5">{{ t('landing.eyebrow') }}</p>

          <h1 class="display text-hero">
            {{ t('landing.h1.line1') }}<br />
            <span class="text-ink-muted">{{ t('landing.h1.line2') }}</span><br />
            {{ t('landing.h1.line3') }}
          </h1>

          <p class="mt-5 sm:mt-6 text-ink-muted max-w-md leading-relaxed">{{ t('landing.lede') }}</p>

          <div class="mt-7 flex flex-wrap gap-2">
            <NuxtLink
              :to="localePath(auth.authenticated ? '/dashboard' : '/login')"
              class="btn-brand"
            >
              {{ auth.authenticated ? t('landing.cta.dashboard') : t('landing.cta.signIn') }}
              <UiIcon name="arrowRight" :size="15" class="flip-rtl" />
            </NuxtLink>
            <NuxtLink :to="localePath('/risk')" class="btn-ghost">
              {{ t('landing.cta.risk') }}
            </NuxtLink>
          </div>

          <!-- Real state, only when there is real state to show. -->
          <dl v-if="auth.authenticated" class="mt-9 flex flex-wrap gap-x-8 sm:gap-x-10 gap-y-4">
            <div>
              <dt class="label">{{ t('landing.stat.accounts') }}</dt>
              <dd class="num text-2xl mt-1">{{ accountCount ?? '—' }}</dd>
            </div>
            <div v-if="exchangeCount">
              <dt class="label">{{ t('landing.stat.exchanges') }}</dt>
              <dd class="num text-2xl mt-1">{{ exchangeCount }}</dd>
            </div>
            <div v-if="lastFanout">
              <dt class="label">{{ t('landing.stat.lastFanout') }}</dt>
              <dd
                class="num text-2xl mt-1"
                :class="lastFanout.withinBudget ? 'text-ok' : 'text-signal'"
              >
                {{ ms(lastFanout.ms) }}
              </dd>
            </div>
            <div v-if="lastFanout">
              <dt class="label">{{ t('landing.stat.lastSymbol') }}</dt>
              <dd class="num text-2xl mt-1">{{ lastFanout.symbol }}</dd>
            </div>
          </dl>
        </div>

        <div class="panel p-4 sm:p-6">
          <FanOutDiagram :legs="legs">
            <template #caption>
              {{ legs.length ? t('landing.diagram.real') : t('landing.diagram.demo') }}
            </template>
          </FanOutDiagram>
        </div>
      </div>
    </section>

    <!-- Three things that are true of every trade. Not features — constraints. -->
    <section class="border-t border-line">
      <div class="max-w-6xl mx-auto px-4 py-12 sm:py-16 grid md:grid-cols-3 gap-8 md:gap-10">
        <div v-for="truth in truths" :key="truth.key">
          <span
            class="w-9 h-9 rounded-lg grid place-items-center bg-brand-dim border border-brand/25 text-brand"
          >
            <UiIcon :name="truth.icon" :size="17" />
          </span>
          <h2 class="display text-base mt-4">{{ t(`landing.truths.${truth.key}.term`) }}</h2>
          <p class="mt-2 text-sm text-ink-muted leading-relaxed">
            {{ t(`landing.truths.${truth.key}.body`) }}
          </p>
        </div>
      </div>
    </section>

    <!-- How it goes, in the order it actually happens. -->
    <section class="border-t border-line bg-panel/40">
      <div class="max-w-6xl mx-auto px-4 py-12 sm:py-16">
        <h2 class="display text-xl sm:text-2xl">{{ t('landing.how.title') }}</h2>
        <ol class="mt-8 grid md:grid-cols-3 gap-6 md:gap-8">
          <li v-for="(step, i) in steps" :key="step" class="panel p-5">
            <span class="num text-tick text-ink-faint">0{{ i + 1 }}</span>
            <h3 class="text-sm font-medium mt-2">{{ t(`landing.how.${step}.term`) }}</h3>
            <p class="mt-2 text-sm text-ink-muted leading-relaxed">
              {{ t(`landing.how.${step}.body`) }}
            </p>
          </li>
        </ol>
      </div>
    </section>

    <!-- Coverage. Honest about what is not verified yet. -->
    <section class="border-t border-line">
      <div class="max-w-6xl mx-auto px-4 py-12 sm:py-16 grid lg:grid-cols-[1fr_1.2fr] gap-8 lg:gap-12">
        <div>
          <h2 class="display text-xl sm:text-2xl">{{ t('landing.coverage.title') }}</h2>
          <p class="mt-3 text-sm text-ink-muted leading-relaxed max-w-md">
            {{ t('landing.coverage.body') }}
          </p>
        </div>
        <ul class="flex flex-wrap gap-2 content-start">
          <li
            v-for="exchange in EXCHANGES"
            :key="exchange"
            class="chip border-line text-ink-muted bg-panel normal-case tracking-normal text-xs"
          >
            {{ exchange }}
          </li>
        </ul>
      </div>
    </section>

    <!-- Security is the reason to trust it with a key, so it gets its own block. -->
    <section class="border-t border-line">
      <div class="max-w-6xl mx-auto px-4 py-12 sm:py-16 flex flex-col sm:flex-row gap-6 sm:gap-10">
        <span
          class="w-10 h-10 shrink-0 rounded-lg grid place-items-center bg-ok-dim border border-ok/25 text-ok"
        >
          <UiIcon name="shield" :size="19" />
        </span>
        <div class="max-w-2xl">
          <h2 class="display text-lg">{{ t('landing.security.title') }}</h2>
          <p class="mt-2 text-sm text-ink-muted leading-relaxed">{{ t('landing.security.body') }}</p>
          <NuxtLink
            :to="localePath(auth.authenticated ? '/accounts' : '/login')"
            class="btn-ghost btn-sm mt-5"
          >
            {{ t('landing.cta.accounts') }}
            <UiIcon name="arrowRight" :size="14" class="flip-rtl" />
          </NuxtLink>
        </div>
      </div>
    </section>
  </div>
</template>
