<script setup lang="ts">
/**
 * The access history: who reached the panel, from where, and what they changed.
 *
 * Only written while the audit switch is on — with it off there is nothing to
 * show, and the card says that rather than rendering an empty list that reads
 * like "nobody has signed in". The one exception is a change to the switches
 * themselves, which is always recorded, so a history that looks empty except
 * for policy rows is exactly right.
 *
 * Every label comes from the server. Mapping a code to prose in the browser
 * would make a second list to keep in step with `SecurityEventKind`.
 */
const props = defineProps<{ enabled: boolean }>()

const { t } = useI18n()
const { dateTime, since } = useFormat()
const security = useSecurityStore()

const expanded = ref(false)

/** Which rows read as trouble. Everything else is normal traffic. */
const ALARMING = new Set([
  'login_failed',
  'login_locked',
  'mfa_failed',
  'recovery_used',
  'ip_blocked',
  'rate_limited',
  'step_up_failed',
  'new_device',
])
const NOTABLE = new Set(['policy_changed', 'session_revoked', 'mfa_disabled'])

function tone(kind: string) {
  if (ALARMING.has(kind)) return 'signal' as const
  if (NOTABLE.has(kind)) return 'brand' as const
  return 'neutral' as const
}

const rows = computed(() => (expanded.value ? security.events : security.events.slice(0, 8)))

onMounted(() => {
  if (props.enabled) security.loadEvents()
})
watch(
  () => props.enabled,
  (on) => on && security.loadEvents(),
)
</script>

<template>
  <div>
    <div v-if="security.eventsLoading" class="p-4 space-y-2">
      <div v-for="i in 4" :key="i" class="skeleton h-8" />
    </div>

    <ul v-else-if="rows.length" class="divide-y divide-line">
      <li
        v-for="event in rows"
        :key="event.id"
        class="px-4 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1"
      >
        <UiBadge :tone="tone(event.kind)" dot>{{ event.label }}</UiBadge>
        <span v-if="event.username" class="num text-xs">{{ event.username }}</span>
        <span class="num text-xs text-ink-muted">{{ event.ip_address || '—' }}</span>
        <span class="text-xs text-ink-faint ms-auto" :title="dateTime(event.at)">
          {{ since(event.at) }}
        </span>
      </li>
    </ul>

    <UiEmpty
      v-else
      icon="shield"
      :title="enabled ? t('security.events.emptyTitle') : t('security.events.offTitle')"
      :body="enabled ? t('security.events.emptyBody') : t('security.events.offBody')"
    />

    <button
      v-if="security.events.length > 8"
      class="btn-ghost btn-sm w-full rounded-none border-t border-line"
      @click="expanded = !expanded"
    >
      {{ expanded ? t('common.showLess') : t('security.events.showAll', { n: security.events.length }) }}
    </button>
  </div>
</template>
