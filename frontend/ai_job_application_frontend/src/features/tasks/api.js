import { api } from '@/api/client'

export const tasksApi = {
  list: (page = 1) => api.get(`/tasks?page=${page}&page_size=20`),
  get: (id) => api.get(`/tasks/${id}`),
  createTestPdf: () => api.post('/tasks/test-pdf'),
  createTestFailure: () => api.post('/admin/system/test-failure'),
  createTestAi: () => api.post('/admin/system/test-ai'),
}

export const ACTIVE_STATUSES = ['queued', 'running']

export function isActive(task) {
  return ACTIVE_STATUSES.includes(task?.status)
}

const TASK_LABELS = {
  test_pdf: 'Test PDF',
  test_failure: 'Failure test',
  ai_test: 'AI connection test',
  resume_parse: 'Resume parsing',
  resume_ats: 'ATS analysis',
  resume_improve: 'Improved resume',
  resume_linkedin: 'LinkedIn summary',
  job_search: 'Job search',
  job_fetch_page: 'Job description fetch',
  job_analyze: 'Match score',
  job_analyze_batch: 'Batch match scoring',
}

export function taskLabel(type) {
  return TASK_LABELS[type] ?? type
}
