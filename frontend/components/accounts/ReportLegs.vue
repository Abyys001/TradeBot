<script setup lang="ts">
/**
 * Every leg this account was given, newest first — the small trades and the
 * small results the account page is opened for.
 *
 * A leg, not a trade: one admin action fans out to N accounts, and what this
 * account got is one of those N. So the row shows the pair and side it
 * inherited from the trade next to the size, price and PnL that are its own,
 * and a leg that never filled keeps its row with the reason on it. Dropping
 * failures would make the log read as if the fan-out always lands.
 */
const props = defineProps<{ report: AccountReport }>()

const { t } = useI18n()
const { money, qty, pct, dateTime, ms } = useFormat()

const filter = ref<'all' | 'open' | 'closed' | 'failed'>('all')

const rows = computed(() => {
  const legs = props.report.legs
  if (filter.value === 'open') return legs.filter((leg) => leg.open)
  if (filter.value === 'closed') return legs.filter((leg) => leg.ok && !leg.open)
  if (filter.value === 'failed') return legs.filter((leg) => !leg.ok)
  return legs
})

const options = computed(() => [
  { value: 'all', label: `${t('history.all')} ${props.report.trading.legs}` },
  { value: 'open', label: `${t('history.open')} ${props.report.trading.open}` },
  { value: 'closed', label: `${t('accounts.report.legs.closed')} ${props.report.trading.scored}` },
  {
    value: 'failed',
    label: `${t('accounts.report.legs.failed')} ${props.report.trading.failed}`,
    tone: 'short' as const,
  },
])

function pnlText(value: string | null): string {
  if (value === null) return '—'
  const n = Number(value)
  return `${n > 0 ? '+' : n < 0 ? '−' : ''}$${money(Math.abs(n))}`
}

function pnlClass(value: string | null): string {
  const n = Number(value)
  if (value === null || Number.isNaN(n) || n === 0) return 'text-ink'
  return n > 0 ? 'text-long' : 'text-short'
}
</script>

