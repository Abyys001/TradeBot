
import type { DefineComponent, SlotsType } from 'vue'
type IslandComponent<T> = DefineComponent<{}, {refresh: () => Promise<void>}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, SlotsType<{ fallback: { error: unknown } }>> & T

type HydrationStrategies = {
  hydrateOnVisible?: IntersectionObserverInit | true
  hydrateOnIdle?: number | true
  hydrateOnInteraction?: keyof HTMLElementEventMap | Array<keyof HTMLElementEventMap> | true
  hydrateOnMediaQuery?: string
  hydrateAfter?: number
  hydrateWhen?: boolean
  hydrateNever?: true
}
type LazyComponent<T> = DefineComponent<HydrationStrategies, {}, {}, {}, {}, {}, {}, { hydrated: () => void }> & T

interface _GlobalComponents {
  FailureNotifications: typeof import("../../components/FailureNotifications.vue")['default']
  FanOutDiagram: typeof import("../../components/FanOutDiagram.vue")['default']
  AccountsConnectForm: typeof import("../../components/accounts/ConnectForm.vue")['default']
  AppLocaleToggle: typeof import("../../components/app/LocaleToggle.vue")['default']
  AppMobileNav: typeof import("../../components/app/MobileNav.vue")['default']
  AppSidebar: typeof import("../../components/app/Sidebar.vue")['default']
  AppThemeToggle: typeof import("../../components/app/ThemeToggle.vue")['default']
  AppTopbar: typeof import("../../components/app/Topbar.vue")['default']
  DashboardAlerts: typeof import("../../components/dashboard/Alerts.vue")['default']
  DashboardOpenPosition: typeof import("../../components/dashboard/OpenPosition.vue")['default']
  DashboardRecentTrades: typeof import("../../components/dashboard/RecentTrades.vue")['default']
  TerminalAccountsPane: typeof import("../../components/terminal/AccountsPane.vue")['default']
  TerminalFanOutSummary: typeof import("../../components/terminal/FanOutSummary.vue")['default']
  TerminalPositionBar: typeof import("../../components/terminal/PositionBar.vue")['default']
  TerminalTicket: typeof import("../../components/terminal/Ticket.vue")['default']
  UiBadge: typeof import("../../components/ui/Badge.vue")['default']
  UiBarSeries: typeof import("../../components/ui/BarSeries.vue")['default']
  UiCard: typeof import("../../components/ui/Card.vue")['default']
  UiColumnChart: typeof import("../../components/ui/ColumnChart.vue")['default']
  UiEmpty: typeof import("../../components/ui/Empty.vue")['default']
  UiField: typeof import("../../components/ui/Field.vue")['default']
  UiIcon: typeof import("../../components/ui/Icon.vue")['default']
  UiModal: typeof import("../../components/ui/Modal.vue")['default']
  UiSegmented: typeof import("../../components/ui/Segmented.vue")['default']
  UiStat: typeof import("../../components/ui/Stat.vue")['default']
  UiSwitch: typeof import("../../components/ui/Switch.vue")['default']
  UiTrendChart: typeof import("../../components/ui/TrendChart.vue")['default']
  NuxtWelcome: typeof import("../../node_modules/nuxt/dist/app/components/welcome.vue")['default']
  NuxtLayout: typeof import("../../node_modules/nuxt/dist/app/components/nuxt-layout")['default']
  NuxtErrorBoundary: typeof import("../../node_modules/nuxt/dist/app/components/nuxt-error-boundary.vue")['default']
  ClientOnly: typeof import("../../node_modules/nuxt/dist/app/components/client-only")['default']
  DevOnly: typeof import("../../node_modules/nuxt/dist/app/components/dev-only")['default']
  ServerPlaceholder: typeof import("../../node_modules/nuxt/dist/app/components/server-placeholder")['default']
  NuxtLink: typeof import("../../node_modules/nuxt/dist/app/components/nuxt-link")['default']
  NuxtLoadingIndicator: typeof import("../../node_modules/nuxt/dist/app/components/nuxt-loading-indicator")['default']
  NuxtTime: typeof import("../../node_modules/nuxt/dist/app/components/nuxt-time.vue")['default']
  NuxtRouteAnnouncer: typeof import("../../node_modules/nuxt/dist/app/components/nuxt-route-announcer")['default']
  NuxtImg: typeof import("../../node_modules/nuxt/dist/app/components/nuxt-stubs")['NuxtImg']
  NuxtPicture: typeof import("../../node_modules/nuxt/dist/app/components/nuxt-stubs")['NuxtPicture']
  NuxtLinkLocale: typeof import("../../node_modules/@nuxtjs/i18n/dist/runtime/components/NuxtLinkLocale")['default']
  SwitchLocalePathLink: typeof import("../../node_modules/@nuxtjs/i18n/dist/runtime/components/SwitchLocalePathLink")['default']
  NuxtPage: typeof import("../../node_modules/nuxt/dist/pages/runtime/page")['default']
  NoScript: typeof import("../../node_modules/nuxt/dist/head/runtime/components")['NoScript']
  Link: typeof import("../../node_modules/nuxt/dist/head/runtime/components")['Link']
  Base: typeof import("../../node_modules/nuxt/dist/head/runtime/components")['Base']
  Title: typeof import("../../node_modules/nuxt/dist/head/runtime/components")['Title']
  Meta: typeof import("../../node_modules/nuxt/dist/head/runtime/components")['Meta']
  Style: typeof import("../../node_modules/nuxt/dist/head/runtime/components")['Style']
  Head: typeof import("../../node_modules/nuxt/dist/head/runtime/components")['Head']
  Html: typeof import("../../node_modules/nuxt/dist/head/runtime/components")['Html']
  Body: typeof import("../../node_modules/nuxt/dist/head/runtime/components")['Body']
  NuxtIsland: typeof import("../../node_modules/nuxt/dist/app/components/nuxt-island")['default']
  LazyFailureNotifications: LazyComponent<typeof import("../../components/FailureNotifications.vue")['default']>
  LazyFanOutDiagram: LazyComponent<typeof import("../../components/FanOutDiagram.vue")['default']>
  LazyAccountsConnectForm: LazyComponent<typeof import("../../components/accounts/ConnectForm.vue")['default']>
  LazyAppLocaleToggle: LazyComponent<typeof import("../../components/app/LocaleToggle.vue")['default']>
  LazyAppMobileNav: LazyComponent<typeof import("../../components/app/MobileNav.vue")['default']>
  LazyAppSidebar: LazyComponent<typeof import("../../components/app/Sidebar.vue")['default']>
  LazyAppThemeToggle: LazyComponent<typeof import("../../components/app/ThemeToggle.vue")['default']>
  LazyAppTopbar: LazyComponent<typeof import("../../components/app/Topbar.vue")['default']>
  LazyDashboardAlerts: LazyComponent<typeof import("../../components/dashboard/Alerts.vue")['default']>
  LazyDashboardOpenPosition: LazyComponent<typeof import("../../components/dashboard/OpenPosition.vue")['default']>
  LazyDashboardRecentTrades: LazyComponent<typeof import("../../components/dashboard/RecentTrades.vue")['default']>
  LazyTerminalAccountsPane: LazyComponent<typeof import("../../components/terminal/AccountsPane.vue")['default']>
  LazyTerminalFanOutSummary: LazyComponent<typeof import("../../components/terminal/FanOutSummary.vue")['default']>
  LazyTerminalPositionBar: LazyComponent<typeof import("../../components/terminal/PositionBar.vue")['default']>
  LazyTerminalTicket: LazyComponent<typeof import("../../components/terminal/Ticket.vue")['default']>
  LazyUiBadge: LazyComponent<typeof import("../../components/ui/Badge.vue")['default']>
  LazyUiBarSeries: LazyComponent<typeof import("../../components/ui/BarSeries.vue")['default']>
  LazyUiCard: LazyComponent<typeof import("../../components/ui/Card.vue")['default']>
  LazyUiColumnChart: LazyComponent<typeof import("../../components/ui/ColumnChart.vue")['default']>
  LazyUiEmpty: LazyComponent<typeof import("../../components/ui/Empty.vue")['default']>
  LazyUiField: LazyComponent<typeof import("../../components/ui/Field.vue")['default']>
  LazyUiIcon: LazyComponent<typeof import("../../components/ui/Icon.vue")['default']>
  LazyUiModal: LazyComponent<typeof import("../../components/ui/Modal.vue")['default']>
  LazyUiSegmented: LazyComponent<typeof import("../../components/ui/Segmented.vue")['default']>
  LazyUiStat: LazyComponent<typeof import("../../components/ui/Stat.vue")['default']>
  LazyUiSwitch: LazyComponent<typeof import("../../components/ui/Switch.vue")['default']>
  LazyUiTrendChart: LazyComponent<typeof import("../../components/ui/TrendChart.vue")['default']>
  LazyNuxtWelcome: LazyComponent<typeof import("../../node_modules/nuxt/dist/app/components/welcome.vue")['default']>
  LazyNuxtLayout: LazyComponent<typeof import("../../node_modules/nuxt/dist/app/components/nuxt-layout")['default']>
  LazyNuxtErrorBoundary: LazyComponent<typeof import("../../node_modules/nuxt/dist/app/components/nuxt-error-boundary.vue")['default']>
  LazyClientOnly: LazyComponent<typeof import("../../node_modules/nuxt/dist/app/components/client-only")['default']>
  LazyDevOnly: LazyComponent<typeof import("../../node_modules/nuxt/dist/app/components/dev-only")['default']>
  LazyServerPlaceholder: LazyComponent<typeof import("../../node_modules/nuxt/dist/app/components/server-placeholder")['default']>
  LazyNuxtLink: LazyComponent<typeof import("../../node_modules/nuxt/dist/app/components/nuxt-link")['default']>
  LazyNuxtLoadingIndicator: LazyComponent<typeof import("../../node_modules/nuxt/dist/app/components/nuxt-loading-indicator")['default']>
  LazyNuxtTime: LazyComponent<typeof import("../../node_modules/nuxt/dist/app/components/nuxt-time.vue")['default']>
  LazyNuxtRouteAnnouncer: LazyComponent<typeof import("../../node_modules/nuxt/dist/app/components/nuxt-route-announcer")['default']>
  LazyNuxtImg: LazyComponent<typeof import("../../node_modules/nuxt/dist/app/components/nuxt-stubs")['NuxtImg']>
  LazyNuxtPicture: LazyComponent<typeof import("../../node_modules/nuxt/dist/app/components/nuxt-stubs")['NuxtPicture']>
  LazyNuxtLinkLocale: LazyComponent<typeof import("../../node_modules/@nuxtjs/i18n/dist/runtime/components/NuxtLinkLocale")['default']>
  LazySwitchLocalePathLink: LazyComponent<typeof import("../../node_modules/@nuxtjs/i18n/dist/runtime/components/SwitchLocalePathLink")['default']>
  LazyNuxtPage: LazyComponent<typeof import("../../node_modules/nuxt/dist/pages/runtime/page")['default']>
  LazyNoScript: LazyComponent<typeof import("../../node_modules/nuxt/dist/head/runtime/components")['NoScript']>
  LazyLink: LazyComponent<typeof import("../../node_modules/nuxt/dist/head/runtime/components")['Link']>
  LazyBase: LazyComponent<typeof import("../../node_modules/nuxt/dist/head/runtime/components")['Base']>
  LazyTitle: LazyComponent<typeof import("../../node_modules/nuxt/dist/head/runtime/components")['Title']>
  LazyMeta: LazyComponent<typeof import("../../node_modules/nuxt/dist/head/runtime/components")['Meta']>
  LazyStyle: LazyComponent<typeof import("../../node_modules/nuxt/dist/head/runtime/components")['Style']>
  LazyHead: LazyComponent<typeof import("../../node_modules/nuxt/dist/head/runtime/components")['Head']>
  LazyHtml: LazyComponent<typeof import("../../node_modules/nuxt/dist/head/runtime/components")['Html']>
  LazyBody: LazyComponent<typeof import("../../node_modules/nuxt/dist/head/runtime/components")['Body']>
  LazyNuxtIsland: LazyComponent<typeof import("../../node_modules/nuxt/dist/app/components/nuxt-island")['default']>
}

declare module 'vue' {
  export interface GlobalComponents extends _GlobalComponents { }
}

export {}
