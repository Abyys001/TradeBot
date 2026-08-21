<script setup lang="ts">
/**
 * What went wrong on this account, and every change made to its money record.
 *
 * The notification centre shows the *active* failures across the panel, which
 * is the right shape for acting on them and the wrong one for asking "does this
 * account keep failing". Dismissed notices are kept here for that reason: a
 * cleared notification is still evidence.
 */
defineProps<{ report: AccountReport }>()

const { t } = useI18n()
const { dateTime } = useFormat()
</script>

<template>
  <div class="space-y-3 sm:space-y-4">
    <UiCard
      :title="t('accounts.report.failures')"
      :hint="t('accounts.report.failuresHint')"
      flush
    >
      <ul v-if="report.notifications.length" class="divide-y divide-line max-h-[26rem] overflow-y-auto">
        <li v-for="notice in report.notifications" :key="notice.id" class="px-4 py-2.5 space-y-1">
          <div class="flex flex-wrap items-center gap-x-2.5 gap-y-1">
            <UiBadge :tone="notice.is_active ? 'signal' : 'neutral'" :dot="notice.is_active">
              {{ notice.is_active ? t('accounts.report.active') : t('accounts.report.dismissed') }}
            </UiBadge>
            <span v-if="notice.code" class="num text-xs text-ink-muted">{{ notice.code }}</span>
            <span class="num text-[0.65rem] text-ink-faint ms-auto">
              {{ dateTime(notice.created_at) }}
            </span>
          </div>
          <p class="text-xs leading-relaxed">{{ notice.message }}</p>
        </li>
      </ul>

      <div v-else class="p-6">
        <UiEmpty
          icon="check"
          :title="t('accounts.report.noFailures')"
          :body="t('accounts.report.noFailuresBody')"
        />
      </div>
    </UiCard>

    <!-- The same audit trail the finance page shows, narrowed to this account. -->
    <FinanceAuditTrail :account="report.account.id" />
  </div>
</template>
