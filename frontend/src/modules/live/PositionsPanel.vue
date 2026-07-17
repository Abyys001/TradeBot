<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useIntervalFn } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { api } from '../../api/client'
import { useStrategyStore } from '../../stores/strategy'
import { useToast } from '../../composables/useToast'
import ResponsiveTable from '../../components/ResponsiveTable.vue'
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
  <div class="rounded-lg border border-border overflow-hidden">
    <div class="px-3 py-2 border-b border-border flex items-center justify-between">
      <span class="text-xs font-medium text-fg-muted">{{ t('positions.title') }}</span>
      <button
        type="button"
        class="text-[10px] text-fg-muted hover:text-fg"
        :disabled="loading"
        @click="refresh"
      >
        {{ t('positions.refresh') }}
      </button>
    </div>
    <ResponsiveTable :loading="loading && !positions.length" :empty="!loading && !positions.length">
      <template #loading>
        <span class="block px-3 py-4 text-xs">{{ t('overview.loading') }}</span>
      </template>
      <template #empty>
        <span class="block px-3 py-4 text-xs">{{ t('positions.empty') }}</span>
      </template>
      <template #head>
        <th class="px-3 py-1 text-start">{{ t('data.coin') }}</th>
        <th class="px-3 py-1 text-start">{{ t('positions.side') }}</th>
        <th class="px-3 py-1 text-end">{{ t('positions.size') }}</th>
        <th class="px-3 py-1 text-end">{{ t('positions.entry') }}</th>
        <th class="px-3 py-1 text-end">{{ t('positions.liq') }}</th>
        <th class="px-3 py-1 text-end">PnL</th>
        <th v-if="closable" class="px-3 py-1 text-end"></th>
      </template>
      <template #row>
        <tr v-for="p in positions" :key="p.coin" class="border-t border-border/50 text-xs">
          <td class="px-3 py-1.5 text-fg">{{ p.coin }}</td>
          <td class="px-3 py-1.5">
            <span :class="sideOf(p) === 'long' ? 'text-positive' : 'text-negative'">
              {{ sideOf(p) === 'long' ? 'Long' : 'Short' }}
            </span>
          </td>
          <td class="px-3 py-1.5 text-end text-fg-muted">{{ p.size }}</td>
          <td class="px-3 py-1.5 text-end text-fg-muted">{{ p.entry_px }}</td>
          <td class="px-3 py-1.5 text-end text-fg-muted">{{ p.liquidation_px ?? '—' }}</td>
          <td class="px-3 py-1.5 text-end" :class="Number(p.unrealized_pnl) >= 0 ? 'text-positive' : 'text-negative'">
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
      </template>
      <template #card>
        <div v-for="p in positions" :key="p.coin" class="rounded-lg border border-border/70 p-2 text-xs">
          <div class="flex items-center justify-between">
            <span class="font-medium text-fg">{{ p.coin }}</span>
            <span :class="Number(p.unrealized_pnl) >= 0 ? 'text-positive' : 'text-negative'">{{ p.unrealized_pnl }}</span>
          </div>
          <div class="mt-1 flex items-center justify-between text-fg-muted">
            <span>{{ t('positions.size') }}: {{ p.size }}</span>
            <span>{{ t('positions.liq') }}: {{ p.liquidation_px ?? '—' }}</span>
          </div>
        </div>
      </template>
    </ResponsiveTable>

    <AppModal
      v-if="closeTarget"
      :title="t('positions.closeConfirmTitle')"
      @close="closeTarget = null"
    >
      <p class="px-4 py-4 text-sm text-fg">
        {{ t('positions.closeConfirmBody', { coin: closeTarget.coin }) }}
      </p>
      <template #footer>
        <div class="flex justify-end gap-2">
          <button
            type="button"
            class="rounded-lg px-4 py-2 text-sm text-fg-muted hover:text-fg"
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
