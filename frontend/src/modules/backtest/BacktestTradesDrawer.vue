<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { BacktestTrade } from '../../api/client'
import ResponsiveTable from '../../components/ResponsiveTable.vue'

defineProps<{ trades: BacktestTrade[] }>()

const { t } = useI18n()
const open = ref(false)

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'medium', hour12: false })
}
</script>

<template>
  <div v-if="trades.length" class="shrink-0 border-t border-border bg-surface">
    <button
      type="button"
      class="flex w-full items-center justify-between px-3 py-2 text-xs text-fg-muted hover:bg-surface-muted/50"
      @click="open = !open"
    >
      <span>{{ t('backtest.tradesTitle', { count: trades.length }) }}</span>
      <span>{{ open ? '▼' : '▶' }}</span>
    </button>
    <div v-show="open" class="scrollbar-styled scrollbar-thin max-h-48 overflow-y-auto border-t border-border/50">
      <ResponsiveTable sticky-head>
        <template #head>
          <th class="px-3 py-2 text-start">{{ t('backtest.side') }}</th>
          <th class="px-3 py-2 text-start">{{ t('backtest.time') }}</th>
          <th class="px-3 py-2 text-end">{{ t('backtest.entry') }}</th>
          <th class="px-3 py-2 text-end">{{ t('backtest.exit') }}</th>
          <th class="px-3 py-2 text-end">{{ t('backtest.pnl') }}</th>
          <th class="px-3 py-2 text-end">{{ t('backtest.exitReason') }}</th>
        </template>
        <template #row>
          <tr v-for="(tr, i) in trades" :key="i" class="border-t border-border/50 text-xs">
            <td class="px-3 py-1.5 text-fg">{{ tr.side }}</td>
            <td class="px-3 py-1.5 text-fg-muted">
              <div>{{ fmtTime(tr.entry_time) }}</div>
              <div v-if="tr.exit_time" class="text-fg-muted">→ {{ fmtTime(tr.exit_time) }}</div>
            </td>
            <td class="px-3 py-1.5 text-end text-fg-muted">{{ tr.entry_price }}</td>
            <td class="px-3 py-1.5 text-end text-fg-muted">{{ tr.exit_price ?? '—' }}</td>
            <td class="px-3 py-1.5 text-end" :class="Number(tr.pnl) >= 0 ? 'text-positive' : 'text-negative'">
              {{ tr.pnl }}
            </td>
            <td class="px-3 py-1.5 text-end text-fg-muted">{{ tr.exit_reason || '—' }}</td>
          </tr>
        </template>
        <template #card>
          <div v-for="(tr, i) in trades" :key="i" class="rounded-lg border border-border bg-surface-muted/40 p-3 text-xs">
            <div class="flex items-center justify-between">
              <span class="font-medium text-fg">{{ tr.side }}</span>
              <span :class="Number(tr.pnl) >= 0 ? 'text-positive' : 'text-negative'">{{ tr.pnl }}</span>
            </div>
            <div class="mt-1 text-fg-muted">
              {{ fmtTime(tr.entry_time) }}<span v-if="tr.exit_time"> → {{ fmtTime(tr.exit_time) }}</span>
            </div>
            <div class="mt-1.5 grid grid-cols-3 gap-y-1">
              <div>
                <div class="text-[10px] text-fg-muted">{{ t('backtest.entry') }}</div>
                <div class="text-fg-muted">{{ tr.entry_price }}</div>
              </div>
              <div>
                <div class="text-[10px] text-fg-muted">{{ t('backtest.exit') }}</div>
                <div class="text-fg-muted">{{ tr.exit_price ?? '—' }}</div>
              </div>
              <div>
                <div class="text-[10px] text-fg-muted">{{ t('backtest.exitReason') }}</div>
                <div class="text-fg-muted">{{ tr.exit_reason || '—' }}</div>
              </div>
            </div>
          </div>
        </template>
      </ResponsiveTable>
    </div>
  </div>
</template>
