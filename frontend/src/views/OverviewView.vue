<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import StatCard from '../modules/overview/StatCard.vue'
import { useOverviewStore } from '../stores/overview'

const { t } = useI18n()
const router = useRouter()
const overview = useOverviewStore()

onMounted(() => overview.fetchOverview())

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function goStrategy(id: number | null) {
  if (id) router.push({ name: 'strategy-detail', params: { id } })
}
</script>

<template>
  <div class="flex-1 overflow-y-auto p-6 space-y-6">
    <h1 class="text-lg font-semibold text-zinc-200">{{ t('overview.title') }}</h1>

    <div v-if="overview.loading && !overview.data" class="text-zinc-500 text-sm">
      {{ t('overview.loading') }}
    </div>

    <template v-else-if="overview.data">
      <div class="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
        <StatCard
          :label="t('overview.totalBots')"
          :value="overview.data.strategies.total"
          :sub="`${overview.data.strategies.active} ${t('overview.active')}`"
        />
        <StatCard
          :label="t('overview.totalTrades')"
          :value="overview.data.orders.total"
          :sub="`${overview.data.orders.today} ${t('overview.today')}`"
        />
        <StatCard
          :label="t('overview.filledOrders')"
          :value="overview.data.orders.filled"
        />
        <StatCard
          :label="t('overview.totalPnl')"
          :value="overview.data.pnl.total_unrealized"
          :accent="parseFloat(overview.data.pnl.total_unrealized) >= 0 ? 'green' : 'red'"
        />
        <StatCard
          :label="t('overview.errors24h')"
          :value="overview.data.logs.errors_24h"
          :sub="`${overview.data.logs.warnings_24h} ${t('overview.warnings')}`"
          accent="amber"
        />
      </div>

      <div class="grid lg:grid-cols-2 gap-6">
        <section class="rounded-xl border border-zinc-800 bg-zinc-900/40 overflow-hidden">
          <h2 class="text-sm font-medium text-zinc-400 px-4 py-3 border-b border-zinc-800">
            {{ t('overview.recentOrders') }}
          </h2>
          <div v-if="!overview.data.recent_orders.length" class="p-4 text-sm text-zinc-600">
            {{ t('overview.noOrders') }}
          </div>
          <table v-else class="w-full text-xs">
            <tbody>
              <tr
                v-for="order in overview.data.recent_orders"
                :key="order.id"
                class="border-b border-zinc-800/50 hover:bg-zinc-800/30 cursor-pointer"
                @click="goStrategy(order.strategy)"
              >
                <td class="px-4 py-2 text-zinc-300">{{ order.symbol }}</td>
                <td class="px-4 py-2" :class="order.side === 'buy' ? 'text-emerald-400' : 'text-red-400'">
                  {{ order.side.toUpperCase() }}
                </td>
                <td class="px-4 py-2 text-zinc-500">{{ order.status }}</td>
                <td class="px-4 py-2 text-zinc-600">{{ formatTime(order.created_at) }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="rounded-xl border border-zinc-800 bg-zinc-900/40 overflow-hidden">
          <h2 class="text-sm font-medium text-zinc-400 px-4 py-3 border-b border-zinc-800">
            {{ t('overview.recentLogs') }}
          </h2>
          <div v-if="!overview.data.recent_logs.length" class="p-4 text-sm text-zinc-600">
            {{ t('overview.noLogs') }}
          </div>
          <table v-else class="w-full text-xs">
            <tbody>
              <tr
                v-for="log in overview.data.recent_logs"
                :key="log.id"
                class="border-b border-zinc-800/50 hover:bg-zinc-800/30 cursor-pointer"
                @click="goStrategy(log.strategy)"
              >
                <td class="px-4 py-2 font-mono text-zinc-500">{{ log.level }}</td>
                <td class="px-4 py-2 text-zinc-300">{{ log.event }}</td>
                <td class="px-4 py-2 text-zinc-600">{{ formatTime(log.created_at) }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </template>
  </div>
</template>
