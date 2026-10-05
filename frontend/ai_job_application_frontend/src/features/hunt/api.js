import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { toast } from 'sonner'

import { api } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import { isActive } from '@/features/tasks/api'
import { useTaskPolling } from '@/features/tasks/hooks'

export const huntApi = {
  digest: () => api.get('/digest'),
  runDigest: () => api.post('/digest/run'),
  skills: () => api.get('/skills'),
  makePlan: () => api.post('/skills/plan'),
  answers: (jobId) => api.get(`/jobs/${jobId}/answers`),
  makeAnswers: (jobId, customQuestions) =>
    api.post(`/jobs/${jobId}/answers`, { custom_questions: customQuestions }),
  editAnswer: (jobId, key, answer) => api.patch(`/jobs/${jobId}/answers/${key}`, { answer }),
  prep: (jobId) => api.get(`/jobs/${jobId}/prep`),
  makePrep: (jobId) => api.post(`/jobs/${jobId}/prep`),
}

export const FILL_IN = '[fill in]'

/** Follow a task (started now or already running) and refresh `key` when it ends. */
function useTaskFollow(taskId, key, onDone) {
  const queryClient = useQueryClient()
  const task = useTaskPolling(taskId).data
  useEffect(() => {
    if (!task || isActive(task)) return
    queryClient.invalidateQueries({ queryKey: key })
    onDone?.(task)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per finished task
  }, [task?.id, task?.status])
  return task
}

function useStartAndFollow({ queryKey, start, runningTaskId, onDone }) {
  const mutation = useMutation({
    mutationFn: start,
    onError: (error) => toast.error(error.message),
  })
  const taskId = mutation.data?.task_id ?? runningTaskId ?? null
  const task = useTaskFollow(taskId, queryKey, onDone)
  return {
    start: (...args) => mutation.mutate(...args),
    task,
    running: mutation.isPending || (task ? isActive(task) : Boolean(runningTaskId)),
  }
}

// ---------- digest ----------

export function useDigest() {
  return useQuery({ queryKey: queryKeys.hunt.digest(), queryFn: huntApi.digest })
}

export function useRunDigest(runningTaskId) {
  return useStartAndFollow({
    queryKey: queryKeys.hunt.digest(),
    start: huntApi.runDigest,
    runningTaskId,
    onDone: (task) => {
      if (task.status !== 'succeeded') return toast.error(task.error ?? 'The digest failed.')
      const r = task.result ?? {}
      toast.success(
        r.jobs ? `${r.jobs} match${r.jobs === 1 ? '' : 'es'} found.` : (r.note ?? 'Done.'),
      )
    },
  })
}

// ---------- skills ----------

export function useSkills() {
  return useQuery({ queryKey: queryKeys.hunt.skills(), queryFn: huntApi.skills })
}

export function useMakePlan(runningTaskId) {
  return useStartAndFollow({
    queryKey: queryKeys.hunt.skills(),
    start: huntApi.makePlan,
    runningTaskId,
    onDone: (task) =>
      task.status === 'succeeded'
        ? toast.success('Your learning plan is ready.')
        : toast.error(task.error ?? 'The plan could not be written.'),
  })
}

// ---------- screening answers ----------

export function useAnswers(jobId) {
  return useQuery({
    queryKey: queryKeys.hunt.answers(jobId),
    queryFn: () => huntApi.answers(jobId),
    enabled: Boolean(jobId),
  })
}

export function useMakeAnswers(jobId, runningTaskId) {
  return useStartAndFollow({
    queryKey: queryKeys.hunt.answers(jobId),
    start: (questions) => huntApi.makeAnswers(jobId, questions),
    runningTaskId,
    onDone: (task) =>
      task.status === 'succeeded'
        ? toast.success('Answers ready — check the [fill in] parts.')
        : toast.error(task.error ?? 'The answers could not be written.'),
  })
}

export function useEditAnswer(jobId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ key, answer }) => huntApi.editAnswer(jobId, key, answer),
    onSuccess: (saved) => {
      queryClient.setQueryData(queryKeys.hunt.answers(jobId), saved)
      toast.success('Answer saved.')
    },
    onError: (error) => toast.error(error.message),
  })
}

// ---------- interview prep pack (Phase 17) ----------

export function usePrep(jobId) {
  return useQuery({
    queryKey: queryKeys.hunt.prep(jobId),
    queryFn: () => huntApi.prep(jobId),
    enabled: Boolean(jobId),
  })
}

export function useMakePrep(jobId, runningTaskId) {
  return useStartAndFollow({
    queryKey: queryKeys.hunt.prep(jobId),
    start: () => huntApi.makePrep(jobId),
    runningTaskId,
    onDone: (task) =>
      task.status === 'succeeded'
        ? toast.success('Your interview prep is ready.')
        : toast.error(task.error ?? 'The prep pack could not be made.'),
  })
}
