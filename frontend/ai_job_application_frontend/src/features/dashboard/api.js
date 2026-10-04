import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'

export const dashboardApi = {
  get: () => api.get('/dashboard'),
  usage: () => api.get('/usage'),
}

export function useDashboard() {
  return useQuery({ queryKey: queryKeys.dashboard.summary(), queryFn: dashboardApi.get })
}

/** This month's job searches, LinkedIn fetches and AI spend vs. the limits. */
export function useUsage() {
  return useQuery({ queryKey: queryKeys.usage(), queryFn: dashboardApi.usage })
}

/** Same groups (and order) as the Applications board. */
export const STAGES = [
  { key: 'to_do', label: 'To do' },
  { key: 'outbox', label: 'Outbox' },
  { key: 'applied', label: 'Applied' },
  { key: 'in_process', label: 'In process' },
  { key: 'offer', label: 'Offer' },
  { key: 'closed', label: 'Closed' },
]

export const SOURCE_LABELS = {
  jsearch: 'Job search',
  linkedin_post: 'LinkedIn posts',
  manual: 'Pasted / scanned',
  legacy_sheet: 'Old system import',
}

export const RESUME_LABELS = {
  master: 'Master resume',
  improved: 'Improved resume',
  tailored: 'Tailored resume',
  none: 'No resume',
}
