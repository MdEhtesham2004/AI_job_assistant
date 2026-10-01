import { QueryClient } from '@tanstack/react-query'

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // Retry once on server/network errors, never on 4xx.
        retry: (failureCount, error) =>
          failureCount < 1 && (error?.status === 0 || error?.status >= 500),
      },
    },
  })
}
