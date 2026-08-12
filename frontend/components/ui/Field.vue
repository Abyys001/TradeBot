<script setup lang="ts">
/**
 * Label + control + hint/error, wired together.
 *
 * The wiring is the point: `for`/`id` and `aria-describedby` are what make a
 * hint reach a screen reader and a click on the label focus the input. Doing it
 * by hand at forty call sites means it is right at thirty of them.
 */
defineProps<{ label: string; hint?: string; error?: string; optional?: boolean }>()

const id = useId()
const hintId = useId()
</script>

<template>
  <div class="min-w-0">
    <label :for="id" class="label flex items-baseline gap-2">
      <span>{{ label }}</span>
      <span v-if="optional" class="text-ink-faint normal-case tracking-normal">
        {{ $t('common.optional') }}
      </span>
    </label>

    <div class="mt-1.5">
      <slot :id="id" :described-by="hint || error ? hintId : undefined" />
    </div>

    <p v-if="error" :id="hintId" class="text-xs text-short mt-1.5">{{ error }}</p>
    <p v-else-if="hint" :id="hintId" class="text-xs text-ink-faint mt-1.5 leading-relaxed">
      {{ hint }}
    </p>
  </div>
</template>
