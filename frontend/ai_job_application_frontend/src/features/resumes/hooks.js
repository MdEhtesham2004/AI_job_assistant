import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { toast } from 'sonner'

import { queryKeys } from '@/api/queryKeys'
import { isActive } from '@/features/tasks/api'
import { useTaskPolling } from '@/features/tasks/hooks'

import { resumesApi } from './api'

const POLL_MS = 2000

/** Resume + versions; polls while a version is still being parsed. */
export function useResumes() {
  return useQuery({
    queryKey: queryKeys.resumes.overview(),
    queryFn: resumesApi.overview,
    refetchInterval: (query) =>
      query.state.data?.versions.some((v) => v.parse_status === 'pending') ? POLL_MS : false,
  })
}

// File links expire after 15 minutes; refresh them before that.
const LINK_REFRESH_MS = 10 * 60 * 1000

export function useResumeVersion(id) {
  return useQuery({
    queryKey: queryKeys.resumes.version(id),
    queryFn: () => resumesApi.version(id),
    refetchInterval: (query) =>
      query.state.data?.parse_status === 'pending' ? POLL_MS : LINK_REFRESH_MS,
  })
}

export function useUploadResume() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: resumesApi.upload,
    onSuccess: ({ version }) => {
      toast.success(`Version ${version.version_no} uploaded — reading your resume…`)
      queryClient.invalidateQueries({ queryKey: queryKeys.resumes.all() })
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all() })
    },
  })
}

export function useActivateVersion() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: resumesApi.activate,
    onSuccess: () => {
      toast.success('Active resume changed.')
      queryClient.invalidateQueries({ queryKey: queryKeys.resumes.all() })
    },
    onError: (error) => toast.error(error.message),
  })
}

/**
 * One AI action on a version (ATS, improve, LinkedIn). Follows its task — the one just
 * started, or one already running when the page opened — and refreshes resumes when done.
 */
export function useResumeAction(start, { versionId, runningTaskId, label, onDone }) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => start(versionId),
    onError: (error) => toast.error(error.message),
  })
  const taskId = mutation.data?.task_id ?? runningTaskId ?? null
  const task = useTaskPolling(taskId).data
  const status = task?.status

  useEffect(() => {
    if (!task || isActive(task)) return
    queryClient.invalidateQueries({ queryKey: queryKeys.resumes.all() })
    if (status === 'succeeded' && mutation.data) {
      toast.success(`${label} ready.`)
      onDone?.(task)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- react once per finished task
  }, [task?.id, status])

  return {
    start: () => mutation.mutate(),
    task,
    running: mutation.isPending || isActive(task),
  }
}
