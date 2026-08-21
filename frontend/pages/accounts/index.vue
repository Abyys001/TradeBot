<script setup lang="ts">
/**
 * Spec §6: add, pause, resume, delete; balances visible at all times.
 *
 * Two renderings of the same rows — a table from `sm` up, cards below it. A
 * seven-column table on a phone is a horizontal scroll, and a horizontal scroll
 * is where the "status" column goes to die.
 */
const { t } = useI18n()
const localePath = useLocalePath()
const accounts = useAccountsStore()
const { money, since } = useFormat()

useHead({ title: t('nav.accounts') })

const connectOpen = ref(false)
const pendingDelete = ref<Account | null>(null)
const busy = ref<number | null>(null)
const actionError = ref('')
const filter = ref<'all' | 'active' | 'paused' | 'attention'>('all')

onMounted(() => accounts.ensure())

const filtered = computed(() => {
  const rows = accounts.byCapital
  if (filter.value === 'active') return rows.filter((a) => a.status === 'active')
  if (filter.value === 'paused') return rows.filter((a) => a.status === 'paused')
  if (filter.value === 'attention') {
    return rows.filter(
      (a) => a.status === 'error' || (a.last_balance_asset && !a.balance_is_usdt),
    )
  }
  return rows
})

const filterOptions = computed(() => [
  { value: 'all', label: `${t('accounts.filter.all')} ${accounts.items.length}` },
  { value: 'active', label: `${t('accounts.filter.active')} ${accounts.active.length}` },
  { value: 'paused', label: `${t('accounts.filter.paused')} ${accounts.paused.length}` },
  {
    value: 'attention',
    label: `${t('accounts.filter.attention')} ${accounts.failing.length}`,
  },
])

const STATUS_TONE = { active: 'ok', paused: 'neutral', error: 'short' } as const

/**
 * Older than three refresh cycles. The panel refreshes every 45s, so anything
 * past ~2.5 minutes means the exchange is not answering — which is a fact about
 * that account, not a rendering detail.
 */
const STALE_AFTER_MS = 150_000
const now = ref(Date.now())
let clock: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  clock = setInterval(() => (now.value = Date.now()), 15000)
})
onBeforeUnmount(() => clock && clearInterval(clock))

function isStale(account: Account) {
  if (!account.last_balance_at) return true
  return now.value - new Date(account.last_balance_at).getTime() > STALE_AFTER_MS
}

async function run(account: Account, fn: () => Promise<unknown>) {
  busy.value = account.id
  actionError.value = ''
  try {
    await fn()
  } catch (e: any) {
    actionError.value = errorMessage(e)
  } finally {
    busy.value = null
  }
}

const toggle = (account: Account) =>
  run(account, () => accounts.setPaused(account, account.status === 'active'))

const verify = (account: Account) => run(account, () => accounts.verify(account))

async function confirmDelete() {
  const account = pendingDelete.value
  if (!account) return
  await run(account, () => accounts.remove(account.id))
  pendingDelete.value = null
}
</script>

