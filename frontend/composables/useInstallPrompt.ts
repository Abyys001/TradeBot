/**
 * "Install app", without a trip through the browser menu.
 *
 * Chromium fires `beforeinstallprompt` once, early, and only lets the page
 * show the prompt later if the event was kept — so it is stashed at module
 * level and the first caller (the layout) attaches the listeners. iOS Safari
 * never fires it at all; there the only route is Share → Add to Home Screen,
 * which a button can explain but not perform.
 */
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

const DISMISSED_KEY = 'tradebot.install.dismissed'

const deferred = ref<BeforeInstallPromptEvent | null>(null)
const installed = ref(false)
const dismissed = ref(false)
const isIos = ref(false)
let bound = false

function readDismissed(): boolean {
  try {
    return localStorage.getItem(DISMISSED_KEY) === '1'
  } catch {
    return false
  }
}

function isStandalone(): boolean {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  )
}

function bind() {
  if (bound || import.meta.server) return
  bound = true

  installed.value = isStandalone()
  dismissed.value = readDismissed()
  const ua = navigator.userAgent
  // iPadOS reports as a Mac with touch points.
  const ios = /iphone|ipad|ipod/i.test(ua) || (/macintosh/i.test(ua) && navigator.maxTouchPoints > 1)
  // Other iOS browsers cannot add to the home screen; only Safari can.
  isIos.value = ios && /safari/i.test(ua) && !/crios|fxios|edgios|opios/i.test(ua)

  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault()
    deferred.value = event as BeforeInstallPromptEvent
  })
  window.addEventListener('appinstalled', () => {
    installed.value = true
    deferred.value = null
  })
}

export function useInstallPrompt() {
  onMounted(bind)

  /** Offer it only where something would happen when it is pressed. */
  const canInstall = computed(
    () => !installed.value && !dismissed.value && (deferred.value !== null || isIos.value),
  )
  const showIosHelp = ref(false)

  async function install() {
    if (deferred.value) {
      const event = deferred.value
      // A prompt can be used once; keep none around afterwards.
      deferred.value = null
      await event.prompt()
      const { outcome } = await event.userChoice
      if (outcome === 'accepted') installed.value = true
      else dismiss()
      return
    }
    if (isIos.value) showIosHelp.value = true
  }

  function dismiss() {
    dismissed.value = true
    try {
      localStorage.setItem(DISMISSED_KEY, '1')
    } catch {
      // Private mode: the button returns next visit, which is acceptable.
    }
  }

  return { canInstall, isIos, showIosHelp, install, dismiss }
}
