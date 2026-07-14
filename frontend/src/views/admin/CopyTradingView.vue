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
    <h1 class="mb-1 text-xl font-semibold text-zinc-100">{{ t('copyAdmin.title') }}</h1>
    <p class="mb-6 text-sm text-zinc-500">{{ t('copyAdmin.subtitle') }}</p>

    <div class="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatCard :label="t('copyAdmin.investors')" :value="copy.overview?.totals.investor_count ?? 0" />
      <StatCard :label="t('copyAdmin.realized')" :value="'$' + fmt(copy.overview?.totals.realized_pnl)" />
      <StatCard :label="t('copyAdmin.feesAccrued')" :value="'$' + fmt(copy.overview?.totals.fees_accrued)" accent="amber" />
      <StatCard :label="t('copyAdmin.feesOwed')" :value="'$' + fmt(copy.overview?.totals.fees_owed)" accent="amber" :sub="t('copyAdmin.unsettled')" />
    </div>

    <!-- Fee config -->
    <div class="mb-8 rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
      <h2 class="mb-4 text-sm font-medium text-zinc-300">{{ t('copyAdmin.feeConfig') }}</h2>
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500">{{ t('copyAdmin.sharePct') }}</span>
          <input v-model="feeForm.share_pct" type="number" min="0" max="100" step="0.5"
            class="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-violet-500" />
        </label>
        <label class="flex flex-col gap-1 sm:col-span-2">
          <span class="text-xs text-zinc-500">{{ t('copyAdmin.destAccount') }}</span>
          <input v-model="feeForm.destination_account" type="text" :placeholder="t('copyAdmin.destPlaceholder')"
            class="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-sm text-zinc-100 outline-none focus:border-violet-500" />
        </label>
      </div>
      <div class="mt-4 flex items-center gap-3">
        <button type="button" @click="saveFee"
          class="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500">
          {{ t('copyAdmin.save') }}
        </button>
        <span v-if="saved" class="text-sm text-emerald-400">{{ t('copyAdmin.saved') }}</span>
      </div>
    </div>

    <!-- Investors overview -->
    <h2 class="mb-2 text-sm font-medium text-zinc-300">{{ t('copyAdmin.investorTable') }}</h2>
    <div class="mb-8 overflow-x-auto rounded-xl border border-zinc-800">
      <table class="w-full text-left text-sm">
        <thead class="bg-zinc-900/70 text-xs uppercase text-zinc-500">
          <tr>
            <th class="px-4 py-3">{{ t('copyAdmin.investor') }}</th>
            <th class="px-4 py-3">{{ t('copyAdmin.trading') }}</th>
            <th class="px-4 py-3">{{ t('copyAdmin.hwm') }}</th>
            <th class="px-4 py-3">{{ t('copyAdmin.realizedPnl') }}</th>
            <th class="px-4 py-3">{{ t('copyAdmin.fees') }}</th>
            <th class="px-4 py-3">{{ t('copyAdmin.open') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-zinc-800">
          <tr v-for="r in copy.overview?.investors ?? []" :key="r.subscription_id" class="text-zinc-300">
            <td class="px-4 py-2 font-medium text-zinc-100">{{ r.investor }}</td>
            <td class="px-4 py-2">
              <span :class="r.trading_enabled ? 'text-emerald-400' : 'text-zinc-500'">
                {{ r.trading_enabled ? t('copyAdmin.on') : t('copyAdmin.off') }}
              </span>
            </td>
            <td class="px-4 py-2 tabular-nums">{{ fmt(r.high_water_mark) }}</td>
            <td class="px-4 py-2 tabular-nums" :class="Number(r.realized_pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'">
              {{ fmt(r.realized_pnl) }}
            </td>
            <td class="px-4 py-2 tabular-nums text-amber-400">{{ fmt(r.fees_accrued) }}</td>
            <td class="px-4 py-2 tabular-nums">{{ r.open_trades }}</td>
          </tr>
          <tr v-if="!copy.loading && (copy.overview?.investors.length ?? 0) === 0">
            <td colspan="6" class="px-4 py-8 text-center text-zinc-600">{{ t('copyAdmin.noInvestors') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Fee ledger -->
    <div class="mb-2 flex items-center justify-between">
      <h2 class="text-sm font-medium text-zinc-300">{{ t('copyAdmin.ledger') }}</h2>
      <button type="button" @click="settleAll"
        class="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800">
        {{ t('copyAdmin.settleAll') }}
      </button>
    </div>
    <div class="overflow-x-auto rounded-xl border border-zinc-800">
      <table class="w-full text-left text-sm">
        <thead class="bg-zinc-900/70 text-xs uppercase text-zinc-500">
          <tr>
            <th class="px-4 py-3">{{ t('copyAdmin.investor') }}</th>
            <th class="px-4 py-3">{{ t('copyAdmin.amount') }}</th>
            <th class="px-4 py-3">%</th>
            <th class="px-4 py-3">{{ t('copyAdmin.status') }}</th>
            <th class="px-4 py-3">{{ t('copyAdmin.accrued') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-zinc-800">
          <tr v-for="l in copy.ledger" :key="l.id" class="text-zinc-300">
            <td class="px-4 py-2">{{ l.investor }}</td>
            <td class="px-4 py-2 tabular-nums text-amber-400">{{ fmt(l.amount) }}</td>
            <td class="px-4 py-2 tabular-nums">{{ fmt(l.share_pct, 1) }}</td>
            <td class="px-4 py-2">
              <span :class="l.status === 'settled' ? 'text-emerald-400' : 'text-amber-400'">{{ l.status }}</span>
            </td>
            <td class="px-4 py-2 text-zinc-500">{{ new Date(l.accrued_at).toLocaleDateString() }}</td>
          </tr>
          <tr v-if="!copy.loading && copy.ledger.length === 0">
            <td colspan="5" class="px-4 py-8 text-center text-zinc-600">{{ t('copyAdmin.noLedger') }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
