<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { useRouter } from 'vue-router'

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
  <div class="min-h-screen flex items-center justify-center bg-zinc-950 px-4">
    <form
      class="w-full max-w-sm rounded-xl border border-zinc-800 bg-zinc-900 p-8 shadow-xl"
      @submit.prevent="submit"
    >
      <h1 class="text-xl font-semibold text-zinc-100 mb-6">{{ t('app.title') }}</h1>
      <label class="block text-sm text-zinc-400 mb-1">{{ t('auth.username') }}</label>
      <input
        v-model="username"
        type="text"
        autocomplete="username"
        class="w-full mb-4 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-zinc-100 focus:border-emerald-500 focus:outline-none"
      />
      <label class="block text-sm text-zinc-400 mb-1">{{ t('auth.password') }}</label>
      <div class="relative mb-4">
        <input
          v-model="password"
          :type="showPassword ? 'text' : 'password'"
          autocomplete="current-password"
          class="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 pe-10 text-zinc-100 focus:border-emerald-500 focus:outline-none"
        />
        <button
          type="button"
          class="absolute inset-y-0 end-0 flex items-center px-3 text-zinc-400 hover:text-zinc-200 transition-colors"
          :aria-label="showPassword ? t('auth.hidePassword') : t('auth.showPassword')"
          @click="showPassword = !showPassword"
        >
          <svg
            v-if="showPassword"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.75"
            class="h-5 w-5"
            aria-hidden="true"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M3.98 8.223A10.477 10.477 0 0 0 1.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.451 10.451 0 0 1 12 4.5c4.756 0 8.773 3.162 10.065 7.498a10.522 10.522 0 0 1-4.293 5.774M6.228 6.228 3 3m3.228 3.228 3.65 3.65m7.894 7.894L21 21m-3.228-3.228-3.65-3.65m0 0a3 3 0 1 0-4.243-4.243m4.242 4.242L9.88 9.88"
            />
          </svg>
          <svg
            v-else
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.75"
            class="h-5 w-5"
            aria-hidden="true"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z"
            />
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
          </svg>
        </button>
      </div>
      <p v-if="error" class="text-red-400 text-sm mb-3">{{ error }}</p>
      <button
        type="submit"
        class="w-full rounded-lg bg-emerald-600 py-2.5 font-medium text-white hover:bg-emerald-500 transition-colors"
        :disabled="auth.loading"
      >
        {{ t('auth.signIn') }}
      </button>
    </form>
  </div>
</template>
