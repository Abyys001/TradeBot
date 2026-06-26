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
      <input
        v-model="password"
        type="password"
        autocomplete="current-password"
        class="w-full mb-4 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-zinc-100 focus:border-emerald-500 focus:outline-none"
      />
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
