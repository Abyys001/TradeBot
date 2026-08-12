<script setup lang="ts">
/**
 * A segmented control: two to four mutually exclusive choices, all visible.
 *
 * Preferred over a `<select>` wherever the options matter — side, basis, order
 * type. Hiding "short" behind a dropdown adds a click and a moment of doubt to
 * every trade in that direction.
 */
type Option = { value: string; label: string; tone?: 'long' | 'short' | 'default' }

const model = defineModel<string>({ required: true })
withDefaults(defineProps<{ options: Option[]; size?: 'sm' | 'md'; block?: boolean }>(), {
  size: 'md',
  block: true,
})

const TONE: Record<string, string> = {
  long: 'bg-long/10 text-long border-long/60',
  short: 'bg-short/10 text-short border-short/60',
  default: 'bg-raised text-ink border-line-strong',
}
</script>

<template>
  <div
    class="inline-flex p-0.5 rounded-lg bg-sunken border border-line"
    :class="block ? 'w-full' : ''"
    role="group"
  >
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      class="flex-1 rounded-[0.4rem] border transition-all duration-150 font-medium whitespace-nowrap"
      :class="[
        size === 'sm' ? 'text-xs py-1 px-2' : 'text-sm py-1.5 px-3',
        model === option.value
          ? TONE[option.tone ?? 'default']
          : 'border-transparent text-ink-muted hover:text-ink',
      ]"
      :aria-pressed="model === option.value"
      @click="model = option.value"
    >
      {{ option.label }}
    </button>
  </div>
</template>
