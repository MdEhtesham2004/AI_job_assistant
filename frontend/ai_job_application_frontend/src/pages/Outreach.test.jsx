import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { GmailCard } from '@/features/outreach/components/GmailCard'
import { RepliesCard } from '@/features/outreach/components/RepliesCard'
import { jsonResponse, mockApi, renderWithProviders } from '@/test/utils'

import ApplicationDetailPage from './ApplicationDetailPage'
import ContactsPage from './ContactsPage'
import OutboxPage from './OutboxPage'

afterEach(() => vi.unstubAllGlobals())

const CONNECTED = {
  configured: true,
  connected: true,
  status: 'connected',
  account_email: 'asha@gmail.com',
  can_send: true,
  can_read: true,
  connected_at: '2026-10-03T09:00:00Z',
}

function makeContact(overrides = {}) {
  return {
    id: 'c1',
    email: 'priya.hr@gmail.com',
    name: 'Priya',
    role_title: 'HR Manager at ABC Technologies',
    company: 'ABC Technologies',
    source: 'linkedin_post',
    source_url: 'https://www.linkedin.com/posts/p1',
    source_excerpt: '…share your resume at priya.hr@gmail.com…',
    verification: 'valid',
    verified_at: '2026-10-03T09:00:00Z',
    approval: 'pending',
    approved_at: null,
    blocked: false,
    job: { id: 'j1', title: 'React Native Developer', company: 'ABC Technologies' },
    created_at: '2026-10-03T09:00:00Z',
    ...overrides,
  }
}

function makeEmail(overrides = {}) {
  return {
    id: 'e1',
    status: 'draft',
    from_address: 'asha@gmail.com',
    to_address: 'priya.hr@gmail.com',
    subject: 'Application for React Native Developer – Asha Verma',
    body_text: 'Dear Priya,\n\nI am applying…\n\nBest regards,\nAsha Verma',
    approved_at: null,
    scheduled_for: null,
    sent_at: null,
    error: null,
    gmail_thread_id: null,
    contact: {
      id: 'c1',
      email: 'priya.hr@gmail.com',
      name: 'Priya',
      approval: 'approved',
      verification: 'valid',
    },
    application: {
      id: 'a1',
      status: 'waiting_for_approval',
      job_id: 'j1',
      job_title: 'React Native Developer',
      company: 'ABC Technologies',
    },
    attachments: [
      {
        id: 'f1',
        file_name: 'Asha Verma - Resume.pdf',
        mime_type: 'application/pdf',
        file_size: 2048,
        download_url: '/api/v1/files/t',
      },
    ],
    warnings: [],
    updated_at: '2026-10-03T09:00:00Z',
    ...overrides,
  }
}

const page = (items) => ({ items, total: items.length, page: 1, page_size: 100 })

const AUTOMATION = {
  keywords: ['Data Scientist'],
  ready: true,
  not_ready_reason: null,
  saved_ready: 2,
  fetch_allowed: false,
  fetch_problem: null,
  max_jobs: 5,
  last_run: null,
}

describe('GmailCard', () => {
  it('starts the Google consent when not connected', async () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    mockApi({
      'GET /integrations/gmail': {
        ...CONNECTED,
        connected: false,
        status: null,
        account_email: null,
      },
      'POST /integrations/gmail/connect': { auth_url: 'https://accounts.google.com/o/oauth2/x' },
    })
    renderWithProviders(<GmailCard />)

    await userEvent.click(await screen.findByRole('button', { name: 'Connect Gmail' }))

    await vi.waitFor(() =>
      expect(assign).toHaveBeenCalledWith('https://accounts.google.com/o/oauth2/x'),
    )
  })

  it('shows the connected account and what it may do', async () => {
    mockApi({ 'GET /integrations/gmail': CONNECTED })
    renderWithProviders(<GmailCard />)

    expect(await screen.findByText('asha@gmail.com')).toBeInTheDocument()
    expect(screen.getByText('Can send')).toBeInTheDocument()
    expect(screen.getByText('Can read replies')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Disconnect' })).toBeInTheDocument()
  })
})

