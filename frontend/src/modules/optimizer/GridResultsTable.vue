<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { GridResult } from '../../stores/optimizer'
import ResponsiveTable from '../../components/ResponsiveTable.vue'

const props = defineProps<{ results: GridResult[] }>()
const { t } = useI18n()

const sorted = computed(() =>
  [...props.results].sort((a, b) => (b.metrics.net_pnl ?? 0) - (a.metrics.net_pnl ?? 0)),
)
</script>

<template>
  <div class="rounded-lg border border-border overflow-hidden">
    <ResponsiveTable>
      <template #head>
        <th class="px-2 py-1 text-start text-[10px]">{{ t('optimizer.params') }}</th>
        <th class="px-2 py-1 text-end text-[10px]">PnL</th>
        <th class="px-2 py-1 text-end text-[10px]">Sharpe</th>
      </template>
      <template #row>
        <tr v-for="(r, i) in sorted" :key="i" class="border-t border-border/50 text-[10px]">
          <td class="px-2 py-1 text-fg-muted font-mono">{{ JSON.stringify(r.params) }}</td>
          <td class="px-2 py-1 text-end text-positive">{{ r.metrics.net_pnl?.toFixed(2) ?? '—' }}</td>
          <td class="px-2 py-1 text-end text-fg-muted">{{ r.metrics.sharpe_ratio?.toFixed(2) ?? '—' }}</td>
        </tr>
      </template>
      <template #card>
        <div v-for="(r, i) in sorted" :key="i" class="rounded border border-border/70 p-2 text-[10px]">
          <div class="break-all font-mono text-fg-muted">{{ JSON.stringify(r.params) }}</div>
          <div class="mt-1 flex items-center justify-between">
            <span class="text-fg-muted">PnL <span class="text-positive">{{ r.metrics.net_pnl?.toFixed(2) ?? '—' }}</span></span>
            <span class="text-fg-muted">Sharpe <span class="text-fg">{{ r.metrics.sharpe_ratio?.toFixed(2) ?? '—' }}</span></span>
          </div>
        </div>
      </template>
    </ResponsiveTable>
  </div>
</template>
