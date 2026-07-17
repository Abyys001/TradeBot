<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTerminalStore } from '../../stores/terminal'

const props = defineProps<{ strategyId?: number }>()

const { t } = useI18n()
const terminal = useTerminalStore()
const box = ref<HTMLElement | null>(null)

const levels = ['all', 'debug', 'info', 'warning', 'error']

const lines = computed(() => terminal.filteredLines)

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString('en-GB', { hour12: false })
  } catch {
    return '--:--:--'
  }
}

function levelClass(level: string) {
  if (level === 'error') return 'text-negative'
  if (level === 'warning') return 'text-warning'
  if (level === 'debug') return 'text-fg-muted'
  return 'text-fg'
}

onMounted(() => {
  terminal.setStrategyFilter(props.strategyId ?? null)
  void terminal.fetchLogs({ strategy: props.strategyId ?? null })
})

watch(
  () => props.strategyId,
  (id) => {
    terminal.setStrategyFilter(id ?? null)
    void terminal.fetchLogs({ strategy: id ?? null })
  },
)

watch(
  () => lines.value.length,
  async () => {
    if (terminal.paused) return
    await nextTick()
    if (box.value) box.value.scrollTop = box.value.scrollHeight
  },
)
</script>

<template>
  <div class="h-48 shrink-0 border-t border-border flex flex-col bg-[#0a0a0a]">
    <div class="flex items-center gap-2 border-b border-border px-3 py-1.5">
      <span class="text-xs font-medium text-fg-muted">{{ t('terminal.title') }}</span>
      <div class="flex gap-1 ms-auto">
        <button
          v-for="lv in levels"
          :key="lv"
          type="button"
          class="rounded px-2 py-0.5 text-[10px] uppercase"
          :class="
            terminal.levelFilter === lv
              ? 'bg-border text-fg'
              : 'text-fg-muted hover:text-fg-muted'
          "
          @click="terminal.levelFilter = lv"
        >
          {{ lv === 'all' ? t('terminal.all') : lv }}
        </button>
        <button
          type="button"
          class="rounded px-2 py-0.5 text-[10px] text-fg-muted"
          @click="terminal.paused = !terminal.paused"
        >
          {{ terminal.paused ? '▶' : t('terminal.paused') }}
        </button>
      </div>
    </div>
    <div
      ref="box"
      class="scrollbar-styled scrollbar-thin scrollbar-idle-fade flex-1 overflow-y-auto p-2 font-mono text-[11px] leading-relaxed"
      @mouseenter="terminal.paused = true"
      @mouseleave="terminal.paused = false"
    >
      <div v-for="line in lines" :key="line.id" :class="levelClass(line.level)">
        <span class="text-fg-muted">[{{ formatTime(line.created_at) }}]</span>
        {{ line.message }}
      </div>
    </div>
  </div>
</template>
