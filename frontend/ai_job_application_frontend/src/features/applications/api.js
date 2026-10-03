import { api } from '@/api/client'

/** status may be a list → repeated ?status=…&status=… */
export function toQuery({ statuses = [], ...rest } = {}) {
  const search = new URLSearchParams()
  for (const status of statuses) search.append('status', status)
  for (const [key, value] of Object.entries(rest)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  return search.toString()
}

export const applicationsApi = {
  list: (filters) => api.get(`/applications?${toQuery(filters)}`),
  counts: () => api.get('/applications/counts'),
  get: (id) => api.get(`/applications/${id}`),
  forJob: (jobId) => api.get(`/jobs/${jobId}/application`),
  create: (jobId, body) => api.post(`/jobs/${jobId}/applications`, body),
  update: (id, changes) => api.patch(`/applications/${id}`, changes),
  move: (id, toStatus, note) =>
    api.post(`/applications/${id}/status`, { to_status: toStatus, note: note || null }),
  markApplied: (id, note) => api.post(`/applications/${id}/mark-applied`, { note: note || null }),
  exportCsv: (filters) =>
    api.download(`/applications/export.csv?${toQuery(filters)}`, 'applications.csv'),
}

export const STATUS_LABELS = {
  ready_to_apply: 'Ready to apply',
  waiting_for_approval: 'Waiting for approval',
  approved: 'Approved',
  sending: 'Sending',
  applied: 'Applied',
  responded: 'Responded',
  interview: 'Interview',
  offer: 'Offer',
  rejected_by_user: 'Not sent',
  failed: 'Sending failed',
  rejected: 'Rejected',
  no_response: 'No response',
  withdrawn: 'Withdrawn',
}

export const STATUS_VARIANT = {
  ready_to_apply: 'outline',
  waiting_for_approval: 'warning',
  approved: 'default',
  sending: 'warning',
  applied: 'default',
  responded: 'success',
  interview: 'success',
  offer: 'success',
  rejected_by_user: 'outline',
  failed: 'destructive',
  rejected: 'destructive',
  no_response: 'outline',
  withdrawn: 'outline',
}

/** Kanban columns (statuses grouped by stage). */
export const BOARD_COLUMNS = [
  { key: 'prepare', label: 'To do', statuses: ['ready_to_apply', 'rejected_by_user'] },
  {
    key: 'outbox',
    label: 'Outbox',
    statuses: ['waiting_for_approval', 'approved', 'sending', 'failed'],
  },
  { key: 'applied', label: 'Applied', statuses: ['applied', 'no_response'] },
  { key: 'talking', label: 'In process', statuses: ['responded', 'interview'] },
  { key: 'offer', label: 'Offer', statuses: ['offer'] },
  { key: 'closed', label: 'Closed', statuses: ['rejected', 'withdrawn'] },
]

export const CHANNEL_LABELS = {
  portal: 'Company site (portal)',
  email: 'Email',
  referral: 'Referral',
}

/** Wording for a move button: "Mark as interview" reads oddly, so use verbs. */
export const MOVE_LABELS = {
  waiting_for_approval: 'Send for approval',
  approved: 'Approve',
  ready_to_apply: 'Back to ready',
  applied: 'Mark as applied',
  responded: 'They responded',
  interview: 'Interview',
  offer: 'Offer received',
  rejected_by_user: 'Do not send',
  rejected: 'Rejected',
  no_response: 'No response',
  withdrawn: 'Withdraw',
}
