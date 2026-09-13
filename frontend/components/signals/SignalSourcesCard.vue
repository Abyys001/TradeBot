<script setup lang="ts">
/**
 * External strategies allowed to move this platform's positions (Q37).
 *
 * The card exists because the endpoint it configures is the only
 * unauthenticated write surface on the platform. Everything that normally
 * comes from the admin's session — who is calling, whether they may — has to
 * be carried inside each request instead, and this is where those controls are
 * set: the shared secret, the replay window, the address allowlist.
 *
 * Three things it deliberately does:
 *
 *  - **Shows the secret exactly once.** The server returns it in the response
 *    to the create or rotate that produced it and never again. Copy it now or
 *    rotate it later; there is no third option, and offering one would undo
 *    the point of storing it write-only.
 *  - **Says what a source may not do.** A sender cannot choose the pair, the
 *    size, the leverage or the account — all of that is the bot's, and the bot
 *    is named on the row. That is the sentence that makes the endpoint
 *    reviewable at a glance.
 *  - **Calls out an unsigned source that is switched on**, because then the
 *    URL is the only thing standing between anyone who has seen it and this
 *    bot's positions. The server already refuses that combination on a live
 *    bot; on a paper one it is legal and worth saying out loud.
 */
const { t } = useI18n()
const { dateTime } = useFormat()
const signals = useSignalsStore()
const bots = useBotsStore()

onMounted(async () => {
  await Promise.all([signals.load(), bots.load()])
})
// A one-time secret must not outlive the page that revealed it.
onUnmounted(() => signals.forget())

/** The last write that hit step-up, replayed once the password is confirmed. */
const retry = ref<(() => unknown) | null>(null)

async function afterStepUp() {
  if (!retry.value) return
  const fn = retry.value
  retry.value = null
  await fn()
}

/**
 * Only a webhook bot may be bound. A Pine bot already has something deciding
 * its positions, and a bot driven by both would have two.
 */
const bindable = computed(() => bots.bots.filter((bot) => bot.signal_source === 'webhook'))

const adding = ref(false)
const form = reactive({ name: '', bot: null as number | null })

async function create() {
  if (!form.name.trim() || form.bot === null) return
  retry.value = () => create()
  const ok = await signals.create({ name: form.name.trim(), bot: form.bot })
  if (ok) {
    adding.value = false
    form.name = ''
    form.bot = null
  }
}

async function toggle(source: SignalSource, enabled: boolean) {
  retry.value = () => toggle(source, enabled)
  await signals.update(source.id, { enabled })
}

async function rotate(source: SignalSource) {
  retry.value = () => rotate(source)
  await signals.rotate(source.id)
}

async function remove(source: SignalSource) {
  retry.value = () => remove(source)
  await signals.remove(source.id)
}

/** The full URL a sender posts to — the panel's own origin, not the API's. */
function fullUrl(source: SignalSource): string {
  const origin = import.meta.client ? window.location.origin : ''
  return `${origin}${source.endpoint}`
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // Clipboard access can be refused outright (an insecure origin, a denied
    // permission). The value is on screen and selectable either way, so a
    // failed copy is not worth an error banner.
  }
}
</script>

