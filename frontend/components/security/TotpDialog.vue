<script setup lang="ts">
/**
 * Enrolling an authenticator app — three steps, in three panes.
 *
 * The steps are not ceremony. A secret written but never proved would arm a
 * prompt nobody can answer, and codes minted but never saved would turn a lost
 * phone into a lost platform. So: scan, prove, save. The switch stays refused
 * until all three are done, which is the lock-out escape expressed as a
 * refusal rather than a warning.
 *
 * The QR arrives as inline SVG from the server. Inline because the panel's own
 * Content-Security-Policy — which this same card can switch on — would block an
 * external image, and this dialog must not be the thing that breaks under it.
 */
const { t } = useI18n()
const api = useApi()
const security = useSecurityStore()

const open = defineModel<boolean>({ required: true })

type Step = 'scan' | 'confirm' | 'save'
const step = ref<Step>('scan')
const secret = ref('')
const qr = ref('')
const code = ref('')
const codes = ref<string[]>([])
const error = ref('')
const pending = ref(false)
const copied = ref(false)
const showSecret = ref(false)

watch(open, async (isOpen) => {
  if (!isOpen) return
  step.value = 'scan'
  code.value = ''
  codes.value = []
  error.value = ''
  showSecret.value = false
  pending.value = true
  try {
    const started = await api.totpBegin()
    secret.value = started.secret
    qr.value = started.qr_svg
  } catch (e: unknown) {
    error.value = errorMessage(e)
  } finally {
    pending.value = false
  }
})

async function confirm() {
  if (code.value.length < 6 || pending.value) return
  pending.value = true
  error.value = ''
  try {
    const result = await api.totpConfirm(code.value)
    codes.value = result.recovery_codes
    security.applyTotp(result)
    step.value = 'save'
  } catch (e: unknown) {
    error.value = errorMessage(e)
  } finally {
    pending.value = false
  }
}

async function finish() {
  pending.value = true
  try {
    security.applyTotp(await api.totpAcknowledge())
    open.value = false
  } catch (e: unknown) {
    error.value = errorMessage(e)
  } finally {
    pending.value = false
  }
}

/** Best effort: clipboard access is blocked outside a secure context, and the
    codes are on screen anyway — the button going quiet is the whole failure. */
async function copyCodes() {
  try {
    await navigator.clipboard.writeText(codes.value.join('\n'))
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    copied.value = false
  }
}

function downloadCodes() {
  const blob = new Blob([codes.value.join('\n') + '\n'], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'tradebot-recovery-codes.txt'
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <UiModal v-model="open" :title="t('security.totp.title')">
    <!-- 1. Scan -->
    <div v-if="step === 'scan'" class="space-y-4">
      <p class="text-sm text-ink-muted leading-relaxed">{{ t('security.totp.scanBody') }}</p>

      <div v-if="pending" class="skeleton h-44 w-44 mx-auto rounded-xl" />
      <div
        v-else-if="qr"
        class="mx-auto w-44 h-44 rounded-xl bg-white p-2 grid place-items-center [&_svg]:w-full [&_svg]:h-full"
        v-html="qr"
      />

      <div class="rounded-lg border border-line bg-sunken px-3 py-2.5">
        <div class="flex items-center gap-2">
          <p class="label">{{ t('security.totp.manualKey') }}</p>
          <button
            type="button"
            class="ms-auto text-ink-faint hover:text-ink"
            :aria-label="t('common.reveal')"
            @click="showSecret = !showSecret"
          >
            <UiIcon :name="showSecret ? 'eyeOff' : 'eye'" :size="14" />
          </button>
        </div>
        <p class="num text-xs mt-1.5 break-all">
          {{ showSecret ? secret : '•'.repeat(32) }}
        </p>
        <p class="text-[0.7rem] text-ink-faint mt-1.5 leading-relaxed">
          {{ t('security.totp.manualHint') }}
        </p>
      </div>
    </div>

    <!-- 2. Prove the app holds it -->
    <form v-else-if="step === 'confirm'" id="totp-confirm" class="space-y-4" @submit.prevent="confirm">
      <p class="text-sm text-ink-muted leading-relaxed">{{ t('security.totp.confirmBody') }}</p>
      <UiField v-slot="{ id }" :label="t('security.totp.code')">
        <input
          :id="id"
          v-model="code"
          class="field num text-center text-lg tracking-[0.4em]"
          inputmode="numeric"
          autocomplete="one-time-code"
          maxlength="6"
          autofocus
        />
      </UiField>
    </form>

    <!-- 3. The codes, shown once -->
    <div v-else class="space-y-4">
      <div class="alert p-3 text-xs leading-relaxed">{{ t('security.totp.saveWarning') }}</div>

      <ul class="grid grid-cols-2 gap-1.5 rounded-lg border border-line bg-sunken p-3">
        <li v-for="one in codes" :key="one" class="num text-xs">{{ one }}</li>
      </ul>

      <div class="flex gap-2">
        <button class="btn-ghost btn-sm" @click="copyCodes">
          <UiIcon :name="copied ? 'check' : 'fileText'" :size="14" />
          {{ copied ? t('common.copied') : t('security.totp.copy') }}
        </button>
        <button class="btn-ghost btn-sm" @click="downloadCodes">
          <UiIcon name="download" :size="14" />
          {{ t('security.totp.download') }}
        </button>
      </div>
    </div>

    <p v-if="error" class="alert p-2.5 text-xs mt-4">{{ error }}</p>

    <template #footer>
      <div class="flex gap-2 justify-end">
        <button v-if="step !== 'save'" class="btn-ghost" @click="open = false">
          {{ t('common.cancel') }}
        </button>

        <button
          v-if="step === 'scan'"
          class="btn-brand"
          :disabled="pending || !qr"
          @click="step = 'confirm'"
        >
          {{ t('common.next') }}
        </button>
        <button
          v-else-if="step === 'confirm'"
          class="btn-brand"
          type="submit"
          form="totp-confirm"
          :disabled="code.length < 6 || pending"
        >
          {{ t('security.totp.verify') }}
        </button>
        <button v-else class="btn-brand" :disabled="pending" @click="finish">
          {{ t('security.totp.saved') }}
        </button>
      </div>
    </template>
  </UiModal>
</template>
