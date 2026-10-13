<script setup lang="ts">
/**
 * "Install app" — shown only where pressing it does something: a Chromium
 * browser holding an install prompt, or iOS Safari where the only route is the
 * Share sheet and this explains it. Gone once installed or dismissed.
 */
withDefaults(defineProps<{ variant?: 'icon' | 'row' }>(), { variant: 'icon' })

const { t } = useI18n()
const { canInstall, showIosHelp, install, dismiss } = useInstallPrompt()
</script>

<template>
  <div class="contents">
    <template v-if="canInstall">
      <div v-if="variant === 'row'" class="flex items-center rounded-lg hover:bg-raised transition-colors">
        <button
          class="flex-1 min-w-0 flex items-center gap-3 px-3 h-11 text-sm text-ink-muted hover:text-ink"
          @click="install"
        >
          <UiIcon name="download" :size="18" />
          <span class="truncate">{{ t('install.button') }}</span>
        </button>
        <button
          class="btn-quiet btn-sm btn-icon me-1"
          :aria-label="t('install.dismiss')"
          :title="t('install.dismiss')"
          @click="dismiss"
        >
          <UiIcon name="close" :size="14" />
        </button>
      </div>
      <button v-else class="btn-ghost btn-sm hidden sm:inline-flex" :title="t('install.hint')" @click="install">
        <UiIcon name="download" :size="14" />
        <span class="hidden lg:inline">{{ t('install.button') }}</span>
        <span class="sr-only lg:hidden">{{ t('install.button') }}</span>
      </button>
    </template>

    <UiModal v-model="showIosHelp" :title="t('install.iosTitle')" size="sm">
      <ol class="space-y-3 text-sm leading-relaxed list-decimal ps-5">
        <li>{{ t('install.iosStep1') }}</li>
        <li>{{ t('install.iosStep2') }}</li>
        <li>{{ t('install.iosStep3') }}</li>
      </ol>
      <template #footer>
        <div class="flex gap-2 justify-end">
          <button class="btn-ghost btn-sm" @click="dismiss(); showIosHelp = false">
            {{ t('install.dontAsk') }}
          </button>
          <button class="btn-brand btn-sm" @click="showIosHelp = false">{{ t('common.close') }}</button>
        </div>
      </template>
    </UiModal>
  </div>
</template>
