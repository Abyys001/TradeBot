<script setup lang="ts">
/**
 * Who is signed in right now.
 *
 * The panel has one staff login by design — everybody uses the same name — so
 * "who has access" cannot be read off a user list. It is a list of *sessions*:
 * one row per browser holding that login, where it connected from, what it is
 * running, and when it was last seen. On a shared credential that list is the
 * only place an extra participant would show up at all.
 *
 * Polled slowly: this answers "who is here", which does not change between
 * heartbeats, and the dashboard already has three fast polls on it.
 */
const POLL_MS = 30000

const { t } = useI18n()
const { dateTime, since } = useFormat()
const api = useApi()

const sessions = ref<PanelSession[]>([])
const loading = ref(true)
const error = ref('')
let timer: ReturnType<typeof setInterval> | null = null

async function load() {
  try {
    sessions.value = (await api.sessions()).sessions
    error.value = ''
  } catch (e: unknown) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, POLL_MS)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  timer = null
})

const online = computed(() => sessions.value.filter((s) => s.online).length)
</script>

<template>
  <UiCard :title="t('dashboard.sessions')" :hint="t('dashboard.sessionsHint')" flush>
    <template #actions>
      <UiBadge :tone="online > 1 ? 'signal' : 'neutral'">
        {{ t('dashboard.sessionsOnline', { n: online }) }}
      </UiBadge>
    </template>

    <div v-if="loading" class="p-4 space-y-3">
      <div v-for="i in 2" :key="i" class="skeleton h-8" />
    </div>

    <ul v-else-if="sessions.length" class="divide-y divide-line">
      <li
        v-for="session in sessions"
        :key="session.id"
        class="px-4 py-3 flex flex-wrap items-center gap-x-4 gap-y-1.5"
      >
        <span
          class="w-1.5 h-1.5 rounded-full shrink-0"
          :class="session.online ? 'bg-long' : 'bg-ink-faint'"
          :aria-label="session.online ? t('dashboard.sessionOnline') : t('dashboard.sessionIdle')"
        />
        <span class="num text-sm font-medium">{{ session.username }}</span>
        <UiBadge v-if="session.current" tone="ok">{{ t('dashboard.sessionYou') }}</UiBadge>

        <span class="text-xs text-ink-muted">
          {{ session.device || t('dashboard.sessionUnknownDevice') }}
        </span>
        <span class="num text-xs text-ink-muted">
          {{ session.ip_address || '—' }}
        </span>

        <span class="text-xs text-ink-muted ms-auto" :title="dateTime(session.started_at)">
          {{ t('dashboard.sessionSince', { when: since(session.started_at) }) }}
        </span>
        <span class="text-xs w-28 text-end" :class="session.online ? 'text-long' : 'text-ink-faint'">
          {{
            session.online
              ? t('dashboard.sessionOnline')
              : t('dashboard.sessionSeen', { when: since(session.last_seen_at) })
          }}
        </span>
      </li>
    </ul>

    <UiEmpty
      v-else
      icon="accounts"
      :title="t('dashboard.noSessionsTitle')"
      :body="t('dashboard.noSessionsBody')"
    />

    <p v-if="error" class="px-4 py-2 text-[0.7rem] text-signal">{{ error }}</p>
  </UiCard>
</template>
