<script setup lang="ts">
/**
 * "What needs you" — the one panel that earns the top of the dashboard.
 *
 * Everything else on this page reports; this one asks. It gathers the five
 * states that are quietly dangerous and would otherwise each hide on a
 * different page:
 *
 *   - spec §4 failures nobody has dismissed
 *   - keys whose trade-only scope was never proven (spec §7)
 *   - balances not denominated in USDT, which are reported, never traded (Q4)
 *   - filled legs carrying no stop — a live position with no floor
 *   - routing halted platform-wide
 *
 * When it is empty it says so and takes up almost no room. An "all clear" that
 * costs half a screen trains the eye to skip the place warnings appear.
 */
const { t } = useI18n()
const localePath = useLocalePath()
const accounts = useAccountsStore()
const trading = useTradingStore()
const notifications = useNotificationStore()

interface Alert {
  key: string
  tone: 'signal' | 'short'
  title: string
  body: string
  to?: string
  action?: string
}

const alerts = computed<Alert[]>(() => {
  const list: Alert[] = []

  if (trading.policy?.stop_all) {
    list.push({
      key: 'stop-all',
      tone: 'signal',
      title: t('alerts.stopAll.title'),
      body: t('alerts.stopAll.body'),
      to: localePath('/settings'),
      action: t('alerts.viewPolicy'),
    })
  }

  if (notifications.count) {
    list.push({
      key: 'failures',
      tone: 'short',
      title: t('alerts.failures.title', { n: notifications.count }),
      body: notifications.newest
        ? t('alerts.failures.body', {
            account: notifications.newest.accountLabel,
            message: notifications.newest.message,
          })
        : '',
    })
  }

  const unprotected = trading.unprotectedLegs
  if (unprotected.length) {
    list.push({
      key: 'unprotected',
      tone: 'short',
      title: t('alerts.unprotected.title', { n: unprotected.length }),
      body: t('alerts.unprotected.body', {
        accounts: unprotected.map((l) => l.account_label).join(', '),
      }),
      to: localePath('/chart'),
      action: t('alerts.openTerminal'),
    })
  }

  if (accounts.unverified.length) {
    list.push({
      key: 'unverified',
      tone: 'signal',
      title: t('alerts.unverified.title', { n: accounts.unverified.length }),
      body: t('alerts.unverified.body', {
        accounts: accounts.unverified.map((a) => a.label).join(', '),
      }),
      to: localePath('/accounts'),
      action: t('alerts.reviewAccounts'),
    })
  }

  if (accounts.nonUsdt.length) {
    list.push({
      key: 'non-usdt',
      tone: 'signal',
      title: t('alerts.nonUsdt.title', { n: accounts.nonUsdt.length }),
      body: t('alerts.nonUsdt.body', {
        accounts: accounts.nonUsdt.map((a) => `${a.label} (${a.asset})`).join(', '),
      }),
      to: localePath('/accounts'),
      action: t('alerts.reviewAccounts'),
    })
  }

  const failing = accounts.failing
  if (failing.length) {
    list.push({
      key: 'errored',
      tone: 'short',
      title: t('alerts.errored.title', { n: failing.length }),
      body: failing.map((a) => `${a.label}: ${a.last_error || t('alerts.unknownError')}`).join(' · '),
      to: localePath('/accounts'),
      action: t('alerts.reviewAccounts'),
    })
  }

  return list
})
</script>

<template>
  <UiCard :title="t('alerts.title')" :tone="alerts.length ? 'signal' : 'default'" flush>
    <template #actions>
      <UiBadge :tone="alerts.length ? 'signal' : 'ok'" dot>
        {{ alerts.length ? t('alerts.count', { n: alerts.length }) : t('alerts.clear') }}
      </UiBadge>
    </template>

    <ul v-if="alerts.length" class="divide-y divide-line">
      <li
        v-for="alert in alerts"
        :key="alert.key"
        class="p-4 flex flex-col sm:flex-row sm:items-start gap-3"
      >
        <UiIcon
          name="alert"
          :size="16"
          class="mt-0.5 shrink-0"
          :class="alert.tone === 'short' ? 'text-short' : 'text-signal'"
        />
        <div class="min-w-0 flex-1">
          <p class="text-sm font-medium" :class="alert.tone === 'short' ? 'text-short' : 'text-signal'">
            {{ alert.title }}
          </p>
          <p class="text-xs text-ink-muted mt-1 leading-relaxed break-words">{{ alert.body }}</p>
        </div>
        <NuxtLink v-if="alert.to" :to="alert.to" class="btn-ghost btn-sm shrink-0 self-start">
          {{ alert.action }}
        </NuxtLink>
      </li>
    </ul>

    <div v-else class="px-4 py-5 flex items-center gap-3">
      <span class="w-8 h-8 rounded-full grid place-items-center bg-ok/10 text-ok border border-ok/30">
        <UiIcon name="check" :size="15" />
      </span>
      <div>
        <p class="text-sm">{{ t('alerts.emptyTitle') }}</p>
        <p class="text-xs text-ink-muted mt-0.5">{{ t('alerts.emptyBody') }}</p>
      </div>
    </div>
  </UiCard>
</template>