<template>
  <div class="max-w-[100rem] mx-auto p-3 sm:p-4 lg:p-6 space-y-3 sm:space-y-4">
    <div class="flex flex-wrap items-center gap-3">
      <div class="min-w-0">
        <h1 class="display text-xl sm:text-2xl">{{ t('accounts.title') }}</h1>
        <p class="text-xs text-ink-muted mt-1">{{ t('accounts.subtitle') }}</p>
      </div>

      <div class="ms-auto flex items-center gap-2">
        <button class="btn-ghost btn-sm" :disabled="accounts.refreshing" @click="accounts.refresh()">
          <UiIcon name="refresh" :size="14" :class="accounts.refreshing ? 'animate-spin' : ''" />
          <span class="hidden xs:inline">
            {{ accounts.refreshing ? t('accounts.refreshing') : t('accounts.refresh') }}
          </span>
        </button>
        <button class="btn-brand btn-sm" @click="connectOpen = true">
          <UiIcon name="plus" :size="14" />
          {{ t('accounts.connect') }}
        </button>
      </div>
    </div>

    <!-- Totals worth seeing before any single row. -->
    <div class="grid grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4">
      <UiStat
        :label="t('accounts.stat.tradeable')"
        :value="`$${money(accounts.tradeableUsdt)}`"
        :sub="t('accounts.stat.tradeableSub', { n: accounts.tradeable.length })"
        icon="wallet"
        :loading="accounts.initial"
      />
      <UiStat
        :label="t('accounts.stat.active')"
        :value="`${accounts.active.length}/${accounts.items.length}`"
        :sub="t('accounts.stat.exchanges', { n: accounts.exchangeCount })"
        icon="accounts"
        :loading="accounts.initial"
      />
      <UiStat
        :label="t('accounts.stat.nonUsdt')"
        :value="accounts.nonUsdt.length"
        :sub="t('accounts.stat.nonUsdtSub')"
        icon="alert"
        :tone="accounts.nonUsdt.length ? 'signal' : 'default'"
        :loading="accounts.initial"
      />
    </div>

    <p v-if="accounts.error || actionError" class="alert p-3 text-xs">
      {{ accounts.error || actionError }}
    </p>

    <UiCard flush>
      <template #header>
        <div class="overflow-x-auto no-scrollbar -my-1 py-1">
          <UiSegmented v-model="filter" :options="filterOptions" size="sm" :block="false" />
        </div>
      </template>

      <!-- Loading: skeleton rows rather than a spinner, so the page does not
           jump when the data lands. -->
      <div v-if="accounts.initial" class="p-4 space-y-3">
        <div v-for="i in 4" :key="i" class="skeleton h-12" />
      </div>

      <template v-else-if="filtered.length">
        <!-- Table, sm and up -->
        <div class="hidden sm:block overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-line">
                <th class="label text-start font-normal px-4 py-2.5">{{ t('accounts.label') }}</th>
                <th class="label text-start font-normal py-2.5">{{ t('accounts.exchange') }}</th>
                <th class="label text-end font-normal py-2.5">{{ t('accounts.balance') }}</th>
                <th class="label text-start font-normal ps-4 py-2.5">{{ t('accounts.status') }}</th>
                <th class="label text-end font-normal px-4 py-2.5">{{ t('accounts.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="account in filtered"
                :key="account.id"
                class="border-b border-line/60 last:border-0 hover:bg-raised/60 transition-colors"
              >
                <td class="px-4 py-3 min-w-0">
                  <div class="flex items-center gap-2 min-w-0">
                    <NuxtLink
                      :to="localePath(`/accounts/${account.id}`)"
                      class="truncate font-medium hover:text-brand transition-colors"
                    >
                      {{ account.label }}
                    </NuxtLink>
                    <UiBadge v-if="account.testnet" tone="brand">{{ t('accounts.testnet') }}</UiBadge>
                    <!-- Only ever rendered for the one operator who can see the
                         account at all: no other session receives the row. -->
                    <UiBadge v-if="account.hidden" tone="signal">
                      <UiIcon name="eyeOff" :size="12" />
                      {{ t('accounts.hidden') }}
                    </UiBadge>
                  </div>
                  <p v-if="account.last_error" class="text-xs text-signal mt-0.5 truncate max-w-xs">
                    {{ account.last_error }}
                  </p>
                </td>
                <td class="text-ink-muted py-3">{{ account.exchange_label }}</td>
                <td class="text-end py-3 whitespace-nowrap">
                  <span class="num">{{ money(account.last_balance) }}</span>
                  <span class="text-ink-faint text-xs ms-1">{{ account.last_balance_asset || '—' }}</span>
                  <!-- Spec §6 wants a *current* balance. When it is not, say so
                       in amber rather than letting a five-hour-old figure read
                       as live because it is rendered in the same grey. -->
                  <p
                    v-if="account.last_balance_at"
                    class="text-[0.65rem]"
                    :class="isStale(account) ? 'text-signal' : 'text-ink-faint'"
                  >
                    {{ since(account.last_balance_at) }}
                  </p>
                  <p v-else class="text-[0.65rem] text-signal">{{ t('accounts.neverFetched') }}</p>
                </td>
                <td class="ps-4 py-3">
                  <div class="flex flex-wrap items-center gap-1.5">
                    <UiBadge :tone="STATUS_TONE[account.status]" dot>
                      {{ t(`accounts.state.${account.status}`) }}
                    </UiBadge>
                    <UiBadge v-if="account.last_balance_asset && !account.balance_is_usdt" tone="signal">
                      {{ account.last_balance_asset }}
                    </UiBadge>
                  </div>
                </td>
                <td class="px-4 py-3">
                  <div class="flex items-center justify-end gap-1.5">
                    <!-- The account's own page: when it was connected, what it
                         was paid, every leg it was given. The list can only
                         ever answer "is it connected and what is it worth". -->
                    <NuxtLink
                      :to="localePath(`/accounts/${account.id}`)"
                      class="btn-quiet btn-sm"
                      :title="t('accounts.openReport')"
                    >
                      <UiIcon name="external" :size="13" />
                      <span class="hidden lg:inline">{{ t('accounts.details') }}</span>
                    </NuxtLink>
                    <!-- Pause is amber because a paused account is the same
                         "not trading" state the badges use; resume is the
                         healthy green. Same colour, same meaning, everywhere. -->
                    <button
                      :class="account.status === 'active' ? 'btn-warn' : 'btn-ok'"
                      class="btn-sm btn-icon"
                      :disabled="busy === account.id"
                      :title="account.status === 'active' ? t('accounts.pause') : t('accounts.resume')"
                      :aria-label="account.status === 'active' ? t('accounts.pause') : t('accounts.resume')"
                      @click="toggle(account)"
                    >
                      <UiIcon
                        v-if="busy === account.id"
                        name="refresh"
                        :size="13"
                        class="animate-spin"
                      />
                      <UiIcon
                        v-else
                        :name="account.status === 'active' ? 'pause' : 'play'"
                        :size="13"
                      />
                    </button>
                    <button
                      class="btn-info btn-sm btn-icon"
                      :disabled="busy === account.id"
                      :title="t('accounts.verify')"
                      :aria-label="t('accounts.verify')"
                      @click="verify(account)"
                    >
                      <UiIcon name="shield" :size="13" />
                    </button>
                    <button
                      class="btn-danger btn-sm btn-icon"
                      :title="t('accounts.delete')"
                      :aria-label="t('accounts.delete')"
                      @click="pendingDelete = account"
                    >
                      <UiIcon name="trash" :size="13" />
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Cards, below sm -->
        <ul class="sm:hidden divide-y divide-line">
          <li v-for="account in filtered" :key="account.id" class="p-4 space-y-3">
            <div class="flex items-start gap-2">
              <div class="min-w-0 flex-1">
                <NuxtLink
                  :to="localePath(`/accounts/${account.id}`)"
                  class="font-medium truncate block hover:text-brand transition-colors"
                >
                  {{ account.label }}
                </NuxtLink>
                <p class="text-xs text-ink-muted">{{ account.exchange_label }}</p>
              </div>
              <div class="text-end">
                <p class="num text-sm">{{ money(account.last_balance) }}</p>
                <p class="text-[0.65rem] text-ink-faint">{{ account.last_balance_asset || '—' }}</p>
              </div>
            </div>

            <div class="flex flex-wrap gap-1.5">
              <UiBadge :tone="STATUS_TONE[account.status]" dot>
                {{ t(`accounts.state.${account.status}`) }}
              </UiBadge>
              <UiBadge v-if="account.testnet" tone="brand">{{ t('accounts.testnet') }}</UiBadge>
              <UiBadge v-if="account.hidden" tone="signal">
                <UiIcon name="eyeOff" :size="12" />
                {{ t('accounts.hidden') }}
              </UiBadge>
            </div>

            <p v-if="account.last_error" class="text-xs text-signal">{{ account.last_error }}</p>

            <div class="flex gap-2">
              <NuxtLink
                :to="localePath(`/accounts/${account.id}`)"
                class="btn-quiet btn-sm flex-1 justify-center"
              >
                <UiIcon name="external" :size="13" />
                {{ t('accounts.details') }}
              </NuxtLink>
              <button
                :class="account.status === 'active' ? 'btn-warn' : 'btn-ok'"
                class="btn-sm flex-1"
                :disabled="busy === account.id"
                @click="toggle(account)"
              >
                <UiIcon :name="account.status === 'active' ? 'pause' : 'play'" :size="13" />
                {{ account.status === 'active' ? t('accounts.pause') : t('accounts.resume') }}
              </button>
              <button
                class="btn-info btn-sm"
                :disabled="busy === account.id"
                :aria-label="t('accounts.verify')"
                @click="verify(account)"
              >
                <UiIcon name="shield" :size="13" />
                <span class="xs:inline">{{ t('accounts.verify') }}</span>
              </button>
              <button
                class="btn-danger btn-sm btn-icon shrink-0"
                :aria-label="t('accounts.delete')"
                @click="pendingDelete = account"
              >
                <UiIcon name="trash" :size="13" />
              </button>
            </div>
          </li>
        </ul>
      </template>

      <UiEmpty
        v-else
        icon="wallet"
        :title="filter === 'all' ? t('accounts.empty') : t('accounts.emptyFilter')"
        :body="filter === 'all' ? t('accounts.emptyBody') : undefined"
      >
        <button v-if="filter === 'all'" class="btn-brand btn-sm" @click="connectOpen = true">
          {{ t('accounts.connect') }}
        </button>
        <button v-else class="btn-ghost btn-sm" @click="filter = 'all'">
          {{ t('accounts.filter.all') }}
        </button>
      </UiEmpty>
    </UiCard>

    <AccountsConnectForm v-model="connectOpen" />

    <!-- Deleting a connection is irreversible and the credential cannot be
         recovered, so it asks in a dialog rather than a browser confirm(). -->
    <UiModal
      :model-value="pendingDelete !== null"
      :title="t('accounts.deleteTitle')"
      size="sm"
      @update:model-value="pendingDelete = null"
    >
      <p class="text-sm leading-relaxed">
        {{ t('accounts.confirmDelete', { label: pendingDelete?.label ?? '' }) }}
      </p>
      <template #footer>
        <div class="flex gap-2 justify-end">
          <button class="btn-ghost" @click="pendingDelete = null">{{ t('common.cancel') }}</button>
          <button class="btn-danger" @click="confirmDelete">{{ t('accounts.delete') }}</button>
        </div>
      </template>
    </UiModal>
  </div>
</template>
