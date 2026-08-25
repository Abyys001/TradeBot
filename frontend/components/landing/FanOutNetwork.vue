<script setup lang="ts">
/**
 * The product's promise, drawn as a constellation.
 *
 * One origin — the admin's action — emits a pulse that splits into legs, each
 * reaching an exchange node at that leg's own dispatch speed. A slow exchange
 * visibly lags, and the one that fails stops short and turns amber, the same
 * colour the persistent failure notice uses, because it means the same thing.
 *
 * The hero version of FanOutDiagram: same story, more atmosphere. Rings pulse
 * off the origin, the nodes carry halos, and a terminal-style readout under
 * the drawing tells the whole trade in one line. The demo replay re-keys only
 * the travelling strokes and the mobile bars — everything else stays mounted,
 * so a cycle never flashes the figure.
 */
const { t } = useI18n()

const props = withDefaults(defineProps<{ legs?: FanLeg[] }>(), {})

const legs = computed(() => (props.legs?.length ? props.legs : DEMO_LEGS))
const isDemo = computed(() => !props.legs?.length)

const W = 560
const H = 380
const ORIGIN = { x: 88, y: H / 2 }

const nodes = computed(() =>
  legs.value.map((leg, i) => {
    const count = legs.value.length
    const spread = H - 92
    const y = count === 1 ? H / 2 : 46 + (spread / (count - 1)) * i
    return { ...leg, x: W - 156, y }
  }),
)

const slowest = computed(() => Math.max(...legs.value.map((l) => l.ms), 1))

const okCount = computed(() => legs.value.filter((l) => l.ok).length)
const failed = computed(() => legs.value.find((l) => !l.ok))

const cycle = ref(0)
const CYCLE_MS = 4600

function pathFor(node: { x: number; y: number }) {
  const midX = (ORIGIN.x + node.x) / 2
  return `M ${ORIGIN.x} ${ORIGIN.y} C ${midX} ${ORIGIN.y}, ${midX} ${node.y}, ${node.x} ${node.y}`
}

/** Slow the real millisecond figures to something the eye can follow. */
function durationFor(ms: number) {
  return `${Math.max(0.35, (ms / slowest.value) * 1.6)}s`
}

const BOLT = 'M13 2 4 14h7l-1 8 9-12h-7l1-8Z'

