/**
 * `v-reveal` — scroll-triggered entrance.
 *
 * Adds a fade-and-rise to an element the first time it enters the viewport.
 * Nothing here runs for a visitor who prefers reduced motion, and nothing is
 * hidden if IntersectionObserver is missing: the element simply renders.
 * Content is never invisible without JavaScript, because the hidden state is
 * applied by this directive itself at mount time — no-JS pages show it whole.
 *
 * Usage:
 *   <div v-reveal>                      plain fade + rise (16px)
 *   <div v-reveal="120">                same, delayed 120ms (stagger)
 *   <div v-reveal="{ y: 32, delay: 200 }">
 *
 * The delay exists for staggering siblings: give each card an increasing
 * delay rather than relying on scroll position to space them out.
 */
import type { DirectiveBinding } from 'vue'

type RevealOptions = number | { y?: number; delay?: number }

const REDUCED = '(prefers-reduced-motion: reduce)'

function applyHidden(el: HTMLElement, y: number) {
  el.style.opacity = '0'
  el.style.transform = `translateY(${y}px)`
  el.style.willChange = 'opacity, transform'
}

function applyVisible(el: HTMLElement, delay: number) {
  el.style.transition =
    `opacity 0.6s cubic-bezier(0.2, 0.7, 0.3, 1) ${delay}ms, ` +
    `transform 0.6s cubic-bezier(0.2, 0.7, 0.3, 1) ${delay}ms`
  el.style.opacity = '1'
  el.style.transform = 'translateY(0)'
  el.style.willChange = 'auto'
}

function normalize(value: RevealOptions | undefined): { y: number; delay: number } {
  if (typeof value === 'number') return { y: 16, delay: value }
  return { y: value?.y ?? 16, delay: value?.delay ?? 0 }
}

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.vueApp.directive('reveal', {
    mounted(el: HTMLElement, binding: DirectiveBinding<RevealOptions>) {
      if (window.matchMedia(REDUCED).matches || typeof IntersectionObserver === 'undefined') {
        return
      }
      const { y, delay } = normalize(binding.value)
      applyHidden(el, y)
      const observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting) {
              applyVisible(el, delay)
              observer.disconnect()
            }
          }
        },
        // A little headroom: the element has started rising before it is fully
        // inside the viewport, so a reveal never feels late.
        { threshold: 0.15, rootMargin: '0px 0px -8% 0px' },
      )
      observer.observe(el)
    },
  })
})
