import { AppLayout } from '@/layouts/AppLayout'
import { AuthLayout } from '@/layouts/AuthLayout'
import AwaitingApprovalPage from '@/pages/AwaitingApprovalPage'
import ChangePasswordPage from '@/pages/ChangePasswordPage'
import HomePage from '@/pages/HomePage'
import LoginPage from '@/pages/LoginPage'
import NotFoundPage from '@/pages/NotFoundPage'
import RegisterPage from '@/pages/RegisterPage'
import RouteErrorPage from '@/pages/RouteErrorPage'
import SystemStatusPage from '@/pages/SystemStatusPage'

import { GuestOnly, RequireApproved, RequireAuth } from './guards'

/** Route table — grows per phase (see Phase 1 §8 page map). */
export const routes = [
  {
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: (
          <GuestOnly>
            <AuthLayout />
          </GuestOnly>
        ),
        children: [
          { path: 'login', element: <LoginPage /> },
          { path: 'register', element: <RegisterPage /> },
        ],
      },
      {
        element: (
          <RequireAuth>
            <AuthLayout />
          </RequireAuth>
        ),
        children: [{ path: 'awaiting-approval', element: <AwaitingApprovalPage /> }],
      },
      {
        element: (
          <RequireAuth>
            <RequireApproved>
              <AppLayout />
            </RequireApproved>
          </RequireAuth>
        ),
        children: [
          { index: true, element: <HomePage /> },
          { path: 'system', element: <SystemStatusPage /> },
          { path: 'account/password', element: <ChangePasswordPage /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]
