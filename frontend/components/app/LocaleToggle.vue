<script setup lang="ts">
/**
 * The language switcher. Two locales used to be a toggle; with six, a menu.
 *
 * Choosing a locale also flips the document direction — see app.vue, which is
 * what makes Persian and Arabic a translation pass rather than a rebuild.
 *
 * The menu closes on outside click and Escape, and the whole control stays a
 * plain button until opened so keyboard users get the same one-tab experience.
 */
const { locale, locales, setLocale, t } = useI18n()

const open = ref(false)
const root = ref<HTMLElement | null>(null)

const all = computed(() => locales.value as { code: string; name: string }[])

function pick(code: string) {
  open.value = false
  setLocale(code as any)
}

function onDocumentClick(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) open.value = false
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') open.value = false
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div ref="root" class="relative">
    <button
      class="btn-quiet btn-sm text-xs font-medium uppercase"
      :aria-label="t('nav.language')"
      :aria-haspopup="'menu'"
      :aria-expanded="open"
      @click="open = !open"
    >
      <UiIcon name="globe" :size="15" />
      <span class="num">{{ locale }}</span>
      <UiIcon
        name="chevronDown"
        :size="13"
        class="transition-transform duration-150"
        :class="open ? 'rotate-180' : ''"
      />
    </button>

    <Transition
      enter-active-class="transition duration-100 ease-out"
      enter-from-class="opacity-0 translate-y-1"
      leave-active-class="transition duration-75 ease-in"
      leave-to-class="opacity-0"
    >
      <div
        v-if="open"
        role="menu"
        class="absolute end-0 top-full mt-1.5 z-50 min-w-44 max-h-80 overflow-y-auto py-1
               rounded-panel bg-panel border border-line shadow-pop"
      >
        <button
          v-for="l in all"
          :key="l.code"
          role="menuitem"
          class="w-full flex items-center gap-2.5 px-3 py-2 text-start text-sm transition-colors
                 hover:bg-raised"
          :class="l.code === locale ? 'text-brand' : 'text-ink-muted'"
          @click="pick(l.code)"
        >
          <span
            class="num text-[0.65rem] uppercase w-7 shrink-0 text-center rounded
                   border border-line bg-sunken py-0.5"
          >
            {{ l.code }}
          </span>
          <span class="truncate">{{ l.name }}</span>
          <UiIcon v-if="l.code === locale" name="check" :size="14" class="ms-auto" />
        </button>
      </div>
    </Transition>
  </div>
</template>
