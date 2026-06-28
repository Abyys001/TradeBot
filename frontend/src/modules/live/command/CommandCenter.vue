<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../../../stores/strategy'
import { useDashboardWebSocket } from '../../../composables/useDashboardWebSocket'
import TradingChart from '../../chart/TradingChart.vue'
import AuditTerminal from '../../terminal/AuditTerminal.vue'
import PositionsPanel from '../PositionsPanel.vue'

const emit = defineEmits<{ newDeployment: [] }>()

const { t } = useI18n()
const store = useStrategyStore()
const ws = useDashboardWebSocket()

const selectedId = ref<number | null>(null)

const live = computed(() => store.liveStrategies)
const active = computed(() => live.value.find((s) => s.id === selectedId.value) ?? live.value[0] ?? null)

watch(
  live,
  (list) => {
    if (!selectedId.value && list.length) selectedId.value = list[0].id
    if (selectedId.value && !list.find((s) => s.id === selectedId.value)) {
      selectedId.value = list[0]?.id ?? null
    }
  },
  { immediate: true },
)

function pnlClass(pnl?: string) {
  return Number(pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'
}

onMounted(() => {
  ws.connect()
})
</script>

<template>
  <div class="flex h-full min-h-0 flex-col">
    <!-- header -->
    <div class="flex shrink-0 items-center gap-3 border-b border-zinc-800 bg-zinc-900/30 px-4 py-2">
      <h1 class="text-sm font-semibold text-violet-200">{{ t('live.commandCenter') }}</h1>
      <span class="flex items-center gap-1.5 text-xs text-zinc-500">
        <span class="h-2 w-2 rounded-full" :class="ws.connected.value ? 'bg-emerald-500' : 'bg-red-500'" />
        {{ live.length }} {{ t('strategies.statusActive').toLowerCase() }}
      </span>
      <button
        type="button"
        class="ms-auto rounded-lg bg-violet-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-600"
        @click="emit('newDeployment')"
      >
        ＋ {{ t('live.newDeployment') }}
      </button>
    </div>

    <div class="grid min-h-0 flex-1 overflow-hidden" style="grid-template-columns: minmax(0, 1fr) 320px">
      <!-- chart -->
      <main class="flex min-h-0 min-w-0 flex-col overflow-hidden">
        <div class="relative min-h-0 flex-1 overflow-hidden">
          <TradingChart
            v-if="active"
            class="h-full w-full"
            :strategy-id="active.id"
            mode="live"
          />
          <div v-else class="flex h-full items-center justify-center text-sm text-zinc-600">
            {{ t('chart.noStrategy') }}
          </div>
        </div>
        <AuditTerminal :strategy-id="undefined" />
      </main>

      <!-- right rail -->
      <aside class="flex min-h-0 flex-col gap-3 overflow-y-auto border-s border-zinc-800 bg-zinc-950 p-3">
        <div class="rounded-lg border border-zinc-800 overflow-hidden">
          <div class="border-b border-zinc-800 px-3 py-2 text-xs font-medium text-zinc-400">
            {{ t('nav.strategies') }}
          </div>
          <button
            v-for="s in live"
            :key="s.id"
            type="button"
            class="flex w-full items-center justify-between px-3 py-2 text-start text-xs transition-colors"
            :class="s.id === active?.id ? 'bg-zinc-800/60 text-zinc-100' : 'text-zinc-400 hover:bg-zinc-800/30'"
            @click="selectedId = s.id"
          >
            <span class="min-w-0 truncate">{{ s.name }}</span>
            <span :class="pnlClass(s.state?.pnl)">{{ s.state?.pnl ?? '0' }}</span>
          </button>
        </div>

        <PositionsPanel
          v-if="active"
          :key="active.id"
          :strategy-id="active.id"
          :active="true"
          :closable="true"
        />
      </aside>
    </div>
  </div>
</template>
