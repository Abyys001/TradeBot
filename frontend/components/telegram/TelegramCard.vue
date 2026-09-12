<script setup lang="ts">
/**
 * Telegram delivery for the notifications the panel already raises — one
 * chat, one bot token held encrypted server-side and never shown again.
 *
 * Enabling is refused server-side with no token or no linked chat, so the
 * switch here is disabled with a reason rather than sent and bounced.
 * Token replacement, linking and unlinking are the sensitive writes and can
 * ask for the password again — same shared prompt `SecurityCard`
 * uses, replayed the same way: keep the retry, replay it once granted.
 */
const { t } = useI18n()
const { dateTime } = useFormat()
const telegram = useTelegramStore()

onMounted(async () => {
  await telegram.load()
  if (telegram.linkPending && !telegram.linked) telegram.startPolling()
})
onUnmounted(() => telegram.stopPolling())

const state = computed(() => telegram.state)

/** The last change that hit step-up, replayed once the password is confirmed. */
const retry = ref<(() => unknown) | null>(null)

async function afterStepUp() {
  if (!retry.value) return
  const fn = retry.value
  retry.value = null
  await fn()
}

async function onToggleEnabled(on: boolean) {
  retry.value = () => onToggleEnabled(on)
  await telegram.save({ enabled: on }, 'enabled')
}

const enableBlocked = computed(() =>
  !telegram.configured
    ? t('telegram.enable.blockedToken')
    : !telegram.linked
      ? t('telegram.enable.blockedLink')
      : '',
)

// --- token ---
const tokenInput = ref('')
const replacingToken = ref(false)
const removingToken = ref(false)

async function saveToken() {
  if (!tokenInput.value.trim()) return
  retry.value = () => saveToken()
  const ok = await telegram.saveToken(tokenInput.value.trim())
  if (ok) {
    tokenInput.value = ''
    replacingToken.value = false
  }
}

async function removeToken() {
  retry.value = () => removeToken()
  const ok = await telegram.saveToken('')
  if (ok) removingToken.value = false
}

// --- recipient ---
const recipient = ref('')
watch(
  () => state.value?.recipient_username,
  (value) => (recipient.value = value ?? ''),
  { immediate: true },
)

function stripHandle(value: string): string {
  return value.trim().replace(/^@/, '')
}

async function saveRecipient() {
  const value = stripHandle(recipient.value)
  if (value === (state.value?.recipient_username ?? '')) return
  retry.value = () => saveRecipient()
  await telegram.save({ recipient_username: value }, 'recipient')
  recipient.value = telegram.state?.recipient_username ?? value
}

const canLink = computed(
  () => telegram.configured && Boolean(stripHandle(recipient.value)) && !telegram.linked,
)

async function onLink() {
  retry.value = () => onLink()
  await telegram.link()
}

async function onUnlink() {
  retry.value = () => onUnlink()
  await telegram.unlink()
}

// --- language ---
const LANGUAGE_OPTIONS = computed(() => [
  { value: 'en', label: t('telegram.language.en') },
  { value: 'fa', label: t('telegram.language.fa') },
])

const language = computed({
  get: () => state.value?.language ?? 'en',
  set: (value: string) => {
    const lang = value as 'en' | 'fa'
    retry.value = () => telegram.save({ language: lang }, 'language')
    telegram.save({ language: lang }, 'language')
  },
})

// --- groups ---
const ALL_GROUPS = ['trades', 'bots', 'money', 'risk', 'system', 'admin'] as const

function groupOn(name: string): boolean {
  return telegram.groups.includes(name)
}

async function toggleGroup(name: string, on: boolean) {
  const next = on ? [...telegram.groups, name] : telegram.groups.filter((g) => g !== name)
  retry.value = () => toggleGroup(name, on)
  await telegram.save({ groups: next }, `group:${name}`)
}

async function onTest() {
  await telegram.test()
}
</script>

