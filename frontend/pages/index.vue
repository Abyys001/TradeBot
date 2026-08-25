<script setup lang="ts">
/**
 * Landing page.
 *
 * Its one job: make the fan-out legible in five seconds, then hand over real
 * state — how many accounts are connected, how the last trade actually
 * performed against the one-second promise. The hero draws the promise as an
 * animated constellation; the sections below are constraints, not features.
 * "One failure stays one failure" is a guarantee someone is trusting with
 * their capital, and it earns more space than a list of buttons would.
 *
 * Everything animated here is CSS + IntersectionObserver (see plugins/reveal.ts
 * and the landing components): no animation library, nothing fetched, and the
 * whole page renders complete for a visitor who prefers reduced motion.
 */
definePageMeta({ layout: 'public' })

const { t } = useI18n()
const localePath = useLocalePath()
const auth = useAuthStore()
const trading = useTradingStore()
const { ms } = useFormat()

const legs = ref<FanLeg[]>([])
const accountCount = ref<number | null>(null)
const exchangeCount = ref<number | null>(null)
const lastFanout = ref<{ ms: number; withinBudget: boolean; symbol: string } | null>(null)

// Real numbers when signed in; the diagrams fall back to their demo cycle
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
    // Signed in but the API is unreachable — the demo diagrams still render.
  }
})

/** The count-up band. Figures are honest ones from the repo's own record. */
interface Stat {
  key: string
  to: number
  decimals?: number
  suffix?: string
}
const stats: Stat[] = [
  { key: 'exchanges', to: 8 },
  { key: 'tests', to: 350, suffix: '+' },
  { key: 'margin', to: 99, suffix: '%' },
  { key: 'fanout', to: 0.3, decimals: 1, suffix: 'ms' },
]

const steps = computed(() => ['connect', 'trade', 'watch'] as const)
const stepIcons = { connect: 'key', trade: 'bolt', watch: 'eye' } as const

const features = [
  { key: 'isolation', icon: 'shield' },
  { key: 'sizing', icon: 'wallet' },
  { key: 'stops', icon: 'bolt' },
  { key: 'keys', icon: 'lock' },
  { key: 'mark', icon: 'layers' },
  { key: 'statements', icon: 'fileText' },
] as const

const securityItems = computed(() => [
  t('landing.security.item1'),
  t('landing.security.item2'),
  t('landing.security.item3'),
  t('landing.security.item4'),
  t('landing.security.item5'),
])
</script>

