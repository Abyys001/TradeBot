<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import loader from '@monaco-editor/loader'
import type { editor } from 'monaco-editor'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const container = ref<HTMLElement | null>(null)
let monacoEditor: editor.IStandaloneCodeEditor | null = null

onMounted(async () => {
  const monaco = await loader.init()
  if (!container.value) return
  const editor = monaco.editor.create(container.value, {
    value: props.modelValue,
    language: 'javascript',
    theme: 'vs-dark',
    automaticLayout: true,
    minimap: { enabled: true },
    fontSize: 13,
    lineNumbers: 'on',
    scrollBeyondLastLine: false,
    padding: { top: 12 },
  })
  monacoEditor = editor
  editor.onDidChangeModelContent(() => {
    emit('update:modelValue', editor.getValue())
  })
})

watch(
  () => props.modelValue,
  (v) => {
    if (monacoEditor && v !== monacoEditor.getValue()) {
      monacoEditor.setValue(v)
    }
  },
)

onUnmounted(() => {
  monacoEditor?.dispose()
  monacoEditor = null
})
</script>

<template>
  <div ref="container" class="h-full min-h-[320px] w-full rounded-lg border border-zinc-800 overflow-hidden" />
</template>
