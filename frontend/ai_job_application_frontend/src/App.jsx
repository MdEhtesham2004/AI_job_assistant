import { QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { createBrowserRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { Toaster } from 'sonner'

import { createQueryClient } from '@/api/queryClient'
import { AuthProvider } from '@/auth/AuthProvider'
import { routes } from '@/routes/routes'
import { ThemeProvider } from '@/theme/ThemeProvider'
import { useTheme } from '@/theme/useTheme'

const router = createBrowserRouter(routes)

function ThemedToaster() {
  const { theme } = useTheme()
  return <Toaster theme={theme} richColors closeButton position="top-right" />
}

export default function App() {
  const [queryClient] = useState(createQueryClient)

  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
        <ThemedToaster />
      </QueryClientProvider>
    </ThemeProvider>
  )
}
