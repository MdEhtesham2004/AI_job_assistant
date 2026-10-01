import { AppLayout } from '@/layouts/AppLayout'
import HomePage from '@/pages/HomePage'
import NotFoundPage from '@/pages/NotFoundPage'
import RouteErrorPage from '@/pages/RouteErrorPage'
import SystemStatusPage from '@/pages/SystemStatusPage'

/** Route table — grows per phase (see Phase 1 §8 page map). */
export const routes = [
  {
    element: <AppLayout />,
    errorElement: <RouteErrorPage />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'system', element: <SystemStatusPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
