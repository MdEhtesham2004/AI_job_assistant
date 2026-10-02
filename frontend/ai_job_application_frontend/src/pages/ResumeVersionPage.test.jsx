import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { makeReport, makeVersion, PARSED } from '@/test/resumeFixtures'
import { mockApi, renderWithProviders } from '@/test/utils'

import ResumeVersionPage from './ResumeVersionPage'

function detail(overrides) {
  return {
    ...makeVersion(),
    parsed: PARSED,
    download_url: '/api/v1/files/tok',
    ats_report: null,
    active_tasks: [],
    ...overrides,
  }
}

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/resumes/:versionId" element={<ResumeVersionPage />} />
    </Routes>,
    { route: '/resumes/v1' },
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('ResumeVersionPage', () => {
  it('shows the parsed resume and starts an ATS analysis', async () => {
    const fetchMock = mockApi({
      'GET /resumes/versions/v1': detail(),
      'POST /resumes/versions/v1/ats': { task_id: 't1' },
      'GET /tasks/t1': { id: 't1', type: 'resume_ats', status: 'running', progress: 10 },
    })
    renderPage()

    expect(await screen.findByText('Acme Apps', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('React Native')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Preview' })).toHaveAttribute(
      'href',
      '/api/v1/files/tok',
    )
    expect(screen.queryByRole('button', { name: /improved resume/ })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Run ATS analysis' }))

    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/v1/ats'))).toBe(true),
    )
    expect(await screen.findByRole('progressbar')).toHaveAttribute('aria-valuenow', '10')
  })

  it('shows the ATS report, follow-up actions and a copyable LinkedIn summary', async () => {
    const writeText = vi.fn().mockResolvedValue()
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })
    mockApi({
      'GET /resumes/versions/v1': detail({
        ats_report: makeReport({
          linkedin_summary: { headline: 'Mobile Engineer | React Native', about: 'I build apps.' },
        }),
      }),
    })
    renderPage()

    expect(await screen.findByLabelText('ATS score 72 out of 100')).toBeInTheDocument()
    expect(screen.getByText('GraphQL')).toBeInTheDocument()
    expect(screen.getByText('Add a projects section')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generate improved resume' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Copy headline' }))
    expect(writeText).toHaveBeenCalledWith('Mobile Engineer | React Native')
    expect(await screen.findByText('Copied')).toBeInTheDocument()
  })

  it('shows a parse failure with a retry button', async () => {
    mockApi({
      'GET /resumes/versions/v1': detail({
        parse_status: 'failed',
        parse_error: 'The AI returned an invalid answer.',
        parsed: null,
      }),
    })
    renderPage()

    expect(await screen.findByText(/The AI returned an invalid answer/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
