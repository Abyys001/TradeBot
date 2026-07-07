<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../../stores/auth'
import { useToast } from '../../composables/useToast'
import { api } from '../../api/client'

const { t } = useI18n()
const auth = useAuthStore()
const toast = useToast()
const toggling = ref(false)

async function toggleTrading() {
  if (!auth.user) return
  toggling.value = true
  try {
    const enabled = !auth.user.is_trading_enabled
    await api.post('/me/kill-switch/', { enabled, close_positions: false })
    auth.user.is_trading_enabled = enabled
    toast.show(enabled ? t('settings.tradingEnabled') : t('settings.tradingDisabled'), 'success')
  } finally {
    toggling.value = false
  }
}
</script>

<template>
  <section class="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6">
    <h2 class="text-sm font-semibold text-zinc-300 mb-4">{{ t('settings.account') }}</h2>
    <dl class="space-y-3 text-sm">
      <div class="flex justify-between">
        <dt class="text-zinc-500">{{ t('auth.username') }}</dt>
        <dd class="text-zinc-200">{{ auth.user?.username }}</dd>
      </div>
      <div class="flex justify-between items-center">
        <dt class="text-zinc-500">{{ t('health.trading') }}</dt>
        <dd>
          <button
            type="button"
            class="rounded-lg px-3 py-1 text-xs font-medium transition-colors disabled:opacity-50"
            :class="
              auth.user?.is_trading_enabled
                ? 'bg-emerald-900/50 text-emerald-400'
                : 'bg-zinc-800 text-zinc-500'
            "
            :disabled="toggling"
            @click="toggleTrading"
          >
            {{ auth.user?.is_trading_enabled ? t('health.on') : t('health.off') }}
          </button>
        </dd>
      </div>
    </dl>
  </section>
</template>
