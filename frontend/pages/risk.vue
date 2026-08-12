<script setup lang="ts">
/**
 * The Q5a decision tool.
 *
 * Type a balance, leverage and an SL/TP percentage; see exactly what that
 * percentage means under both readings, side by side, in dollars. The point is
 * to make the choice by looking at numbers instead of arguing about prose.
 *
 * It is reachable signed out — it reads no account data, it only does
 * arithmetic on numbers you type — so it borrows whichever shell fits the
 * visitor rather than forcing a login screen in front of a calculator.
 */
definePageMeta({ layout: 'public' })

const { t } = useI18n()
const api = useApi()
const auth = useAuthStore()
const accounts = useAccountsStore()
const { money, pct } = useFormat()

useHead({ title: t('nav.risk') })

if (auth.authenticated) setPageLayout('default')

const form = reactive({
  balance: '1000',
  leverage: 10,
  entry: '100000',
  side: 'long' as 'long' | 'short',
  sl_pct: '2',
  tp_pct: '4',
})

const preview = ref<RiskPreview | null>(null)
const pending = ref(false)
const error = ref('')
const loadingPrice = ref(false)

/** Prefill the entry with the live mark, so the comparison is about today. */
async function useLivePrice() {
  loadingPrice.value = true
  try {
    const quote = await api.ticker('BTCUSDT', 'futures')
    form.entry = String(Math.round(Number(quote.price) * 100) / 100)
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loadingPrice.value = false
  }
}

/**
 * Debounced: this fires on every keystroke in six fields, and the endpoint does
 * real decimal work per call. 250ms is below the threshold where the numbers
 * feel like they lag the typing.
 */
let timer: ReturnType<typeof setTimeout> | null = null
function schedule() {
  if (timer) clearTimeout(timer)
  timer = setTimeout(refresh, 250)
}

async function refresh() {
  pending.value = true
  error.value = ''
  try {
    preview.value = await api.riskPreview({ ...form })
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    pending.value = false
  }
}

watch(form, schedule, { deep: true })
onMounted(() => {
  // Signed in, the honest default is the capital actually connected.
  if (auth.authenticated && accounts.tradeableUsdt > 0) {
    form.balance = String(Math.round(accounts.tradeableUsdt))
  }
  refresh()
})
onBeforeUnmount(() => timer && clearTimeout(timer))

const sideOptions = computed(() => [
  { value: 'long', label: t('side.long'), tone: 'long' as const },
  { value: 'short', label: t('side.short'), tone: 'short' as const },
])

const readings = computed(() =>
  preview.value
    ? ([
        { key: 'price', line: preview.value.readings.price },
        { key: 'margin', line: preview.value.readings.margin },
      ] as const)
    : [],
)

/** The whole argument in one number: how many times worse reading A is. */
const multiple = computed(() => {
  if (!preview.value) return null
  const a = Number(preview.value.readings.price.loss_at_stop)
  const b = Number(preview.value.readings.margin.loss_at_stop)
  return b > 0 ? a / b : null
})
</script>

