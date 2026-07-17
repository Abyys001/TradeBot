<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useCopyTradingStore } from '../../stores/copytrading'
import StatCard from '../../modules/overview/StatCard.vue'

const { t } = useI18n()
const copy = useCopyTradingStore()

const feeForm = reactive({ share_pct: '20', destination_account: '', destination_exchange: 'tabdeal' })
const saved = ref(false)

watch(
  () => copy.feeConfig,
  (c) => {
    if (c) {
      feeForm.share_pct = c.share_pct
      feeForm.destination_account = c.destination_account
      feeForm.destination_exchange = c.destination_exchange
    }
  },
)

async function saveFee() {
  await copy.saveFeeConfig({ ...feeForm })
  saved.value = true
  setTimeout(() => (saved.value = false), 2000)
}

async function settleAll() {
  const ids = copy.ledger.filter((l) => l.status === 'accrued').map((l) => l.id)
  if (ids.length) await copy.settle(ids)
}

function fmt(v: string | number | undefined, dp = 2) {
  return Number(v ?? 0).toLocaleString(undefined, { maximumFractionDigits: dp })
}

onMounted(() => copy.fetchAdmin())
</script>

<template>
  <div class="mx-auto max-w-6xl p-6">
    <h1 class="mb-1 text-xl font-semibold text-fg">{{ t('copyAdmin.title') }}</h1>
    <p class="mb-6 text-sm text-fg-muted">{{ t('copyAdmin.subtitle') }}</p>

    <div class="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatCard :label="t('copyAdmin.investors')" :value="copy.overview?.totals.investor_count ?? 0" />
      <StatCard :label="t('copyAdmin.realized')" :value="'$' + fmt(copy.overview?.totals.realized_pnl)" />
      <StatCard :label="t('copyAdmin.feesAccrued')" :value="'$' + fmt(copy.overview?.totals.fees_accrued)" accent="amber" />
      <StatCard :label="t('copyAdmin.feesOwed')" :value="'$' + fmt(copy.overview?.totals.fees_owed)" accent="amber" :sub="t('copyAdmin.unsettled')" />
    </div>

    <!-- Fee config -->
    <div class="mb-8 rounded-xl border border-border bg-surface-raised p-5">
      <h2 class="mb-4 text-sm font-medium text-fg">{{ t('copyAdmin.feeConfig') }}</h2>
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label class="flex flex-col gap-1">
          <span class="text-xs text-fg-muted">{{ t('copyAdmin.sharePct') }}</span>
          <input v-model="feeForm.share_pct" type="number" min="0" max="100" step="0.5"
            class="rounded-lg border border-border bg-surface px-3 py-2 text-sm text-fg outline-none focus:border-accent" />
        </label>
        <label class="flex flex-col gap-1 sm:col-span-2">
          <span class="text-xs text-fg-muted">{{ t('copyAdmin.destAccount') }}</span>
          <input v-model="feeForm.destination_account" type="text" :placeholder="t('copyAdmin.destPlaceholder')"
            class="rounded-lg border border-border bg-surface px-3 py-2 font-mono text-sm text-fg outline-none focus:border-accent" />
        </label>
      </div>
      <div class="mt-4 flex items-center gap-3">
        <button type="button" @click="saveFee"
          class="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-fg hover:opacity-90">
          {{ t('copyAdmin.save') }}
        </button>
        <span v-if="saved" class="text-sm text-positive">{{ t('copyAdmin.saved') }}</span>
      </div>
    </div>

    <!-- Investors overview -->
    <h2 class="mb-2 text-sm font-medium text-fg">{{ t('copyAdmin.investorTable') }}</h2>
    <div class="mb-8 overflow-x-auto rounded-xl border border-border">
      <table class="w-full text-left text-sm">
        <thead class="bg-surface-raised text-xs uppercase text-fg-muted">
          <tr>
            <th class="px-4 py-3">{{ t('copyAdmin.investor') }}</th>
            <th class="px-4 py-3">{{ t('copyAdmin.trading') }}</th>
            <th class="px-4 py-3">{{ t('copyAdmin.hwm') }}</th>
            <th class="px-4 py-3">{{ t('copyAdmin.realizedPnl') }}</th>
            <th class="px-4 py-3">{{ t('copyAdmin.fees') }}</th>
            <th class="px-4 py-3">{{ t('copyAdmin.open') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border">
          <tr v-for="r in copy.overview?.investors ?? []" :key="r.subscription_id" class="text-fg">
            <td class="px-4 py-2 font-medium text-fg">{{ r.investor }}</td>
            <td class="px-4 py-2">
              <span :class="r.trading_enabled ? 'text-positive' : 'text-fg-muted'">
                {{ r.trading_enabled ? t('copyAdmin.on') : t('copyAdmin.off') }}
              </span>
            </td>
            <td class="px-4 py-2 tabular-nums">{{ fmt(r.high_water_mark) }}</td>
            <td class="px-4 py-2 tabular-nums" :class="Number(r.realized_pnl) >= 0 ? 'text-positive' : 'text-negative'">
              {{ fmt(r.realized_pnl) }}
            </td>
            <td class="px-4 py-2 tabular-nums text-warning">{{ fmt(r.fees_accrued) }}</td>
            <td class="px-4 py-2 tabular-nums">{{ r.open_trades }}</td>
          </tr>
          <tr v-if="!copy.loading && (copy.overview?.investors.length ?? 0) === 0">
            <td colspan="6" class="px-4 py-8 text-center text-fg-muted">{{ t('copyAdmin.noInvestors') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Fee ledger -->
    <div class="mb-2 flex items-center justify-between">
      <h2 class="text-sm font-medium text-fg">{{ t('copyAdmin.ledger') }}</h2>
      <button type="button" @click="settleAll"
        class="rounded-lg border border-border px-3 py-1.5 text-xs text-fg hover:bg-surface-raised">
        {{ t('copyAdmin.settleAll') }}
      </button>
    </div>
    <div class="overflow-x-auto rounded-xl border border-border">
      <table class="w-full text-left text-sm">
        <thead class="bg-surface-raised text-xs uppercase text-fg-muted">
          <tr>
            <th class="px-4 py-3">{{ t('copyAdmin.investor') }}</th>
            <th class="px-4 py-3">{{ t('copyAdmin.amount') }}</th>
            <th class="px-4 py-3">%</th>
            <th class="px-4 py-3">{{ t('copyAdmin.status') }}</th>
            <th class="px-4 py-3">{{ t('copyAdmin.accrued') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border">
          <tr v-for="l in copy.ledger" :key="l.id" class="text-fg">
            <td class="px-4 py-2">{{ l.investor }}</td>
            <td class="px-4 py-2 tabular-nums text-warning">{{ fmt(l.amount) }}</td>
            <td class="px-4 py-2 tabular-nums">{{ fmt(l.share_pct, 1) }}</td>
            <td class="px-4 py-2">
              <span :class="l.status === 'settled' ? 'text-positive' : 'text-warning'">{{ l.status }}</span>
            </td>
            <td class="px-4 py-2 text-fg-muted">{{ new Date(l.accrued_at).toLocaleDateString() }}</td>
          </tr>
          <tr v-if="!copy.loading && copy.ledger.length === 0">
            <td colspan="5" class="px-4 py-8 text-center text-fg-muted">{{ t('copyAdmin.noLedger') }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
