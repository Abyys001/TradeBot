import { defineStore } from 'pinia'

/**
 * The optional security layer, as the Settings card sees it.
 *
 * Every control here is off until somebody turns it on, and the store keeps
 * that property visible rather than smoothing it away:
 *
 *   - `available` false means the environment pinned the whole layer off. The
 *     rows render locked instead of pretending to move.
 *   - a save posts **only what changed**. The server holds the tunables, the
 *     lock-out guards and the refusals; sending the whole policy back would
 *     make this file a second copy of them.
 *   - a refusal is kept as `error` next to the row, not swallowed. "Enrol an
 *     authenticator first" is the answer to the click, and hiding it would
 *     leave a switch that silently springs back.
 *
 * Nothing here is on the order-routing path — see `docs/security-plan.md` §1.
 */
export const useSecurityStore = defineStore('security', {
  state: () => ({
    policy: null as SecurityState | null,
    events: [] as SecurityEvent[],
    loading: true,
    /** The switch currently in flight, so one row spins rather than the card. */
    saving: '' as string,
    error: '',
    eventsLoading: false,
    /** Set when a write needs the password again; the modal watches it. */
    stepUpPending: false,
  }),

  getters: {
    /** False when `SECURITY_FEATURES=false` — every row is locked. */
    available: (state) => state.policy?.available ?? false,
    switches: (state) => state.policy?.switches ?? [],
    totp: (state) => state.policy?.totp ?? null,
    /**
     * The second factor cannot be armed until a device is enrolled *and* the
     * recovery codes are saved. The card disables the row and says why rather
     * than letting the click fail.
     */
    twoFactorReady: (state) => state.policy?.totp?.ready ?? false,
    /** How many controls are on — the card's one-line summary. */
    activeCount(state): number {
      if (!state.policy) return 0
      return (state.policy.switches ?? []).filter((name) => state.policy![name]).length
    },
  },

  actions: {
    async load() {
      try {
        this.policy = await useApi().securityPolicy()
        this.error = ''
      } catch (e: unknown) {
        this.error = errorMessage(e)
      } finally {
        this.loading = false
      }
    },

    /**
     * Write one setting. Returns whether it landed.
     *
     * A 403 carrying `step_up_required` is not an error to show — it is the
     * platform asking for the password again, so it raises the modal and the
     * caller retries after the grant.
     */
    async save(changes: Partial<SecurityPolicy>, key = ''): Promise<boolean> {
      this.saving = key || Object.keys(changes)[0] || 'policy'
      this.error = ''
      try {
        this.policy = await useApi().saveSecurityPolicy(changes)
        return true
      } catch (e: any) {
        if (e?.data?.code === 'step_up_required') {
          this.stepUpPending = true
          return false
        }
        this.error = errorMessage(e)
        // The switch the operator moved did not move on the server, so put the
        // card back to what is actually in force rather than leaving the row
        // showing a state nothing is enforcing.
        await this.load()
        return false
      } finally {
        this.saving = ''
      }
    },

    toggle(name: SecuritySwitch, on: boolean) {
      return this.save({ [name]: on } as Partial<SecurityPolicy>, name)
    },

    async loadEvents(limit = 50) {
      this.eventsLoading = true
      try {
        this.events = (await useApi().securityEvents(limit)).events
      } catch {
        this.events = []
      } finally {
        this.eventsLoading = false
      }
    },

    /** Re-enter the password. On success the grant is in the session cookie. */
    async confirmPassword(password: string): Promise<string> {
      try {
        const result = await useApi().stepUp(password)
        if (this.policy) this.policy.step_up_seconds_left = result.seconds_left
        this.stepUpPending = false
        return ''
      } catch (e: unknown) {
        return errorMessage(e)
      }
    },

    /** Keep the card's TOTP block in step after an enrolment step. */
    applyTotp(totp: TotpState) {
      if (this.policy) this.policy.totp = totp
    },
  },
})
