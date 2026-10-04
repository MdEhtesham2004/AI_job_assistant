import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AccountDataCard } from '@/features/account/AccountDataCard'
import { errorResponse, jsonResponse, makeAuth, mockApi, renderWithProviders } from '@/test/utils'

import AnalyticsPage from './admin/AnalyticsPage'
import AuditLogPage from './admin/AuditLogPage'
import HomePage from './HomePage'
import ImportPage from './ImportPage'
import NotificationsPage from './NotificationsPage'

afterEach(() => vi.unstubAllGlobals())

const DASHBOARD = {
  jobs_found: 42,
  jobs_new_this_week: 7,
  stages: { to_do: 1, outbox: 2, applied: 5, in_process: 2, offer: 1, closed: 3 },
  statuses: {},
  waiting_for_approval: 2,
  applied_total: 11,
  responses: 4,
  response_rate: 0.364,
  interviews: 2,
  offers: 1,
  rejected: 1,
  emails_sent: 9,
  emails_sent_today: 1,
  tasks_running: 0,
  ai_cost_month_usd: '1.2345',
  by_source: [{ key: 'linkedin_post', applied: 8, responded: 3, rate: 0.375 }],
  by_resume: [{ key: 'tailored', applied: 6, responded: 3, rate: 0.5 }],
  activity: [
    {
      application_id: 'a1',
      job_title: 'Data Scientist',
      company: 'Concentrix',
      to_status: 'interview',
      source: 'email_reply',
      note: 'Asks for a call on Thursday',
      at: '2026-10-03T09:51:00Z',
    },
  ],
}

describe('Dashboard (home page)', () => {
  it('shows the key numbers, the pipeline and recent activity', async () => {
    mockApi({ 'GET /dashboard': DASHBOARD })
    renderWithProviders(<HomePage />)

    const numbers = await screen.findByRole('region', { name: 'Key numbers' })
    expect(within(numbers).getByRole('link', { name: 'Jobs found: 42' })).toHaveAttribute(
      'href',
      '/jobs',
    )
    expect(within(numbers).getByText('36% response rate')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /2 applications? waiting for your approval/ }),
    ).toHaveAttribute('href', '/outbox')
    const pipeline = screen.getByRole('list', { name: 'Applications per stage' })
    expect(within(pipeline).getByTitle('Applied: 5')).toBeInTheDocument()
    expect(screen.getByText('LinkedIn posts')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument() // tailored resume rate
    expect(screen.getByRole('link', { name: 'Data Scientist' })).toHaveAttribute(
      'href',
      '/applications/a1',
    )
    expect(screen.getByText('$1.23')).toBeInTheDocument()
  })

  it('shows this month’s usage against the limits', async () => {
    mockApi({
      'GET /dashboard': DASHBOARD,
      'GET /usage': {
        jsearch_month: { used: 57, limit: 60, left: 3 },
        apify_month: { used: 2, limit: 20, left: 18 },
        apify_today: { used: 1, limit: 0, left: null },
        resets_at: '2026-11-01T00:00:00Z',
        cached_hits_month: 4,
        ai_spent_month_usd: '1.2345',
        ai_budget_usd: '5.00',
      },
    })
    renderWithProviders(<HomePage />)

    expect(await screen.findByText('57 / 60')).toBeInTheDocument()
    expect(screen.getByRole('meter', { name: 'Job searches requests this month' })).toHaveAttribute(
      'aria-valuenow',
      '57',
    )
    expect(screen.getByText('1 · no limit')).toBeInTheDocument()
    expect(screen.getByText('$1.23 / $5.00')).toBeInTheDocument()
    expect(screen.getByText(/reused for free \(4 this month\)/)).toBeInTheDocument()
  })
})

describe('Admin › Analytics', () => {
  it('shows paid search calls next to cache hits', async () => {
    mockApi({
      'GET /admin/analytics': {
        users_by_status: { approved: 2 },
        jobs_in_catalog: 10,
        applications_total: 3,
        emails_sent_30d: 1,
        ai_cost_month_usd: '0.04',
        ai_calls_month: 95,
        ai_cost_by_feature: [],
        users: [],
        failed_tasks_7d: 0,
        providers: [
          {
            provider: 'jsearch',
            calls: 3,
            cache_hits: 9,
            cache_rate: 0.75,
            units: 3,
            cost_usd: '0',
            failed: 0,
          },
        ],
        jsearch_quota_remaining: 97,
      },
      'GET /admin/errors': [],
    })
    renderWithProviders(<AnalyticsPage />)

    const row = (await screen.findByText('JSearch (job search)')).closest('tr')
    expect(within(row).getByText('(75%)')).toBeInTheDocument()
    expect(within(row).getByText('3 requests')).toBeInTheDocument()
    expect(screen.getByText(/JSearch plan: 97 requests left/)).toBeInTheDocument()
  })
})

