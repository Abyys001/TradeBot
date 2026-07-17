<script setup lang="ts">
import AccountPanel from '../modules/settings/AccountPanel.vue'
import CredentialsPanel from '../modules/settings/CredentialsPanel.vue'
import SignumSettingsPanel from '../modules/settings/SignumSettingsPanel.vue'
import TelegramSettingsPanel from '../modules/settings/TelegramSettingsPanel.vue'
import { useI18n } from 'vue-i18n'
import { useTheme } from '../composables/useTheme'

const { t } = useI18n()
const { theme, toggle } = useTheme()
</script>

<template>
  <div class="flex-1 overflow-y-auto p-6 space-y-6 max-w-2xl">
    <h1 class="text-lg font-semibold text-zinc-200">{{ t('settings.title') }}</h1>

    <section class="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 flex items-center justify-between">
      <div>
        <h2 class="text-sm font-medium text-zinc-200">Appearance</h2>
        <p class="text-xs text-zinc-500">Toggle light / dark theme.</p>
      </div>
      <button
        type="button"
        class="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-800"
        @click="toggle"
      >
        {{ theme === 'dark' ? '☀️ Light' : '🌙 Dark' }}
      </button>
    </section>

    <AccountPanel />
    <CredentialsPanel />
    <TelegramSettingsPanel />
    <SignumSettingsPanel />
  </div>
</template>
