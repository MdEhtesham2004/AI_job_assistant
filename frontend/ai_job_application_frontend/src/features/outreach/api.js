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
  exportCsv: (filters) => api.download(`/contacts/export.csv${query(filters)}`, 'contacts.csv'),
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
  action: (id, action, { approveContact = false } = {}) =>
    api.post(`/emails/${id}/${action}${approveContact ? '?approve_contact=true' : ''}`),
  approveBatch: (ids, approveContacts = false) =>
    api.post('/emails/approve-batch', { email_ids: ids, approve_contacts: approveContacts }),
}

export const automationApi = {
  status: () => api.get('/automation'),
  /** mode: 'saved' (jobs you already have) | 'fetch' (search LinkedIn first) */
  run: (mode) => api.post('/automation/run', { mode }),
  platform: () => api.get('/admin/platform'),
  updatePlatform: (changes) => api.patch('/admin/platform', changes),
}

export const repliesApi = {
  forApplication: (applicationId) => api.get(`/applications/${applicationId}/replies`),
  confirm: (classificationId, accept) =>
    api.post(`/replies/${classificationId}/confirm`, { accept }),
}

export const REPLY_CATEGORY = {
  interview_invite: { label: 'Interview invite', variant: 'success' },
  info_request: { label: 'Asks for information', variant: 'warning' },
  rejection: { label: 'Rejection', variant: 'destructive' },
  offer: { label: 'Offer', variant: 'success' },
  auto_reply: { label: 'Automatic reply', variant: 'outline' },
  other: { label: 'Reply', variant: 'default' },
}

/** What confirming a reply would change the status to. */
export const REPLY_TARGET = {
  interview_invite: 'Interview',
  info_request: 'Responded',
  rejection: 'Rejected',
  offer: 'Offer',
  other: 'Responded',
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
  { key: 'drafts', label: 'Ready for approval', statuses: ['draft'] },
  { key: 'scheduled', label: 'Scheduled', statuses: ['queued', 'sending'] },
  { key: 'sent', label: 'Sent', statuses: ['sent', 'bounced'] },
  { key: 'failed', label: 'Failed', statuses: ['failed'] },
  { key: 'rejected', label: 'Not sent', statuses: ['rejected'] },
]
