import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { toast } from 'sonner'

import { queryKeys } from '@/api/queryKeys'
import { isActive } from '@/features/tasks/api'
import { useTaskPolling } from '@/features/tasks/hooks'

import { jobsApi, savedSearchesApi } from './api'

const POLL_MS = 2000
const RUN_ACTIVE = ['queued', 'running']

export function useJobs(filters, { enabled = true } = {}) {
  return useQuery({
    queryKey: queryKeys.jobs.list(filters),
    queryFn: () => jobsApi.list(filters),
    enabled,
    placeholderData: keepPreviousData,
  })
}

export function useJobCounts() {
  return useQuery({ queryKey: queryKeys.jobs.counts(), queryFn: jobsApi.counts })
}

export function useJob(id) {
  return useQuery({
    queryKey: queryKeys.jobs.detail(id),
    queryFn: () => jobsApi.get(id),
    enabled: Boolean(id),
    refetchInterval: (query) => (query.state.data?.active_tasks.length ? POLL_MS : false),
  })
}

export function useUpdateJob(id) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (changes) => jobsApi.update(id, changes),
    onSuccess: (job) => {
      queryClient.setQueryData(queryKeys.jobs.detail(id), job)
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all() })
    },
    onError: (error) => toast.error(error.message),
  })
}

/** Quick state change from a list row (save / skip / restore). */
export function useSetJobState() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, state }) => jobsApi.update(id, { state }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all() }),
    onError: (error) => toast.error(error.message),
  })
}

export function useSuggestedRoles() {
  return useQuery({ queryKey: queryKeys.jobs.suggestedRoles(), queryFn: jobsApi.suggestedRoles })
}

export function useRecentSearches() {
  return useQuery({
    queryKey: queryKeys.jobs.searches(),
    queryFn: jobsApi.searches,
    refetchInterval: (query) =>
      query.state.data?.some((run) => RUN_ACTIVE.includes(run.status)) ? POLL_MS : false,
  })
}

/** One search run; polls until it has finished, then refreshes the job list. */
export function useSearchRun(id) {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: queryKeys.jobs.searchRun(id),
    enabled: Boolean(id),
    queryFn: async () => {
      const run = await jobsApi.searchRun(id)
      if (!RUN_ACTIVE.includes(run.status)) {
        queryClient.invalidateQueries({ queryKey: queryKeys.jobs.lists() })
        queryClient.invalidateQueries({ queryKey: queryKeys.jobs.counts() })
        queryClient.invalidateQueries({ queryKey: queryKeys.jobs.searches() })
      }
      return run
    },
    refetchInterval: (query) =>
      !query.state.data || RUN_ACTIVE.includes(query.state.data.status) ? POLL_MS : false,
  })
}

export function isRunActive(run) {
  return RUN_ACTIVE.includes(run?.status)
}

export function useLoadMore(runId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => jobsApi.loadMore(runId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.jobs.searchRun(runId) }),
    onError: (error) => toast.error(error.message),
  })
}

export function useExportJobs() {
  return useMutation({
    mutationFn: jobsApi.exportCsv,
    onSuccess: (name) => toast.success(`Downloaded ${name}`),
    onError: (error) => toast.error(error.message),
  })
}

export function useStartSearch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: jobsApi.search,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.jobs.searches() }),
  })
}

/** "Read the job page" task: follows it and refreshes the job when done. */
export function useFetchDescription(jobId, runningTaskId) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => jobsApi.fetchDescription(jobId),
    onError: (error) => toast.error(error.message),
  })
  const taskId = mutation.data?.task_id ?? runningTaskId ?? null
  const task = useTaskPolling(taskId).data
  const status = task?.status

  useEffect(() => {
    if (!task || isActive(task)) return
    queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all() })
    if (status === 'succeeded' && mutation.data) toast.success('Full description added.')
    // eslint-disable-next-line react-hooks/exhaustive-deps -- react once per finished task
  }, [task?.id, status])

  return { start: () => mutation.mutate(), task, running: mutation.isPending || isActive(task) }
}

// ---------- match scores (Phase 9, on demand) ----------

/** Follow one background task and refresh all job data when it finishes. */
function useFollowTask(taskId, { onSuccess } = {}) {
  const queryClient = useQueryClient()
  const task = useTaskPolling(taskId).data
  const status = task?.status
  useEffect(() => {
    if (!task || isActive(task)) return
    queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all() })
    if (status === 'succeeded') onSuccess?.(task)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- react once per finished task
  }, [task?.id, status])
  return task
}

