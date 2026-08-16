<script setup lang="ts">
/**
 * Financial management: deposits, withdrawals, PnL, and the profit split.
 *
 * Two sources of truth, combined on the server (apps/accounts/ledger.py) and
 * never recomputed here: cash flows are recorded by hand — the API keys are
 * trade-only (spec §7), so no exchange can tell us who moved money in or out —
 * and the current balance is the exchange's live number from the regular
 * polling. PnL is "what it is worth now minus what went in", since inception.
 *
 * The split percentages are global (set in Settings) and divide profit only;
 * on a loss there is nothing to divide, so the shares are zero.
 */
const { t } = useI18n()
const api = useApi()
const accounts = useAccountsStore()
const { money, pct, dateTime } = useFormat()

useHead({ title: t('nav.finance') })

const SPLIT_ROLES = ['investor', 'trader', 'programmer'] as const
type SplitRole = (typeof SPLIT_ROLES)[number]

const snapshot = ref<LedgerSnapshot | null>(null)
const loading = ref(true)
const error = ref('')

const movements = ref<FundMovement[]>([])
const movementsLoading = ref(false)

const addOpen = ref(false)
const saving = ref(false)
const formError = ref('')
const form = reactive({
  account: null as number | null,
  kind: 'deposit' as 'deposit' | 'withdrawal',
  amount: '',
  note: '',
})

const pendingDelete = ref<FundMovement | null>(null)
const deleting = ref(false)

onMounted(async () => {
  await accounts.ensure()
  await Promise.all([load(), loadMovements()])
})