describe('Notification centre', () => {
  it('filters by kind and unread', async () => {
    const fetchMock = mockApi({
      'GET /notifications': {
        items: [
          {
            id: 'n1',
            type: 'reply_status',
            title: 'An interview invite — Data Scientist',
            body: 'Status set to interview.',
            link: '/applications/a1',
            severity: 'success',
            read_at: null,
            created_at: '2026-10-03T09:51:00Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 30,
      },
      'POST /notifications/n1/read': { id: 'n1' },
    })
    renderWithProviders(<NotificationsPage />)

    expect(await screen.findByText('An interview invite — Data Scientist')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Kind'), 'replies')
    await userEvent.click(screen.getByRole('tab', { name: 'Unread' }))
    await userEvent.click(screen.getByRole('button', { name: 'Mark read' }))

    await vi.waitFor(() => {
      const urls = fetchMock.mock.calls.map(([url]) => String(url))
      expect(
        urls.some((u) => u.includes('category=replies') && u.includes('unread_only=true')),
      ).toBe(true)
      expect(urls.some((u) => u.endsWith('/notifications/n1/read'))).toBe(true)
    })
  })
})

describe('Admin › Audit log', () => {
  it('lists entries and filters by action', async () => {
    const fetchMock = mockApi({
      'GET /admin/audit': {
        items: [
          {
            id: 'x1',
            created_at: '2026-10-03T10:00:00Z',
            actor_type: 'admin',
            user_email: 'admin@example.com',
            action: 'platform.automation_fetch',
            entity_type: 'app_settings',
            entity_id: null,
            data: { enabled: true },
            ip_address: null,
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
      },
    })
    renderWithProviders(<AuditLogPage />)

    expect(await screen.findByText('platform.automation_fetch')).toBeInTheDocument()
    expect(screen.getByText('{"enabled":true}')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Action'), 'user.')

    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes('action=user.'))).toBe(true),
    )
  })
})

describe('Account › Your data', () => {
  it('deletes the account only with email and password, then signs out', async () => {
    const logout = vi.fn()
    let attempts = 0
    const fetchMock = mockApi({
      'POST /users/me/delete': () => {
        attempts += 1
        return attempts === 1
          ? errorResponse(422, 'WRONG_PASSWORD', 'The password is not correct.')
          : new Response(null, { status: 204 })
      },
    })
    renderWithProviders(<AccountDataCard />, { auth: makeAuth({ logout }) })

    await userEvent.click(screen.getByRole('button', { name: 'Delete account' }))
    const confirm = screen.getByRole('button', { name: 'Delete my account' })
    expect(confirm).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/Type your email/), 'person@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong')
    await userEvent.click(confirm)
    expect(await screen.findByRole('alert')).toHaveTextContent('The password is not correct.')
    await userEvent.click(confirm)

    await vi.waitFor(() => expect(logout).toHaveBeenCalled())
    const body = JSON.parse(fetchMock.mock.calls.at(-1)[1].body)
    expect(body).toEqual({ password: 'wrong', confirm_email: 'person@example.com' })
  })
})

describe('Jobs › Import', () => {
  it('uploads a CSV and shows what was imported', async () => {
    const fetchMock = mockApi({
      'POST /imports/legacy': () =>
        jsonResponse({
          kind: 'leads',
          rows: 3,
          jobs_created: 2,
          jobs_existing: 0,
          contacts_created: 2,
          contacts_existing: 0,
          already_emailed: 1,
          skipped: ['Row 4: no valid email'],
          skipped_count: 1,
        }),
    })
    renderWithProviders(<ImportPage />)

    const csv = new File(['email,post_url\n'], 'leads.csv', { type: 'text/csv' })
    await userEvent.upload(screen.getByTestId('import-file'), csv)

    expect(await screen.findByText('Imported LinkedIn leads (3 rows)')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Review contacts' })).toHaveAttribute(
      'href',
      '/contacts?approval=pending',
    )
    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/imports/legacy'))
    expect(init.body.get('file').name).toBe('leads.csv')
  })
})
