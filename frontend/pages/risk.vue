<script setup lang="ts">
/**
 * The Q5a decision tool: what does a stop percentage actually cost?
 *
 * One question, one answer, in dollars. The page used to explain the two
 * readings in prose and then print two equal tables for the reader to compare;
 * it now leads with the number the admin came for — what the stop in force
 * costs on this balance — and keeps the other reading beside it as the
 * comparison rather than as a second homework problem.
 *
 * Reachable signed out: it reads no account data, only arithmetic on typed
 * numbers, so it borrows whichever shell fits the visitor.
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

/** The reading the platform is actually configured for, and the other one. */
const active = computed(() =>
  preview.value ? preview.value.readings[preview.value.active_basis] : null,
)
const otherKey = computed(() =>
  preview.value?.active_basis === 'price' ? 'margin' : ('price' as const),
)
const other = computed(() => (preview.value ? preview.value.readings[otherKey.value] : null))

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
  <div class="max-w-5xl mx-auto p-4 sm:p-6 lg:py-10 space-y-4">
    <header>
      <h1 class="display text-2xl sm:text-3xl">{{ t('risk.title') }}</h1>
      <p class="text-sm text-ink-muted mt-1.5">{{ t('risk.intro') }}</p>
    </header>

    <!-- Inputs. A toolbar, not a form: nothing is submitted, every keystroke
         re-answers the question below it. -->
    <UiCard flush>
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 p-3 sm:p-4">
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

    <template v-if="preview && active">
      <!-- The answer. One number, in the money the account is denominated in,
           under the reading that is actually in force. -->
      <section class="panel border-short/30 bg-short-dim p-4 sm:p-6">
        <div class="flex flex-wrap items-end gap-x-6 gap-y-3">
          <div class="min-w-0">
            <p class="label">{{ t('risk.answer.costs', { pct: form.sl_pct }) }}</p>
            <p class="num text-short mt-1 text-[clamp(2rem,6vw,3rem)] leading-none">
              −${{ money(active.loss_at_stop) }}
            </p>
            <p class="text-xs text-ink-muted mt-2">
              {{ t('risk.answer.ofAccount', { pct: pct(active.loss_pct_of_account) }) }}
              · {{ t(`risk.basis.${preview.active_basis}`) }}
            </p>
          </div>

          <div class="ms-auto text-end">
            <p class="label">{{ t('risk.answer.pays') }}</p>
            <p class="num text-long text-2xl mt-1">+${{ money(active.profit_at_tp) }}</p>
            <p class="text-xs text-ink-muted mt-1">
              {{ t('risk.answer.atTp', { pct: form.tp_pct }) }}
            </p>
          </div>
        </div>

        <!-- The comparison, in one line instead of a paragraph. -->
        <p
          v-if="other && multiple && multiple > 1.05"
          class="text-xs text-ink-muted mt-4 pt-3 border-t border-line/60"
        >
          {{ t('risk.answer.otherWay', {
            basis: t(`risk.basis.${otherKey}`),
            amount: money(other.loss_at_stop),
            multiple: multiple.toFixed(0),
          }) }}
        </p>

        <p v-if="!active.reachable" class="alert p-2.5 text-xs mt-3 leading-relaxed">
          {{ t('risk.unreachable') }}
        </p>
      </section>

      <!-- The two readings, side by side. The one in force reads first. -->
      <div class="grid md:grid-cols-2 gap-3 sm:gap-4">
        <UiCard
          v-for="{ key, line } in readings"
          :key="key"
          :title="t(`risk.basis.${key}`)"
          :hint="t(`risk.basisHint.${key}`)"
          :tone="key === preview.active_basis ? 'ok' : 'default'"
          :class="key === preview.active_basis ? '' : 'opacity-80'"
        >
          <template #actions>
            <UiBadge v-if="key === preview.active_basis" tone="ok" dot>
              {{ t('risk.inForce') }}
            </UiBadge>
          </template>

          <dl class="space-y-2 text-sm">
            <div class="flex justify-between gap-3">
              <dt class="text-ink-muted">{{ t('risk.lossAtStop') }}</dt>
              <dd class="num text-short font-medium">
                ${{ money(line.loss_at_stop) }}
                <span class="text-ink-faint font-normal">
                  ({{ pct(line.loss_pct_of_account) }})
                </span>
              </dd>
            </div>
            <div class="flex justify-between gap-3">
              <dt class="text-ink-muted">{{ t('risk.profitAtTp') }}</dt>
              <dd class="num text-long">${{ money(line.profit_at_tp) }}</dd>
            </div>
            <div class="flex justify-between gap-3 border-t border-line pt-2">
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
          </dl>

          <p v-if="!line.reachable" class="alert p-2.5 text-xs mt-3 leading-relaxed">
            {{ t('risk.unreachable') }}
          </p>
        </UiCard>
      </div>

      <!-- The position the numbers above are about. A strip: it is context,
           not a finding, and it was taking a whole card to say so. -->
      <UiCard :title="t('risk.position')" :hint="t('risk.liqNote')">
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
    </template>

    <div v-else-if="pending" class="space-y-4">
      <div class="skeleton h-32 rounded-panel" />
      <div class="grid md:grid-cols-2 gap-4">
        <div class="skeleton h-56 rounded-panel" />
        <div class="skeleton h-56 rounded-panel" />
      </div>
    </div>
  </div>
</template>
