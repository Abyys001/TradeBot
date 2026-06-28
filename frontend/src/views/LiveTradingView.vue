<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../stores/strategy'
import SetupWizard from '../modules/live/wizard/SetupWizard.vue'
import CommandCenter from '../modules/live/command/CommandCenter.vue'

const { t } = useI18n()
const store = useStrategyStore()

type Mode = 'wizard' | 'command'
const mode = ref<Mode>('wizard')
const loading = ref(true)

onMounted(async () => {
  try {
    await store.fetchAll()
    mode.value = store.liveStrategies.length ? 'command' : 'wizard'
  } finally {
    loading.value = false
  }
})

async function onDeployed() {
  await store.fetchAll()
  mode.value = 'command'
}

function onCancel() {
  mode.value = store.liveStrategies.length ? 'command' : 'wizard'
}
</script>

<template>
  <div class="h-full min-h-0">
    <div v-if="loading" class="flex h-full items-center justify-center text-zinc-500">
      {{ t('overview.loading') }}
    </div>
    <CommandCenter
      v-else-if="mode === 'command'"
      @new-deployment="mode = 'wizard'"
    />
    <SetupWizard
      v-else
      @deployed="onDeployed"
      @cancel="onCancel"
    />
  </div>
</template>