<template>
  <div class="max-w-5xl mx-auto p-4 sm:p-6 lg:py-10 space-y-4 sm:space-y-6">
    <header>
      <h1 class="display text-2xl sm:text-3xl">{{ t('risk.title') }}</h1>
      <p class="text-sm text-ink-muted mt-2 max-w-2xl leading-relaxed">{{ t('risk.intro') }}</p>
    </header>

    <UiCard>
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4">
        <UiField v-slot="{ id }" :label="t('risk.balance')">
          <input :id="id" v-model="form.balance" class="field" inputmode="decimal" />
        </UiField>
        <UiField v-slot="{ id }" :label="t('risk.leverage')">
          <input :id="id" v-model.number="form.leverage" type="number" min="1" max="125" class="field" />
        </UiField>
        <UiField v-slot="{ id }" :label="t('risk.entry')">
          <div class="flex gap-2">
            <input :id="id" v-model="form.entry" class="field" inputmode="decimal" />
            <!-- Signed in, the honest entry is the price on the chart right
                 now. Signed out there is no feed to ask, so no button. -->
            <button
              v-if="auth.authenticated"
              class="btn-ghost btn-sm shrink-0"
              :disabled="loadingPrice"
              @click="useLivePrice"
            >
              {{ t('ticket.useMark') }}
            </button>
          </div>
        </UiField>
        <div class="col-span-2 sm:col-span-1">
          <span class="label">{{ t('risk.side') }}</span>
          <UiSegmented v-model="form.side" :options="sideOptions" size="sm" class="mt-1.5" />
        </div>
        <UiField v-slot="{ id }" :label="t('risk.slPct')">
          <input :id="id" v-model="form.sl_pct" class="field" inputmode="decimal" />
        </UiField>
        <UiField v-slot="{ id }" :label="t('risk.tpPct')">
          <input :id="id" v-model="form.tp_pct" class="field" inputmode="decimal" />
        </UiField>
      </div>
    </UiCard>

    <p v-if="error" class="alert p-3 text-xs">{{ error }}</p>

    <template v-if="preview">
      <UiCard :title="t('risk.position')">
        <dl class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 text-sm">
          <div>
            <dt class="label">{{ t('risk.margin') }}</dt>
            <dd class="num mt-1">${{ money(preview.position.margin) }}</dd>
          </div>
          <div>
            <dt class="label">{{ t('risk.notional') }}</dt>
            <dd class="num mt-1">${{ money(preview.position.notional) }}</dd>
          </div>
          <div>
            <dt class="label">{{ t('risk.qty') }}</dt>
            <dd class="num mt-1">{{ Number(preview.position.qty).toFixed(6) }}</dd>
          </div>
          <div>
            <dt class="label">{{ t('risk.liquidation') }}</dt>
            <dd class="num mt-1 text-signal">${{ money(preview.position.liquidation_price) }}</dd>
          </div>
          <div>
            <dt class="label">{{ t('risk.liqDistance') }}</dt>
            <dd class="num mt-1">{{ pct(preview.position.liquidation_distance_pct) }}</dd>
          </div>
        </dl>
      </UiCard>

      <!-- The headline: the two readings differ by the leverage multiple. -->
      <p v-if="multiple && multiple > 1.05" class="alert p-3 text-sm leading-relaxed">
        {{ t('risk.headline', { multiple: multiple.toFixed(0) }) }}
      </p>

      <div class="grid md:grid-cols-2 gap-3 sm:gap-4">
        <UiCard
          v-for="{ key, line } in readings"
          :key="key"
          :title="t(`risk.basis.${key}`)"
          :tone="key === preview.active_basis ? 'ok' : 'default'"
        >
          <template #actions>
            <UiBadge v-if="key === preview.active_basis" tone="ok" dot>
              {{ t('risk.inForce') }}
            </UiBadge>
          </template>

          <p class="text-xs text-ink-muted mb-4 leading-relaxed">{{ t(`risk.basisHint.${key}`) }}</p>

          <dl class="space-y-2 text-sm">
            <div class="flex justify-between gap-3">
              <dt class="text-ink-muted">{{ t('risk.priceMove') }}</dt>
              <dd class="num">{{ Number(line.price_move_pct).toFixed(3) }}%</dd>
            </div>
            <div class="flex justify-between gap-3">
              <dt class="text-ink-muted">{{ t('risk.stopPrice') }}</dt>
              <dd class="num">${{ money(line.stop_price) }}</dd>
            </div>
            <div class="flex justify-between gap-3">
              <dt class="text-ink-muted">{{ t('risk.tpPrice') }}</dt>
              <dd class="num">${{ money(line.take_profit_price) }}</dd>
            </div>
            <div class="flex justify-between gap-3 border-t border-line pt-2">
              <dt class="text-ink-muted">{{ t('risk.lossAtStop') }}</dt>
              <dd class="num text-short">${{ money(line.loss_at_stop) }}</dd>
            </div>
            <div class="flex justify-between gap-3">
              <dt class="text-ink-muted">{{ t('risk.lossPct') }}</dt>
              <dd class="num text-short font-medium">{{ pct(line.loss_pct_of_account) }}</dd>
            </div>
            <div class="flex justify-between gap-3">
              <dt class="text-ink-muted">{{ t('risk.profitAtTp') }}</dt>
              <dd class="num text-long">${{ money(line.profit_at_tp) }}</dd>
            </div>
          </dl>

          <p v-if="!line.reachable" class="alert p-2.5 text-xs mt-3 leading-relaxed">
            {{ t('risk.unreachable') }}
          </p>
        </UiCard>
      </div>

      <p class="text-xs text-ink-faint leading-relaxed">{{ t('risk.footnote') }}</p>
    </template>

    <div v-else-if="pending" class="space-y-4">
      <div class="skeleton h-24 rounded-panel" />
      <div class="grid md:grid-cols-2 gap-4">
        <div class="skeleton h-64 rounded-panel" />
        <div class="skeleton h-64 rounded-panel" />
      </div>
    </div>
  </div>
</template>