<template>
  <UiCard :title="t('telegram.title')" :hint="t('telegram.hint')" flush>
    <template #actions>
      <UiBadge v-if="telegram.linked" tone="ok" dot>{{ t('telegram.status.linked') }}</UiBadge>
      <UiBadge v-else-if="telegram.linkPending" tone="signal" dot>{{ t('telegram.status.pending') }}</UiBadge>
      <UiBadge v-else tone="neutral">{{ t('telegram.status.notLinked') }}</UiBadge>
    </template>

    <div v-if="telegram.loading" class="p-4 space-y-3">
      <div v-for="i in 4" :key="i" class="skeleton h-10" />
    </div>

    <template v-else>
      <p v-if="telegram.error" class="px-4 py-2.5 alert text-xs rounded-none border-x-0 border-t-0">
        {{ telegram.error }}
      </p>

      <ul class="divide-y divide-line">
        <!-- Enable -->
        <li class="px-4 py-3.5">
          <UiSwitch
            :model-value="Boolean(state?.enabled)"
            :label="t('telegram.enable.label')"
            :hint="enableBlocked || t('telegram.enable.hint')"
            :disabled="Boolean(enableBlocked) || telegram.saving === 'enabled'"
            @update:model-value="onToggleEnabled"
          />
        </li>

        <!-- Bot token -->
        <li class="px-4 py-3.5">
          <p class="text-sm">{{ t('telegram.token.label') }}</p>
          <p class="text-xs text-ink-muted mt-0.5 leading-relaxed">{{ t('telegram.token.help') }}</p>

          <div v-if="state?.configured && !replacingToken" class="mt-2.5 flex flex-wrap items-center gap-2 text-xs">
            <UiBadge tone="ok" dot>@{{ state.bot_username }}</UiBadge>
            <UiBadge tone="neutral">{{ t('telegram.token.fingerprint', { fp: state.token_fingerprint }) }}</UiBadge>
            <button class="btn-ghost btn-sm" @click="replacingToken = true">{{ t('common.change') }}</button>
            <button class="btn-ghost btn-sm text-short" @click="removingToken = true">{{ t('common.delete') }}</button>
          </div>

          <div v-else class="mt-2.5 flex flex-wrap items-end gap-2">
            <UiField v-slot="{ id }" :label="t('telegram.token.fieldLabel')" class="w-64">
              <input
                :id="id"
                v-model="tokenInput"
                type="password"
                class="field"
                autocomplete="off"
                spellcheck="false"
                :placeholder="t('telegram.token.placeholder')"
                @keydown.enter="saveToken"
              />
            </UiField>
            <button
              class="btn-brand btn-sm"
              :disabled="!tokenInput.trim() || telegram.saving === 'token'"
              @click="saveToken"
            >
              {{ telegram.saving === 'token' ? t('common.saving') : t('common.save') }}
            </button>
            <button v-if="state?.configured" class="btn-ghost btn-sm" @click="replacingToken = false">
              {{ t('common.cancel') }}
            </button>
          </div>
        </li>

        <!-- Recipient -->
        <li class="px-4 py-3.5">
          <UiField
            v-slot="{ id }"
            :label="t('telegram.recipient.label')"
            :hint="t('telegram.recipient.hint')"
            class="max-w-xs"
          >
            <input
              :id="id"
              v-model="recipient"
              class="field"
              autocomplete="off"
              spellcheck="false"
              placeholder="username"
              @blur="saveRecipient"
              @keydown.enter="saveRecipient"
            />
          </UiField>
        </li>

        <!-- Link -->
        <li class="px-4 py-3.5">
          <template v-if="telegram.linked">
            <p class="text-sm">
              {{ t('telegram.link.linkedTo', { username: state?.recipient_username || '—' }) }}
            </p>
            <button class="btn-ghost btn-sm mt-2" :disabled="telegram.saving === 'unlink'" @click="onUnlink">
              {{ telegram.saving === 'unlink' ? t('common.saving') : t('telegram.link.unlink') }}
            </button>
          </template>
          <template v-else>
            <p class="text-sm">{{ t('telegram.link.label') }}</p>
            <p class="text-xs text-ink-muted mt-0.5 leading-relaxed">{{ t('telegram.link.hint') }}</p>

            <div v-if="telegram.linkUrl" class="mt-2.5 space-y-1.5">
              <a
                :href="telegram.linkUrl"
                target="_blank"
                rel="noopener"
                class="text-xs text-brand inline-flex items-center gap-1 hover:underline"
              >
                <UiIcon name="external" :size="12" />
                {{ t('telegram.link.openLink') }}
              </a>
              <p class="text-xs text-ink-faint">{{ t('telegram.link.waiting') }}</p>
            </div>
            <p v-else-if="telegram.linkPending" class="text-xs text-ink-faint mt-2">
              {{ t('telegram.link.waiting') }}
            </p>
            <button
              v-else
              class="btn-brand btn-sm mt-2.5"
              :disabled="!canLink || telegram.saving === 'link'"
              @click="onLink"
            >
              {{ telegram.saving === 'link' ? t('common.saving') : t('telegram.link.button') }}
            </button>
          </template>
        </li>

        <!-- Language -->
        <li class="px-4 py-3.5">
          <p class="text-sm mb-2">{{ t('telegram.language.label') }}</p>
          <div class="max-w-[12rem]">
            <UiSegmented v-model="language" :options="LANGUAGE_OPTIONS" size="sm" />
          </div>
        </li>

        <!-- Event groups -->
        <li class="px-4 py-3.5">
          <p class="text-sm mb-2.5">{{ t('telegram.groups.label') }}</p>
          <div class="space-y-3">
            <UiSwitch
              v-for="name in ALL_GROUPS"
              :key="name"
              :model-value="groupOn(name)"
              :label="t(`telegram.groups.${name}.label`)"
              :hint="t(`telegram.groups.${name}.description`)"
              :disabled="telegram.saving === `group:${name}`"
              @update:model-value="toggleGroup(name, $event)"
            />
          </div>
        </li>

        <!-- Test -->
        <li class="px-4 py-3.5">
          <div class="flex items-center gap-3">
            <button
              class="btn-ghost btn-sm"
              :disabled="!telegram.linked || telegram.saving === 'test'"
              @click="onTest"
            >
              <UiIcon name="bolt" :size="14" />
              {{ telegram.saving === 'test' ? t('common.saving') : t('telegram.test.button') }}
            </button>
            <span v-if="telegram.testResult === 'ok'" class="text-xs text-ok">{{ t('telegram.test.ok') }}</span>
            <span v-else-if="telegram.testResult === 'failed'" class="text-xs text-short">
              {{ telegram.testError || t('telegram.test.failed') }}
            </span>
          </div>
        </li>

        <!-- Health -->
        <li class="px-4 py-3.5">
          <p v-if="state?.configured && !state.health.notifier_running" class="text-xs text-short leading-relaxed">
            {{ t('telegram.health.notifierDown') }}
          </p>
          <template v-else-if="state?.configured">
            <p class="text-xs text-ink-muted">
              {{
                state.health.last_sent_at
                  ? t('telegram.health.lastDelivery', { when: dateTime(state.health.last_sent_at) })
                  : t('telegram.health.noDeliveryYet')
              }}
            </p>
            <p v-if="state.health.last_error" class="text-xs text-short mt-1">
              {{ t('telegram.health.lastError', { error: state.health.last_error }) }}
            </p>
          </template>
          <p class="text-xs text-ink-faint mt-2 leading-relaxed">{{ t('telegram.commandsHint') }}</p>
        </li>
      </ul>

      <p v-if="state?.updated_at" class="px-4 py-2.5 text-[0.7rem] text-ink-faint border-t border-line">
        {{ t('telegram.updated', { user: state.updated_by || '—', when: dateTime(state.updated_at) }) }}
      </p>
    </template>

    <SecurityStepUpDialog @confirmed="afterStepUp" />

    <UiModal v-model="removingToken" :title="t('telegram.token.removeTitle')" size="sm">
      <p class="text-sm leading-relaxed">{{ t('telegram.token.removeBody') }}</p>
      <template #footer>
        <div class="flex gap-2 justify-end">
          <button class="btn-ghost" @click="removingToken = false">{{ t('common.cancel') }}</button>
          <button class="btn-danger" @click="removeToken">{{ t('common.delete') }}</button>
        </div>
      </template>
    </UiModal>
  </UiCard>
</template>