describe('ContactsPage', () => {
  it('shows the evidence and approves a contact', async () => {
    const fetchMock = mockApi({
      'GET /contacts': page([makeContact()]),
      'GET /contacts/counts': { counts: { pending: 1, approved: 0, rejected: 0 }, total: 1 },
      'GET /do-not-contact': [],
      'GET /users/me/settings': { linkedin_source_enabled: false },
      'PATCH /contacts/c1': (_, init) =>
        jsonResponse(makeContact({ approval: JSON.parse(init.body).approval })),
    })
    renderWithProviders(<ContactsPage />)

    const row = (await screen.findByText('priya.hr@gmail.com')).closest('li')
    expect(within(row).getByText('…share your resume at priya.hr@gmail.com…')).toBeInTheDocument()
    expect(within(row).getByRole('link', { name: /View post/ })).toHaveAttribute(
      'href',
      'https://www.linkedin.com/posts/p1',
    )
    expect(within(row).getByText('Needs approval')).toBeInTheDocument()
    expect(screen.getByText(/This source is off/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Search' })).toBeDisabled()

    await userEvent.click(within(row).getByRole('button', { name: 'Approve' }))

    await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
      expect(JSON.parse(call[1].body)).toEqual({ approval: 'approved' })
    })
  })

  it('searches LinkedIn hiring posts when the source is on', async () => {
    const fetchMock = mockApi({
      'GET /contacts': page([]),
      'GET /contacts/counts': { counts: { pending: 0, approved: 0, rejected: 0 }, total: 0 },
      'GET /do-not-contact': [],
      'GET /users/me/settings': { linkedin_source_enabled: true },
      'POST /contacts/discover': { task_id: 't1' },
      'GET /tasks/t1': { id: 't1', type: 'contact_discover', status: 'running', progress: 40 },
    })
    renderWithProviders(<ContactsPage />)

    const keyword = await screen.findByLabelText('Role or skill')
    await vi.waitFor(() => expect(keyword).toBeEnabled()) // after the settings have loaded
    await userEvent.type(keyword, 'React Native')
    await userEvent.selectOptions(screen.getByLabelText('Posted within'), 'month')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByRole('progressbar')).toHaveAttribute('aria-valuenow', '40')
    const post = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/contacts/discover'))
    expect(JSON.parse(post[1].body)).toEqual({
      keyword: 'React Native',
      posted_limit: 'month',
      max_posts: 50,
    })
  })
})

describe('OutboxPage', () => {
  const SUMMARY = {
    counts: { draft: 2, queued: 0, sending: 0, sent: 3, failed: 0, bounced: 0, rejected: 0 },
    sent_today: 3,
    daily_cap: 25,
    interval_seconds: 90,
    next_slot: '2026-10-03T10:00:00Z',
    gmail_connected: true,
    gmail_email: 'asha@gmail.com',
  }

  it('approves the selected drafts in one go', async () => {
    const fetchMock = mockApi({
      'GET /outbox': page([makeEmail(), makeEmail({ id: 'e2', to_address: 'hr@acme.com' })]),
      'GET /outbox/summary': SUMMARY,
      'POST /emails/approve-batch': { approved: ['e1', 'e2'], errors: {} },
    })
    renderWithProviders(<OutboxPage />)

    expect(await screen.findByText('3 / 25')).toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: 'Select all' }))
    await userEvent.click(screen.getByRole('button', { name: 'Approve selected (2)' }))

    await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/approve-batch'))
      // The cards show each contact's evidence, so pending contacts are approved too.
      expect(JSON.parse(call[1].body)).toEqual({ email_ids: ['e1', 'e2'], approve_contacts: true })
    })
  })

  it('saves edits before a draft can be approved', async () => {
    const fetchMock = mockApi({
      'GET /outbox': page([makeEmail()]),
      'GET /outbox/summary': SUMMARY,
      'PUT /emails/e1': (_, init) => jsonResponse(makeEmail(JSON.parse(init.body))),
    })
    renderWithProviders(<OutboxPage />)

    const subject = await screen.findByLabelText('Subject')
    expect(screen.getByRole('link', { name: /Asha Verma - Resume.pdf/ })).toBeInTheDocument()
    await userEvent.clear(subject)
    await userEvent.type(subject, 'Application – React Native Developer')

    expect(screen.getByRole('button', { name: 'Approve & send' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT')
      expect(JSON.parse(call[1].body).subject).toBe('Application – React Native Developer')
    })
  })
})

describe('Email on the application page', () => {
  it('drafts the email to the chosen approved contact', async () => {
    const fetchMock = mockApi({
      'GET /applications/a1': {
        id: 'a1',
        job: {
          id: 'j1',
          title: 'React Native Developer',
          company: 'ABC Technologies',
          location: null,
          apply_url: null,
        },
        channel: 'email',
        status: 'ready_to_apply',
        next_action: null,
        applied_at: null,
        last_status_at: '2026-10-03T09:00:00Z',
        created_at: '2026-10-03T09:00:00Z',
        match_score: null,
        resume: null,
        cover_letter: null,
        contact: null,
        history: [],
        allowed_next: ['withdrawn'],
      },
      'GET /applications/a1/email': () => jsonResponse(null),
      'GET /integrations/gmail': CONNECTED,
      'GET /contacts': page([
        makeContact({ id: 'c9', email: 'other@acme.com', approval: 'approved', job: null }),
        makeContact({ approval: 'approved' }),
      ]),
      'POST /applications/a1/email/draft': { task_id: 't1' },
      'GET /tasks/t1': { id: 't1', type: 'email_draft', status: 'running', progress: 10 },
    })
    renderWithProviders(
      <Routes>
        <Route path="/applications/:applicationId" element={<ApplicationDetailPage />} />
      </Routes>,
      { route: '/applications/a1' },
    )

    // This job's contact is offered first.
    const sendTo = await screen.findByLabelText('Send to')
    await vi.waitFor(() => expect(sendTo).toHaveValue('c1'))
    await vi.waitFor(() =>
      expect(screen.getByRole('button', { name: 'Write email' })).toBeEnabled(),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Write email' }))

    await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/email/draft'))
      expect(JSON.parse(call[1].body)).toEqual({ contact_id: 'c1' })
    })
    expect(screen.queryByRole('button', { name: 'Send for approval' })).not.toBeInTheDocument()
  })
})

