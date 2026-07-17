<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: number
    min?: number
    max?: number
    step?: number
    label?: string
    suffix?: string
  }>(),
  {
    min: 0,
    max: 100,
    step: 1,
    label: '',
    suffix: '',
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: number] }>()

const textInput = ref(String(props.modelValue))

const fillPct = computed(() => {
  const span = props.max - props.min
  if (span <= 0) return '0%'
  const pct = ((clamp(props.modelValue) - props.min) / span) * 100
  return `${Math.min(100, Math.max(0, pct))}%`
})

function clamp(v: number) {
  if (Number.isNaN(v)) return props.min
  return Math.min(props.max, Math.max(props.min, v))
}

function emitValue(v: number) {
  const next = clamp(v)
  emit('update:modelValue', next)
  textInput.value = formatDisplay(next)
}

function formatDisplay(v: number) {
  return Number.isInteger(props.step) || props.step >= 1
    ? String(Math.round(v))
    : String(Number(v.toFixed(1)))
}

function onSliderInput(e: Event) {
  emitValue(Number((e.target as HTMLInputElement).value))
}

function onTextInput(e: Event) {
  const raw = (e.target as HTMLInputElement).value
  textInput.value = raw
  const parsed = parseFloat(raw)
  if (!Number.isNaN(parsed)) {
    emit('update:modelValue', clamp(parsed))
  }
}

function onTextBlur() {
  const parsed = parseFloat(textInput.value)
  emitValue(Number.isNaN(parsed) ? props.min : parsed)
}

watch(
  () => props.modelValue,
  (v) => {
    textInput.value = formatDisplay(clamp(v))
  },
  { immediate: true },
)

watch(
  () => [props.min, props.max],
  () => {
    if (props.modelValue < props.min || props.modelValue > props.max) {
      emitValue(props.modelValue)
    }
  },
)
</script>

<template>
  <div class="space-y-1.5">
    <div v-if="label" class="flex items-center justify-between">
      <label class="text-xs text-fg-muted">{{ label }}</label>
      <span v-if="suffix" class="text-[10px] text-fg-muted">{{ suffix }}</span>
    </div>
    <div class="flex items-center gap-3">
      <input
        type="range"
        class="risk-slider min-w-0 flex-1"
        :style="{ '--slider-pct': fillPct }"
        :min="min"
        :max="max"
        :step="step"
        :value="clamp(modelValue)"
        @input="onSliderInput"
      />
      <input
        type="number"
        class="w-20 shrink-0 rounded-lg border border-border bg-surface px-2 py-1.5 text-end text-sm text-fg focus:border-violet-600 focus:outline-none focus:ring-1 focus:ring-violet-600/40"
        :min="min"
        :max="max"
        :step="step"
        :value="textInput"
        @input="onTextInput"
        @blur="onTextBlur"
      />
    </div>
  </div>
</template>

<style scoped>
.risk-slider {
  -webkit-appearance: none;
  appearance: none;
  height: 6px;
  border-radius: 9999px;
  background: linear-gradient(to right, #7c3aed var(--slider-pct), #3f3f46 var(--slider-pct));
  outline: none;
  accent-color: #7c3aed;
}

.risk-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #8b5cf6;
  border: 2px solid #1e1b4b;
  cursor: pointer;
  transition: background 0.15s;
}

.risk-slider::-webkit-slider-thumb:hover {
  background: #a78bfa;
}

.risk-slider::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #8b5cf6;
  border: 2px solid #1e1b4b;
  cursor: pointer;
  transition: background 0.15s;
}

.risk-slider::-moz-range-thumb:hover {
  background: #a78bfa;
}

.risk-slider::-moz-range-track {
  height: 6px;
  border-radius: 9999px;
  background: transparent;
}
</style>