async function load() {
  loading.value = true
  try {
    snapshot.value = await api.ledger()
    error.value = ''
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

async function loadMovements() {
  movementsLoading.value = true
  try {
    movements.value = await api.movements()
  } finally {
    movementsLoading.value = false
  }
}

const kindOptions = computed(() => [
  { value: 'deposit', label: t('finance.movements.deposit'), tone: 'ok' as const },
  { value: 'withdrawal', label: t('finance.movements.withdrawal'), tone: 'signal' as const },
])

function pnlTone(value: string | null): 'default' | 'long' | 'short' {
  const n = Number(value)
  if (value === null || Number.isNaN(n) || n === 0) return 'default'
  return n > 0 ? 'long' : 'short'
}

const PNL_TEXT: Record<'default' | 'long' | 'short', string> = {
  default: 'text-ink',
  long: 'text-long',
  short: 'text-short',
}

function pnlClass(value: string | null): string {
  return PNL_TEXT[pnlTone(value)]
}

/** "+$12.34" / "−$5.00" / "—". A negative PnL is rendered as an explicit minus. */
function pnlText(value: string | null): string {
  if (value === null) return '—'
  const n = Number(value)
  return `${n > 0 ? '+' : n < 0 ? '−' : ''}$${money(value)}`
}

function roleLabel(role: SplitRole) {
  return t(`finance.role.${role}`)
}

function splitValue(): string {
  const s = snapshot.value?.split
  if (!s) return '—'
  return SPLIT_ROLES.map((role) => `${money(s[role], 0)}%`).join(' · ')
}

function openAdd() {
  form.account = accounts.items[0]?.id ?? null
  form.kind = 'deposit'
  form.amount = ''
  form.note = ''
  formError.value = ''
  addOpen.value = true
}

async function createMovement() {
  const amount = Number(form.amount)
  if (!form.account || !Number.isFinite(amount) || amount <= 0) {
    formError.value = t('finance.form.invalid')
    return
  }
  saving.value = true
  formError.value = ''
  try {
    await api.createMovement({
      account: form.account,
      kind: form.kind,
      amount: form.amount,
      note: form.note || undefined,
    })
    addOpen.value = false
    await Promise.all([load(), loadMovements()])
  } catch (e: any) {
    formError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

async function confirmDelete() {
  const movement = pendingDelete.value
  if (!movement) return
  deleting.value = true
  try {
    await api.deleteMovement(movement.id)
    pendingDelete.value = null
    await Promise.all([load(), loadMovements()])
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="max-w-[100rem] mx-auto p-3 sm:p-4 lg:p-6 space-y-3 sm:space-y-4">
    <div class="flex flex-wrap items-center gap-3">
      <div class="min-w-0">
        <h1 class="display text-xl sm:text-2xl">{{ t('finance.title') }}</h1>
        <p class="text-xs text-ink-muted mt-1">{{ t('finance.subtitle') }}</p>
      </div>

      <button class="btn-ghost btn-sm ms-auto" :disabled="loading" @click="load">
        <UiIcon name="refresh" :size="14" :class="loading ? 'animate-spin' : ''" />
        <span class="hidden xs:inline">{{ t('common.reload') }}</span>
      </button>
    </div>

    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
      <UiStat
        :label="t('finance.stat.invested')"
        :value="`$${money(snapshot?.totals.net_invested)}`"
        :sub="t('finance.stat.investedSub')"
        icon="wallet"
        :loading="loading"
      />
      <UiStat
        :label="t('finance.stat.current')"
        :value="`$${money(snapshot?.totals.current_balance)}`"
        :sub="t('finance.stat.currentSub')"
        icon="accounts"
        :loading="loading"
      />
      <UiStat
        :label="t('finance.stat.pnl')"
        :value="pnlText(snapshot?.totals.pnl ?? null)"
        :sub="t('finance.stat.pnlSub')"
        :tone="pnlTone(snapshot?.totals.pnl ?? null)"
        icon="trend"
        :loading="loading"
      />
      <UiStat
        :label="t('finance.stat.split')"
        :value="splitValue()"
        :sub="t('finance.stat.splitSub')"
        icon="ledger"
        :loading="loading"
      >
        <!-- The three share chips: who gets what, of this very number. -->
        <div class="flex flex-wrap gap-1.5 mt-2">
          <UiBadge v-for="role in SPLIT_ROLES" :key="role">
            {{ roleLabel(role) }}
            <span class="num">${{ money(snapshot?.totals.shares[role]) }}</span>
          </UiBadge>
        </div>
      </UiStat>
    </div>

    <p v-if="error" class="alert p-3 text-xs">{{ error }}</p>

    <template v-if="loading">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        <div v-for="i in 2" :key="i" class="skeleton h-28 rounded-panel" />
      </div>
      <div class="skeleton h-72 rounded-panel" />
    </template>

    <template v-else-if="snapshot">
      <!-- Non-USDT accounts are real rows but cannot join a dollar total. -->
      <p
        v-if="snapshot.non_usdt.length"
        class="alert p-3 text-xs flex flex-wrap gap-x-1"
      >
        {{ t('finance.nonUsdt') }}:
        <span v-for="row in snapshot.non_usdt" :key="row.account" class="num">
          {{ row.label }} ({{ row.asset }}),
        </span>
        <span>{{ t('finance.nonUsdtSub') }}</span>
      </p>

      <!-- Per-exchange aggregate -->
      <div v-if="snapshot.exchanges.length" class="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        <UiCard
          v-for="exchange in snapshot.exchanges"
          :key="exchange.exchange"
          :title="exchange.label"
        >
          <template #actions>
            <UiBadge tone="neutral">{{ t('finance.exchangeAccounts', { n: exchange.accounts }) }}</UiBadge>
          </template>
          <dl class="grid grid-cols-3 gap-3">
            <div>
              <dt class="label">{{ t('finance.exchangesInvested') }}</dt>
              <dd class="num mt-1">{{ money(exchange.net_invested) }}</dd>
            </div>
            <div>
              <dt class="label">{{ t('finance.exchangesCurrent') }}</dt>
              <dd class="num mt-1">{{ money(exchange.current_balance) }}</dd>
            </div>
            <div>
              <dt class="label">{{ t('finance.exchangesPnl') }}</dt>
              <dd class="num mt-1" :class="pnlClass(exchange.pnl)">
                {{ pnlText(exchange.pnl) }}
              </dd>
            </div>
          </dl>
        </UiCard>
      </div>

      <!-- Per-account ledger -->
      <UiCard flush v-if="snapshot.accounts.length">
        <div class="hidden md:block overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-line">
                <th class="label text-start font-normal px-4 py-2.5">{{ t('finance.table.account') }}</th>
                <th class="label text-start font-normal py-2.5">{{ t('finance.table.exchange') }}</th>
                <th class="label text-end font-normal py-2.5">{{ t('finance.table.deposits') }}</th>
                <th class="label text-end font-normal py-2.5">{{ t('finance.table.withdrawals') }}</th>
                <th class="label text-end font-normal py-2.5">{{ t('finance.table.net') }}</th>
                <th class="label text-end font-normal py-2.5">{{ t('finance.table.current') }}</th>
                <th class="label text-end font-normal py-2.5">{{ t('finance.table.pnl') }}</th>
                <th class="label text-end font-normal py-2.5">{{ t('finance.table.pnlPct') }}</th>
                <th class="label text-end font-normal px-4 py-2.5">{{ t('finance.table.split') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in snapshot.accounts"
                :key="row.account"
                class="border-b border-line/60 last:border-0 hover:bg-raised/40 transition-colors"
              >
                <td class="px-4 py-3">
                  <span class="font-medium">{{ row.label }}</span>
                  <UiBadge v-if="row.testnet" tone="brand" class="ms-1.5">{{ t('accounts.testnet') }}</UiBadge>
                </td>
                <td class="text-ink-muted py-3">{{ row.exchange_label }}</td>
                <td class="num text-end py-3">{{ money(row.deposits) }}</td>
                <td class="num text-end py-3">{{ money(row.withdrawals) }}</td>
                <td class="num text-end py-3">{{ money(row.net_invested) }}</td>
                <td class="num text-end py-3">
                  {{ money(row.current_balance) }}
                  <span class="text-ink-faint text-xs">{{ row.asset }}</span>
                </td>
                <td class="num text-end py-3" :class="pnlClass(row.pnl)">
                  {{ pnlText(row.pnl) }}
                </td>
                <td class="num text-end py-3 text-ink-muted">{{ pct(row.pnl_pct) }}</td>
                <td class="px-4 py-3">
                  <div class="text-[0.7rem] text-end leading-tight whitespace-nowrap">
                    <div v-for="role in SPLIT_ROLES" :key="role">
                      {{ roleLabel(role) }}
                      <span class="num">${{ money(row.shares[role]) }}</span>
                    </div>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Cards, below md -->
        <ul class="md:hidden divide-y divide-line">
          <li v-for="row in snapshot.accounts" :key="row.account" class="p-4 space-y-2.5">
            <div class="flex items-baseline justify-between gap-2">
              <span class="font-medium text-sm">{{ row.label }}</span>
              <span class="text-xs text-ink-muted">{{ row.exchange_label }}</span>
            </div>
            <dl class="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
              <div class="flex justify-between gap-2">
                <dt class="label">{{ t('finance.table.net') }}</dt>
                <dd class="num">{{ money(row.net_invested) }}</dd>
              </div>
              <div class="flex justify-between gap-2">
                <dt class="label">{{ t('finance.table.current') }}</dt>
                <dd class="num">{{ money(row.current_balance) }}</dd>
              </div>
              <div class="flex justify-between gap-2">
                <dt class="label">{{ t('finance.table.pnl') }}</dt>
                <dd class="num" :class="pnlClass(row.pnl)">
                  {{ pnlText(row.pnl) }}
                </dd>
              </div>
              <div class="flex justify-between gap-2">
                <dt class="label">{{ t('finance.table.pnlPct') }}</dt>
                <dd class="num text-ink-muted">{{ pct(row.pnl_pct) }}</dd>
              </div>
            </dl>
            <div class="flex flex-wrap gap-x-3 gap-y-1 text-[0.7rem]">
              <span v-for="role in SPLIT_ROLES" :key="role" class="text-ink-muted">
                {{ roleLabel(role) }}
                <span class="num text-ink">${{ money(row.shares[role]) }}</span>
              </span>
            </div>
          </li>
        </ul>
      </UiCard>

      <UiCard v-else>
        <UiEmpty
          icon="ledger"
          :title="t('finance.empty')"
          :body="t('finance.emptyBody')"
        />
      </UiCard>

      <!-- Cash movements, recorded by hand -->
      <UiCard :title="t('finance.movements.title')" :hint="t('finance.movements.subtitle')" flush>
        <template #actions>
          <button class="btn-brand btn-sm" @click="openAdd">
            <UiIcon name="plus" :size="14" />
            {{ t('finance.movements.add') }}
          </button>
        </template>

        <div v-if="movementsLoading" class="p-4 space-y-2">
          <div v-for="i in 3" :key="i" class="skeleton h-10" />
        </div>

        <ul v-else-if="movements.length" class="divide-y divide-line">
          <li
            v-for="movement in movements"
            :key="movement.id"
            class="px-4 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5"
          >
            <UiBadge :tone="movement.kind === 'deposit' ? 'ok' : 'signal'" dot>
              {{ t(`finance.movements.${movement.kind}`) }}
            </UiBadge>
            <span class="text-sm font-medium">{{ movement.account_label }}</span>
            <span class="num text-sm" :class="movement.kind === 'deposit' ? 'text-ok' : 'text-signal'">
              {{ movement.kind === 'deposit' ? '+' : '−' }}{{ money(movement.amount) }}
            </span>
            <span v-if="movement.note" class="text-xs text-ink-muted truncate max-w-[16rem]">
              {{ movement.note }}
            </span>
            <span class="num text-xs text-ink-faint ms-auto">{{ dateTime(movement.occurred_at) }}</span>
            <button
              class="btn-quiet btn-sm btn-icon shrink-0"
              :aria-label="t('accounts.delete')"
              @click="pendingDelete = movement"
            >
              <UiIcon name="trash" :size="13" />
            </button>
          </li>
        </ul>

        <div v-else class="p-6">
          <UiEmpty
            icon="ledger"
            :title="t('finance.movements.empty')"
            :body="t('finance.movements.emptyBody')"
          />
        </div>
      </UiCard>
    </template>

    <!-- Record a deposit / withdrawal -->
    <UiModal v-model="addOpen" :title="t('finance.addTitle')" size="sm">
      <div class="space-y-4">
        <UiField :label="t('finance.form.account')">
          <template #default="{ id, describedBy }">
            <select :id="id" v-model="form.account" class="field" :aria-describedby="describedBy">
              <option v-for="account in accounts.items" :key="account.id" :value="account.id">
                {{ account.label }} — {{ account.exchange_label }}
              </option>
            </select>
          </template>
        </UiField>

        <UiField :label="t('finance.form.kind')">
          <UiSegmented v-model="form.kind" :options="kindOptions" :block="true" />
        </UiField>

        <UiField :label="t('finance.form.amount')" :error="formError">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              v-model="form.amount"
              class="field"
              inputmode="decimal"
              :placeholder="t('finance.form.amountPlaceholder')"
              :aria-describedby="describedBy"
            />
          </template>
        </UiField>

        <UiField :label="t('finance.form.note')" :hint="t('finance.form.noteHint')" :optional="true">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              v-model="form.note"
              class="field"
              :placeholder="t('finance.form.notePlaceholder')"
              :aria-describedby="describedBy"
            />
          </template>
        </UiField>
      </div>

      <template #footer>
        <div class="flex gap-2 justify-end">
          <button class="btn-ghost" @click="addOpen = false">{{ t('common.cancel') }}</button>
          <button class="btn-brand" :disabled="saving" @click="createMovement">
            <UiIcon v-if="saving" name="refresh" :size="14" class="animate-spin" />
            {{ t('finance.form.save') }}
          </button>
        </div>
      </template>
    </UiModal>

    <!-- Deleting a movement changes money records, so it asks first. -->
    <UiModal
      :model-value="pendingDelete !== null"
      :title="t('finance.deleteTitle')"
      size="sm"
      @update:model-value="pendingDelete = null"
    >
      <p class="text-sm leading-relaxed">
        {{ t('finance.deleteBody', {
          kind: t(`finance.movements.${pendingDelete?.kind ?? 'deposit'}`),
          amount: money(pendingDelete?.amount),
          account: pendingDelete?.account_label ?? '',
        }) }}
      </p>
      <template #footer>
        <div class="flex gap-2 justify-end">
          <button class="btn-ghost" :disabled="deleting" @click="pendingDelete = null">
            {{ t('common.cancel') }}
          </button>
          <button class="btn-danger" :disabled="deleting" @click="confirmDelete">
            <UiIcon v-if="deleting" name="refresh" :size="14" class="animate-spin" />
            {{ t('accounts.delete') }}
          </button>
        </div>
      </template>
    </UiModal>
  </div>
</template>
