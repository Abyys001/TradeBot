<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useIntervalFn } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { api } from '../../api/client'
import { useStrategyStore } from '../../stores/strategy'
import { useToast } from '../../composables/useToast'
import AppModal from '../../components/AppModal.vue'

const props = defineProps<{ strategyId: number; active?: boolean; closable?: boolean }>()
const { t } = useI18n()
const strategy = useStrategyStore()
const toast = useToast()

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
const closeTarget = ref<Position | null>(null)
const closing = ref(false)

async function refresh() {
  loading.value = true
  try {
    const { data } = await api.get<{ positions: Position[] }>(`/strategies/${props.strategyId}/positions/`)
    positions.value = data.positions
  } finally {
    loading.value = false
  }
}

function sideOf(p: Position): 'long' | 'short' {
  return Number(p.size) < 0 ? 'short' : 'long'
}

async function confirmClose() {
  if (!closeTarget.value) return
  const coin = closeTarget.value.coin
  closing.value = true
  try {
    const res = await strategy.closePosition(props.strategyId, coin)
    if (res.ok) {
      toast.show(t('positions.closed'), 'success')
      closeTarget.value = null
      await refresh()
    } else {
      toast.show(res.error || t('positions.closeFailed'), 'error')
    }
  } catch {
    toast.show(t('positions.closeFailed'), 'error')
  } finally {
    closing.value = false
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
          <th class="px-3 py-1 text-start">{{ t('positions.side') }}</th>
          <th class="px-3 py-1 text-end">{{ t('positions.size') }}</th>
          <th class="px-3 py-1 text-end">{{ t('positions.entry') }}</th>
          <th class="px-3 py-1 text-end">{{ t('positions.liq') }}</th>
          <th class="px-3 py-1 text-end">PnL</th>
          <th v-if="closable" class="px-3 py-1 text-end"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in positions" :key="p.coin" class="border-t border-zinc-800/50">
          <td class="px-3 py-1.5 text-zinc-300">{{ p.coin }}</td>
          <td class="px-3 py-1.5">
            <span :class="sideOf(p) === 'long' ? 'text-emerald-400' : 'text-red-400'">
              {{ sideOf(p) === 'long' ? '🟢 Long' : '🔴 Short' }}
            </span>
          </td>
          <td class="px-3 py-1.5 text-end text-zinc-400">{{ p.size }}</td>
          <td class="px-3 py-1.5 text-end text-zinc-500">{{ p.entry_px }}</td>
          <td class="px-3 py-1.5 text-end text-zinc-500">{{ p.liquidation_px ?? '—' }}</td>
          <td class="px-3 py-1.5 text-end" :class="Number(p.unrealized_pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'">
            {{ p.unrealized_pnl }}
          </td>
          <td v-if="closable" class="px-3 py-1.5 text-end">
            <button
              type="button"
              class="rounded px-1.5 py-0.5 text-[11px] text-red-400 hover:bg-red-950/40 hover:text-red-300"
              :title="t('positions.close')"
              @click="closeTarget = p"
            >
              ✕
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <AppModal
      v-if="closeTarget"
      :title="t('positions.closeConfirmTitle')"
      @close="closeTarget = null"
    >
      <p class="px-4 py-4 text-sm text-zinc-300">
        {{ t('positions.closeConfirmBody', { coin: closeTarget.coin }) }}
      </p>
      <template #footer>
        <div class="flex justify-end gap-2">
          <button
            type="button"
            class="rounded-lg px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200"
            @click="closeTarget = null"
          >
            {{ t('health.cancel') }}
          </button>
          <button
            type="button"
            class="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
            :disabled="closing"
            @click="confirmClose"
          >
            {{ closing ? t('positions.closing') : t('positions.close') }}
          </button>
        </div>
      </template>
    </AppModal>
  </div>
</template>
