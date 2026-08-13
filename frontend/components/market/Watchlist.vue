<script setup lang="ts">
/**
 * The watchlist, in two densities from one implementation.
 *
 *   compact  the rail beside the chart — every row a click away from loading
 *            that pair, priced, in as little vertical space as stays legible
 *   full     the dashboard block — same data, room to edit, reorder and read
 *
 * One component because two would drift: the dashboard's copy would grow a
 * column the chart's never got, and the two would disagree about what the list
 * even is. The list itself lives in `stores/watchlist.ts` (a cookie), so both
 * instances are always looking at the same rows.
 *
 * Clicking a row loads that pair on the chart. From the dashboard that means
 * navigating there — a watchlist you can only look at is a table.
 */
const props = withDefaults(defineProps<{ variant?: 'compact' | 'full' }>(), {
  variant: 'compact',
})

const { t } = useI18n()
const localePath = useLocalePath()
const router = useRouter()
const route = useRoute()
const watchlist = useWatchlistStore()
const market = useMarketStore()
const { money, pct } = useFormat()

const editing = ref(false)
const adding = ref(false)
const draft = ref('')
const addError = ref('')
const addInput = ref<HTMLInputElement | null>(null)

const full = computed(() => props.variant === 'full')
const onChartPage = computed(() => String(route.name ?? '').split('___')[0] === 'chart')

onMounted(() => watchlist.start())
onBeforeUnmount(() => watchlist.stop())

async function open(symbol: string) {
  if (editing.value) return
  if (!onChartPage.value) {
    // The chart page reads the pair from the market store on mount, so setting
    // it before navigating means the right instrument is loading during the
    // transition rather than after it.
    await market.setSymbol(symbol)
    await router.push(localePath('/chart'))
    return
  }
  await market.setSymbol(symbol)
}

async function startAdding() {
  adding.value = true
  addError.value = ''
  await nextTick()
  addInput.value?.focus()
}

function submitAdd() {
  const value = draft.value.trim().toUpperCase()
  if (!value) return
  if (watchlist.has(value)) {
    addError.value = t('watchlist.alreadyThere', { symbol: value })
    return
  }
  if (watchlist.isFull) {
    addError.value = t('watchlist.full', { n: watchlist.max })
    return
  }
  if (!watchlist.add(value)) {
    addError.value = t('watchlist.invalid')
    return
  }
  draft.value = ''
  addError.value = ''
  adding.value = false
}

function cancelAdd() {
  adding.value = false
  draft.value = ''
  addError.value = ''
}

/** Suggestions the backend already curates, minus what is on the list. */
const suggestions = computed(() =>
  market.symbols.filter((s) => !watchlist.has(s.symbol)).slice(0, 6),
)

const changeTone = (value: number | null) =>
  value === null ? 'text-ink-faint' : value >= 0 ? 'text-long' : 'text-short'
</script>

