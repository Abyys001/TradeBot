import { defineStore } from 'pinia'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    username: '' as string,
    isStaff: false,
    /**
     * Told to us by the server, never inferred from the username in the browser.
     * It only decides whether the hidden toggle and the hidden badge render;
     * the accounts, balances, positions, history and socket frames a session
     * receives are filtered server-side, so this being wrong shows or omits a
     * checkbox and reveals nothing.
     */
    canSeeHidden: false,
    authenticated: false,
    checked: false,
    error: '',
    pending: false,
    /**
     * A sign-in that got past the password and is waiting on a code.
     *
     * The challenge identifies it, not the username — the password was already
     * accepted, and re-posting it at the second step would mean holding it in
     * the browser for the length of a code entry. Empty whenever the second
     * factor is off, which is the default.
     */
    challenge: '',
    recoveryAvailable: false,
  }),

  actions: {
    /** Ask the server who we are. Cheap, and the only source of truth. */
    async check() {
      try {
        const user = await useApi().me()
        this.authenticated = user.authenticated
        this.username = user.username ?? ''
        this.isStaff = user.is_staff ?? false
        this.canSeeHidden = user.can_see_hidden ?? false
      } catch {
        this.authenticated = false
      } finally {
        this.checked = true
      }
    },

    /**
     * Returns true only when there is a session. A challenged sign-in returns
     * false with `challenge` set — the password was right and the form has a
     * second step to show, which is a different thing from a refusal.
     */
    async login(username: string, password: string, remember = false) {
      this.pending = true
      this.error = ''
      this.challenge = ''
      try {
        // Fetch a CSRF cookie first — Django rejects the login POST without it.
        await useApi().csrf()
        const user = await useApi().login(username, password, remember)
        if (user.mfa_required) {
          this.challenge = user.challenge ?? ''
          this.recoveryAvailable = Boolean(user.recovery_available)
          return false
        }
        this.adopt(user)
        return true
      } catch (e: any) {
        // A rejected credential and an unreachable backend are different
        // problems and must not read the same: one is a typo, the other is an
        // outage, and telling them apart saves ten minutes of retyping.
        this.error = e?.status
          ? errorMessage(e)
          : 'Could not reach the server. Check that the API is running.'
        return false
      } finally {
        this.pending = false
      }
    },

    /** The second half of a challenged sign-in: a code from the app, or a
        recovery code. Both go in the same field — the server tells them apart. */
    async mfa(code: string, remember = false) {
      this.pending = true
      this.error = ''
      try {
        this.adopt(await useApi().mfa(this.challenge, code, remember))
        this.challenge = ''
        return true
      } catch (e: any) {
        // An expired challenge is not a wrong code: the form has to go back to
        // the password rather than let the operator retype a code forever.
        if (e?.data?.code === 'challenge_expired') this.challenge = ''
        this.error = e?.status
          ? errorMessage(e)
          : 'Could not reach the server. Check that the API is running.'
        return false
      } finally {
        this.pending = false
      }
    },

    /** Drop the half-finished sign-in and go back to the password. */
    cancelMfa() {
      this.challenge = ''
      this.error = ''
    },

    adopt(user: SessionUser) {
      this.authenticated = true
      this.username = user.username ?? ''
      this.isStaff = user.is_staff ?? false
      this.canSeeHidden = user.can_see_hidden ?? false
    },

    async logout() {
      try {
        await useApi().logout()
      } finally {
        this.$reset()
        this.checked = true
        // Everything downstream is per-session state; leaving it behind would
        // show the next sign-in the previous operator's accounts and trades.
        useAccountsStore().$reset()
        useTradingStore().$reset()
        useNotificationStore().$reset()
        useLiveStore().disconnect()
      }
    },
  },
})
