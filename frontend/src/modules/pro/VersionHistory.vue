<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useProStore } from '../../stores/pro'
import { useStrategyStore } from '../../stores/strategy'
import { useToast } from '../../composables/useToast'

const props = defineProps<{ strategyId: number }>()
const { t } = useI18n()
const pro = useProStore()
const store = useStrategyStore()
const toast = useToast()

onMounted(() => pro.fetchVersions(props.strategyId))

async function snapshot() {
  await pro.snapshotVersion(props.strategyId)
  toast.show(t('versions.saved'), 'success')
}

async function restore(version: number) {
  await pro.restoreVersion(props.strategyId, version)
  await store.fetchAll()
  store.select(props.strategyId)
  toast.show(t('versions.restored'), 'success')
}
</script>

<template>
  <div class="border-t border-zinc-800 pt-3 space-y-2">
    <div class="flex items-center justify-between">
      <h4 class="text-xs font-medium text-zinc-400">{{ t('versions.title') }}</h4>
      <button type="button" class="text-[10px] text-violet-400 hover:underline" @click="snapshot">
        {{ t('versions.snapshot') }}
      </button>
    </div>
    <div v-if="!pro.versions.length" class="text-[10px] text-zinc-600">{{ t('versions.empty') }}</div>
    <ul v-else class="space-y-1 max-h-24 overflow-y-auto">
      <li
        v-for="v in pro.versions"
        :key="v.id"
        class="flex items-center justify-between text-[10px] text-zinc-400"
      >
        <span>v{{ v.version }} · {{ new Date(v.created_at).toLocaleDateString() }}</span>
        <button type="button" class="text-violet-400 hover:underline" @click="restore(v.version)">
          {{ t('versions.restore') }}
        </button>
      </li>
    </ul>
  </div>
</template>
