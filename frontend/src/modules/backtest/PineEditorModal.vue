<script setup lang="ts">
import { onMounted, onUnmounted, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import loader from '@monaco-editor/loader'
import BaseModal from '../../components/BaseModal.vue'

const props = defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  close: []
  save: []
}>()

const { t } = useI18n()
const editorEl = ref<HTMLElement | null>(null)
const editor = shallowRef<import('monaco-editor').editor.IStandaloneCodeEditor | null>(null)
const dragOver = ref(false)

onMounted(async () => {
  const monaco = await loader.init()
  if (!editorEl.value) return
  const ed = monaco.editor.create(editorEl.value, {
    value: props.modelValue,
    language: 'javascript',
    theme: 'vs-dark',
    minimap: { enabled: false },
    fontSize: 13,
    lineNumbers: 'on',
    scrollBeyondLastLine: false,
    automaticLayout: true,
  })
  editor.value = ed
  ed.onDidChangeModelContent(() => {
    emit('update:modelValue', ed.getValue())
  })
})

onUnmounted(() => {
  editor.value?.dispose()
})

function onFile(file: File) {
  const reader = new FileReader()
  reader.onload = () => {
    const text = String(reader.result || '')
    editor.value?.setValue(text)
    emit('update:modelValue', text)
  }
  reader.readAsText(file)
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) onFile(file)
}

function saveAndClose() {
  emit('save')
  emit('close')
}
</script>

<template>
  <BaseModal size="fullscreen" :title="t('backtest.editPine')" @close="emit('close')">
    <div
      class="mb-3 rounded-lg border border-dashed px-3 py-2 text-center text-xs text-zinc-500"
      :class="dragOver ? 'border-violet-500 bg-violet-950/20' : 'border-zinc-700'"
      @dragover.prevent="dragOver = true"
      @dragleave="dragOver = false"
      @drop.prevent="onDrop"
    >
      {{ t('strategies.dropPine') }}
    </div>
    <div ref="editorEl" class="h-[calc(88vh-12rem)] min-h-[320px] rounded-lg border border-zinc-800 overflow-hidden" />
    <template #footer>
      <div class="flex justify-end gap-2">
        <button
          type="button"
          class="rounded-lg px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200"
          @click="emit('close')"
        >
          {{ t('health.cancel') }}
        </button>
        <button
          type="button"
          class="rounded-lg bg-violet-700 px-4 py-2 text-sm text-white hover:bg-violet-600"
          @click="saveAndClose"
        >
          {{ t('backtest.savePine') }}
        </button>
      </div>
    </template>
  </BaseModal>
</template>
