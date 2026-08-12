export default defineNuxtConfig({
  buildDir: process.env.NUXT_BUILD_DIR || '.nuxt',
  compatibilityDate: '2025-01-01',
  devtools: { enabled: true },
  modules: ['@nuxtjs/tailwindcss', '@pinia/nuxt', '@nuxtjs/i18n'],
  css: ['~/assets/css/main.css'],

  // Q2: English complete first, Persian second. Every string goes through i18n
  // from day one so Persian is a translation pass, not a rebuild. `dir` is
  // declared per-locale now so RTL is never retrofitted.
  i18n: {
    strategy: 'prefix_except_default',
    defaultLocale: 'en',
    locales: [
      { code: 'en', language: 'en-US', dir: 'ltr', name: 'English', file: 'en.json' },
      { code: 'fa', language: 'fa-IR', dir: 'rtl', name: 'فارسی', file: 'fa.json' },
    ],
    lazy: true,
    detectBrowserLanguage: { useCookie: true, cookieKey: 'locale', redirectOn: 'root' },
  },

  runtimeConfig: {
    // Server-side only: where the Nuxt server forwards /api/** to. The browser
    // never sees this, so it can be a Docker-internal hostname.
    apiProxyTarget: process.env.NUXT_API_PROXY_TARGET || 'http://localhost:8000/api',
    public: {
      // Same-origin on purpose — see server/api/[...path].ts.
      apiBase: '/api',
      wsBase: process.env.NUXT_PUBLIC_WS_BASE || '',
    },
  },

  // The WebSocket rides the same origin as everything else. nitro forwards the
  // upgrade to Channels, so the browser never needs to reach :8000 directly.
  routeRules: {
    '/ws/**': { proxy: `${process.env.NUXT_WS_PROXY_TARGET || 'http://localhost:8000'}/ws/**` },
  },

  app: {
    head: {
      // No static title: app.vue owns it through titleTemplate, and setting one
      // here makes every page render "WalletManager CopyTrader · WalletManager".
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
        { name: 'apple-mobile-web-app-title', content: 'WalletManager' },
        { name: 'application-name', content: 'WalletManager' },
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
