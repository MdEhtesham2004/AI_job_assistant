import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'

import { makeAuth, makeUser, renderWithProviders } from '@/test/utils'

import { GuestOnly, RequireApproved, RequireAuth } from './guards'

function TestRoutes() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <GuestOnly>
            <p>login page</p>
          </GuestOnly>
        }
      />
      <Route
        path="/awaiting-approval"
        element={
          <RequireAuth>
            <p>awaiting page</p>
          </RequireAuth>
        }
      />
      <Route
        path="/"
        element={
          <RequireAuth>
            <RequireApproved>
              <p>home page</p>
            </RequireApproved>
          </RequireAuth>
        }
      />
      <Route
        path="/jobs"
        element={
          <RequireAuth>
            <RequireApproved>
              <p>jobs page</p>
            </RequireApproved>
          </RequireAuth>
        }
      />
    </Routes>
  )
}

const anonymous = makeAuth({ status: 'anonymous', user: null })
const pending = makeAuth({ user: makeUser({ approval_status: 'pending' }) })
const approved = makeAuth()

describe('route guards', () => {
  it('shows a spinner while the session is being restored', () => {
    renderWithProviders(<TestRoutes />, { auth: makeAuth({ status: 'loading', user: null }) })

    expect(screen.getByRole('status')).toHaveTextContent('Loading')
  })

  it('sends anonymous visitors to the login page', () => {
    renderWithProviders(<TestRoutes />, { route: '/jobs', auth: anonymous })

    expect(screen.getByText('login page')).toBeInTheDocument()
  })

  it('sends pending accounts to "awaiting approval"', () => {
    renderWithProviders(<TestRoutes />, { route: '/', auth: pending })

    expect(screen.getByText('awaiting page')).toBeInTheDocument()
  })

  it('lets approved users in', () => {
    renderWithProviders(<TestRoutes />, { route: '/jobs', auth: approved })

    expect(screen.getByText('jobs page')).toBeInTheDocument()
  })

  it('redirects signed-in users away from the login page', () => {
    renderWithProviders(<TestRoutes />, { route: '/login', auth: approved })

    expect(screen.getByText('home page')).toBeInTheDocument()
  })

  it('returns to the originally requested page after sign-in', () => {
    // The login page receives `from` when RequireAuth redirected there.
    renderWithProviders(<TestRoutes />, {
      route: { pathname: '/login', state: { from: { pathname: '/jobs' } } },
      auth: approved,
    })

    expect(screen.getByText('jobs page')).toBeInTheDocument()
  })
})
