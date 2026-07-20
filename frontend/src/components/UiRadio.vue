<script setup lang="ts">
interface Option {
  label: string
  value: string | number
}

const modelValue = defineModel<string | number>({ default: '' })

defineProps<{
  options: Option[]
  label?: string
  name?: string
  disabled?: boolean
}>()
</script>

<template>
  <div class="ui-radio-group">
    <span v-if="label" class="mb-2 block text-sm font-medium text-fg">{{ label }}</span>
    <div class="flex flex-col gap-2">
      <label
        v-for="opt in options"
        :key="opt.value"
        class="inline-flex cursor-pointer items-center gap-2.5 select-none"
        :class="{ 'cursor-not-allowed opacity-50': disabled }"
      >
        <span
          class="flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-full border-2 transition-all duration-200"
          :class="modelValue === opt.value
            ? 'border-accent bg-accent shadow-sm shadow-accent/20'
            : 'border-border hover:border-border-hover bg-surface'"
        >
          <span
            class="h-2 w-2 rounded-full bg-accent-fg transition-transform duration-200"
            :class="modelValue === opt.value ? 'scale-100' : 'scale-0'"
          />
        </span>
        <input
          :value="opt.value"
          v-model="modelValue"
          type="radio"
          :name="name"
          :disabled="disabled"
          class="sr-only"
        />
        <span class="text-sm text-fg">{{ opt.label }}</span>
      </label>
    </div>
  </div>
</template>
