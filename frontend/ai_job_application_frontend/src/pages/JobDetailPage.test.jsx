import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { makeJobDetail } from '@/test/jobFixtures'
import { jsonResponse, mockApi, renderWithProviders } from '@/test/utils'

import JobDetailPage from './JobDetailPage'

afterEach(() => vi.unstubAllGlobals())

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/jobs/:jobId" element={<JobDetailPage />} />
    </Routes>,
    { route: '/jobs/j1' },
  )
}

describe('JobDetailPage', () => {
  it('shows the description, apply link and saves the job', async () => {
    let job = makeJobDetail()
    const fetchMock = mockApi({
      'GET /jobs/j1': () => jsonResponse(job),
      'PATCH /jobs/j1': () => jsonResponse((job = makeJobDetail({ state: 'saved' }))),
    })
    renderPage()

    expect(await screen.findByText('Responsibilities: build apps.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Apply' })).toHaveAttribute(
      'href',
      'https://abctech.com/careers/1',
    )
    expect(screen.queryByText(/no usable description/)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('button', { name: 'Saved' })).toBeInTheDocument()
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
    expect(JSON.parse(patch[1].body)).toEqual({ state: 'saved' })
  })

  it('offers fetch and paste for a job without a description', async () => {
    const pasted = 'Responsibilities: build React Native apps. Requirements: 3 years.'
    let job = makeJobDetail({ description: null, description_quality: 'missing' })
    const fetchMock = mockApi({
      'GET /jobs/j1': () => jsonResponse(job),
      'POST /jobs/j1/fetch-description': { task_id: 't9' },
      'GET /tasks/t9': {
        id: 't9',
        type: 'job_fetch_page',
        status: 'failed',
        progress: 20,
        error: 'The job page needs a login. Please paste the job description instead.',
      },
      'PATCH /jobs/j1': () =>
        jsonResponse((job = makeJobDetail({ description: pasted, has_own_description: true }))),
    })
    renderPage()

    expect(await screen.findByText(/no usable description/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Read it from the job page' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('needs a login')

    await userEvent.click(screen.getByRole('button', { name: 'Paste description' }))
    await userEvent.click(screen.getByLabelText('Job description'))
    await userEvent.paste(pasted) // a paste, like a real user (typing char by char is slow)
    await userEvent.click(screen.getByRole('button', { name: 'Save description' }))

    expect(await screen.findByText(pasted)).toBeInTheDocument()
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
    expect(JSON.parse(patch[1].body)).toEqual({ description: pasted })
  })
})
