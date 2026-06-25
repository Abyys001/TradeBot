<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useIntervalFn } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { api } from '../../api/client'

const props = defineProps<{ strategyId: number; active?: boolean }>()
const { t } = useI18n()

interface Position {
  coin: string
  size: string
  entry_px: string
  liquidation_px: string | null
  unrealized_pnl: string
  leverage: number | null
}

const positions = ref<Position[]>([])
const loading = ref(true)

async function refresh() {
  loading.value = true
  try {
    const { data } = await api.get<{ positions: Position[] }>(`/strategies/${props.strategyId}/positions/`)
    positions.value = data.positions
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

const { pause, resume } = useIntervalFn(refresh, 30000, { immediate: false })

watch(
  () => props.active,
  (isActive) => {
    if (isActive) resume()
    else pause()
  },
  { immediate: true },
)

onUnmounted(pause)

defineExpose({ refresh })
</script>

<template>
  <div class="rounded-lg border border-zinc-800 overflow-hidden">
    <div class="px-3 py-2 border-b border-zinc-800 flex items-center justify-between">
      <span class="text-xs font-medium text-zinc-400">{{ t('positions.title') }}</span>
      <button
        type="button"
        class="text-[10px] text-zinc-500 hover:text-zinc-300"
        :disabled="loading"
        @click="refresh"
      >
        {{ t('positions.refresh') }}
      </button>
    </div>
    <div v-if="loading && !positions.length" class="px-3 py-4 text-xs text-zinc-500">{{ t('overview.loading') }}</div>
    <div v-else-if="!positions.length" class="px-3 py-4 text-xs text-zinc-500">{{ t('positions.empty') }}</div>
    <table v-else class="w-full text-xs">
      <thead class="text-zinc-500">
        <tr>
          <th class="px-3 py-1 text-start">{{ t('data.coin') }}</th>
          <th class="px-3 py-1 text-end">{{ t('positions.size') }}</th>
          <th class="px-3 py-1 text-end">{{ t('positions.liq') }}</th>
          <th class="px-3 py-1 text-end">PnL</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in positions" :key="p.coin" class="border-t border-zinc-800/50">
          <td class="px-3 py-1.5 text-zinc-300">{{ p.coin }}</td>
          <td class="px-3 py-1.5 text-end text-zinc-400">{{ p.size }}</td>
          <td class="px-3 py-1.5 text-end text-zinc-500">{{ p.liquidation_px ?? '—' }}</td>
          <td class="px-3 py-1.5 text-end" :class="Number(p.unrealized_pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'">
            {{ p.unrealized_pnl }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
