import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { queryKeys } from '@/api/queryKeys'

import { isActive, tasksApi } from './api'

const POLL_MS = 2000

/** Task list; polls every 2 s while any task is queued or running. */
export function useTasks(page = 1) {
  return useQuery({
    queryKey: queryKeys.tasks.list(page),
    queryFn: () => tasksApi.list(page),
    refetchInterval: (query) => (query.state.data?.items.some(isActive) ? POLL_MS : false),
  })
}

/** Phase 1 §7.3 `useTaskPolling`: follows one task until it finishes. */
export function useTaskPolling(taskId) {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: queryKeys.tasks.detail(taskId),
    queryFn: async () => {
      const task = await tasksApi.get(taskId)
      if (!isActive(task)) {
        // Finished: refresh lists and the bell (a notification was created).
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all() })
        queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all() })
      }
      return task
    },
    enabled: Boolean(taskId),
    refetchInterval: (query) => (isActive(query.state.data) || !query.state.data ? POLL_MS : false),
  })
}

/** Start a background task; returns { task_id }. */
export function useStartTask(start, { label }) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: start,
    onSuccess: () => {
      toast.info(`${label} started — it runs in the background.`)
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all() })
    },
    onError: (error) => toast.error(error.message),
  })
}
