<script setup lang="ts">
/**
 * The eight exchanges, scrolling past.
 *
 * One track, two identical copies, animated -50%: the seam is invisible and
 * the loop never stutters. Pauses on hover so a name can be read. The track is
 * pinned LTR so the scroll direction is the same in the RTL locales, and the
 * duplicate copy is hidden under reduced motion rather than left to sit
 * static beside the original.
 */
const { t } = useI18n()
</script>

<template>
  <section class="border-t border-line bg-panel/40" :aria-label="t('landing.marquee.label')">
    <div class="py-5 overflow-hidden" dir="ltr">
      <p class="label text-center mb-4">{{ t('landing.marquee.label') }}</p>
      <div class="flex w-max animate-marquee hover:[animation-play-state:paused]">
        <div v-for="copy in 2" :key="copy" class="flex shrink-0" :aria-hidden="copy === 2">
          <span
            v-for="exchange in EXCHANGES"
            :key="exchange"
            class="chip me-3 border-line text-ink-muted bg-base/60 normal-case tracking-normal text-xs"
          >
            {{ exchange }}
          </span>
        </div>
      </div>
    </div>
  </section>
</template>
