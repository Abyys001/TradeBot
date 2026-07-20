<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { useRouter, RouterLink } from 'vue-router'
import UiInput from '../components/UiInput.vue'
import UiButton from '../components/UiButton.vue'

const { t } = useI18n()
const auth = useAuthStore()
const router = useRouter()

const username = ref('')
const password = ref('')
const showPassword = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  try {
    await auth.login(username.value, password.value)
    router.push({ name: 'overview' })
  } catch {
    error.value = t('auth.invalid')
  }
}
</script>

<template>
  <div class="relative min-h-dvh flex items-center justify-center bg-surface px-4 overflow-hidden">
    <!-- Animated background orbs -->
    <div class="pointer-events-none absolute inset-0 overflow-hidden">
      <div class="orb orb-1" />
      <div class="orb orb-2" />
      <div class="orb orb-3" />
    </div>

    <!-- Grid overlay -->
    <div class="pointer-events-none absolute inset-0 opacity-[0.03]"
      style="background-image: linear-gradient(color-mix(in srgb, var(--tb-fg) 60%, transparent) 1px, transparent 1px), linear-gradient(90deg, color-mix(in srgb, var(--tb-fg) 60%, transparent) 1px, transparent 1px); background-size: 60px 60px;"
    />

    <RouterLink
      :to="{ name: 'landing' }"
      class="absolute start-4 top-4 z-10 flex items-center gap-1 text-sm text-fg-muted hover:text-fg transition-colors"
    >
      <svg class="h-4 w-4 rtl-flip" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
      </svg>
      {{ t('nav.backToHome') }}
    </RouterLink>

    <form
      class="login-card relative w-full max-w-sm rounded-2xl border border-border bg-surface-raised/80 p-8 shadow-xl backdrop-blur-sm"
      @submit.prevent="submit"
    >
      <!-- Logo -->
      <div class="flex justify-center mb-6">
        <div class="logo-icon flex h-12 w-12 items-center justify-center rounded-xl bg-accent shadow-lg shadow-accent/25">
          <svg viewBox="0 0 24 24" class="h-6 w-6 text-accent-fg" fill="none" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z" />
          </svg>
        </div>
      </div>

      <h1 class="text-center text-lg font-semibold text-fg mb-8">{{ t('app.title') }}</h1>

      <div class="space-y-4">
        <UiInput
          v-model="username"
          :label="t('auth.username')"
          type="text"
          autocomplete="username"
          required
          class="login-field"
          style="animation-delay: 0.1s"
        />

        <div class="login-field relative" style="animation-delay: 0.2s">
          <UiInput
            v-model="password"
            :label="t('auth.password')"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="current-password"
            required
          >
            <template #trailing>
              <button
                type="button"
                class="absolute inset-y-0 end-0 flex items-center px-3 text-fg-muted hover:text-fg transition-colors"
                :aria-label="showPassword ? t('auth.hidePassword') : t('auth.showPassword')"
                @click="showPassword = !showPassword"
              >
                <svg v-if="showPassword" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" class="h-5 w-5">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M3.98 8.223A10.477 10.477 0 0 0 1.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.451 10.451 0 0 1 12 4.5c4.756 0 8.773 3.162 10.065 7.498a10.522 10.522 0 0 1-4.293 5.774M6.228 6.228 3 3m3.228 3.228 3.65 3.65m7.894 7.894L21 21m-3.228-3.228-3.65-3.65m0 0a3 3 0 1 0-4.243-4.243m4.242 4.242L9.88 9.88" />
                </svg>
                <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" class="h-5 w-5">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z" />
                  <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                </svg>
              </button>
            </template>
          </UiInput>
        </div>
      </div>

      <Transition
        enter-active-class="transition-all duration-200"
        enter-from-class="opacity-0 -translate-y-1"
        enter-to-class="opacity-100 translate-y-0"
      >
        <p v-if="error" class="error-msg text-negative text-sm mt-4 text-center">{{ error }}</p>
      </Transition>

      <UiButton
        type="submit"
        variant="primary"
        class="login-field mt-6 w-full"
        :loading="auth.loading"
        :disabled="auth.loading"
        style="animation-delay: 0.3s"
      >
        {{ t('auth.signIn') }}
      </UiButton>

      <p class="mt-6 text-center text-xs text-fg-muted/60">Algo Trader v1.0</p>
    </form>
  </div>
</template>

<style scoped>
.login-card {
  animation: cardEnter 0.6s ease-out both;
}

.login-field {
  animation: fadeUp 0.5s ease-out both;
}

.error-msg {
  animation: shakeX 0.4s ease-in-out;
}

@keyframes cardEnter {
  from { opacity: 0; transform: translateY(24px) scale(0.97); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

@keyframes fadeUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes shakeX {
  0%, 100% { transform: translateX(0); }
  10%, 50%, 90% { transform: translateX(-6px); }
  30%, 70% { transform: translateX(6px); }
}

@keyframes orbFloat {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, -30px) scale(1.05); }
  66% { transform: translate(-20px, 20px) scale(0.95); }
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.15;
  animation: orbFloat 20s ease-in-out infinite;
}

[data-theme="dark"] .orb { opacity: 0.18; }

.orb-1 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, var(--tb-accent), transparent 70%);
  top: -100px; right: -100px;
}

.orb-2 {
  width: 350px; height: 350px;
  background: radial-gradient(circle, #6366f1, transparent 70%);
  bottom: -80px; left: -80px;
  animation-delay: -7s;
}

.orb-3 {
  width: 250px; height: 250px;
  background: radial-gradient(circle, #a78bfa, transparent 70%);
  top: 50%; left: 50%;
  animation-delay: -14s;
  opacity: 0.08;
}
</style>
