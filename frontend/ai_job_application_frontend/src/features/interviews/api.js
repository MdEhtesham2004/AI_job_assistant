import { api } from '@/api/client'

export const interviewsApi = {
  create: (jobId, body) => api.post(`/jobs/${jobId}/interviews`, body),
  list: (jobId) => api.get(jobId ? `/interviews?job_id=${jobId}` : '/interviews'),
  get: (id) => api.get(`/interviews/${id}`),
  session: (id) => api.post(`/interviews/${id}/session`),
  turns: (id, turns) => api.post(`/interviews/${id}/turns`, { turns }),
  editTurn: (id, seq, text) => api.patch(`/interviews/${id}/turns/${seq}`, { text }),
  finish: (id) => api.post(`/interviews/${id}/finish`),
  report: (id) => api.post(`/interviews/${id}/report`),
  remove: (id) => api.delete(`/interviews/${id}`),
}

export const ROUND_OPTIONS = [
  { value: 'mixed', label: 'Mixed (skills, a gap, behavioural)' },
  { value: 'hr', label: 'HR / recruiter screen' },
  { value: 'technical', label: 'Technical' },
  { value: 'behavioral', label: 'Behavioural (STAR)' },
]

export const DIFFICULTY_OPTIONS = [
  { value: 'entry', label: 'Entry level' },
  { value: 'mid', label: 'Mid level' },
  { value: 'senior', label: 'Senior' },
]

export const ROUND_LABELS = Object.fromEntries(
  ROUND_OPTIONS.map((o) => [o.value, o.label.split(' (')[0]]),
)

export const VERDICT = {
  ready: { label: 'Ready for the screen', variant: 'success' },
  almost: { label: 'Almost there', variant: 'warning' },
  practice: { label: 'Needs practice', variant: 'destructive' },
}

export const STATUS_LABELS = {
  planning: 'Preparing questions',
  ready: 'Ready to start',
  in_progress: 'In progress',
  ended: 'Review transcript',
  reporting: 'Writing report',
  completed: 'Report ready',
  failed: 'Failed',
}

/** Default difficulty from the job's experience wording. */
export function guessDifficulty(job) {
  const text = `${job?.title ?? ''} ${job?.experience ?? ''}`.toLowerCase()
  if (/\b(senior|lead|principal|staff|sr\.?)\b/.test(text)) return 'senior'
  if (/\b(junior|intern|fresher|graduate|entry|jr\.?)\b/.test(text)) return 'entry'
  return 'mid'
}

export const formatClock = (seconds) => {
  const s = Math.max(0, Math.round(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
