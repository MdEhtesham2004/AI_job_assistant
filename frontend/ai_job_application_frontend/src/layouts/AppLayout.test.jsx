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
  it('hides the admin section from normal users', () => {
    const fetchMock = mockApi({})
    renderLayout(makeUser())

    const nav = screen.getAllByRole('navigation', { name: 'Main' })[0]
    expect(nav).toHaveTextContent('Profile')
    expect(nav).not.toHaveTextContent('Users')
    expect(fetchMock).not.toHaveBeenCalled() // no admin counts requested
  })

  it('shows admins the Users page with the pending count', async () => {
    mockApi({ 'GET /admin/users/counts': COUNTS })
    renderLayout(makeUser({ role: 'admin' }))

    expect(await screen.findByLabelText('2 pending')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /System Status/ })).toBeInTheDocument()
  })
})
