import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import { api } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'

/** Admin › Audit log, Analytics, recent errors (Phase 14). */
export const insightsApi = {
  audit: ({ action = '', actorType = '', q = '', page = 1 }) => {
    const search = new URLSearchParams({ page: String(page), page_size: '50' })
    if (action) search.set('action', action)
    if (actorType) search.set('actor_type', actorType)
    if (q) search.set('q', q)
    return api.get(`/admin/audit?${search}`)
  },
  analytics: () => api.get('/admin/analytics'),
  errors: () => api.get('/admin/errors'),
  testError: () => api.post('/admin/system/test-error'),
}

export function useAudit(filters) {
  return useQuery({
    queryKey: queryKeys.admin_insights.audit(filters),
    queryFn: () => insightsApi.audit(filters),
    placeholderData: keepPreviousData,
  })
}

export function useAnalytics() {
  return useQuery({
    queryKey: queryKeys.admin_insights.analytics(),
    queryFn: insightsApi.analytics,
  })
}

export function useRecentErrors() {
  return useQuery({ queryKey: queryKeys.admin_insights.errors(), queryFn: insightsApi.errors })
}

export function useTestError() {
  return useMutation({
    mutationFn: insightsApi.testError,
    // The endpoint fails on purpose: a 500 is the expected answer.
    onError: (error) =>
      error.status === 500
        ? toast.success('Test error raised — check Sentry (if SENTRY_DSN is set) and the API log.')
        : toast.error(error.message),
  })
}
