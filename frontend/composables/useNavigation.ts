/**
 * One definition of the panel's navigation, consumed by the desktop rail, the
 * mobile drawer and the mobile tab bar. Three copies of this list is how a
 * route ends up reachable on a laptop and invisible on a phone.
 *
 * `primary` marks the four destinations that fit a phone's tab bar; everything
 * else lives in the drawer.
 */
export interface NavItem {
  name: string
  path: string
  icon: IconName
  label: string
  primary: boolean
  /** A count rendered as a badge — currently only unresolved failures. */
  badge?: number
}

export function useNavigation() {
  const { t } = useI18n()
  const localePath = useLocalePath()
  const route = useRoute()
  const notifications = useNotificationStore()

  const items = computed<NavItem[]>(() => [
    {
      name: 'dashboard',
      path: localePath('/dashboard'),
      icon: 'dashboard',
      label: t('nav.dashboard'),
      primary: true,
      badge: notifications.count || undefined,
    },
    {
      name: 'chart',
      path: localePath('/chart'),
      icon: 'chart',
      label: t('nav.chart'),
      primary: true,
    },
    {
      name: 'accounts',
      path: localePath('/accounts'),
      icon: 'wallet',
      label: t('nav.accounts'),
      primary: true,
    },
    {
      name: 'history',
      path: localePath('/history'),
      icon: 'history',
      label: t('nav.history'),
      primary: true,
    },
    {
      name: 'risk',
      path: localePath('/risk'),
      icon: 'risk',
      label: t('nav.risk'),
      primary: false,
    },
    {
      name: 'settings',
      path: localePath('/settings'),
      icon: 'settings',
      label: t('nav.settings'),
      primary: false,
    },
  ])

  /** Locale-prefixed routes arrive as "accounts___fa"; the base name is enough. */
  const current = computed(() => String(route.name ?? '').split('___')[0])

  const isActive = (item: NavItem) => current.value === item.name

  return { items, current, isActive }
}
