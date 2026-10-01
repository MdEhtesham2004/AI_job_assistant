/**
 * Access token kept in memory only (Phase 1 §3.5) — never in localStorage.
 * A page reload loses it; the session is restored from the httpOnly refresh cookie.
 */
let accessToken = null
const sessionEndedListeners = new Set()

export const tokenStore = {
  get: () => accessToken,
  set: (token) => {
    accessToken = token
  },
  clear: () => {
    accessToken = null
  },
  /** Called when the session can no longer be refreshed (e.g. expired or revoked). */
  onSessionEnded: (listener) => {
    sessionEndedListeners.add(listener)
    return () => sessionEndedListeners.delete(listener)
  },
  endSession: () => {
    accessToken = null
    sessionEndedListeners.forEach((listener) => listener())
  },
}
