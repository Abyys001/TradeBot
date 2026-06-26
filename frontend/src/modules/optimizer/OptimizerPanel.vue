<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useOptimizerStore } from '../../stores/optimizer'
import { useBacktestStore } from '../../stores/backtest'
import GridResultsTable from './GridResultsTable.vue'
import MonteCarloChart from './MonteCarloChart.vue'

const props = defineProps<{ strategyId: number }>()
const { t } = useI18n()
const optimizer = useOptimizerStore()
const backtestStore = useBacktestStore()

const tab = ref<'grid' | 'walkforward' | 'montecarlo'>('grid')
const coin = ref('BTC')
const interval = ref('1h')
const network = ref('mainnet')
const paramGridJson = ref('{"leverage": [1, 2, 3]}')
const selectedBacktestId = ref<number | ''>('')
const simulations = ref(500)

const strategyBacktests = computed(() => backtestStore.forStrategy(props.strategyId))

function parseParamGrid() {
  try {
    return JSON.parse(paramGridJson.value) as Record<string, unknown[]>
  } catch {
    return null
  }
}

async function runGrid() {
  const param_grid = parseParamGrid()
  if (!param_grid) return
  await optimizer.runGrid({
    strategy_id: props.strategyId,
    coin: coin.value,
    interval: interval.value,
    network: network.value,
    param_grid,
  })
}

async function runWalkForward() {
  const param_grid = parseParamGrid()
  if (!param_grid) return
  await optimizer.runWalkForward({
    strategy_id: props.strategyId,
    coin: coin.value,
    interval: interval.value,
    network: network.value,
    param_grid,
  })
}

async function runMonteCarlo() {
  if (!selectedBacktestId.value) return
  await optimizer.runMonteCarlo(Number(selectedBacktestId.value), simulations.value)
}
</script>

<template>
  <div class="space-y-3 border-t border-zinc-800 pt-3">
    <h4 class="text-xs font-medium text-zinc-400">{{ t('optimizer.title') }}</h4>
    <div class="flex gap-1">
      <button
        v-for="tname in (['grid', 'walkforward', 'montecarlo'] as const)"
        :key="tname"
        type="button"
        class="rounded px-2 py-0.5 text-[10px]"
        :class="tab === tname ? 'bg-violet-900 text-violet-200' : 'bg-zinc-800 text-zinc-500'"
        @click="tab = tname"
      >
        {{ t(`optimizer.tab.${tname}`) }}
      </button>
    </div>
    <div v-if="tab !== 'montecarlo'" class="grid grid-cols-3 gap-1">
      <input v-model="coin" class="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-[10px]" />
      <input v-model="interval" class="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-[10px]" />
      <select v-model="network" class="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-[10px]">
        <option value="mainnet">mainnet</option>
        <option value="testnet">testnet</option>
      </select>
    </div>
    <textarea
      v-if="tab !== 'montecarlo'"
      v-model="paramGridJson"
      rows="2"
      class="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-[10px] font-mono"
      :placeholder="t('optimizer.paramGrid')"
    />
    <div v-if="tab === 'montecarlo'" class="space-y-1">
      <select
        v-model="selectedBacktestId"
        class="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-[10px]"
      >
        <option value="">{{ t('optimizer.selectBacktest') }}</option>
        <option v-for="bt in strategyBacktests" :key="bt.id" :value="bt.id">
          #{{ bt.id }} {{ bt.symbol }} ({{ bt.status }})
        </option>
      </select>
      <input
        v-model.number="simulations"
        type="number"
        min="100"
        class="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-[10px]"
      />
    </div>
    <button
      type="button"
      class="w-full rounded bg-violet-800 hover:bg-violet-700 text-xs py-1.5 disabled:opacity-50"
      :disabled="optimizer.loading"
      @click="tab === 'grid' ? runGrid() : tab === 'walkforward' ? runWalkForward() : runMonteCarlo()"
    >
      {{ optimizer.loading ? t('optimizer.running') : t('optimizer.run') }}
    </button>
    <p v-if="optimizer.error" class="text-[10px] text-red-400">{{ optimizer.error }}</p>
    <GridResultsTable v-if="tab === 'grid' && optimizer.gridResults.length" :results="optimizer.gridResults" />
    <div v-if="tab === 'walkforward' && optimizer.walkForwardWindows.length" class="text-[10px] text-zinc-400 space-y-1 max-h-32 overflow-y-auto">
      <div v-for="(w, i) in optimizer.walkForwardWindows" :key="i">
        W{{ i + 1 }} test PnL: {{ w.test_metrics?.net_pnl?.toFixed(2) ?? '—' }}
      </div>
    </div>
    <MonteCarloChart v-if="tab === 'montecarlo'" :result="optimizer.monteCarloResult" />
  </div>
</template>
