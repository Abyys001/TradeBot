<script setup lang="ts">
/**
 * Spec §7's emergency halt, in the top bar of every page.
 *
 * It lives in the chrome rather than on the settings page because of *when* it
 * is used: an exchange is behaving strangely, or an order went somewhere it
 * should not have, and the admin needs routing stopped now. Two navigations
 * away is the wrong place for that control.
 *
 * Asymmetric on purpose. Halting is one click, no dialog — the moment this is
 * wanted is not the moment to fill in a form. Resuming asks, because that is
 * the direction that starts moving other people's money again.
 *
 * Closing and amending open positions keep working while halted; the copy says
 * so, so nobody assumes their open leveraged positions are now stranded.
 */
const { t } = useI18n()
const trading = useTradingStore()

const confirmResume = ref(false)

async function halt() {
  try {
    await trading.setHalt(true, 'halted from the panel')
  } catch {
    // The store carries the message; the badge state is authoritative.
  }
}

async function resume() {
  confirmResume.value = false
  try {
    await trading.setHalt(false)
  } catch {
    /* as above */
  }
}
</script>

<template>
  <div>
    <button
      v-if="!trading.halted"
      class="btn-quiet btn-sm text-ink-muted hover:text-short"
      :disabled="trading.haltPending"
      :title="t('policy.stopAllHint')"
      @click="halt"
    >
      <UiIcon name="alert" :size="15" />
      <span class="hidden lg:inline">{{ t('policy.stopAll') }}</span>
    </button>

    <button
      v-else
      class="btn-sm btn border border-signal/60 bg-signal/10 text-signal"
      :disabled="trading.haltPending || trading.haltLocked"
      :title="trading.haltLocked ? t('policy.stopAllLocked') : t('policy.resumeHint')"
      @click="confirmResume = true"
    >
      <span class="w-1.5 h-1.5 rounded-full bg-signal animate-pulse" />
      <span class="hidden sm:inline">{{ t('policy.stopAllActive') }}</span>
    </button>

    <UiModal v-model="confirmResume" :title="t('policy.resumeTitle')" size="sm">
      <p class="text-sm leading-relaxed">{{ t('policy.resumeBody') }}</p>
      <p v-if="trading.haltReason" class="text-xs text-ink-muted mt-3">
        {{ t('policy.haltedBecause', { reason: trading.haltReason }) }}
      </p>
      <template #footer>
        <div class="flex gap-2 justify-end">
          <button class="btn-ghost" @click="confirmResume = false">{{ t('common.cancel') }}</button>
          <button class="btn-brand" :disabled="trading.haltPending" @click="resume">
            {{ t('policy.resume') }}
          </button>
        </div>
      </template>
    </UiModal>
  </div>
</template>
