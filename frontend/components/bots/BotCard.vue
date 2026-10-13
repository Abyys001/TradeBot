<script setup lang="ts">
/**
 * A running bot, on the dashboard, without anyone choosing it from a menu.
 *
 * Everything on it comes from the bot's own row and `/performance/`: realised
 * result, win rate, the curve and the open position's unrealised PnL are the
 * server's Decimal arithmetic, drawn here and never recomputed.
 */
const props = defineProps<{ bot: BotSummary; busy?: boolean; error?: string }>()
const emit = defineEmits<{ stop: [] }>()

const { t } = useI18n()
const localePath = useLocalePath()
const accounts = useAccountsStore()
const { money, qty, signed } = useFormat()

const id = computed(() => props.bot.id)
const running = computed(() => props.bot.state === 'paper' || props.bot.state === 'live')
const { perf, loading } = useBotPerformance(id, running)

const driven = computed(() => accounts.forBot(props.bot.id))

const winRate = computed(() =>
  perf.value && perf.value.trades > 0
    ? `${Math.round((perf.value.wins / perf.value.trades) * 100)}%`
    : '—',
)

const held = computed(() => perf.value?.position.trade ?? null)
const totals = computed(() => perf.value?.position.totals ?? null)
const unrealised = computed(() => (totals.value?.pnl == null ? null : Number(totals.value.pnl)))

const tone = (value: string | number | null | undefined) =>
  value === null || value === undefined || Number(value) === 0
    ? 'text-ink'
    : Number(value) > 0
      ? 'text-long'
      : 'text-short'
</script>

<template>
  <UiCard :tone="bot.state === 'live' ? 'ok' : 'default'" flush>
    <template #header>
      <div class="flex items-center gap-2 min-w-0 flex-wrap">
        <NuxtLink
          :to="localePath(`/bots/${bot.id}`)"
          class="text-sm font-medium truncate hover:text-brand transition-colors"
        >
          {{ bot.name }}
        </NuxtLink>
        <UiBadge :tone="bot.state === 'live' ? 'ok' : 'brand'" dot>
          {{ t(`bots.state.${bot.state}`) }}
        </UiBadge>
      </div>
      <p class="num text-xs text-ink-muted mt-0.5 truncate">
        {{ bot.symbol }} · {{ bot.interval }} · {{ bot.leverage }}×
      </p>
    </template>
    <template #actions>
      <button class="btn-warn btn-sm" :disabled="busy" @click="emit('stop')">
        <UiIcon name="pause" :size="13" />
        <span class="hidden xs:inline">{{ t('bots.stop.action') }}</span>
      </button>
      <NuxtLink :to="localePath(`/bots/${bot.id}`)" class="btn-ghost btn-sm">
        {{ t('bots.perf.open') }}
        <UiIcon name="arrowRight" :size="13" class="flip-rtl" />
      </NuxtLink>
    </template>

    <div class="p-4 space-y-4">
      <p v-if="error" class="alert px-3 py-2 text-xs leading-relaxed" role="alert">{{ error }}</p>

      <!-- Accounts it drives. A running bot with none routes nowhere, which
           reads as a quiet market unless it is said here. -->
      <p v-if="!driven.length" class="alert px-3 py-2 text-xs leading-relaxed flex flex-wrap gap-x-2">
        <span>{{ t('bots.perf.noAccounts') }}</span>
        <NuxtLink :to="localePath('/accounts')" class="text-brand hover:underline">
          {{ t('bots.openAccounts') }}
        </NuxtLink>
      </p>
      <p v-else class="text-xs text-ink-muted leading-relaxed">
        <span class="text-ink">{{ t('bots.perf.accountsN', { n: driven.length }) }}</span>
        · {{ driven.map((a) => a.label).join(', ') }}
      </p>

      <div v-if="loading && !perf" class="skeleton h-28" />
      <template v-else>
        <dl class="grid grid-cols-3 gap-3">
          <div class="min-w-0">
            <dt class="label">{{ t('bots.perf.realised') }}</dt>
            <dd class="num text-base sm:text-lg font-medium truncate" :class="tone(perf?.realised)">
              {{ perf ? signed(perf.realised) : '—' }}
            </dd>
          </div>
          <div class="min-w-0">
            <dt class="label">{{ t('bots.perf.trades') }}</dt>
            <dd class="num text-base sm:text-lg font-medium">{{ perf?.trades ?? '—' }}</dd>
          </div>
          <div class="min-w-0">
            <dt class="label">{{ t('bots.perf.winRate') }}</dt>
            <dd class="num text-base sm:text-lg font-medium">{{ winRate }}</dd>
          </div>
        </dl>

        <BotsPnlCurve :perf="perf" :height="96" />

        <div class="rounded-lg bg-sunken/50 px-3 py-2.5 text-xs">
          <template v-if="held">
            <div class="flex flex-wrap items-center gap-x-4 gap-y-1">
              <UiBadge :tone="held.side === 'long' ? 'long' : 'short'">
                {{ t(`side.${held.side}`) }} · {{ held.symbol }}
              </UiBadge>
              <span class="text-ink-muted">
                {{ t('position.size') }}
                <span class="num text-ink">{{ totals ? qty(totals.qty) : '—' }}</span>
              </span>
              <span class="text-ink-muted ms-auto">
                {{ t('bots.perf.unrealised') }}
                <span class="num font-medium" :class="tone(unrealised)">
                  {{ unrealised === null ? '—' : signed(unrealised) }}
                </span>
              </span>
            </div>
          </template>
          <p v-else class="text-ink-faint">{{ t('bots.flat') }}</p>
        </div>
      </template>
    </div>
  </UiCard>
</template>
