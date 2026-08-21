<script setup lang="ts">
/**
 * Balance changes the closed trades do not explain — and what they were.
 *
 * The keys are trade-only (spec §7), so no exchange can tell us who moved money
 * in or out. The server subtracts instead: equity moved by this much, the legs
 * it placed itself explain that much, the cash already written down explains
 * the rest, and the remainder lands here.
 *
 * Then it answers the question that actually matters — trade result, or
 * somebody's cash — from the one thing the exchange does not know: the platform
 * trades every account at once, so a change that moved one account alone was a
 * transfer (`apps/accounts/classify.py`). Most rows never reach this card; they
 * are decided and booked. What is left is shown as a **question with two
 * answers**, not a confirm button, because the two are different events and
 * booking one as the other is a wrong PnL either way.
 *
 * The decisions the platform made alone are listed underneath and can be
 * overturned. An automatic verdict nobody can change would be worse than the
 * manual queue it replaced.
 */
const emit = defineEmits<{ resolved: [] }>()

const { t } = useI18n()
const api = useApi()
const { money, signed, dateTime } = useFormat()

const rows = ref<DetectedMovement[]>([])
const decided = ref<DetectedMovement[]>([])
const loading = ref(true)
const error = ref('')
const busy = ref<number | null>(null)

/** The operator's answer per row ('trade' | 'investor'), seeded from the
 *  server's reading so the common case is one click. */
const answers = reactive<Record<number, string>>({})
/** Only edited when the answer is "investor" — the trade books no figure. */
const amounts = reactive<Record<number, string>>({})

const dismissing = ref<DetectedMovement | null>(null)
const dismissNote = ref('')

function investorLabel(row: DetectedMovement) {
  return row.suggested_kind === 'deposit'
    ? t('finance.detect.classInvestorDeposit')
    : t('finance.detect.classInvestorWithdrawal')
}

function options(row: DetectedMovement) {
  return [
    { value: 'trade', label: t('finance.detect.classTrade'), tone: 'ok' as const },
    { value: 'investor', label: investorLabel(row), tone: 'signal' as const },
  ]
}

function reasonText(row: DetectedMovement) {
  // A row from before the classifier existed, or from a deployment with it
  // switched off, carries no reason — an empty i18n path, not a missing one.
  return t(`finance.detect.reason.${row.classification_reason || 'unclassified'}`, {
    peers: row.peers_observed,
    moved: row.peers_moved,
  })
}

