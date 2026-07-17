<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import StatCard from '../modules/overview/StatCard.vue'
import ResponsiveTable from '../components/ResponsiveTable.vue'
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
  <div class="scrollbar-styled scrollbar-thin scrollbar-idle-fade flex-1 overflow-y-auto p-6 space-y-6">
    <h1 class="text-lg font-semibold text-fg">{{ t('overview.title') }}</h1>

    <div v-if="overview.loading && !overview.data" class="text-fg-muted text-sm">
      {{ t('overview.loading') }}
    </div>

    <template v-else-if="overview.data">
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
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

      <div class="grid md:grid-cols-2 gap-6">
        <section class="rounded-xl border border-border bg-surface-raised overflow-hidden">
          <h2 class="text-sm font-medium text-fg-muted px-4 py-3 border-b border-border">
            {{ t('overview.recentOrders') }}
          </h2>
          <ResponsiveTable :empty="!overview.data.recent_orders.length">
            <template #empty>
              <span class="text-fg-muted">{{ t('overview.noOrders') }}</span>
            </template>
            <template #row>
              <tr
                v-for="order in overview.data.recent_orders"
                :key="order.id"
                class="border-b border-border/50 hover:bg-surface-raised/30 cursor-pointer"
                @click="goStrategy(order.strategy)"
              >
                <td class="px-4 py-2 text-fg">{{ order.symbol }}</td>
                <td class="px-4 py-2" :class="order.side === 'buy' ? 'text-positive' : 'text-negative'">
                  {{ order.side.toUpperCase() }}
                </td>
                <td class="px-4 py-2 text-fg-muted">{{ order.status }}</td>
                <td class="px-4 py-2 text-fg-muted">{{ formatTime(order.created_at) }}</td>
              </tr>
            </template>
            <template #card>
              <div
                v-for="order in overview.data.recent_orders"
                :key="order.id"
                class="rounded-lg border border-border bg-surface-raised p-3 cursor-pointer"
                @click="goStrategy(order.strategy)"
              >
                <div class="flex items-center justify-between">
                  <span class="text-sm text-fg">{{ order.symbol }}</span>
                  <span class="text-xs font-medium" :class="order.side === 'buy' ? 'text-positive' : 'text-negative'">
                    {{ order.side.toUpperCase() }}
                  </span>
                </div>
                <div class="mt-1 flex items-center justify-between text-xs text-fg-muted">
                  <span>{{ order.status }}</span>
                  <span>{{ formatTime(order.created_at) }}</span>
                </div>
              </div>
            </template>
          </ResponsiveTable>
        </section>

        <section class="rounded-xl border border-border bg-surface-raised overflow-hidden">
          <h2 class="text-sm font-medium text-fg-muted px-4 py-3 border-b border-border">
            {{ t('overview.recentLogs') }}
          </h2>
          <ResponsiveTable :empty="!overview.data.recent_logs.length">
            <template #empty>
              <span class="text-fg-muted">{{ t('overview.noLogs') }}</span>
            </template>
            <template #row>
              <tr
                v-for="log in overview.data.recent_logs"
                :key="log.id"
                class="border-b border-border/50 hover:bg-surface-raised/30 cursor-pointer"
                @click="goStrategy(log.strategy)"
              >
                <td class="px-4 py-2 font-mono text-fg-muted">{{ log.level }}</td>
                <td class="px-4 py-2 text-fg">{{ log.event }}</td>
                <td class="px-4 py-2 text-fg-muted">{{ formatTime(log.created_at) }}</td>
              </tr>
            </template>
            <template #card>
              <div
                v-for="log in overview.data.recent_logs"
                :key="log.id"
                class="rounded-lg border border-border bg-surface-raised p-3 cursor-pointer"
                @click="goStrategy(log.strategy)"
              >
                <div class="flex items-center justify-between">
                  <span class="font-mono text-xs text-fg-muted">{{ log.level }}</span>
                  <span class="text-xs text-fg-muted">{{ formatTime(log.created_at) }}</span>
                </div>
                <div class="mt-1 text-sm text-fg">{{ log.event }}</div>
              </div>
            </template>
          </ResponsiveTable>
        </section>
      </div>
    </template>
  </div>
</template>
