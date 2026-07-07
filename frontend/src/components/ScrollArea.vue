<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, useTemplateRef } from 'vue'

const props = withDefaults(
  defineProps<{
    size?: 'default' | 'thin' | 'wide'
    color?: 'violet' | 'zinc' | 'emerald' | 'red' | 'amber'
    track?: 'zinc' | 'transparent' | 'muted'
    hoverToShow?: boolean
    hideScrollbar?: boolean
    maxHeight?: string
    axis?: 'y' | 'x' | 'both'
  }>(),
  {
    size: 'default',
    color: 'violet',
    track: 'zinc',
    hoverToShow: false,
    hideScrollbar: false,
    axis: 'y',
  },
)

const el = useTemplateRef<HTMLElement>('scrollRef')
const isScrolling = ref(false)
let idleTimer: ReturnType<typeof setTimeout> | null = null

const scrollClasses = computed(() => {
  const classes = ['scrollbar-styled']
  if (props.size !== 'default') classes.push(`scrollbar-${props.size}`)
  if (props.color !== 'violet') classes.push(`scrollbar-${props.color}`)
  if (props.track !== 'zinc') classes.push(`scrollbar-track-${props.track}`)
  if (props.hoverToShow) classes.push('scrollbar-hover')
  if (props.hideScrollbar) classes.push('scrollbar-none')
  return classes
})

const overflowClass = computed(() => {
  switch (props.axis) {
    case 'x': return 'overflow-x-auto'
    case 'both': return 'overflow-auto'
    default: return 'overflow-y-auto'
  }
})

function onScroll() {
  isScrolling.value = true
  if (idleTimer) clearTimeout(idleTimer)
  idleTimer = setTimeout(() => {
    isScrolling.value = false
  }, 1500)
}

onMounted(() => {
  const target = el.value
  if (!target) return
  target.addEventListener('scroll', onScroll, { passive: true })
})

onUnmounted(() => {
  const target = el.value
  if (target) target.removeEventListener('scroll', onScroll)
  if (idleTimer) clearTimeout(idleTimer)
})
</script>

<template>
  <div
    ref="scrollRef"
    class="scroll-area min-h-0"
    :class="[...scrollClasses, overflowClass, { 'is-scrolling': isScrolling }]"
    :style="maxHeight ? { maxHeight: maxHeight } : undefined"
  >
    <slot />
  </div>
</template>

<style scoped>
.scroll-area {
  scroll-behavior: smooth;
}

.scroll-area::-webkit-scrollbar-thumb {
  transition: background var(--sb-transition-duration, 0.15s),
              opacity 0.35s ease;
}

.scroll-area:not(.is-scrolling):not(:hover)::-webkit-scrollbar-thumb {
  opacity: 0.5;
}
</style>
