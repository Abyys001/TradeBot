<script setup lang="ts">
/**
 * The money that entered and left this account, and what is still unexplained.
 *
 * Read-only on purpose. Recording, editing and deleting a cash flow all leave
 * an audit entry with the actor and the before/after
 * (`apps/accounts/bookkeeping.py`), and one write path with one form is how it
 * stays that way — the finance page owns it, and this links there rather than
 * growing a second one.
 */
const props = defineProps<{ report: AccountReport }>()

const { t } = useI18n()
const localePath = useLocalePath()
const { money, signed, dateTime } = useFormat()

const deposits = computed(() =>
  props.report.movements.filter((movement) => movement.kind === 'deposit'),
)
const withdrawals = computed(() =>
  props.report.movements.filter((movement) => movement.kind === 'withdrawal'),
)

/** Still waiting on an answer — the resolved ones live in the audit trail. */
const pending = computed(() =>
  props.report.detections.filter((detection) => detection.status === 'pending'),
)
</script>

<template>
  <div class="space-y-3 sm:space-y-4">
    <UiCard :title="t('accounts.report.cash.title')" :hint="t('accounts.report.cash.hint')" flush>
      <template #actions>
        <NuxtLink :to="localePath('/finance')" class="btn-ghost btn-sm">
          <UiIcon name="ledger" :size="13" />
          {{ t('accounts.report.cash.record') }}
        </NuxtLink>
      </template>

      <dl class="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm p-4 border-b border-line">
        <div>
          <dt class="label">{{ t('finance.table.deposits') }}</dt>
          <dd class="num mt-1 text-long">${{ money(report.ledger.deposits) }}</dd>
          <dd class="text-[0.65rem] text-ink-faint mt-0.5">
            {{ t('accounts.report.cash.count', { n: deposits.length }) }}
          </dd>
        </div>
        <div>
          <dt class="label">{{ t('finance.table.withdrawals') }}</dt>
          <dd class="num mt-1 text-short">${{ money(report.ledger.withdrawals) }}</dd>
          <dd class="text-[0.65rem] text-ink-faint mt-0.5">
            {{ t('accounts.report.cash.count', { n: withdrawals.length }) }}
          </dd>
        </div>
        <div>
          <dt class="label">{{ t('finance.table.net') }}</dt>
          <dd class="num mt-1">${{ money(report.ledger.net_invested) }}</dd>
        </div>
        <div>
          <dt class="label">{{ t('finance.table.current') }}</dt>
          <dd class="num mt-1">
            {{ report.ledger.current_balance === null ? '—' : `$${money(report.ledger.current_balance)}` }}
          </dd>
          <dd class="text-[0.65rem] text-ink-faint mt-0.5">{{ report.ledger.asset }}</dd>
        </div>
      </dl>

      <ul v-if="report.movements.length" class="divide-y divide-line">
        <li
          v-for="movement in report.movements"
          :key="movement.id"
          class="px-4 py-3 flex flex-wrap items-center gap-x-3 gap-y-1"
        >
          <UiBadge :tone="movement.kind === 'deposit' ? 'ok' : 'signal'">
            {{ t(`finance.movements.${movement.kind}`) }}
          </UiBadge>
          <span
            class="num text-sm font-medium"
            :class="movement.kind === 'deposit' ? 'text-long' : 'text-short'"
          >
            {{ movement.kind === 'deposit' ? '+' : '−' }}${{ money(movement.amount) }}
          </span>
          <span class="text-xs text-ink-faint num">{{ movement.asset }}</span>
          <!-- A row the platform proposed and an operator accepted is not the
               same as one somebody typed in, and the ledger keeps them apart. -->
          <UiBadge v-if="movement.source === 'detected'" tone="brand">
            {{ t('finance.movements.detected') }}
          </UiBadge>
          <span v-if="movement.note" class="text-xs text-ink-muted min-w-0 truncate">
            {{ movement.note }}
          </span>
          <span class="ms-auto text-end">
            <span class="num text-xs">{{ dateTime(movement.occurred_at) }}</span>
            <span v-if="movement.created_by" class="block text-[0.65rem] text-ink-faint">
              {{ t('finance.movements.by', { who: movement.created_by }) }}
            </span>
          </span>
        </li>
      </ul>

      <div v-else class="p-6">
        <UiEmpty
          icon="ledger"
          :title="t('finance.movements.empty')"
          :body="t('finance.movements.emptyBody')"
        />
      </div>
    </UiCard>

    <!-- Proposals, never entries: nothing here has touched the ledger yet. -->
    <UiCard
      v-if="pending.length"
      tone="signal"
      :title="t('finance.detect.title')"
      :hint="t('finance.detect.subtitle')"
      flush
    >
      <template #actions>
        <NuxtLink :to="localePath('/finance')" class="btn-ghost btn-sm">
          {{ t('accounts.report.cash.resolve') }}
        </NuxtLink>
      </template>
      <ul class="divide-y divide-line">
        <li v-for="detection in pending" :key="detection.id" class="px-4 py-3 space-y-1">
          <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span class="num text-sm font-medium">{{ signed(detection.unexplained) }}</span>
            <UiBadge tone="signal">{{ t(`finance.movements.${detection.suggested_kind}`) }}</UiBadge>
            <span class="num text-[0.65rem] text-ink-faint ms-auto">
              {{ dateTime(detection.observed_at) }}
            </span>
          </div>
          <!-- The whole subtraction, so it can be checked without leaving the row. -->
          <p class="num text-[0.65rem] text-ink-faint">
            {{ t('finance.detect.equity') }} {{ money(detection.previous_equity) }} →
            {{ money(detection.current_equity) }} ·
            {{ t('finance.detect.trades') }} {{ signed(detection.trade_pnl) }} ·
            {{ t('finance.detect.recorded') }} {{ signed(detection.manual_net) }}
          </p>
        </li>
      </ul>
    </UiCard>
  </div>
</template>
