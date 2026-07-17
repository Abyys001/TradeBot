<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchCsrf } from '../../api/client'
import { useCopytradingStore } from '../../stores/copytrading'

const store = useCopytradingStore()
const loading = ref(true)

onMounted(async () => {
  await fetchCsrf()
  try {
    await Promise.all([
      store.fetchMyPositions(),
      store.fetchMyFees(),
      store.fetchSubscriptions(),
    ])
  } finally {
    loading.value = false
  }
})

async function toggle(id: number, active: boolean) {
  await store.setActive(id, active)
}
</script>

<template>
  <div class="flex-1 overflow-y-auto p-6 space-y-8">
    <h1 class="text-lg font-semibold text-zinc-200">My Portfolio</h1>
    <div v-if="loading" class="text-sm text-zinc-500">Loading…</div>

    <template v-else>
      <!-- Subscriptions -->
      <section class="space-y-2">
        <h2 class="text-sm font-medium text-zinc-200">Subscriptions</h2>
        <div class="overflow-x-auto rounded-lg border border-zinc-800">
          <table class="w-full text-sm">
            <thead class="bg-zinc-900/60 text-zinc-400">
              <tr>
                <th class="px-4 py-2 text-left">Strategy</th>
                <th class="px-4 py-2 text-left">Sizing</th>
                <th class="px-4 py-2 text-right">Leverage</th>
                <th class="px-4 py-2 text-right">Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in store.subscriptions" :key="s.id" class="border-t border-zinc-800">
                <td class="px-4 py-2 text-zinc-200">{{ s.master_name }} <span class="text-zinc-500">{{ s.master_symbol }}</span></td>
                <td class="px-4 py-2 text-zinc-400">
                  {{ s.sizing_mode === 'risk_pct' ? s.risk_pct + '%' : s.fixed_notional }}
                </td>
                <td class="px-4 py-2 text-right text-zinc-300">{{ s.leverage }}×</td>
                <td class="px-4 py-2 text-right">
                  <button
                    type="button"
                    class="rounded px-2 py-1 text-xs"
                    :class="s.is_active ? 'text-emerald-400 hover:bg-zinc-800' : 'text-zinc-500 hover:bg-zinc-800'"
                    @click="toggle(s.id, !s.is_active)"
                  >{{ s.is_active ? 'Active' : 'Paused' }}</button>
                </td>
              </tr>
              <tr v-if="!store.subscriptions.length">
                <td colspan="4" class="px-4 py-3 text-center text-zinc-500">No subscriptions.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Open positions -->
      <section class="space-y-2">
        <h2 class="text-sm font-medium text-zinc-200">Open positions</h2>
        <div class="overflow-x-auto rounded-lg border border-zinc-800">
          <table class="w-full text-sm">
            <thead class="bg-zinc-900/60 text-zinc-400">
              <tr>
                <th class="px-4 py-2 text-left">Coin</th>
                <th class="px-4 py-2 text-right">Size</th>
                <th class="px-4 py-2 text-right">Entry</th>
                <th class="px-4 py-2 text-right">Opened</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in store.positions" :key="p.id" class="border-t border-zinc-800">
                <td class="px-4 py-2 text-zinc-200">{{ p.coin }}</td>
                <td class="px-4 py-2 text-right" :class="Number(p.size) >= 0 ? 'text-emerald-400' : 'text-red-400'">{{ p.size }}</td>
                <td class="px-4 py-2 text-right text-zinc-400">{{ p.entry_price }}</td>
                <td class="px-4 py-2 text-right text-zinc-500">{{ p.opened_at?.slice(0, 10) }}</td>
              </tr>
              <tr v-if="!store.positions.length">
                <td colspan="4" class="px-4 py-3 text-center text-zinc-500">No open positions.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Fees -->
      <section class="space-y-2">
        <h2 class="text-sm font-medium text-zinc-200">Fees owed</h2>
        <div class="overflow-x-auto rounded-lg border border-zinc-800">
          <table class="w-full text-sm">
            <thead class="bg-zinc-900/60 text-zinc-400">
              <tr>
                <th class="px-4 py-2 text-right">Realized PnL</th>
                <th class="px-4 py-2 text-right">High-water mark</th>
                <th class="px-4 py-2 text-right">Fee accrued</th>
                <th class="px-4 py-2 text-right">Rate</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="l in store.myFees" :key="l.id" class="border-t border-zinc-800">
                <td class="px-4 py-2 text-right text-zinc-300">{{ l.realized_pnl }}</td>
                <td class="px-4 py-2 text-right text-zinc-400">{{ l.high_water_mark }}</td>
                <td class="px-4 py-2 text-right text-amber-400">{{ l.fee_accrued }}</td>
                <td class="px-4 py-2 text-right text-zinc-500">{{ (Number(l.fee_rate) * 100).toFixed(0) }}%</td>
              </tr>
              <tr v-if="!store.myFees.length">
                <td colspan="4" class="px-4 py-3 text-center text-zinc-500">No fees yet.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>
