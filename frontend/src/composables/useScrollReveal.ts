import { onMounted, onUnmounted, ref, type Ref } from 'vue'

/**
 * IntersectionObserver-based scroll reveal.
 * Add class `scroll-hidden` to the element, then call `useScrollReveal(el)`.
 * The element will animate in when it enters the viewport.
 */
export function useScrollReveal(el: Ref<HTMLElement | null>, options?: IntersectionObserverInit) {
  const isVisible = ref(false)
  let observer: IntersectionObserver | null = null

  onMounted(() => {
    if (!el.value) return

    observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          isVisible.value = true
          el.value && observer?.unobserve(el.value)
        }
      },
      { threshold: 0.1, rootMargin: '0px 0px -40px 0px', ...options },
    )

    observer.observe(el.value)
  })

  onUnmounted(() => {
    observer?.disconnect()
  })

  return { isVisible }
}
