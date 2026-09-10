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

/**
 * HTTP status of a failed `$fetch`, whichever shape ofetch used this time.
 *
 * The panel treats 503 from the market endpoints as "no exchange reachable",
 * which is a different state from a generic request failure — it is the one
 * case where the chart must stop and say so rather than retry quietly.
 */
export function statusOf(e: any): number | null {
  return e?.statusCode ?? e?.status ?? e?.response?.status ?? null
}

/**
 * Did this request fail *before* it reached the server?
 *
 * A dropped Wi-Fi, a dead tunnel and a stopped backend all surface as an
 * exception with **no status** and a message the browser chose — "Failed to
 * fetch" in Chrome, "Load failed" in Safari, "<no response>" from ofetch. None
 * of them is something the reader can act on, and a panel that polls four
 * endpoints prints four of them a second.
 *
 * A status of any kind means the server answered, so it is not this.
 */
const NETWORK_TEXT =
  /failed to fetch|load failed|network ?error|fetch failed|<no response>|networkerror|ERR_(NETWORK|INTERNET|CONNECTION|NAME_NOT_RESOLVED)|ECONNREFUSED|ECONNRESET|ETIMEDOUT|ENOTFOUND|EAI_AGAIN/i

export function isNetworkError(e: any): boolean {
  if (statusOf(e) !== null) return false
  return NETWORK_TEXT.test(`${e?.name ?? ''} ${e?.message ?? ''} ${e?.cause?.message ?? ''}`)
}
