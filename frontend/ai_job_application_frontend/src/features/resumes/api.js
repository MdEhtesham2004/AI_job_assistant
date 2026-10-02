import { api } from '@/api/client'

export const resumesApi = {
  overview: () => api.get('/resumes'),
  upload: (file) => {
    const body = new FormData()
    body.append('file', file)
    return api.post('/resumes/upload', body)
  },
  version: (id) => api.get(`/resumes/versions/${id}`),
  activate: (id) => api.post(`/resumes/versions/${id}/activate`),
  parse: (id) => api.post(`/resumes/versions/${id}/parse`),
  ats: (id) => api.post(`/resumes/versions/${id}/ats`),
  improve: (id) => api.post(`/resumes/versions/${id}/improve`),
  linkedin: (id) => api.post(`/resumes/versions/${id}/linkedin-summary`),
}

export const PDF_MIME = 'application/pdf'
export const MAX_RESUME_BYTES = 5 * 1024 * 1024
const ALLOWED = ['.pdf', '.docx']

/** Quick check before uploading; the server checks the file contents again. */
export function checkResumeFile(file) {
  const name = file.name.toLowerCase()
  if (!ALLOWED.some((ext) => name.endsWith(ext))) return 'Only PDF and DOCX files are supported.'
  if (file.size > MAX_RESUME_BYTES) return 'The file is larger than 5 MB.'
  if (file.size === 0) return 'The file is empty.'
  return null
}

export const KIND_LABELS = { master: 'Uploaded', improved: 'Improved', tailored: 'Tailored' }