describe('Phase 13: approval queue, automation and replies', () => {
  it('approves a new contact together with its email', async () => {
    const fetchMock = mockApi({
      'GET /outbox': page([
        makeEmail({
          contact: {
            ...makeEmail().contact,
            approval: 'pending',
            source: 'linkedin_post',
            source_url: 'https://www.linkedin.com/posts/p1',
            source_excerpt: '…share your resume at priya.hr@gmail.com…',
            role_title: 'HR Manager',
          },
          application: { ...makeEmail().application, match_score: 81 },
        }),
      ]),
      'GET /outbox/summary': {
        counts: { draft: 1 },
        sent_today: 0,
        daily_cap: 25,
        interval_seconds: 90,
        next_slot: null,
        gmail_connected: true,
        gmail_email: 'asha@gmail.com',
      },
      'GET /automation': {
        ...AUTOMATION,
        fetch_allowed: true,
        last_run: {
          task_id: 't0',
          status: 'succeeded',
          progress: 100,
          result: {
            mode: 'fetch',
            posts: 20,
            candidates: 3,
            scored: 3,
            reused_scores: 0,
            below_minimum: 2,
            prepared: 1,
            empty_keywords: [],
            skipped: [],
            stopped: null,
          },
          error: null,
          created_at: '2026-10-03T09:00:00Z',
          finished_at: '2026-10-03T09:04:00Z',
        },
      },
      'POST /emails/e1/approve': makeEmail({ status: 'queued' }),
    })
    renderWithProviders(<OutboxPage />)

    expect(await screen.findByText('New contact — not approved yet')).toBeInTheDocument()
    expect(screen.getByText('…share your resume at priya.hr@gmail.com…')).toBeInTheDocument()
    expect(screen.getByText('81% match')).toBeInTheDocument()
    expect(await screen.findByText('1 ready for approval')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Approve contact & send' }))

    await vi.waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).endsWith('/emails/e1/approve?approve_contact=true'),
        ),
      ).toBe(true),
    )
  })

  const runBody = (fetchMock) => {
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/automation/run'))
    return call && JSON.parse(call[1].body)
  }

  it('automates saved jobs; fetching is locked until the admin allows it', async () => {
    const fetchMock = mockApi({
      'GET /outbox': page([]),
      'GET /outbox/summary': { counts: {}, sent_today: 0, daily_cap: 25, interval_seconds: 90 },
      'GET /automation': AUTOMATION,
      'POST /automation/run': { task_id: 't1' },
    })
    renderWithProviders(<OutboxPage />)

    const fetchButton = await screen.findByRole('button', { name: /Fetch new jobs & automate/ })
    expect(fetchButton).toBeDisabled()
    expect(screen.getByText(/locked by your admin/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Automate saved jobs (2)' }))

    await vi.waitFor(() => expect(runBody(fetchMock)).toEqual({ mode: 'saved' }))
  })

  it('suggests fetching when no saved job is ready and asks before using credit', async () => {
    const fetchMock = mockApi({
      'GET /outbox': page([]),
      'GET /outbox/summary': { counts: {}, sent_today: 0, daily_cap: 25, interval_seconds: 90 },
      'GET /automation': { ...AUTOMATION, saved_ready: 0, fetch_allowed: true },
      'POST /automation/run': { task_id: 't1' },
    })
    renderWithProviders(<OutboxPage />)

    expect(await screen.findByRole('button', { name: 'Automate saved jobs (0)' })).toBeDisabled()
    expect(screen.getByText(/No saved job is ready/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Fetch new jobs & automate/ }))
    expect(screen.getByRole('dialog', { name: 'Fetch new jobs and automate?' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Fetch & automate' }))

    await vi.waitFor(() => expect(runBody(fetchMock)).toEqual({ mode: 'fetch' }))
  })

  it('shows a reply and lets the user confirm an unsure reading', async () => {
    const fetchMock = mockApi({
      'GET /applications/a1/replies': [
        {
          id: 'r1',
          status: 'received',
          from_address: 'priya@acme.com',
          subject: 'Re: Application',
          body_text: "Let's talk at some point.",
          received_at: '2026-10-03T10:00:00Z',
          classification: {
            id: 'c1',
            category: 'interview_invite',
            confidence: 0.55,
            summary: 'The recruiter would like to talk.',
            suggested_action: 'Reply with 2-3 time slots',
            applied_transition: false,
            user_confirmed: null,
          },
        },
      ],
      'POST /replies/c1/confirm': (_, init) =>
        jsonResponse({ id: 'c1', ...JSON.parse(init.body), applied_transition: true }),
    })
    renderWithProviders(<RepliesCard applicationId="a1" />)

    expect(await screen.findByText('Interview invite')).toBeInTheDocument()
    expect(screen.getByText('55% sure')).toBeInTheDocument()
    expect(screen.getByText('The recruiter would like to talk.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Yes, set to Interview' }))

    await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/replies/c1/confirm'))
      expect(JSON.parse(call[1].body)).toEqual({ accept: true })
    })
  })
})

