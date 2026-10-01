import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'

import { AuthContext } from '@/auth/authContext'

export function jsonResponse(body, { status = 200, headers = {} } = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

export function errorResponse(status, code, message = 'Error', details = {}) {
  return jsonResponse({ error: { code, message, details, request_id: 'req-test' } }, { status })
}

/**
 * Stub fetch with a route table: { 'GET /admin/users': body | (url, init) => Response }.
 * Paths are matched without the /api/v1 prefix and without the query string.
 * Returns the fetch mock so tests can inspect calls.
 */
export function mockApi(routes) {
  const fetchMock = vi.fn(async (url, init = {}) => {
    const path = String(url)
      .replace(/^\/api\/v1/, '')
      .split('?')[0]
    const key = `${init.method ?? 'GET'} ${path}`
    const handler = routes[key]
    if (handler === undefined) return errorResponse(404, 'NOT_FOUND', `No mock for ${key}`)
    return typeof handler === 'function' ? handler(url, init) : jsonResponse(handler)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

export function makeUser(overrides = {}) {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    email: 'person@example.com',
    full_name: 'Test Person',
    role: 'user',
    approval_status: 'approved',
    is_active: true,
    created_at: '2026-10-01T10:00:00Z',
    last_login_at: null,
    ...overrides,
  }
}

/** A fake auth context; pass `status`/`user` and override any action. */
export function makeAuth(overrides = {}) {
  return {
    status: 'authenticated',
    user: makeUser(),
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
    reloadUser: vi.fn(),
    ...overrides,
  }
}

/** Render with a fresh QueryClient (no retries), an in-memory router and an auth context. */
export function renderWithProviders(ui, { route = '/', auth = makeAuth() } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={auth}>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </AuthContext.Provider>
    </QueryClientProvider>,
  )
}
