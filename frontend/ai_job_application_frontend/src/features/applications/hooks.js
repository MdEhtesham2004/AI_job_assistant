import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { queryKeys } from '@/api/queryKeys'

import { applicationsApi } from './api'

export function useApplications(filters) {
  return useQuery({
    queryKey: queryKeys.applications.list(filters),
    queryFn: () => applicationsApi.list(filters),
    placeholderData: keepPreviousData,
  })
}

export function useApplicationCounts() {
  return useQuery({ queryKey: queryKeys.applications.counts(), queryFn: applicationsApi.counts })
}

export function useApplication(id) {
  return useQuery({
    queryKey: queryKeys.applications.detail(id),
    queryFn: () => applicationsApi.get(id),
    enabled: Boolean(id),
  })
}

export function useJobApplication(jobId) {
  return useQuery({
    queryKey: queryKeys.applications.forJob(jobId),
    queryFn: () => applicationsApi.forJob(jobId),
    enabled: Boolean(jobId),
  })
}

/** Every application mutation returns the full detail; cache it and refresh lists. */
function useApplicationMutation(mutationFn, success) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (detail) => {
      queryClient.setQueryData(queryKeys.applications.detail(detail.id), detail)
      queryClient.invalidateQueries({ queryKey: queryKeys.applications.all() })
      if (success) toast.success(typeof success === 'function' ? success(detail) : success)
    },
    onError: (error) => toast.error(error.message),
  })
}

export const useCreateApplication = () =>
  useApplicationMutation(
    ({ jobId, body }) => applicationsApi.create(jobId, body),
    'Application prepared.',
  )

export const useUpdateApplication = () =>
  useApplicationMutation(({ id, changes }) => applicationsApi.update(id, changes), 'Saved.')

export const useMoveApplication = () =>
  useApplicationMutation(
    ({ id, toStatus, note }) => applicationsApi.move(id, toStatus, note),
    'Status updated.',
  )

export const useMarkApplied = () =>
  useApplicationMutation(
    ({ id, note }) => applicationsApi.markApplied(id, note),
    'Marked as applied.',
  )

export function useExportApplications() {
  return useMutation({
    mutationFn: applicationsApi.exportCsv,
    onSuccess: (name) => toast.success(`Downloaded ${name}`),
    onError: (error) => toast.error(error.message),
  })
}
