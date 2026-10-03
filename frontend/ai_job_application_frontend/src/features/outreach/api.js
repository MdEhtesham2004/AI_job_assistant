import { api } from '@/api/client'

function query(params = {}) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) value.forEach((v) => search.append(key, v))
    else search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export const gmailApi = {
  status: () => api.get('/integrations/gmail'),
  connect: () => api.post('/integrations/gmail/connect'),
  disconnect: () => api.delete('/integrations/gmail'),
}

export const contactsApi = {
  list: (filters) => api.get(`/contacts${query(filters)}`),
  counts: () => api.get('/contacts/counts'),
  create: (body) => api.post('/contacts', body),
  update: (id, changes) => api.patch(`/contacts/${id}`, changes),
  verify: (id) => api.post(`/contacts/${id}/verify`),
  remove: (id) => api.delete(`/contacts/${id}`),
  discover: (body) => api.post('/contacts/discover', body),
  blocked: () => api.get('/do-not-contact'),
  block: (body) => api.post('/do-not-contact', body),
  unblock: (id) => api.delete(`/do-not-contact/${id}`),
}

export const emailsApi = {
  forApplication: (applicationId) => api.get(`/applications/${applicationId}/email`),
  draft: (applicationId, contactId) =>
    api.post(`/applications/${applicationId}/email/draft`, { contact_id: contactId ?? null }),
  outbox: (filters) => api.get(`/outbox${query(filters)}`),
  summary: () => api.get('/outbox/summary'),
  edit: (id, changes) => api.put(`/emails/${id}`, changes),
  action: (id, action) => api.post(`/emails/${id}/${action}`),
  approveBatch: (ids) => api.post('/emails/approve-batch', { email_ids: ids }),
}

export const SOURCE_LABELS = {
  user: 'Added by you',
  job_posting: 'Job posting',
  linkedin_post: 'LinkedIn post',
  hunter: 'Hunter.io',
  company_site: 'Company site',
  legacy_import: 'Imported',
}

export const VERIFICATION = {
  valid: { label: 'Accepts email', variant: 'success' },
  risky: { label: 'Risky', variant: 'warning' },
  invalid: { label: 'Cannot receive email', variant: 'destructive' },
  unverified: { label: 'Not checked', variant: 'outline' },
}

export const APPROVAL = {
  pending: { label: 'Needs approval', variant: 'warning' },
  approved: { label: 'Approved', variant: 'success' },
  rejected: { label: 'Rejected', variant: 'outline' },
}

export const EMAIL_STATUS = {
  draft: { label: 'Draft', variant: 'warning' },
  approved: { label: 'Approved', variant: 'default' },
  queued: { label: 'Scheduled', variant: 'default' },
  sending: { label: 'Sending', variant: 'warning' },
  sent: { label: 'Sent', variant: 'success' },
  failed: { label: 'Failed', variant: 'destructive' },
  bounced: { label: 'Bounced', variant: 'destructive' },
  rejected: { label: 'Not sent', variant: 'outline' },
  received: { label: 'Received', variant: 'default' },
}

/** Outbox tabs → email statuses. */
export const OUTBOX_TABS = [
  { key: 'drafts', label: 'Drafts', statuses: ['draft'] },
  { key: 'scheduled', label: 'Scheduled', statuses: ['queued', 'sending'] },
  { key: 'sent', label: 'Sent', statuses: ['sent', 'bounced'] },
  { key: 'failed', label: 'Failed', statuses: ['failed'] },
  { key: 'rejected', label: 'Not sent', statuses: ['rejected'] },
]
