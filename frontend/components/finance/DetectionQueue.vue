<script setup lang="ts">
/**
 * Balance changes the platform cannot explain, waiting for an answer.
 *
 * The keys are trade-only (spec §7), so no exchange can tell us who moved money
 * in or out. What the server *can* do is subtract: equity moved by this much,
 * the legs it placed itself explain that much, the cash already written down
 * explains the rest — and whatever is left over shows up here.
 *
 * It is a proposal, never an entry. Nothing on this card has touched invested
 * capital yet, which is why the whole subtraction is on the row: the operator
 * accepting it should be able to check the arithmetic without leaving the page.
 */
const emit = defineEmits<{ resolved: [] }>()

const { t } = useI18n()
const api = useApi()
const { money, signed, dateTime } = useFormat()

const rows = ref<DetectedMovement[]>([])
const loading = ref(true)
const error = ref('')
const busy = ref<number | null>(null)

const editing = ref<DetectedMovement | null>(null)
const dismissing = ref<DetectedMovement | null>(null)
const form = reactive({ kind: 'deposit' as 'deposit' | 'withdrawal', amount: '', note: '' })
const dismissNote = ref('')
const formError = ref('')

const kindOptions = computed(() => [
  { value: 'deposit', label: t('finance.movements.deposit'), tone: 'ok' as const },
  { value: 'withdrawal', label: t('finance.movements.withdrawal'), tone: 'signal' as const },
])

async function load() {
  loading.value = true
  try {
    rows.value = await api.detections('pending')
    error.value = ''
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
defineExpose({ load })

async function accept(row: DetectedMovement, overrides: Record<string, unknown> = {}) {
  busy.value = row.id
  try {
    await api.acceptDetection(row.id, overrides)
    editing.value = null
    await load()
    emit('resolved')
  } catch (e: any) {
    formError.value = errorMessage(e)
    error.value = errorMessage(e)
  } finally {
    busy.value = null
  }
}

async function dismiss() {
  const row = dismissing.value
  if (!row) return
  busy.value = row.id
  try {
    await api.dismissDetection(row.id, dismissNote.value)
    dismissing.value = null
    await load()
    emit('resolved')
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    busy.value = null
  }
}

function openEdit(row: DetectedMovement) {
  form.kind = row.suggested_kind
  form.amount = row.amount
  form.note = ''
  formError.value = ''
  editing.value = row
}

function saveEdit() {
  const row = editing.value
  if (!row) return
  const amount = Number(form.amount)
  if (!Number.isFinite(amount) || amount <= 0) {
    formError.value = t('finance.form.invalid')
    return
  }
  accept(row, { kind: form.kind, amount: form.amount, note: form.note || undefined })
}

function openDismiss(row: DetectedMovement) {
  dismissNote.value = ''
  dismissing.value = row
}
</script>

<template>
  <UiCard
    v-if="loading || rows.length || error"
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
      <li v-for="row in rows" :key="row.id" class="px-4 py-3 space-y-2">
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <UiBadge :tone="row.suggested_kind === 'deposit' ? 'ok' : 'signal'" dot>
            {{ t(`finance.movements.${row.suggested_kind}`) }}
          </UiBadge>
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

        <div class="flex flex-wrap gap-2">
          <button
            class="btn-brand btn-sm"
            :disabled="busy === row.id"
            @click="accept(row)"
          >
            <UiIcon name="check" :size="13" />
            {{ t('finance.detect.accept') }}
          </button>
          <button class="btn-ghost btn-sm" :disabled="busy === row.id" @click="openEdit(row)">
            {{ t('finance.detect.edit') }}
          </button>
          <button class="btn-quiet btn-sm" :disabled="busy === row.id" @click="openDismiss(row)">
            {{ t('finance.detect.dismiss') }}
          </button>
        </div>
      </li>
    </ul>
  </UiCard>

  <!-- Accept, with the operator's correction. -->
  <UiModal
    :model-value="editing !== null"
    :title="t('finance.detect.editTitle')"
    size="sm"
    @update:model-value="editing = null"
  >
    <div class="space-y-4">
      <p class="text-xs text-ink-muted leading-relaxed">{{ t('finance.detect.editBody') }}</p>
      <UiField :label="t('finance.form.kind')">
        <UiSegmented v-model="form.kind" :options="kindOptions" :block="true" />
      </UiField>
      <UiField :label="t('finance.form.amount')" :error="formError">
        <template #default="{ id, describedBy }">
          <input
            :id="id"
            v-model="form.amount"
            class="field"
            inputmode="decimal"
            :aria-describedby="describedBy"
          />
        </template>
      </UiField>
      <UiField :label="t('finance.form.note')" :optional="true">
        <template #default="{ id, describedBy }">
          <input
            :id="id"
            v-model="form.note"
            class="field"
            :placeholder="t('finance.form.notePlaceholder')"
            :aria-describedby="describedBy"
          />
        </template>
      </UiField>
    </div>
    <template #footer>
      <div class="flex gap-2 justify-end">
        <button class="btn-ghost" @click="editing = null">{{ t('common.cancel') }}</button>
        <button class="btn-brand" :disabled="busy !== null" @click="saveEdit">
          {{ t('finance.detect.accept') }}
        </button>
      </div>
    </template>
  </UiModal>

  <!-- Dismiss. Nothing is booked, but the reason is kept. -->
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
