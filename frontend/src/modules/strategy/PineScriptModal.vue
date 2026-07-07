<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppModal from '../../components/AppModal.vue'
import PineMonacoEditor from '../../components/PineMonacoEditor.vue'
import type { StrategyForm } from '../../composables/useStrategyForm'

const props = defineProps<{ strategyForm: StrategyForm }>()
const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()
const fileInput = ref<HTMLInputElement | null>(null)

const sf = props.strategyForm
const isSaving = computed(() => sf.saving.value)
const selectedStrategy = computed(() => sf.selected.value)
const isDragOver = computed(() => sf.dragOver.value)
const validationText = computed(() => sf.validationMsg.value)

function browseFile() {
  fileInput.value?.click()
}

function onDragOver() {
  sf.dragOver.value = true
}

function onDragLeave() {
  sf.dragOver.value = false
}

async function onSave() {
  await sf.save()
}

async function onValidate() {
  await sf.validate()
}
</script>

<template>
  <AppModal :title="t('backtest.editPineScript')" size="full" @close="emit('close')">
    <div class="flex h-full flex-col p-4 gap-3" style="min-height: calc(100vh - 8rem)">
      <input
        ref="fileInput"
        type="file"
        accept=".pine,.txt,.pinescript"
        class="hidden"
        @change="sf.onFileInput"
      />

      <div
        class="shrink-0 rounded-lg border border-dashed px-3 py-2 text-center text-xs text-zinc-500 transition-colors"
        :class="isDragOver ? 'border-emerald-500 bg-emerald-950/20' : 'border-zinc-700'"
        @dragover.prevent="onDragOver"
        @dragleave="onDragLeave"
        @drop.prevent="sf.onDrop"
      >
        {{ t('strategies.dropPine') }}
        <button type="button" class="ms-2 text-violet-400 hover:underline" @click="browseFile">
          {{ t('strategies.uploadPine') }}
        </button>
      </div>

      <div class="flex shrink-0 items-center gap-3 text-xs">
        <span
          v-if="selectedStrategy?.validation_status === 'error'"
          class="text-red-400"
        >
          ✗ {{ selectedStrategy.validation_error || t('strategy.validatedFail') }}
        </span>
        <span
          v-else-if="validationText"
          class="font-mono text-red-400"
        >{{ validationText }}</span>
      </div>

      <div class="min-h-0 flex-1">
        <PineMonacoEditor
          :model-value="sf.form.source"
          @update:model-value="(v) => sf.setSource(v)"
        />
      </div>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <button
          type="button"
          class="rounded-lg px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200"
          @click="emit('close')"
        >
          {{ t('modal.close') }}
        </button>
        <button
          type="button"
          class="rounded-lg bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
          :disabled="isSaving"
          @click="onSave"
        >
          {{ t('modal.save') }}
        </button>
        <button
          type="button"
          class="rounded-lg bg-violet-700 px-4 py-2 text-sm font-medium text-white hover:bg-violet-600 disabled:opacity-50"
          :disabled="isSaving"
          @click="onValidate"
        >
          {{ t('strategy.validate') }}
        </button>
      </div>
    </template>
  </AppModal>
</template>
