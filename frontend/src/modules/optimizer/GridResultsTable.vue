<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { GridResult } from '../../stores/optimizer'

const props = defineProps<{ results: GridResult[] }>()
const { t } = useI18n()

const sorted = computed(() =>
  [...props.results].sort((a, b) => (b.metrics.net_pnl ?? 0) - (a.metrics.net_pnl ?? 0)),
)
</script>

<template>
  <div class="rounded-lg border border-zinc-800 overflow-hidden">
    <div class="overflow-x-auto"><table class="w-full text-[10px]">
      <thead class="text-zinc-500 bg-zinc-900/50">
        <tr>
          <th class="px-2 py-1 text-start">{{ t('optimizer.params') }}</th>
          <th class="px-2 py-1 text-end">PnL</th>
          <th class="px-2 py-1 text-end">Sharpe</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in sorted" :key="i" class="border-t border-zinc-800/50">
          <td class="px-2 py-1 text-zinc-400 font-mono">{{ JSON.stringify(r.params) }}</td>
          <td class="px-2 py-1 text-end text-emerald-400">{{ r.metrics.net_pnl?.toFixed(2) ?? '—' }}</td>
          <td class="px-2 py-1 text-end text-zinc-400">{{ r.metrics.sharpe_ratio?.toFixed(2) ?? '—' }}</td>
        </tr>
      </tbody>
    </table></div>
  </div>
</template>
