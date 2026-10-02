import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { makeJob, makeRun } from '@/test/jobFixtures'
import { mockApi, renderWithProviders } from '@/test/utils'

import JobSearchPage from './JobSearchPage'

afterEach(() => vi.unstubAllGlobals())

describe('JobSearchPage', () => {
  it('fills the form from a suggested role and shows the results', async () => {
    const fetchMock = mockApi({
      'GET /jobs/suggested-roles': {
        roles: ['Mobile Engineer'],
        location: 'Hyderabad',
        hint: null,
      },
      'GET /jobs/searches': [],
      'POST /jobs/search': { task_id: 't1', run_id: 'r1' },
      'GET /jobs/searches/r1': {
        ...makeRun({ results_count: 2, new_jobs_count: 1, can_load_more: true }),
        jobs: [
          { ...makeJob(), is_new: true },
          { ...makeJob({ id: 'j2', title: 'Mobile Dev' }), is_new: false },
        ],
      },
      'POST /jobs/searches/r1/more': { task_id: 't2', run_id: 'r1' },
    })
    renderWithProviders(<JobSearchPage />)

    await userEvent.click(await screen.findByRole('button', { name: 'Mobile Engineer' }))
    expect(screen.getByLabelText('Location')).toHaveValue('Hyderabad')
    await userEvent.selectOptions(screen.getByLabelText('Experience'), 'under_3_years_experience')
    await userEvent.click(screen.getByLabelText('Remote jobs only'))
    await userEvent.selectOptions(screen.getByLabelText('Results'), '2')
    await userEvent.click(screen.getByRole('button', { name: 'Search jobs' }))

    expect(
      await screen.findByText('2 jobs · 1 just added · 1 already in your list'),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'React Native Developer' })).toBeInTheDocument()
    expect(screen.getByText('Just added')).toBeInTheDocument()
    expect(screen.getByText('Already in your list')).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(post[1].body)).toEqual({
      keywords: 'Mobile Engineer',
      location: 'Hyderabad',
      experience: 'under_3_years_experience',
      remote_only: true,
      country: 'in',
      date_posted: 'week',
      num_pages: 2,
    })

    await userEvent.click(screen.getByRole('button', { name: 'Load more results' }))
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/r1/more'))).toBe(true),
    )
  })

  it('validates keywords and shows the resume hint', async () => {
    const fetchMock = mockApi({
      'GET /jobs/suggested-roles': {
        roles: [],
        location: null,
        hint: 'Upload a resume to get role suggestions.',
      },
      'GET /jobs/searches': [],
    })
    renderWithProviders(<JobSearchPage />)

    expect(await screen.findByText(/Upload a resume/)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Job title or keywords'), 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Search jobs' }))

    expect(await screen.findByText('Enter at least 2 characters.')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  })
})
