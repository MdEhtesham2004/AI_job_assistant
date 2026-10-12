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
        // Finished: refresh the task list and the bell (a notification was created).
        // Not `tasks.all()`: that includes THIS query, and invalidating a query while it
        // fetches cancels the fetch — the "finished" answer was dropped and the next poll
        // did the same, so the progress bar spun until a page refresh (found 2026-10-12).
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks.lists() })
        queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all() })
      }
      return task
    },
    enabled: Boolean(taskId),
    refetchInterval: (query) => (isActive(query.state.data) || !query.state.data ? POLL_MS : false),
    // Keep following while the tab is in the background (e.g. the user switched tabs
    // during a 30-second AI task); otherwise nothing catches up on return.
    refetchIntervalInBackground: true,
  })
}

/** Start a background task; returns { task_id }. */
export function useStartTask(start, { label }) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: start,
    onSuccess: () => {
      toast.info(`${label} started — it runs in the background.`)
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.lists() })
    },
    onError: (error) => toast.error(error.message),
  })
}
