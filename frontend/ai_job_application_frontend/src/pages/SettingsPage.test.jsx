import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse, makeAuth, makeUser, mockApi, renderWithProviders } from '@/test/utils'

import SettingsPage from './SettingsPage'

const SETTINGS = {
  threshold_use_master: 85,
  threshold_tailor: 65,
  score_weights: { skills: 40, experience: 25, technology: 20, education: 10, location: 5 },
  auto_analyze_new_jobs: true,
  daily_send_cap: 25,
  send_interval_seconds: 90,
  recipient_cooldown_days: 30,
  follow_up_days: 7,
  no_response_days: 21,
  linkedin_source_enabled: false,
  automation_enabled: false,
  automation_min_score: 70,
  automation_keywords: ['React Native'],
  automation_interval_hours: 24,
  automation_max_jobs: 5,
  automation_posted_limit: 'week',
  automation_tailor: true,
  automation_cover_letter: true,
  monthly_ai_budget_usd: '5.00',
}

afterEach(() => vi.unstubAllGlobals())

async function setValue(label, value) {
  const input = screen.getByLabelText(label)
  await userEvent.clear(input)
  await userEvent.type(input, String(value))
}

describe('SettingsPage', () => {
  it('sends only the fields that changed', async () => {
    const fetchMock = mockApi({
      'GET /users/me/settings': SETTINGS,
      'PATCH /users/me/settings': (_url, init) =>
        jsonResponse({ ...SETTINGS, ...JSON.parse(init.body) }),
    })
    renderWithProviders(<SettingsPage />)

    await screen.findByLabelText('Daily send limit')
    await setValue('Daily send limit', 10)
    await userEvent.click(screen.getByRole('button', { name: 'Save settings' }))

    const patch = await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
      if (!call) throw new Error('not yet')
      return call
    })
    expect(JSON.parse(patch[1].body)).toEqual({ daily_send_cap: 10 })
  })

  it('sends automation keywords as a list', async () => {
    const fetchMock = mockApi({
      'GET /users/me/settings': SETTINGS,
      'PATCH /users/me/settings': (_url, init) =>
        jsonResponse({ ...SETTINGS, ...JSON.parse(init.body) }),
    })
    renderWithProviders(<SettingsPage />)

    const label = 'Keywords for fetching new jobs (comma-separated, up to 5)'
    await screen.findByLabelText(label)
    await setValue(label, 'React Native, Flutter ,')
    await userEvent.selectOptions(screen.getByLabelText('Fetch posts from the last'), 'month')
    await userEvent.click(screen.getByRole('button', { name: 'Save settings' }))

    const patch = await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
      if (!call) throw new Error('not yet')
      return call
    })
    expect(JSON.parse(patch[1].body)).toEqual({
      automation_keywords: ['React Native', 'Flutter'],
      automation_posted_limit: 'month',
    })
  })

  it('lets an admin unlock "Fetch new jobs & automate"', async () => {
    const fetchMock = mockApi({
      'GET /users/me/settings': SETTINGS,
      'GET /integrations/gmail': { configured: true, connected: false },
      'GET /admin/platform': { automation_fetch_enabled: false },
      'PATCH /admin/platform': (_url, init) => jsonResponse(JSON.parse(init.body)),
    })
    renderWithProviders(<SettingsPage />, { auth: makeAuth({ user: makeUser({ role: 'admin' }) }) })

    await userEvent.click(
      await screen.findByRole('checkbox', { name: /Allow “Fetch new jobs & automate”/ }),
    )

    await vi.waitFor(() => {
      const patch = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith('/admin/platform') && init?.method === 'PATCH',
      )
      expect(JSON.parse(patch[1].body)).toEqual({ automation_fetch_enabled: true })
    })
  })

  it('lets an admin change the per-user search limits', async () => {
    const PLATFORM = {
      automation_fetch_enabled: false,
      jsearch_requests_per_month: 60,
      apify_posts_per_month: 300,
      apify_max_posts_per_fetch: 25,
      apify_runs_per_day: 3,
      jsearch_max_pages: 1,
      jsearch_allow_load_more: true,
      interviews_per_month: 10,
      interview_minutes: 6,
    }
    const fetchMock = mockApi({
      'GET /users/me/settings': SETTINGS,
      'GET /integrations/gmail': { configured: true, connected: false },
      'GET /admin/platform': PLATFORM,
      'PATCH /admin/platform': (_url, init) =>
        jsonResponse({ ...PLATFORM, ...JSON.parse(init.body) }),
    })
    renderWithProviders(<SettingsPage />, { auth: makeAuth({ user: makeUser({ role: 'admin' }) }) })

    const save = await screen.findByRole('button', { name: 'Save limits' })
    expect(save).toBeDisabled() // nothing changed yet
    const field = screen.getByLabelText('Job-search requests per user / month')
    await userEvent.clear(field)
    await userEvent.type(field, '100')
    await userEvent.selectOptions(screen.getByLabelText('Most jobs per search'), '2')
    await userEvent.selectOptions(screen.getByLabelText('Most posts per LinkedIn fetch'), '50')
    await userEvent.click(screen.getByRole('checkbox', { name: /Allow “Load more”/ }))
    await userEvent.click(save)

    await vi.waitFor(() => {
      const patch = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith('/admin/platform') && init?.method === 'PATCH',
      )
      expect(JSON.parse(patch[1].body)).toEqual({
        jsearch_requests_per_month: 100,
        jsearch_max_pages: 2,
        jsearch_allow_load_more: false,
        apify_max_posts_per_fetch: 50,
      })
    })
  })

  it('does not show platform switches to normal users', async () => {
    mockApi({ 'GET /users/me/settings': SETTINGS })
    renderWithProviders(<SettingsPage />)

    await screen.findByLabelText('Daily send limit')
    expect(screen.queryByText('Platform (admin)')).not.toBeInTheDocument()
  })

  it('requires score weights that add up to 100', async () => {
    const fetchMock = mockApi({ 'GET /users/me/settings': SETTINGS })
    renderWithProviders(<SettingsPage />)

    await screen.findByLabelText('Skills')
    await setValue('Skills', 50)
    await userEvent.click(screen.getByRole('button', { name: 'Save settings' }))

    expect(await screen.findByText('Weights must add up to 100')).toBeInTheDocument()
    expect(screen.getByText('(total 110 / 100)')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PATCH')).toBe(false)
  })

  it('requires the tailor threshold to be below the master threshold', async () => {
    mockApi({ 'GET /users/me/settings': SETTINGS })
    renderWithProviders(<SettingsPage />)

    await screen.findByLabelText('Tailor resume at score ≥')
    await setValue('Tailor resume at score ≥', 90)
    await userEvent.click(screen.getByRole('button', { name: 'Save settings' }))

    expect(
      await screen.findByText('Must be lower than the "use master resume" threshold'),
    ).toBeInTheDocument()
  })
})
