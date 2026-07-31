<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchCsrf } from '../../api/client'
import { useCopytradingStore } from '../../stores/copytrading'
import { useToast } from '../../composables/useToast'

const store = useCopytradingStore()
const toast = useToast()
const feeRate = ref('0.20')
const loading = ref(true)

onMounted(async () => {
  await fetchCsrf()
  try {
    await Promise.all([store.fetchInvestors(), store.fetchLedger(), store.fetchFeeConfig()])
    if (store.feeConfig?.fee_rate) feeRate.value = store.feeConfig.fee_rate
  } finally {
    loading.value = false
  }
})

async function saveFee() {
  try {
    await store.setFeeConfig(feeRate.value)
    toast.show('Fee rate updated', 'success')
  } catch {
    toast.show('Failed to update fee', 'error')
  }
}
</script>

<template>
  <div class="flex-1 overflow-y-auto p-6 space-y-8">
    <h1 class="text-lg font-semibold text-zinc-200">Admin Dashboard</h1>

    <div v-if="loading" class="text-sm text-zinc-500">Loading…</div>

    <template v-else>
      <!-- Fee config -->
      <section class="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 max-w-sm">
        <h2 class="text-sm font-medium text-zinc-200">Platform fee</h2>
        <p class="text-xs text-zinc-500 mb-3">Fraction of new profit (above each investor's high-water mark).</p>
        <div class="flex items-end gap-2">
          <label class="block text-xs text-zinc-500 flex-1">
            Fee rate (0.20 = 20%)
            <input
              v-model="feeRate"
              type="number" step="0.01" min="0" max="1"
              class="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200"
            />
          </label>
          <button
            type="button"
            class="rounded-lg bg-violet-700 px-4 py-2 text-sm font-medium text-white hover:bg-violet-600"
            @click="saveFee"
          >Save</button>
        </div>
      </section>

      <!-- Investors -->
      <section class="space-y-2">
        <h2 class="text-sm font-medium text-zinc-200">Investors</h2>
        <div class="overflow-x-auto rounded-lg border border-zinc-800">
          <table class="w-full text-sm">
            <thead class="bg-zinc-900/60 text-zinc-400">
              <tr>
                <th class="px-4 py-2 text-left">Username</th>
                <th class="px-4 py-2 text-left">Email</th>
                <th class="px-4 py-2 text-right">Subscriptions</th>
                <th class="px-4 py-2 text-right">Trading</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="inv in store.investors" :key="inv.id" class="border-t border-zinc-800">
                <td class="px-4 py-2 text-zinc-200">{{ inv.username }}</td>
                <td class="px-4 py-2 text-zinc-400">{{ inv.email || '—' }}</td>
                <td class="px-4 py-2 text-right text-zinc-300">{{ inv.subscriptions }}</td>
                <td class="px-4 py-2 text-right">
                  <span :class="inv.is_trading_enabled ? 'text-emerald-400' : 'text-zinc-500'">
                    {{ inv.is_trading_enabled ? 'on' : 'off' }}
                  </span>
                </td>
              </tr>
              <tr v-if="!store.investors.length">
                <td colspan="4" class="px-4 py-3 text-center text-zinc-500">No investors yet.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Fee ledger -->
      <section class="space-y-2">
        <h2 class="text-sm font-medium text-zinc-200">Fee ledger</h2>
        <div class="overflow-x-auto rounded-lg border border-zinc-800">
          <table class="w-full text-sm">
            <thead class="bg-zinc-900/60 text-zinc-400">
              <tr>
                <th class="px-4 py-2 text-left">Investor</th>
                <th class="px-4 py-2 text-right">Realized PnL</th>
                <th class="px-4 py-2 text-right">High-water mark</th>
                <th class="px-4 py-2 text-right">Fee accrued</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="l in store.ledger" :key="l.id" class="border-t border-zinc-800">
                <td class="px-4 py-2 text-zinc-200">{{ l.investor }}</td>
                <td class="px-4 py-2 text-right text-zinc-300">{{ l.realized_pnl }}</td>
                <td class="px-4 py-2 text-right text-zinc-400">{{ l.high_water_mark }}</td>
                <td class="px-4 py-2 text-right text-emerald-400">{{ l.fee_accrued }}</td>
              </tr>
              <tr v-if="!store.ledger.length">
                <td colspan="4" class="px-4 py-3 text-center text-zinc-500">No fees accrued yet.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>
