<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { BacktestTrade } from '../../api/client'

defineProps<{ trades: BacktestTrade[] }>()

const { t } = useI18n()
const open = ref(false)
</script>

<template>
  <div v-if="trades.length" class="shrink-0 border-t border-zinc-800 bg-zinc-950">
    <button
      type="button"
      class="flex w-full items-center justify-between px-3 py-2 text-xs text-zinc-400 hover:bg-zinc-900/50"
      @click="open = !open"
    >
      <span>{{ t('backtest.tradesTitle', { count: trades.length }) }}</span>
      <span>{{ open ? '▼' : '▶' }}</span>
    </button>
    <div v-show="open" class="max-h-48 overflow-y-auto border-t border-zinc-800/50">
      <table class="w-full text-xs">
        <thead class="sticky top-0 text-zinc-500 uppercase bg-zinc-900/90">
          <tr>
            <th class="px-3 py-2 text-start">{{ t('backtest.side') }}</th>
            <th class="px-3 py-2 text-end">{{ t('backtest.entry') }}</th>
            <th class="px-3 py-2 text-end">{{ t('backtest.exit') }}</th>
            <th class="px-3 py-2 text-end">{{ t('backtest.pnl') }}</th>
            <th class="px-3 py-2 text-end">{{ t('backtest.exitReason') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(tr, i) in trades" :key="i" class="border-t border-zinc-800/50">
            <td class="px-3 py-1.5 text-zinc-300">{{ tr.side }}</td>
            <td class="px-3 py-1.5 text-end text-zinc-400">{{ tr.entry_price }}</td>
            <td class="px-3 py-1.5 text-end text-zinc-400">{{ tr.exit_price ?? '—' }}</td>
            <td class="px-3 py-1.5 text-end" :class="Number(tr.pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'">
              {{ tr.pnl }}
            </td>
            <td class="px-3 py-1.5 text-end text-zinc-500">{{ tr.exit_reason || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