<template>
  <div class="flex flex-col min-h-0">
    <!-- Header -->
    <div
      class="flex items-center gap-2 shrink-0"
      :class="full ? 'px-4 py-3 border-b border-line' : 'px-3 py-2 border-b border-line'"
    >
      <span :class="full ? 'text-sm font-medium' : 'label'">{{ t('watchlist.title') }}</span>
      <span v-if="full" class="num text-xs text-ink-faint">
        {{ watchlist.symbols.length }}/{{ watchlist.max }}
      </span>

      <div class="ms-auto flex items-center gap-1">
        <button
          class="btn-quiet btn-sm"
          :class="editing ? 'text-brand' : ''"
          :title="editing ? t('watchlist.done') : t('watchlist.edit')"
          :aria-label="editing ? t('watchlist.done') : t('watchlist.edit')"
          @click="editing = !editing"
        >
          <UiIcon :name="editing ? 'check' : 'settings'" :size="13" />
          <span v-if="full" class="hidden sm:inline">
            {{ editing ? t('watchlist.done') : t('watchlist.edit') }}
          </span>
        </button>
        <button
          class="btn-quiet btn-sm"
          :disabled="watchlist.isFull"
          :title="t('watchlist.add')"
          :aria-label="t('watchlist.add')"
          @click="startAdding"
        >
          <UiIcon name="plus" :size="13" />
        </button>
      </div>
    </div>

    <!-- Add form -->
    <div v-if="adding" class="px-3 py-2 border-b border-line bg-sunken/60 shrink-0 space-y-2">
      <div class="flex gap-2">
        <input
          ref="addInput"
          v-model="draft"
          class="field uppercase text-xs py-1.5"
          :placeholder="t('watchlist.placeholder')"
          spellcheck="false"
          @keyup.enter="submitAdd"
          @keyup.esc="cancelAdd"
        />
        <button class="btn-brand btn-sm shrink-0" @click="submitAdd">
          {{ t('watchlist.add') }}
        </button>
        <button class="btn-quiet btn-sm shrink-0" :aria-label="t('common.cancel')" @click="cancelAdd">
          <UiIcon name="close" :size="13" />
        </button>
      </div>

      <p v-if="addError" class="text-[0.7rem] text-short">{{ addError }}</p>

      <div v-if="suggestions.length" class="flex flex-wrap gap-1">
        <button
          v-for="option in suggestions"
          :key="option.symbol"
          class="num text-[0.65rem] px-1.5 py-0.5 rounded-md border border-line text-ink-muted
                 hover:text-ink hover:border-line-strong transition-colors"
          @click="watchlist.add(option.symbol)"
        >
          + {{ option.base }}
        </button>
      </div>
    </div>

    <!-- Rows. The dashboard lays them out as tiles across the width it has; the
         rail keeps a single dense column, which is all 22rem can carry. -->
    <ul
      class="overflow-y-auto min-h-0"
      :class="
        full
          ? 'grid gap-2 p-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4'
          : 'divide-y divide-line/60'
      "
    >
      <li
        v-for="(row, index) in watchlist.rows"
        :key="row.symbol"
        class="group flex items-center gap-2 transition-colors"
        :class="[
          full
            ? 'rounded-lg border border-line bg-sunken/50 px-3 py-2.5 hover:border-line-strong'
            : 'px-3 py-1.5',
          row.symbol === market.symbol && onChartPage
            ? full
              ? 'border-brand/50 bg-brand-dim'
              : 'bg-brand-dim'
            : full
              ? ''
              : 'hover:bg-raised/60',
        ]"
      >
        <!-- The row itself is the button: the whole line is the target, which
             is what makes this usable with a thumb. -->
        <button
          class="flex items-center gap-2 min-w-0 flex-1 text-start"
          :disabled="editing"
          :title="t('watchlist.openHint', { symbol: row.symbol })"
          @click="open(row.symbol)"
        >
          <span
            v-if="row.symbol === market.symbol && onChartPage"
            class="w-0.5 h-4 rounded-full bg-brand shrink-0 -ms-1"
          />
          <span class="min-w-0">
            <span class="num block truncate" :class="full ? 'text-sm' : 'text-xs'">
              {{ row.symbol.replace(/USDT$/, '') }}<span class="text-ink-faint">/USDT</span>
            </span>
            <!-- A row nobody could quote stays on the list and says so. It is
                 never filled in with a price from anywhere but an exchange. -->
            <span v-if="full && !row.live" class="label text-signal">
              {{ t('terminal.noQuote') }}
            </span>
          </span>

          <span class="ms-auto text-end shrink-0">
            <span
              class="num block"
              :class="[
                full ? 'text-sm' : 'text-xs',
                row.direction === 'up'
                  ? 'text-long'
                  : row.direction === 'down'
                    ? 'text-short'
                    : '',
              ]"
            >
              {{ row.price === null ? '—' : money(row.price, row.price < 10 ? 4 : 2) }}
            </span>
            <span
              v-if="row.changePct !== null"
              class="num block text-[0.65rem]"
              :class="changeTone(row.changePct)"
            >
              {{ row.changePct >= 0 ? '+' : '' }}{{ pct(row.changePct) }}
            </span>
          </span>
        </button>

        <!-- Edit controls. Hidden until edit mode so the resting state stays a
             price list rather than a row of buttons. -->
        <div v-if="editing" class="flex items-center gap-0.5 shrink-0">
          <button
            class="btn-quiet btn-sm px-1.5"
            :disabled="index === 0"
            :aria-label="t('watchlist.moveUp')"
            @click="watchlist.move(row.symbol, -1)"
          >
            <UiIcon name="arrowUp" :size="12" />
          </button>
          <button
            class="btn-quiet btn-sm px-1.5"
            :disabled="index === watchlist.rows.length - 1"
            :aria-label="t('watchlist.moveDown')"
            @click="watchlist.move(row.symbol, 1)"
          >
            <UiIcon name="arrowDown" :size="12" />
          </button>
          <button
            class="btn-quiet btn-sm px-1.5 text-ink-faint hover:text-short"
            :aria-label="t('watchlist.remove', { symbol: row.symbol })"
            @click="watchlist.remove(row.symbol)"
          >
            <UiIcon name="trash" :size="12" />
          </button>
        </div>
      </li>

      <li
        v-if="!watchlist.rows.length"
        class="px-4 py-6 text-center"
        :class="full ? 'sm:col-span-2 xl:col-span-3 2xl:col-span-4' : ''"
      >
        <p class="text-xs text-ink-muted">{{ t('watchlist.empty') }}</p>
        <button class="btn-ghost btn-sm mt-2" @click="watchlist.reset()">
          {{ t('watchlist.restore') }}
        </button>
      </li>
    </ul>

    <p v-if="watchlist.error" class="px-3 py-2 text-[0.7rem] text-signal shrink-0">
      {{ watchlist.error }}
    </p>
  </div>
</template>
