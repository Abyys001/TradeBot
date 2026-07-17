<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Strategy } from '../../api/client'

const props = defineProps<{
  strategy: Strategy
  pnl?: string
  toggling?: boolean
}>()

defineEmits<{ toggle: [] }>()

const { t } = useI18n()

const isActive = computed(() => props.strategy.status === 'active')

const pnlValue = computed(() => parseFloat(props.pnl ?? '0'))
const pnlClass = computed(() =>
  pnlValue.value >= 0 ? 'text-positive' : 'text-negative',
)

const canStart = computed(
  () => props.strategy.validation_status === 'ok' && !!props.strategy.credential,
)

const statusHint = computed(() => {
  if (props.strategy.validation_status !== 'ok') return t('bots.notValidated')
  if (props.strategy.state?.live_error) return props.strategy.state.live_error
  return ''
})
</script>

<template>
  <div class="rounded-xl border border-border bg-surface-muted/60 p-4 flex flex-col gap-3">
    <div class="flex items-start justify-between gap-2">
      <div class="min-w-0">
        <div class="text-sm font-medium text-fg truncate">{{ strategy.name }}</div>
        <div class="text-xs text-fg-muted mt-0.5 font-mono">{{ strategy.symbol }}</div>
      </div>
      <button
        type="button"
        class="shrink-0 rounded-lg px-3 py-1 text-xs font-medium transition-colors disabled:opacity-50"
        :class="isActive ? 'bg-success-bg text-positive' : 'bg-surface-raised text-fg-muted'"
        :disabled="toggling || (!isActive && !canStart)"
        :title="!isActive && !canStart ? statusHint : ''"
        @click="$emit('toggle')"
      >
        {{ isActive ? t('bots.on') : t('bots.off') }}
      </button>
    </div>

    <div>
      <div class="text-xs text-fg-muted mb-1">{{ t('bots.pnl') }}</div>
      <div class="text-lg font-mono font-semibold" :class="pnlClass">
        {{ pnlValue >= 0 ? '+' : '' }}{{ pnlValue.toFixed(2) }}
      </div>
    </div>

    <div v-if="statusHint && strategy.validation_status !== 'ok'" class="text-xs text-warning">
      {{ statusHint }}
    </div>
    <div v-else-if="strategy.state?.live_error" class="text-xs text-negative truncate" :title="strategy.state.live_error">
      {{ strategy.state.live_error }}
    </div>
  </div>
</template>
