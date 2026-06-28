<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import PineMonacoEditor from '../../../components/PineMonacoEditor.vue'
import AppModal from '../../../components/AppModal.vue'
import type { StrategyForm } from '../../../composables/useStrategyForm'

const props = defineProps<{ strategyForm: StrategyForm }>()
const { t } = useI18n()

const sf = props.strategyForm
const fileInput = ref<HTMLInputElement | null>(null)
const showEditor = ref(false)
const validating = ref(false)

const selected = computed(() => sf.selected.value)
const hasSource = computed(() => !!sf.form.source.trim())

function browse() {
  fileInput.value?.click()
}

async function runValidate() {
  validating.value = true
  try {
    await sf.validate()
  } finally {
    validating.value = false
  }
}
</script>

<template>
  <div class="space-y-4">
    <div>
      <h3 class="text-sm font-semibold text-zinc-200">{{ t('live.strategyStep.title') }}</h3>
    </div>

    <input
      ref="fileInput"
      type="file"
      accept=".pine,.txt,.pinescript"
      class="hidden"
      @change="sf.onFileInput"
    />

    <div>
      <label class="text-xs text-zinc-500">{{ t('live.strategyStep.name') }}</label>
      <input
        v-model="sf.form.name"
        class="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
      />
    </div>

    <div
      class="rounded-lg border border-dashed px-4 py-6 text-center text-xs text-zinc-500 transition-colors"
      :class="sf.dragOver.value ? 'border-emerald-500 bg-emerald-950/20' : 'border-zinc-700'"
      @dragover.prevent="sf.dragOver.value = true"
      @dragleave="sf.dragOver.value = false"
      @drop.prevent="sf.onDrop"
    >
      {{ t('strategies.dropPine') }}
      <div class="mt-2 flex justify-center gap-3">
        <button type="button" class="text-violet-400 hover:underline" @click="browse">
          {{ t('strategies.uploadPine') }}
        </button>
        <button type="button" class="text-violet-400 hover:underline" @click="showEditor = true">
          {{ t('live.strategyStep.openEditor') }}
        </button>
      </div>
    </div>

    <div v-if="hasSource" class="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
      <pre class="max-h-32 overflow-y-auto font-mono text-[11px] leading-relaxed text-zinc-400">{{ sf.form.source }}</pre>
    </div>

    <div class="flex items-center gap-3">
      <button
        type="button"
        class="rounded-lg bg-violet-700 px-4 py-2 text-sm font-medium text-white hover:bg-violet-600 disabled:opacity-50"
        :disabled="validating || !hasSource"
        @click="runValidate"
      >
        {{ validating ? t('live.strategyStep.validating') : t('strategy.validate') }}
      </button>
      <span v-if="!hasSource" class="text-xs text-zinc-600">{{ t('live.strategyStep.needSource') }}</span>
      <span v-else-if="selected?.validation_status === 'ok'" class="text-xs text-emerald-400">
        ✓ {{ t('live.strategyStep.validated') }}
      </span>
      <span v-else-if="sf.validationMsg.value" class="font-mono text-xs text-red-400">{{ sf.validationMsg.value }}</span>
    </div>

    <AppModal v-if="showEditor" :title="t('live.strategyStep.openEditor')" size="full" @close="showEditor = false">
      <div class="h-full p-4" style="min-height: calc(100vh - 8rem)">
        <PineMonacoEditor
          :model-value="sf.form.source"
          @update:model-value="(v) => sf.setSource(v)"
        />
      </div>
      <template #footer>
        <div class="flex justify-end">
          <button
            type="button"
            class="rounded-lg bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
            @click="showEditor = false"
          >
            {{ t('modal.close') }}
          </button>
        </div>
      </template>
    </AppModal>
  </div>
</template>
