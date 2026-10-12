import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { makeAuth, makeUser, mockApi, renderWithProviders } from '@/test/utils'
import { ThemeProvider } from '@/theme/ThemeProvider'

import { AppLayout } from './AppLayout'

const COUNTS = { all: 3, pending: 2, approved: 1, rejected: 0, deactivated: 0 }

afterEach(() => vi.unstubAllGlobals())

function renderLayout(user) {
  return renderWithProviders(
    <ThemeProvider>
      <AppLayout />
    </ThemeProvider>,
    { auth: makeAuth({ user }) },
  )
}

describe('AppLayout navigation', () => {
  it('shows the short menu and hides the admin section from normal users', () => {
    const fetchMock = mockApi({ 'GET /notifications/unread-count': { unread: 0 } })
    renderLayout(makeUser())

    const nav = screen.getAllByRole('navigation', { name: 'Main' })[0]
    const labels = Array.from(nav.querySelectorAll('a')).map((a) => a.textContent)
    // Phase 18: grouped menu; Outreach only once Gmail or LinkedIn posts are in use.
    expect(labels).toEqual(['Home', 'Jobs', 'Applications', 'Prepare', 'Resume', 'Settings'])
    const requested = fetchMock.mock.calls.map(([url]) => url)
    expect(requested.some((url) => url.includes('/admin/'))).toBe(false)
  })

  it('shows Outreach when Gmail is connected', async () => {
    mockApi({
      'GET /notifications/unread-count': { unread: 0 },
      'GET /integrations/gmail': { configured: true, connected: true },
    })
    renderLayout(makeUser())

    expect(await screen.findByRole('link', { name: 'Outreach' })).toHaveAttribute(
      'href',
      '/contacts',
    )
  })

  it('shows admins the Users page with the pending count', async () => {
    mockApi({
      'GET /admin/users/counts': COUNTS,
      'GET /notifications/unread-count': { unread: 0 },
    })
    renderLayout(makeUser({ role: 'admin' }))

    expect(await screen.findByLabelText('2 pending')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /System/ })).toBeInTheDocument()
  })

  it('shows the unread notification count on the bell', async () => {
    mockApi({ 'GET /notifications/unread-count': { unread: 3 } })
    renderLayout(makeUser())

    expect(await screen.findByLabelText('Notifications, 3 unread')).toBeInTheDocument()
  })
})
