import { AppLayout } from '@/layouts/AppLayout'
import { AuthLayout } from '@/layouts/AuthLayout'
import AdminUsersPage from '@/pages/admin/AdminUsersPage'
import AwaitingApprovalPage from '@/pages/AwaitingApprovalPage'
import ChangePasswordPage from '@/pages/ChangePasswordPage'
import HomePage from '@/pages/HomePage'
import LoginPage from '@/pages/LoginPage'
import NotFoundPage from '@/pages/NotFoundPage'
import ProfilePage from '@/pages/ProfilePage'
import RegisterPage from '@/pages/RegisterPage'
import RouteErrorPage from '@/pages/RouteErrorPage'
import SettingsPage from '@/pages/SettingsPage'
import SystemStatusPage from '@/pages/SystemStatusPage'
import TasksPage from '@/pages/TasksPage'

import { GuestOnly, RequireAdmin, RequireApproved, RequireAuth } from './guards'

const admin = (page) => <RequireAdmin>{page}</RequireAdmin>

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
          { path: 'tasks', element: <TasksPage /> },
          { path: 'profile', element: <ProfilePage /> },
          { path: 'settings', element: <SettingsPage /> },
          { path: 'account/password', element: <ChangePasswordPage /> },
          { path: 'admin/users', element: admin(<AdminUsersPage />) },
          { path: 'admin/system', element: admin(<SystemStatusPage />) },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]