<template>
  <div>
    <!-- Hero: the promise, drawn. -->
    <section class="relative overflow-hidden">
      <!-- Ambient glow, drifting behind everything. Cheap (transform-only),
           and it gives the dark ground the depth a plain panel cannot. -->
      <div
        class="pointer-events-none absolute -top-24 -start-24 h-96 w-96 rounded-full bg-brand/15 blur-[110px] animate-drift"
        aria-hidden="true"
      />
      <div
        class="pointer-events-none absolute top-1/3 -end-32 h-80 w-80 rounded-full bg-long/10 blur-[100px] animate-drift"
        style="animation-delay: -8s"
        aria-hidden="true"
      />
      <div
        class="pointer-events-none absolute bottom-0 start-1/2 h-64 w-64 -translate-x-1/2 rounded-full bg-ok/10 blur-[90px] animate-drift"
        style="animation-delay: -4s"
        aria-hidden="true"
      />
      <!-- A quiet grid behind the whole hero, like a chart surface. -->
      <div
        class="pointer-events-none absolute inset-0 hero-grid opacity-60"
        aria-hidden="true"
      />

      <div class="relative max-w-6xl mx-auto px-4 pt-10 sm:pt-16 pb-12 sm:pb-16">
        <div class="grid lg:grid-cols-[1fr_1.08fr] gap-10 lg:gap-12 items-center">
          <div class="min-w-0">
            <p v-reveal class="label mb-4 sm:mb-5 flex items-center gap-2">
              <span class="h-1.5 w-1.5 rounded-full bg-ok" />
              {{ t('landing.badge') }}
            </p>

            <h1 v-reveal="60" class="display text-hero">
              {{ t('landing.h1.line1') }}<br />
              <span class="text-ink-muted">{{ t('landing.h1.line2') }}</span><br />
              <span
                class="bg-gradient-to-r from-brand to-long bg-clip-text text-transparent"
              >
                {{ t('landing.h1.line3') }}
              </span>
            </h1>

            <p v-reveal="140" class="mt-5 sm:mt-6 text-ink-muted max-w-md leading-relaxed">
              {{ t('landing.lede') }}
            </p>

            <div v-reveal="220" class="mt-7 flex flex-wrap gap-2">
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
            <dl v-if="auth.authenticated" v-reveal="300" class="mt-9 flex flex-wrap gap-x-8 sm:gap-x-10 gap-y-4">
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

          <div v-reveal="{ y: 24, delay: 180 }" class="panel p-4 sm:p-6">
            <LandingFanOutNetwork :legs="legs" />
          </div>
        </div>
      </div>
    </section>

    <!-- The exchanges, scrolling past. -->
    <LandingExchangeMarquee />

    <!-- The numbers, counted. -->
    <section class="border-t border-line">
      <div class="max-w-6xl mx-auto px-4 py-12 sm:py-16">
        <LandingSectionHeading
          :eyebrow="t('landing.sections.stats')"
          :title="t('landing.stats.title')"
          :body="t('landing.stats.body')"
          align="center"
        />
        <dl class="mt-10 grid grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-8">
          <div v-for="(stat, i) in stats" :key="stat.key" v-reveal="i * 90" class="text-center">
            <dd class="num text-[clamp(2rem,5vw,3.25rem)] leading-none tracking-tight">
              <LandingStatNumber :to="stat.to" :decimals="stat.decimals ?? 0" />
              <span v-if="stat.suffix" class="text-brand">{{ stat.suffix }}</span>
            </dd>
            <dt class="label mt-2.5">{{ t(`landing.stats.${stat.key}.label`) }}</dt>
            <p class="text-xs text-ink-faint mt-1">{{ t(`landing.stats.${stat.key}.body`) }}</p>
          </div>
        </dl>
      </div>
    </section>

    <!-- How it goes, in the order it actually happens. -->
    <section class="border-t border-line bg-panel/40">
      <div class="max-w-6xl mx-auto px-4 py-12 sm:py-16">
        <LandingSectionHeading
          :eyebrow="t('landing.sections.how')"
          :title="t('landing.how.title')"
          align="center"
        />
        <ol class="mt-10 relative grid md:grid-cols-3 gap-6 md:gap-8">
          <!-- The line that ties the three steps together, md and up. -->
          <div
            class="hidden md:block absolute top-6 inset-x-[16%] h-px bg-gradient-to-r from-transparent via-line-strong to-transparent"
            aria-hidden="true"
          />
          <li
            v-for="(step, i) in steps"
            :key="step"
            v-reveal="i * 110"
            class="panel p-5 relative"
          >
            <span
              class="w-12 h-12 rounded-xl bg-brand-dim border border-brand/25 grid place-items-center text-brand"
            >
              <UiIcon :name="stepIcons[step]" :size="20" />
            </span>
            <!-- A real sequence, so the number earns its place. -->
            <span class="num text-tick text-ink-faint absolute top-5 end-5">0{{ i + 1 }}</span>
            <h3 class="display text-base mt-4">{{ t(`landing.how.${step}.term`) }}</h3>
            <p class="mt-2 text-sm text-ink-muted leading-relaxed">
              {{ t(`landing.how.${step}.body`) }}
            </p>
          </li>
        </ol>
      </div>
    </section>

    <!-- The constraints that make the promise true. -->
    <section class="border-t border-line">
      <div class="max-w-6xl mx-auto px-4 py-12 sm:py-16">
        <LandingSectionHeading
          :eyebrow="t('landing.sections.features')"
          :title="t('landing.features.title')"
          :body="t('landing.features.body')"
        />
        <div class="mt-10 grid sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
          <div
            v-for="(f, i) in features"
            :key="f.key"
            v-reveal="(i % 3) * 90"
            class="group panel p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lift"
          >
            <span
              class="w-10 h-10 rounded-lg bg-raised border border-line grid place-items-center text-ink-muted
                     group-hover:text-brand group-hover:border-brand/40 group-hover:bg-brand-dim
                     transition-colors duration-200"
            >
              <UiIcon :name="f.icon" :size="18" />
            </span>
            <h3 class="display text-base mt-4">{{ t(`landing.features.${f.key}.term`) }}</h3>
            <p class="mt-2 text-sm text-ink-muted leading-relaxed">
              {{ t(`landing.features.${f.key}.body`) }}
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- The fan-out, live: your own last trade, or the demo. -->
    <section class="border-t border-line bg-panel/40">
      <div class="max-w-6xl mx-auto px-4 py-12 sm:py-16 grid lg:grid-cols-[1fr_1.1fr] gap-10 items-center">
        <LandingSectionHeading
          :eyebrow="t('landing.sections.live')"
          :title="t('landing.live.title')"
          :body="t('landing.live.body')"
        />
        <div v-reveal="{ y: 24, delay: 120 }" class="panel p-4 sm:p-6">
          <FanOutDiagram :legs="legs">
            <template #caption>
              {{ legs.length ? t('landing.diagram.real') : t('landing.diagram.demo') }}
            </template>
          </FanOutDiagram>
        </div>
      </div>
    </section>

    <!-- Security is the reason to trust it with a key, so it gets its own block. -->
    <section class="border-t border-line">
      <div class="max-w-6xl mx-auto px-4 py-12 sm:py-16 grid lg:grid-cols-[1fr_1.2fr] gap-8 lg:gap-12">
        <LandingSectionHeading
          :eyebrow="t('landing.sections.security')"
          :title="t('landing.security.title')"
          :body="t('landing.security.body')"
        />
        <ul v-reveal class="space-y-3">
          <li
            v-for="(item, i) in securityItems"
            :key="i"
            class="flex items-start gap-3"
          >
            <span
              class="mt-0.5 w-5 h-5 shrink-0 rounded-full bg-ok-dim border border-ok/30 grid place-items-center text-ok"
            >
              <UiIcon name="check" :size="12" />
            </span>
            <span class="text-sm text-ink-muted leading-relaxed">{{ item }}</span>
          </li>
          <li class="pt-2">
            <NuxtLink
              :to="localePath(auth.authenticated ? '/accounts' : '/login')"
              class="btn-ghost btn-sm"
            >
              {{ t('landing.cta.accounts') }}
              <UiIcon name="arrowRight" :size="14" class="flip-rtl" />
            </NuxtLink>
          </li>
        </ul>
      </div>
    </section>

    <!-- Straight answers. -->
    <section class="border-t border-line bg-panel/40">
      <div class="max-w-6xl mx-auto px-4 py-12 sm:py-16 grid lg:grid-cols-[1fr_1.25fr] gap-8 lg:gap-12">
        <LandingSectionHeading
          :eyebrow="t('landing.sections.faq')"
          :title="t('landing.faq.title')"
          :body="t('landing.faq.body')"
        />
        <LandingFaq />
      </div>
    </section>

    <!-- The close. -->
    <section class="border-t border-line relative overflow-hidden">
      <div
        class="pointer-events-none absolute inset-x-0 bottom-0 h-64 bg-gradient-to-t from-brand/10 to-transparent"
        aria-hidden="true"
      />
      <div
        class="pointer-events-none absolute -bottom-24 left-1/2 -translate-x-1/2 h-72 w-[36rem] rounded-full bg-brand/15 blur-[120px] animate-drift"
        aria-hidden="true"
      />
      <div class="relative max-w-6xl mx-auto px-4 py-16 sm:py-24 text-center">
        <h2 v-reveal class="display text-3xl sm:text-5xl tracking-tight">
          {{ t('landing.cta.title') }}
        </h2>
        <p v-reveal="100" class="mt-4 text-sm sm:text-base text-ink-muted max-w-xl mx-auto leading-relaxed">
          {{ t('landing.cta.body') }}
        </p>
        <div v-reveal="200" class="mt-8 flex flex-wrap gap-3 justify-center">
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
      </div>
    </section>
  </div>
</template>

<style scoped>
/* The faint dot lattice behind the hero, like a chart surface. The mask fades
   it out toward the edges so it never competes with the copy. */
.hero-grid {
  background-image: radial-gradient(rgb(var(--c-line) / 0.6) 1px, transparent 1px);
  background-size: 26px 26px;
  mask-image: radial-gradient(ellipse 90% 70% at 50% 30%, black 40%, transparent 100%);
}
</style>
