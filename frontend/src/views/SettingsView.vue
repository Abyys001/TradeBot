<script setup lang="ts">
import AccountPanel from '../modules/settings/AccountPanel.vue'
import CredentialsPanel from '../modules/settings/CredentialsPanel.vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="flex-1 overflow-y-auto p-6 space-y-6 max-w-2xl">
    <h1 class="text-lg font-semibold text-zinc-200">{{ t('settings.title') }}</h1>
    <AccountPanel />
    <CredentialsPanel />
  </div>
</template>
