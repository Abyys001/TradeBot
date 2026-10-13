<script setup lang="ts">
/**
 * The bots, on the dashboard.
 *
 * A bot that is trading appears here by itself, expanded — nobody should have
 * to pick it from a list to see whether it is making or losing money. Bots
 * that are not running sit below as compact rows with a start button, so the
 * whole fleet can be run from this one block. Manual trading is a separate
 * section further down; the two stay visibly distinct.
 */
const { t } = useI18n()
const localePath = useLocalePath()
const bots = useBotsStore()
const accounts = useAccountsStore()

const busyId = ref<number | null>(null)
const errors = ref<Record<number, string>>({})

onMounted(() => {
  if (!bots.bots.length && !bots.loading) bots.load()
})

const idle = computed(() => bots.bots.filter((bot) => bot.state === 'draft' || bot.state === 'stopped'))

async function act(bot: BotSummary, action: 'paper' | 'stop') {
  busyId.value = bot.id
  delete errors.value[bot.id]
  try {
    if (action === 'stop') await bots.stop(bot.id, t('bots.stoppedByHand'))
    else await bots.start(bot.id, 'paper')
  } catch (e: any) {
    errors.value[bot.id] = e?.data?.gate ? t('bots.gateUnmetHere') : errorMessage(e)
  } finally {
    busyId.value = null
  }
}
</script>

<template>
  <section class="space-y-3" :aria-label="t('dashboard.bots.title')">
    <div class="flex items-center gap-3">
      <div class="min-w-0">
        <h2 class="display text-base sm:text-lg">{{ t('dashboard.bots.title') }}</h2>
        <p class="text-xs text-ink-muted mt-0.5">
          {{ t('dashboard.bots.running', { n: bots.running.length }) }}
        </p>
      </div>
      <NuxtLink :to="localePath('/bots')" class="btn-ghost btn-sm ms-auto">
        {{ t('dashboard.viewAll') }}
      </NuxtLink>
    </div>

    <div v-if="bots.loading && !bots.bots.length" class="skeleton h-40" />

    <UiCard v-else-if="!bots.bots.length">
      <UiEmpty icon="bot" :title="t('bots.none')" :body="t('bots.noneBody')">
        <NuxtLink :to="localePath('/bots')" class="btn-brand btn-sm">{{ t('bots.newBot') }}</NuxtLink>
      </UiEmpty>
    </UiCard>

    <template v-else>
      <div v-if="bots.running.length" class="grid gap-3 sm:gap-4 grid-cols-1 xl:grid-cols-2">
        <BotsBotCard
          v-for="bot in bots.running"
          :key="bot.id"
          :bot="bot"
          :busy="busyId === bot.id"
          :error="errors[bot.id]"
          @stop="act(bot, 'stop')"
        />
      </div>
      <p v-else class="text-xs text-ink-faint px-1">{{ t('dashboard.bots.noneRunning') }}</p>

      <UiCard v-if="idle.length" flush>
        <ul class="divide-y divide-line">
          <li v-for="bot in idle" :key="bot.id" class="px-4 py-2.5 space-y-1.5">
            <div class="flex items-center gap-2 min-w-0">
              <div class="min-w-0 flex-1">
                <NuxtLink
                  :to="localePath(`/bots/${bot.id}`)"
                  class="text-sm font-medium truncate block hover:text-brand transition-colors"
                >
                  {{ bot.name }}
                </NuxtLink>
                <p class="num text-xs text-ink-muted truncate">
                  {{ bot.symbol }} · {{ bot.interval }} ·
                  {{ t('bots.perf.accountsN', { n: accounts.forBot(bot.id).length }) }}
                </p>
              </div>
              <UiBadge :tone="bot.state === 'stopped' ? 'signal' : 'neutral'">
                {{ t(`bots.state.${bot.state}`) }}
              </UiBadge>
              <button
                class="btn-info btn-sm shrink-0"
                :disabled="busyId === bot.id"
                @click="act(bot, 'paper')"
              >
                <UiIcon name="play" :size="13" />
                <span class="hidden xs:inline">{{ t('bots.startPaper') }}</span>
              </button>
            </div>
            <p v-if="errors[bot.id]" class="text-xs text-signal leading-relaxed" role="alert">
              {{ errors[bot.id] }}
              <NuxtLink :to="localePath(`/bots/${bot.id}`)" class="text-brand hover:underline ms-1">
                {{ t('bots.perf.open') }}
              </NuxtLink>
            </p>
          </li>
        </ul>
      </UiCard>
    </template>
  </section>
</template>
