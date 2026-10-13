import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { makeSaved } from '@/test/jobFixtures'
import { jsonResponse, mockApi, renderWithProviders } from '@/test/utils'

import SavedSearchesPage from './SavedSearchesPage'

afterEach(() => vi.unstubAllGlobals())

const bodyOf = (fetchMock, method) =>
  JSON.parse(fetchMock.mock.calls.find(([, init]) => init?.method === method)[1].body)

describe('SavedSearchesPage', () => {
  it('shows schedules and pauses or runs a search', async () => {
    const fetchMock = mockApi({
      'GET /saved-searches': [
        makeSaved(),
        makeSaved({ id: 's2', name: 'Weekly', schedule_cron: '15 7 * * 2', is_active: false }),
      ],
      'PATCH /saved-searches/s1': () => jsonResponse(makeSaved({ is_active: false })),
      'POST /saved-searches/s1/run': { task_id: 't', run_id: 'r' },
    })
    renderWithProviders(<SavedSearchesPage />)

    expect(await screen.findByText(/Every day at 08:00/)).toBeInTheDocument()
    expect(screen.getByText(/Custom: 15 7 \* \* 2/)).toBeInTheDocument()
    expect(screen.getByText('Paused')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Pause RN Hyderabad' }))
    await vi.waitFor(() => expect(bodyOf(fetchMock, 'PATCH')).toEqual({ is_active: false }))

    await userEvent.click(screen.getAllByRole('button', { name: 'Run now' })[0])
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/s1/run'))).toBe(true),
    )
  })

  it('creates a saved search with a custom schedule', async () => {
    const fetchMock = mockApi({
      'GET /saved-searches': [],
      'POST /saved-searches': () => jsonResponse(makeSaved(), { status: 201 }),
    })
    renderWithProviders(<SavedSearchesPage />)
    await screen.findByText(/No saved searches yet/)

    await userEvent.click(screen.getByRole('button', { name: 'New saved search' }))
    await userEvent.type(screen.getByLabelText('Name'), 'Remote RN')
    await userEvent.type(screen.getByLabelText('Keywords'), 'React Native')
    await userEvent.selectOptions(screen.getByLabelText('Schedule'), 'custom')
    await userEvent.type(screen.getByLabelText('Cron schedule'), '30 7 * * 1-5')
    await userEvent.click(screen.getByLabelText('Remote jobs only'))
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))

    await vi.waitFor(() =>
      expect(bodyOf(fetchMock, 'POST')).toEqual({
        name: 'Remote RN',
        keywords: 'React Native',
        location: null,
        experience: null,
        remote_only: true,
        country: 'in',
        schedule_cron: '30 7 * * 1-5',
        kind: 'jobs',
      }),
    )
    expect(screen.queryByLabelText('What to fetch')).not.toBeInTheDocument() // not allowed
  })

  it('schedules recruiter emails when the admin allows it, and shows an admin pause', async () => {
    const fetchMock = mockApi({
      'GET /saved-searches': [
        makeSaved({
          id: 's9',
          name: 'RN emails',
          kind: 'linkedin',
          max_posts: 25,
          paused_reason: 'Recruiter-email searches were turned off by an admin.',
        }),
      ],
      'GET /users/me/settings': { linkedin_schedule_allowed: true },
      'GET /usage': { max_posts_per_fetch: 15 }, // admin cap
      'POST /saved-searches': () => jsonResponse(makeSaved(), { status: 201 }),
    })
    renderWithProviders(<SavedSearchesPage />)

    expect(await screen.findByText('Recruiter emails')).toBeInTheDocument()
    expect(screen.getByText(/turned off by an admin/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run now' })).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'New saved search' }))
    await userEvent.selectOptions(await screen.findByLabelText('What to fetch'), 'linkedin')
    expect(screen.queryByLabelText('Location')).not.toBeInTheDocument()
    const posts = screen.getByLabelText('Posts per fetch')
    await vi.waitFor(() =>
      expect([...posts.options].map((o) => o.value)).toEqual(['5', '10', '15']),
    )
    await userEvent.selectOptions(posts, '10')
    await userEvent.type(screen.getByLabelText('Name'), 'RN')
    await userEvent.type(screen.getByLabelText('Keywords'), 'React Native')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))

    await vi.waitFor(() =>
      expect(bodyOf(fetchMock, 'POST')).toMatchObject({
        kind: 'linkedin',
        keywords: 'React Native',
        schedule_cron: '0 9 * * *',
        posted_limit: '24h',
        max_posts: 10,
      }),
    )
  })
})
