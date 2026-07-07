<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'

const props = withDefaults(
  defineProps<{
    title?: string
    size?: 'md' | 'lg' | 'fullscreen'
  }>(),
  { size: 'md' },
)

const emit = defineEmits<{ close: [] }>()

const sizeClass = {
  md: 'max-w-lg',
  lg: 'max-w-3xl',
  fullscreen: 'max-w-[92vw] w-[92vw] h-[88vh]',
}[props.size]

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @click.self="emit('close')">
    <div
      class="flex w-full flex-col rounded-xl border border-zinc-700 bg-zinc-900 shadow-2xl"
      :class="sizeClass"
      role="dialog"
      aria-modal="true"
    >
      <div v-if="title || $slots.header" class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-5 py-4">
        <slot name="header">
          <h2 class="text-base font-semibold text-zinc-100">{{ title }}</h2>
        </slot>
        <button
          type="button"
          class="rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
          @click="emit('close')"
        >
          <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div class="scrollbar-styled scrollbar-thin min-h-0 flex-1 overflow-y-auto p-5">
        <slot />
      </div>
      <div v-if="$slots.footer" class="shrink-0 border-t border-zinc-800 px-5 py-4">
        <slot name="footer" />
      </div>
    </div>
  </div>
</template>
