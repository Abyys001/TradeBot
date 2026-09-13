import { defineStore } from 'pinia'

/**
 * External signal sources, as the Settings card sees them (Q37).
 *
 * Shaped like `stores/telegram.ts`, and for the same reasons: writes that
 * matter come back 403 with `step_up_required`, which is not an error to show
 * — creating a source, rotating its secret and deleting one are sensitive
 * writes, the same tier as connecting an exchange account, so they raise the
 * shared password prompt and the caller replays once it is granted.
 *
 * **The secret lives here for exactly as long as one dialog.** The server
 * returns it once, in the response to the create or the rotate that produced
 * it, and never again — so this store holds it in `revealed` until the operator
 * dismisses it, and `forget()` is called on every navigation away. A value the
 * browser keeps is a value in a heap dump and a screenshot; the whole point of
 * write-only storage is lost if the panel decides to be helpful about it.
 */
export const useSignalsStore = defineStore('signals', {
  state: () => ({
    sources: [] as SignalSource[],
    events: [] as SignalEvent[],
    loading: true,
    /** Which write is in flight, so one row spins rather than the whole card. */
    saving: '' as string,
    error: '',
    /** The one-time secret, and which source it belongs to. Never persisted. */
    revealed: null as { id: number; secret: string } | null,
  }),

  getters: {
    /** Sources that can actually receive right now. */
    active: (state) => state.sources.filter((source) => source.enabled),
    /**
     * A source that is on but has never been signed is the one configuration
     * worth calling out on the card: the endpoint URL is then the only thing
     * between anyone who has seen it and this bot's positions.
     */
    unsigned: (state) =>
      state.sources.filter((source) => source.enabled && !source.require_signature),
  },

  actions: {
    async load() {
      this.loading = true
      try {
        this.sources = await useApi().signalSources()
        this.error = ''
      } catch (e: unknown) {
        this.error = errorMessage(e)
      } finally {
        this.loading = false
      }
    },

    async loadEvents(params: { source?: number; bot?: number } = {}) {
      try {
        this.events = await useApi().signalEvents(params)
      } catch (e: unknown) {
        this.error = errorMessage(e)
      }
    },

    /**
     * Returns false on a step-up refusal without setting `error` — the caller
     * keeps its retry and replays it once the prompt is satisfied.
     */
    async create(body: Record<string, unknown>): Promise<boolean> {
      this.saving = 'create'
      this.error = ''
      try {
        const created = await useApi().createSignalSource(body)
        this.sources = [...this.sources, created]
        this.revealed = { id: created.id, secret: created.secret_shown_once }
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

    async update(id: number, body: Record<string, unknown>): Promise<boolean> {
      this.saving = `update:${id}`
      this.error = ''
      try {
        const updated = await useApi().updateSignalSource(id, body)
        this.sources = this.sources.map((row) => (row.id === id ? updated : row))
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

    /**
     * A new secret. The old one stops working the instant this returns, which
     * is why it is one button rather than delete-and-recreate: recreating would
     * issue a new token too, and the sender would need reconfiguring on both
     * halves when only one of them leaked.
     */
    async rotate(id: number): Promise<boolean> {
      this.saving = `rotate:${id}`
      this.error = ''
      try {
        const rotated = await useApi().rotateSignalSecret(id)
        this.sources = this.sources.map((row) => (row.id === id ? rotated : row))
        this.revealed = { id, secret: rotated.secret_shown_once }
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

    async remove(id: number): Promise<boolean> {
      this.saving = `remove:${id}`
      this.error = ''
      try {
        await useApi().deleteSignalSource(id)
        this.sources = this.sources.filter((row) => row.id !== id)
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

    /** Drop the one-time secret. Called on dismiss and on leaving the page. */
    forget() {
      this.revealed = null
    },
  },
})