let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  // Reduced motion is honoured in CSS below rather than here, so the drawing
  // renders complete on the server too instead of waiting for hydration.
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  if (!isDemo.value) return
  timer = setInterval(() => cycle.value++, CYCLE_MS)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <figure class="relative min-w-0" dir="ltr">
    <!-- A quiet dot grid behind the drawing: exchange charts read as grids,
         and this one anchors the constellation without competing with it. -->
    <div class="dot-grid pointer-events-none absolute inset-0 rounded-panel" aria-hidden="true" />

    <!-- Header: what this figure is, in one line. -->
    <figcaption class="relative flex items-center gap-2.5">
      <span class="relative flex h-2 w-2 shrink-0" :title="t('landing.network.badge')">
        <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-ok opacity-60" />
        <span class="relative inline-flex h-2 w-2 rounded-full bg-ok" />
      </span>
      <span class="label">{{ t('landing.network.badge') }}</span>
      <span class="label text-ink-faint">·</span>
      <span class="text-xs font-medium text-ink truncate">{{ t('landing.network.title') }}</span>
    </figcaption>

    <!-- Fan, sm and up -->
    <svg
      :viewBox="`0 0 ${W} ${H}`"
      class="hidden sm:block w-full h-auto overflow-visible"
      role="img"
      :aria-label="`One order fanning out to ${legs.length} accounts`"
    >
      <g fill="none" stroke-linecap="round">
        <!-- Rails: where the legs travel, faint. -->
        <path
          v-for="(node, i) in nodes"
          :key="`p-${i}`"
          :d="pathFor(node)"
          class="stroke-line-strong"
          stroke-width="1"
        />
        <!-- The only thing that restarts. Re-keying replaces the element in the
             same patch, so the stroke redraws without the figure ever emptying. -->
        <path
          v-for="(node, i) in nodes"
          :key="`a-${i}-${cycle}`"
          :d="pathFor(node)"
          class="fan-animated"
          :class="node.ok ? 'stroke-long' : 'stroke-signal'"
          stroke-width="1.6"
          pathLength="100"
          stroke-dasharray="100"
          :style="{
            '--dash': 100,
            animation: `travel ${durationFor(node.ms)} cubic-bezier(0.2, 0.7, 0.3, 1) forwards`,
          }"
        />
      </g>

      <!-- Origin: the admin's action. -->
      <g>
        <circle :cx="ORIGIN.x" :cy="ORIGIN.y" r="54" class="fill-brand/5" />
        <circle
          :cx="ORIGIN.x"
          :cy="ORIGIN.y"
          r="24"
          class="ring-pulse animate-pulse-ring stroke-brand/40"
          stroke-width="1"
        />
        <circle
          :cx="ORIGIN.x"
          :cy="ORIGIN.y"
          r="40"
          class="ring-pulse animate-pulse-ring stroke-brand/25"
          stroke-width="1"
          style="animation-delay: 0.9s"
        />
        <circle :cx="ORIGIN.x" :cy="ORIGIN.y" r="21" class="fill-panel stroke-line" />
        <path
          :d="BOLT"
          :transform="`translate(${ORIGIN.x - 6.25}, ${ORIGIN.y - 6}) scale(0.5)`"
          class="fill-brand"
        />
        <text
          :x="ORIGIN.x"
          :y="ORIGIN.y + 42"
          text-anchor="middle"
          class="fill-ink-faint text-[10px] uppercase tracking-[0.16em]"
        >
          {{ $t('landing.diagram.origin') }}
        </text>
      </g>

      <!-- Accounts: halos pop in once on first draw, never on replay. -->
      <g>
        <g
          v-for="(node, i) in nodes"
          :key="`n-${i}`"
          class="fan-animated"
          :style="
            cycle === 0
              ? { animation: `arrive 0.28s ease-out ${durationFor(node.ms)} backwards` }
              : undefined
          "
        >
          <circle
            :cx="node.x"
            :cy="node.y"
            r="10"
            :class="node.ok ? 'fill-long/10 stroke-long/30' : 'fill-signal/10 stroke-signal/40'"
            stroke-width="1"
          />
          <circle :cx="node.x" :cy="node.y" r="4.5" :class="node.ok ? 'fill-long' : 'fill-signal'" />
          <text
            :x="node.x + 16"
            :y="node.y + 2"
            class="text-[11px]"
            :class="node.ok ? 'fill-ink-muted' : 'fill-signal'"
          >
            {{ node.label }}
          </text>
          <text
            :x="node.x + 16"
            :y="node.y + 15"
            class="text-[10px] tabular-nums"
            :class="node.ok ? 'fill-ink-faint' : 'fill-signal'"
          >
            {{ node.ok ? `${node.ms} ms` : $t('landing.diagram.failed') }}
          </text>
        </g>
      </g>
    </svg>

    <!-- Stacked, below sm. Same data, bar length is the same dispatch time. -->
    <ul class="sm:hidden mt-4 space-y-2">
      <li v-for="(leg, i) in legs" :key="`m-${i}`" class="flex items-center gap-3">
        <span class="text-xs w-24 shrink-0 truncate" :class="leg.ok ? 'text-ink' : 'text-signal'">
          {{ leg.label }}
        </span>
        <span class="flex-1 h-1 rounded-full bg-raised overflow-hidden">
          <span
            :key="`b-${i}-${cycle}`"
            class="fan-animated block h-full rounded-full origin-left"
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

    <!-- The whole trade in one terminal-style line. -->
    <div class="relative mt-4 sm:mt-5 pt-3 border-t border-line flex items-center gap-2 flex-wrap num text-xs">
      <span class="text-ink font-medium">BTCUSDT</span>
      <span class="text-long">LONG</span>
      <span class="text-ink-faint">·</span>
      <span :class="failed ? 'text-ink-muted' : 'text-ok'">
        {{ t('landing.network.filled', { ok: okCount, total: legs.length }) }}
      </span>
      <template v-if="failed">
        <span class="text-ink-faint">·</span>
        <span class="text-signal">{{ t('landing.network.failed', { label: failed.label }) }}</span>
      </template>
    </div>
  </figure>
</template>

<style scoped>
/* Handled here rather than in JS so the drawing is already whole in the server
   render — nothing waits for hydration, so there is no first-paint flash. */
@media (prefers-reduced-motion: reduce) {
  .fan-animated {
    animation: none !important;
    stroke-dashoffset: 0 !important;
    opacity: 1 !important;
    transform: none !important;
  }
  .ring-pulse {
    animation: none !important;
    opacity: 1 !important;
  }
}

/* Pulse rings must scale around their own centre, not the SVG origin. The
   animation itself is Tailwind's animate-pulse-ring, so its keyframes are
   emitted once and shared. */
.ring-pulse {
  transform-box: fill-box;
  transform-origin: center;
}

.dot-grid {
  background-image: radial-gradient(rgb(var(--c-line) / 0.55) 1px, transparent 1px);
  background-size: 22px 22px;
  mask-image: radial-gradient(ellipse at center, black 55%, transparent 100%);
}
</style>
