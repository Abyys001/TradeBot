<script setup lang="ts">
/**
 * Connect a partner account (spec §6), in a dialog.
 *
 * The credential fields change shape per exchange: Hyperliquid needs an agent
 * wallet private key plus the master address, OKX and KuCoin need a passphrase,
 * the rest need key + secret. Showing all fields to everyone invites pasting a
 * secret into the wrong box — which, with real trading credentials, is not a
 * recoverable mistake.
 *
 * Secrets are typed into password fields with a deliberate reveal, never
 * echoed back by the server, and never pre-filled.
 */
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ created: [] }>()

const { t } = useI18n()
const api = useApi()
const accounts = useAccountsStore()
const auth = useAuthStore()

const exchanges = ref<ExchangeInfo[]>([])
const submitting = ref(false)
const error = ref('')
const reveal = reactive({ secret: false, passphrase: false })

const form = reactive({
  label: '',
  exchange: 'paper',
  testnet: false,
  hidden: false,
  api_key: '',
  api_secret: '',
  api_passphrase: '',
  wallet_address: '',
})

onMounted(async () => {
  try {
    exchanges.value = (await api.exchanges()).exchanges
  } catch {
    exchanges.value = []
  }
})

const selected = computed(() => exchanges.value.find((e) => e.exchange === form.exchange))
const isWallet = computed(() => selected.value?.wallet_based_auth ?? false)
const needsPassphrase = computed(() => ['okx', 'kucoin'].includes(form.exchange))
const isPaper = computed(() => form.exchange === 'paper')

function reset() {
  Object.assign(form, {
    label: '',
    hidden: false,
    api_key: '',
    api_secret: '',
    api_passphrase: '',
    wallet_address: '',
  })
  reveal.secret = false
  reveal.passphrase = false
  error.value = ''
}

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    await api.createAccount({ ...form })
    reset()
    open.value = false
    await accounts.load()
    emit('created')
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <UiModal v-model="open" :title="t('accounts.connect')">
    <form id="connect-account" class="space-y-4" @submit.prevent="submit">
      <div class="grid sm:grid-cols-2 gap-4">
        <UiField v-slot="{ id }" :label="t('accounts.label')">
          <input :id="id" v-model="form.label" class="field" required :placeholder="t('accounts.labelPlaceholder')" />
        </UiField>

        <UiField v-slot="{ id }" :label="t('accounts.exchange')">
          <select :id="id" v-model="form.exchange" class="field">
            <option v-for="ex in exchanges" :key="ex.exchange" :value="ex.exchange">
              {{ ex.label }}
            </option>
          </select>
        </UiField>
      </div>

      <!-- Spec §9 / Q9: never offer a testnet toggle for an exchange without
           one. Claiming a test environment that does not exist sends someone
           to trade real money believing they are not. -->
      <UiSwitch
        v-if="selected?.has_testnet"
        v-model="form.testnet"
        :label="t('accounts.useTestnet')"
        :hint="t('accounts.useTestnetHint')"
      />
      <p v-else-if="selected && !isPaper" class="alert p-2.5 text-xs">
        {{ selected.note || t('accounts.noTestnet') }}
      </p>

      <!-- Only the one operator allowed to see hidden accounts is offered the
           toggle. Rendering it for everyone else would advertise the feature,
           and the server refuses the field from anyone else regardless. -->
      <UiSwitch
        v-if="auth.canSeeHidden"
        v-model="form.hidden"
        :label="t('accounts.hidden')"
        :hint="t('accounts.hiddenHint')"
      />

      <template v-if="!isPaper">
        <!-- Hyperliquid: agent wallet key, not an API key/secret pair. -->
        <template v-if="isWallet">
          <UiField v-slot="{ id }" :label="t('accounts.agentKey')" :hint="t('accounts.agentKeyHint')">
            <div class="relative">
              <input
                :id="id"
                v-model="form.api_passphrase"
                :type="reveal.passphrase ? 'text' : 'password'"
                class="field pe-10"
                autocomplete="off"
                spellcheck="false"
                required
              />
              <button
                type="button"
                class="absolute inset-y-0 end-0 px-3 text-ink-faint hover:text-ink"
                :aria-label="t('common.reveal')"
                @click="reveal.passphrase = !reveal.passphrase"
              >
                <UiIcon :name="reveal.passphrase ? 'eyeOff' : 'eye'" :size="16" />
              </button>
            </div>
          </UiField>

          <UiField
            v-slot="{ id }"
            :label="t('accounts.masterAddress')"
            :hint="t('accounts.masterAddressHint')"
          >
            <input :id="id" v-model="form.wallet_address" class="field" placeholder="0x…" required />
          </UiField>
        </template>

        <template v-else>
          <UiField v-slot="{ id }" :label="t('accounts.apiKey')">
            <input
              :id="id"
              v-model="form.api_key"
              class="field"
              autocomplete="off"
              spellcheck="false"
              required
            />
          </UiField>

          <UiField v-slot="{ id }" :label="t('accounts.apiSecret')">
            <div class="relative">
              <input
                :id="id"
                v-model="form.api_secret"
                :type="reveal.secret ? 'text' : 'password'"
                class="field pe-10"
                autocomplete="off"
                spellcheck="false"
                required
              />
              <button
                type="button"
                class="absolute inset-y-0 end-0 px-3 text-ink-faint hover:text-ink"
                :aria-label="t('common.reveal')"
                @click="reveal.secret = !reveal.secret"
              >
                <UiIcon :name="reveal.secret ? 'eyeOff' : 'eye'" :size="16" />
              </button>
            </div>
          </UiField>

          <UiField v-if="needsPassphrase" v-slot="{ id }" :label="t('accounts.passphrase')">
            <input
              :id="id"
              v-model="form.api_passphrase"
              type="password"
              class="field"
              autocomplete="off"
              required
            />
          </UiField>
        </template>

        <p class="alert p-3 text-xs flex gap-2 leading-relaxed">
          <UiIcon name="shield" :size="15" class="mt-0.5" />
          <span>{{ t('accounts.withdrawalWarning') }}</span>
        </p>
      </template>

      <p v-if="error" class="text-xs text-short">{{ error }}</p>
    </form>

    <template #footer>
      <div class="flex gap-2 justify-end">
        <button class="btn-ghost" type="button" @click="open = false">
          {{ t('common.cancel') }}
        </button>
        <button class="btn-brand" type="submit" form="connect-account" :disabled="submitting">
          {{ submitting ? t('accounts.connecting') : t('accounts.connect') }}
        </button>
      </div>
    </template>
  </UiModal>
</template>
