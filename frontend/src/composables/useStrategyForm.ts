import { computed, onMounted, reactive, ref, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../stores/strategy'
import { useToast } from './useToast'
import type { LiveConfig } from '../api/client'

export const TIMEFRAME_OPTIONS = ['1m', '3m', '5m', '15m', '30m', '1H', '4H', '1D']

export const ADVANCED_RISK_FIELDS = [
  'risk_per_trade_pct',
  'max_daily_loss_pct',
  'max_drawdown_pct',
  'max_open_trades',
  'max_exposure_pct',
  'max_leverage',
] as const

export function useStrategyForm(strategyId: Ref<number> | number) {
  const { t } = useI18n()
  const store = useStrategyStore()
  const toast = useToast()

  const idRef = computed(() => (typeof strategyId === 'number' ? strategyId : strategyId.value))

  const form = reactive({
    name: '',
    source: '',
    live_config: {
      symbols: [] as string[],
      timeframes: [] as string[],
      risk: { leverage: 1, position_size_pct: 5, global_stop_loss_pct: 10 },
    } as LiveConfig,
  })

  const newSymbol = ref('')
  const saving = ref(false)
  const dragOver = ref(false)
  const validationMsg = ref('')
  const engineType = ref('pine')

  const selected = computed(() => store.strategies.find((s) => s.id === idRef.value) ?? null)

  function syncFromStrategy(s: NonNullable<typeof selected.value>) {
    engineType.value = s.type || 'pine'
    form.name = s.name
    form.source = s.source
    form.live_config = {
      symbols: s.live_config?.symbols?.length ? [...s.live_config.symbols] : [s.symbol],
      timeframes: s.live_config?.timeframes?.length ? [...s.live_config.timeframes] : [s.timeframe],
      risk: {
        leverage: s.live_config?.risk?.leverage ?? 1,
        position_size_pct: s.live_config?.risk?.position_size_pct ?? 5,
        global_stop_loss_pct: s.live_config?.risk?.global_stop_loss_pct ?? 10,
        risk_per_trade_pct: s.live_config?.risk?.risk_per_trade_pct ?? 1,
        max_daily_loss_pct: s.live_config?.risk?.max_daily_loss_pct ?? 5,
        max_drawdown_pct: s.live_config?.risk?.max_drawdown_pct ?? 15,
        max_open_trades: s.live_config?.risk?.max_open_trades ?? 3,
        max_exposure_pct: s.live_config?.risk?.max_exposure_pct ?? 50,
        max_leverage: s.live_config?.risk?.max_leverage ?? 10,
      },
    }
    validationMsg.value = ''
  }

  watch(
    [selected, idRef],
    ([s]) => {
      if (s) syncFromStrategy(s)
    },
    { immediate: true },
  )

  onMounted(async () => {
    if (!store.engines.length) await store.fetchEngines()
  })

  function addSymbol() {
    const v = newSymbol.value.trim().toUpperCase()
    if (v && !form.live_config.symbols?.includes(v)) {
      form.live_config.symbols = [...(form.live_config.symbols || []), v]
    }
    newSymbol.value = ''
  }

  function removeSymbol(s: string) {
    form.live_config.symbols = form.live_config.symbols?.filter((x) => x !== s)
  }

  function addTf(tf: string) {
    if (!tf) return
    if (!form.live_config.timeframes?.includes(tf)) {
      form.live_config.timeframes = [...(form.live_config.timeframes || []), tf]
    }
  }

  function removeTf(tf: string) {
    form.live_config.timeframes = form.live_config.timeframes?.filter((x) => x !== tf)
  }

  function onFile(file: File) {
    const reader = new FileReader()
    reader.onload = () => {
      form.source = String(reader.result || '')
    }
    reader.readAsText(file)
  }

  function onDrop(e: DragEvent) {
    dragOver.value = false
    const file = e.dataTransfer?.files?.[0]
    if (file) onFile(file)
  }

  function onFileInput(e: Event) {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (file) onFile(file)
  }

  async function save() {
    const s = selected.value
    if (!s) return false
    saving.value = true
    try {
      await store.updateStrategy(s.id, {
        name: form.name,
        credential: s.credential,
        source: form.source,
        type: engineType.value,
        live_config: form.live_config,
      })
      toast.show(t('strategy.saved'), 'success')
      return true
    } catch {
      toast.show(t('strategy.saveFailed'), 'error')
      return false
    } finally {
      saving.value = false
    }
  }

  async function validate() {
    const s = selected.value
    if (!s) return false
    await save()
    const result = await store.validate(s.id)
    if (result.ok) {
      validationMsg.value = ''
      toast.show(t('strategy.validatedOk'), 'success')
      return true
    }
    const loc = result.line != null ? ` (line ${result.line}, col ${result.column ?? '?'})` : ''
    validationMsg.value = `${result.error || t('strategy.validatedFail')}${loc}`
    toast.show(validationMsg.value, 'error')
    return false
  }

  function loadSourceFrom(id: number) {
    const s = store.strategies.find((x) => x.id === id)
    if (s?.source) form.source = s.source
  }

  function setSource(value: string) {
    form.source = value
  }

  return {
    store,
    form,
    newSymbol,
    saving,
    dragOver,
    validationMsg,
    engineType,
    selected,
    addSymbol,
    removeSymbol,
    addTf,
    removeTf,
    onDrop,
    onFileInput,
    save,
    validate,
    loadSourceFrom,
    setSource,
    syncFromStrategy,
  }
}

export type StrategyForm = ReturnType<typeof useStrategyForm>
