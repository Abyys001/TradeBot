<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import SliderInput from '../../../components/SliderInput.vue'
import { TIMEFRAME_OPTIONS, type StrategyForm } from '../../../composables/useStrategyForm'
import type { LiveConfig } from '../../../api/client'

const props = defineProps<{ strategyForm: StrategyForm }>()
const { t } = useI18n()

const sf = props.strategyForm
const risk = sf.form.live_config.risk as Required<NonNullable<LiveConfig['risk']>>
</script>

<template>
  <div class="space-y-5">
    <h3 class="text-sm font-semibold text-zinc-200">{{ t('live.risk.title') }}</h3>

    <!-- pairs -->
    <div class="space-y-2">
      <label class="text-xs text-zinc-500">{{ t('live.risk.pairs') }}</label>
      <div class="flex flex-wrap gap-2">
        <span
          v-for="s in sf.form.live_config.symbols"
          :key="s"
          class="flex items-center gap-1 rounded-lg bg-zinc-800 px-2 py-1 text-xs text-zinc-200"
        >
          {{ s }}
          <button type="button" class="text-zinc-500 hover:text-red-400" @click="sf.removeSymbol(s)">✕</button>
        </span>
      </div>
      <div class="flex gap-2">
        <input
          v-model="sf.newSymbol.value"
          :placeholder="t('live.risk.addPair')"
          class="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm uppercase"
          @keydown.enter.prevent="sf.addSymbol"
        />
        <button
          type="button"
          class="rounded-lg bg-zinc-800 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
          @click="sf.addSymbol"
        >
          +
        </button>
      </div>
    </div>

    <!-- timeframes -->
    <div class="space-y-2">
      <label class="text-xs text-zinc-500">{{ t('live.risk.timeframe') }}</label>
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="tf in TIMEFRAME_OPTIONS"
          :key="tf"
          type="button"
          class="rounded-lg px-2.5 py-1 text-xs transition-colors"
          :class="sf.form.live_config.timeframes?.includes(tf)
            ? 'bg-violet-700 text-white'
            : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'"
          @click="sf.form.live_config.timeframes?.includes(tf) ? sf.removeTf(tf) : sf.addTf(tf)"
        >
          {{ tf }}
        </button>
      </div>
    </div>

    <!-- risk sliders -->
    <div class="space-y-4 rounded-lg border border-zinc-800 p-4">
      <SliderInput
        v-model="risk.leverage"
        :label="t('live.risk.leverage')"
        :min="1"
        :max="50"
        :step="1"
        suffix="×"
      />
      <SliderInput
        v-model="risk.position_size_pct"
        :label="t('live.risk.positionSize')"
        :min="1"
        :max="100"
        :step="1"
        suffix="%"
      />
      <SliderInput
        v-model="risk.global_stop_loss_pct"
        :label="t('live.risk.stopLoss')"
        :min="1"
        :max="100"
        :step="1"
        suffix="%"
      />
    </div>
  </div>
</template>
