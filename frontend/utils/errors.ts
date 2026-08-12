/**
 * DRF puts the useful text in a different place depending on how it failed:
 * a plain string, a `detail` key, or a map of field -> list of messages. The
 * panel shows one line either way, because "[object Object]" in a red box
 * during a fan-out is worse than no message at all.
 */
export function errorMessage(e: any): string {
  const data = e?.data
  if (typeof data === 'string' && data) return data
  if (data?.detail) return String(data.detail)
  if (data && typeof data === 'object') {
    const flat = Object.values(data).flat().filter(Boolean)
    if (flat.length) return flat.map(String).join(' ')
  }
  return e?.message ?? String(e)
}
