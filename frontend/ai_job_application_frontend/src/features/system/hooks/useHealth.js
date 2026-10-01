import { useQuery } from '@tanstack/react-query'

import { queryKeys } from '@/api/queryKeys'

import { getHealth } from '../api'

export const HEALTH_REFRESH_MS = 15_000

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.system.health(),
    queryFn: ({ signal }) => getHealth({ signal }),
    refetchInterval: HEALTH_REFRESH_MS,
    staleTime: 0,
    retry: false,
  })
}
