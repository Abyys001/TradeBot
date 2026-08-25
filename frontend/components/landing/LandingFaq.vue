<script setup lang="ts">
/**
 * The operator's questions, answered straight.
 *
 * One panel open at a time — an accordion is a navigation aid, and two open
 * answers would just be a long page. The body animates via grid-template-rows
 * (0fr → 1fr), which needs no measuring and never fights the RTL layout.
 */
const { t } = useI18n()

const open = ref<number | null>(0)

const items = computed(() =>
  [1, 2, 3, 4, 5, 6].map((i) => ({
    q: t(`landing.faq.q${i}`),
    a: t(`landing.faq.a${i}`),
  })),
)
</script>

<template>
  <div class="space-y-2.5">
    <div
      v-for="(item, i) in items"
      :key="i"
      v-reveal="i * 70"
      class="panel overflow-hidden"
    >
      <button
        class="w-full flex items-center gap-3 px-4 sm:px-5 py-4 text-start transition-colors hover:bg-raised/60"
        :aria-expanded="open === i"
        :aria-controls="`faq-${i}`"
        @click="open = open === i ? null : i"
      >
        <span class="flex-1 text-sm font-medium min-w-0">{{ item.q }}</span>
        <UiIcon
          name="chevronDown"
          :size="16"
          class="shrink-0 text-ink-faint transition-transform duration-200"
          :class="open === i ? 'rotate-180' : ''"
        />
      </button>
      <div
        :id="`faq-${i}`"
        class="grid transition-[grid-template-rows] duration-300 ease-out"
        :class="open === i ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'"
      >
        <div class="overflow-hidden">
          <p class="px-4 sm:px-5 pb-4 ps-12 text-sm text-ink-muted leading-relaxed">
            {{ item.a }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
