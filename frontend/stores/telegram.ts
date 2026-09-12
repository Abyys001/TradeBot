import { defineStore } from 'pinia'

/**
 * Telegram delivery, as the Settings card sees it.
 *
 * Shaped like `stores/security.ts`: a save posts only what changed, and a
 * 403 carrying `step_up_required` is not an error to show — token changes,
 * linking and unlinking the chat are sensitive writes, same tier as
 * connecting an account, so they raise the same password prompt. That prompt
 * is the security layer's own (`useSecurityStore().stepUpPending`); this
 * store only remembers *what* to retry once it is granted, which lives as a
 * closure on the caller since the four writes here — settings, token, link,
 * unlink — do not share one shape the way the security switches do.
 */
export const useTelegramStore = defineStore('telegram', {
  state: () => ({
    state: null as TelegramState | null,
    loading: true,
    /** The write currently in flight, so one control spins rather than the card. */
    saving: '' as string,
    error: '',
    linkUrl: '',
    linkExpiresAt: '',
    poller: null as ReturnType<typeof setInterval> | null,
    testResult: '' as 'ok' | 'failed' | '',
    testError: '',
  }),

  getters: {
    configured: (state) => state.state?.configured ?? false,
    linked: (state) => state.state?.linked ?? false,
    linkPending: (state) => state.state?.link_pending ?? false,
    groups: (state) => state.state?.groups ?? [],
    allGroups: (state) => state.state?.all_groups ?? [],
  },

  actions: {
    async load() {
      try {
        this.state = await useApi().telegramState()
        this.error = ''
      } catch (e: unknown) {
        this.error = errorMessage(e)
      } finally {
        this.loading = false
      }
    },

    /**
     * A 403 with `step_up_required` raises the shared password prompt and
     * returns false without touching `error` — the caller keeps its retry
     * and replays it once `afterStepUp` fires.
     */
    async save(
      changes: Partial<Pick<TelegramState, 'enabled' | 'recipient_username' | 'language' | 'groups'>>,
      key = '',
    ): Promise<boolean> {
      this.saving = key || Object.keys(changes)[0] || 'state'
      this.error = ''
      try {
        this.state = await useApi().saveTelegram(changes)
        return true
      } catch (e: any) {
        if (e?.data?.code === 'step_up_required') {
          useSecurityStore().stepUpPending = true
          return false
        }
        this.error = errorMessage(e)
        return false
      } finally {
        this.saving = ''
      }
    },

    /** An empty string removes the stored token. Never prefilled from here —
        the server does not send the token back for this to hold. */
    async saveToken(token: string): Promise<boolean> {
      this.saving = 'token'
      this.error = ''
      try {
        this.state = await useApi().saveTelegramToken(token)
        return true
      } catch (e: any) {
        if (e?.data?.code === 'step_up_required') {
          useSecurityStore().stepUpPending = true
          return false
        }
        this.error = errorMessage(e)
        return false
      } finally {
        this.saving = ''
      }
    },

    async link(): Promise<boolean> {
      this.saving = 'link'
      this.error = ''
      try {
        const result = await useApi().telegramLink()
        this.state = result
        this.linkUrl = result.link_url
        this.linkExpiresAt = result.link_expires_at
        if (import.meta.client) window.open(result.link_url, '_blank', 'noopener')
        this.startPolling()
        return true
      } catch (e: any) {
        if (e?.data?.code === 'step_up_required') {
          useSecurityStore().stepUpPending = true
          return false
        }
        this.error = errorMessage(e)
        return false
      } finally {
        this.saving = ''
      }
    },

    async unlink(): Promise<boolean> {
      this.saving = 'unlink'
      this.error = ''
      try {
        this.state = await useApi().telegramUnlink()
        this.linkUrl = ''
        this.linkExpiresAt = ''
        this.stopPolling()
        return true
      } catch (e: any) {
        if (e?.data?.code === 'step_up_required') {
          useSecurityStore().stepUpPending = true
          return false
        }
        this.error = errorMessage(e)
        return false
      } finally {
        this.saving = ''
      }
    },

    async test() {
      this.saving = 'test'
      this.testResult = ''
      this.testError = ''
      try {
        await useApi().telegramTest()
        this.testResult = 'ok'
      } catch (e: unknown) {
        this.testResult = 'failed'
        this.testError = errorMessage(e)
      } finally {
        this.saving = ''
      }
    },

    /** Every 3s until linked, or the code expires — whichever comes first. */
    startPolling() {
      this.stopPolling()
      this.poller = setInterval(async () => {
        if (this.linkExpiresAt && Date.now() > new Date(this.linkExpiresAt).getTime()) {
          this.stopPolling()
          return
        }
        try {
          this.state = await useApi().telegramState()
          if (this.state.linked) {
            this.linkUrl = ''
            this.linkExpiresAt = ''
            this.stopPolling()
          }
        } catch {
          // One failed poll is not worth surfacing — the next one retries.
        }
      }, 3000)
    },

    stopPolling() {
      if (this.poller) clearInterval(this.poller)
      this.poller = null
    },
  },
})
