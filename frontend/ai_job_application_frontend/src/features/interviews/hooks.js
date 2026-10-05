import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { queryKeys } from '@/api/queryKeys'

import { interviewsApi } from './api'

const WORKING = ['planning', 'reporting']

export function useInterviews(jobId) {
  return useQuery({
    queryKey: queryKeys.interviews.list(jobId),
    queryFn: () => interviewsApi.list(jobId),
  })
}

/** One interview; polls while the AI is writing the plan or the report. */
export function useInterview(id) {
  return useQuery({
    queryKey: queryKeys.interviews.detail(id),
    queryFn: () => interviewsApi.get(id),
    enabled: Boolean(id),
    refetchInterval: (query) => (WORKING.includes(query.state.data?.status) ? 2000 : false),
  })
}

function useRefresh(id) {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.interviews.all() })
    if (id) queryClient.invalidateQueries({ queryKey: queryKeys.interviews.detail(id) })
    queryClient.invalidateQueries({ queryKey: queryKeys.usage() })
  }
}

export function useCreateInterview(jobId) {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (body) => interviewsApi.create(jobId, body),
    onSuccess: refresh,
    onError: (error) => toast.error(error.message),
  })
}

export function useEditTurn(id) {
  const refresh = useRefresh(id)
  return useMutation({
    mutationFn: ({ seq, text }) => interviewsApi.editTurn(id, seq, text),
    onSuccess: () => {
      refresh()
      toast.success('Answer corrected.')
    },
    onError: (error) => toast.error(error.message),
  })
}

export function useStartReport(id) {
  const refresh = useRefresh(id)
  return useMutation({
    mutationFn: () => interviewsApi.report(id),
    onSuccess: refresh,
    onError: (error) => toast.error(error.message),
  })
}

export function useDeleteInterview(id) {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: () => interviewsApi.remove(id),
    onSuccess: () => {
      refresh()
      toast.success('Interview deleted.')
    },
    onError: (error) => toast.error(error.message),
  })
}

export { useRefresh as useRefreshInterview }
