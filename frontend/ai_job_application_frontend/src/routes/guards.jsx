import { Navigate, useLocation } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { FullPageSpinner } from '@/components/common/FullPageSpinner'

function homeFor(user) {
  return user?.approval_status === 'approved' ? '/' : '/awaiting-approval'
}

/**
 * Login/register: once signed in, go back to the page that required sign-in
 * (or the start page). Pending accounts always land on "awaiting approval".
 */
export function GuestOnly({ children }) {
  const { status, user } = useAuth()
  const location = useLocation()
  if (status === 'loading') return <FullPageSpinner />
  if (status === 'authenticated') {
    const from = location.state?.from?.pathname
    const target = user?.approval_status === 'approved' && from ? from : homeFor(user)
    return <Navigate to={target} replace />
  }
  return children
}

/** Any signed-in user (including accounts waiting for approval). */
export function RequireAuth({ children }) {
  const { status } = useAuth()
  const location = useLocation()
  if (status === 'loading') return <FullPageSpinner />
  if (status === 'anonymous') return <Navigate to="/login" replace state={{ from: location }} />
  return children
}

/** Feature pages: the account must be approved by an admin. Use inside RequireAuth. */
export function RequireApproved({ children }) {
  const { user } = useAuth()
  if (user?.approval_status !== 'approved') return <Navigate to="/awaiting-approval" replace />
  return children
}
