import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { COUNTS, makeJob } from '@/test/jobFixtures'
import { jsonResponse, mockApi, renderWithProviders } from '@/test/utils'

import JobsPage from './JobsPage'

afterEach(() => vi.unstubAllGlobals())

const page = (items) => ({ items, total: items.length, page: 1, page_size: 20 })

describe('JobsPage', () => {
  it('lists jobs with their state, quality and apply link', async () => {
    mockApi({
      'GET /jobs': page([
        makeJob(),
        makeJob({ id: 'j2', title: 'Flutter Dev', description_quality: 'missing', state: 'saved' }),
      ]),
      'GET /jobs/counts': COUNTS,
    })
    renderWithProviders(<JobsPage />)

    expect(await screen.findByRole('link', { name: 'React Native Developer' })).toHaveAttribute(
      'href',
      '/jobs/j1',
    )
    expect(screen.getByText('No description')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Apply for React Native Developer/ })).toHaveAttribute(
      'href',
      'https://abctech.com/careers/1',
    )
    expect(screen.getByRole('tab', { name: /Inbox/ })).toHaveTextContent('3') // new + saved
    expect(screen.getByRole('tab', { name: /Skipped/ })).toHaveTextContent('3')
  })

  it('exports the current tab as CSV', async () => {
    const createObjectURL = vi.fn(() => 'blob:jobs')
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }))
    const fetchMock = mockApi({
      'GET /jobs': page([makeJob()]),
      'GET /jobs/counts': COUNTS,
      'GET /jobs/export.csv': () =>
        new Response('﻿Title\r\nReact Native Developer\r\n', {
          headers: {
            'Content-Type': 'text/csv',
            'Content-Disposition': 'attachment; filename="jobs-saved-2026-10-02.csv"',
          },
        }),
    })
    renderWithProviders(<JobsPage />, { route: '/jobs?state=saved&page=2' })
    await screen.findByText('React Native Developer')

    await userEvent.click(screen.getByLabelText('with descriptions'))
    await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }))

    await vi.waitFor(() => expect(createObjectURL).toHaveBeenCalled())
    const url = String(fetchMock.mock.calls.find(([u]) => String(u).includes('export.csv'))[0])
    expect(url).toContain('state=saved')
    expect(url).toContain('include_description=true')
    expect(url).not.toContain('page=') // every page is exported
  })

  it('sends filters to the API and skips a job', async () => {
    const fetchMock = mockApi({
      'GET /jobs': page([makeJob()]),
      'GET /jobs/counts': COUNTS,
      'PATCH /jobs/j1': () => jsonResponse(makeJob({ state: 'skipped' })),
    })
    renderWithProviders(<JobsPage />)
    await screen.findByText('React Native Developer')

    await userEvent.click(screen.getByRole('tab', { name: /Saved/ }))
    await userEvent.selectOptions(screen.getByLabelText('Sort'), 'company')
    await userEvent.type(screen.getByLabelText('Title or company'), 'react{Enter}')

    await vi.waitFor(() => {
      const last = String(
        fetchMock.mock.calls.filter(([u]) => String(u).includes('/jobs?')).at(-1)[0],
      )
      expect(last).toContain('state=saved')
      expect(last).toContain('sort=company')
      expect(last).toContain('q=react')
    })

    await userEvent.click(screen.getByRole('button', { name: 'Skip React Native Developer' }))
    await vi.waitFor(() => {
      const patch = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
      expect(JSON.parse(patch[1].body)).toEqual({ state: 'skipped' })
    })
  })
})
