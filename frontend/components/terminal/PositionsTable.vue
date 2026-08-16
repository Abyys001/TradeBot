<script setup lang="ts">
/**
 * The open position, account by account (spec §3 + §5).
 *
 * The aggregate in the bar above answers "how am I doing"; this answers "and
 * did every account actually get there". They are different questions: spec §5
 * makes each account's dollar size differ, and spec §4 lets one account fail
 * while the rest fill — so a single blended number can look healthy while one
 * partner is sitting flat or, worse, unprotected.
 *
 * Failed legs are listed with the filled ones rather than hidden behind a
 * filter. An account that did not get in is a fact about this trade.
 */
const { t } = useI18n()
const positions = usePositionsStore()
const { money, pct, qty } = useFormat()

const rows = computed(() =>
  [...positions.legs].sort((a, b) => Number(b.notional ?? 0) - Number(a.notional ?? 0)),
)

function tone(value: string | null) {
  const n = Number(value ?? 0)
  return n === 0 ? 'text-ink-faint' : n > 0 ? 'text-long' : 'text-short'
}
</script>

<template>
  <div v-if="positions.hasPosition">
    <!-- Table from sm up -->
    <div class="hidden sm:block overflow-x-auto">
      <table class="w-full text-xs">
        <thead>
          <tr class="border-b border-line">
            <th class="label text-start font-normal px-4 py-2">{{ t('dashboard.account') }}</th>
            <th class="label text-end font-normal py-2">{{ t('dashboard.qty') }}</th>
            <th class="label text-end font-normal py-2">{{ t('dashboard.entry') }}</th>
            <th class="label text-end font-normal py-2">{{ t('position.margin') }}</th>
            <th class="label text-end font-normal py-2">{{ t('ticket.sl') }}</th>
            <th class="label text-end font-normal py-2">{{ t('ticket.tp') }}</th>
            <th class="label text-end font-normal py-2">{{ t('position.liquidation') }}</th>
            <th class="label text-end font-normal px-4 py-2">{{ t('position.pnl') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="leg in rows"
            :key="leg.account"
            class="border-b border-line/50 last:border-0"
            :class="leg.ok ? '' : 'opacity-70'"
          >
            <td class="px-4 py-2">
              <div class="flex items-center gap-2 min-w-0">
                <span class="truncate">{{ leg.account_label }}</span>
                <UiBadge v-if="leg.ok && !leg.sltp_attached" tone="signal">
                  {{ t('position.noStop') }}
                </UiBadge>
                <UiBadge
                  v-else-if="leg.ok && !leg.sltp_verified"
                  tone="signal"
                  :title="t('position.unconfirmed')"
                >
                  {{ t('position.unconfirmed') }}
                </UiBadge>
                <UiBadge v-if="!leg.ok" tone="short">{{ t('position.notFilled') }}</UiBadge>
              </div>
              <p v-if="!leg.ok && leg.error" class="text-[0.65rem] text-short truncate max-w-xs">
                {{ leg.error }}
              </p>
            </td>
            <td class="num text-end py-2">{{ qty(leg.qty) }}</td>
            <td class="num text-end py-2">{{ money(leg.entry_price) }}</td>
            <td class="num text-end py-2">${{ money(leg.margin) }}</td>
            <td class="num text-end py-2 text-short">{{ money(leg.stop_loss) }}</td>
            <td class="num text-end py-2 text-long">{{ money(leg.take_profit) }}</td>
            <td class="num text-end py-2 text-signal">{{ money(leg.liquidation_price) }}</td>
            <td class="num text-end px-4 py-2" :class="tone(leg.pnl)">
              <template v-if="leg.pnl === null">—</template>
              <template v-else>
                {{ Number(leg.pnl) >= 0 ? '+' : '' }}${{ money(leg.pnl) }}
                <span v-if="leg.roe_pct" class="block text-[0.65rem]">
                  {{ Number(leg.roe_pct) >= 0 ? '+' : '' }}{{ pct(leg.roe_pct) }}
                </span>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Cards below sm -->
    <ul class="sm:hidden divide-y divide-line">
      <li v-for="leg in rows" :key="leg.account" class="px-4 py-3 space-y-1.5">
        <div class="flex items-baseline justify-between gap-2">
          <span class="text-xs truncate">{{ leg.account_label }}</span>
          <span class="num text-xs" :class="tone(leg.pnl)">
            {{ leg.pnl === null ? '—' : `${Number(leg.pnl) >= 0 ? '+' : ''}$${money(leg.pnl)}` }}
          </span>
        </div>
        <p v-if="leg.ok" class="num text-[0.65rem] text-ink-faint">
          {{ qty(leg.qty) }} @ {{ money(leg.entry_price) }} · ${{ money(leg.margin) }}
          {{ t('position.margin').toLowerCase() }}
        </p>
        <p v-else class="text-[0.65rem] text-short">{{ leg.error }}</p>
        <UiBadge v-if="leg.ok && !leg.sltp_attached" tone="signal">
          {{ t('position.noStop') }}
        </UiBadge>
        <UiBadge v-else-if="leg.ok && !leg.sltp_verified" tone="signal">
          {{ t('position.unconfirmed') }}
        </UiBadge>
      </li>
    </ul>
  </div>

  <UiEmpty
    v-else
    icon="terminal"
    :title="t('position.flatTitle')"
    :body="t('position.flatBody')"
    class="py-6"
  />
</template>
