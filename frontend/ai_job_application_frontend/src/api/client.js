import { tokenStore } from '@/auth/tokenStore'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
const REFRESH_PATH = '/auth/refresh'
const RACE_RETRY_DELAY_MS = 300

/** Normalized error for every failed API call (see Phase 1 §3.4 error format). */
export class ApiError extends Error {
  constructor({ status, code, message, details = {}, requestId = null }) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.requestId = requestId
  }
}

async function send(path, { method = 'GET', body, headers = {}, signal } = {}) {
  const init = {
    method,
    headers: { Accept: 'application/json', ...headers },
    credentials: 'include',
    signal,
  }
  const token = tokenStore.get()
  if (token) init.headers.Authorization = `Bearer ${token}`
  if (body instanceof FormData) {
    init.body = body
  } else if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }

  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init)
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new ApiError({ status: 0, code: 'NETWORK_ERROR', message: 'Cannot reach the server.' })
  }

  const requestId = response.headers.get('X-Request-ID')
  if (response.status === 204) return null

  const isJson = response.headers.get('Content-Type')?.includes('application/json')
  const data = isJson ? await response.json() : await response.text()

  if (!response.ok) {
    const error = isJson ? data?.error : undefined
    throw new ApiError({
      status: response.status,
      code: error?.code ?? 'HTTP_ERROR',
      message: error?.message ?? `Request failed with status ${response.status}.`,
      details: error?.details ?? {},
      requestId: error?.request_id ?? requestId,
    })
  }
  return data
}

let refreshInFlight = null

async function refreshOnce() {
  try {
    return await send(REFRESH_PATH, { method: 'POST' })
  } catch (error) {
    // Another tab rotated the cookie a moment ago; the browser now holds the new one.
    if (error instanceof ApiError && error.code === 'REFRESH_RACE') {
      await new Promise((resolve) => setTimeout(resolve, RACE_RETRY_DELAY_MS))
      return send(REFRESH_PATH, { method: 'POST' })
    }
    throw error
  }
}

/**
 * Exchange the refresh cookie for a new access token. Parallel callers share one request,
 * so the cookie is rotated only once.
 */
export function refreshSession() {
  if (!refreshInFlight) {
    refreshInFlight = refreshOnce()
      .then((session) => {
        tokenStore.set(session.access_token)
        return session
      })
      .finally(() => {
        refreshInFlight = null
      })
  }
  return refreshInFlight
}

/**
 * Single entry point for all backend calls. Components never call fetch directly.
 * On 401 it refreshes the session once and retries; if that fails the session ends.
 */
export async function apiRequest(path, options = {}) {
  try {
    return await send(path, options)
  } catch (error) {
    const canRetry =
      error instanceof ApiError &&
      error.status === 401 &&
      !path.startsWith('/auth/') &&
      !options.skipAuthRetry &&
      tokenStore.get() !== null
    if (!canRetry) throw error

    try {
      await refreshSession()
    } catch {
      tokenStore.endSession()
      throw error
    }
    return send(path, options)
  }
}

export const api = {
  get: (path, options) => apiRequest(path, { ...options, method: 'GET' }),
  post: (path, body, options) => apiRequest(path, { ...options, method: 'POST', body }),
  put: (path, body, options) => apiRequest(path, { ...options, method: 'PUT', body }),
  patch: (path, body, options) => apiRequest(path, { ...options, method: 'PATCH', body }),
  delete: (path, options) => apiRequest(path, { ...options, method: 'DELETE' }),
}
