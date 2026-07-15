<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../../api/client'
import { useExchangeWebSocket } from '../../composables/useExchangeWebSocket'
import ResponsiveTable from '../../components/ResponsiveTable.vue'

const props = defineProps<{ credentialId: number }>()

interface LivePosition {
  coin: string
  szi: string
  entryPx: string
  unrealizedPnl: string
  leverage: string
}

interface MarginSummary {
  accountValue: string
  totalMarginUsed: string
  withdrawable: string
}

const positions = ref<LivePosition[]>([])
const margin = ref<MarginSummary | null>(null)
const loading = ref(true)
const lastUpdated = ref<Date | null>(null)

async function hydrate() {
  loading.value = true
  try {
    const { data } = await api.get<{
      positions: LivePosition[]
      margin: MarginSummary
    }>(`/credentials/${props.credentialId}/live-state/`)
    positions.value = data.positions ?? []
    margin.value = data.margin ?? null
    lastUpdated.value = new Date()
  } catch {
    // non-fatal — WS updates will populate state
  } finally {
    loading.value = false
  }
}

onMounted(hydrate)

const { onEvent } = useExchangeWebSocket(() => props.credentialId)

onEvent((payload) => {
  if (payload.type === 'ws.snapshot.hydrated') {
    hydrate()
    return
  }
  if (payload.type === 'position.update' && Array.isArray(payload.positions)) {
    positions.value = payload.positions as LivePosition[]
    lastUpdated.value = new Date()
  }
})

function pnlClass(val: string) {
  return Number(val) >= 0 ? 'text-emerald-400' : 'text-red-400'
}

function fmt(val: string | undefined, decimals = 2) {
  const n = Number(val ?? 0)
  return isNaN(n) ? '—' : n.toFixed(decimals)
}
</script>

<template>
  <div class="rounded-xl border border-zinc-800 overflow-hidden">
    <!-- Header -->
    <div class="px-4 py-2.5 border-b border-zinc-800 flex items-center justify-between">
      <span class="text-xs font-semibold text-zinc-300 tracking-wide uppercase">Live Positions</span>
      <div class="flex items-center gap-3">
        <span v-if="lastUpdated" class="text-[10px] text-zinc-600">
          {{ lastUpdated.toLocaleTimeString() }}
        </span>
        <button
          type="button"
          class="text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors"
          @click="hydrate"
        >
          Refresh
        </button>
      </div>
    </div>

    <!-- Margin summary -->
    <div v-if="margin" class="grid grid-cols-3 gap-px border-b border-zinc-800 bg-zinc-800">
      <div class="bg-zinc-900 px-3 py-2">
        <p class="text-[10px] text-zinc-500 mb-0.5">Account Value</p>
        <p class="text-xs font-medium text-zinc-200">${{ fmt(margin.accountValue) }}</p>
      </div>
      <div class="bg-zinc-900 px-3 py-2">
        <p class="text-[10px] text-zinc-500 mb-0.5">Margin Used</p>
        <p class="text-xs font-medium text-zinc-200">${{ fmt(margin.totalMarginUsed) }}</p>
      </div>
      <div class="bg-zinc-900 px-3 py-2">
        <p class="text-[10px] text-zinc-500 mb-0.5">Free</p>
        <p class="text-xs font-medium text-emerald-400">
          ${{ fmt((Number(margin.accountValue) - Number(margin.totalMarginUsed)).toFixed(2)) }}
        </p>
      </div>
    </div>

    <ResponsiveTable :loading="loading && !positions.length" :empty="!loading && !positions.length">
      <template #loading>
        <span class="block px-4 py-6 text-center text-xs">Loading positions…</span>
      </template>
      <template #empty>
        <span class="block px-4 py-6 text-center text-xs">No open positions</span>
      </template>
      <template #head>
        <th class="px-3 py-2 text-start font-medium">Coin</th>
        <th class="px-3 py-2 text-end font-medium">Size</th>
        <th class="px-3 py-2 text-end font-medium">Entry Px</th>
        <th class="px-3 py-2 text-end font-medium">Leverage</th>
        <th class="px-3 py-2 text-end font-medium">uPnL</th>
      </template>
      <template #row>
        <tr
          v-for="pos in positions"
          :key="pos.coin"
          class="border-t border-zinc-800/60 text-xs hover:bg-zinc-800/30 transition-colors"
        >
          <td class="px-3 py-2 text-zinc-200 font-medium">{{ pos.coin }}</td>
          <td class="px-3 py-2 text-end" :class="Number(pos.szi) > 0 ? 'text-emerald-400' : 'text-red-400'">
            {{ fmt(pos.szi, 4) }}
          </td>
          <td class="px-3 py-2 text-end text-zinc-400">${{ fmt(pos.entryPx) }}</td>
          <td class="px-3 py-2 text-end text-zinc-400">{{ fmt(pos.leverage, 1) }}×</td>
          <td class="px-3 py-2 text-end font-medium" :class="pnlClass(pos.unrealizedPnl)">
            ${{ fmt(pos.unrealizedPnl) }}
          </td>
        </tr>
      </template>
      <template #card>
        <div v-for="pos in positions" :key="pos.coin" class="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 text-xs">
          <div class="flex items-center justify-between">
            <span class="font-medium text-zinc-200">{{ pos.coin }}</span>
            <span class="font-medium" :class="pnlClass(pos.unrealizedPnl)">${{ fmt(pos.unrealizedPnl) }}</span>
          </div>
          <div class="mt-1.5 grid grid-cols-3 gap-y-1 text-zinc-500">
            <div>
              <div class="text-[10px]">Size</div>
              <div :class="Number(pos.szi) > 0 ? 'text-emerald-400' : 'text-red-400'">{{ fmt(pos.szi, 4) }}</div>
            </div>
            <div>
              <div class="text-[10px]">Entry Px</div>
              <div class="text-zinc-400">${{ fmt(pos.entryPx) }}</div>
            </div>
            <div>
              <div class="text-[10px]">Leverage</div>
              <div class="text-zinc-400">{{ fmt(pos.leverage, 1) }}×</div>
            </div>
          </div>
        </div>
      </template>
    </ResponsiveTable>
  </div>
</template>