async function load() {
  loading.value = true
  try {
    const [pending, resolved] = await Promise.all([
      api.detections('pending'),
      api.detections('resolved'),
    ])
    rows.value = pending
    decided.value = resolved.filter((row) => row.auto_resolved)
    for (const row of pending) {
      answers[row.id] = row.suggested_class
      amounts[row.id] = row.amount
    }
    error.value = ''
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
defineExpose({ load })

async function run(id: number, action: () => Promise<unknown>) {
  busy.value = id
  try {
    await action()
    await load()
    emit('resolved')
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    busy.value = null
  }
}

function confirm(row: DetectedMovement) {
  if (answers[row.id] === 'trade') {
    return run(row.id, () => api.attributeDetection(row.id))
  }
  const amount = Number(amounts[row.id])
  if (!Number.isFinite(amount) || amount <= 0) {
    error.value = t('finance.form.invalid')
    return
  }
  return run(row.id, () =>
    api.acceptDetection(row.id, { kind: row.suggested_kind, amount: amounts[row.id] }),
  )
}

function reopen(row: DetectedMovement) {
  return run(row.id, () => api.reopenDetection(row.id))
}

function dismiss() {
  const row = dismissing.value
  if (!row) return
  return run(row.id, async () => {
    await api.dismissDetection(row.id, dismissNote.value)
    dismissing.value = null
  })
}

function openDismiss(row: DetectedMovement) {
  dismissNote.value = ''
  dismissing.value = row
}
</script>

<template>
  <UiCard
    v-if="loading || rows.length || decided.length || error"
    :title="t('finance.detect.title')"
    :hint="t('finance.detect.subtitle')"
    :tone="rows.length ? 'signal' : 'default'"
    flush
  >
    <template #actions>
      <UiBadge v-if="rows.length" tone="signal" dot>
        {{ t('finance.detect.waiting', { n: rows.length }) }}
      </UiBadge>
      <button class="btn-quiet btn-sm btn-icon" :aria-label="t('common.reload')" @click="load">
        <UiIcon name="refresh" :size="13" :class="loading ? 'animate-spin' : ''" />
      </button>
    </template>

    <p v-if="error" class="alert p-3 m-4 text-xs">{{ error }}</p>

    <div v-if="loading" class="p-4 space-y-2">
      <div v-for="i in 2" :key="i" class="skeleton h-16" />
    </div>

    <ul v-else-if="rows.length" class="divide-y divide-line">
      <li v-for="row in rows" :key="row.id" class="px-4 py-3 space-y-3">
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <span class="num text-sm font-medium">${{ money(row.amount) }}</span>
          <span class="text-sm">{{ row.account_label }}</span>
          <span class="text-xs text-ink-muted">{{ row.exchange_label }}</span>
          <span class="num text-xs text-ink-faint ms-auto">{{ dateTime(row.observed_at) }}</span>
        </div>

        <!-- The subtraction, shown rather than summarised. -->
        <dl class="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1 text-[0.7rem]">
          <div class="flex justify-between gap-2">
            <dt class="label">{{ t('finance.detect.equity') }}</dt>
            <dd class="num">
              {{ money(row.previous_equity) }} → {{ money(row.current_equity) }}
            </dd>
          </div>
          <div class="flex justify-between gap-2">
            <dt class="label">{{ t('finance.detect.moved') }}</dt>
            <dd class="num">${{ signed(row.delta) }}</dd>
          </div>
          <div class="flex justify-between gap-2">
            <dt class="label">{{ t('finance.detect.trades') }}</dt>
            <dd class="num">${{ signed(row.trade_pnl) }}</dd>
          </div>
          <div class="flex justify-between gap-2">
            <dt class="label">{{ t('finance.detect.recorded') }}</dt>
            <dd class="num">${{ signed(row.manual_net) }}</dd>
          </div>
        </dl>

        <!-- Why the server pre-selected what it did, so it can be checked. -->
        <p class="text-[0.7rem] text-ink-muted leading-relaxed">
          <span class="label">{{ t('finance.detect.verdict') }}:</span>
          {{ reasonText(row) }}
        </p>

        <UiField :label="t('finance.detect.question')">
          <UiSegmented v-model="answers[row.id]" :options="options(row)" :block="true" />
        </UiField>

        <p v-if="answers[row.id] === 'trade'" class="text-[0.7rem] text-ink-muted">
          {{ t('finance.detect.classTradeHint') }}
        </p>
        <div v-else class="space-y-2">
          <p class="text-[0.7rem] text-ink-muted">{{ t('finance.detect.classInvestorHint') }}</p>
          <UiField :label="t('finance.form.amount')" :hint="t('finance.detect.amountHint')">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                v-model="amounts[row.id]"
                class="field"
                inputmode="decimal"
                :aria-describedby="describedBy"
              />
            </template>
          </UiField>
        </div>

        <div class="flex flex-wrap gap-2">
          <button class="btn-brand btn-sm" :disabled="busy === row.id" @click="confirm(row)">
            <UiIcon name="check" :size="13" />
            {{ t('finance.detect.confirm') }}
          </button>
          <button class="btn-quiet btn-sm" :disabled="busy === row.id" @click="openDismiss(row)">
            {{ t('finance.detect.dismiss') }}
          </button>
        </div>
      </li>
    </ul>

    <div v-else-if="!error" class="p-6 text-center space-y-1">
      <p class="text-sm">{{ t('finance.detect.empty') }}</p>
      <p class="text-xs text-ink-muted">{{ t('finance.detect.emptyBody') }}</p>
    </div>

    <!-- What the platform decided on its own, and the way back. -->
    <details v-if="decided.length" class="border-t border-line">
      <summary class="px-4 py-2.5 text-xs cursor-pointer select-none">
        {{ t('finance.detect.decidedTitle') }}
        <span class="text-ink-muted">
          {{ t('finance.detect.decidedHint', { n: decided.length }) }}
        </span>
      </summary>
      <ul class="divide-y divide-line border-t border-line">
        <li
          v-for="row in decided"
          :key="row.id"
          class="px-4 py-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs"
        >
          <UiBadge :tone="row.status === 'trade' ? 'brand' : 'signal'">
            {{ t(`finance.detect.decidedAs.${row.status}`) }}
          </UiBadge>
          <span class="num font-medium">${{ money(row.amount) }}</span>
          <span>{{ row.account_label }}</span>
          <span class="text-ink-muted truncate">{{ reasonText(row) }}</span>
          <span class="num text-ink-faint ms-auto">{{ dateTime(row.observed_at) }}</span>
          <button class="btn-quiet btn-sm" :disabled="busy === row.id" @click="reopen(row)">
            {{ t('finance.detect.reopen') }}
          </button>
        </li>
      </ul>
    </details>
  </UiCard>

  <!-- Neither a trade nor a transfer: nothing is booked and nothing is credited. -->
  <UiModal
    :model-value="dismissing !== null"
    :title="t('finance.detect.dismissTitle')"
    size="sm"
    @update:model-value="dismissing = null"
  >
    <div class="space-y-4">
      <p class="text-sm leading-relaxed">{{ t('finance.detect.dismissBody') }}</p>
      <UiField :label="t('finance.form.note')" :optional="true">
        <template #default="{ id, describedBy }">
          <input
            :id="id"
            v-model="dismissNote"
            class="field"
            :placeholder="t('finance.detect.dismissPlaceholder')"
            :aria-describedby="describedBy"
          />
        </template>
      </UiField>
    </div>
    <template #footer>
      <div class="flex gap-2 justify-end">
        <button class="btn-ghost" @click="dismissing = null">{{ t('common.cancel') }}</button>
        <button class="btn-danger" :disabled="busy !== null" @click="dismiss">
          {{ t('finance.detect.dismiss') }}
        </button>
      </div>
    </template>
  </UiModal>
</template>
