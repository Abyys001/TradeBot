<script setup lang="ts">
/**
 * The product's promise, drawn.
 *
 * One origin (the admin's action) fans out to N accounts. Each line animates
 * for that leg's real dispatch time, so a slow exchange visibly lags and a
 * failed leg stops short and turns amber — the same colour the persistent
 * failure notification uses, because it means the same thing.
 *
 * With no trades yet it runs a demo cycle, since an empty hero would teach the
 * viewer nothing about what the platform does. The demo is labelled as a demo
 * by the caption, never dressed up as real activity.
 *
 * Two renderings: the fan on `sm` and up, a stacked list below it. Scaling a
 * 560-wide viewBox down to a phone puts the account labels at about seven
 * pixels, which is a decoration rather than a diagram.
 */
type Leg = { label: string; ms: number; ok: boolean }

const props = withDefaults(defineProps<{ legs?: Leg[]; budgetMs?: number }>(), {
  budgetMs: 1000,
})

const DEMO: Leg[] = [
  { label: 'Hyperliquid', ms: 180, ok: true },
  { label: 'Bybit', ms: 240, ok: true },
  { label: 'Binance', ms: 310, ok: true },
  { label: 'OKX', ms: 420, ok: true },
  { label: 'Gate.io', ms: 260, ok: true },
  { label: 'KuCoin', ms: 900, ok: false },
  { label: 'Toobit', ms: 380, ok: true },
]

const legs = computed(() => (props.legs?.length ? props.legs : DEMO))
const isDemo = computed(() => !props.legs?.length)

const W = 560
const H = 340
const ORIGIN = { x: 74, y: H / 2 }
const running = ref(false)

// Vertical fan on the right; the origin sits left of centre so the lines have
// room to read as a spread rather than a starburst.
const nodes = computed(() =>
  legs.value.map((leg, i) => {
    const count = legs.value.length
    const spread = H - 72
    const y = count === 1 ? H / 2 : 36 + (spread / (count - 1)) * i
    return { ...leg, x: W - 150, y }
  }),
)

const slowest = computed(() => Math.max(...legs.value.map((l) => l.ms), 1))

function pathFor(node: { x: number; y: number }) {
  const midX = (ORIGIN.x + node.x) / 2
  return `M ${ORIGIN.x} ${ORIGIN.y} C ${midX} ${ORIGIN.y}, ${midX} ${node.y}, ${node.x} ${node.y}`
}

/** Slow the real millisecond figures to something the eye can follow. */
function durationFor(ms: number) {
  return `${Math.max(0.35, (ms / slowest.value) * 1.6)}s`
}

let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  running.value = true
  if (reduced || !isDemo.value) return
  timer = setInterval(() => {
    running.value = false
    setTimeout(() => (running.value = true), 80)
  }, 4200)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <figure class="relative min-w-0">
    <!-- Fan, sm and up -->
    <svg
      :viewBox="`0 0 ${W} ${H}`"
      class="hidden sm:block w-full h-auto overflow-visible"
      role="img"
      :aria-label="`One order fanning out to ${legs.length} accounts`"
    >
      <g v-if="running" fill="none" stroke-linecap="round">
        <path
          v-for="(node, i) in nodes"
          :key="`p-${i}`"
          :d="pathFor(node)"
          class="stroke-line-strong"
          stroke-width="1"
        />
        <path
          v-for="(node, i) in nodes"
          :key="`a-${i}`"
          :d="pathFor(node)"
          :class="node.ok ? 'stroke-long' : 'stroke-signal'"
          stroke-width="1.5"
          pathLength="100"
          stroke-dasharray="100"
          style="--dash: 100"
          :style="{
            animation: `travel ${durationFor(node.ms)} cubic-bezier(0.2, 0.7, 0.3, 1) forwards`,
          }"
        />
      </g>

      <!-- origin -->
      <g>
        <circle
          :cx="ORIGIN.x"
          :cy="ORIGIN.y"
          r="26"
          class="fill-panel stroke-line"
        />
        <circle :cx="ORIGIN.x" :cy="ORIGIN.y" r="5" class="fill-ink" />
        <text
          :x="ORIGIN.x"
          :y="ORIGIN.y + 46"
          text-anchor="middle"
          class="fill-ink-faint text-[10px] uppercase tracking-[0.16em]"
        >
          {{ $t('landing.diagram.origin') }}
        </text>
      </g>

      <!-- accounts -->
      <g v-if="running">
        <g
          v-for="(node, i) in nodes"
          :key="`n-${i}`"
          :style="{ animation: `arrive 0.28s ease-out ${durationFor(node.ms)} backwards` }"
        >
          <circle :cx="node.x" :cy="node.y" r="4" :class="node.ok ? 'fill-long' : 'fill-signal'" />
          <text
            :x="node.x + 14"
            :y="node.y + 3"
            class="text-[11px]"
            :class="node.ok ? 'fill-ink-muted' : 'fill-signal'"
          >
            {{ node.label }}
          </text>
          <text
            :x="node.x + 14"
            :y="node.y + 16"
            class="text-[10px] tabular-nums"
            :class="node.ok ? 'fill-ink-faint' : 'fill-signal'"
          >
            {{ node.ok ? `${node.ms} ms` : $t('landing.diagram.failed') }}
          </text>
        </g>
      </g>
    </svg>

    <!-- Stacked, below sm. Same data, bar length is the same dispatch time. -->
    <ul v-if="running" class="sm:hidden space-y-2">
      <li v-for="(leg, i) in legs" :key="`m-${i}`" class="flex items-center gap-3">
        <span class="text-xs w-24 shrink-0 truncate" :class="leg.ok ? 'text-ink' : 'text-signal'">
          {{ leg.label }}
        </span>
        <span class="flex-1 h-1 rounded-full bg-raised overflow-hidden">
          <span
            class="block h-full rounded-full origin-left"
            :class="leg.ok ? 'bg-long' : 'bg-signal'"
            :style="{
              width: `${(leg.ms / slowest) * 100}%`,
              animation: `arrive ${durationFor(leg.ms)} cubic-bezier(0.2, 0.7, 0.3, 1) backwards`,
            }"
          />
        </span>
        <span class="num text-[0.65rem] shrink-0" :class="leg.ok ? 'text-ink-faint' : 'text-signal'">
          {{ leg.ok ? `${leg.ms}ms` : $t('landing.diagram.failedShort') }}
        </span>
      </li>
    </ul>

    <figcaption class="label mt-3 text-center">
      <slot name="caption" />
    </figcaption>
  </figure>
</template>
