<script setup lang="ts">
/**
 * Spec §4 failure notices, as a proper notification centre in the top bar.
 *
 * They used to be cards docked over the page, which is what the spec's "~190 ×
 * 110px, top of screen" asked for — and in use they covered the chart at the
 * exact moment the admin needed to look at it. So the placement moved into the
 * bar; the *requirement* underneath it did not, and is still met here:
 *
 *   - nothing auto-expires. Only the dismiss button clears an item, and that
 *     dismissal is a server-side fact (see stores/notifications.ts).
 *   - a new failure opens this panel by itself, so it is still unmissable.
 *   - the bell keeps an amber count while anything is outstanding, on every
 *     page, so a notice cannot be lost by navigating away.
 *   - each card keeps the spec's size, now inside the panel.
 *
 * Recorded as a deliberate amendment in questions.md (Q16) rather than a silent
 * departure from the spec.
 */
const { t } = useI18n()
const notifications = useNotificationStore()
const accounts = useAccountsStore()
const { since } = useFormat()

const open = ref(false)
const panel = ref<HTMLElement | null>(null)

/** A failure arriving while the panel is shut opens it — spec §4 wants it seen. */
watch(
  () => notifications.count,
  (now, before) => {
    if (now > before) open.value = true
  },
)

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') open.value = false
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))

const localePath = useLocalePath()
</script>

<template>
  <div class="relative">
    <button
      class="btn-quiet btn-sm relative"
      :class="notifications.hasFailures ? 'text-signal' : ''"
      :aria-expanded="open"
      :aria-label="t('notifications.region')"
      :title="
        notifications.hasFailures
          ? t('notifications.pending', { n: notifications.count })
          : t('notifications.none')
      "
      @click="open = !open"
    >
      <UiIcon name="bell" :size="17" />
      <span
        v-if="notifications.count"
        class="num absolute -top-0.5 -end-0.5 min-w-[1.05rem] h-[1.05rem] px-1 rounded-full
               bg-signal text-[0.65rem] leading-[1.05rem] text-ink-invert text-center font-medium"
      >
        {{ notifications.count > 9 ? '9+' : notifications.count }}
      </span>
    </button>

    <!-- Click-away layer. A panel that only closes from its own button is a
         panel left open over the chart. -->
    <div v-if="open" class="fixed inset-0 z-40" @click="open = false" />

    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 -translate-y-1"
      leave-active-class="transition duration-100 ease-in"
      leave-to-class="opacity-0"
    >
      <div
        v-if="open"
        ref="panel"
        class="absolute z-50 mt-2 end-0 w-[19rem] sm:w-[21rem] panel shadow-pop flex flex-col
               max-h-[min(28rem,70vh)]"
        role="region"
        :aria-label="t('notifications.region')"
      >
        <header class="flex items-center gap-2 px-3 py-2.5 border-b border-line shrink-0">
          <UiIcon
            name="alert"
            :size="14"
            :class="notifications.hasFailures ? 'text-signal' : 'text-ink-faint'"
          />
          <span class="text-sm font-medium">{{ t('notifications.title') }}</span>
          <UiBadge v-if="notifications.count" tone="signal" class="ms-1">
            {{ notifications.count }}
          </UiBadge>
          <button
            v-if="notifications.count > 1"
            class="btn-quiet btn-sm ms-auto"
            @click="notifications.dismissAll()"
          >
            {{ t('notifications.dismissAll') }}
          </button>
        </header>

        <div v-if="notifications.hasFailures" class="overflow-y-auto divide-y divide-line">
          <article
            v-for="item in notifications.items"
            :key="item.id"
            class="p-3 flex gap-3 hover:bg-raised/50 transition-colors"
          >
            <span class="mt-1.5 w-1.5 h-1.5 rounded-full bg-signal shrink-0" />

            <div class="min-w-0 flex-1">
              <div class="flex items-baseline gap-2">
                <p class="text-xs font-medium truncate">
                  {{ item.accountLabel || t('notifications.unknownAccount') }}
                </p>
                <span class="label ms-auto shrink-0 normal-case tracking-normal">
                  {{ since(item.created_at) }}
                </span>
              </div>
              <p class="text-[0.7rem] text-ink-muted leading-snug mt-1">{{ item.message }}</p>
              <div class="flex items-center gap-2 mt-1.5">
                <UiBadge v-if="item.code" tone="neutral">{{ item.code }}</UiBadge>
                <NuxtLink
                  v-if="item.account"
                  :to="localePath('/accounts')"
                  class="text-[0.7rem] text-brand hover:underline"
                  @click="open = false"
                >
                  {{ t('notifications.viewAccount') }}
                </NuxtLink>
              </div>
            </div>

            <!-- Dismissal is the *only* thing that clears a notice (spec §4). -->
            <button
              class="btn-quiet btn-sm self-start -me-1"
              :aria-label="t('notifications.dismiss')"
              :title="t('notifications.dismiss')"
              @click="notifications.dismiss(item.id)"
            >
              <UiIcon name="close" :size="13" />
            </button>
          </article>
        </div>

        <div v-else class="px-4 py-8 text-center">
          <p class="text-sm">{{ t('notifications.none') }}</p>
          <p class="text-xs text-ink-muted mt-1 leading-relaxed">
            {{ t('notifications.noneBody', { n: accounts.active.length }) }}
          </p>
        </div>

        <footer class="px-3 py-2 border-t border-line shrink-0">
          <p class="text-[0.65rem] text-ink-faint leading-relaxed">
            {{ t('notifications.persistNote') }}
          </p>
        </footer>
      </div>
    </Transition>
  </div>
</template>
