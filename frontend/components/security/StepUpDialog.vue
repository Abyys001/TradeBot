<script setup lang="ts">
/**
 * "Confirm your password to continue."
 *
 * Raised by the store when a write comes back with `step_up_required`, and by
 * nothing else. It never stands in front of opening, amending or closing a
 * position, or in front of the halt — see `apps/security/stepup.py` for why
 * that exclusion is the design rather than an omission.
 *
 * The grant lives in the session, so confirming here covers the next few
 * minutes of writes in this browser and no other.
 */
const { t } = useI18n()
const security = useSecurityStore()

const open = computed({
  get: () => security.stepUpPending,
  set: (value: boolean) => (security.stepUpPending = value),
})

const password = ref('')
const error = ref('')
const pending = ref(false)
const reveal = ref(false)

const emit = defineEmits<{ confirmed: [] }>()

watch(open, (isOpen) => {
  if (isOpen) {
    password.value = ''
    error.value = ''
  }
})

async function submit() {
  if (!password.value || pending.value) return
  pending.value = true
  error.value = await security.confirmPassword(password.value)
  pending.value = false
  if (!error.value) {
    password.value = ''
    emit('confirmed')
  }
}
</script>

<template>
  <UiModal v-model="open" :title="t('security.stepUp.title')" size="sm">
    <form id="step-up-form" class="space-y-4" @submit.prevent="submit">
      <p class="text-sm text-ink-muted leading-relaxed">{{ t('security.stepUp.body') }}</p>

      <UiField v-slot="{ id }" :label="t('login.password')">
        <div class="relative">
          <input
            :id="id"
            v-model="password"
            :type="reveal ? 'text' : 'password'"
            class="field pe-10"
            autocomplete="current-password"
            required
            autofocus
          />
          <button
            type="button"
            class="absolute inset-y-0 end-0 px-3 text-ink-faint hover:text-ink"
            :aria-label="t('common.reveal')"
            @click="reveal = !reveal"
          >
            <UiIcon :name="reveal ? 'eyeOff' : 'eye'" :size="16" />
          </button>
        </div>
      </UiField>

      <p v-if="error" class="alert p-2.5 text-xs">{{ error }}</p>
    </form>

    <template #footer>
      <div class="flex gap-2 justify-end">
        <button class="btn-ghost" @click="open = false">{{ t('common.cancel') }}</button>
        <button
          class="btn-brand"
          type="submit"
          form="step-up-form"
          :disabled="!password || pending"
        >
          {{ pending ? t('security.stepUp.confirming') : t('security.stepUp.confirm') }}
        </button>
      </div>
    </template>
  </UiModal>
</template>
