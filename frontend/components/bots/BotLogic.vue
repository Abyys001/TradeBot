<script setup lang="ts">
/**
 * What makes this strategy trade, read back out of its own source.
 *
 * Deliberately not a plain-English summary. "If RSI goes above 50 we take a
 * long" is the most convincing thing on the page to be wrong, because nobody
 * can check it — so what is shown is the condition **as written**,
 * `ta.crossover(fast, slow) and rsi > 50`, with the line number beside it. The
 * one liberty taken is expanding a single-assignment alias (`longCond`) into
 * what it was assigned, since a name is not a condition.
 *
 * The indicator list doubles as the chart's key: the names here are the keys
 * the runtime emits its plot values under, which is what joins this tab to the
 * lines drawn on the chart tab.
 */
const props = defineProps<{ botId: number }>()

const { t } = useI18n()
const api = useApi()

const data = ref<BotLogic | null>(null)
const loading = ref(true)
const error = ref('')

const KIND_TONE: Record<string, 'ok' | 'signal' | 'brand' | 'neutral'> = {
  entry: 'ok',
  order: 'brand',
  close: 'signal',
  exit: 'signal',
}

/** Entries first: they are what a reader opens this tab to find. */
const triggers = computed(() => {
  const order = ['entry', 'order', 'exit', 'close']
  return [...(data.value?.triggers ?? [])].sort(
    (a, b) => order.indexOf(a.kind) - order.indexOf(b.kind) || a.line - b.line,
  )
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await api.botLogic(props.botId)
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.botId, load)
</script>

<template>
  <div class="space-y-4">
    <p v-if="error" class="alert px-3 py-2 text-xs leading-relaxed">{{ error }}</p>
    <div v-if="loading" class="skeleton h-48" />

    <template v-else-if="data">
      <p v-if="data.error" class="alert px-3 py-2 text-xs leading-relaxed">{{ data.error }}</p>

      <UiCard :title="t('bots.triggers')" :hint="t('bots.triggersHint')" flush>
        <UiEmpty v-if="!triggers.length" icon="logs" :title="t('bots.noTriggers')" />
        <ul v-else class="divide-y divide-line">
          <li v-for="(row, index) in triggers" :key="index" class="px-4 py-3 space-y-2">
            <div class="flex items-center gap-2 flex-wrap">
              <UiBadge :tone="KIND_TONE[row.kind] ?? 'neutral'">
                {{ t(`bots.trigger.${row.kind}`) }}
              </UiBadge>
              <UiBadge v-if="row.side" :tone="row.side === 'long' ? 'long' : 'short'">
                {{ t(`side.${row.side}`) }}
              </UiBadge>
              <span v-if="row.order_id" class="num text-xs text-ink-muted">{{ row.order_id }}</span>
              <span class="num text-tick text-ink-faint ms-auto">
                {{ t('bots.line') }} {{ row.line }}
              </span>
            </div>

            <!-- The conditions, outermost first. "when … and …" is the reading
                 order; nesting them visually would imply a precedence the
                 source does not have. -->
            <div v-if="row.expanded.length" class="space-y-1">
              <p class="text-tick text-ink-faint">{{ t('bots.firesWhen') }}</p>
              <p
                v-for="(condition, ci) in row.expanded"
                :key="ci"
                class="num text-xs bg-sunken border border-line rounded-md px-2.5 py-1.5
                       overflow-x-auto whitespace-pre"
              >{{ condition }}</p>
            </div>
            <p v-else-if="row.inside_function" class="text-xs text-ink-faint leading-relaxed">
              {{ t('bots.triggerInFunction') }}
            </p>
            <p v-else class="text-xs text-signal leading-relaxed">
              {{ t('bots.triggerUnconditional') }}
            </p>

            <p class="num text-tick text-ink-faint overflow-x-auto whitespace-pre">
              {{ row.call_text }}
            </p>
          </li>
        </ul>
      </UiCard>

      <UiCard :title="t('bots.indicators')" :hint="t('bots.indicatorsHint')" flush>
        <UiEmpty v-if="!data.indicators.length" icon="chart" :title="t('bots.noIndicators')" />
        <div v-else class="overflow-x-auto">
          <table class="w-full text-xs">
            <thead>
              <tr class="label">
                <th class="text-start px-4 py-2 font-normal">{{ t('bots.series') }}</th>
                <th class="text-start px-4 py-2 font-normal">{{ t('bots.formula') }}</th>
                <th class="text-start px-4 py-2 font-normal">{{ t('bots.onChart') }}</th>
                <th class="text-end px-4 py-2 font-normal">{{ t('bots.line') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-line">
              <tr v-for="row in data.indicators" :key="`${row.name}-${row.line}`">
                <td class="px-4 py-2 num">
                  {{ row.label }}
                  <span v-if="row.label !== row.name" class="text-ink-faint">({{ row.name }})</span>
                </td>
                <td class="px-4 py-2 num text-ink-muted">
                  <template v-if="row.func">{{ row.func }}({{ row.args }})</template>
                  <span v-else class="text-ink-faint">—</span>
                </td>
                <td class="px-4 py-2">
                  <UiBadge v-if="row.plotted" tone="ok">{{ t('bots.plotted') }}</UiBadge>
                  <span v-else class="text-ink-faint">—</span>
                </td>
                <td class="px-4 py-2 num text-end text-ink-faint">{{ row.line }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </UiCard>

      <UiCard v-if="data.inputs.length" :title="t('bots.scriptInputs')" flush>
        <ul class="divide-y divide-line">
          <li v-for="name in data.inputs" :key="name" class="px-4 py-2 text-xs">{{ name }}</li>
        </ul>
      </UiCard>
    </template>
  </div>
</template>
