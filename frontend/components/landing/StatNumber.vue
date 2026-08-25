<script setup lang="ts">
/**
 * Counts from zero to `to` when it scrolls into view.
 *
 * An ease-out cubic so the number slows as it lands; reduced-motion visitors
 * get the final value with no animation. The digits are tabular (`num`), so a
 * ticking figure never reflows the layout.
 */
const props = withDefaults(
  defineProps<{
    to: number
    decimals?: number
    duration?: number
  }>(),
  { decimals: 0, duration: 1500 },
)

const root = ref<HTMLElement | null>(null)
const display = ref('0')
let raf = 0

function format(n: number): string {
  return n.toLocaleString('en-US', {
    minimumFractionDigits: props.decimals,
    maximumFractionDigits: props.decimals,
  })
}

function run() {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    display.value = format(props.to)
    return
  }
  const start = performance.now()
  const tick = (now: number) => {
    const p = Math.min(1, (now - start) / props.duration)
    const eased = 1 - Math.pow(1 - p, 3)
    display.value = format(props.to * eased)
    if (p < 1) raf = requestAnimationFrame(tick)
  }
  raf = requestAnimationFrame(tick)
}

onMounted(() => {
  if (typeof IntersectionObserver === 'undefined' || !root.value) {
    run()
    return
  }
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          run()
          observer.disconnect()
        }
      }
    },
    { threshold: 0.4 },
  )
  observer.observe(root.value)
})

onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<template>
  <span ref="root" class="num inline-block">{{ display }}</span>
</template>