/** "Get match score" for one job. Cached scores come back at once (no task). */
export function useAnalyzeJob(jobId, runningTaskId) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (force) => jobsApi.analyze(jobId, force),
    onSuccess: (started) => {
      if (started.cached) queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all() })
    },
    onError: (error) => toast.error(error.message),
  })
  const task = useFollowTask(mutation.data?.task_id ?? runningTaskId ?? null)
  return {
    start: (force = false) => mutation.mutate(force),
    task,
    running: mutation.isPending || isActive(task),
  }
}

export function useAnalysisSummary(filters, { enabled = true } = {}) {
  return useQuery({
    queryKey: queryKeys.jobs.analysisSummary(filters),
    queryFn: () => jobsApi.analysisSummary(filters),
    enabled,
    retry: false, // 409 RESUME_REQUIRED is an answer, not a glitch
  })
}

/** "Score all" for a view; `onDone` runs after the batch task has finished. */
export function useAnalyzeBatch({ onDone } = {}) {
  const mutation = useMutation({
    mutationFn: jobsApi.analyzeBatch,
    onSuccess: (started) => {
      if (!started.task_id) toast.info('Everything here already has a match score.')
    },
    onError: (error) => toast.error(error.message),
  })
  const task = useFollowTask(mutation.data?.task_id ?? null, {
    onSuccess: (finished) => {
      const r = finished.result ?? {}
      if (r.stopped) toast.warning(`Stopped after ${r.scored} jobs: ${r.stopped}`)
      else toast.success(`Scored ${r.scored} job${r.scored === 1 ? '' : 's'}.`)
      onDone?.(finished)
    },
  })
  return {
    start: (filters) => mutation.mutate(filters),
    task,
    running: mutation.isPending || isActive(task),
  }
}

// ---------- documents (Phase 10) ----------

export function useJobDocuments(jobId) {
  return useQuery({
    queryKey: queryKeys.jobs.documents(jobId),
    queryFn: () => jobsApi.documents(jobId),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (query.state.data?.active_tasks.length ? POLL_MS : false),
  })
}

/** Start "tailored resume" or "cover letter" and follow the task. */
export function useGenerateDocument(start, { runningTaskId, label }) {
  const mutation = useMutation({
    mutationFn: start,
    onError: (error) => toast.error(error.message),
  })
  const task = useFollowTask(mutation.data?.task_id ?? runningTaskId ?? null, {
    onSuccess: () => toast.success(`${label} ready.`),
  })
  return {
    start: (...args) => mutation.mutate(...args),
    task,
    running: mutation.isPending || isActive(task),
  }
}

function useSaveDocument(mutationFn, success) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (docs) => {
      queryClient.setQueryData(queryKeys.jobs.documents(docs.job_id), docs)
      toast.success(success)
    },
    onError: (error) => toast.error(error.message),
  })
}

export const useEditTailored = () =>
  useSaveDocument(
    ({ versionId, parsed }) => jobsApi.editTailored(versionId, parsed),
    'Tailored resume saved — PDF updated.',
  )

export const useEditCoverLetter = () =>
  useSaveDocument(
    ({ letterId, changes }) => jobsApi.editCoverLetter(letterId, changes),
    'Cover letter saved.',
  )

export function useScanText() {
  return useMutation({ mutationFn: jobsApi.scanText })
}

// ---------- saved searches ----------

export function useSavedSearches() {
  return useQuery({ queryKey: queryKeys.jobs.saved(), queryFn: savedSearchesApi.list })
}

function useSavedMutation(mutationFn, success) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: () => {
      if (success) toast.success(success)
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs.saved() })
    },
  })
}

export const useCreateSavedSearch = () =>
  useSavedMutation(savedSearchesApi.create, 'Saved search created.')

export const useUpdateSavedSearch = () =>
  useSavedMutation(({ id, changes }) => savedSearchesApi.update(id, changes))

export const useDeleteSavedSearch = () =>
  useSavedMutation(savedSearchesApi.remove, 'Saved search deleted.')

export function useRunSavedSearch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: savedSearchesApi.run,
    onSuccess: () => {
      toast.info('Search started — it runs in the background.')
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs.saved() })
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs.searches() })
    },
    onError: (error) => toast.error(error.message),
  })
}
