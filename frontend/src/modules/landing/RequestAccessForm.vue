<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { submitLead } from '../../api/public'

const { t, locale } = useI18n()

const name = ref('')
const email = ref('')
const contact = ref('')
const message = ref('')
const website = ref('') // honeypot — real users never see or fill this

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
  <section id="request-access" class="mx-auto max-w-xl px-4 py-16 sm:px-6">
    <div class="text-center">
      <h2 class="text-2xl font-bold text-fg sm:text-3xl">{{ t('landing.requestAccess.title') }}</h2>
      <p class="mt-2 text-fg-muted">{{ t('landing.requestAccess.subtitle') }}</p>
    </div>

    <form
      v-if="status !== 'success'"
      class="mt-8 space-y-4 rounded-xl border border-border bg-surface-raised p-6"
      @submit.prevent="submit"
    >
      <div>
        <label class="mb-1 block text-sm text-fg-muted">{{ t('landing.requestAccess.name') }}</label>
        <input
          v-model="name"
          type="text"
          required
          class="w-full rounded-lg border border-border bg-surface px-3 py-2 text-fg focus:border-accent/70 focus:outline-none"
        />
      </div>

      <div>
        <label class="mb-1 block text-sm text-fg-muted">{{ t('landing.requestAccess.email') }}</label>
        <input
          v-model="email"
          type="email"
          required
          class="w-full rounded-lg border border-border bg-surface px-3 py-2 text-fg focus:border-accent/70 focus:outline-none"
        />
      </div>

      <div>
        <label class="mb-1 block text-sm text-fg-muted">{{ t('landing.requestAccess.contact') }}</label>
        <input
          v-model="contact"
          type="text"
          class="w-full rounded-lg border border-border bg-surface px-3 py-2 text-fg focus:border-accent/70 focus:outline-none"
        />
      </div>

      <div>
        <label class="mb-1 block text-sm text-fg-muted">{{ t('landing.requestAccess.message') }}</label>
        <textarea
          v-model="message"
          rows="3"
          class="w-full rounded-lg border border-border bg-surface px-3 py-2 text-fg focus:border-accent/70 focus:outline-none"
        />
      </div>

      <!-- Honeypot: zero-size and aria-hidden so it's invisible to real users
           (sighted or screen-reader) but still present in the DOM for bots
           that blindly fill every field to trip. -->
      <div class="h-0 w-0 overflow-hidden opacity-0" aria-hidden="true">
        <input v-model="website" type="text" tabindex="-1" autocomplete="off" />
      </div>

      <p v-if="status === 'error'" class="text-sm text-negative">{{ t('landing.requestAccess.error') }}</p>

      <button
        type="submit"
        :disabled="status === 'submitting'"
        class="w-full rounded-lg bg-accent px-4 py-2.5 font-medium text-accent-fg hover:opacity-90 transition-opacity disabled:opacity-60"
      >
        {{ status === 'submitting' ? t('landing.requestAccess.submitting') : t('landing.requestAccess.submit') }}
      </button>
    </form>

    <div v-else class="mt-8 rounded-xl border border-positive/40 bg-success-bg p-6 text-center text-positive">
      {{ t('landing.requestAccess.success') }}
    </div>
  </section>
</template>
