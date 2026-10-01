import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { availableActions } from '@/features/admin/userRules'
import { makeAuth, makeUser, mockApi, renderWithProviders } from '@/test/utils'

import AdminUsersPage from './AdminUsersPage'

const ADMIN = makeUser({ id: 'admin-1', role: 'admin', full_name: 'Admin Person' })
const WAITING = makeUser({
  id: 'u-1',
  email: 'testuser@gmail.com',
  full_name: 'Test user',
  approval_status: 'pending',
  approved_at: null,
  approved_by: null,
  rejection_reason: null,
  updated_at: '2026-10-01T10:00:00Z',
})
const COUNTS = { all: 2, pending: 1, approved: 1, rejected: 0, deactivated: 0 }

function page(items) {
  return { items, total: items.length, page: 1, page_size: 20 }
}

afterEach(() => vi.unstubAllGlobals())

describe('AdminUsersPage', () => {
  it('lists pending sign-ups with their counts', async () => {
    mockApi({ 'GET /admin/users': page([WAITING]), 'GET /admin/users/counts': COUNTS })

    renderWithProviders(<AdminUsersPage />, { auth: makeAuth({ user: ADMIN }) })

    expect(await screen.findByText('testuser@gmail.com')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Pending/ })).toHaveTextContent('1')
    expect(screen.getByRole('button', { name: 'Approve Test user' })).toBeInTheDocument()
  })

  it('approves a sign-up and refreshes the list', async () => {
    const fetchMock = mockApi({
      'GET /admin/users': page([WAITING]),
      'GET /admin/users/counts': COUNTS,
      'POST /admin/users/u-1/approve': { ...WAITING, approval_status: 'approved' },
    })
    renderWithProviders(<AdminUsersPage />, { auth: makeAuth({ user: ADMIN }) })

    await userEvent.click(await screen.findByRole('button', { name: 'Approve Test user' }))

    const calls = fetchMock.mock.calls.map(([url, init]) => `${init?.method ?? 'GET'} ${url}`)
    expect(calls).toContain('POST /api/v1/admin/users/u-1/approve')
  })

  it('asks for an optional reason before rejecting', async () => {
    const fetchMock = mockApi({
      'GET /admin/users': page([WAITING]),
      'GET /admin/users/counts': COUNTS,
      'POST /admin/users/u-1/reject': { ...WAITING, approval_status: 'rejected' },
    })
    renderWithProviders(<AdminUsersPage />, { auth: makeAuth({ user: ADMIN }) })

    await userEvent.click(await screen.findByRole('button', { name: 'Reject Test user' }))
    const dialog = screen.getByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText(/Reason/), 'Not in the pilot')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Reject' }))

    const reject = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/reject'))
    expect(JSON.parse(reject[1].body)).toEqual({ reason: 'Not in the pilot' })
  })
})

describe('availableActions', () => {
  const base = { is_active: true, role: 'user' }

  it.each([
    [{ approval_status: 'pending' }, ['approve', 'reject', 'deactivate']],
    [{ approval_status: 'rejected' }, ['approve', 'deactivate']],
    [{ approval_status: 'approved' }, ['makeAdmin', 'deactivate']],
    [{ approval_status: 'approved', role: 'admin' }, ['removeAdmin', 'deactivate']],
    [{ approval_status: 'approved', is_active: false }, ['reactivate']],
  ])('%o → %o', (overrides, expected) => {
    expect(availableActions({ id: 'x', ...base, ...overrides }, 'me')).toEqual(expected)
  })

  it('offers nothing on your own row', () => {
    expect(availableActions({ id: 'me', ...base, approval_status: 'approved' }, 'me')).toEqual([])
  })
})
