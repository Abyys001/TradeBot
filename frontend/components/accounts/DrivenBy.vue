<script setup lang="ts">
/**
 * Who trades this account: the admin by hand, or exactly one bot.
 *
 * One control instead of two switches because the two switches could say
 * "both" and "neither", and the platform only has one honest answer per
 * account. The server decides what a change costs: an account holding a
 * position answers 409 `account_has_position` and nothing moves until the
 * admin agrees, here, to close *this account's* leg. The trade carries on
 * everywhere else.
 */
const props = defineProps<{ account: Account; compact?: boolean }>()
const emit = defineEmits<{ changed: [account: Account] }>()

const { t } = useI18n()
const accounts = useAccountsStore()
const bots = useBotsStore()
const security = useSecurityStore()
const { qty, money } = useFormat()

const busy = ref(false)
const error = ref('')
/** The refused switch, waiting on the admin's decision about the open position. */
const conflict = ref<{ target: number | null; info: AccountHasPosition } | null>(null)
const awaitingStepUp = ref(false)
let replay: (() => Promise<void>) | null = null

onMounted(() => {
  if (!bots.bots.length && !bots.loading) bots.load()
})

const selectId = useId()

const targetName = (target: number | null) =>
  target === null ? t('accounts.driven.manual') : (bots.byId(target)?.name ?? `#${target}`)

async function assign(target: number | null, closePosition = false) {
  busy.value = true
  error.value = ''
  replay = () => assign(target, closePosition)
  try {
    const updated = await accounts.assign(props.account, target, closePosition)
    conflict.value = null
    emit('changed', updated)
  } catch (e: any) {
    const data = e?.data ?? {}
    if (data.code === 'step_up_required') {
      awaitingStepUp.value = true
      security.stepUpPending = true
    } else if (data.code === 'account_has_position' && !closePosition) {
      conflict.value = { target, info: data as AccountHasPosition }
    } else {
      // stop_all / no_legs / close_failed: the assignment did not change.
      conflict.value = conflict.value && closePosition ? conflict.value : null
      error.value = errorMessage(e)
    }
  } finally {
    busy.value = false
  }
}

function onSelect(event: Event) {
  const el = event.target as HTMLSelectElement
  const target = el.value === '' ? null : Number(el.value)
  // Show the committed value again until the server agrees.
  el.value = props.account.bot === null ? '' : String(props.account.bot)
  if (target === props.account.bot) return
  assign(target)
}

function afterStepUp() {
  awaitingStepUp.value = false
  replay?.()
}

watch(
  () => security.stepUpPending,
  (open) => {
    if (!open) awaitingStepUp.value = false
  },
)
</script>

<template>
  <div class="min-w-0" :class="compact ? '' : 'space-y-1'">
    <label :for="selectId" class="label block" :class="compact ? 'sr-only' : ''">
      {{ t('accounts.driven.label') }}
    </label>
    <select
      :id="selectId"
      class="field"
      :class="compact ? 'py-1.5 text-xs' : ''"
      :value="account.bot === null ? '' : String(account.bot)"
      :disabled="busy"
      @change="onSelect"
    >
      <option value="">{{ t('accounts.driven.manual') }}</option>
      <option v-for="bot in bots.bots" :key="bot.id" :value="String(bot.id)">
        {{ bot.name }} · {{ t(`bots.state.${bot.state}`) }}
      </option>
    </select>
    <p v-if="error" class="text-xs text-signal leading-relaxed" role="alert">{{ error }}</p>

    <UiModal
      :model-value="conflict !== null"
      :title="t('accounts.driven.positionTitle')"
      size="sm"
      @update:model-value="conflict = null"
    >
      <p v-if="conflict" class="text-sm leading-relaxed">
        {{
          t('accounts.driven.positionBody', {
            side: t(`side.${conflict.info.side}`),
            symbol: conflict.info.symbol,
            qty: qty(conflict.info.qty),
            entry: conflict.info.entry_price ? money(conflict.info.entry_price) : '—',
            target: targetName(conflict.target),
          })
        }}
      </p>
      <p v-if="error" class="alert px-3 py-2 text-xs leading-relaxed mt-3" role="alert">{{ error }}</p>
      <template #footer>
        <div class="flex gap-2 justify-end">
          <button class="btn-ghost btn-sm" @click="conflict = null">{{ t('common.cancel') }}</button>
          <button
            class="btn-danger btn-sm"
            :disabled="busy"
            @click="conflict && assign(conflict.target, true)"
          >
            {{ t('accounts.driven.closeAndSwitch') }}
          </button>
        </div>
      </template>
    </UiModal>

    <SecurityStepUpDialog v-if="awaitingStepUp" @confirmed="afterStepUp" />
  </div>
</template>
