import { onMounted, onUnmounted, type Ref } from 'vue'
import { onKeyStroke } from '@vueuse/core'

interface BacktestHotkeysOptions {
  run: () => void | Promise<void>
  canRun: Ref<boolean> | (() => boolean)
  blocked: Ref<boolean> | (() => boolean)
}

function resolveRefOrFn(value: Ref<boolean> | (() => boolean)): boolean {
  return typeof value === 'function' ? value() : value.value
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (target.isContentEditable) return true
  if (target.closest('.monaco-editor')) return true
  return false
}

export function useBacktestHotkeys(options: BacktestHotkeysOptions) {
  let stop: (() => void) | undefined

  onMounted(() => {
    stop = onKeyStroke(
      'Enter',
      (e) => {
        if (!(e.metaKey || e.ctrlKey)) return
        if (resolveRefOrFn(options.blocked)) return
        if (!resolveRefOrFn(options.canRun)) return
        if (isEditableTarget(e.target)) return
        e.preventDefault()
        void options.run()
      },
      { dedupe: true },
    )
  })

  onUnmounted(() => {
    stop?.()
  })
}