<template>
  <UiCard :title="t('signals.title')" :hint="t('signals.hint')" flush>
    <template #actions>
      <UiBadge v-if="signals.active.length" tone="ok" dot>
        {{ t('signals.status.active', { n: signals.active.length }) }}
      </UiBadge>
      <UiBadge v-else tone="neutral">{{ t('signals.status.none') }}</UiBadge>
    </template>

    <div v-if="signals.loading" class="p-4 space-y-3">
      <div v-for="i in 3" :key="i" class="skeleton h-10" />
    </div>

    <template v-else>
      <p v-if="signals.error" class="px-4 py-2.5 alert text-xs rounded-none border-x-0 border-t-0">
        {{ signals.error }}
      </p>

      <!-- The one-time secret. Loud, because there is no second chance. -->
      <div
        v-if="signals.revealed"
        class="px-4 py-3.5 border-b border-line bg-signal/5"
      >
        <p class="text-sm font-medium">{{ t('signals.secret.title') }}</p>
        <p class="text-xs text-ink-muted mt-0.5 leading-relaxed">
          {{ t('signals.secret.help') }}
        </p>
        <div class="mt-2.5 flex flex-wrap items-center gap-2">
          <code class="num text-xs px-2 py-1.5 rounded-md bg-sunken border border-line break-all">
            {{ signals.revealed.secret }}
          </code>
          <button class="btn-ghost btn-sm" @click="copy(signals.revealed!.secret)">
            {{ t('common.copy') }}
          </button>
          <button class="btn-brand btn-sm" @click="signals.forget()">
            {{ t('signals.secret.saved') }}
          </button>
        </div>
      </div>

      <ul v-if="signals.sources.length" class="divide-y divide-line">
        <li v-for="source in signals.sources" :key="source.id" class="px-4 py-3.5">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="text-sm font-medium truncate">{{ source.name }}</p>
              <!-- The bot is the whole security story: it owns the pair, the
                   leverage and the size, and the sender owns none of them. -->
              <p class="text-xs text-ink-muted mt-0.5">
                {{ t('signals.boundTo', { bot: source.bot_name, symbol: source.symbol }) }}
              </p>
            </div>
            <UiSwitch
              :model-value="source.enabled"
              :disabled="signals.saving === `update:${source.id}`"
              @update:model-value="toggle(source, $event)"
            />
          </div>

          <div class="mt-2.5 flex flex-wrap items-center gap-2 text-xs">
            <code class="num px-2 py-1 rounded-md bg-sunken border border-line break-all">
              {{ fullUrl(source) }}
            </code>
            <button class="btn-ghost btn-sm" @click="copy(fullUrl(source))">
              {{ t('common.copy') }}
            </button>
          </div>

          <div class="mt-2 flex flex-wrap items-center gap-2 text-xs">
            <UiBadge v-if="source.require_signature" tone="ok">
              {{ t('signals.signed', { fp: source.secret_fingerprint }) }}
            </UiBadge>
            <UiBadge v-else tone="signal">{{ t('signals.unsigned') }}</UiBadge>
            <UiBadge v-if="source.last_accepted_at" tone="neutral">
              {{ t('signals.lastAccepted', { when: dateTime(source.last_accepted_at) }) }}
            </UiBadge>
            <UiBadge v-else-if="source.last_seen_at" tone="neutral">
              {{ t('signals.lastSeen', { when: dateTime(source.last_seen_at) }) }}
            </UiBadge>
            <UiBadge v-else tone="neutral">{{ t('signals.neverUsed') }}</UiBadge>
            <button
              class="btn-ghost btn-sm"
              :disabled="signals.saving === `rotate:${source.id}`"
              @click="rotate(source)"
            >
              {{ t('signals.rotate') }}
            </button>
            <button
              class="btn-ghost btn-sm text-short"
              :disabled="signals.saving === `remove:${source.id}`"
              @click="remove(source)"
            >
              {{ t('common.delete') }}
            </button>
          </div>

          <p v-if="source.enabled && !source.require_signature" class="alert mt-2.5 p-2 text-xs leading-relaxed">
            {{ t('signals.unsignedWarning') }}
          </p>
        </li>
      </ul>

      <p v-else class="px-4 py-3.5 text-xs text-ink-muted leading-relaxed">
        {{ t('signals.empty') }}
      </p>

      <div class="px-4 py-3.5 border-t border-line">
        <div v-if="!adding">
          <button
            class="btn-ghost btn-sm"
            :disabled="!bindable.length"
            @click="adding = true"
          >
            {{ t('signals.add') }}
          </button>
          <!-- Said here rather than as a disabled-button mystery: a source has
               nowhere to point until a bot exists that takes external signals. -->
          <p v-if="!bindable.length" class="text-xs text-ink-muted mt-1.5 leading-relaxed">
            {{ t('signals.noWebhookBots') }}
          </p>
        </div>

        <div v-else class="flex flex-wrap items-end gap-2">
          <UiField v-slot="{ id }" :label="t('signals.form.name')" class="w-56">
            <input :id="id" v-model="form.name" class="field" spellcheck="false" />
          </UiField>
          <UiField v-slot="{ id }" :label="t('signals.form.bot')" class="w-56">
            <select :id="id" v-model="form.bot" class="field">
              <option :value="null" disabled>{{ t('signals.form.pickBot') }}</option>
              <option v-for="bot in bindable" :key="bot.id" :value="bot.id">
                {{ bot.name }} · {{ bot.symbol }}
              </option>
            </select>
          </UiField>
          <button
            class="btn-brand btn-sm"
            :disabled="!form.name.trim() || form.bot === null || signals.saving === 'create'"
            @click="create"
          >
            {{ signals.saving === 'create' ? t('common.saving') : t('common.create') }}
          </button>
          <button class="btn-ghost btn-sm" @click="adding = false">
            {{ t('common.cancel') }}
          </button>
        </div>
      </div>
    </template>

    <SecurityStepUpDialog @confirmed="afterStepUp" />
  </UiCard>
</template>
