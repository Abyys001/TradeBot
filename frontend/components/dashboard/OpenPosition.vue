<script setup lang="ts">
/**
 * The open trade, leg by leg.
 *
 * Spec §5's promise is that leverage and SL/TP percentages are identical across
 * accounts and only the dollar size differs — so this table puts each leg's
 * margin and quantity next to the shared terms, which is how you *see* the
 * promise being kept rather than take it on faith.
 *
 * A leg that filled without a stop attached is called out in amber, because a
 * live position with no floor is the most expensive thing on this page.
 *
 * PnL comes from the positions endpoint rather than being recomputed here —
 * one Decimal implementation, on the server (see stores/positions.ts).
 */
const { t } = useI18n()
const localePath = useLocalePath()
const trading = useTradingStore()
const positions = usePositionsStore()
const { money, qty, ms, pct } = useFormat()

const trade = computed(() => trading.openTrade)
const filled = computed(() => trade.value?.legs.filter((l) => l.ok) ?? [])
const skipped = computed(() => trade.value?.legs.filter((l) => !l.ok) ?? [])

const totalMargin = computed(() =>
  filled.value.reduce((sum, leg) => sum + Number(leg.margin ?? 0), 0),
)

const pnlOf = (accountId: number) => positions.byAccount(accountId)?.pnl ?? null
const tone = (value: string | number | null) =>
  value === null || Number(value) === 0
    ? 'text-ink-faint'
    : Number(value) > 0
      ? 'text-long'
      : 'text-short'
</script>

<template>
  <UiCard :title="t('dashboard.openPosition')" flush>
    <template #actions>
      <NuxtLink :to="localePath('/chart')" class="btn-ghost btn-sm">
        {{ t('dashboard.manage') }}
      </NuxtLink>
    </template>

    <template v-if="trade">
      <!-- The terms every account shares. -->
      <div class="px-4 py-3 flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-line">
        <span class="num text-sm font-medium">{{ trade.symbol }}</span>
        <UiBadge :tone="trade.side === 'long' ? 'long' : 'short'">
          {{ t(`side.${trade.side}`) }} · {{ trade.leverage }}x
        </UiBadge>
        <span class="text-xs text-ink-muted">
          {{ t('dashboard.sl') }}
          <span class="num text-ink">{{ trade.sl_pct ? pct(trade.sl_pct) : '—' }}</span>
        </span>
        <span class="text-xs text-ink-muted">
          {{ t('dashboard.tp') }}
          <span class="num text-ink">{{ trade.tp_pct ? pct(trade.tp_pct) : '—' }}</span>
        </span>
        <span class="text-xs text-ink-muted ms-auto">
          {{ t('dashboard.committed') }}
          <span class="num text-ink">${{ money(totalMargin) }}</span>
        </span>
        <span v-if="positions.pnl !== null" class="text-xs text-ink-muted">
          {{ t('position.pnl') }}
          <span class="num font-medium" :class="tone(positions.pnl)">
            {{ positions.pnl >= 0 ? '+' : '' }}${{ money(positions.pnl) }}
          </span>
        </span>
      </div>

      <!-- Desktop: a table. Phone: the same rows as cards — a five-column
           table on a 390px screen is a horizontal scroll nobody performs. -->
      <div class="hidden sm:block overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-line">
              <th class="label text-start font-normal px-4 py-2">{{ t('dashboard.account') }}</th>
              <th class="label text-start font-normal py-2">{{ t('dashboard.exchange') }}</th>
              <th class="label text-end font-normal py-2">{{ t('dashboard.margin') }}</th>
              <th class="label text-end font-normal py-2">{{ t('dashboard.qty') }}</th>
              <th class="label text-end font-normal py-2">{{ t('dashboard.entry') }}</th>
              <th class="label text-end font-normal py-2">{{ t('position.pnl') }}</th>
              <th class="label text-end font-normal px-4 py-2">{{ t('dashboard.dispatch') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="leg in filled" :key="leg.id" class="border-b border-line/60 last:border-0">
              <td class="px-4 py-2.5 min-w-0">
                <span class="truncate block">{{ leg.account_label }}</span>
                <span v-if="!leg.sltp_attached" class="label text-signal">
                  {{ t('history.unprotected') }}
                </span>
              </td>
              <td class="text-ink-muted py-2.5">{{ leg.exchange }}</td>
              <td class="num text-end py-2.5">${{ money(leg.margin) }}</td>
              <td class="num text-end py-2.5">{{ qty(leg.qty) }}</td>
              <td class="num text-end py-2.5">{{ money(leg.entry_price) }}</td>
              <td class="num text-end py-2.5" :class="tone(pnlOf(leg.account))">
                {{
                  pnlOf(leg.account) === null
                    ? '—'
                    : `${Number(pnlOf(leg.account)) >= 0 ? '+' : ''}$${money(pnlOf(leg.account))}`
                }}
              </td>
              <td class="num text-end px-4 py-2.5 text-ink-muted">{{ ms(leg.dispatch_ms) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <ul class="sm:hidden divide-y divide-line">
        <li v-for="leg in filled" :key="leg.id" class="p-4 space-y-1.5">
          <div class="flex items-baseline justify-between gap-2">
            <span class="text-sm truncate">{{ leg.account_label }}</span>
            <span class="num text-sm">${{ money(leg.margin) }}</span>
          </div>
          <div class="flex items-baseline justify-between gap-2 text-xs text-ink-muted">
            <span>{{ leg.exchange }}</span>
            <span class="num">{{ qty(leg.qty) }} @ {{ money(leg.entry_price) }}</span>
          </div>
          <p v-if="pnlOf(leg.account) !== null" class="num text-xs" :class="tone(pnlOf(leg.account))">
            {{ Number(pnlOf(leg.account)) >= 0 ? '+' : '' }}${{ money(pnlOf(leg.account)) }}
          </p>
          <p v-if="!leg.sltp_attached" class="label text-signal">{{ t('history.unprotected') }}</p>
        </li>
      </ul>

      <!-- Spec §5: an account below the exchange minimum is skipped, never
           rounded up. Naming which ones is the difference between a rule and
           a silent omission. -->
      <div v-if="skipped.length" class="px-4 py-3 border-t border-line bg-signal/[0.04]">
        <p class="label text-signal">{{ t('dashboard.skipped', { n: skipped.length }) }}</p>
        <ul class="mt-1.5 space-y-1">
          <li v-for="leg in skipped" :key="leg.id" class="text-xs text-ink-muted">
            <span class="text-ink">{{ leg.account_label }}</span> — {{ leg.error }}
          </li>
        </ul>
      </div>
    </template>

    <UiEmpty
      v-else
      icon="terminal"
      :title="t('dashboard.noPositionTitle')"
      :body="t('dashboard.noPositionBody')"
    >
      <NuxtLink :to="localePath('/chart')" class="btn-brand btn-sm">
        {{ t('dashboard.openTerminal') }}
      </NuxtLink>
    </UiEmpty>
  </UiCard>
</template>
