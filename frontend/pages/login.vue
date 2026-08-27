<script setup lang="ts">
/**
 * Sign in.
 *
 * Session cookies, not tokens — see the backend's auth_views. The form's only
 * job beyond that is to fail clearly: a wrong password and an unreachable API
 * must not look the same, because one is a typo and the other is an outage.
 *
 * With the optional second factor armed the form has a second pane. It is a
 * pane rather than a page so the browser's password manager still sees one
 * form, and the "remember this browser" box lives on the first pane because
 * that is where the operator is already deciding about this machine.
 * `auth.challenge` is what switches between them, and it is empty whenever the
 * switch is off — which is the default.
 */
definePageMeta({ layout: 'public' })

const { t } = useI18n()
const auth = useAuthStore()
const route = useRoute()
const localePath = useLocalePath()

useHead({ title: t('login.title') })

const form = reactive({ username: '', password: '', code: '', remember: false })
const reveal = ref(false)

async function go() {
  const next = route.query.next
  await navigateTo(typeof next === 'string' && next ? next : localePath('/dashboard'))
}

async function submit() {
  if (await auth.login(form.username, form.password, form.remember)) await go()
  // Not signed in and not refused means a code is wanted; the pane swaps
  // itself on `auth.challenge`. Clear the password either way — it has done
  // its job and there is no reason for it to sit in memory through a code entry.
  form.password = ''
}

async function submitCode() {
  if (await auth.mfa(form.code, form.remember)) await go()
  form.code = ''
}
</script>

<template>
  <div class="min-h-[calc(100dvh-3.5rem)] grid place-items-center px-4 py-10">
    <div class="w-full max-w-sm">
      <h1 class="display text-2xl">{{ t('login.title') }}</h1>
      <p class="text-sm text-ink-muted mt-2 leading-relaxed">{{ t('login.lede') }}</p>

      <form v-if="!auth.challenge" class="panel p-5 mt-6 space-y-4" @submit.prevent="submit">
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

        <label class="flex items-center gap-2 text-xs text-ink-muted cursor-pointer select-none">
          <input v-model="form.remember" type="checkbox" class="accent-brand" />
          {{ t('login.remember') }}
        </label>

        <p v-if="auth.error" class="alert p-2.5 text-xs">{{ auth.error }}</p>

        <button class="btn-brand w-full" :disabled="auth.pending">
          {{ auth.pending ? t('login.signingIn') : t('login.signIn') }}
        </button>
      </form>

      <!-- The second pane. Reached only when the second factor is switched on
           and this browser is not one the operator chose to remember. -->
      <form v-else class="panel p-5 mt-6 space-y-4" @submit.prevent="submitCode">
        <div>
          <p class="text-sm font-medium">{{ t('login.mfaTitle') }}</p>
          <p class="text-xs text-ink-muted mt-1 leading-relaxed">{{ t('login.mfaBody') }}</p>
        </div>

        <UiField
          v-slot="{ id }"
          :label="t('login.mfaCode')"
          :hint="auth.recoveryAvailable ? t('login.mfaRecoveryHint') : undefined"
        >
          <input
            :id="id"
            v-model="form.code"
            class="field num text-center text-lg tracking-[0.3em]"
            inputmode="text"
            autocomplete="one-time-code"
            autofocus
            required
          />
        </UiField>

        <p v-if="auth.error" class="alert p-2.5 text-xs">{{ auth.error }}</p>

        <button class="btn-brand w-full" :disabled="auth.pending || !form.code">
          {{ auth.pending ? t('login.signingIn') : t('login.verify') }}
        </button>
        <button type="button" class="btn-ghost btn-sm w-full" @click="auth.cancelMfa()">
          {{ t('common.back') }}
        </button>
      </form>

      <p class="text-xs text-ink-faint mt-4 leading-relaxed">{{ t('login.note') }}</p>
      <code class="block text-[0.65rem] num text-ink-faint mt-2 bg-sunken border border-line rounded p-2 overflow-x-auto">
        docker compose exec backend python manage.py createsuperuser
      </code>
    </div>
  </div>
</template>
