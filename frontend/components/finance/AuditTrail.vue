<script setup lang="ts">
/**
 * Who changed the money record, when, and from what to what.
 *
 * Append-only on the server (`apps/accounts/bookkeeping.py`): a deleted cash
 * flow still has its entry here, because a deletion is exactly the change worth
 * keeping a record of. `actor` is blank when the platform itself acted — the
 * detector proposing something is an event too, and it has no operator behind
 * it.
 */
const props = defineProps<{ account?: number | null }>()

const { t } = useI18n()
const api = useApi()
const { money, dateTime } = useFormat()

const rows = ref<LedgerEvent[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  try {
    rows.value = await api.ledgerEvents(props.account ?? null)
    error.value = ''
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.account, load)
defineExpose({ load })

const TONE: Record<LedgerEvent['action'], 'neutral' | 'ok' | 'signal' | 'brand'> = {
  detected: 'brand',
  created: 'ok',
  accepted: 'ok',
  edited: 'neutral',
  deleted: 'signal',
  dismissed: 'neutral',
  split: 'brand',
}

/** "amount 100.00 → 250.00, note '' → 'corrected'" — only what actually moved. */
function changes(event: LedgerEvent): string {
  const keys = new Set([
    ...Object.keys(event.before ?? {}),
    ...Object.keys(event.after ?? {}),
  ])
  return [...keys]
    .map((key) => {
      const from = event.before?.[key]
      const to = event.after?.[key]
      if (from !== undefined && to !== undefined) return `${key} ${from} → ${to}`
      return `${key} ${from ?? to}`
    })
    .join(' · ')
}
</script>

<template>
  <UiCard :title="t('finance.audit.title')" :hint="t('finance.audit.subtitle')" flush>
    <template #actions>
      <button class="btn-quiet btn-sm btn-icon" :aria-label="t('common.reload')" @click="load">
        <UiIcon name="refresh" :size="13" :class="loading ? 'animate-spin' : ''" />
      </button>
    </template>

    <p v-if="error" class="alert p-3 m-4 text-xs">{{ error }}</p>

    <div v-if="loading" class="p-4 space-y-2">
      <div v-for="i in 3" :key="i" class="skeleton h-8" />
    </div>

    <ul v-else-if="rows.length" class="divide-y divide-line max-h-[26rem] overflow-y-auto">
      <li v-for="event in rows" :key="event.id" class="px-4 py-2.5 space-y-1">
        <div class="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <UiBadge :tone="TONE[event.action]">{{ t(`finance.audit.action.${event.action}`) }}</UiBadge>
          <span class="text-xs font-medium">
            {{ event.actor || t('finance.audit.platform') }}
          </span>
          <span v-if="event.amount" class="num text-xs">
            {{ event.kind ? t(`finance.movements.${event.kind}`) : '' }}
            ${{ money(event.amount) }}
          </span>
          <span v-if="event.account_label" class="text-xs text-ink-muted">
            {{ event.account_label }}
          </span>
          <span class="num text-[0.65rem] text-ink-faint ms-auto">
            {{ dateTime(event.created_at) }}
          </span>
        </div>
        <p v-if="event.before || event.after" class="num text-[0.65rem] text-ink-faint break-words">
          {{ changes(event) }}
        </p>
        <p v-if="event.note" class="text-[0.65rem] text-ink-muted">{{ event.note }}</p>
      </li>
    </ul>

    <div v-else class="p-6">
      <UiEmpty
        icon="history"
        :title="t('finance.audit.empty')"
        :body="t('finance.audit.emptyBody')"
      />
    </div>
  </UiCard>
</template>
