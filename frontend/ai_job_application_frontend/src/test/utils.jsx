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
