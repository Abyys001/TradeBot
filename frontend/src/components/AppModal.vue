<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'

const props = withDefaults(
  defineProps<{
    title: string
    size?: 'md' | 'lg' | 'full'
  }>(),
  { size: 'md' },
)

const emit = defineEmits<{ close: [] }>()

const panelClass = {
  md: 'w-full max-w-lg max-h-[85vh]',
  lg: 'w-full max-w-[80vw] max-h-[80vh]',
  full: 'w-[calc(100vw-2rem)] h-[calc(100vh-2rem)] max-w-none max-h-none',
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      @click.self="emit('close')"
    >
      <div
        class="flex flex-col rounded-xl border border-zinc-700 bg-zinc-900 shadow-2xl overflow-hidden"
        :class="panelClass[props.size]"
        role="dialog"
        aria-modal="true"
      >
        <div class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-4 py-3">
          <h2 class="text-sm font-semibold text-zinc-200">{{ title }}</h2>
          <button
            type="button"
            class="rounded px-2 py-0.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
            aria-label="Close"
            @click="emit('close')"
          >
            ✕
          </button>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto">
          <slot />
        </div>
        <div v-if="$slots.footer" class="shrink-0 border-t border-zinc-800 px-4 py-3">
          <slot name="footer" />
        </div>
      </div>
    </div>
  </Teleport>
</template>
