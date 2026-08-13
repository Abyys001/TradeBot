<script setup lang="ts">
/**
 * A dialog that behaves like one: Escape closes it, focus moves into it and is
 * trapped, background scroll is locked, and on a phone it docks to the bottom
 * as a sheet rather than floating in the middle where the keyboard covers it.
 */
const open = defineModel<boolean>({ required: true })
const props = withDefaults(defineProps<{ title: string; size?: 'sm' | 'md' | 'lg' }>(), {
  size: 'md',
})

const panel = ref<HTMLElement | null>(null)
const titleId = useId()

const WIDTH = { sm: 'sm:max-w-sm', md: 'sm:max-w-lg', lg: 'sm:max-w-3xl' }

function close() {
  open.value = false
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    close()
    return
  }
  if (event.key !== 'Tab' || !panel.value) return

  // Focus trap. Without it, tabbing walks out of the dialog and into the page
  // behind it — which here means the order ticket, mid-trade.
  const focusable = panel.value.querySelectorAll<HTMLElement>(
    'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])',
  )
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(
  open,
  async (isOpen) => {
    if (import.meta.server) return
    document.body.style.overflow = isOpen ? 'hidden' : ''
    if (!isOpen) return
    await nextTick()
    panel.value?.querySelector<HTMLElement>('input, select, textarea, button')?.focus()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (import.meta.client) document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0"
      leave-active-class="transition duration-150 ease-in"
      leave-to-class="opacity-0"
    >
      <div
        v-if="open"
        class="fixed inset-0 z-[100] scrim backdrop-blur-sm flex items-end sm:items-center justify-center sm:p-4"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        @keydown="onKeydown"
        @click.self="close"
      >
        <div
          ref="panel"
          class="w-full bg-panel border border-line shadow-pop flex flex-col
                 max-h-[92vh] rounded-t-2xl sm:rounded-panel animate-fade-up"
          :class="WIDTH[props.size]"
        >
          <header class="flex items-center gap-3 px-4 sm:px-5 py-3.5 border-b border-line">
            <h2 :id="titleId" class="text-sm font-medium">{{ title }}</h2>
            <button class="btn-quiet btn-sm ms-auto -me-1.5" :aria-label="$t('common.close')" @click="close">
              <UiIcon name="close" :size="16" />
            </button>
          </header>

          <div class="p-4 sm:p-5 overflow-y-auto">
            <slot />
          </div>

          <footer v-if="$slots.footer" class="px-4 sm:px-5 py-3.5 border-t border-line">
            <slot name="footer" />
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
