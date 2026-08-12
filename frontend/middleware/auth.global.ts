/**
 * Keeps signed-out visitors out of the operating surfaces.
 *
 * The server enforces this too — this only avoids showing a shell that would
 * immediately fail to load. The landing page and the risk calculator stay open:
 * the calculator reads no account data, it only does arithmetic on numbers you
 * type.
 */
const PUBLIC_ROUTES = ['index', 'login', 'risk']

function routeName(name: unknown): string {
  // Locale-prefixed routes arrive as "accounts___fa"; the base name is enough.
  return String(name ?? '').split('___')[0]
}

export default defineNuxtRouteMiddleware(async (to) => {
  if (import.meta.server) return

  const auth = useAuthStore()
  if (!auth.checked) await auth.check()

  const name = routeName(to.name)
  const localePath = useLocalePath()

  if (!auth.authenticated && !PUBLIC_ROUTES.includes(name)) {
    return navigateTo({ path: localePath('/login'), query: { next: to.fullPath } })
  }
  if (auth.authenticated && name === 'login') {
    return navigateTo(localePath('/dashboard'))
  }
})