describe('Email application from an approved contact', () => {
  it('creates the email application and opens it', async () => {
    const fetchMock = mockApi({
      'GET /contacts': page([makeContact({ approval: 'approved' })]),
      'GET /contacts/counts': { counts: { pending: 0, approved: 1, rejected: 0 }, total: 1 },
      'GET /do-not-contact': [],
      'GET /users/me/settings': { linkedin_source_enabled: false },
      'POST /jobs/j1/applications': (_, init) =>
        jsonResponse({ id: 'a9', ...JSON.parse(init.body) }, { status: 201 }),
    })
    renderWithProviders(
      <Routes>
        <Route path="/contacts" element={<ContactsPage />} />
        <Route path="/applications/:applicationId" element={<p>Application page</p>} />
      </Routes>,
      { route: '/contacts?approval=approved' },
    )

    await userEvent.click(await screen.findByRole('button', { name: 'Email application' }))

    expect(await screen.findByText('Application page')).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/jobs/j1/applications'))
    expect(JSON.parse(post[1].body)).toEqual({ channel: 'email', contact_id: 'c1' })
  })
})

describe('Outbox after an automation run', () => {
  it('shows the new drafts as soon as the run finishes', async () => {
    let polls = 0
    const run = (status) => ({
      ...AUTOMATION,
      last_run: {
        task_id: 't1',
        status,
        progress: status === 'running' ? 50 : 100,
        result:
          status === 'running' ? null : { mode: 'saved', candidates: 3, scored: 3, prepared: 1 },
        error: null,
        created_at: '2026-10-03T14:36:00Z',
        finished_at: status === 'running' ? null : '2026-10-03T14:36:19Z',
      },
    })
    mockApi({
      'GET /automation': () => {
        polls += 1 // first answer: running; from the next poll on: finished
        return jsonResponse(run(polls > 1 ? 'succeeded' : 'running'))
      },
      'GET /outbox': () => jsonResponse(page(polls > 1 ? [makeEmail()] : [])),
      'GET /outbox/summary': { counts: {}, sent_today: 0, daily_cap: 25, interval_seconds: 90 },
    })
    renderWithProviders(<OutboxPage />)

    expect(await screen.findByText(/No drafts/)).toBeInTheDocument()
    expect(await screen.findByLabelText('Subject', {}, { timeout: 8000 })).toHaveValue(
      'Application for React Native Developer – Asha Verma',
    )
  })
})

describe('Contacts CSV export', () => {
  it('downloads the contacts of the current tab and search', async () => {
    vi.stubGlobal(
      'URL',
      Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }),
    )
    const fetchMock = mockApi({
      'GET /contacts': page([makeContact({ approval: 'approved' })]),
      'GET /contacts/counts': { counts: { pending: 0, approved: 1, rejected: 0 }, total: 1 },
      'GET /do-not-contact': [],
      'GET /users/me/settings': { linkedin_source_enabled: false },
      'GET /contacts/export.csv': () =>
        new Response('\ufeffEmail\r\n', {
          headers: {
            'Content-Type': 'text/csv',
            'Content-Disposition': 'attachment; filename="contacts-2026-10-03.csv"',
          },
        }),
    })
    renderWithProviders(<ContactsPage />, { route: '/contacts?approval=approved' })

    await screen.findByText('priya.hr@gmail.com')
    await userEvent.type(screen.getByLabelText('Search contacts'), 'priya')
    await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }))

    await vi.waitFor(() => {
      const url = String(fetchMock.mock.calls.find(([u]) => String(u).includes('export.csv'))[0])
      expect(url).toContain('approval=approved')
      expect(url).toContain('q=priya')
    })
  })
})
