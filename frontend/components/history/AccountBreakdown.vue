<script lang="ts">
/** One account's share of the trades currently in view. */
export interface AccountRow {
  account: number
  label: string
  exchange: string
  /** Legs in view, settled or not. */
  legs: number
  /** Legs with a PnL the exchange has confirmed. */
  settled: number
  wins: number
  failed: number
  pnl: number
  margin: number
}
</script>

<script setup lang="ts">
/**
 * What each account actually made, in dollars and as a percentage.
 *
 * The trade log answers "what did this platform do"; one row per trade, with
 * the accounts folded away inside it. That is the wrong shape for the question
 * the admin opens this page with, which is about the partners' money: *this*
 * account is up, *that* one is down, and by how much relative to what it put
 * in. Reading that out of the log means expanding every trade and adding legs
 * up by hand, so it gets its own table.
 *
 * The percentage is **return on the margin that account committed**, not on its
 * balance: margin is the money the trade actually used, and it is the only base
 * under which two accounts of different size are comparable at all — which is
 * the whole point of a platform that routes one decision to N wallets.
 *
 * Nothing here is recomputed from prices. Every figure is a sum of PnL the
 * server already settled, so this table and the trade log cannot disagree.
 */
const props = defineProps<{ rows: AccountRow[]; loading?: boolean }>()

const { t } = useI18n()
const { money } = useFormat()

/** Return on committed margin. `null` when nothing has settled to divide by. */
function ret(row: AccountRow): number | null {
  return row.settled && row.margin > 0 ? (row.pnl / row.margin) * 100 : null
}

function signedMoney(value: number): string {
  return `${value > 0 ? '+' : value < 0 ? '−' : ''}$${money(Math.abs(value))}`
}

function tone(value: number, settled: number): string {
  if (!settled || value === 0) return 'text-ink-faint'
  return value > 0 ? 'text-long' : 'text-short'
}

/** Bar width relative to the biggest mover, so the column is scannable. */
const peak = computed(() => Math.max(...props.rows.map((r) => Math.abs(r.pnl)), 0) || 1)
</script>

<template>
  <UiCard flush>
    <template #header>
      <div class="min-w-0">
        <h2 class="text-sm font-medium">{{ t('history.byAccount.title') }}</h2>
        <p class="text-xs text-ink-muted mt-0.5">{{ t('history.byAccount.hint') }}</p>
      </div>
    </template>

    <div v-if="loading" class="p-4 space-y-2">
      <div v-for="i in 3" :key="i" class="skeleton h-8 rounded" />
    </div>

    <!-- Table on anything wide enough to hold seven columns honestly. -->
    <div v-else class="hidden md:block overflow-x-auto">
      <table class="w-full text-xs">
        <thead>
          <tr class="border-b border-line">
            <th class="label text-start font-normal px-4 py-2">
              {{ t('history.byAccount.account') }}
            </th>
            <th class="label text-end font-normal py-2">{{ t('history.byAccount.legs') }}</th>
            <th class="label text-end font-normal py-2">{{ t('history.byAccount.wins') }}</th>
            <th class="label text-end font-normal py-2">{{ t('history.byAccount.margin') }}</th>
            <th class="label text-end font-normal py-2">{{ t('history.byAccount.pnl') }}</th>
            <th class="label text-end font-normal py-2">{{ t('history.byAccount.return') }}</th>
            <th class="label text-start font-normal px-4 py-2 w-32">
              <span class="sr-only">{{ t('history.byAccount.pnl') }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.account" class="border-b border-line/50 last:border-0">
            <td class="px-4 py-2">
              <span class="font-medium">{{ row.label }}</span>
              <span class="text-ink-faint ms-2">{{ row.exchange }}</span>
            </td>
            <td class="num text-end py-2 text-ink-muted">
              {{ row.legs }}
              <span v-if="row.failed" class="text-short ms-1">−{{ row.failed }}</span>
            </td>
            <td class="num text-end py-2 text-ink-muted">
              {{ row.settled ? `${row.wins}/${row.settled}` : '—' }}
            </td>
            <td class="num text-end py-2 text-ink-muted">
              {{ row.margin > 0 ? `$${money(row.margin)}` : '—' }}
            </td>
            <td class="num text-end py-2 font-medium" :class="tone(row.pnl, row.settled)">
              {{ row.settled ? signedMoney(row.pnl) : '—' }}
            </td>
            <td class="num text-end py-2" :class="tone(row.pnl, row.settled)">
              {{ ret(row) === null ? '—' : `${row.pnl > 0 ? '+' : ''}${ret(row)!.toFixed(2)}%` }}
            </td>
            <td class="px-4 py-2">
              <div class="h-1.5 rounded-full bg-raised overflow-hidden flex" aria-hidden="true">
                <div
                  class="h-full rounded-full"
                  :class="row.pnl >= 0 ? 'bg-long' : 'bg-short'"
                  :style="{ width: `${(Math.abs(row.pnl) / peak) * 100}%` }"
                />
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Phone: the same numbers, stacked. Seven columns on 360px is a lie. -->
    <ul v-if="!loading" class="md:hidden divide-y divide-line">
      <li v-for="row in rows" :key="row.account" class="px-4 py-3 space-y-1">
        <div class="flex items-baseline justify-between gap-2">
          <span class="text-xs font-medium truncate">{{ row.label }}</span>
          <span class="num text-xs font-medium" :class="tone(row.pnl, row.settled)">
            {{ row.settled ? signedMoney(row.pnl) : '—' }}
            <template v-if="ret(row) !== null">
              ({{ row.pnl > 0 ? '+' : '' }}{{ ret(row)!.toFixed(2) }}%)
            </template>
          </span>
        </div>
        <p class="text-[0.65rem] text-ink-faint num">
          {{ row.exchange }} ·
          {{ t('history.byAccount.legsCount', { n: row.legs }) }} ·
          {{ row.settled ? `${row.wins}/${row.settled}` : t('history.byAccount.noneSettled') }}
        </p>
      </li>
    </ul>
  </UiCard>
</template>
