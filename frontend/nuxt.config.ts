export default defineNuxtConfig({
  buildDir: process.env.NUXT_BUILD_DIR || '.nuxt',
  compatibilityDate: '2025-01-01',
  devtools: { enabled: true },
  modules: ['@nuxtjs/tailwindcss', '@pinia/nuxt', '@nuxtjs/i18n'],
  css: ['~/assets/css/main.css'],

  // Q2: English complete first, Persian second. Every string goes through i18n
  // from day one so Persian is a translation pass, not a rebuild. `dir` is
  // declared per-locale now so RTL is never retrofitted.
  //
  // ar/es/de/tr are landing-complete: the whole landing tree and core chrome
  // are translated, and anything left untranslated falls back to English (the
  // instrument UI stays English-first — the panel is operated in en/fa).
  i18n: {
    strategy: 'prefix_except_default',
    defaultLocale: 'en',
    fallbackLocale: 'en',
    locales: [
      { code: 'en', language: 'en-US', dir: 'ltr', name: 'English', file: 'en.json' },
      { code: 'fa', language: 'fa-IR', dir: 'rtl', name: 'فارسی', file: 'fa.json' },
      { code: 'ar', language: 'ar-SA', dir: 'rtl', name: 'العربية', file: 'ar.json' },
      { code: 'es', language: 'es-ES', dir: 'ltr', name: 'Español', file: 'es.json' },
      { code: 'de', language: 'de-DE', dir: 'ltr', name: 'Deutsch', file: 'de.json' },
      { code: 'tr', language: 'tr-TR', dir: 'ltr', name: 'Türkçe', file: 'tr.json' },
    ],
    lazy: true,
    detectBrowserLanguage: { useCookie: true, cookieKey: 'locale', redirectOn: 'root' },
  },

  runtimeConfig: {
    // Server-side only: where the Nuxt server forwards /api/** to. The browser
    // never sees this, so it can be a Docker-internal hostname.
    apiProxyTarget: process.env.NUXT_API_PROXY_TARGET || 'http://localhost:8000/api',
    // The same, for the live channel — see server/routes/ws/[...].ts.
    wsProxyTarget: process.env.NUXT_WS_PROXY_TARGET || 'ws://localhost:8000',
    public: {
      // Same-origin on purpose — see server/api/[...path].ts.
      apiBase: '/api',
      // Almost always empty now: the panel derives wss://<its own host>/ws/
      // and the relay below carries it. Kept as an escape hatch for a
      // deployment that puts Channels on a separate hostname, and ignored by
      // stores/live.ts when it names a loopback the browser cannot reach.
      wsBase: process.env.NUXT_PUBLIC_WS_BASE || '',
    },
  },

  // Still no /ws route *rule*: `routeRules[].proxy` is an h3 `proxyRequest`,
  // which forwards the HTTP request and drops the `Upgrade` handshake. That is
  // what left the socket stuck on "connecting" with both latency readings blank.
  //
  // A WebSocket *handler* is a different mechanism — nitro hands upgrades to
  // the worker, which is where server/routes/ws/[...].ts runs — so the panel
  // now carries its own socket on its own origin, in dev and in the built
  // server alike. Caddy still short-circuits /ws straight to Channels in the
  // production stack; that is one hop fewer, not a different contract.
  nitro: {
    experimental: { websocket: true },
  },

  app: {
    head: {
      // No static title: app.vue owns it through titleTemplate, and setting one
      // here makes every page render "TradeBot · TradeBot".
      // viewport-fit=cover is what makes env(safe-area-inset-*) non-zero, which
      // the mobile tab bar and the page gutters rely on to clear the notch and
      // the home indicator.
      meta: [
        { name: 'viewport', content: 'width=device-width, initial-scale=1, viewport-fit=cover' },
        // iOS installs from Safari's "Add to Home Screen" and reads these
        // rather than the manifest: without them the panel opens in a browser
        // chrome with a screenshot as its icon.
        { name: 'mobile-web-app-capable', content: 'yes' },
        { name: 'apple-mobile-web-app-capable', content: 'yes' },
        { name: 'apple-mobile-web-app-status-bar-style', content: 'black-translucent' },
        { name: 'apple-mobile-web-app-title', content: 'TradeBot' },
        { name: 'application-name', content: 'TradeBot' },
      ],
      link: [
        // SVG first for the browsers that take it (any size, theme-aware), .ico
        // as the fallback, and the 180px PNG for iOS which takes neither.
        { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
        { rel: 'alternate icon', type: 'image/x-icon', href: '/favicon.ico', sizes: '48x48' },
        { rel: 'apple-touch-icon', href: '/apple-touch-icon.png', sizes: '180x180' },
        { rel: 'manifest', href: '/manifest.webmanifest' },
      ],
      htmlAttrs: { 'data-theme': 'dark' },
    },
    pageTransition: { name: 'page', mode: 'out-in' },
  },
})
