<script setup lang="ts">
/**
 * Transient confirmations — spec §10's open question about *successful* trade
 * notifications, answered.
 *
 * These auto-expire; spec §4 failure notices never do and live in the top bar's
 * notification centre instead. Keeping the two visually distinct matters: if
 * both looked alike, an admin who learned that "those little cards go away on
 * their own" would learn the wrong lesson about the ones that do not.
 *
 * Bottom-centre, above the phone tab bar and clear of the order ticket.
 */
const notifications = useNotificationStore()
const { t } = useI18n()
</script>

<template>
  <div
    class="fixed z-[70] inset-x-0 bottom-[4.75rem] lg:bottom-5 flex flex-col items-center gap-2
           px-3 pointer-events-none"
    role="status"
    aria-live="polite"
  >
    <TransitionGroup
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0 translate-y-2"
      leave-active-class="transition duration-150 ease-in absolute"
      leave-to-class="opacity-0 translate-y-1"
      move-class="transition duration-150"
    >
      <div
        v-for="toast in notifications.toasts"
        :key="toast.id"
        class="pointer-events-auto max-w-sm w-full sm:w-auto flex items-center gap-2.5 rounded-lg
               border bg-panel px-3 py-2 shadow-lift"
        :class="toast.tone === 'ok' ? 'border-ok/40' : 'border-signal/50'"
      >
        <UiIcon
          :name="toast.tone === 'ok' ? 'check' : 'alert'"
          :size="14"
          :class="toast.tone === 'ok' ? 'text-ok' : 'text-signal'"
        />
        <div class="min-w-0">
          <p class="text-xs">{{ toast.message }}</p>
          <p v-if="toast.detail" class="num text-[0.65rem] text-ink-faint">{{ toast.detail }}</p>
        </div>
        <button
          class="btn-quiet btn-sm -me-1.5 ms-auto"
          :aria-label="t('common.close')"
          @click="notifications.dropToast(toast.id)"
        >
          <UiIcon name="close" :size="12" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>
