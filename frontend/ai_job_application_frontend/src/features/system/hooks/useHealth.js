import { useQuery } from '@tanstack/react-query'

import { queryKeys } from '@/api/queryKeys'

import { getSystemStatus } from '../api'

export const HEALTH_REFRESH_MS = 15_000

/** Admin › System: health of every service (Phase 6). */
export function useSystemStatus() {
  return useQuery({
    queryKey: queryKeys.system.admin(),
    queryFn: ({ signal }) => getSystemStatus({ signal }),
    refetchInterval: HEALTH_REFRESH_MS,
    staleTime: 0,
    retry: false,
  })
}
