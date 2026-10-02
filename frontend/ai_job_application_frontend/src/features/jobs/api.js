import { api } from '@/api/client'

/** Drop empty values so the URL only carries active filters. */
export function toQuery(params) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '' || value === false) continue
    search.set(key, String(value))
  }
  return search.toString()
}

export const jobsApi = {
  search: (body) => api.post('/jobs/search', body),
  searches: () => api.get('/jobs/searches'),
  searchRun: (id) => api.get(`/jobs/searches/${id}`),
  loadMore: (id) => api.post(`/jobs/searches/${id}/more`),
  exportCsv: (filters) => api.download(`/jobs/export.csv?${toQuery(filters)}`, 'jobs.csv'),
  suggestedRoles: () => api.get('/jobs/suggested-roles'),
  counts: () => api.get('/jobs/counts'),
  list: (filters) => api.get(`/jobs?${toQuery(filters)}`),
  get: (id) => api.get(`/jobs/${id}`),
  update: (id, changes) => api.patch(`/jobs/${id}`, changes),
  fetchDescription: (id) => api.post(`/jobs/${id}/fetch-description`),
  // Phase 9 — match scores, only when asked
  analyze: (id, force = false) => api.post(`/jobs/${id}/analyze`, force ? { force } : undefined),
  analysisSummary: (filters) => api.get(`/jobs/analysis-summary?${toQuery(filters)}`),
  analyzeBatch: (filters) => api.post(`/jobs/analyze-batch?${toQuery(filters)}`),
  scanText: (body) => api.post('/jobs/scan-text', body),
}

export const DECISION_LABELS = {
  use_master: 'Apply with your resume',
  tailor: 'Tailor first',
  skip: 'Weak match',
}

/** Rough AI cost per scored job, shown before batch scoring (live: ≈ $0.001). */
export const COST_PER_SCORE_USD = 0.001

/** Filters for "the current view" — the list's filters without paging. */
export function viewFilters(filters) {
  // eslint-disable-next-line no-unused-vars -- paging is not part of the view
  const { page, page_size, ...view } = filters
  return view
}

export const savedSearchesApi = {
  list: () => api.get('/saved-searches'),
  create: (body) => api.post('/saved-searches', body),
  update: (id, changes) => api.patch(`/saved-searches/${id}`, changes),
  remove: (id) => api.delete(`/saved-searches/${id}`),
  run: (id) => api.post(`/saved-searches/${id}/run`),
}

export const EXPERIENCE_OPTIONS = [
  { value: '', label: 'Any experience' },
  { value: 'no_experience', label: 'No experience (fresher)' },
  { value: 'under_3_years_experience', label: 'Under 3 years' },
  { value: 'more_than_3_years_experience', label: 'More than 3 years' },
  { value: 'no_degree', label: 'No degree required' },
]

export const PAGE_OPTIONS = [
  { value: 1, label: '1 page (~10 jobs)' },
  { value: 2, label: '2 pages (~20 jobs)' },
  { value: 3, label: '3 pages (~30 jobs)' },
]

export const DATE_POSTED_OPTIONS = [
  { value: 'today', label: 'Today' },
  { value: '3days', label: 'Last 3 days' },
  { value: 'week', label: 'Last week' },
  { value: 'month', label: 'Last month' },
  { value: 'all', label: 'Any time' },
]

export const STATE_LABELS = {
  new: 'New',
  saved: 'Saved',
  analyzed: 'Analyzed',
  skipped: 'Skipped',
  archived: 'Archived',
}

export const QUALITY_LABELS = {
  complete: 'Full description',
  partial: 'Partial description',
  missing: 'No description',
}

/** Schedules offered in the UI; anything else is shown as its cron text. */
export const SCHEDULE_PRESETS = [
  { cron: '0 8 * * *', label: 'Every day at 08:00' },
  { cron: '0 8,18 * * *', label: 'Twice a day (08:00 and 18:00)' },
  { cron: '0 9 * * 1-5', label: 'Weekdays at 09:00' },
  { cron: '0 9 * * 1', label: 'Every Monday at 09:00' },
]

export function describeSchedule(cron) {
  return SCHEDULE_PRESETS.find((preset) => preset.cron === cron)?.label ?? `Custom: ${cron}`
}

export function experienceLabel(value) {
  return EXPERIENCE_OPTIONS.find((option) => option.value === value)?.label ?? null
}

/** "React Native · in Hyderabad · remote · Under 3 years" */
export function describeQuery(query) {
  return [
    query.keywords,
    query.location && `in ${query.location}`,
    query.remote_only && 'remote',
    query.experience && experienceLabel(query.experience),
  ]
    .filter(Boolean)
    .join(' · ')
}
