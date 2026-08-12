<script setup lang="ts">
/**
 * Sign in.
 *
 * Session cookies, not tokens — see the backend's auth_views. The form's only
 * job beyond that is to fail clearly: a wrong password and an unreachable API
 * must not look the same, because one is a typo and the other is an outage.
 */
definePageMeta({ layout: 'public' })

const { t } = useI18n()
const auth = useAuthStore()
const route = useRoute()
const localePath = useLocalePath()

useHead({ title: t('login.title') })

const form = reactive({ username: '', password: '' })
const reveal = ref(false)

async function submit() {
  if (await auth.login(form.username, form.password)) {
    const next = route.query.next
    await navigateTo(typeof next === 'string' && next ? next : localePath('/dashboard'))
  }
}
</script>

<template>
  <div class="min-h-[calc(100dvh-3.5rem)] grid place-items-center px-4 py-10">
    <div class="w-full max-w-sm">
      <h1 class="display text-2xl">{{ t('login.title') }}</h1>
      <p class="text-sm text-ink-muted mt-2 leading-relaxed">{{ t('login.lede') }}</p>

      <form class="panel p-5 mt-6 space-y-4" @submit.prevent="submit">
        <UiField v-slot="{ id }" :label="t('login.username')">
          <input
            :id="id"
            v-model="form.username"
            class="field"
            autocomplete="username"
            autofocus
            required
          />
        </UiField>

        <UiField v-slot="{ id }" :label="t('login.password')">
          <div class="relative">
            <input
              :id="id"
              v-model="form.password"
              :type="reveal ? 'text' : 'password'"
              class="field pe-10"
              autocomplete="current-password"
              required
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

        <p v-if="auth.error" class="alert p-2.5 text-xs">{{ auth.error }}</p>

        <button class="btn-brand w-full" :disabled="auth.pending">
          {{ auth.pending ? t('login.signingIn') : t('login.signIn') }}
        </button>
      </form>

      <p class="text-xs text-ink-faint mt-4 leading-relaxed">{{ t('login.note') }}</p>
      <code class="block text-[0.65rem] num text-ink-faint mt-2 bg-sunken border border-line rounded p-2 overflow-x-auto">
        docker compose exec backend python manage.py createsuperuser
      </code>
    </div>
  </div>
</template>
