<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { submitLead } from '../../api/public'
import UiInput from '../../components/UiInput.vue'
import UiButton from '../../components/UiButton.vue'

const { t, locale } = useI18n()

const name = ref('')
const email = ref('')
const contact = ref('')
const message = ref('')
const website = ref('') // honeypot

const status = ref<'idle' | 'submitting' | 'success' | 'error'>('idle')

async function submit() {
  status.value = 'submitting'
  try {
    await submitLead({
      name: name.value,
      email: email.value,
      contact: contact.value,
      message: message.value,
      locale: locale.value,
      website: website.value,
    })
    status.value = 'success'
    name.value = ''
    email.value = ''
    contact.value = ''
    message.value = ''
  } catch {
    status.value = 'error'
  }
}
</script>

<template>
  <section id="request-access" class="mx-auto max-w-xl px-4 py-20 sm:px-6">
    <div class="text-center">
      <span class="inline-block rounded-full bg-accent-muted px-3 py-1 text-xs font-medium text-accent">{{ t('landing.nav.requestAccess') }}</span>
      <h2 class="mt-4 text-3xl font-bold tracking-tight text-fg sm:text-4xl">{{ t('landing.requestAccess.title') }}</h2>
      <p class="mx-auto mt-3 max-w-2xl text-lg text-fg-muted">{{ t('landing.requestAccess.subtitle') }}</p>
    </div>

    <form
      v-if="status !== 'success'"
      class="mt-10 space-y-5 rounded-2xl border border-border bg-surface-raised p-8 shadow-lg shadow-black/[0.03] backdrop-blur-sm dark:shadow-black/20"
      @submit.prevent="submit"
    >
      <UiInput v-model="name" :label="t('landing.requestAccess.name')" required />

      <UiInput v-model="email" type="email" :label="t('landing.requestAccess.email')" required />

      <UiInput v-model="contact" :label="t('landing.requestAccess.contact')" :hint="t('landing.requestAccess.contact').includes('اختیاری') ? '' : ''" />

      <div>
        <label class="mb-1.5 block text-sm font-medium text-fg">{{ t('landing.requestAccess.message') }}</label>
        <textarea
          v-model="message"
          rows="3"
          class="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-fg transition-all duration-200 placeholder:text-fg-muted/50 hover:border-border-hover focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
        />
      </div>

      <!-- Honeypot -->
      <div class="h-0 w-0 overflow-hidden opacity-0" aria-hidden="true">
        <input v-model="website" type="text" tabindex="-1" autocomplete="off" />
      </div>

      <p v-if="status === 'error'" class="text-sm text-negative">{{ t('landing.requestAccess.error') }}</p>

      <UiButton type="submit" :loading="status === 'submitting'" variant="primary" class="w-full">
        {{ status === 'submitting' ? t('landing.requestAccess.submitting') : t('landing.requestAccess.submit') }}
      </UiButton>
    </form>

    <Transition
      enter-active-class="transition-all duration-300 ease-out"
      enter-from-class="opacity-0 scale-95"
      enter-to-class="opacity-100 scale-100"
    >
      <div v-if="status === 'success'" class="mt-10 rounded-2xl border border-positive/30 bg-success-bg p-8 text-center">
        <div class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-positive/10">
          <svg class="h-6 w-6 text-positive" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <p class="font-medium text-positive">{{ t('landing.requestAccess.success') }}</p>
      </div>
    </Transition>
  </section>
</template>