<template>
  <UiCard flush>
    <template #header>
      <div class="overflow-x-auto no-scrollbar -my-1 py-1">
        <UiSegmented v-model="filter" :options="options" size="sm" :block="false" />
      </div>
    </template>
    <template #actions>
      <span v-if="report.legs.length >= report.leg_limit" class="text-xs text-ink-faint">
        {{ t('accounts.report.legs.capped', { n: report.leg_limit }) }}
      </span>
    </template>

    <template v-if="rows.length">
      <!-- Table, sm and up -->
      <div class="hidden sm:block overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-line">
              <th class="label text-start font-normal px-4 py-2.5">{{ t('accounts.report.legs.pair') }}</th>
              <th class="label text-end font-normal py-2.5">{{ t('accounts.report.legs.size') }}</th>
              <th class="label text-end font-normal py-2.5">{{ t('accounts.report.legs.entry') }}</th>
              <th class="label text-end font-normal py-2.5">{{ t('accounts.report.legs.exit') }}</th>
              <th class="label text-end font-normal py-2.5">{{ t('accounts.report.legs.margin') }}</th>
              <th class="label text-end font-normal py-2.5">{{ t('accounts.report.legs.pnl') }}</th>
              <th class="label text-end font-normal px-4 py-2.5">{{ t('accounts.report.legs.opened') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="leg in rows"
              :key="leg.id"
              class="border-b border-line/60 last:border-0 hover:bg-raised/60 transition-colors"
            >
              <td class="px-4 py-3 min-w-0">
                <div class="flex flex-wrap items-center gap-1.5">
                  <span class="num font-medium">{{ leg.symbol }}</span>
                  <UiBadge :tone="leg.side === 'long' ? 'long' : 'short'">
                    {{ t(`side.${leg.side}`) }} {{ leg.leverage }}x
                  </UiBadge>
                  <UiBadge v-if="leg.open" tone="brand" dot>{{ t('history.open') }}</UiBadge>
                  <UiBadge v-if="!leg.ok" tone="short">
                    {{ leg.error_code || t('accounts.report.legs.failed') }}
                  </UiBadge>
                  <!-- Q5e: the entry filled and the protection did not. It is a
                       different state from a failed leg and a worse one. -->
                  <UiBadge v-if="leg.ok && !leg.sltp_attached" tone="signal">
                    {{ t('accounts.report.legs.noSltp') }}
                  </UiBadge>
                </div>
                <p v-if="leg.error" class="text-xs text-signal mt-0.5 truncate max-w-md">
                  {{ leg.error }}
                </p>
              </td>
              <td class="text-end py-3 num whitespace-nowrap">
                {{ qty(leg.qty) }}
                <p v-if="leg.notional" class="text-[0.65rem] text-ink-faint">
                  ${{ money(leg.notional) }}
                </p>
              </td>
              <td class="text-end py-3 num whitespace-nowrap">{{ money(leg.entry_price, 4) }}</td>
              <td class="text-end py-3 num whitespace-nowrap">{{ money(leg.exit_price, 4) }}</td>
              <td class="text-end py-3 num whitespace-nowrap">{{ money(leg.margin) }}</td>
              <td class="text-end py-3 num whitespace-nowrap" :class="pnlClass(leg.pnl)">
                {{ pnlText(leg.pnl) }}
                <!-- Return on the margin this leg locked up, which is what the
                     exchange's own screen shows — not return on the account. -->
                <p v-if="leg.roe_pct" class="text-[0.65rem] text-ink-faint">
                  {{ pct(leg.roe_pct) }}
                </p>
              </td>
              <td class="px-4 py-3 text-end whitespace-nowrap">
                <span class="num text-xs">{{ dateTime(leg.opened_at) }}</span>
                <p class="text-[0.65rem] text-ink-faint">
                  {{ leg.closed_at ? dateTime(leg.closed_at) : t('history.open') }}
                  <span v-if="leg.dispatch_ms !== null"> · {{ ms(leg.dispatch_ms) }}</span>
                </p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Cards, below sm -->
      <ul class="sm:hidden divide-y divide-line">
        <li v-for="leg in rows" :key="leg.id" class="p-4 space-y-2">
          <div class="flex items-start gap-2">
            <div class="min-w-0 flex-1">
              <p class="num font-medium">{{ leg.symbol }}</p>
              <p class="text-xs text-ink-muted">{{ dateTime(leg.opened_at) }}</p>
            </div>
            <p class="num text-sm" :class="pnlClass(leg.pnl)">{{ pnlText(leg.pnl) }}</p>
          </div>
          <div class="flex flex-wrap gap-1.5">
            <UiBadge :tone="leg.side === 'long' ? 'long' : 'short'">
              {{ t(`side.${leg.side}`) }} {{ leg.leverage }}x
            </UiBadge>
            <UiBadge v-if="leg.open" tone="brand" dot>{{ t('history.open') }}</UiBadge>
            <UiBadge v-if="!leg.ok" tone="short">
              {{ leg.error_code || t('accounts.report.legs.failed') }}
            </UiBadge>
          </div>
          <dl class="grid grid-cols-3 gap-2 text-xs">
            <div>
              <dt class="label">{{ t('accounts.report.legs.size') }}</dt>
              <dd class="num">{{ qty(leg.qty) }}</dd>
            </div>
            <div>
              <dt class="label">{{ t('accounts.report.legs.entry') }}</dt>
              <dd class="num">{{ money(leg.entry_price, 4) }}</dd>
            </div>
            <div>
              <dt class="label">{{ t('accounts.report.legs.margin') }}</dt>
              <dd class="num">{{ money(leg.margin) }}</dd>
            </div>
          </dl>
          <p v-if="leg.error" class="text-xs text-signal">{{ leg.error }}</p>
        </li>
      </ul>
    </template>

    <UiEmpty
      v-else
      icon="history"
      :title="t('accounts.report.noTrades')"
      :body="t('accounts.report.noTradesBody')"
    />
  </UiCard>
</template>
