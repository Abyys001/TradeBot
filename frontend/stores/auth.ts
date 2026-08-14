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

    async login(username: string, password: string) {
      this.pending = true
      this.error = ''
      try {
        // Fetch a CSRF cookie first — Django rejects the login POST without it.
        await useApi().csrf()
        const user = await useApi().login(username, password)
        this.authenticated = true
        this.username = user.username ?? ''
        this.isStaff = user.is_staff ?? false
        this.canSeeHidden = user.can_see_hidden ?? false
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
