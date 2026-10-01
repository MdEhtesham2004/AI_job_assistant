const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

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

/**
 * Single entry point for all backend calls. Components never call fetch directly.
 * Authentication headers and token refresh are added in Phase 4.
 */
export async function apiRequest(path, { method = 'GET', body, headers = {}, signal } = {}) {
  const init = {
    method,
    headers: { Accept: 'application/json', ...headers },
    credentials: 'include',
    signal,
  }
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

export const api = {
  get: (path, options) => apiRequest(path, { ...options, method: 'GET' }),
  post: (path, body, options) => apiRequest(path, { ...options, method: 'POST', body }),
  put: (path, body, options) => apiRequest(path, { ...options, method: 'PUT', body }),
  patch: (path, body, options) => apiRequest(path, { ...options, method: 'PATCH', body }),
  delete: (path, options) => apiRequest(path, { ...options, method: 'DELETE' }),
}
