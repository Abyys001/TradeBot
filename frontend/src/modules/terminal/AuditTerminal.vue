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
  if (level === 'error') return 'text-red-400'
  if (level === 'warning') return 'text-amber-400'
  if (level === 'debug') return 'text-zinc-600'
  return 'text-zinc-300'
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
  <div class="h-48 shrink-0 border-t border-zinc-800 flex flex-col bg-[#0a0a0a]">
    <div class="flex items-center gap-2 border-b border-zinc-800 px-3 py-1.5">
      <span class="text-xs font-medium text-zinc-400">{{ t('terminal.title') }}</span>
      <div class="flex gap-1 ms-auto">
        <button
          v-for="lv in levels"
          :key="lv"
          type="button"
          class="rounded px-2 py-0.5 text-[10px] uppercase"
          :class="
            terminal.levelFilter === lv
              ? 'bg-zinc-700 text-zinc-200'
              : 'text-zinc-600 hover:text-zinc-400'
          "
          @click="terminal.levelFilter = lv"
        >
          {{ lv === 'all' ? t('terminal.all') : lv }}
        </button>
        <button
          type="button"
          class="rounded px-2 py-0.5 text-[10px] text-zinc-500"
          @click="terminal.paused = !terminal.paused"
        >
          {{ terminal.paused ? '▶' : t('terminal.paused') }}
        </button>
      </div>
    </div>
    <div
      ref="box"
      class="flex-1 overflow-y-auto p-2 font-mono text-[11px] leading-relaxed"
      @mouseenter="terminal.paused = true"
      @mouseleave="terminal.paused = false"
    >
      <div v-for="line in lines" :key="line.id" :class="levelClass(line.level)">
        <span class="text-zinc-600">[{{ formatTime(line.created_at) }}]</span>
        {{ line.message }}
      </div>
    </div>
  </div>
</template>
